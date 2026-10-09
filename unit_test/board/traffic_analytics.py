"""Run through k230_lab after copying the traffic example to its APP_DIR."""
import time


class _Track:
    def __init__(self, samples, start_ms, speed=None):
        self.history = [(time.ticks_add(start_ms, elapsed), x, y)
                        for elapsed, x, y in samples]
        self.speed_valid = speed is not None
        self.speed_kmh = 0.0 if speed is None else speed
        self.max_speed_kmh = self.speed_kmh


class _Point:
    def __init__(self, event, x=12, y=34):
        self.event = event
        self.x = x
        self.y = y


class _TouchSamples:
    def __init__(self, samples):
        self.samples = iter(samples)

    def read(self, count):
        return next(self.samples)


def _near(actual, expected):
    assert abs(actual - expected) < 0.001, (actual, expected)


def run():
    app_dir = "/sdcard/examples/29-Traffic-analytics"
    namespace = {"__name__": "traffic_analytics_board_test"}
    with open(app_dir + "/main.py") as source:
        exec(source.read(), namespace)
    import config
    from analytics.speed_estimator import SpeedEstimator
    from machine import TOUCH
    from ui.touch_controller import _Device

    assert config.APP_DIR == app_dir
    assert config.SPEED_WINDOW_MS == namespace["SPEED_WINDOW_MS"]
    assert "TrafficApp" in namespace
    print("PASS config publication and all entry-point imports")

    estimator = SpeedEstimator(0.1)
    for start_ms in (0, time.ticks_add(0, -800)):
        track = _Track([(0, -100, 0), (200, 0, 0), (1200, 10, 0)], start_ms)
        estimator.update(track)
        assert track.speed_valid
        _near(track.speed_kmh, 3.6)
        _near(track.max_speed_kmh, 3.6)
    print("PASS expired samples and inclusive window boundary, normal/wrapped")

    for start_ms in (0, time.ticks_add(0, -100)):
        for span_ms in (299, 300):
            track = _Track([(0, 0, 0), (span_ms, 10, 0)], start_ms)
            estimator.update(track)
            assert track.speed_valid == (span_ms == 300)
            _near(track.speed_kmh, 12.0 if span_ms == 300 else 0.0)
    print("PASS minimum measurement span, normal/wrapped")

    for start_ms in (0, time.ticks_add(0, -100)):
        track = _Track([(0, 0, 0), (500, 10, 0)], start_ms, speed=20.0)
        estimator.update(track)
        _near(track.speed_kmh, 15.52)
        _near(track.max_speed_kmh, 20.0)
    print("PASS smoothing and peak speed, normal/wrapped")

    down = [_Point(TOUCH.EVENT_DOWN)]
    move = [_Point(TOUCH.EVENT_MOVE)]
    up = [_Point(TOUCH.EVENT_UP)]
    device = _Device(_TouchSamples([[], down, move, down, up, down, [], down, up]),
                     "test")
    for expected in (None, (12, 34), None, None, None, (12, 34), None, (12, 34), None):
        actual = device.read_press()
        assert actual == expected, (actual, expected)
    print("PASS touch down/move/up, held contact and empty reads")
    print("TRAFFIC_ANALYTICS_REVIEW_PASS")


if __name__ == "__main__":
    run()
