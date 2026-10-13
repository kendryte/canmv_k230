# mcbytepp/tracker.py - the McByte++ association pipeline.
#
# Per frame, in the paper's order (section 3.4):
#   1. Kalman prediction for every tracklet
#   2. conditional CMC correction of the predicted boxes
#   3. detections split high/low at a fixed 0.6
#   4. cost = 1 - IoU
#   5. mask cue subtracted where the match is ambiguous or isolated
#   6. Hungarian assignment, rejecting matches above the cost threshold
#   7. BYTE's second pass over low-confidence detections, then unconfirmed
#      tracks, then births and deaths
#   8. a long-term re-ID query for every newborn tracklet

from . import lap
from .cmc import ConditionalCMC
from .kalman import KalmanFilterXYAH
from .maskcue import MaskPropagator
from .reid import IdentityMemory, extract
from .strack import STrack, LOST, REMOVED, TRACKED


class McBytePlusPlus:
    def __init__(self, cfg, det_size=None, aux_size=None, frame_rate=30):
        self.cfg = cfg
        det_size = det_size or cfg.det_frame_size
        aux_size = aux_size or cfg.aux_size
        self.det_size = det_size

        self.tracked = []
        self.lost = []
        self.removed = []
        self.pending = []          # newborns still inside the re-ID window

        self.frame_id = 0
        self._next_id = 0
        self.max_time_lost = int(frame_rate / 30.0 * cfg.track_buffer)

        self.kf = KalmanFilterXYAH()
        self.cmc = ConditionalCMC(cfg, det_size)
        self.masks = MaskPropagator(cfg, det_size, aux_size)
        self.memory = IdentityMemory(cfg)

        self.stats = {"reid_hits": 0, "cmc_applied": 0, "cmc_skipped": 0,
                      "mask_hits": 0, "births": 0}

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    # ------------------------------------------------------------------ main
    def update(self, dets, aux_img=None, grid_buf=None):
        """dets: [[x1, y1, x2, y2, score], ...] in detector-frame coordinates."""
        self.frame_id += 1
        cfg = self.cfg
        activated, refind, newly_lost, newly_removed = [], [], [], []

        high = [STrack(d, d[4]) for d in dets if d[4] >= cfg.track_thresh]
        low = [STrack(d, d[4]) for d in dets
               if cfg.conf_low <= d[4] < cfg.track_thresh]

        unconfirmed = [t for t in self.tracked if not t.is_activated]
        tracked = [t for t in self.tracked if t.is_activated]
        pool = _joint(tracked, self.lost)

        # 1. predict ----------------------------------------------------------
        for t in pool:
            t.predict()
        for t in unconfirmed:
            t.predict()

        # 2. conditional camera motion compensation ---------------------------
        warp = self.cmc.estimate(aux_img)
        if warp is not None:
            dx, dy, scale = warp
            for t in pool:
                t.apply_cmc(dx, dy, scale)
            for t in unconfirmed:
                t.apply_cmc(dx, dy, scale)

        # Bound the predicted states before anything consumes them: absurd
        # geometry from a long-coasting tracklet would otherwise reach the
        # mask grid and the drawing code as out-of-range indices.
        fw, fh = self.det_size[0], self.det_size[1]
        for t in pool:
            t.clamp(fw, fh)
        for t in unconfirmed:
            t.clamp(fw, fh)

        # masks are evaluated in the corrected, propagated boxes
        self.masks.set_grid(grid_buf)
        self.masks.propagate(pool)

        # 3-6. first association, high-confidence detections -------------------
        boxes_high = [d.tlbr for d in high]
        cost = lap.iou_distance(pool, boxes_high)
        cost = self.masks.apply_guidance(cost, pool, boxes_high,
                                         cfg.match_thresh)
        matches, u_track, u_det = lap.linear_assignment(
            cost, cfg.match_thresh, len(pool), len(high))

        for it, idet in matches:
            t = pool[it]
            d = high[idet]
            if t.state == TRACKED:
                t.update(d, self.frame_id)
                activated.append(t)
            else:
                t.re_activate(d, self.frame_id)
                refind.append(t)
            self._observe(t, d, aux_img)

        # 7a. second association, low-confidence detections --------------------
        r_tracked = [pool[i] for i in u_track if pool[i].state == TRACKED]
        if low and r_tracked:
            boxes_low = [d.tlbr for d in low]
            cost2 = lap.iou_distance(r_tracked, boxes_low)
            cost2 = self.masks.apply_guidance(cost2, r_tracked, boxes_low,
                                              cfg.match_thresh_second)
            matches2, u_track2, _ = lap.linear_assignment(
                cost2, cfg.match_thresh_second, len(r_tracked), len(low))
            for it, idet in matches2:
                t = r_tracked[it]
                d = low[idet]
                if t.state == TRACKED:
                    t.update(d, self.frame_id)
                    activated.append(t)
                else:
                    t.re_activate(d, self.frame_id)
                    refind.append(t)
                self._observe(t, d, aux_img)
        else:
            u_track2 = list(range(len(r_tracked)))

        for i in u_track2:
            t = r_tracked[i]
            if t.state != LOST:
                t.mark_lost()
                newly_lost.append(t)

        # 7b. unconfirmed tracks against what is left --------------------------
        left = [high[i] for i in u_det]
        boxes_left = [d.tlbr for d in left]
        cost3 = lap.iou_distance(unconfirmed, boxes_left)
        matches3, u_unconf, u_det3 = lap.linear_assignment(
            cost3, cfg.match_thresh_unconfirmed, len(unconfirmed),
            len(boxes_left))
        for it, idet in matches3:
            t = unconfirmed[it]
            t.update(left[idet], self.frame_id)
            activated.append(t)
            self._observe(t, left[idet], aux_img)
        for i in u_unconf:
            t = unconfirmed[i]
            t.mark_removed()
            newly_removed.append(t)

        # 7c. births -----------------------------------------------------------
        for i in u_det3:
            d = left[i]
            if d.score < cfg.new_track_thresh:
                continue
            d.activate(self.kf, self.frame_id, self._new_id())
            self.masks.observe(d, d.tlbr)
            self._birth(d, aux_img)
            activated.append(d)
            self.stats["births"] += 1

        # 7d. deaths -----------------------------------------------------------
        for t in self.lost:
            if self.frame_id - t.end_frame > self.max_time_lost:
                t.mark_removed()
                newly_removed.append(t)
                if t.is_activated:
                    self.memory.deposit(t, self.frame_id)

        # bookkeeping ----------------------------------------------------------
        self.tracked = [t for t in self.tracked if t.state == TRACKED]
        self.tracked = _joint(self.tracked, activated)
        self.tracked = _joint(self.tracked, refind)
        self.lost = _sub(self.lost, self.tracked)
        self.lost.extend(newly_lost)
        self.lost = _sub(self.lost, newly_removed)
        self.removed.extend(newly_removed)
        if len(self.removed) > 256:
            self.removed = self.removed[-256:]
        self.tracked, self.lost = _remove_duplicates(self.tracked, self.lost)

        # 8. long-term re-ID ---------------------------------------------------
        self._resolve_pending()
        self.memory.expire(self.frame_id)

        self.stats["cmc_applied"] = self.cmc.applied
        self.stats["cmc_skipped"] = self.cmc.skipped
        self.stats["mask_hits"] = self.masks.hits
        return [t for t in self.tracked if t.is_activated]

    # --------------------------------------------------------------- re-ID
    def _observe(self, track, det, aux_img):
        """Refresh the appearance models of a track that just matched."""
        self.masks.observe(track, det.tlbr)
        cfg = self.cfg
        if not cfg.reid_enable or aux_img is None:
            return
        if det.score < cfg.reid_min_score:
            return
        if self.frame_id - track.last_feat_frame < cfg.reid_extract_stride:
            return
        feat = extract(aux_img, det.tlbr, self.det_size, cfg)
        track.add_feature(feat, self.frame_id)

    def _birth(self, track, aux_img):
        cfg = self.cfg
        if not cfg.reid_enable:
            return
        if aux_img is not None:
            track.add_feature(extract(aux_img, track.tlbr, self.det_size, cfg),
                              self.frame_id)
        track.reid_pending = True
        self.pending.append(track)

    def _resolve_pending(self):
        """Query the memory for newborns, and finalize those that time out."""
        cfg = self.cfg
        if not cfg.reid_enable or not self.pending:
            return
        window = cfg.reid_finalize_window
        alive = []
        for t in self.pending:
            if t.state == REMOVED or not t.reid_pending:
                continue
            if self.frame_id - t.start_frame > window:
                t.reid_pending = False       # confirmed as a fresh identity
                continue
            alive.append(t)
        self.pending = alive

        candidates = [t for t in alive if t.feat_avg is not None]
        for track, old_id in self.memory.query(candidates):
            track.track_id = old_id
            track.reid_inherited = True
            track.reid_pending = False
            self.stats["reid_hits"] += 1
        self.pending = [t for t in self.pending if t.reid_pending]

    def reset(self):
        self.tracked = []
        self.lost = []
        self.removed = []
        self.pending = []
        self.cmc.reset()


# ----------------------------------------------------------------- helpers
def _joint(list_a, list_b):
    out = list(list_a)
    seen = set(id(t) for t in list_a)
    for t in list_b:
        if id(t) not in seen:
            seen.add(id(t))
            out.append(t)
    return out


def _sub(list_a, list_b):
    drop = set(id(t) for t in list_b)
    return [t for t in list_a if id(t) not in drop]


def _remove_duplicates(list_a, list_b):
    """Drop the shorter of any two tracks sitting on top of each other."""
    if not list_a or not list_b:
        return list_a, list_b
    dup_a = set()
    dup_b = set()
    for i, ta in enumerate(list_a):
        for j, tb in enumerate(list_b):
            if lap.iou(ta.tlbr, tb.tlbr) < 0.85:
                continue
            age_a = ta.frame_id - ta.start_frame
            age_b = tb.frame_id - tb.start_frame
            if age_a > age_b:
                dup_b.add(j)
            else:
                dup_a.add(i)
    return ([t for i, t in enumerate(list_a) if i not in dup_a],
            [t for j, t in enumerate(list_b) if j not in dup_b])
