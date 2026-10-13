# McByte++ on the Kendryte K230

A MicroPython port of [McByte++](https://github.com/tstanczyk95/McBytePlusPlus)
— "Training-Free Long-Term Multi-Object Tracking for Sports Video Analytics"
(Stanczyk, Yoon & Brémond, [arXiv:2608.15688](https://arxiv.org/abs/2608.15688))
— running on a CanMV K230 board, tracking people from the camera in real time.

## What was ported, and what could not be

The upstream project is a PyTorch pipeline benchmarked on an H100. Three of its
components are neural networks that do not fit on a K230 at any speed, so each
one has an on-device stand-in. **The tracking algorithm itself — which is what
the paper contributes — is ported as published.**

| McByte++ component | Here | Fidelity |
|---|---|---|
| BYTE two-stage association, Kalman filter, track lifecycle | ported | exact, incl. all thresholds |
| Mask guidance signal: `mc`, `mf`, gates, `cost -= mf` | ported | exact formulas & thresholds (0.90 / 0.05) |
| Ambiguity / isolation regime gating | ported | as described in §3.1 |
| Conditional CMC: reliability gate, retain-last-estimate | ported | exact policy |
| Online re-ID: ℓ2-norm, averaging, memory, mutual-best, 0.8, delete-on-match, delayed finalization | ported | exact policy |
| Hungarian assignment | reimplemented | Jonker–Volgenant, replaces `lap.lapjv` |
| **Detector** — YOLOX-X | YOLOv5n person detector (CanMV kmodel) | different detector, same interface |
| **Mask propagation** — EdgeTAM | luma-band segmentation in the propagated box | **proxy, not a segmentation** |
| **Re-ID embedding** — OSNet | 8×16 spatial colour-layout descriptor | **proxy, keys on clothing colour** |
| **CMC estimate** — ORB + affine | phase correlation (`find_displacement`) | translation only (affine optional, off) |

Consequences worth knowing before you trust a number out of this:

- The re-ID descriptor distinguishes people by **clothing colour and its
  vertical arrangement**. It re-identifies people in different-coloured clothes
  well, and teammates in identical kit badly — which is precisely the case
  OSNet exists to handle. Do not expect the paper's IDF1 on SoccerNet.
- The mask cue helps when a subject's brightness differs from the ground
  behind them and does nothing when it does not. It degrades to plain
  ByteTrack + CMC, which is safe.
- CMC compensates pan and tilt. Roll and zoom need `cfg.cmc_similarity = True`,
  which uses the log-polar variant; its correlation response is weak on real
  scenes, so it is off by default.
- Each substitution is documented in the module that makes it: `detector.py`,
  `maskcue.py`, `reid.py`, `cmc.py`.

## Requirements

- CanMV K230 board (developed against firmware `v1.8-0`, 01Studio 2G)
- `person_detect_yolov5n.kmodel`, normally at
  `/sdcard/examples/kmodel/person_detect_yolov5n.kmodel`
- A display (HDMI or LCD), or set `cfg.display_mode = "virt"`

## Running it

Copy the entire `30-McByte++/` directory to `/sdcard/examples/`, then run
`/sdcard/examples/30-McByte++/main.py` from the CanMV IDE. This matches the
package search path set in `main.py`.

Edit the **USER SETTINGS** section of `main.py` for all configuration, including
display, camera, model, tracking and output options. No changes to the
`mcbytepp/` package are needed.

### Before you make it start on boot

The board runs `/sdcard/main.py` at power-on. If that file crashes the
*firmware* — as opposed to raising a Python error — the board wedges before
the USB debug link comes up, and no power cycle will get you back in: each one
just repeats the crash. Recovering then needs a card reader or a reflash.

`main.py` therefore opens with a boot guard: it announces itself, waits five
seconds before touching any hardware so the IDE can attach and stop it, and
skips the app entirely if a file called `/sdcard/mcbytepp.off` exists. Keep
both of those if you rename this to start on boot.

If you are already locked out: power down, read the card in a PC, and rename
`main.py` out of the way.

### On-screen output

The live camera feed goes to the video layer and the tracking overlay is
composited above it in an ARGB8888 OSD layer, so the board runs standalone —
no IDE attached, nothing on the serial console needed.

```
+--------------------------------------------------+
| McByte++  27 fps  trk 3     re-ID 2  cmc 58/60 ids 7 |  <- status bar
|                                              (o) |  <- CMC active marker
|            +------+                              |
|         3  |      |         +----+               |
|            |      |      7* |    |                  * = identity reclaimed
|            +------+         +----+               |     from the re-ID memory
|             .·˙                ·.                |
|          .·˙                     ˙·.             |  <- fading ground trails
+--------------------------------------------------+
```

Every dimension — font size, line weight, bar height, label placement — is a
fraction of the panel height, so the same overlay is readable on an 800×480
LCD and on a 1080p HDMI screen. `display_mode` defaults to `"lcd"`; use
`"hdmi"`, `"virt"` (no panel, IDE preview only), or `"auto"` to try LCD then
HDMI. A named driver that fails to initialise falls back to `"virt"` rather
than killing the run.

The sensor is 16:9 and most LCDs are not, so the video is scaled to the panel
rather than cropped — a ~6% horizontal squeeze on an 800×480 panel. Boxes stay
aligned regardless, since the display and detector channels see the same field
of view.

Set `cfg.mot_output` to a path to also write MOT-format records
(`frame,id,x,y,w,h,conf,-1,-1,-1`).

## Self-test (no camera, no kmodel)

`mcbytepp/selftest.py` renders a synthetic scene into a real `image.Image` and
runs the full tracker over it — so phase correlation, mean pooling and crops
all execute against real firmware image ops. It needs no SD card and no model,
which makes it the way to check the port on a board with a failing card:

```python
import sys; sys.path.insert(0, "/tmp")   # or wherever the package lives
from mcbytepp.selftest import run
run()
```

It checks the assignment solver and Kalman filter standalone, that two crossing
subjects do not swap identities, that the CMC engages during a camera pan, and
that a subject who leaves for 40 frames — longer than `track_buffer`, so the
tracklet genuinely dies — gets the same ID back when they return.

## Tuning

All sample settings live in `main.py`: boot options are at the top of the
**USER SETTINGS** section, followed by `create_config()` with every detector,
tracking, camera and output setting. Edit the `cfg.*` assignments there.
`mcbytepp/config.py` retains internal defaults and provenance notes for
standalone package, diagnostic and self-test use; it does not need editing.

`SAFE_MODE = True` preserves the default two-channel pipeline. It forces
`aux_enable = False`, `draw_trails = False` and `debug = 1`, overriding those
three assignments in `create_config()`. Set `SAFE_MODE = False` to use their
configured values and enable the auxiliary mask, CMC and re-ID processing.

If the board freezes without a Python traceback, first check the camera
pipeline with `mcbytepp.diag.drain_test()`. Run from the IDE or REPL:

```python
import sys
sys.path.append("/sdcard/examples/30-McByte++")
from mcbytepp.diag import drain_test
drain_test()             # three sensor channels
# On a separate run, compare with drain_test(aux=False) for two channels.
```

If only the three-channel run freezes, keep `SAFE_MODE = True` while
investigating the auxiliary channel.

The settings worth reaching for first:

| Setting | Effect |
|---|---|
| `reid_sim_thresh` | 0.8. Lower merges look-alikes; raise if IDs get swapped |
| `reid_grid_w`, `reid_grid_h` | 8×16. Descriptor thumbnail width and height; 384 RGB values. Larger grids increase detail, memory use and extraction cost |
| `track_thresh` | 0.35. The high/low detection split for the supplied YOLOv5n |
| `paper_thresholds` | Set to `True` for YOLOX-calibrated split/birth thresholds of 0.6/0.7 |
| `track_buffer` | 30. Frames a lost tracklet survives before it dies |
| `mask_enable`, `cmc_enable`, `reid_enable` | Ablate each contribution |
| `aux_size` | Resolution of the CMC / mask / re-ID channel |
| `cmc_size` | 128. **Must stay a power of two and square** |
| `display_mode` | `"lcd"`, `"hdmi"`, `"virt"`, `"auto"` |
| `osd_text_scale` | Bump above 1.0 for a small or distant panel |
| `hud_enable`, `draw_trails` | Turn off the status bar / motion trails |

The `cmc_size` constraint is not a style preference: `find_displacement` on a 160×96 input
returns a zero displacement at zero response rather than an error.

## Layout

```
main.py                 all user settings, entry point and boot guard
mcbytepp/config.py      internal defaults, provenance notes and shared helpers
mcbytepp/tracker.py     the McByte++ pipeline
mcbytepp/strack.py      one tracklet
mcbytepp/kalman.py      ByteTrack's constant-velocity filter, on ulab
mcbytepp/lap.py         Jonker-Volgenant assignment + IoU costs
mcbytepp/maskcue.py     mask guidance signal          (§3.1)
mcbytepp/cmc.py         conditional motion compensation (§3.2)
mcbytepp/reid.py        long-term re-identification     (§3.3)
mcbytepp/detector.py    YOLOv5n via nncase_runtime
mcbytepp/app.py         sensor pipeline, drawing, MOT output
mcbytepp/selftest.py    synthetic end-to-end check
```

Upstream McByte++ is Apache-2.0; it builds on ByteTrack, YOLOX, Cutie, EdgeTAM,
BoT-SORT and torchreid.
