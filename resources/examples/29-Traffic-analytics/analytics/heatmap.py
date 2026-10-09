import gc
import math
import time
from array import array

import config
from helper import bounding_box, point_in_polygon

# value -> colour. Black at 0 so "no heat" blends to nothing.
_RAMP = (
    (0.00, (0, 0, 0)),
    (0.16, (10, 30, 130)),
    (0.34, (0, 115, 230)),
    (0.52, (0, 210, 205)),
    (0.68, (70, 225, 75)),
    (0.84, (255, 215, 0)),
    (1.00, (255, 55, 40)),
)


def heat_color(value):
    """0..1 -> the heatmap ramp (black, blue, cyan, green, yellow, red)."""
    v = 0.0 if value < 0 else (1.0 if value > 1 else value)
    for i in range(1, len(_RAMP)):
        t1, c1 = _RAMP[i]
        if v <= t1:
            t0, c0 = _RAMP[i - 1]
            k = (v - t0) / (t1 - t0) if t1 > t0 else 0.0
            return (int(c0[0] + (c1[0] - c0[0]) * k),
                    int(c0[1] + (c1[1] - c0[1]) * k),
                    int(c0[2] + (c1[2] - c0[2]) * k))
    return _RAMP[-1][1]


def legend_color(value):
    """Same ramp, but never black - used for bars and the report legend."""
    return heat_color(0.14 + 0.86 * value)


class HeatmapAccumulator:
    """Grid of heat, in stage (camera window) coordinates."""

    def __init__(self, stage_size, cell_px=config.HEATMAP_CELL_PX):
        self.width = int(stage_size[0])
        self.height = int(stage_size[1])
        self.cols = max(4, int(self.width / cell_px))
        self.rows = max(4, int(self.height / cell_px))
        self.cell_w = self.width / float(self.cols)
        self.cell_h = self.height / float(self.rows)
        self.reset()

    def reset(self):
        self._grid = array("f", [0.0] * (self.cols * self.rows))
        self._started_ms = time.ticks_ms()

    def elapsed_ms(self):
        return time.ticks_diff(time.ticks_ms(), self._started_ms)

    # ------------------------------------------------------------- live --
    def add(self, point, weight=1.0):
        col = int(point[0] / self.cell_w)
        row = int(point[1] / self.cell_h)
        col = 0 if col < 0 else (self.cols - 1 if col >= self.cols else col)
        row = 0 if row < 0 else (self.rows - 1 if row >= self.rows else row)
        self._grid[row * self.cols + col] += weight

    def smoothed_grid(self):
        return self._box_blur(self._box_blur(self._grid))

    def peak(self, grid=None):
        grid = self._grid if grid is None else grid
        return max(grid)

    def hotspot(self, grid=None):
        """Hottest cell centre, in stage coordinates, or None."""
        grid = self.smoothed_grid() if grid is None else grid
        peak = max(grid)
        if peak <= 0:
            return None
        index = 0
        for i in range(len(grid)):
            if grid[i] == peak:
                index = i
                break
        row, col = divmod(index, self.cols)
        return (int((col + 0.5) * self.cell_w), int((row + 0.5) * self.cell_h))

    def lane_scores(self, lanes, grid=None):
        """Average heat per lane, normalised so the hottest lane = 1.0."""
        grid = self.smoothed_grid() if grid is None else grid
        sums = [0.0] * len(lanes)
        cells = [0] * len(lanes)
        bounds = [bounding_box(lane) for lane in lanes]
        for row in range(self.rows):
            cy = (row + 0.5) * self.cell_h
            for col in range(self.cols):
                cx = (col + 0.5) * self.cell_w
                for i in range(len(lanes)):
                    x0, y0, x1, y1 = bounds[i]
                    if x0 <= cx <= x1 and y0 <= cy <= y1 and point_in_polygon((cx, cy), lanes[i]):
                        sums[i] += grid[row * self.cols + col]
                        cells[i] += 1
                        break
        density = [sums[i] / cells[i] if cells[i] else 0.0 for i in range(len(lanes))]
        peak = max(density) if density else 0.0
        return [d / peak if peak > 0 else 0.0 for d in density]

    # ----------------------------------------------------------- report --
    def render(self, frame, out_size, lanes=(), grid=None):
        """Blends the heatmap into `frame`, a (h, w, 3) uint8 ulab array.

        Returns True if anything was drawn. The frame is modified in place.
        """
        import ulab.numpy as np
        import cv_lite

        grid = self.smoothed_grid() if grid is None else grid
        peak = max(grid)
        if peak <= 0:
            return False

        out_w, out_h = int(out_size[0]), int(out_size[1])
        mask = self._lane_mask(lanes) if (lanes and config.HEATMAP_LANES_ONLY) else None
        cells = self._cells(grid, peak, mask)
        if not cells:
            return False

        shape = [out_h, out_w]
        colour = self._paint(np, cells, out_w, out_h, False)
        colour = cv_lite.rgb888_gaussian_blur_fast(shape, colour, config.HEATMAP_BLUR)
        gc.collect()
        alpha = self._paint(np, cells, out_w, out_h, True)
        alpha = cv_lite.rgb888_gaussian_blur_fast(shape, alpha, config.HEATMAP_BLUR)
        gc.collect()

        self._blend(np, frame, colour, alpha, out_h)
        colour = None
        alpha = None
        gc.collect()
        return True

    # ---------------------------------------------------------- helpers --
    def _cells(self, grid, peak, mask):
        """[(row, col, (r, g, b), alpha)] for every cell worth painting."""
        cells = []
        for index in range(len(grid)):
            if mask is not None and not mask[index]:
                continue
            value = grid[index] / peak
            if value <= 0.004:
                continue
            level = min(1.0, math.sqrt(value) * config.HEATMAP_GAIN)
            row, col = divmod(index, self.cols)
            cells.append((row, col, heat_color(level),
                          int(config.HEATMAP_ALPHA_MAX * level)))
        return cells

    def _lane_mask(self, lanes):
        mask = bytearray(self.cols * self.rows)
        bounds = [bounding_box(lane) for lane in lanes]
        for row in range(self.rows):
            cy = (row + 0.5) * self.cell_h
            for col in range(self.cols):
                cx = (col + 0.5) * self.cell_w
                for i in range(len(lanes)):
                    x0, y0, x1, y1 = bounds[i]
                    if x0 <= cx <= x1 and y0 <= cy <= y1 and point_in_polygon((cx, cy), lanes[i]):
                        mask[row * self.cols + col] = 1
                        break
        return mask

    def _paint(self, np, cells, out_w, out_h, alpha_only):
        """Coarse grid -> full size image, ready to be blurred."""
        img = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        cw = out_w / float(self.cols)
        ch = out_h / float(self.rows)
        for row, col, colour, alpha in cells:
            y0 = int(row * ch)
            y1 = out_h if row == self.rows - 1 else int((row + 1) * ch)
            x0 = int(col * cw)
            x1 = out_w if col == self.cols - 1 else int((col + 1) * cw)
            if alpha_only:
                img[y0:y1, x0:x1, 0] = alpha
                img[y0:y1, x0:x1, 1] = alpha
                img[y0:y1, x0:x1, 2] = alpha
            else:
                img[y0:y1, x0:x1, 0] = colour[0]
                img[y0:y1, x0:x1, 1] = colour[1]
                img[y0:y1, x0:x1, 2] = colour[2]
        return img

    @staticmethod
    def _blend(np, frame, colour, alpha, out_h, band=120):
        """frame = frame + (colour - frame) * alpha, in horizontal bands so
        the float temporaries stay small."""
        for y0 in range(0, out_h, band):
            y1 = min(out_h, y0 + band)
            base = np.array(frame[y0:y1], dtype=np.float)
            weight = np.array(alpha[y0:y1], dtype=np.float) * (1.0 / 255.0)
            top = np.array(colour[y0:y1], dtype=np.float)
            frame[y0:y1] = np.array(base + (top - base) * weight, dtype=np.uint8)
            base = None
            weight = None
            top = None
            gc.collect()

    def _box_blur(self, src):
        cols, rows = self.cols, self.rows
        dst = array("f", [0.0] * len(src))
        for row in range(rows):
            r0 = row - 1 if row > 0 else 0
            r1 = row + 1 if row < rows - 1 else rows - 1
            for col in range(cols):
                c0 = col - 1 if col > 0 else 0
                c1 = col + 1 if col < cols - 1 else cols - 1
                total = 0.0
                count = 0
                for rr in range(r0, r1 + 1):
                    base = rr * cols
                    for cc in range(c0, c1 + 1):
                        total += src[base + cc]
                        count += 1
                dst[row * cols + col] = total / count
        return dst
