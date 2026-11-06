# Jaywalking Detector on the Kendryte K230

Two scripts watch a street through a CanMV K230's on-board camera and show the
results on the LCD in real time.

| | `jaywalk_detect.py` (v1) | `jaywalk_detect_v2.py` (v2) |
|---|---|---|
| Red box + count for each **jaywalker** | ✓ | ✓ |
| **Face blur** on every person | ✓ | ✓ |
| **Vehicle tracking**: blue box, persistent ID, speed in km/h | | ✓ |
| **Jaywalker IDs** (`J1`, `J2`, ...) | | ✓ |
| **Hit score**: 0-99 % collision risk per vehicle-jaywalker pair | | ✓ |
| **Risk table** in the bottom-right corner | | ✓ |

v2 keeps all of v1's detection logic unchanged; every v2 addition is marked
`[V2]` in the code. Neither script needs a road map, calibration or zones, and
everything runs on the board: no image is stored or sent anywhere.

Full design documents:
[jaywalk_detect_v1.md](jaywalk_detect_v1.md) (v1) ·
[jaywalk_detect_v2.md](jaywalk_detect_v2.md) (v2)

## How it works, in short

**Finding jaywalkers (v1 and v2)**

- **The road is wherever vehicles just drove.** Every *moving* car, bus, truck
  or motorbike leaves a "footprint" (the strip where its wheels meet the
  ground), kept for 6 seconds. Parked vehicles leave none.
- **A jaywalker** has their feet, for at least 0.5 s, either **in a lane**
  (inside a recent footprint) or **between lanes** (with traffic on both
  sides). People on the pavement have traffic on one side only, so they are
  not flagged.
- **Riders are never jaywalkers.** Anyone sitting on a bike or motorbike,
  inside a car, or moving faster than a person can run is excluded. A count
  made within 2 s before a rider is recognised is taken back.
- **Counted once.** Duplicate boxes on one person are merged, and someone
  hidden behind a passing car for up to 8 s keeps their track, and their count,
  when they reappear.
- **Distances are measured in body heights**, so the same rules work for near
  and far people without any setup.

**Vehicle tracking and speed (v2)**

- Each vehicle gets an **ID after it has been matched 3 times**, so one-frame
  false detections don't use up IDs. IDs only count up and are never reused.
  A vehicle hidden for more than 2 s comes back with a new ID.
- **Speed** comes from how far the bottom centre of the box (where the vehicle
  meets the road) moves in 0.6 s, timed with real frame timestamps.
- **Pixels become metres automatically** by using the vehicle's own height as
  a ruler: car 1.5 m, motorbike 1.2 m, bus 3.2 m, truck 3.0 m. This follows
  perspective with no scene setup. For top-down cameras, a fixed scale can be
  used instead.
- The number is smoothed, shows `--.-` until it is known, reads `0.0` below
  2 km/h (box jitter) and is capped at 200 km/h.

**Jaywalker IDs (v2)**

- A J-number is given only once a count is **final**, i.e. 2 s after it is
  made, when it can no longer be taken back. Until then the label shows `J?`.
- So every J-number is a count that stands, and **the highest J-number matches
  the HUD total**. The ID stays with the person if they are hidden and found
  again.

**Hit score (v2)**

A 0-99 % score for every vehicle-jaywalker pair on screen. It is a
**rule-based risk index, not a measured probability**: it is built to rise
smoothly with danger, to always read high for an imminent hit, and to stay low
for harmless situations.

- **Distance** is measured in metres from the jaywalker's feet to the nearest
  part of the vehicle's footprint.
- **Stopped vehicle:** scores from distance alone, **capped at 40 %**.
- **Moving vehicle:** the **highest** of three measures:
  - **proximity**: closer is riskier, lowered a little for slow vehicles or
    ones driving away;
  - **time to contact**: distance ÷ speed towards the jaywalker, so a fast car
    several metres away scores high;
  - **near floor**: within **1 m**, at least **80 %**, rising to 99 % at
    contact.
- The score **rises quickly and falls slowly**, so danger shows at once without
  flicker. It is always kept within 0-99 %.

First-frame scores for a vehicle heading towards a jaywalker:

| Distance | Stopped | 10 km/h | 20 km/h | 40 km/h |
|---|---|---|---|---|
| 0.5 m | 36 | 90 | 93 | 96 |
| **1 m** | 32 | **80** | **88** | **93** |
| 2 m | 27 | 61 | 78 | 88 |
| 5 m | 15 | 30 | 54 | 73 |
| 10 m | 5 | 11 | 30 | 54 |

The score was redesigned after the first version scored a car at about
10 km/h within 1 m **below 50 %**. The full analysis, including the formula
and a worked example, is in [jaywalk_detect_v2.md §10](jaywalk_detect_v2.md#10-v2-the-hit-score-analysis-and-design).

## Models

Both scripts use the same three stock CanMV example models, run on the K230's
KPU.

| Model | File | Input | Used for |
|---|---|---|---|
| Person detector (YOLOv5n) | `person_detect_yolov5n.kmodel` | 640 × 640 | Who is in the scene, and where their feet are |
| Vehicle detector (YOLOv8n, COCO) | `yolov8n_320.kmodel` | 320 × 320 | Where traffic drives (car, motorbike, bus, truck); who is riding (bicycle, motorbike, cabins); v2 vehicle tracking and speed |
| Face detector | `face_detection_320.kmodel` + `prior_data_320.bin` | 320 × 320 | Extra face coverage for the blur |

Heads are also blurred straight from the person boxes on every frame, so the
blur works even for people facing away.

## Requirements

- CanMV K230 board, firmware v1.8 or later, with the on-board camera and an LCD.
- On the SD card (from the standard CanMV examples):
  - `/sdcard/examples/kmodel/person_detect_yolov5n.kmodel`
  - `/sdcard/examples/kmodel/yolov8n_320.kmodel`
  - `/sdcard/examples/kmodel/face_detection_320.kmodel`
  - `/sdcard/examples/utils/prior_data_320.bin`

## Running it

Open `jaywalk_detect.py` or `jaywalk_detect_v2.py` in the CanMV IDE and run it.

To start it on power-up, save it to the board as `/sdcard/main.py`. Test it
from the IDE first: if a script run at boot crashes the firmware, the board can
lock up before the IDE can connect, and recovery then needs a card reader.

## On screen

| Element | Meaning | Version |
|---|---|---|
| Red box + "JAYWALKING" | A current jaywalker | v1, v2 |
| HUD `Jaywalkers: N` | Running total for this run | v1, v2 |
| HUD `Jaywalking now: N` | Jaywalkers on screen right now | v1, v2 |
| HUD `Traffic seen (n)` / `No moving traffic` | Whether there is recent traffic. With none, nobody can be flagged | v1, v2 |
| Thin blue box + `ID 3  42.5 km/h` tag | A tracked vehicle, its ID and speed | v2 |
| Yellow `J4` tag beside the red box | The jaywalker's ID | v2 |
| Grey `J?` tag | Jaywalker whose count is not yet final (first 2 s) | v2 |
| Risk table, bottom right | One row per vehicle-jaywalker pair | v2 |

**Risk table (v2)**

```
 +-------------------------------------------+
 | Veh ID | Jay ID | Speed km/h | Hit %      |
 |--------+--------+------------+------------|
 | V3     | J4     | 42.5       | 93%  (red) |   <- highest risk first
 | V5     | J4     | 12.0       | 58%  (org) |
 | V3     | J?     | 42.5       | 31%  (yel) |
 | +2 more                                   |
 +-------------------------------------------+
```

- Rows are rebuilt every frame: a pair appears when both are on screen and
  disappears when either leaves.
- **Score colours:** green up to 30 %, yellow 31-50 %, **orange above 50 %**,
  **red above 75 %**.
- The table stays out of the way: at most 6 rows, 35 % of the screen height
  and 45 % of its width, with extra pairs summarised as "+N more". It is
  semi-transparent, and more so when a tracked object passes behind it.
- It is drawn **first**, so boxes and face blurs always appear on top of it.

**Console**

| Message | When | Version |
|---|---|---|
| `jaywalker #N (track id, lane\|between)` | A person is counted | v1, v2 |
| `retracted track id: on a vehicle` | A count is taken back | v1, v2 |
| `jaywalker ID J<n> confirmed (track id)` | A count becomes final and gets its ID | v2 |
| `jaywalkers counted this run: N` | On exit | v1, v2 |
| `vehicles tracked this run: N` | On exit | v2 |

`jaywalker #N` numbers can be reused after a retraction, so match the screen
against the `J<n> confirmed` lines.

Set `DEBUG = True` to see the traffic footprints and why each person was or
wasn't flagged.

## Quick tuning

All settings are constants at the top of the script. In v2, the new settings
are grouped in a **V2 CALIBRATION** block at the very top.

**Jaywalk detection (v1 and v2)**

| Symptom | Adjust |
|---|---|
| Obvious jaywalkers not flagged | Turn on `DEBUG`. No footprints nearby: lower `VEH_CONF`. Footprints nearby: raise `ACROSS_BODY` or `LANE_MARGIN` |
| Flagged too late | Lower `JAY_MIN_MS` |
| Pavement walkers flagged | Lower `ACROSS_BODY` and `LANE_MARGIN`, raise `MIN_SIDE_HITS` |
| Riders counted | Raise `RIDER_HOLD_MS`, lower `RIDER_SPEED_BODY` |
| Same person counted twice | Raise `GHOST_MS` and `GHOST_SPEED` |
| People on a zebra crossing flagged | List the crossing in `CROSSWALK_ZONES` |
| Too slow | `USE_FACE_DET = False`, raise `FACE_EVERY`, or set `VEH_EVERY = 2` |

**Speed and hit score (v2)**

| Symptom | Adjust |
|---|---|
| Speeds consistently too high or low | `SPEED_SCALE` (check against a vehicle of known speed: if 40 km/h shows 50, set 0.8) |
| Top-down camera, or speeds wrong for every vehicle type | `SPEED_MODE = "fixed"` and measure `METERS_PER_PIXEL` |
| Speed number jumps around | Lower `SPEED_SMOOTH` |
| Scores rise too late as vehicles approach | Raise `RISK_TTC_SCALE_S` or `RISK_DIST_SCALE_M` |
| Too many high scores for distant traffic | Lower `RISK_TTC_SCALE_S` or `RISK_DIST_SCALE_M` |
| Want a larger "imminent" zone | Raise `RISK_NEAR_M` (keep `RISK_NEAR_FLOOR_PCT` above 75) |
| Table too big on a small screen | Lower `TABLE_MAX_ROWS`, `TABLE_MAX_H_FRAC`, `TABLE_MAX_W_FRAC` |
| Table text overlaps | Adjust `CHAR_W` |

The full v1 parameter list is in
[jaywalk_detect_v1.md §7](jaywalk_detect_v1.md#7-adjustable-parameters); the v2 guide is
in [jaywalk_detect_v2.md §13](jaywalk_detect_v2.md#13-calibration-guide).

## Performance

The three AI models take almost all of each frame's time; the v2 additions
are simple arithmetic plus a few dozen small draws. 30 fps is **not
guaranteed**: the frame rate is set by the models. Set `DEBUG_TIMING = True`
to print per-frame timings.

## Known limitations

**Jaywalk detection (v1 and v2)**

- **No moving traffic, no detection.** On an empty or fully stopped road,
  nobody can be flagged.
- **One-sided traffic** past someone standing in the road looks the same as
  someone on the pavement.
- **Zebra crossings** must be entered by hand.
- **Sprinters** may be mistaken for riders.
- **Validation:** the rules were checked in a 20-scenario box-level
  simulation, not yet on live footage.

**Speed, IDs and hit score (v2)**

- **One camera, estimated distances.** Movement towards or away from the camera
  looks shorter than it is, so those vehicles' **speed reads low**. Their
  **distance to the jaywalker also reads low**, which errs on the safe side by
  raising the hit score.
- **Reference heights are averages:** an SUV or van reads slightly slow, a low
  sports car slightly fast.
- **The near floor also applies to vehicles driving away.** One that has just
  passed 0.5 m from a person still scores about 90 %, as a near miss.
- **`J?` delay:** for 2 s after a count, the HUD total is ahead of the highest
  J-number by the number of `J?` labels on screen.
- **Validation:** v2 was tested on a desktop with simulated detections, not yet
  on the K230 with live footage.

## Files

```
jaywalk_detect_v1.py        	v1: the detector
jaywalk_detect_v2.py     	v2: adds vehicle tracking, IDs, hit score, risk table
jaywalk_detect_v1.md   	 	full design of v1
jaywalk_detect_v2.md 	 	full design of v2, including the hit-score analysis
README.md        	 	this file
```
