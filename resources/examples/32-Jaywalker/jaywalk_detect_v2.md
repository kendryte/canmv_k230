# Architecture of `jaywalk_detect_v2.py`

This document explains how `jaywalk_detect_v2.py` works, why it is built the
way it is, which AI models it uses, and how the vehicle-hits-jaywalker score
is calculated.

---

## 1. What the program does

The script runs on a **CanMV K230** board with a camera and a display. It
watches a street in real time and:

1. **Finds jaywalkers**: people standing or walking where vehicles are
   driving. It outlines them in red and counts each person once.
2. **Protects privacy**: it pixelates the head and face of every person on
   screen.
3. **Tracks vehicles**: it gives each car, motorbike, bus and truck a
   persistent ID, draws a thin blue box around it and shows its speed in km/h.
4. **Labels jaywalkers**: each confirmed jaywalker gets a persistent ID
   (`J1`, `J2`, ...).
5. **Scores collision risk**: for every vehicle-jaywalker pair it calculates
   a **hit score from 0 % to 99 %** and lists the pairs in a table in the
   bottom-right corner of the screen.

Items 1 and 2 come from the original `jaywalk_detect.py`. Items 3 to 5 are the
version 2 (V2) additions. Every V2 change in the code is marked `[V2]`, and
the original logic is kept unchanged.

---

## 2. Platform, and why it shapes the design

| Fact about the platform | Effect on the design |
|---|---|
| The K230 runs **MicroPython**, not desktop Python. | No OpenCV, no full NumPy, no SORT/ByteTrack, no Ultralytics tracker. Everything beyond the models is written in plain Python with `math`. |
| Neural networks run on the K230's **KPU** (AI accelerator) as compiled `.kmodel` files. | Models must be small, pre-compiled, and called through the CanMV `AIBase` / `Ai2d` libraries. |
| The camera gives **two streams**: one goes straight to the display, one goes to the AI. | The video itself is never redrawn by Python. Python only draws boxes and text on a transparent **OSD layer** (on-screen display) laid over the video. This is cheap and avoids flicker. |
| The CPU is modest, and three models already run each frame. | All added logic is simple arithmetic over a handful of objects. There is no image processing in Python apart from the small mosaics. |

### Camera and display pipeline

```
                    +--> channel 0 (YUV420) ----------------> video layer --+
  camera sensor ----+                                                       +--> display
                    +--> channel 2 (RGB planar, 1280x720) --> AI models     |
                                                                 |          |
                                         Python logic <----------+          |
                                              |                             |
                                              +--> OSD layer (ARGB8888) ----+
                                                   boxes, labels, table, HUD
```

All detection and tracking happens in **AI-frame pixels** (1280 x 720).
Coordinates are scaled to the display size only when drawing.

---

## 3. The AI models

Three pre-trained models are used. All are read from the SD card.

| Model | File | Input | What it finds | How often | Why this model |
|---|---|---|---|---|---|
| **Person detector** (YOLOv5n, 1 class) | `person_detect_yolov5n.kmodel` | 640 x 640 | People | Every frame | Specialised for people, so it is more reliable on pedestrians than a general detector. The larger input finds small, distant people. |
| **Vehicle detector** (YOLOv8n, COCO 80 classes) | `yolov8n_320.kmodel` | 320 x 320 | Bicycle (1), car (2), motorcycle (3), bus (5), truck (7) | Every frame (`VEH_EVERY = 1`) | One model covers every vehicle type. Vehicles are big, so a small 320 px input is enough and keeps it fast. |
| **Face detector** | `face_detection_320.kmodel` + `prior_data_320.bin` | 320 x 320 | Faces | Every 2nd frame (`FACE_EVERY = 2`) | Only used for privacy blurring. Heads are also blurred from the person boxes on every frame, so running this one less often is safe. |

The vehicle detector's results are used for two things:

- **Cars, motorcycles, buses and trucks** are tracked as traffic.
- **Bicycles and motorcycles**, plus the cabins of cars, buses and trucks,
  are used to recognise people who are **riding** a vehicle. Riders are
  never jaywalkers.

---

## 4. One frame, step by step

```
 1. get frame (RGB, 1280x720)
 2. run person detector                     -> person boxes
 3. run vehicle detector                    -> vehicle boxes by class
 4. run face detector (every 2nd frame)     -> face boxes
 5. TrafficMemory.prune                     forget old vehicle footprints
 6. VehicleTracker.update                   match vehicles, record footprints,
                                            [V2] assign IDs, measure speed
 7. JaywalkTracker.update                   match people, judge jaywalking,
                                            [V2] assign jaywalker IDs
 8. [V2] RiskAssessor.update                score every vehicle-jaywalker pair
 9. draw on the OSD, in this order:
      a. [V2] risk table (bottom right)
      b. head and face mosaics
      c. [V2] blue vehicle boxes with ID + speed
      d. red jaywalker boxes, "JAYWALKING", [V2] J-number label
      e. HUD (top left): total count, jaywalking now, traffic status
10. show the OSD, free memory
```

All the decisions (steps 5 to 8) are made before any drawing starts. Drawing
then only reads the results, so every element on screen shows the same
moment in time.

---

## 5. Main building blocks

| Class / function | Role | Origin |
|---|---|---|
| `PersonDetectionApp`, `VehicleDetectionApp`, `FaceDetectionApp` | Wrap each model: resize/pad the frame, run the KPU, decode the boxes. | Original |
| `TrafficMemory` | Remembers where vehicles have recently driven ("footprints") and judges whether a person's feet are in that path. | Original |
| `_match` | Small tracker that links each new detection to the nearest existing track. Shared by people and vehicles. | Original |
| `VehicleTracker`, `_VehTrack` | Track vehicles and turn their movement into footprints. **[V2]** adds IDs, scale, speed and direction. | Original + V2 |
| `JaywalkTracker`, `_Track` | Track people, apply the jaywalk rule, detect riders, count jaywalkers. **[V2]** adds jaywalker IDs. | Original + V2 |
| `RiskAssessor` | **[V2]** Calculates the 0-99 % hit score for every pair. | V2 |
| `Renderer` | Draws everything on the OSD. **[V2]** adds vehicle labels, J-number labels and the risk table. | Original + V2 |

---

## 6. Finding the road without a road model

### The idea

The program is **never told where the road is**. Instead:

> The road is wherever vehicles have been driving in the last few seconds.

Every moving vehicle leaves a **footprint**: the bottom 25 % of its box
(`VEH_FOOT`), which is roughly where its wheels touch the ground. Footprints are
kept for 6 seconds (`TRAFFIC_WINDOW_MS`), up to 300 at a time.

### Why it is built this way

- **No setup**: the same script works on any camera angle and any street.
- **Adapts by itself**: lane closures, parked cars and roadworks are handled
  automatically, because only *recent, moving* traffic counts.
- **Fewer false alarms**: on an empty road, or when all traffic has stopped,
  nobody is flagged, because there is no recent traffic to be in the way of.

### Only moving vehicles count

Each vehicle's position is sampled every 200 ms (`VEH_SAMPLE_MS`). A
footprint is recorded only if the vehicle moved at least 5 % of its own width
(`VEH_MIN_MOVE`). Otherwise a car parked on the pavement would make the
pavement look like a lane. Both the old and the new position are recorded,
so a fast vehicle does not leave gaps in its own lane.

---

## 7. The jaywalk rule

A person's **feet** (bottom-centre of their box, smoothed) are compared with
the recent footprints. There are two ways to be "in the path of traffic":

```
   IN A LANE                          BETWEEN
   feet inside a footprint            traffic passed on BOTH sides

   =====[car]=====>                   =====[car]=====>
         (o)                                (o)
                                      <====[car]======
```

- **In a lane**: the feet are inside a recent footprint, slightly enlarged
  (`LANE_MARGIN` = 10 % of body height).
- **Between lanes**: vehicles passed on both sides. The program first works
  out the main direction of nearby traffic, then counts footprints on each
  side of the person across that direction. It needs at least 2 on each side
  (`MIN_SIDE_HITS`), within 4 body heights across (`ACROSS_BODY`) and 2 along
  the road (`ALONG_BODY`). Someone on the pavement has traffic on one side
  only, so they are not flagged.

Distances are measured in **body heights**. A person's height in pixels is a
ruler that automatically follows perspective: near people are big, far
people are small.

### Timing rules (to avoid false alarms and flicker)

| Rule | Setting | Why |
|---|---|---|
| Must be in the path for at least 0.5 s | `JAY_MIN_MS` | Someone stepping briefly off the kerb is not flagged. |
| Track must be seen 3 times and its speed known | `TRACK_MIN_HITS`, `SPEED_WINDOW_MS` | A rider must not be counted before their speed shows they are riding. |
| Short blips out of the path (< 0.7 s) are ignored | `PATH_GRACE_MS` | Detector jitter would otherwise reset the timer. |
| Red box stays for 2 s after leaving the path, or as long as they stay where they were caught | `JAY_HOLD_MS`, `STAY_BODY` | Once the traffic around a standing person ages out of memory, they are still in the road. |
| Optional legal crossing zones | `CROSSWALK_ZONES` | A zebra crossing looks like road. Listing it stops people on it being flagged. |

### People on vehicles are never jaywalkers

Motorbike riders and cyclists are "in the lane" too, so they must be excluded.
A person counts as **on a vehicle** if:

- their box sits on a bicycle or motorbike box (centred over it, feet within
  it, head above it), or is mostly (60 %) inside a car, bus or truck with the
  feet hidden above the wheels. This must be seen at least **2 times within
  1 s**, because the detector often loses the bike for a frame while still
  seeing the rider; **or**
- they move faster than **3 body heights per second**, faster than a person
  runs. This catches riders whose bike is never detected.

The "on a vehicle" state is held for 3 s (`RIDER_HOLD_MS`).

### Counting once, and taking a count back

- **One count per person**: duplicate boxes on the same person are merged
  first. When a tracked person disappears, behind a passing car for example,
  their track is kept as a **ghost** for 8 s (`GHOST_MS`). Someone reappearing
  nearby takes the ghost over, counted state included.
- **Retraction**: if a person is counted and then, within 2 s
  (`RETRACT_MS`), turns out to be on a vehicle, the count is taken back.

---

## 8. Tracking

### The tracker (`_match`)

A deliberately simple tracker, chosen because it fits MicroPython:

1. Detections are processed largest first. Large boxes are nearby objects and
   the most reliable.
2. Each detection is linked to the **nearest** unclaimed track, but only
   within a gate. The gate is the box size times 1.0 for people, or times 1.5
   for vehicles.
3. Vehicles also need a **similar height** (within 1.6x), so a near car is
   never mistaken for a far motorbike.
4. Unmatched detections start new tracks. Tracks not seen for 2 s are dropped.

This is the association step of SORT without the Kalman filter. At camera
frame rates, objects move only a little between frames, so "nearest similar
box" is both fast and accurate enough.

### [V2] Vehicle IDs

- A vehicle gets an ID only after it has been **matched 3 times**
  (`VEH_CONFIRM_HITS`), so one-frame false detections do not use up IDs.
- IDs come from a counter that **only goes up**, so an ID is never reused.
- The blue box stays for 400 ms after the vehicle was last seen
  (`VEH_SHOW_MS`), so a single missed detection does not make it flicker.
- A vehicle hidden for more than 2 s comes back with a new ID.

### [V2] Jaywalker IDs

A J-number is handed out only when a count becomes **final**, that is, once it
is older than the 2 s retraction window. Until then the label shows **`J?`** on
a grey background.

**Why:** the original logic can take a count back within those 2 s. In the
first V2 version, IDs were given at once, so every retracted rider used up an
ID. The highest J-number then drifted above the HUD total (for example J19
against a total of 15). With deferred IDs, every J-number is a count that
stands, so **the highest J-number equals the HUD total** once no `J?` is on
screen.

The ID lives on the person's track, so a person found again through the
ghost logic keeps the same J-number.

---

## 9. [V2] Vehicle speed

### How it is measured

```
 speed (km/h) = (pixels moved per second) x (metres per pixel) x 3.6 x SPEED_SCALE
```

1. **Point tracked**: the **bottom centre** of the vehicle box, where it meets
   the road. The top of the box bounces with the car body; the bottom moves
   with the road.
2. **Time**: movement is measured over the last 0.6 s
   (`VEH_SPEED_WINDOW_MS`) using real frame timestamps. Timestamps stay
   correct even when processing is slower than the camera. If
   `SPEED_FPS` is set, frame counts at that fixed rate are used instead, which
   is useful for recorded video.
3. **Metres per pixel** (`SPEED_MODE = "auto"`): the vehicle's own **height**
   is the ruler. A car is about 1.5 m tall, so if its box is 150 px tall, one
   pixel is about 1 cm at that distance.

   | Class | Reference height |
   |---|---|
   | Car | 1.5 m |
   | Motorcycle | 1.2 m |
   | Bus | 3.2 m |
   | Truck | 3.0 m |

   Height is used rather than width because a car's width in the image changes
   a lot with viewing angle (side-on vs. head-on), while its height barely
   changes. It also follows perspective by itself: far vehicles have small
   boxes, so each pixel covers more road. For a top-down camera, where height
   cannot be seen, `SPEED_MODE = "fixed"` uses one `METERS_PER_PIXEL` value.

### Keeping the number steady

| Step | Setting | Why |
|---|---|---|
| Shown only after 0.25 s of tracking | `VEH_SPEED_MIN_MS` | Shows `--.-` instead of a wild first guess. |
| Smoothed over frames | `SPEED_SMOOTH` = 0.35, `SCALE_SMOOTH` = 0.2 | Box jitter otherwise makes the number jump. |
| Below 2 km/h shown as 0.0 | `SPEED_DEADBAND_KMH` | A parked car's box jitter is not movement. |
| Capped at 200 km/h | `SPEED_MAX_KMH` | Rejects tracking glitches. |
| Tracking gap > 0.5 s restarts the measurement | `VEH_SPEED_GAP_MS` | After a gap the box may belong to a different vehicle. |
| Overall correction factor | `SPEED_SCALE` | Calibrate against a vehicle of known speed: if 40 km/h shows as 50, set 0.8. |

**Tested:** a simulated car moving 303 px/s with a 150 px tall box showed
**10.9 km/h**, the exact expected value.

---

## 10. [V2] The hit score: analysis and design

### 10.1 What the score is, and what it is not

The score answers: **"How dangerous is this vehicle to this jaywalker right
now?"** on a 0-99 % scale, for every vehicle-jaywalker pair on screen.

It is a **risk index built from rules**, not a statistically calibrated
probability. There is no crash data behind it, and 80 % does not mean
"8 in 10 such situations end in a hit". It is designed so that:

- it rises smoothly as danger grows and falls as danger passes;
- an imminent hit always reads high (above 75 %, shown in red);
- harmless situations stay low.

The range is strictly **0 to 99 %**. 100 % is never shown, because the
system cannot be certain a hit will happen.

### 10.2 Inputs

| Input | How it is measured |
|---|---|
| **Distance `d`** (metres) | Straight-line distance from the jaywalker's feet to the nearest point of the vehicle's footprint, the part that would actually hit them. Pixels are turned into metres with the average of the vehicle's scale and the person's scale (a person is taken as 1.7 m tall). |
| **Speed** (km/h) | From section 9. |
| **Direction** | The angle between the vehicle's direction of travel and the line from the vehicle to the jaywalker: +1 = heading straight at them, 0 = passing sideways, -1 = driving straight away. |

### 10.3 The formula

**Stopped vehicle** (speed 0, or not yet known):

```
score = 99 x exp(-d / 5 m) x 0.4
```

A stopped vehicle cannot hit anyone, but a jaywalker right next to one is
still in a risky place (it may pull away). So the score is capped at **40 %**
(`RISK_STATIONARY_WEIGHT`).

**Moving vehicle**: the score is the **highest** of three measures:

```
1. Proximity      99 x exp(-d / 5 m)
                     x (0.7 + 0.3 x min(1, km/h / 30))      slower = a little lower
                     x (1 - 0.5 x how directly it is driving away)

2. Time to        99 x exp(-TTC / 1.5 s)
   contact        where TTC = d / (speed towards the jaywalker)
                  (only while the vehicle is closing in)

3. Near floor     if d <= 1 m:  80 % at 1 m, rising evenly to 99 % at contact
```

Then the score is smoothed over frames and clamped to 0-99 %.

### 10.4 Why each part exists

**Proximity**: the basic sense that "closer is more dangerous". An
exponential curve was chosen because danger grows much faster in the last few
metres than it falls off far away, and the curve never jumps.

**Time to contact (TTC)**: distance alone misses what matters most. A car
5 m away at 60 km/h reaches the person in 0.3 s, while a car 5 m away at
5 km/h takes 3.6 s. TTC is the standard measure in road safety for exactly
this reason. Only the part of the speed **towards** the jaywalker is used, so
a car passing in the next lane does not produce a false alarm.

**Near floor**: a guaranteed minimum for the most critical case. A moving
vehicle within 1 m of a person is an imminent hit whatever the other terms
say, so it always scores **at least 80 %**. That is safely above the 75 % red
threshold.

**Taking the highest, not multiplying**: each measure captures a different
kind of danger (close, fast-approaching, touching). Taking the highest means
any one of them can raise the alarm on its own, and a weak value in one term
cannot hide a strong one.

### 10.5 Why it was redesigned

The first V2 version **multiplied** proximity by a speed factor that dropped
sharply for slow vehicles. Testing showed that a car moving at about 10 km/h
**within 1 m** of a jaywalker scored **below 50 %**, far too low for a near
miss. On top of that, even smoothing made the score climb slowly, so it lagged
behind an approaching car.

The redesign:

- reduced the speed penalty on proximity (weight 0.6 down to 0.3);
- added the time-to-contact measure;
- added the 1 m near floor, applied **after** smoothing so it holds from the
  very first frame;
- made smoothing **asymmetric**: the score rises quickly (weight 0.8 per
  frame) so danger shows at once, and falls slowly (0.3 per frame) so it does
  not flicker down when a detection wobbles.

### 10.6 Resulting values

First-frame scores for a vehicle heading towards the jaywalker:

| Distance | Stopped | 5 km/h | 10 km/h | 20 km/h | 40 km/h | 60 km/h |
|---|---|---|---|---|---|---|
| 0.0 m | 40 | 99 | 99 | 99 | 99 | 99 |
| 0.5 m | 36 | 90 | 90 | 93 | 96 | 97 |
| **1.0 m** | 32 | **80** | **80** | **88** | **93** | **95** |
| 2.0 m | 27 | 50 | 61 | 78 | 88 | 91 |
| 3.0 m | 22 | 41 | 48 | 69 | 83 | 88 |
| 5.0 m | 15 | 27 | 30 | 54 | 73 | 81 |
| 10.0 m | 5 | 10 | 11 | 30 | 54 | 66 |
| 20.0 m | 1 | 1 | 1 | 9 | 30 | 44 |

Reading the table:

- Every moving vehicle within 1 m is **above 75 %**.
- Faster vehicles reach high scores from further away, as they should.
- A stopped vehicle never exceeds 40 %.

**Worked example** (1 m, 10 km/h, heading straight at the person):

```
proximity     = 99 x exp(-1/5) x (0.7 + 0.3 x 10/30)     = 99 x 0.819 x 0.8   = 65
time to       : closing speed 10 km/h = 2.78 m/s, TTC = 1 / 2.78 = 0.36 s
  contact       99 x exp(-0.36 / 1.5)                                       = 78
near floor    : d = 1.0 m -> 80
score         = highest = 80 %
```

**A car approaching at 20 km/h, then driving away** (scores frame by frame,
with smoothing):

```
distance  8 m  6 m  4 m  2 m  1 m  0.5 m | 3 m  6 m  9 m
score     38   46   58   74   85   92    | 85   74   62
                   rises quickly ------->|<---- falls gradually
```

### 10.7 A design choice to be aware of

The 1 m near floor applies to **any** moving vehicle, including one driving
away. A vehicle that has just passed 0.5 m from a person still scores about
90 %, because that was a near miss. If only approaching vehicles should
trigger the floor, it can be limited to them.

### 10.8 Colours

| Score | Colour | Meaning |
|---|---|---|
| 0-30 % | Green | Low risk |
| 31-50 % | Yellow | Watch |
| 51-75 % | **Orange** | Elevated risk |
| 76-99 % | **Red** | High risk / imminent |

---

## 11. Drawing and the on-screen layout

### Elements

| Element | Look | Why |
|---|---|---|
| Vehicle box | Thin 2 px pure blue | Visible without hiding the vehicle. |
| Vehicle label | White text on a solid blue tag above the box: `ID 3  42.5 km/h` | A solid tag stays readable on any background (sky, road, other cars). |
| Jaywalker box | 4 px red + "JAYWALKING" | Unchanged from the original. |
| Jaywalker ID | Black on yellow `J4` beside the box (left side if no room); black on grey `J?` while pending | High contrast; grey shows the count is not yet final. |
| Risk table | Bottom right, semi-transparent | See below. |
| HUD | Top left: total, jaywalking now, traffic status | Unchanged from the original. |

### Risk table

```
 +-------------------------------------------+
 | Veh ID | Jay ID | Speed km/h | Hit %      |   <- header (dark blue band)
 |--------+--------+------------+------------|
 | V3     | J4     | 42.5       | 93%  (red) |   <- highest risk first
 | V5     | J4     | 12.0       | 58%  (org) |
 | V3     | J?     | 42.5       | 31%  (yel) |   <- pending jaywalker
 | +2 more                                   |
 +-------------------------------------------+
```

- Rows are **rebuilt every frame**. A pair appears when both the vehicle and
  the jaywalker are on screen, and disappears when either leaves.
- Rows are sorted by score, highest first, so the most dangerous pair is
  always at the top.
- **Size limits**, so the table never covers the detection area: at most 6
  rows, at most 35 % of the screen height and 45 % of the width. The font
  shrinks to fit, and any extra pairs are summarised as "+N more". With no
  pairs, it shows "No risk pairs".
- **Transparency**: the background is semi-transparent (opacity 150/255). If a
  tracked vehicle or jaywalker passes behind it, it becomes more transparent
  (70/255).

### Why the drawing order matters

The OSD does not blend layers: a later drawing **replaces** the pixels under
it. So the order is chosen on purpose:

1. **Table first**, so the boxes and mosaics drawn afterwards appear on top of
   it. Nothing tracked is ever hidden by the table.
2. **Mosaics** next, so a face behind the table is still blurred. Privacy
   comes before readability.
3. **Blue vehicle boxes**, then **red jaywalker boxes** on top, so the most
   important outline always wins.
4. **HUD** last.

The whole OSD is cleared and redrawn every frame from data decided in advance,
so there is no partial update and no flicker.

### Privacy mosaics

Every person's head region is estimated from their box (about the top fifth
of a standing body) and pixelated into 5 x 5 blocks on **every frame**. Face
detections are pixelated as well. Blurring continues for 0.5 s after a person
was last seen, so a missed detection never exposes a face.

---

## 12. Performance

- The three neural networks take almost all of the time per frame. They run
  on the KPU accelerator.
- The V2 additions are light: simple arithmetic for each vehicle and for each
  vehicle-jaywalker pair (a few objects), plus about 30 small text and
  rectangle draws for the labels and table.
- 30 fps is **not guaranteed**. With three models per frame the frame rate is
  set by the models, not by the V2 logic. If more speed is needed, the easiest
  options are `VEH_EVERY = 2` or a larger `FACE_EVERY`.
- Set `DEBUG_TIMING = True` to print the time per frame on the console.

---

## 13. Calibration guide

All V2 settings are in the **V2 CALIBRATION** block at the top of the script.

| You notice | Change |
|---|---|
| Speeds consistently too high or too low | `SPEED_SCALE` (measure a vehicle of known speed) |
| Top-down camera, or speeds wrong for every vehicle type | `SPEED_MODE = "fixed"` and measure `METERS_PER_PIXEL` |
| Speed number jumps around | Lower `SPEED_SMOOTH` |
| Scores rise too late as vehicles approach | Raise `RISK_TTC_SCALE_S` or `RISK_DIST_SCALE_M` |
| Too many high scores for distant traffic | Lower `RISK_TTC_SCALE_S` or `RISK_DIST_SCALE_M` |
| Want a larger "imminent" zone | Raise `RISK_NEAR_M` (keep `RISK_NEAR_FLOOR_PCT` above 75) |
| Table too big on a small screen | Lower `TABLE_MAX_ROWS`, `TABLE_MAX_H_FRAC`, `TABLE_MAX_W_FRAC` |
| Table text overlaps | Adjust `CHAR_W` (average character width) |

---

## 14. Known limitations

- **Single-camera distance**: everything is estimated from one 2D image.
  Movement towards or away from the camera appears shorter than it really is,
  so for those vehicles **speed tends to be underestimated** and the
  **distance to the jaywalker also tends to be underestimated**. The second
  effect errs on the safe side: it makes the hit score higher, not lower.
- **Reference heights are averages**: an SUV or van is taller than 1.5 m, so
  its speed reads slightly low; a low sports car reads slightly high.
- **The hit score is a rule-based risk index**, not a measured probability
  (section 10.1).
- **Zebra crossings** look like road unless listed in `CROSSWALK_ZONES`.
- **IDs after long occlusion**: a vehicle hidden for more than 2 s gets a new
  ID. A person hidden for more than 8 s is treated as a new person.
- **Pending jaywalkers**: for the first 2 s a jaywalker shows `J?`, and the
  HUD total can be briefly ahead of the highest J-number by the number of
  `J?` labels on screen.
- The script has been tested on a desktop computer with simulated detections.
  Final tuning needs real footage on the K230.
