# mcbytepp/maskcue.py - the mask guidance signal (McByte++ section 3.1).
#
# WHAT THE PAPER DOES
#   EdgeTAM propagates a segmentation mask for every tracklet.  Two pixel-count
#   ratios are formed against each candidate detection box j:
#       mc = |mask_i n bbox_j| / |mask_i|     (coverage, a gate)
#       mf = |mask_i n bbox_j| / |bbox_j|     (fill, the discriminative term)
#   and where the match is ambiguous or isolated, the IoU cost is lowered:
#       cost = cost_iou - mf
#   gated on mf >= 0.05 and mc >= 0.90.
#
# WHAT RUNS HERE
#   EdgeTAM is a transformer; there is no room for it beside the detector on
#   this part.  The mask is instead produced by thresholding a coarse luminance
#   grid inside the tracklet's own predicted box, against a per-track luma band
#   learned from its matched detections and updated by EMA.  It is genuinely
#   propagated -- the box it is evaluated in comes from the Kalman prediction
#   after camera motion compensation, and the band is temporal state -- but it
#   is a proxy, not a segmentation.  Expect it to behave well when a subject
#   differs in brightness from the ground behind them and poorly otherwise.
#
#   Everything downstream of the mask -- both ratios, both thresholds, the
#   ambiguity/isolation regimes and the cost update -- is exactly as published.


class MaskPropagator:
    def __init__(self, cfg, det_size, aux_size):
        self.cfg = cfg
        div = cfg.mask_grid_div
        self.gw = aux_size[0] // div
        self.gh = aux_size[1] // div
        # tracking coordinates (detector frame) -> mask grid cells
        self.sx = float(self.gw) / det_size[0]
        self.sy = float(self.gh) / det_size[1]
        self.buf = None
        self.hits = 0          # cost entries adjusted, for reporting

    # ------------------------------------------------------------ per frame
    def set_grid(self, buf):
        """buf: gw*gh bytes of mean-pooled luminance for the current frame."""
        self.buf = buf

    def _to_grid(self, box):
        gx0 = int(box[0] * self.sx)
        gy0 = int(box[1] * self.sy)
        gx1 = int(box[2] * self.sx + 0.5)
        gy1 = int(box[3] * self.sy + 0.5)
        if gx0 < 0:
            gx0 = 0
        if gy0 < 0:
            gy0 = 0
        if gx1 > self.gw:
            gx1 = self.gw
        if gy1 > self.gh:
            gy1 = self.gh
        return gx0, gy0, gx1, gy1

    # --------------------------------------------------- appearance model
    def observe(self, track, box):
        """Refresh a track's luma band from the detection it just matched."""
        if self.buf is None or not self.cfg.mask_enable:
            return
        gx0, gy0, gx1, gy1 = self._to_grid(box)
        if gx1 <= gx0 or gy1 <= gy0:
            return
        # Sample the centre of the box: the border of a person box is mostly
        # background, and feeding that into the band would swallow the scene.
        f = self.cfg.mask_inner_frac
        mx = (gx1 - gx0) * (1.0 - f) / 2.0
        my = (gy1 - gy0) * (1.0 - f) / 2.0
        ix0 = int(gx0 + mx)
        iy0 = int(gy0 + my)
        ix1 = int(gx1 - mx)
        iy1 = int(gy1 - my)
        if ix1 <= ix0:
            ix1 = ix0 + 1
        if iy1 <= iy0:
            iy1 = iy0 + 1
        if ix1 > self.gw or iy1 > self.gh:
            return

        buf = self.buf
        gw = self.gw
        total = 0
        count = 0
        for gy in range(iy0, iy1):
            row = gy * gw
            for gx in range(ix0, ix1):
                total += buf[row + gx]
                count += 1
        if count == 0:
            return
        mean = total / count

        dev = 0
        for gy in range(iy0, iy1):
            row = gy * gw
            for gx in range(ix0, ix1):
                d = buf[row + gx] - mean
                dev += d if d >= 0 else -d
        mad = dev / count
        if mad < 4.0:           # a flat patch still needs a usable band
            mad = 4.0

        lo = mean - self.cfg.mask_band_k * mad
        hi = mean + self.cfg.mask_band_k * mad
        a = self.cfg.mask_band_ema
        if track.luma_lo is None:
            track.luma_lo = lo
            track.luma_hi = hi
        else:
            track.luma_lo = (1 - a) * track.luma_lo + a * lo
            track.luma_hi = (1 - a) * track.luma_hi + a * hi

    # ---------------------------------------------------------- propagation
    def propagate(self, tracks):
        """Rebuild every track's mask inside its propagated box."""
        if self.buf is None or not self.cfg.mask_enable:
            for t in tracks:
                t.mask_sat = None
            return
        for t in tracks:
            self._build(t)

    def _build(self, track):
        track.mask_sat = None
        track.mask_area = 0
        if track.luma_lo is None:
            return
        gx0, gy0, gx1, gy1 = self._to_grid(track.tlbr)
        bw = gx1 - gx0
        bh = gy1 - gy0
        if bw <= 0 or bh <= 0:
            return

        buf = self.buf
        gw = self.gw
        lo = track.luma_lo
        hi = track.luma_hi
        stride = bw + 1
        # Summed-area table, so that intersecting the mask with any detection
        # box later is O(1) instead of O(cells).
        sat = [0] * (stride * (bh + 1))
        area = 0
        for row in range(bh):
            src = (gy0 + row) * gw + gx0
            above = row * stride
            here = above + stride
            run = 0
            for col in range(bw):
                v = buf[src + col]
                if lo <= v <= hi:
                    run += 1
                sat[here + col + 1] = sat[above + col + 1] + run
            area += run
        if area < self.cfg.mask_min_cells:
            return
        track.mask_sat = sat
        track.mask_box = (gx0, gy0, bw, bh)
        track.mask_area = area

    def _intersect(self, track, box):
        """|mask n box| in grid cells."""
        sat = track.mask_sat
        gx0, gy0, bw, bh = track.mask_box
        bx0, by0, bx1, by1 = self._to_grid(box)
        # clamp the query to the mask's own extent, then localise
        x0 = bx0 - gx0
        y0 = by0 - gy0
        x1 = bx1 - gx0
        y1 = by1 - gy0
        if x0 < 0:
            x0 = 0
        if y0 < 0:
            y0 = 0
        if x1 > bw:
            x1 = bw
        if y1 > bh:
            y1 = bh
        if x1 <= x0 or y1 <= y0:
            return 0
        stride = bw + 1
        return (sat[y1 * stride + x1] - sat[y0 * stride + x1]
                - sat[y1 * stride + x0] + sat[y0 * stride + x0])

    # ------------------------------------------------------------- guidance
    def apply_guidance(self, cost, tracks, boxes, match_thresh):
        """cost <- cost - mf, for ambiguous or isolated pairs that pass the gates."""
        if not self.cfg.mask_enable or not cost or not boxes:
            return cost
        if not any(t.mask_sat for t in tracks):
            return cost

        margin = self.cfg.mask_ambiguity_margin
        row_min, row_second = _two_smallest_rows(cost)
        col_min, col_second = _two_smallest_cols(cost)

        for i, t in enumerate(tracks):
            if not t.mask_sat:
                continue
            row = cost[i]
            row_tie = (row_second[i] - row_min[i]) <= margin
            for j, box in enumerate(boxes):
                c = row[j]
                # Regime test: is this pair worth spending the cue on?
                isolated = c > match_thresh
                ambiguous = ((row_tie and (c - row_min[i]) <= margin)
                             or ((col_second[j] - col_min[j]) <= margin
                                 and (c - col_min[j]) <= margin))
                if not (isolated or ambiguous):
                    continue

                inter = self._intersect(t, box)
                if inter == 0:
                    continue
                area_box = ((box[2] - box[0]) * self.sx) * ((box[3] - box[1]) * self.sy)
                if area_box <= 0:
                    continue
                mf = inter / area_box
                mc = inter / float(t.mask_area)
                if mf < self.cfg.mask_mf_min or mc < self.cfg.mask_mc_min:
                    continue
                row[j] = c - mf
                self.hits += 1
        return cost


def _two_smallest_rows(cost):
    mins = []
    seconds = []
    for row in cost:
        m1 = m2 = 1e9
        for v in row:
            if v < m1:
                m2 = m1
                m1 = v
            elif v < m2:
                m2 = v
        mins.append(m1)
        seconds.append(m2)
    return mins, seconds


def _two_smallest_cols(cost):
    n = len(cost[0])
    mins = [1e9] * n
    seconds = [1e9] * n
    for row in cost:
        for j in range(n):
            v = row[j]
            if v < mins[j]:
                seconds[j] = mins[j]
                mins[j] = v
            elif v < seconds[j]:
                seconds[j] = v
    return mins, seconds
