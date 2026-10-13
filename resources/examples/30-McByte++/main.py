# McByte++ on the K230 - entry point.
#
# Output goes to the onboard LCD: the live camera feed on the video layer with
# the tracking overlay composited above it.
#
# ---------------------------------------------------------------------------
# BOOT GUARD - do not remove.
#
# When this file is /sdcard/main.py the board runs it at power-on.  If it then
# crashes the firmware, the board wedges before the USB debug link comes up,
# and you can no longer connect to fix it: every power cycle just repeats the
# crash.  The only ways out at that point are a card reader or a reflash.
#
# So: announce, wait, and give the IDE a window to attach and stop us before
# any camera or model is touched.  Drop a file called /sdcard/mcbytepp.off on
# the card to skip the app entirely and land at the REPL.
# ---------------------------------------------------------------------------

import os
import time
import sys
sys.path.append("/sdcard/examples/30-McByte++")

# ---------------------------------------------------------------------------
# USER SETTINGS - edit only this file to configure the sample.
# mcbytepp/config.py supplies internal defaults for standalone package users.
# ---------------------------------------------------------------------------
BOOT_DELAY = 5          # seconds of grace before touching the hardware
DISABLE_FLAG = "/sdcard/mcbytepp.off"
SAFE_MODE = True        # force aux OFF, trails OFF and debug=1


def create_config():
    from mcbytepp.config import Config

    cfg = Config()

    # --- display and camera -------------------------------------------------
    cfg.display_mode = "lcd"      # "lcd" / "hdmi" / "virt" / "auto"
    cfg.display_size = None       # native panel size, or e.g. [800, 480]
    cfg.display_to_ide = True
    cfg.sensor_hmirror = None    # True/False to override, None to leave
    cfg.sensor_vflip = None
    cfg.sensor_fps = 30
    cfg.sensor_framebuffers = 0  # 0 = firmware default; try 3-4 if starved

    # The third sensor channel supplies pixels for mask cues, CMC and re-ID.
    # SAFE_MODE disables it, leaving plain ByteTrack on two sensor channels.
    cfg.aux_enable = True
    cfg.aux_stride = 1           # process the aux channel 1 frame in N
    cfg.aux_size = [320, 192]

    # --- detector -----------------------------------------------------------
    cfg.kmodel_path = "/sdcard/examples/kmodel/person_detect_yolov5n.kmodel"
    cfg.det_input_size = [640, 640]
    cfg.det_frame_size = [640, 360]  # sensor RGBP888 channel, before letterbox
    cfg.labels = ["person"]
    cfg.anchors = [10, 13, 16, 30, 33, 23, 30, 61, 62, 45,
                   59, 119, 116, 90, 156, 198, 373, 326]
    cfg.strides = [8, 16, 32]
    cfg.nms_threshold = 0.6
    cfg.conf_low = 0.10          # discard detections below this score
    cfg.track_thresh = 0.35      # high/low split for the supplied YOLOv5n
    cfg.new_track_thresh = 0.45  # minimum score to start a track
    cfg.paper_thresholds = False  # True overrides the split/births to 0.6/0.7

    # --- association (ByteTrack defaults) ------------------------------------
    cfg.match_thresh = 0.8       # stage 1 max IoU cost
    cfg.match_thresh_second = 0.5
    cfg.match_thresh_unconfirmed = 0.7
    cfg.track_buffer = 30        # frames a lost track survives

    # --- mask cue -----------------------------------------------------------
    cfg.mask_enable = True
    cfg.mask_mc_min = 0.90       # paper: min bbox coverage of the mask
    cfg.mask_mf_min = 0.05       # paper: min mask fill ratio of the bbox
    cfg.mask_ambiguity_margin = 0.10
    cfg.mask_grid_div = 4        # aux frame -> mask grid downscale
    cfg.mask_min_cells = 6
    cfg.mask_band_k = 2.5        # luma band half-width, in MADs
    cfg.mask_band_ema = 0.5
    cfg.mask_inner_frac = 0.6

    # --- camera motion compensation ----------------------------------------
    cfg.cmc_enable = True
    cfg.cmc_size = 128           # must be a power of two; square input
    cfg.cmc_min_response = 0.25
    cfg.cmc_max_shift_frac = 0.25
    cfg.cmc_hold_frames = 1
    cfg.cmc_similarity = False   # also estimate rotation/scale (logpolar)
    cfg.cmc_max_scale = 1.15
    cfg.cmc_max_rotation = 0.15   # radians
    cfg.cmc_flip_y = True

    # --- re-identification --------------------------------------------------
    cfg.reid_enable = True
    cfg.reid_sim_thresh = 0.8    # raise if IDs get swapped
    cfg.reid_grid_w = 8          # descriptor thumbnail width
    cfg.reid_grid_h = 16         # descriptor thumbnail height
    cfg.reid_memory_size = 64
    cfg.reid_memory_ttl = 900    # forget an identity after N frames
    cfg.reid_finalize_window = 10
    cfg.reid_extract_stride = 3
    cfg.reid_min_score = 0.6

    # --- on-screen output ---------------------------------------------------
    cfg.draw_boxes = True
    cfg.draw_labels = True
    cfg.hud_enable = True
    cfg.draw_trails = True
    cfg.trail_length = 16
    cfg.osd_text_scale = 1.0     # bigger labels on a small panel
    cfg.label_min_box = 18       # skip ID labels on boxes this narrow
    cfg.draw_mask_cue = False

    # --- recording and diagnostics -----------------------------------------
    cfg.mot_output = None       # e.g. "/sdcard/mcbytepp_mot.txt"
    cfg.print_stats_every = 30  # frames between stat lines; 0 disables
    cfg.debug = 0               # 1 = per-frame counts/scores/heap, 2 = timings
    cfg.max_frames = 0          # 0 = run forever

    # Safe mode takes precedence over these three settings. Set SAFE_MODE to
    # False above to use the aux channel, trails or your chosen debug level.
    # For a freeze without a traceback, check mcbytepp.diag.drain_test() first.
    # Compare with drain_test(aux=False) to isolate the third sensor channel;
    # see README.md for the diagnostic commands.
    if SAFE_MODE:
        cfg.aux_enable = False
        cfg.draw_trails = False
        cfg.debug = 1
    return cfg


# ---------------------------------------------------------------------------
# Startup - configuration above is applied only after the boot guard.
# ---------------------------------------------------------------------------


def _disabled():
    try:
        os.stat(DISABLE_FLAG)
        return True
    except OSError:
        return False


def _wait_for_escape():
    try:
        os.exitpoint(os.EXITPOINT_ENABLE)
    except Exception:
        pass
    print("[mcbytepp] starting in %d s - stop now to get a REPL" % BOOT_DELAY)
    for i in range(BOOT_DELAY, 0, -1):
        print("  %d..." % i)
        try:
            os.exitpoint()
        except Exception:
            pass
        time.sleep(1)


if _disabled():
    print("[mcbytepp] %s present - not starting. Delete it to re-enable."
          % DISABLE_FLAG)
else:
    _wait_for_escape()

    from mcbytepp.app import main

    cfg = create_config()
    main(cfg)
