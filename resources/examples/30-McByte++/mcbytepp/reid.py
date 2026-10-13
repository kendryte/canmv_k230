# mcbytepp/reid.py - online long-term re-identification (McByte++ section 3.3).
#
# WHAT THE PAPER DOES
#   An off-the-shelf OSNet embeds crops of reliable detections.  Features are
#   L2-normalised, averaged per tracklet, re-normalised, and parked in a
#   long-term memory when the tracklet dies.  Re-ID is never part of the
#   frame-to-frame cost -- it fires only when a new tracklet is born.  A match
#   requires mutual best agreement and cosine similarity above 0.8; on a match
#   the newcomer inherits the old ID and the memory entry is deleted.
#
# WHAT RUNS HERE
#   OSNet will not fit alongside the detector, so the embedding is a spatial
#   colour-layout descriptor: the crop is resampled to a 8x16 thumbnail and its
#   channels are read out as a 384-dim vector.  It is mean-centred before
#   normalisation, which matters -- raw colour vectors sit at cosine ~0.99 to
#   each other, and the paper's 0.8 threshold would accept everything.  After
#   centring, cosine similarity is the Pearson correlation of the two layouts
#   and 0.8 is once again a meaningful bar.
#
#   This descriptor keys on clothing colour and its vertical arrangement.  It
#   re-identifies people in differently coloured kit well and teammates in
#   identical kit badly -- which is exactly the case OSNet was trained to
#   handle.  Everything around the descriptor -- averaging, the memory, the
#   mutual-best rule, the threshold, deletion on match, delayed finalization --
#   is as published.

from .strack import _l2_normalise


def extract(aux_img, box, det_size, cfg):
    """Descriptor for a detection box, or None if the crop is unusable."""
    if aux_img is None:
        return None
    aw = aux_img.width()
    ah = aux_img.height()
    sx = float(aw) / det_size[0]
    sy = float(ah) / det_size[1]
    x0 = int(box[0] * sx)
    y0 = int(box[1] * sy)
    x1 = int(box[2] * sx + 0.5)
    y1 = int(box[3] * sy + 0.5)
    if x0 < 0:
        x0 = 0
    if y0 < 0:
        y0 = 0
    if x1 > aw:
        x1 = aw
    if y1 > ah:
        y1 = ah
    w = x1 - x0
    h = y1 - y0
    if w < cfg.reid_grid_w or h < cfg.reid_grid_h:
        return None
    # Belt and braces before handing a rectangle to the firmware: a ROI that
    # runs off the source image is an out-of-bounds read, not an exception.
    if x0 < 0 or y0 < 0 or x0 + w > aw or y0 + h > ah:
        return None

    try:
        thumb = aux_img.crop(roi=(x0, y0, w, h),
                             x_size=cfg.reid_grid_w,
                             y_size=cfg.reid_grid_h)
        buf = thumb.bytearray()
    except Exception:
        return None

    cells = cfg.reid_grid_w * cfg.reid_grid_h
    if cells == 0:
        return None
    bpp = len(buf) // cells
    vec = []
    if bpp >= 3:
        for i in range(cells):
            o = i * bpp
            vec.append(float(buf[o]))
            vec.append(float(buf[o + 1]))
            vec.append(float(buf[o + 2]))
    elif bpp == 2:                        # RGB565
        for i in range(cells):
            o = i * 2
            px = (buf[o] << 8) | buf[o + 1]
            vec.append(float((px >> 11) & 0x1F) * 8.0)
            vec.append(float((px >> 5) & 0x3F) * 4.0)
            vec.append(float(px & 0x1F) * 8.0)
    elif bpp == 1:                        # grayscale
        for i in range(cells):
            vec.append(float(buf[i]))
    else:
        return None

    # Centre, then normalise: cosine of the result is a correlation.
    mean = sum(vec) / len(vec)
    return _l2_normalise([v - mean for v in vec])


def cosine(a, b):
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


class IdentityMemory:
    """Features of tracklets that have ended, keyed by the ID they held."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.entries = []        # [track_id, feat, frame_deposited]

    def deposit(self, track, frame_id):
        if not self.cfg.reid_enable or track.feat_avg is None:
            return
        for e in self.entries:
            if e[0] == track.track_id:
                e[1] = track.feat_avg
                e[2] = frame_id
                return
        self.entries.append([track.track_id, track.feat_avg, frame_id])
        if len(self.entries) > self.cfg.reid_memory_size:
            self.entries.pop(0)      # oldest first

    def expire(self, frame_id):
        ttl = self.cfg.reid_memory_ttl
        if ttl <= 0:
            return
        self.entries = [e for e in self.entries if frame_id - e[2] <= ttl]

    def query(self, candidates):
        """Mutual-best matching between new tracklets and stored identities.

        candidates: tracklets with a feat_avg, awaiting finalization.
        Returns [(track, old_track_id), ...] and removes the entries used.
        """
        if not self.entries or not candidates:
            return []

        sims = []
        for t in candidates:
            f = t.feat_avg
            sims.append([cosine(f, e[1]) for e in self.entries])

        accepted = []
        used_entries = set()
        for i, t in enumerate(candidates):
            row = sims[i]
            bj = -1
            bv = -2.0
            for j, v in enumerate(row):
                if v > bv:
                    bv = v
                    bj = j
            if bj < 0 or bv < self.cfg.reid_sim_thresh or bj in used_entries:
                continue
            # The entry has to prefer this tracklet back.
            best_i = -1
            best_v = -2.0
            for k in range(len(candidates)):
                v = sims[k][bj]
                if v > best_v:
                    best_v = v
                    best_i = k
            if best_i != i:
                continue
            accepted.append((t, self.entries[bj][0]))
            used_entries.add(bj)

        if used_entries:
            self.entries = [e for j, e in enumerate(self.entries)
                            if j not in used_entries]
        return accepted
