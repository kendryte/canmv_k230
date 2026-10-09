import config

DENSITY_LEVELS = ("LOW", "MEDIUM", "HIGH")
CONGESTION_LEVELS = ("FREE FLOW", "NORMAL", "HEAVY", "SLOW", "CONGESTED")
QUEUE_STATES = ("SLOW", "CONGESTED")


def empty_type_counts():
    return dict((vtype, 0) for vtype in config.VEHICLE_TYPES)


class LaneStats:
    def __init__(self, index):
        self.index = index
        self.name = "L{}".format(index + 1)
        self.live = 0
        self.passed = 0
        self.passed_by_type = empty_type_counts()
        self.avg_speed_kmh = 0.0
        self.occupancy = 0.0
        self.density = "LOW"
        self.congestion = "FREE FLOW"


class TrafficStats:
    def __init__(self, lane_count):
        self.lanes = [LaneStats(i) for i in range(lane_count)]
        self.passed_by_type = empty_type_counts()
        self.passed_total = 0
        self.count_in = 0
        self.count_out = 0
        self.speeding_total = 0
        self.stops_total = 0
        self.incidents_total = 0
        self.elapsed_ms = 0
        self.fps = 0.0
        # Smoothed scene-level values, updated by TrafficAnalyzer
        self.avg_speed_kmh = 0.0
        self.flow_rate_vpm = 0.0
        self.occupancy = 0.0
        self.density = "LOW"
        self.congestion = "FREE FLOW"
        self.begin_frame()

    def begin_frame(self):
        self.live_by_type = empty_type_counts()
        self.live_total = 0
        self.speeding_now = 0
        self.stopped_now = 0
        self.incidents_now = 0
        self.alerts = []
        for lane in self.lanes:
            lane.live = 0
