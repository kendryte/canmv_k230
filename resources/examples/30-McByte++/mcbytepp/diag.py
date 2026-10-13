# mcbytepp/diag.py - find out which subsystem is killing the board.
#
# The failure to explain: the overlay renders on the LCD for a few seconds and
# then the board dies with no Python traceback at all.  No traceback means it
# is not an exception -- it is the firmware aborting or rebooting underneath
# MicroPython, which points at a resource (frame buffers, the nncase pool, the
# display layer) rather than at the tracking code.
#
# So bring the subsystems up one at a time, in the order they were added, and
# print the free heap as we go.  Whichever stage is on screen when the board
# stops talking is the culprit, and the memory trend says whether it starved
# or tripped over something.
#
#     import sys; sys.path.insert(0, "/sdcard")
#     from mcbytepp.diag import run; run()
#
# Stages, cumulative:
#   1  snapshot both camera channels             (sensor + buffer pool)
#   2  + draw the HUD and push it to the panel   (OSD layer + LCD)
#   3  + grayscale grid and phase correlation    (per-frame image allocation)
#   4  + the detector                            (kmodel + nncase pool)
#   5  + the tracker core, HUD only              (Kalman, association)
#   6  + the mask cue and re-ID                  (per-track crops, SATs)
#   7  + drawing the tracks themselves           (boxes, labels, trails)
#
# The last three stages are split deliberately.  The board survives
# indefinitely with zero tracks and dies seconds after detections appear, so
# the question is which track-only path kills it: the tracking arithmetic, the
# per-track image work, or the act of drawing a box -- and a box belonging to
# someone at the edge of frame is the first geometry here that goes negative.

import gc
import os
import time

from .app import Pipeline, Renderer
from .config import Config
from .detector import PersonDetector
from .tracker import McBytePlusPlus

STAGES = ("snapshots", "+display", "+imageops", "+detector",
          "+tracker core", "+mask & re-ID", "+track drawing")


def _mem():
    gc.collect()
    return gc.mem_free()


def _banner(stage, name, n):
    print("")
    print("=== stage %d: %s (%d frames) === mem %d" % (stage, name, n, _mem()))


def _grid_stats(buf):
    """Cheap sanity check that the aux channel is delivering a real picture."""
    n = len(buf)
    if not n:
        return 0, 0, 0.0
    step = max(1, n // 256)
    lo, hi, total, count = 255, 0, 0, 0
    for i in range(0, n, step):
        v = buf[i]
        if v < lo:
            lo = v
        if v > hi:
            hi = v
        total += v
        count += 1
    return lo, hi, total / float(count)


def drain_test(delay_ms=60, frames=150, cfg=None, aux=True):
    """Is the camera pipeline safe to drain slowly?  Run this one first.

    No detector, no tracker, no drawing -- just snapshot the channels and
    sleep, so the loop runs at roughly the speed the full app runs at.  The
    suspicion is that the crash has nothing to do with tracking and everything
    to do with the loop being too slow to keep three sensor channels drained:
    the sensor fills them at its own rate regardless of us.

        drain_test()              # three channels, slow loop
        drain_test(aux=False)     # two channels, slow loop

    If the first dies and the second survives, the aux channel is the problem
    and no amount of fixing the tracker will help.  If neither dies, the
    pipeline is innocent and the fault is in what the app does per frame.
    """
    cfg = cfg or Config()
    cfg.aux_enable = aux
    cfg.mot_output = None
    print("[drain] %d channels, %d ms/frame, %d frames (~%.1fs)"
          % (3 if aux else 2, delay_ms, frames, frames * delay_ms / 1000.0))

    pl = Pipeline(cfg)
    try:
        pl.create()
        for i in range(frames):
            os.exitpoint()
            ai = pl.get_ai_frame()
            a = pl.get_aux_frame(i)
            if i % 10 == 0:
                print("  f%3d mem %7d drop %d ai=%s aux=%s"
                      % (i, _mem(), pl.dropped,
                         "ok" if ai is not None else "MISS",
                         "ok" if a is not None else ("off" if not aux else "MISS")))
            time.sleep_ms(delay_ms)
        print("[drain] SURVIVED %d frames -- the camera pipeline is not the"
              " problem at this rate" % frames)
    except BaseException as e:
        print("[drain] aborted: %r" % (e,))
    finally:
        try:
            pl.destroy()
        except Exception as e:
            print("[drain] destroy: %r" % (e,))
        gc.collect()
        print("[drain] done, mem %d" % _mem())


def run(frames=100, cfg=None, stop_after=7):
    cfg = cfg or Config()
    cfg.mot_output = None
    cfg.print_stats_every = 0

    print("[diag] building pipeline, mem %d" % _mem())
    pl = Pipeline(cfg)
    renderer = None
    det = None
    tracker = None

    try:
        # Inside the try: a half-started sensor left behind by a failure here
        # makes every later run hang in Display.init until a power cycle.
        pl.create()
        print("[diag] panel %s %dx%d, mem %d"
              % (pl.display_driver, pl.display_size[0], pl.display_size[1],
                 _mem()))
        for stage in range(1, stop_after + 1):
            _banner(stage, STAGES[stage - 1], frames)

            if stage == 2:
                renderer = Renderer(cfg, cfg.det_frame_size, pl.display_size)
            if stage == 4:
                print("[diag] loading kmodel %s" % cfg.kmodel_path)
                det = PersonDetector(cfg)
                print("[diag] kmodel loaded, mem %d" % _mem())
            if stage == 5:
                # Tracker core only: no per-track crops, no mask SATs.
                cfg.mask_enable = False
                cfg.reid_enable = False
                tracker = McBytePlusPlus(cfg, det.frame_size, cfg.aux_size,
                                         frame_rate=cfg.sensor_fps)
            if stage == 6:
                cfg.mask_enable = True
                cfg.reid_enable = True
                print("[diag] mask cue and re-ID enabled")

            t_start = time.ticks_ms()
            det_frames = 0
            det_total = 0
            best_score = 0.0

            for i in range(frames):
                os.exitpoint()
                ai = pl.get_ai_frame()
                if ai is None:
                    continue
                aux = pl.get_aux_frame(i)

                grid = None
                if stage >= 3 and aux is not None:
                    grid = pl.make_grid(aux)

                dets = []
                if stage >= 4:
                    dets = det.run(ai)
                    det_frames += 1
                    det_total += det.last_count
                    if det.last_max_score > best_score:
                        best_score = det.last_max_score

                tracks = []
                if stage >= 5:
                    live = tracker.update(dets, aux, grid)
                    # Stages 5 and 6 hand the renderer nothing, so only the
                    # HUD is drawn; stage 7 is the first to draw a track.
                    tracks = live if stage >= 7 else []
                elif stage == 3 and aux is not None:
                    # Exercise the CMC path even without a tracker, since it is
                    # the per-frame image allocation we are suspicious of.
                    pl.cmc_probe = aux.to_grayscale(x_size=cfg.cmc_size,
                                                    y_size=cfg.cmc_size)

                if stage >= 2 and renderer is not None:
                    renderer.draw(pl.osd_img, tracks,
                                  tracker or _FakeTracker(), 0.0)
                    pl.show()

                if i % 20 == 0:
                    line = "  f%3d mem %7d drop %d" % (i, _mem(), pl.dropped)
                    if grid is not None:
                        lo, hi, avg = _grid_stats(grid)
                        line += "  aux[min %d max %d avg %.0f]" % (lo, hi, avg)
                    if stage >= 4:
                        line += "  det %d max %.2f" % (det.last_count,
                                                       det.last_max_score)
                    if stage >= 5:
                        line += "  trk %d lost %d" % (len(live),
                                                      len(tracker.lost))
                    print(line)

            dt = time.ticks_diff(time.ticks_ms(), t_start)
            print("  stage %d OK: %.1f fps, mem %d, dropped %d"
                  % (stage, frames * 1000.0 / max(dt, 1), _mem(), pl.dropped))
            if stage >= 4 and det_frames:
                print("  detector: %.2f boxes/frame, best score %.2f over %d frames"
                      % (det_total / float(det_frames), best_score, det_frames))
                if best_score:
                    print("  -> track_thresh %.2f / new_track_thresh %.2f: %s"
                          % (cfg.track_thresh, cfg.new_track_thresh,
                             "reachable" if best_score >= cfg.new_track_thresh
                             else "NEVER REACHED, nothing can be born"))
    except BaseException as e:
        print("[diag] aborted: %r" % (e,))
    finally:
        print("[diag] tearing down, mem %d" % _mem())
        if det is not None:
            try:
                det.deinit()
            except Exception as e:
                print("[diag] detector deinit: %r" % (e,))
        try:
            pl.destroy()
        except Exception as e:
            print("[diag] pipeline destroy: %r" % (e,))
        gc.collect()
        print("[diag] done, mem %d" % _mem())


class _FakeTracker:
    """Just enough surface for the HUD before the real tracker exists."""

    def __init__(self):
        self.stats = {"reid_hits": 0, "cmc_applied": 0, "cmc_skipped": 0,
                      "mask_hits": 0, "births": 0}
        self._next_id = 0
        self.cmc = _FakeCMC()
        self.lost = []


class _FakeCMC:
    hold_left = 0
    last_response = 0.0
