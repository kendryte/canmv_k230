# 🚦 AI Traffic Analytics System

Real-time **road traffic analytics** on the **K230 / CanMV MicroPython** platform. A single camera watches a stretch of road, and on-device AI turns the live feed into vehicle counts, per-lane speed and congestion, a touch-drawn counting line, a stop/incident watchdog and a congestion heatmap — all without a cloud service or host PC.

---

## 📋 Prerequisites

### Hardware

- **K230 development board**
- **Touch LCD display** — the scene setup wizard (drawing the calibration line, counting line and lanes) is touch-driven; `DISPLAY_MODE` also supports HDMI, but you still need a touch source to place points (the CanMV IDE preview window can supply touch input during development)
- **Camera module** on the CSI interface
- SD card

### Software

- CanMV IDE
- K230 MicroPython firmware — [Kendryte K230 Resource Center](https://www.kendryte.com/en/resource/images,k230)
- A **YOLOv8n** vehicle-detection kmodel (`yolov8n_224.kmodel`)

---

## ⚙️ Setup

### 1. Flash Firmware

This project supports different K230 boards — flash the **MicroPython image suitable for your own board**. After flashing, verify the board runs MicroPython and connects to CanMV IDE.

### 2. Copy Project Files

```bash
git clone git@g.a-bug.org:canmv/k230/canmv.git
```

Copy `canmv/resources/examples/29-Traffic-analytics` to the SD card's `examples` directory, keeping the folder name. The resulting path must be `/sdcard/examples/29-Traffic-analytics`, matching `APP_DIR` in `main.py`, which is used to load the app's modules.

```
SD Card (/sdcard)
│
└── examples/
    └── 29-Traffic-analytics/
        ├── main.py                    # configuration + entry point
        ├── helper.py                  # geometry, timestamps, storage utilities
        ├── analytics/
        │   ├── scene_config.py        # calibration / lanes / counting-line model
        │   ├── traffic_analyzer.py    # per-lane + whole-road stats, alerts
        │   ├── traffic_stats.py       # stats containers
        │   ├── speed_estimator.py     # pixel displacement -> km/h
        │   ├── incidents.py           # stillness, queueing, stop + collision alerts
        │   └── heatmap.py             # congestion heat accumulator + renderer
        ├── vision/
        │   ├── camera.py              # sensor and display setup
        │   ├── detector.py            # YOLOv8n vehicle detection
        │   └── tracker.py             # IoU / distance multi-object tracker
        ├── ui/
        │   ├── setup_wizard.py        # touch-driven scene setup flow
        │   ├── setup_steps.py         # individual wizard steps
        │   ├── analytics_view.py      # live dashboard + on-screen buttons
        │   ├── dashboard.py           # stats panel
        │   ├── scene_painter.py       # lanes / lines / vehicle box drawing
        │   ├── touch_controller.py    # touch input + axis calibration
        │   └── theme.py, chrome.py, painter.py, widgets.py, layout.py
        └── reporting/
            ├── report_generator.py    # saves dashboard + heatmap snapshots
            └── heatmap_panel.py       # heatmap report side panel
```

### 3. Model

The kmodel is loaded from a path shared with other K230 examples, not from the app folder itself:

| Model | Input | Purpose |
|---|---|---|
| **`yolov8n_224.kmodel`** | 224 × 224 | Detects vehicles (car, motorcycle, bicycle, bus, truck) in the frame |

Place it at `KMODEL_PATH` in `main.py` (default `/sdcard/examples/kmodel/yolov8n_224.kmodel`), or update that path to wherever your kmodel lives.

### 4. Run

Open **CanMV IDE**, open `canmv/resources/examples/29-Traffic-analytics/main.py` from the cloned repository, and run it on the K230 board after copying the project files to the SD card as above.

---

## 🧩 How It Works

### 1. Scene Setup Wizard

Every run starts with a short touch wizard that teaches the system the geometry of your road, so pixel measurements can become real speeds and lane statistics.

| Step | What you do |
|---|---|
| **Calibration line** | Tap 2 points on the road whose real-world distance you know |
| **Real distance** | Enter that distance in metres — this fixes metres-per-pixel |
| **Speed limit** | Enter the posted speed limit (km/h) |
| **Counting line** | Tap 2 points across the road; crossing direction decides IN vs OUT |
| **Lanes** | Draw up to 6 lane polygons that vehicles are attributed to |
| **Review** | Confirm, or reload the last saved scene and skip straight to analytics |

The last completed scene is remembered in memory, so returning to setup mid-session offers a one-tap **LOAD** instead of redrawing everything.

### 2. Live Analytics

Once the scene is confirmed, every frame runs through the same pipeline:

```
Detect (YOLOv8n) → Track (IoU / distance) → Lane assignment
   → Speed estimate → Counting-line crossing → Stop / incident check
   → Heatmap accumulation → Dashboard render
```

The on-screen dashboard shows live and passed vehicle counts (overall and per lane, by vehicle type), average speed, occupancy, a LOW/MEDIUM/HIGH density rating, a FREE FLOW → NORMAL → HEAVY/SLOW → CONGESTED rating, flow rate (vehicles/min) and a rolling alert ticker — with a speed-limit sign and per-vehicle boxes overlaid on the video itself.

### 3. AI Intent: Stops, Queues and Incidents

Vehicles are tracked continuously so the system can tell a genuine problem from ordinary traffic:

| Signal | Meaning |
|---|---|
| **Queueing** | Several slow/stopped vehicles in the same lane, or a lane already rated SLOW/CONGESTED — not alerted on |
| **Abnormal stop** | A vehicle stays still (outside a queue) longer than `STOP_ALERT_SEC` — raised as a stop alert |
| **Possible incident** | Two long-stopped, non-queued vehicles overlap or sit unusually close together for several consecutive frames — raised as an incident alert |

A vehicle stuck in ordinary congestion never triggers a stop or incident alert; only vehicles stopped **outside** a queue do.

### 4. Congestion Heatmap

Every tracked vehicle deposits heat at its road-contact point, weighted higher the slower it's moving, so idle traffic builds up more colour than free-flowing traffic. The live grid is smoothed and can be rendered as a jet-style overlay (black → blue → cyan → green → yellow → red) confined to the drawn lanes, with the single hottest lane and hotspot highlighted.

### 5. On-Screen Controls

| Button | Action |
|---|---|
| **SAVE REPORT** | Freezes the current frame and writes two JPEG reports (dashboard + heatmap) to storage |
| **RESET** | Clears all counters and the heatmap without leaving analytics |
| **SETUP** | Returns to the setup wizard to redraw the scene |

### 6. Reports

`SAVE REPORT` renders two annotated snapshots — a dashboard view (lanes, counting line, tracked vehicles, full stats panel) and a heatmap view (congestion overlay, hotspot marker, per-lane ranking) — and saves both as timestamped JPEGs to `config.DATA_DIR` (falling back to the SD card if that path isn't writable).

---

## 🎛️ Configuration

All parameters live in the configuration section at the top of `main.py`. The entry point publishes them as the `config` module before importing the app's submodules; no separate `config.py` file is needed.

### Model & Detection

```python
MODEL_NAME = "YOLOv8n"
KMODEL_PATH = "/sdcard/examples/kmodel/yolov8n_224.kmodel"
MODEL_INPUT_SIZE = [224, 224]
CONFIDENCE_THRESHOLD = 0.35
NMS_THRESHOLD = 0.45
```

### Tracking

```python
TRACK_IOU_MATCH = 0.20          # IoU needed for a confident match
TRACK_MIN_HITS = 3              # detections before a track is trusted
TRACK_TIMEOUT_MS = 1200         # confirmed track dropped after this long unseen
STILL_TRACK_TIMEOUT_MS = 4000   # a stationary vehicle keeps its id through occlusion
```

### Speed & Stops

```python
SPEED_WINDOW_MS = 1000          # displacement measured over this window
SPEEDING_CONFIRM_FRAMES = 3     # consecutive over-limit frames before a red box
STOP_ALERT_SEC = 8              # stationary this long (not in a queue) = alert
INCIDENT_MIN_STOP_SEC = 5       # both vehicles stopped at least this long
```

Lower `STOP_ALERT_SEC` / `INCIDENT_MIN_STOP_SEC` for a more sensitive watchdog in a busy junction; raise them to tolerate normal red-light waits.

### Key Parameters

| Parameter | Default | Purpose |
|---|---|---|
| `CONFIDENCE_THRESHOLD` | `0.35` | Vehicle detection confidence cutoff |
| `TRACK_IOU_MATCH` | `0.20` | Overlap required to match a track across frames |
| `SPEED_SMOOTHING` | `0.35` | EMA weight of the newest speed measurement |
| `SPEEDING_CONFIRM_FRAMES` | `3` | Frames above the limit before flagging speeding |
| `STOP_ALERT_SEC` | `8` | Time stopped outside a queue before an alert |
| `INCIDENT_IOU` | `0.25` | Box overlap treated as a possible collision |
| `QUEUE_MIN_VEHICLES` | `3` | Nearby slow neighbours needed to call it a queue |
| `DENSITY_MEDIUM` / `DENSITY_HIGH` | `0.12` / `0.30` | Occupancy thresholds for density rating |
| `CONGESTION_SLOW_RATIO` / `CONGESTION_JAM_RATIO` | `0.50` / `0.25` | Avg-speed / speed-limit thresholds for congestion rating |
| `HEATMAP_CELL_PX` | `20` | Heatmap accumulator cell size, in stage pixels |
| `FLOW_WINDOW_SEC` | `60` | Window used for the vehicles/minute flow rate |

---

## 📊 System Block Diagram

```
Camera (CSI)
  |
  v
Scene Setup Wizard (calibration, speed limit, counting line, lanes)
  |
  v
Vehicle detection (YOLOv8n)
  |
  v
Multi-object tracking (IoU / distance)
  |
  v
Lane assignment + speed estimation
  |
  v
Counting-line crossing + flow rate
  |
  v
Stop / queue / incident detection
  |
  v
Congestion heatmap accumulation
  |
  v
Live dashboard  +  JPEG report snapshots
```

---

## 🎯 Applications

- Smart-city intersection and mid-block traffic monitoring
- Speed-limit compliance spot checks
- Congestion and queue-length analytics for signal timing studies
- Incident (stall/collision) detection for faster response
- Vehicle-mix counting (cars, motorcycles, bicycles, buses, trucks) for planning
- Temporary deployment for traffic surveys without fixed infrastructure
