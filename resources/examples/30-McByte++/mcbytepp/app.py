# mcbytepp/app.py - camera pipeline, LCD rendering, MOT output, main loop.
#
# Three sensor channels are used at once:
#   chn0  YUV420SP at panel resolution     -> bound straight to the video layer
#   chn1  RGB888, small                    -> CMC, mask cue, re-ID descriptors
#   chn2  RGBP888 at det_frame_size        -> the detector
# The aux channel is what makes the auxiliary CV cheap: everything that needs
# pixels rather than boxes reads a 320x192 image instead of a 1280x720 one.
#
# The overlay is drawn into an ARGB8888 OSD layer composited over the live
# video, and every dimension in it is derived from the panel size -- the same
# code gives readable output on an 800x480 LCD and on a 1080p HDMI screen.

import gc
import os
import time

import image
from media.display import *
from media.sensor import *

from .config import Config, apply_paper_thresholds, display_candidates
from .detector import PersonDetector, align_up
from .tracker import McBytePlusPlus

# ARGB8888: (alpha, r, g, b)
PALETTE = [
    (255, 255, 64, 64), (255, 64, 255, 64), (255, 64, 160, 255),
    (255, 255, 200, 0), (255, 255, 64, 255), (255, 0, 230, 230),
    (255, 255, 128, 0), (255, 160, 100, 255), (255, 120, 255, 180),
    (255, 230, 230, 230),
]
WHITE = (255, 255, 255, 255)
DIM = (255, 170, 170, 170)
ACCENT = (255, 120, 255, 180)

DISPLAY_MAP = {
    "hdmi": "LT9611", "lt9611": "LT9611", "lcd": "ST7701", "st7701": "ST7701",
    "hx8399": "HX8399", "nt35516": "NT35516", "nt35532": "NT35532",
    "gc9503": "GC9503", "aml020t": "AML020T", "jd9852": "JD9852",
    "ili9806": "ILI9806", "virt": "VIRT",
}


class Pipeline:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sensor = None
        self.osd_img = None
        self.display_size = None
        self.display_driver = None
        self.ai_frame = None
        self._gray = None
        self._grid = None
        self._grid_direct = True     # one-allocation grid path, until proven bad
        self.grid_size = [cfg.aux_size[0] // cfg.mask_grid_div,
                          cfg.aux_size[1] // cfg.mask_grid_div]
        self.dropped = 0             # frames the sensor refused to hand over

    # ------------------------------------------------------------- display
    def _init_display(self):
        """Bring up the first panel driver that initialises without error."""
        cfg = self.cfg
        last_error = None
        for name in display_candidates(cfg.display_mode):
            attr = DISPLAY_MAP.get(name)
            if attr is None or not hasattr(Display, attr):
                continue
            driver = getattr(Display, attr)
            # The virtual display has no panel to ask, so it needs a size given.
            size = cfg.display_size
            if size is None and name == "virt":
                size = [800, 480]
            try:
                if size:
                    Display.init(driver, width=size[0], height=size[1],
                                 osd_num=1, to_ide=cfg.display_to_ide)
                    self.display_size = list(size)
                else:
                    Display.init(driver, osd_num=1, to_ide=cfg.display_to_ide)
                    self.display_size = [Display.width(), Display.height()]
                if not self.display_size[0] or not self.display_size[1]:
                    raise RuntimeError("driver reported a zero-sized panel")
                self.display_driver = name
                print("[mcbytepp] display: %s %dx%d"
                      % (name, self.display_size[0], self.display_size[1]))
                return
            except Exception as e:
                last_error = e
                print("[mcbytepp] display %s failed (%r), trying next" % (name, e))
        raise RuntimeError("no usable display driver: %r" % (last_error,))

    def create(self):
        cfg = self.cfg
        # The sensor will round the aux width up to a multiple of 16 whatever
        # we ask for; pin it here so the tracker, the mask grid and the actual
        # frame all agree on one number.
        cfg.aux_size[0] = align_up(cfg.aux_size[0], 16)
        self.grid_size = [cfg.aux_size[0] // cfg.mask_grid_div,
                          cfg.aux_size[1] // cfg.mask_grid_div]
        os.exitpoint(os.EXITPOINT_ENABLE)
        self.sensor = Sensor(fps=cfg.sensor_fps)
        self.sensor.reset()
        if isinstance(cfg.sensor_hmirror, bool):
            self.sensor.set_hmirror(cfg.sensor_hmirror)
        if isinstance(cfg.sensor_vflip, bool):
            self.sensor.set_vflip(cfg.sensor_vflip)

        self._init_display()
        dw, dh = self.display_size

        # chn0 feeds the panel directly. The sensor is 16:9 and a typical LCD
        # is not, so this squeezes slightly rather than cropping -- detections
        # stay aligned either way, because both channels see the same FOV.
        self.sensor.set_framesize(w=dw, h=dh, chn=CAM_CHN_ID_0)
        self.sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)

        # Only configure the aux channel if it is going to be drained. An
        # enabled-but-unread channel is the classic way to starve the pool.
        if cfg.aux_enable:
            self.sensor.set_framesize(w=align_up(cfg.aux_size[0], 16),
                                      h=cfg.aux_size[1], chn=CAM_CHN_ID_1)
            self.sensor.set_pixformat(Sensor.RGB888, chn=CAM_CHN_ID_1)

        self.sensor.set_framesize(w=align_up(cfg.det_frame_size[0], 16),
                                  h=cfg.det_frame_size[1], chn=CAM_CHN_ID_2)
        self.sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)

        if cfg.sensor_framebuffers:
            try:
                self.sensor.set_framebuffers(cfg.sensor_framebuffers)
            except Exception as e:
                print("[mcbytepp] set_framebuffers ignored: %r" % (e,))

        self.osd_img = image.Image(dw, dh, image.ARGB8888)
        bind_info = self.sensor.bind_info(x=0, y=0, chn=CAM_CHN_ID_0)
        Display.bind_layer(**bind_info, layer=Display.LAYER_VIDEO1)
        self.sensor.run()
        print("[mcbytepp] channels: display+detector%s"
              % ("+aux" if cfg.aux_enable else " (aux OFF)"))

    # --------------------------------------------------------------- frames
    def _snapshot(self, chn):
        """A frame, or None. The firmware returns -1 when it cannot supply one,
        and calling image methods on that int is how a dropped frame turns
        into a crash three lines later."""
        img = self.sensor.snapshot(chn=chn)
        # NB: image.Image is a factory function here, not a class, so
        # isinstance(img, image.Image) raises TypeError rather than returning
        # False.  The firmware signals "no frame" with the int -1, which is
        # what the stock examples test for.
        if img is None or isinstance(img, int):
            self.dropped += 1
            return None
        return img

    def get_ai_frame(self):
        self.ai_frame = self._snapshot(CAM_CHN_ID_2)
        if self.ai_frame is None:
            return None
        return self.ai_frame.to_numpy_ref()

    def get_aux_frame(self, frame_id=0):
        """The aux frame, or None when the channel is off or being skipped.

        Everything downstream already treats a missing aux frame as "no CMC,
        no mask, no re-ID this frame", so skipping is safe -- it degrades the
        cues rather than breaking the tracker.
        """
        if not self.cfg.aux_enable:
            return None
        stride = self.cfg.aux_stride
        if stride > 1 and (frame_id % stride):
            return None
        return self._snapshot(CAM_CHN_ID_1)

    def make_grid(self, aux):
        """Luminance grid backing the mask cue.

        to_grayscale can resize on the way out, so this is one allocation per
        frame rather than a full-size grayscale copy plus a pooled one.  Every
        image allocated in the loop is pressure on a fixed pool, and halving
        that is worth more here than the slightly better antialiasing that
        mean_pool would give on a mask proxy.
        """
        gw, gh = self.grid_size
        if self._grid_direct:
            try:
                self._gray = None
                self._grid = aux.to_grayscale(x_size=gw, y_size=gh)
                return self._grid.bytearray()
            except Exception as e:
                print("[mcbytepp] resizing to_grayscale unavailable (%r);"
                      " falling back to mean_pool" % e)
                self._grid_direct = False
        div = self.cfg.mask_grid_div
        # bytearray() is a view into the image buffer, so both images have to
        # stay referenced for as long as the caller uses the returned buffer.
        self._gray = aux.to_grayscale()
        self._grid = self._gray.mean_pooled(div, div)
        return self._grid.bytearray()

    def show(self):
        Display.show_image(self.osd_img, 0, 0, Display.LAYER_OSD3)

    def destroy(self):
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        try:
            if self.sensor:
                self.sensor.stop()
        finally:
            Display.deinit()


class Renderer:
    """Draws the tracking overlay, scaled to whatever panel came up."""

    def __init__(self, cfg, det_size, display_size):
        self.cfg = cfg
        self.dw, self.dh = display_size
        self.sx = self.dw / float(det_size[0])
        self.sy = self.dh / float(det_size[1])

        # Everything is a fraction of panel height, so an 800x480 LCD and a
        # 1080p screen both get proportionate text and line weights.
        scale = cfg.osd_text_scale
        self.font = max(12, int(self.dh * 0.045 * scale))
        self.thick = max(1, int(self.dh / 300))
        self.hud_h = self.font + 8
        self.trails = {}

    # ------------------------------------------------------------- helpers
    def _box(self, track):
        b = track.tlbr
        x = int(b[0] * self.sx)
        y = int(b[1] * self.sy)
        w = int((b[2] - b[0]) * self.sx)
        h = int((b[3] - b[1]) * self.sy)
        return x, y, w, h

    def _text_w(self, text):
        return int(len(text) * self.font * 0.55)

    def _clip_rect(self, x, y, w, h):
        """Intersect a box with the panel, or None if it misses entirely.

        The firmware draw calls are not guaranteed to clip their inputs, and a
        person standing at the edge of frame produces a box with a negative
        origin.  Handing that straight to draw_rectangle is an out-of-bounds
        write into the framebuffer -- which takes the board down with no
        Python traceback, because no Python error ever happened.
        """
        x0 = x if x > 0 else 0
        y0 = y if y > 0 else 0
        x1 = x + w
        y1 = y + h
        if x1 > self.dw:
            x1 = self.dw
        if y1 > self.dh:
            y1 = self.dh
        if x1 <= x0 or y1 <= y0:
            return None
        return x0, y0, x1 - x0, y1 - y0

    def _inside(self, x, y):
        return 0 <= x < self.dw and 0 <= y < self.dh

    def _update_trails(self, tracks):
        """Keep a short history of each track's foot point, in panel pixels."""
        seen = {}
        limit = self.cfg.trail_length
        for t in tracks:
            b = t.tlbr
            cx = int((b[0] + b[2]) * 0.5 * self.sx)
            cy = int(b[3] * self.sy)            # bottom centre = ground contact
            pts = self.trails.get(t.track_id)
            pts = list(pts) if pts else []
            pts.append((cx, cy))
            if len(pts) > limit:
                pts = pts[-limit:]
            seen[t.track_id] = pts
        self.trails = seen                       # drops tracks that ended

    def _draw_trails(self, osd):
        for tid, pts in self.trails.items():
            if len(pts) < 2:
                continue
            base = PALETTE[tid % len(PALETTE)]
            n = len(pts)
            for i in range(1, n):
                ax, ay = pts[i - 1]
                bx, by = pts[i]
                # Trails are decoration; drop any segment that leaves the
                # panel rather than trusting the line drawer to clip it.
                if not (self._inside(ax, ay) and self._inside(bx, by)):
                    continue
                alpha = int(40 + 180 * i / n)    # older segments fade out
                osd.draw_line(ax, ay, bx, by,
                              color=(alpha, base[1], base[2], base[3]),
                              thickness=self.thick)

    def _draw_track(self, osd, track):
        x, y, w, h = self._box(track)
        if w <= 0 or h <= 0:
            return
        clipped = self._clip_rect(x, y, w, h)
        if clipped is None:
            return
        cx, cy, cw, ch = clipped
        color = PALETTE[track.track_id % len(PALETTE)]
        # A reclaimed identity gets a heavier box so it is obvious on a panel
        # you are watching from across the room.
        thickness = self.thick * 2 if track.reid_inherited else self.thick
        osd.draw_rectangle(cx, cy, cw, ch, color=color, thickness=thickness)

        if w < self.cfg.label_min_box or not self.cfg.draw_labels:
            return
        label = "%d" % track.track_id
        if track.reid_inherited:
            label += "*"
        # Above the box when there is room below the HUD, inside it otherwise.
        ty = y - self.font - 2
        if ty < self.hud_h + 2:
            ty = y + 2
        tx = x + 2
        # Only draw text whose whole extent lands on the panel: partially
        # off-panel glyph rendering is the riskiest call in this file.
        if tx < 0:
            tx = 0
        if not self._inside(tx, ty):
            return
        if tx + self._text_w(label) >= self.dw or ty + self.font >= self.dh:
            return
        osd.draw_string_advanced(tx, ty, self.font, label, color=color)

    def _draw_hud(self, osd, tracks, tracker, fps):
        osd.draw_rectangle(0, 0, self.dw, self.hud_h,
                           color=(150, 0, 0, 0), fill=True)
        s = tracker.stats
        left = "McByte++  %.0f fps  trk %d" % (fps, len(tracks))
        osd.draw_string_advanced(6, 3, self.font, left, color=WHITE)

        cmc_total = s["cmc_applied"] + s["cmc_skipped"]
        right = "re-ID %d  cmc %d/%d  ids %d" % (
            s["reid_hits"], s["cmc_applied"], cmc_total, tracker._next_id)
        rx = self.dw - self._text_w(right) - 6
        if rx > self._text_w(left) + 12:
            osd.draw_string_advanced(rx, 3, self.font, right, color=DIM)

        # A live marker while camera motion is actually being compensated.
        if tracker.cmc.hold_left or tracker.cmc.last_response > \
                self.cfg.cmc_min_response:
            r = max(3, self.font // 3)
            osd.draw_circle(self.dw - r - 4, self.hud_h + r + 4, r,
                            color=ACCENT, fill=True)

    # ---------------------------------------------------------------- entry
    def draw(self, osd, tracks, tracker, fps, clear=True):
        # clear=False lets a caller paint a background into the OSD first --
        # the self-test draws its synthetic scene there, since it has no
        # camera to put on the video layer.
        if clear:
            osd.clear()
        if self.cfg.draw_trails:
            self._update_trails(tracks)
            self._draw_trails(osd)
        for t in tracks:
            self._draw_track(osd, t)
        if self.cfg.hud_enable:
            self._draw_hud(osd, tracks, tracker, fps)


class MotWriter:
    """MOT Challenge format: frame, id, x, y, w, h, conf, -1, -1, -1."""

    def __init__(self, path, flush_every=60):
        self.path = path
        self.flush_every = flush_every
        self.lines = []
        self.failed = False
        if path:
            try:
                open(path, "w").close()
            except Exception as e:
                print("[mcbytepp] MOT output disabled:", repr(e))
                self.failed = True

    def add(self, frame_id, tracks):
        if not self.path or self.failed:
            return
        for t in tracks:
            x, y, w, h = t.tlwh
            self.lines.append("%d,%d,%.2f,%.2f,%.2f,%.2f,%.3f,-1,-1,-1"
                              % (frame_id, t.track_id, x, y, w, h, t.score))
        if len(self.lines) >= self.flush_every:
            self.flush()

    def flush(self):
        if not self.path or self.failed or not self.lines:
            return
        try:
            with open(self.path, "a") as f:
                f.write("\n".join(self.lines) + "\n")
            self.lines = []
        except Exception as e:
            print("[mcbytepp] MOT write failed, disabling:", repr(e))
            self.failed = True
            self.lines = []


def _shutdown(writer, det, pl):
    """Tear down in order, and never let one failure skip the rest.

    This matters more than it looks: an aborted run that leaves the sensor
    running or the nncase pool allocated makes the *next* run hang in
    Display.init or Sensor.reset, which reads like a random crash rather than
    a cleanup bug.  Any object may be None if we failed partway through
    starting up -- that is exactly the case that most needs cleaning up.
    """
    for label, obj, method in (("mot flush", writer, "flush"),
                               ("detector deinit", det, "deinit"),
                               ("pipeline destroy", pl, "destroy")):
        if obj is None:
            continue
        try:
            getattr(obj, method)()
        except Exception as e:
            print("[mcbytepp] %s failed: %r" % (label, e))
    try:
        gc.collect()
    except Exception:
        pass


def main(cfg=None):
    cfg = cfg or Config()
    if cfg.paper_thresholds:
        apply_paper_thresholds(cfg)
    # Everything from here on lives inside the try, so that a failure while
    # bringing the hardware up still reaches _shutdown.  Leaving a half-started
    # sensor behind makes the *next* run hang on Display.init, and then the
    # board has to be power-cycled to recover.
    pl = Pipeline(cfg)
    det = None
    writer = MotWriter(cfg.mot_output)
    fps = 0.0
    try:
        pl.create()
        det = PersonDetector(cfg)
        det_size = det.frame_size
        tracker = McBytePlusPlus(cfg, det_size, cfg.aux_size,
                                 frame_rate=cfg.sensor_fps)
        renderer = Renderer(cfg, det_size, pl.display_size)
        print("[mcbytepp] det %dx%d  aux %dx%d  grid %dx%d  thresholds %.2f/%.2f"
              % (det_size[0], det_size[1], cfg.aux_size[0], cfg.aux_size[1],
                 pl.grid_size[0], pl.grid_size[1],
                 cfg.track_thresh, cfg.new_track_thresh))

        last = time.ticks_ms()
        while True:
            os.exitpoint()
            if cfg.max_frames and tracker.frame_id >= cfg.max_frames:
                print("[mcbytepp] reached max_frames=%d" % cfg.max_frames)
                break

            t_snap = time.ticks_ms()
            ai = pl.get_ai_frame()
            if ai is None:
                # A dropped frame is survivable; pushing None downstream is not.
                continue
            # aux is legitimately None when the channel is off or skipped; the
            # tracker treats that as "no cues this frame", not as an error.
            aux = pl.get_aux_frame(tracker.frame_id)

            t_det = time.ticks_ms()
            dets = det.run(ai)
            t_trk = time.ticks_ms()
            grid = pl.make_grid(aux) if aux is not None else None
            tracks = tracker.update(dets, aux, grid)
            t_end = time.ticks_ms()

            writer.add(tracker.frame_id, tracks)
            if cfg.draw_boxes:
                renderer.draw(pl.osd_img, tracks, tracker, fps)
                pl.show()

            now = time.ticks_ms()
            dt = time.ticks_diff(now, last)
            last = now
            if dt > 0:
                inst = 1000.0 / dt
                fps = 0.9 * fps + 0.1 * inst if fps else inst

            if cfg.debug:
                line = ("f%d det=%d max=%.2f trk=%d lost=%d mem=%d drop=%d"
                        % (tracker.frame_id, det.last_count,
                           det.last_max_score, len(tracks),
                           len(tracker.lost), gc.mem_free(), pl.dropped))
                if cfg.debug >= 2:
                    # Where the frame time goes. If snap climbs, the camera is
                    # starving us; if track climbs, we are starving the camera.
                    line += ("  snap=%d det=%d track=%d draw=%d"
                             % (time.ticks_diff(t_det, t_snap),
                                time.ticks_diff(t_trk, t_det),
                                time.ticks_diff(t_end, t_trk),
                                time.ticks_diff(time.ticks_ms(), t_end)))
                print(line)
            elif cfg.print_stats_every and \
                    tracker.frame_id % cfg.print_stats_every == 0:
                s = tracker.stats
                print("[%d] %.1f fps | tracks %d | births %d | re-ID %d | "
                      "cmc %d/%d | mask %d | det %d/%.2f | mem %d | drop %d"
                      % (tracker.frame_id, fps, len(tracks), s["births"],
                         s["reid_hits"], s["cmc_applied"],
                         s["cmc_applied"] + s["cmc_skipped"], s["mask_hits"],
                         det.last_count, det.last_max_score, gc.mem_free(),
                         pl.dropped))
            gc.collect()
    except BaseException as e:
        # The IDE's stop button raises a plain Exception("IDE interrupt"), not
        # KeyboardInterrupt, so handle both cancellation forms explicitly.
        if isinstance(e, KeyboardInterrupt) or "IDE interrupt" in str(e):
            print("[mcbytepp] stopping: %r" % (e,))
        else:
            import sys
            sys.print_exception(e)
            raise
    finally:
        _shutdown(writer, det, pl)
        print("[mcbytepp] shutdown complete")
