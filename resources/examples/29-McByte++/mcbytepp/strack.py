# mcbytepp/strack.py - one tracklet.
#
# ByteTrack's STrack plus the two pieces McByte++ adds: an averaged appearance
# feature for long-term re-ID, and a propagated mask used as an association cue.

NEW = 0
TRACKED = 1
LOST = 2
REMOVED = 3


class STrack:
    def __init__(self, tlbr, score):
        self._tlbr = [float(v) for v in tlbr[:4]]
        self.score = float(score)
        self.kalman_filter = None
        self.mean = None
        self.covariance = None

        self.track_id = 0
        self.state = NEW
        self.is_activated = False
        self.tracklet_len = 0
        self.frame_id = 0
        self.start_frame = 0

        # --- re-ID: running average of L2-normalised features (McByte++ 3.3)
        self.feat_sum = None
        self.feat_count = 0
        self.feat_avg = None
        self.last_feat_frame = -1000
        self.reid_pending = False      # still inside the finalization window
        self.reid_inherited = False    # ID came from the long-term memory

        # --- mask cue: summed-area table over the mask grid (McByte++ 3.1)
        self.mask_sat = None
        self.mask_box = None           # (gx0, gy0, gw, gh) in grid cells
        self.mask_area = 0
        self.luma_lo = None
        self.luma_hi = None

    # ------------------------------------------------------------- geometry
    @property
    def tlbr(self):
        if self.mean is None:
            return self._tlbr
        x, y, a, h = (self.mean[0, 0], self.mean[0, 1],
                      self.mean[0, 2], self.mean[0, 3])
        w = a * h
        return [x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0]

    @property
    def tlwh(self):
        b = self.tlbr
        return [b[0], b[1], b[2] - b[0], b[3] - b[1]]

    @staticmethod
    def tlbr_to_xyah(tlbr):
        w = tlbr[2] - tlbr[0]
        h = tlbr[3] - tlbr[1]
        if h <= 0:
            h = 1e-3
        return [tlbr[0] + w / 2.0, tlbr[1] + h / 2.0, w / h, h]

    @property
    def end_frame(self):
        return self.frame_id

    # ------------------------------------------------------------ lifecycle
    def activate(self, kalman_filter, frame_id, track_id):
        self.kalman_filter = kalman_filter
        self.track_id = track_id
        self.mean, self.covariance = kalman_filter.initiate(
            self.tlbr_to_xyah(self._tlbr))
        self.tracklet_len = 0
        self.state = TRACKED
        # A track seen in the very first frame is trusted immediately; every
        # other one has to survive a second association before it is shown.
        self.is_activated = frame_id == 1
        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, det, frame_id, new_id=None):
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlbr_to_xyah(det.tlbr))
        self.tracklet_len = 0
        self.state = TRACKED
        self.is_activated = True
        self.frame_id = frame_id
        self.score = det.score
        if new_id is not None:
            self.track_id = new_id

    def update(self, det, frame_id):
        self.frame_id = frame_id
        self.tracklet_len += 1
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlbr_to_xyah(det.tlbr))
        self.state = TRACKED
        self.is_activated = True
        self.score = det.score

    def predict(self):
        if self.mean is None:
            return
        # A lost track is not moving as far as we know; damp its velocity the
        # way ByteTrack does so it does not drift off during the gap.
        if self.state != TRACKED:
            self.mean[0, 7] = 0.0
        self.mean, self.covariance = self.kalman_filter.predict(
            self.mean, self.covariance)

    def clamp(self, frame_w, frame_h):
        """Keep the filter state physically plausible.

        A tracklet coasting on prediction alone -- lost for many frames, or
        repeatedly scaled by CMC -- can drift its height towards zero or its
        centre thousands of pixels off frame.  Such a box is meaningless for
        association and actively dangerous downstream, because it reaches the
        firmware drawing calls as out-of-bounds geometry.  Bound it here, once,
        rather than defending against it in five other places.
        """
        m = self.mean
        if m is None:
            return
        h = m[0, 3]
        if h < 2.0:
            m[0, 3] = 2.0
        elif h > 4.0 * frame_h:
            m[0, 3] = 4.0 * frame_h
        a = m[0, 2]
        if a < 0.05:
            m[0, 2] = 0.05
        elif a > 10.0:
            m[0, 2] = 10.0
        # Allow one frame's worth of overshoot outside the image, no more.
        x = m[0, 0]
        if x < -frame_w:
            m[0, 0] = -frame_w
        elif x > 2.0 * frame_w:
            m[0, 0] = 2.0 * frame_w
        y = m[0, 1]
        if y < -frame_h:
            m[0, 1] = -frame_h
        elif y > 2.0 * frame_h:
            m[0, 1] = 2.0 * frame_h

    def mark_lost(self):
        self.state = LOST

    def mark_removed(self):
        self.state = REMOVED

    # ------------------------------------------------------------------ cmc
    def apply_cmc(self, dx, dy, scale=1.0):
        """Shift the predicted state by the estimated global camera motion."""
        if self.mean is None:
            return
        if scale != 1.0:
            self.mean[0, 0] = self.mean[0, 0] * scale + dx
            self.mean[0, 1] = self.mean[0, 1] * scale + dy
            self.mean[0, 3] = self.mean[0, 3] * scale
            self.mean[0, 4] = self.mean[0, 4] * scale
            self.mean[0, 5] = self.mean[0, 5] * scale
            self.mean[0, 7] = self.mean[0, 7] * scale
            # Uniformly scale the covariance by scale^2.
            self.covariance = self.covariance * (scale * scale)
        else:
            # Pure translation leaves the covariance untouched.
            self.mean[0, 0] = self.mean[0, 0] + dx
            self.mean[0, 1] = self.mean[0, 1] + dy

    # ---------------------------------------------------------------- re-ID
    def add_feature(self, feat, frame_id):
        """Accumulate an L2-normalised feature, per McByte++ eq. (4)-(5)."""
        if feat is None:
            return
        if self.feat_sum is None:
            self.feat_sum = list(feat)
            self.feat_count = 1
        else:
            for i in range(len(feat)):
                self.feat_sum[i] += feat[i]
            self.feat_count += 1
        self.last_feat_frame = frame_id
        self.feat_avg = _l2_normalise(self.feat_sum)


def _l2_normalise(vec):
    total = 0.0
    for v in vec:
        total += v * v
    if total <= 0:
        return None
    inv = 1.0 / (total ** 0.5)
    return [v * inv for v in vec]
