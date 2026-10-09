import time

import config
from helper import box_anchor, box_center, box_iou, distance


class Track:
    def __init__(self, track_id, detection, now_ms):
        self.id = track_id
        self.box = detection.box
        self.vtype = detection.vtype
        self.score = detection.score
        self.hits = 1
        self.first_ms = now_ms
        self.last_ms = now_ms
        self.history = []                
        self._votes = {detection.vtype: 1}
        self._append_history(now_ms)

        self.lane = -1
        self.speed_kmh = 0.0
        self.max_speed_kmh = 0.0
        self.speed_valid = False
        self.line_side = 0
        self.counted = False
        self.speeding_frames = 0
        self.is_speeding = False
        self.speeding_logged = False

        self.still_ms = 0              
        self.stop_frames = 0              
        self.incident_frames = 0
        self.in_queue = False
        self.is_abnormal = False
        self.is_incident = False
        self.stop_logged = False
        self.incident_logged = False

    def anchor(self):
        # Use the configured vehicle anchor point for tracking.
        return box_anchor(self.box)

    def size(self):
        # Use the larger box dimension as vehicle size.
        return max(self.box[2], self.box[3])

    def age_ms(self, now_ms):
        # How long this track has existed.
        return time.ticks_diff(now_ms, self.first_ms)

    def is_confirmed(self):
        # Require several detections before trusting the track.
        return self.hits >= config.TRACK_MIN_HITS

    def is_visible(self, now_ms):
        # True if the vehicle was seen recently.
        return time.ticks_diff(now_ms, self.last_ms) <= config.TRACK_VISIBLE_MS

    def is_alert(self):
        # Vehicle currently has a traffic alert.
        return self.is_speeding or self.is_abnormal or self.is_incident

    def is_slow(self, speed_limit_kmh):
        # Slow enough to be part of a queue.
        if self.still_ms > 0:
            return True
        return (self.speed_valid and speed_limit_kmh > 0
                and self.speed_kmh < speed_limit_kmh * config.CONGESTION_SLOW_RATIO)

    def displacement(self, window_ms, now_ms):
        if len(self.history) < 3:
            return None
        newest = self.history[-1]
        oldest = None
        moved = 0.0
        for sample in self.history:
            if time.ticks_diff(newest[0], sample[0]) > window_ms:
                continue
            if oldest is None:
                oldest = sample
            gap = distance((newest[1], newest[2]), (sample[1], sample[2]))
            if gap > moved:
                moved = gap
        if oldest is None:
            return None
        if time.ticks_diff(newest[0], oldest[0]) < window_ms * 0.6:
            return None
        return moved

    def update(self, detection, now_ms):
        # Update the track with a new YOLO detection.
        self.box = detection.box
        self.score = detection.score
        self.hits += 1
        self.last_ms = now_ms

        # Vote on vehicle type to make classification stable.
        self._votes[detection.vtype] = self._votes.get(detection.vtype, 0) + 1
        self.vtype = max(self._votes, key=self._votes.get)   # majority vote

        # Store the new position for movement analysis.
        self._append_history(now_ms)

    def _append_history(self, now_ms):
        # Store timestamp + vehicle position.
        ax, ay = self.anchor()
        self.history.append((now_ms, ax, ay))

        # Keep only the most recent samples.
        if len(self.history) > config.TRACK_HISTORY_LEN:
            self.history.pop(0)


class VehicleTracker:
    # Match YOLO detections across frames and maintain vehicle IDs.
    def __init__(self):
        self.tracks = []
        self._next_id = 1

    def reset(self):
        # Remove all existing tracks.
        self.tracks = []

    def update(self, detections, now_ms):
        # Match current detections to existing vehicles.
        matched_tracks, matched_dets = self._associate(detections, now_ms)

        # Any unmatched detection is a new vehicle.
        for index in range(len(detections)):
            if index not in matched_dets:
                self.tracks.append(Track(self._next_id, detections[index], now_ms))
                self._next_id += 1

        # Remove vehicles that have disappeared for too long.
        self.tracks = [t for t in self.tracks if self._is_alive(t, now_ms)]
        return self.tracks

    def _associate(self, detections, now_ms):
        """
        Match existing tracks with new detections.

        First prefer high IoU.
        If IoU is low, use center distance.
        """

        pairs = []
        for ti in range(len(self.tracks)):
            track = self.tracks[ti]
            centre = box_center(track.box)
            gate = max(track.box[2], track.box[3]) * config.TRACK_DISTANCE_GATE
            for di in range(len(detections)):
                detection = detections[di]
                iou = box_iou(track.box, detection.box)
                if iou >= config.TRACK_IOU_MATCH:
                    pairs.append((1.0 + iou, ti, di))
                elif gate > 0:
                    d = distance(centre, box_center(detection.box))
                    if d < gate:
                        pairs.append((1.0 - d / gate, ti, di))
        pairs.sort(key=lambda pair: pair[0], reverse=True)

        used_tracks = set()
        used_dets = set()
        for _, ti, di in pairs:
            if ti in used_tracks or di in used_dets:
                continue
            self.tracks[ti].update(detections[di], now_ms)
            used_tracks.add(ti)
            used_dets.add(di)
        return used_tracks, used_dets

    @staticmethod
    def _is_alive(track, now_ms):
        # Decide whether a track should remain active.
        if not track.is_confirmed():
            # New tracks get a short grace period.
            timeout = config.TENTATIVE_TIMEOUT_MS
        elif track.still_ms >= 1000:
            # Stopped vehicles are kept longer.
            timeout = config.STILL_TRACK_TIMEOUT_MS
        else:
            # Normal moving vehicle timeout.
            timeout = config.TRACK_TIMEOUT_MS
        return time.ticks_diff(now_ms, track.last_ms) <= timeout
