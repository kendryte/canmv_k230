import time
import config
from analytics.incidents import IncidentDetector
from analytics.speed_estimator import SpeedEstimator
from analytics.traffic_stats import TrafficStats
from helper import (bounding_box, point_in_polygon, polygon_area,
                           projection_t, side_of_line)


def classify_density(occupancy):
    # Convert occupancy into LOW / MEDIUM / HIGH
    if occupancy >= config.DENSITY_HIGH:
        return "HIGH"
    if occupancy >= config.DENSITY_MEDIUM:
        return "MEDIUM"
    return "LOW"


def classify_congestion(vehicle_count, density, avg_speed_kmh, has_speed, speed_limit_kmh):
    # No vehicles = free flowing
    if vehicle_count == 0:
        return "FREE FLOW"

    # Too few vehicles or low density = normal traffic
    if vehicle_count < config.QUEUE_MIN_VEHICLES or density == "LOW":
        return "NORMAL"

    # Compare average speed with speed limit
    ratio = avg_speed_kmh / speed_limit_kmh if (has_speed and speed_limit_kmh > 0) else 1.0

    # Very low speed = congestion
    if ratio < config.CONGESTION_JAM_RATIO:
        return "CONGESTED"
    
    # Moderately low speed = slow traffic
    if ratio < config.CONGESTION_SLOW_RATIO:
        return "SLOW"

    # High vehicle density = heavy traffic
    if density == "HIGH":
        return "HEAVY"
    return "NORMAL"


def _smooth(previous, current):
    # Smooth occupancy to reduce frame-to-frame jumps
    k = config.DENSITY_SMOOTHING
    return k * current + (1 - k) * previous


class TrafficAnalyzer:
    def __init__(self, scene, heatmap=None):
        self.scene = scene
        self.heatmap = heatmap

        # Create speed and incident analyzers
        self.speed_estimator = SpeedEstimator(scene.meters_per_pixel)
        self.incidents = IncidentDetector(scene)

        # Pre-calculate lane geometry
        self._lane_bounds = [bounding_box(lane) for lane in scene.lanes]
        self._lane_areas = [max(1.0, polygon_area(lane)) for lane in scene.lanes]

        # Total road area
        self._road_area = max(1.0, sum(self._lane_areas))
        self.reset()

    def reset(self):
        # Reset all traffic statistics
        self.stats = TrafficStats(len(self.scene.lanes))
        self._crossings_ms = []
        self._start_ms = time.ticks_ms()
        self._last_ms = None

    def update(self, tracks, now_ms):
        # Start a new statistics frame
        stats = self.stats
        stats.begin_frame()

        # Calculate time since previous frame
        dt_ms = 0 if self._last_ms is None else time.ticks_diff(now_ms, self._last_ms)

        # Ignore very long pauses
        dt_ms = max(0, min(500, dt_ms))          # ignore pauses (report saving)
        self._last_ms = now_ms

        # Only use confirmed and currently visible tracks
        active = [t for t in tracks if t.is_confirmed() and t.is_visible(now_ms)]

        lane_count = len(self.scene.lanes)

        # Temporary per-lane statistics
        lane_box_area = [0.0] * lane_count
        lane_speed_sum = [0.0] * lane_count
        lane_speed_n = [0] * lane_count

        speed_sum = 0.0
        speed_n = 0
        road_box_area = 0.0

        # Process every active vehicle
        for track in active:
            # Estimate vehicle speed
            self.speed_estimator.update(track)

            # Determine vehicle lane
            track.lane = self._find_lane(track.anchor())

            # Check counting-line crossing
            self._update_counting(track, now_ms)

            # Count currently visible vehicles
            stats.live_by_type[track.vtype] = stats.live_by_type.get(track.vtype, 0) + 1
            stats.live_total += 1

            # Add valid speed to average
            if track.speed_valid:
                speed_sum += track.speed_kmh
                speed_n += 1

            # Update lane-specific statistics
            if track.lane >= 0:
                area = track.box[2] * track.box[3]

                stats.lanes[track.lane].live += 1
                lane_box_area[track.lane] += area
                road_box_area += area

                if track.speed_valid:
                    lane_speed_sum[track.lane] += track.speed_kmh
                    lane_speed_n[track.lane] += 1

                # Add vehicle to congestion heatmap
                if self.heatmap is not None:        
                    self.heatmap.add(track.anchor(), self._heat_weight(track))

        # Calculate statistics for every lane
        limit = self.scene.speed_limit_kmh

        for i in range(len(stats.lanes)):
            lane = stats.lanes[i]

            # Vehicle area / lane area = occupancy
            lane.occupancy = _smooth(lane.occupancy,
                                     min(1.0, lane_box_area[i] / self._lane_areas[i]))

            # Calculate average lane speed
            lane.avg_speed_kmh = lane_speed_sum[i] / lane_speed_n[i] if lane_speed_n[i] else 0.0

            # Convert occupancy to density category
            lane.density = classify_density(lane.occupancy)

            # Determine lane congestion
            lane.congestion = classify_congestion(lane.live, lane.density, lane.avg_speed_kmh,
                                                  lane_speed_n[i] > 0, limit)

        # Calculate whole-road average speed
        stats.avg_speed_kmh = speed_sum / speed_n if speed_n else 0.0

        # Calculate whole-road occupancy
        stats.occupancy = _smooth(stats.occupancy, min(1.0, road_box_area / self._road_area))

        # Whole-road density and congestion
        stats.density = classify_density(stats.occupancy)
        stats.congestion = classify_congestion(stats.live_total, stats.density,
                                               stats.avg_speed_kmh, speed_n > 0, limit)

        # Update vehicle flow rate
        self._update_flow(now_ms)

        # Check speeding vehicles
        for track in active:
            self._update_speeding(track)

        # Check stopped vehicles and incidents
        self.incidents.update(active, now_ms, dt_ms, stats.lanes)

        # Build alerts for the UI
        self._collect_alerts(active)
        return stats

    def _find_lane(self, point):
        # Find which lane contains the vehicle
        x, y = point
        for i in range(len(self.scene.lanes)):
            x0, y0, x1, y1 = self._lane_bounds[i]
            # Quick bounding-box check first
            if x0 <= x <= x1 and y0 <= y <= y1 and point_in_polygon(point, self.scene.lanes[i]):
                return i

        # Vehicle is outside all defined lanes
        return -1

    def _update_counting(self, track, now_ms):
        # Check whether the vehicle crossed the counting line
        line = self.scene.count_line

        if len(line) != 2:
            return
        
        a, b = line
        point = track.anchor()

        # Check whether vehicle is near the line segment
        t = projection_t(a, b, point)
        if t < -0.05 or t > 1.05:       
            track.line_side = 0
            return

        # Determine which side of the line the vehicle is on
        side = side_of_line(a, b, point)
        if side == 0:
            return
        if track.line_side != 0 and side != track.line_side and not track.counted:
            self._register_crossing(track, side, now_ms)
        track.line_side = side

    def _register_crossing(self, track, new_side, now_ms):
        # Mark vehicle so it is counted only once
        stats = self.stats
        track.counted = True

        # Update total vehicle count
        stats.passed_total += 1

        # Update count by vehicle type
        stats.passed_by_type[track.vtype] = stats.passed_by_type.get(track.vtype, 0) + 1

        # Determine IN or OUT direction
        if new_side == self.scene.in_side:
            stats.count_in += 1
        else:
            stats.count_out += 1

        # Update lane-specific count
        if track.lane >= 0:
            lane = stats.lanes[track.lane]
            lane.passed += 1
            lane.passed_by_type[track.vtype] = lane.passed_by_type.get(track.vtype, 0) + 1

        # Save crossing time for flow calculation
        self._crossings_ms.append(now_ms)

    def _update_flow(self, now_ms):
        # Keep only crossings inside the flow time window
        window_ms = config.FLOW_WINDOW_SEC * 1000
        while self._crossings_ms and time.ticks_diff(now_ms, self._crossings_ms[0]) > window_ms:
            self._crossings_ms.pop(0)

        # Calculate elapsed time since analyzer started
        elapsed = time.ticks_diff(now_ms, self._start_ms)
        self.stats.elapsed_ms = elapsed

        # Prevent unstable flow values at startup
        effective_ms = max(10000, min(window_ms, elapsed))

        # Vehicles per minute
        self.stats.flow_rate_vpm = len(self._crossings_ms) * 60000.0 / effective_ms

    def _update_speeding(self, track):
        # Check whether vehicle is above speed limit
        limit = self.scene.speed_limit_kmh

        if track.speed_valid and limit > 0 and track.speed_kmh > limit:
            # Require several frames before confirming speeding
            track.speeding_frames = min(track.speeding_frames + 1,
                                        config.SPEEDING_CONFIRM_FRAMES * 2)
        elif track.speeding_frames > 0:
            # Gradually remove speeding state
            track.speeding_frames -= 1

        # Confirm speeding after enough frames
        if track.speeding_frames >= config.SPEEDING_CONFIRM_FRAMES:
            track.is_speeding = True

            # Count the event only once
            if not track.speeding_logged:
                track.speeding_logged = True
                self.stats.speeding_total += 1
        elif track.speeding_frames == 0:
            track.is_speeding = False

    def _collect_alerts(self, active):
        # Convert vehicle states into UI alerts
        stats = self.stats
        incident_alerts = []
        stop_alerts = []
        for track in active:
            lane = "LANE {}".format(track.lane + 1) if track.lane >= 0 else "ROADSIDE"

            # Count currently speeding vehicles
            if track.is_speeding:
                stats.speeding_now += 1

            # Incident alert
            if track.is_incident:
                stats.incidents_now += 1
                if not track.incident_logged:
                    track.incident_logged = True
                    stats.incidents_total += 1
                incident_alerts.append("POSSIBLE INCIDENT AT {}".format(lane))

            # Abnormal stopped vehicle alert
            elif track.is_abnormal:
                stats.stopped_now += 1
                if not track.stop_logged:
                    track.stop_logged = True
                    stats.stops_total += 1
                stop_alerts.append("VEHICLE #{} STOPPED {}s AT {}".format(
                    track.id, track.still_ms // 1000, lane))

        # Show maximum 3 alerts
        stats.alerts = (incident_alerts[:1] + stop_alerts)[:3]


    def _heat_weight(self, track):
        # Slow vehicles produce more heat
        limit = self.scene.speed_limit_kmh

        # No valid speed = normal heat
        if not track.speed_valid or limit <= 0:
            return 1.0

        # Calculate how slow the vehicle is
        slowness = 1.0 - min(1.0, track.speed_kmh / limit)

        # Slow/stopped vehicles get higher heat
        return 1.0 + 3.0 * slowness
