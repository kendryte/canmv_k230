"""Run with CanMV on a board with the selected display attached."""

import gc
import image
import time
import uctypes
from _media import Display, _MediaManager
from mpp.sys import kd_mpi_sys_mmap, kd_mpi_sys_munmap
from mpp.video_struct import PIXEL_FORMAT_RGB_888


def run(panel=Display.LT9611, width=1280, height=720):
    img = image.Image(64, 32, image.RGB565)
    layers = (Display.LAYER_OSD0, Display.LAYER_OSD1,
              Display.LAYER_OSD2, Display.LAYER_OSD3)
    block_size = (width * height * 4 + 4095) & ~4095

    def show(layer, frame):
        img.draw_rectangle(0, 0, 64, 32,
                           color=(255, 0, 0) if frame & 1 else (0, 255, 0),
                           fill=True)
        options = {"direct_show": False} if frame & 1 else {}
        Display.show_image(img, x=0, y=(layer - layers[0]) * 40, layer=layer,
                           **options)

    for cycle in range(2):
        for count in range(1, 5):
            gc.collect()
            used_before = gc.sys_mmz()[1]
            try:
                Display.init(panel, width=width, height=height,
                             flag=Display.FLAG_ROTATION_0, osd_num=count,
                             to_ide=False)
                reserved = gc.sys_mmz()[1] - used_before
                expected = (count + 1) * block_size
                assert expected <= reserved <= expected + 65536, (reserved, expected)
                for frame in range(64):
                    # Let scanout latch, then replace pending frames in bursts.
                    time.sleep_ms(20)
                    for burst in range(3):
                        for layer in layers[:count]:
                            show(layer, frame + burst)
                print("PASS display buffers cycle=%d osd_num=%d reserved=%d" %
                      (cycle, count, reserved))
            finally:
                Display.deinit()
            gc.collect()
            assert gc.sys_mmz()[1] <= used_before + 65536, "display pool leak"

    # A spare must retain its full capacity when the image size/format grows.
    large = image.Image(width & ~7, 96, image.RGB888)
    large.draw_rectangle(0, 0, large.width(), large.height(),
                         color=(0, 0, 255), fill=True)
    try:
        Display.init(panel, width=width, height=height, osd_num=1, to_ide=False)
        for frame in range(32):
            # Reserve the largest geometry before the small frame can latch.
            Display.config_layer(layer=layers[0],
                                 rect=(0, 0, large.width(), large.height()),
                                 pix_format=PIXEL_FORMAT_RGB_888)
            show(layers[0], frame)
            time.sleep_ms(20)
            Display.show_image(large, layer=layers[0])
            Display.disable_layer(layers[0])
            show(layers[1], frame)
            show(layers[1], frame + 1)
            Display.disable_layer(layers[1])
        print("PASS size/format growth and disable/re-enable with osd_num=1")
    finally:
        Display.deinit()
        large = None
        gc.collect()

    # Direct sources remain caller-owned. Switching one layer to a direct
    # source must release its copied-layer budget without overwriting scanout.
    pool = _MediaManager.VBPool.create(4096, 1)
    direct_buffer = None
    try:
        direct_buffer = _MediaManager.Buffer.get(4096, pool.pool_id)
        direct = image.Image(64, 32, image.RGB565, alloc=image.ALLOC_VB,
                             phyaddr=direct_buffer.phys_addr,
                             virtaddr=direct_buffer.virt_addr,
                             poolid=direct_buffer.pool_id)
        direct.draw_rectangle(0, 0, 64, 32, color=(0, 0, 255), fill=True)
        Display.init(panel, width=width, height=height, osd_num=1, to_ide=False)
        for frame in range(32):
            show(layers[0], frame)
            show(layers[0], frame + 1)
            Display.show_image(direct, layer=layers[0], direct_show=True)
            show(layers[1], frame)
            show(layers[1], frame + 1)
            Display.disable_layer(layers[1])
        print("PASS copied/direct/copied transitions with osd_num=1")
    finally:
        Display.deinit()
        direct = None
        if direct_buffer is not None:
            assert direct_buffer.destroy(), "direct buffer still held"
        assert pool.destroy(), "direct pool still held"

    # Inspect the scanout result, including after the source pixels change.
    try:
        Display.init(panel, width=width, height=height, osd_num=4, to_ide=False)
        Display.writeback(True)
        for frame in range(4):
            for index, layer in enumerate(layers):
                color = (255, 255, 255) if (index + frame) & 1 else (0, 0, 0)
                img.draw_rectangle(0, 0, 64, 32, color=color, fill=True)
                Display.show_image(img, y=index * 40, layer=layer)
                img.clear()
            time.sleep_ms(50)
            # Discard earlier captures still queued before the final update.
            for _ in range(3):
                captured = Display.writeback_dump(1000)
                assert captured is not None, "writeback timed out"
            captured_image = captured.v_frame.to_image()
            cached_pixels = captured_image.bytearray()
            assert len(cached_pixels) == width * height * 3 // 2, "expected YUV420 writeback"
            cached_values = [cached_pixels[(index * 40 + 8) * width + 8] for index in range(4)]
            # to_image() maps cached memory without invalidating the hardware
            # writeback. Inspect the Y plane uncached for the scanout assertion.
            mapping = kd_mpi_sys_mmap(captured.v_frame.phys_addr[0], width * height)
            assert mapping, "writeback mmap failed"
            try:
                pixels = uctypes.bytearray_at(mapping, width * height)
                values = [pixels[(index * 40 + 8) * width + 8] for index in range(4)]
            finally:
                kd_mpi_sys_munmap(mapping, width * height)
            for index, value in enumerate(values):
                assert value > 180 if (index + frame) & 1 else value < 80, (frame, values)
            print("PASS writeback frame=%d luma=%s cached=%s" % (frame, values, cached_values))
            pixels = cached_pixels = captured_image = captured = None
            gc.collect()
    finally:
        Display.deinit()

    # Too few configured layers must identify the public configuration knob.
    for count in (0, 1):
        try:
            Display.init(panel, width=width, height=height,
                         flag=Display.FLAG_ROTATION_0, osd_num=count, to_ide=False)
            try:
                for layer in layers:
                    show(layer, 0)
            except RuntimeError as error:
                message = str(error)
                assert "alloc layer buffer failed" in message, message
                assert "osd_num=%d" % count in message, message
                assert "Display.init()" in message, message
                print("PASS insufficient osd_num=%d: %s" % (count, message))
            else:
                raise AssertionError("expected an OSD buffer allocation error")
        finally:
            Display.deinit()

    # Rotation copies synchronously into the driver's own buffers, so one
    # shared input buffer still serves all four layers.
    try:
        Display.init(panel, width=width, height=height,
                     flag=Display.FLAG_ROTATION_90, osd_num=4, to_ide=False)
        for frame in range(64):
            for layer in layers:
                show(layer, frame)
        print("PASS rotated display with four OSD layers")
    finally:
        Display.deinit()

    # MMZ images have no VB pool ID. Direct mode must validate the image,
    # rather than accidentally taking the copied-buffer path with osd_num=0.
    try:
        Display.init(panel, width=width, height=height,
                     flag=Display.FLAG_ROTATION_0, osd_num=0, to_ide=False)
        try:
            Display.show_image(img, direct_show=True)
        except ValueError as error:
            assert "direct show image require physical address" in str(error), str(error)
            print("PASS direct_show=True validates the source image")
        else:
            raise AssertionError("expected direct image validation to fail")
    finally:
        Display.deinit()

    print("CANMV_DISPLAY_BUFFER_POOL: PASS")


def run_low_fps():
    """Exercise release waits and disabled-layer spare reuse at 1 fps."""
    # This timing fits the VO pixel-clock divider's 8-bit range at 1 fps.
    width, height = 1920, 1200
    img = image.Image(64, 32, image.RGB565)
    img.clear()
    gc.collect()
    used_before = gc.sys_mmz()[1]
    try:
        Display.init(Display.VIRT, width=width, height=height, fps=1,
                     flag=Display.FLAG_ROTATION_0, osd_num=1, to_ide=False)
        assert Display.fps() == 1
        block_size = (width * height * 4 + 4095) & ~4095
        reserved = gc.sys_mmz()[1] - used_before
        assert 2 * block_size <= reserved <= 2 * block_size + 65536, reserved
        print("PASS virtual display uses two ownership-tracked buffers reserved=%d" % reserved)
        layer = Display.LAYER_OSD0
        Display.show_image(img, layer=layer)
        time.sleep_ms(2500)
        waits = []
        for frame in range(8):
            img.draw_rectangle(0, 0, 64, 32,
                               color=(255, 0, 0) if frame & 1 else (0, 255, 0),
                               fill=True)
            start = time.ticks_ms()
            Display.show_image(img, layer=layer)
            waits.append(time.ticks_diff(time.ticks_ms(), start))
        assert max(waits) >= 500, ("slow scanout wait not exercised", waits)
        assert max(waits) < 3500, ("release wait exceeded three frames", waits)
        print("PASS 1fps frame release waits_ms=%s" % waits)

        reuse_times = []
        for _ in range(4):
            # Leave a replaced frame in the spare, then reuse it on another layer.
            Display.show_image(img, layer=layer)
            Display.disable_layer(layer)
            layer = (Display.LAYER_OSD1 if layer == Display.LAYER_OSD0
                     else Display.LAYER_OSD0)
            start = time.ticks_ms()
            Display.show_image(img, layer=layer)
            reuse_times.append(time.ticks_diff(time.ticks_ms(), start))
        assert max(reuse_times) < 250, ("disabled spare still waits for scanout", reuse_times)
        print("PASS disabled spare cross-layer reuse at 1fps elapsed_ms=%s" % reuse_times)
    finally:
        Display.deinit()
    gc.collect()
    assert gc.sys_mmz()[1] <= used_before + 65536, "low-fps display pool leak"
    print("CANMV_DISPLAY_LOW_FPS: PASS")


if __name__ == "__main__":
    run()
    run_low_fps()
