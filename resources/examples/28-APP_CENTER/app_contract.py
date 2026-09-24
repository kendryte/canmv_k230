# app_contract.py - Resource-agnostic application protocol

import gc


class Application:
    """Minimal application lifecycle understood by runner.

    This class deliberately has no Sensor, Media, KPU, audio, image format or
    resolution policy.  Applications own those decisions and resources.
    """

    name = "Application"

    def __init__(self):
        self.running = False
        self.stop_req = False
        self.display = None
        self._opened = False
        self._closed = False

    @classmethod
    def create(cls, display):
        app = cls()
        app.display = display
        return app

    def open(self):
        if self._opened or self.stop_req:
            return
        self.start()
        self._opened = True

    def run_once(self):
        """Process one frame and return its result count.

        Interactive applications may return None while previewing or paused;
        runner excludes those idle iterations from the displayed frame rate.
        """
        raise NotImplementedError

    def should_run(self):
        return self.running and not self.stop_req

    def request_stop(self):
        # Called from the LVGL thread: flags only, never release resources.
        self.stop_req = True
        self.running = False

    def start(self):
        self.stop_req = False
        self.running = True

    def stop(self):
        self.stop_req = True
        self.running = False

    def _release_owned_resources(self):
        """Application-specific final cleanup hook, called exactly once."""
        pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            try:
                self.stop()
            except Exception as e:
                print("application stop failed:", e)
            deinit = getattr(self, "deinit", None)
            if deinit is not None:
                try:
                    deinit()
                except Exception as e:
                    print("application deinit failed:", e)
        finally:
            try:
                self._release_owned_resources()
            except Exception as e:
                print("application resource cleanup failed:", e)
            self.display = None
            gc.collect()
