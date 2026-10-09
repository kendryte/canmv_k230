# How McByte++ works on the Kendryte K230

This document explains the whole system: what the original algorithm does, what
the K230 can and cannot provide, how the port bridges the two, and what happens
to a single frame from photons to a box on the LCD.

It assumes you know roughly what multi-object tracking is and have seen a
CanMV/MicroPython script before. It assumes nothing about the paper.

---

## 1. What McByte++ is

[McByte++](https://github.com/tstanczyk95/McBytePlusPlus) accompanies *Training-
Free Long-Term Multi-Object Tracking for Sports Video Analytics* (Stanczyk, Yoon
& Brémond, arXiv:2608.15688). It is a **tracking-by-detection** system: a
detector finds people in each frame, and the tracker's job is to decide which
box in frame *t* is the same person as which box in frame *t−1*, and to keep
that identity stable over time.

Its contribution is that it does this **without training anything**. It takes
off-the-shelf components and combines three cues on top of a ByteTrack core:

1. **A mask cue** — a segmentation mask is propagated per tracklet and used to
   disambiguate matches that box overlap alone cannot resolve.
2. **Conditional camera motion compensation (CMC)** — global camera movement is
   estimated and subtracted from the predicted boxes, but only when the
   estimate looks trustworthy.
3. **Online long-term re-identification** — when someone leaves the scene and
   returns, an appearance memory gives them their original ID back.

Upstream this runs on an H100 at 8–20 FPS, using YOLOX-X for detection, EdgeTAM
for masks, and OSNet for re-ID.

### What this port is, honestly

**The algorithm is ported faithfully. The three neural networks it depends on
are not, because they cannot fit on this chip.** Each is replaced by a
cheap on-device equivalent:

| Upstream | Here | Consequence |
|---|---|---|
| YOLOX-X detector | YOLOv5n person kmodel | different score calibration, weaker on small/occluded people |
| EdgeTAM mask propagation | luminance-band segmentation in the predicted box | works when subject and background differ in brightness; otherwise inert |
| OSNet re-ID embedding | 8×16 spatial colour-layout descriptor | separates differently-dressed people; fails on identical kit |
| `lap.lapjv` | hand-written Jonker–Volgenant solver | equivalent |

Everything else — the two-stage association, the Kalman filter, the track
lifecycle, both mask ratios and their thresholds, the CMC reliability policy,
and the entire re-ID protocol — matches the publication.

So: **this is the McByte++ *method* running on a K230, not a reproduction of
its published accuracy.** Do not expect SoccerNet numbers from it.

---

## 2. The K230 hardware uses

Four independent blocks/models are in play, and understanding which does what explains
most of the design:

| Block | Role here |
|---|---|
| **Sensor / VI** | GC2093 camera, native 1920×1080@30. Produces up to three independently sized, independently formatted output channels from one capture. |
| **KPU + nncase** | The neural accelerator. Runs the quantised `.kmodel`. |
| **ai2d** | Fixed-function image preprocessor: pad, resize, crop, affine. Feeds the KPU without CPU involvement. |
| **VO / display** | Composites hardware layers: a video layer and OSD overlay layers, blended on the way to the panel. |

The **three sensor channels** are the backbone of the design. One capture is
scaled three different ways in hardware, so nothing has to be resized in
Python:

```
                 ┌─────────────────────────────────────────┐
   GC2093 ──────►│  VI: one capture, three scaled outputs   │
   1920×1080     └───────┬──────────────┬──────────────┬────┘
                         │              │              │
                   chn0  │        chn1  │        chn2  │
              800×480    │   320×192    │    640×360   │
              YUV420SP   │   RGB888     │    RGBP888   │
                         │              │              │
                         ▼              ▼              ▼
                  ┌────────────┐  ┌──────────┐  ┌────────────┐
                  │ video layer│  │ CMC      │  │ ai2d ─► KPU│
                  │ (hardware, │  │ mask cue │  │  detector  │
                  │  no CPU)   │  │ re-ID    │  └─────┬──────┘
                  └─────┬──────┘  └────┬─────┘        │
                        │              │              ▼
                        │              │        detections
                        │              │              │
                        │              └──────┬───────┘
                        │                     ▼
                        │              ┌─────────────┐
                        │              │  TRACKER    │
                        │              └──────┬──────┘
                        │                     ▼
                        │              ┌─────────────┐
                        └─────────────►│ OSD overlay │──► LCD
                                       └─────────────┘
```

Two properties of this arrangement matter:

- **chn0 never touches Python.** It is bound to the video layer in hardware, so
  the live picture keeps painting even if the Python loop stalls or dies. This
  is a genuine debugging hazard: a frozen program still *looks* like it is
  running.
- **chn2 is 640×360, deliberately.** The model input is 640×640, and the
  letterbox scales 640×360 up by 1.0 and pads to 640. Feeding 1280×720 instead
  produces a byte-identical model input after ai2d's 2× downscale — at 4× the
  frame buffer (2.76 MB vs 691 KB). The smaller channel is free.

---

## 3. One frame, end to end

This is `main()` in [`app.py`](mcbytepp/app.py), and it mirrors §3.4 of the
paper.

### Step 0 — acquire

`snapshot()` on chn2 gives the detector frame; `to_numpy_ref()` exposes it as a
CHW `uint8` array **without copying**. chn1 gives the aux frame as a normal
`image.Image`.

Either may fail: the firmware returns the integer `-1` rather than a frame. Both
are checked, and a miss skips the frame rather than propagating downstream.

### Step 1 — detect

`ai2d` letterboxes 640×360 into 640×640 (pad 140 rows top and bottom) and hands
the result to the KPU. The model emits three feature maps, one per stride
(8/16/32); `aicube.anchorbasedet_post_process` decodes anchors and runs NMS,
returning `[label, score, x1, y1, x2, y2]`.

Output: a list of `[x1, y1, x2, y2, score]` in **detector-frame coordinates**.

### Step 2 — predict

Every tracklet advances one step through a constant-velocity Kalman filter.
State is 8-dimensional — `(x, y, a, h, vx, vy, va, vh)` — box centre, aspect
ratio, height, and their velocities. Process and measurement noise both scale
with the target's height, exactly as ByteTrack does, so distant (small) targets
are trusted more tightly than near ones.

Lost tracklets have their height velocity zeroed first: we do not know they are
still moving, and letting them coast unbounded is how a box ends up a thousand
pixels off-screen.

### Step 3 — compensate for camera motion

If the camera panned, every box moved even though nobody walked. CMC estimates
that global shift and applies it to the predictions *before* matching.

The estimate comes from **phase correlation** on a 128×128 grayscale reduction
of the aux frame against the previous frame's. The paper uses ORB features and
an affine fit; no ORB exists on this firmware, but phase correlation returns
translation directly *plus a correlation-peak response* that makes an excellent
reliability gate — which is precisely the "conditional" half of the method.

An estimate is accepted only if:

- the correlation response clears `cmc_min_response` (0.25),
- the implied shift is under 25% of the frame in each axis.

Rejected estimates do not overwrite the retained one; the last good estimate is
reused for `cmc_hold_frames` and then abandoned. Pan and tilt are compensated;
roll and zoom are not, unless `cmc_similarity` is enabled (log-polar, off by
default because its response is weak on real scenes).

Afterwards every state is **clamped** to plausible bounds. This is not in the
paper — it is defence against a coasting tracklet producing geometry that later
becomes an out-of-range array index or an off-screen draw call.

### Step 4 — build the cost matrix

`cost[i][j] = 1 − IoU(track_i, detection_j)`. Nothing more; appearance never
enters frame-to-frame matching, by design.

### Step 5 — apply the mask cue

Each tracklet carries a mask. Against each candidate box, two pixel-count
ratios are formed:

```
mc = |mask_i ∩ bbox_j| / |mask_i|     coverage — a gate
mf = |mask_i ∩ bbox_j| / |bbox_j|     fill — the discriminative term
```

and where the pair is **ambiguous** (several near-equal costs in that row or
column) or **isolated** (cost already above the match threshold), the cost is
lowered:

```
cost[i][j] = cost[i][j] − mf      if mf ≥ 0.05 and mc ≥ 0.90
```

The asymmetry is intentional: `mc` only gates, because several masks can sit
inside one box and score identically; `mf` is what actually perturbs the cost.

**How the mask is produced here.** EdgeTAM is a transformer and will not fit
beside the detector. Instead each tracklet keeps a **luminance band** —
mean ± 2.5·MAD over the centre 60% of its matched box, EMA-updated — and the
mask is the set of cells inside its *predicted* box whose luminance falls in
that band, evaluated on an 80×48 mean-pooled grid.

It is genuinely propagated: the box comes from the Kalman prediction after CMC,
and the band is temporal state. But it is a proxy, not a segmentation.

Intersections are answered in O(1) using a **summed-area table** built per
tracklet per frame, so the cost of testing a mask against 20 detections does not
scale with mask area.

### Step 6 — assign

Hungarian assignment via Jonker–Volgenant shortest augmenting paths, in plain
Python lists (track counts are tens; the O(n³) term is negligible). Pairs above
the threshold are priced out of the solver and filtered again afterwards on
their original cost, mimicking `lapjv`'s `cost_limit`.

### Step 7 — the BYTE second pass and the lifecycle

This is what makes ByteTrack work. Detections are split by score:

- **high** (≥ `track_thresh`) match against all tracklets, at cost ≤ 0.8;
- **low** (≥ `conf_low`, < `track_thresh`) then match against whatever is still
  unmatched, at the stricter cost ≤ 0.5.

The insight is that a *weak* detection in the right place is usually a real
person who is partly occluded — far better evidence than discarding them and
declaring the tracklet lost. Unmatched tracklets go **lost** and survive
`track_buffer` (30) frames on prediction alone before being **removed**.

Unmatched high detections are offered to *unconfirmed* tracklets (born last
frame, not yet corroborated) and otherwise **born** as new tracklets, if they
clear `new_track_thresh`. A newborn is not reported until it survives a second
association — one-frame detector noise never reaches the output.

### Step 8 — long-term re-ID

Re-ID is deliberately **not** part of frame-to-frame matching. It fires in
exactly two places:

- **On every reliable match**, a descriptor is extracted, ℓ2-normalised, and
  folded into the tracklet's running average (which is re-normalised).
- **When a tracklet dies**, that average is deposited in a long-term identity
  memory alongside the ID it held.
- **When a tracklet is born**, the memory is queried. A match requires
  **mutual best agreement** — the newcomer's top candidate must rank the
  newcomer as *its* top candidate — and cosine similarity ≥ 0.8. On a match the
  newcomer inherits the old ID and the memory entry is deleted so it cannot be
  handed out twice. Otherwise the newcomer stays provisional for
  `reid_finalize_window` frames, re-querying each frame, before being confirmed
  as a genuinely new identity.

**The descriptor here.** The crop is resampled to an 8×16 thumbnail and read out
as a 384-dim vector, then **mean-centred** before normalisation. The centring is
essential: raw colour vectors sit at cosine ≈ 0.99 to each other, so the paper's
0.8 threshold would accept everything. After centring, cosine similarity is the
Pearson correlation of the two layouts, and 0.8 is a meaningful bar again.

This keys on clothing colour and its vertical arrangement. It re-identifies
people in different-coloured clothes well and teammates in identical kit badly —
which is exactly the case OSNet exists to handle.

### Step 9 — draw

The overlay is drawn into an ARGB8888 OSD image and pushed to an OSD layer,
which the VO blends over the live video. Per track: a coloured box (thicker if
its identity was reclaimed), an ID label, and a fading ground-contact trail.
A status bar carries FPS, track count, re-ID hits and CMC engagement.

Every dimension derives from panel height, so the same code is legible on an
800×480 LCD and a 1080p monitor. **Every draw call is clipped to the panel
first** — see §7.

---

## 4. Coordinate spaces

Four spaces coexist. Confusing them is the easiest way to introduce a subtle
bug, so they are worth stating plainly:

| Space | Size | Used by |
|---|---|---|
| **Detector frame** | 640×360 | all tracking: detections, Kalman state, IoU, MOT output |
| **Aux frame** | 320×192 | CMC input, re-ID crops |
| **Mask grid** | 80×48 | mask cue only (aux ÷ `mask_grid_div`) |
| **Panel** | 800×480 | drawing only |

**Detector-frame is the canonical space.** Nothing else is ever stored in a
track. Conversions happen at the boundary and nowhere else: `MaskPropagator`
holds `sx`/`sy` into grid cells, `reid.extract` scales into aux pixels, and
`Renderer` scales into panel pixels.

Because all three channels come from one capture, they share a field of view —
so a normalised position means the same thing in all four spaces, and boxes
stay aligned with the video even though the panel is not 16:9. The LCD is
5:3 against a 16:9 sensor, so the picture is squeezed ~6% horizontally rather
than cropped.

---

## 5. Module map

```
main.py                 all user settings, entry point and boot guard
mcbytepp/config.py      internal defaults, provenance notes and shared helpers
mcbytepp/app.py         sensor pipeline, Renderer, MOT output, main loop
mcbytepp/detector.py    ai2d + KPU + aicube post-processing
mcbytepp/tracker.py     the McByte++ pipeline (steps 2-8)
mcbytepp/strack.py      one tracklet: state, lifecycle, feature average
mcbytepp/kalman.py      ByteTrack's constant-velocity filter, on ulab
mcbytepp/lap.py         Jonker-Volgenant assignment + IoU costs
mcbytepp/maskcue.py     mask guidance signal        (paper §3.1)
mcbytepp/cmc.py         conditional motion comp.    (paper §3.2)
mcbytepp/reid.py        long-term re-identification (paper §3.3)
mcbytepp/selftest.py    synthetic end-to-end check, no camera or model
mcbytepp/diag.py        staged bring-up for isolating firmware-level faults
```

Every file that makes a substitution documents it at the top, under headings
"WHAT THE PAPER DOES" and "WHAT RUNS HERE".

The port deliberately **does not import `/sdcard/libs`** (the stock
`PipeLine`/`AIBase`/`Ai2d` helpers) and talks to `nncase_runtime` directly. The
only file it needs off the card is the kmodel.

---

## 6. Parameters worth knowing

| Setting | Value | Origin |
|---|---|---|
| `conf_low` | 0.10 | detector floor |
| `track_thresh` | 0.35 | **paper says 0.6** — rescaled, see below |
| `new_track_thresh` | 0.45 | **paper/ByteTrack say 0.7** — rescaled |
| `match_thresh` | 0.8 / 0.5 / 0.7 | ByteTrack (stage 1 / stage 2 / unconfirmed) |
| `track_buffer` | 30 frames | ByteTrack |
| `mask_mc_min` / `mask_mf_min` | 0.90 / 0.05 | paper, unchanged |
| `reid_sim_thresh` | 0.8 | paper, unchanged |
| `cmc_size` | 128 | **must stay square and a power of two** |

**Why the detection thresholds moved.** The paper's 0.6 split and 0.7 birth
threshold are calibrated to YOLOX-X, which scores high on sports footage. The
stock CanMV demo for *this* kmodel runs at a confidence threshold of 0.2 — the
same person scores far lower. Keeping 0.6/0.7 means nothing is ever confident
enough to start a tracklet, and the tracker reports zero tracks forever. Set
`paper_thresholds = True` to restore the published values if you swap in a
detector calibrated like YOLOX's.

`cmc_size` is not a style preference: `find_displacement` on a non-power-of-two
input returns a **zero displacement at zero response**, silently, instead of an
error.

---

## 7. Failure modes this hardware implementation has observed

These were all hit during development and are worth knowing before you modify
anything.

**A silent freeze is not a Python bug.** If the board stops with no traceback,
no Python exception occurred — the firmware aborted underneath. Look at
resources (sensor channels, buffer pools, the nncase pool) and at native calls
given out-of-range arguments, not at tracking logic.

**Out-of-range draw calls are the classic way to trigger one.** The firmware
draw primitives are not guaranteed to clip. A person at the edge of frame
produces a box with negative origin; a coasting lost tracklet produces one
entirely off-screen. Both are clipped before any draw call, and text is drawn
only when its whole extent lands on the panel.

**`image.Image` is a factory function, not a class.** `isinstance(x,
image.Image)` raises `TypeError` rather than returning `False`. Test
`sensor.snapshot()` failure against the integer `-1`.

**The video layer lies to you.** It is bound in hardware, so the LCD shows live
camera output whether or not the Python loop is executing. A completely stalled
program looks like a working one. Per-frame logging (`cfg.debug = 1`) is the
only reliable way to know a frame completed.

**Always tear down inside `finally`, including setup.** A run that fails partway
through `Pipeline.create()` leaves the sensor and display initialised, and the
*next* run hangs in `Display.init()` until the board is power-cycled.

**Never auto-run unverified code as `/sdcard/main.py`.** If it takes down the
firmware, the board wedges before USB debug comes up and every power cycle
repeats it — recoverable only with a card reader. `main.py` therefore has a
boot guard: a five-second countdown before touching hardware, and a
`/sdcard/mcbytepp.off` flag file that skips the app entirely.

---

## 8. Measured on the board

| Quantity | Measured |
|---|---|
| Sensor | GC2093 CSI-2, 1920×1080@30 native |
| Panel | ST7701, 800×480 |
| chn2 snapshot (640×360 RGBP888) | ~36 ms, no drops over 5 |
| kmodel load | 361 ms |
| KPU tensors | 1 input, 3 outputs |
| Free MicroPython heap at idle | ~4.1 MB |
| Full loop, 3 channels @1280×720 | 15.7 FPS |
| Frame-buffer cost, chn2 @640×360 | 691 KB (vs 2.76 MB at 1280×720) |

**Verification status.** The camera path, the kmodel load and the display path
are confirmed working on hardware. The tracker's association logic has been
reviewed but not yet observed running end to end on the board; `selftest.py`
exercises it against a synthetic scene using real firmware image operations and
is the intended way to confirm it.

---

## 9. Where this will and will not work

Reasonable expectations, given the substitutions:

- **Good:** a handful of people, moderately separated, distinguishable clothing,
  a camera that pans rather than rolls or zooms.
- **Poor:** crowds with heavy mutual occlusion; people in identical uniforms
  (the descriptor cannot separate them and re-ID will merge identities); very
  small or distant subjects (detector limit); fast zoom (uncompensated).
- **Degrades safely:** if the mask cue or CMC cannot get a signal, both become
  inert and the system falls back to plain ByteTrack, which still tracks.

Each cue can be ablated independently — `mask_enable`, `cmc_enable`,
`reid_enable` — which is the fastest way to find out what is actually earning
its keep on your footage.
