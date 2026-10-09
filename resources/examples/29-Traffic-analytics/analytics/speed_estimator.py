import math
import time
import config


class SpeedEstimator:
    def __init__(self, meters_per_pixel):
        # Camera calibration: real meters represented by 1 pixel
        self.meters_per_pixel = meters_per_pixel

    def update(self, track):
        history = track.history

        # Need valid calibration and at least 2 positions
        if self.meters_per_pixel <= 0 or len(history) < 2:
            return

        # Current vehicle position
        now_ms, x, y = history[-1]

        # Find an older position within the speed time window
        reference = None
        for sample in history:                      
            if time.ticks_diff(now_ms, sample[0]) <= config.SPEED_WINDOW_MS:
                reference = sample
                break
        if reference is None:
            return

        # Time between the two positions
        span_ms = time.ticks_diff(now_ms, reference[0])

        # Ignore measurements with too little time difference
        if span_ms < config.SPEED_MIN_SPAN_MS:
            return

        # Calculate movement in pixels
        dx = x - reference[1]
        dy = y - reference[2]
        pixels = math.sqrt(dx * dx + dy * dy)

        # Ignore very small tracking noise
        if pixels < config.SPEED_DEADBAND_PX:
            pixels = 0.0

        # Convert pixel movement → meters → km/h
        kmh = pixels * self.meters_per_pixel / (span_ms / 1000.0) * 3.6

        # Smooth speed to reduce jitter
        if track.speed_valid:
            k = config.SPEED_SMOOTHING
            track.speed_kmh = k * kmh + (1 - k) * track.speed_kmh
        else:
            track.speed_kmh = kmh
            track.speed_valid = True

        # Keep the highest speed seen for this vehicle
        if track.speed_kmh > track.max_speed_kmh:
            track.max_speed_kmh = track.speed_kmh
