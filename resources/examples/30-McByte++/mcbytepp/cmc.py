# mcbytepp/cmc.py - conditional camera motion compensation (McByte++ section 3.2).
#
# WHAT THE PAPER DOES
#   ORB features are matched between consecutive downscaled frames, an affine
#   transform is fitted, and it is applied to the Kalman-predicted boxes before
#   association -- but only when the estimate passes a plausibility check.  An
#   unreliable estimate never overwrites the retained one.  Default downscale 4.
#
# WHAT RUNS HERE
#   There is no ORB on this firmware.  image.find_displacement() is a phase
#   correlation, which estimates whole-frame translation directly and hands
#   back a correlation peak response that makes an excellent reliability gate --
#   the "conditional" half of the method maps onto it almost exactly.  What is
#   lost is the affine part: translation is exact, and rotation/scale are only
#   available through the log-polar variant, which is off by default because
#   its response is weak on real scenes.  Pan and tilt are compensated; roll
#   and zoom are not, unless cmc_similarity is enabled.
#
#   find_displacement needs square power-of-two inputs (a 160x96 input silently
#   returns a zero displacement at zero response), hence cmc_size.  Aspect
#   distortion from squaring the frame is harmless for translation and is
#   undone when the shift is mapped back to tracking coordinates.

import image


class ConditionalCMC:
    def __init__(self, cfg, det_size):
        self.cfg = cfg
        n = cfg.cmc_size
        self.n = n
        self.sx = float(det_size[0]) / n     # cmc grid -> tracking coordinates
        self.sy = float(det_size[1]) / n
        self.cx = det_size[0] / 2.0
        self.cy = det_size[1] / 2.0
        self.prev = None
        self.held = None                     # last reliable (dx, dy, scale)
        self.hold_left = 0
        self.last_response = 0.0
        self.applied = 0
        self.skipped = 0

    def estimate(self, aux_img):
        """Return (dx, dy, scale) in tracking coordinates, or None to skip."""
        if not self.cfg.cmc_enable or aux_img is None:
            return None

        cur = aux_img.to_grayscale(x_size=self.n, y_size=self.n)
        prev = self.prev
        self.prev = cur
        if prev is None:
            return None

        try:
            d = cur.find_displacement(prev)
        except Exception:
            return self._hold()

        response = d.response()
        self.last_response = response
        dx = d.x_translation() * self.sx
        dy = d.y_translation() * self.sy
        if self.cfg.cmc_flip_y:
            dy = -dy

        scale = 1.0
        if self.cfg.cmc_similarity:
            try:
                lp = cur.find_displacement(prev, logpolar=True)
            except Exception:
                return self._hold()
            rot = lp.rotation()
            scale = lp.scale()
            if abs(rot) > self.cfg.cmc_max_rotation:
                return self._hold()
            hi = self.cfg.cmc_max_scale
            if scale > hi or scale < 1.0 / hi:
                return self._hold()

        if not self._plausible(response, dx, dy):
            return self._hold()

        if scale != 1.0:
            # Fold the centre of rotation into the translation so the track
            # update stays a single x' = s*x + dx.
            dx += self.cx * (1.0 - scale)
            dy += self.cy * (1.0 - scale)

        warp = (dx, dy, scale)
        self.held = warp
        self.hold_left = self.cfg.cmc_hold_frames
        self.applied += 1
        return warp

    def _plausible(self, response, dx, dy):
        if response < self.cfg.cmc_min_response:
            return False
        limit_x = self.cfg.cmc_max_shift_frac * self.cx * 2
        limit_y = self.cfg.cmc_max_shift_frac * self.cy * 2
        if abs(dx) > limit_x or abs(dy) > limit_y:
            return False
        return True

    def _hold(self):
        """Reuse the last reliable estimate, briefly, then give up on it."""
        self.skipped += 1
        if self.held is not None and self.hold_left > 0:
            self.hold_left -= 1
            return self.held
        return None

    def reset(self):
        self.prev = None
        self.held = None
        self.hold_left = 0
