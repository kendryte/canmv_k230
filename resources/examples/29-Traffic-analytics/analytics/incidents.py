import config
from analytics.traffic_stats import QUEUE_STATES
from helper import box_iou, distance


class IncidentDetector:
    def __init__(self, scene):
        self.scene = scene

    def update(self, tracks, now_ms, dt_ms, lanes):
        # Check how long each vehicle has been still
        for track in tracks:
            self._update_stillness(track, now_ms, dt_ms)

        # Check whether vehicles are part of a traffic queue
        for track in tracks:
            self._update_queueing(track, tracks, lanes)

        # Detect unusually long stops
        for track in tracks:
            self._update_stop_alert(track, now_ms)

        # Detect possible vehicle collisions
        self._update_incidents(tracks)

    @staticmethod
    def _update_stillness(track, now_ms, dt_ms):
        # Measure recent vehicle movement
        moved = track.displacement(config.STILL_WINDOW_MS, now_ms)
        size = track.size()
        if moved is None or size <= 0:
            return

        # Small movement = vehicle is still                       
        if moved <= size * config.STILL_MOVE_RATIO:
            track.still_ms += dt_ms

        # Moving again = gradually reduce still timer
        elif track.still_ms > 0:
            track.still_ms = max(0, track.still_ms - int(dt_ms * config.STILL_DECAY))

    def _update_queueing(self, track, tracks, lanes):
        # No valid lane = cannot be in a queue
        if track.lane < 0:
            track.in_queue = False
            return

        # If lane is congested, vehicle is in the queue
        if track.lane < len(lanes) and lanes[track.lane].congestion in QUEUE_STATES:
            track.in_queue = True
            return
        limit = self.scene.speed_limit_kmh
        radius = track.size() * config.QUEUE_RADIUS_RATIO
        anchor = track.anchor()
        neighbours = 0

        # Count nearby slow vehicles in the same lane
        for other in tracks:
            if other is track or other.lane != track.lane:
                continue
            if other.is_slow(limit) and distance(anchor, other.anchor()) <= radius:
                neighbours += 1

        # Enough nearby slow vehicles = queue
        track.in_queue = neighbours >= config.QUEUE_MIN_VEHICLES - 1

    @staticmethod
    def _update_stop_alert(track, now_ms):
        # Check if stopped long enough to be suspicious
        eligible = (track.still_ms >= config.STOP_ALERT_SEC * 1000
                    and not track.in_queue
                    and track.size() >= config.MIN_ALERT_BOX_PX
                    and track.age_ms(now_ms) >= config.MIN_ALERT_TRACK_MS)
        if eligible:
            # Keep alert active for several frames
            track.stop_frames = config.ALERT_HOLD_FRAMES
        elif track.stop_frames > 0:
            # Gradually remove alert
            track.stop_frames -= 1
        track.is_abnormal = track.stop_frames > 0

    @staticmethod
    def _update_incidents(tracks):
        # Only consider long-stopped, non-queue vehicles
        min_still = config.INCIDENT_MIN_STOP_SEC * 1000
        pool = [t for t in tracks
                if t.still_ms >= min_still and not t.in_queue
                and t.size() >= config.MIN_ALERT_BOX_PX]
        colliding = set()

        # Compare every pair of candidate vehicles
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                first, second = pool[i], pool[j]
                if _looks_like_collision(first, second):
                    colliding.add(first.id)
                    colliding.add(second.id)

        # Require collision to remain for several frames
        confirm = config.INCIDENT_CONFIRM_FRAMES
        
        for track in tracks:
            if track.id in colliding:
                track.incident_frames = min(track.incident_frames + 1, confirm * 2)
            elif track.incident_frames > 0:
                track.incident_frames -= 1
            track.is_incident = track.incident_frames >= confirm


def _looks_like_collision(first, second):
    # Collision if bounding boxes overlap enough
    if box_iou(first.box, second.box) >= config.INCIDENT_IOU:
        return True

    # Otherwise, check whether vehicle anchors are extremely close
    reference = (first.box[2] + second.box[2]) * 0.5
    if reference <= 0:
        return False
    return distance(first.anchor(), second.anchor()) <= reference * config.INCIDENT_GAP_RATIO
