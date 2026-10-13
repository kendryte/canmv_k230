# mcbytepp/config.py - internal defaults and shared configuration helpers.
# Configure the sample in main.py; users do not need to edit this file.
# These defaults also support standalone app, diagnostic and self-test calls.
#
# Values marked [paper] are taken from "Training-Free Long-Term Multi-Object
# Tracking for Sports Video Analytics" (Stanczyk et al., arXiv:2608.15688) or
# from the ByteTrack base tracker it builds on.  Values marked [k230] have no
# counterpart in the paper; they belong to the on-device substitutes for the
# GPU components and were chosen for this hardware.


class Config:
    # ---------------------------------------------------------------- detector
    kmodel_path = "/sdcard/examples/kmodel/person_detect_yolov5n.kmodel"
    det_input_size = [640, 640]          # kmodel input
    # Sensor -> AI channel (chn2), RGBP888.  640x360 rather than the stock
    # demo's 1280x720, and this costs nothing in detection quality: the
    # letterbox into a 640x640 model input scales 1280x720 down to exactly
    # 640x360 and pads it, so the model sees an identical image either way.
    # What changes is the frame buffer -- 691 KB instead of 2.76 MB, on the
    # heaviest channel of three.  That is 4x less DDR traffic per frame for
    # the same result, and the sensor fills these buffers at its own rate
    # whether or not the loop keeps up.
    det_frame_size = [640, 360]
    labels = ["person"]
    anchors = [10, 13, 16, 30, 33, 23, 30, 61, 62, 45,
               59, 119, 116, 90, 156, 198, 373, 326]
    strides = [8, 16, 32]
    nms_threshold = 0.6

    # Detections below conf_low are dropped entirely; detections in
    # [conf_low, track_thresh) are the "low confidence" set used by the second
    # BYTE association stage.
    #
    # THESE ARE DETECTOR-DEPENDENT, NOT UNIVERSAL.  The paper fixes the
    # high/low split at 0.6 and ByteTrack births at 0.7, but both numbers are
    # calibrated to YOLOX-X, whose scores on sports footage run high.  The
    # stock CanMV demo for person_detect_yolov5n runs at a confidence
    # threshold of 0.2, i.e. this model scores far lower for the same person.
    # Keeping 0.6/0.7 here means almost nothing is ever confident enough to
    # start a tracklet.  Scaled to this detector:
    conf_low = 0.10                      # floor: below this a box is noise
    track_thresh = 0.35                  # [paper 0.6] BYTE high/low split
    new_track_thresh = 0.45              # [ByteTrack +0.1] births
    # Set paper_thresholds = True to restore 0.6/0.7 when you swap in a
    # detector whose scores are calibrated like YOLOX's.
    paper_thresholds = False

    # ------------------------------------------------------------ association
    match_thresh = 0.8                   # [ByteTrack] stage 1 max IoU cost
    match_thresh_second = 0.5            # [ByteTrack] stage 2 (low-conf dets)
    match_thresh_unconfirmed = 0.7       # [ByteTrack] unconfirmed tracks
    track_buffer = 30                    # [ByteTrack] frames a lost track survives

    # ------------------------------------------------------------- mask cue
    # On-device stand-in for EdgeTAM mask propagation.  See maskcue.py.
    mask_enable = True
    mask_mc_min = 0.90                   # [paper] min bbox coverage of the mask
    mask_mf_min = 0.05                   # [paper] min mask fill ratio of the bbox
    mask_ambiguity_margin = 0.10         # [k230] "several similar IoU costs"
    mask_grid_div = 4                    # [k230] aux frame -> mask grid downscale
    mask_min_cells = 6                   # [k230] below this the mask is "not visible"
    mask_band_k = 2.5                    # [k230] luma band half-width, in MADs
    mask_band_ema = 0.5                  # [k230] appearance model update rate
    mask_inner_frac = 0.6                # [k230] central fraction sampled for the band

    # ------------------------------------------------------------------- CMC
    # Conditional camera motion compensation.  Phase correlation replaces the
    # paper's ORB + affine estimate; see cmc.py.
    cmc_enable = True
    cmc_size = 128                       # [k230] must be a power of two, square
    cmc_min_response = 0.25              # [k230] reliability gate on correlation peak
    cmc_max_shift_frac = 0.25            # [k230] reject implausible translations
    cmc_hold_frames = 1                  # [paper] retain last reliable estimate
    cmc_similarity = False               # [k230] also estimate rotation/scale (logpolar)
    cmc_max_scale = 1.15                 # [k230] plausibility bound on scale
    cmc_max_rotation = 0.15              # [k230] plausibility bound, radians
    cmc_flip_y = True                    # [k230] find_displacement y sign convention

    # ------------------------------------------------------------------ re-ID
    # OSNet is replaced by a spatial colour-layout descriptor; see reid.py.
    reid_enable = True
    reid_sim_thresh = 0.8                # [paper] cosine similarity threshold
    # Thumbnail geometry for the descriptor.  8x16 rather than 4x8: a 4-pixel
    # wide RGB888 image has a 12-byte row stride, which is the kind of
    # unaligned buffer that firmware image paths handle least well, and the
    # larger grid is more discriminative anyway.
    reid_grid_w = 8                      # [k230] descriptor thumbnail width
    reid_grid_h = 16                     # [k230] descriptor thumbnail height
    reid_memory_size = 64                # [k230] long-term identity memory capacity
    reid_memory_ttl = 900                # [k230] forget an identity after N frames
    reid_finalize_window = 10            # [paper] delayed finalization, in frames
    reid_extract_stride = 3              # [k230] extract a feature every N frames
    reid_min_score = 0.6                 # [paper] features only from reliable dets

    # ------------------------------------------------------------------ video
    # The aux channel is a THIRD camera output, on top of the display channel
    # and the detector channel.  The sensor fills all three at its own rate --
    # the GC2093 snaps 720p to 90fps whatever you ask for -- while this loop
    # drains them at perhaps 15fps.  If draining gets slower than the pool can
    # absorb, snapshot() starves, and the firmware's answer to a stalled
    # capture is to reboot the board: a freeze with no Python traceback.
    #
    # aux_enable = False drops to a two-channel pipeline, the same shape as the
    # stock CanMV examples.  That costs the mask cue, CMC and re-ID (all three
    # need pixels), leaving plain ByteTrack -- which still tracks.  Turn it off
    # first when diagnosing a silent freeze.
    aux_enable = True
    aux_stride = 1                       # process the aux channel 1 frame in N
    aux_size = [320, 192]                # [k230] chn1 RGB888, feeds cmc/mask/re-ID
    sensor_framebuffers = 0              # 0 = firmware default; try 3-4 if starved
    # Panel driver: "lcd"/"st7701" for the onboard LCD, "hdmi"/"lt9611" for
    # HDMI, "virt" for no panel at all, or "auto" to try LCD then HDMI.  Named
    # drivers still fall back to "virt" if init fails, so a missing panel
    # degrades to IDE-only preview instead of killing the run.
    display_mode = "lcd"
    display_size = None                  # None = the panel's native resolution
    display_to_ide = True                # also mirror the overlay to the IDE
    sensor_hmirror = None                # True/False to override, None to leave
    sensor_vflip = None
    # The GC2093 only has a few real modes and snaps to the nearest one; asking
    # for a higher rate than the AI loop can consume costs throughput rather
    # than buying it, because the extra frames still cost DDR bandwidth.
    sensor_fps = 30

    # ---------------------------------------------------------- on-screen UI
    draw_boxes = True
    draw_labels = True                   # per-track ID text
    hud_enable = True                    # top bar: fps, track count, re-ID, cmc
    draw_trails = True                   # fading ground-track polyline per ID
    trail_length = 16                    # trail points retained per track
    osd_text_scale = 1.0                 # bump for a small/far-away panel
    label_min_box = 18                   # skip ID labels on boxes this narrow
    draw_mask_cue = False                # tint boxes whose cost got a mask bonus

    # ----------------------------------------------------------------- output
    mot_output = None                    # e.g. "/sdcard/mcbytepp_mot.txt", None disables
    print_stats_every = 30               # frames between console stat lines; 0 disables
    # debug 1 = per-frame detection counts and scores, plus free heap; use it
    # when the tracker reports no tracks, to see whether the detector is the
    # one coming up empty.  debug 2 also prints stage timings.
    debug = 0
    max_frames = 0                       # stop after N frames; 0 = run forever


def apply_paper_thresholds(cfg):
    """Restore the publication's detector thresholds (YOLOX-X calibrated)."""
    cfg.track_thresh = 0.6
    cfg.new_track_thresh = 0.7
    return cfg


def display_candidates(mode):
    """Panel drivers to try, in order.  Always ends at 'virt' as a safety net."""
    if mode == "auto":
        # LCD first: on the boards this targets it is the panel that is
        # actually attached, and HDMI init succeeds even with nothing plugged
        # in, so probing cannot tell them apart -- order is the only lever.
        order = ["st7701", "lt9611"]
    else:
        order = [mode]
    if "virt" not in order:
        order.append("virt")
    return order
