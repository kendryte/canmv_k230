import time, os, sys

from media.sensor import *
from media.display import *
from media.media import *

sensor_id = 2
sensor = None

# 显示模式选择：可以是 "VIRT"、"LCD" 或 "HDMI"
DISPLAY_MODE = "LCD"

# 根据模式设置显示宽高
if DISPLAY_MODE == "VIRT":
    # 虚拟显示器模式
    DISPLAY_WIDTH = ALIGN_UP(1920, 16)
    DISPLAY_HEIGHT = 1080
elif DISPLAY_MODE == "LCD":
    # 3.1 寸屏幕模式
    DISPLAY_WIDTH = 800
    DISPLAY_HEIGHT = 480
elif DISPLAY_MODE == "HDMI":
    # HDMI 扩展板模式
    DISPLAY_WIDTH = 1920
    DISPLAY_HEIGHT = 1080
else:
    raise ValueError("未知的 DISPLAY_MODE, 请选择 'VIRT', 'LCD' 或 'HDMI'")

# 根据模式初始化显示器
if DISPLAY_MODE == "VIRT":
    Display.init(Display.VIRT, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, fps=60)
elif DISPLAY_MODE == "LCD":
    Display.init(Display.ST7701, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, to_ide=True)
elif DISPLAY_MODE == "HDMI":
    Display.init(Display.LT9611, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, to_ide=True)

# 构造一个具有默认配置的摄像头对象
sensor = Sensor(id=sensor_id)
# 重置摄像头 sensor
sensor.reset()

# 设置水平镜像
# sensor.set_hmirror(False)
# 设置垂直翻转
# sensor.set_vflip(False)

sensor.set_framesize(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, chn=CAM_CHN_ID_0)
sensor.set_pixformat(Sensor.RGB888, chn=CAM_CHN_ID_0)

# ==================== 曝光控制演示 ====================

# 1. 获取曝光范围
print("=" * 50)
print("曝光控制演示")
print("=" * 50)

# 2. 关闭自动曝光（在 run 之前）
print("\n关闭自动曝光...")
sensor.auto_exposure(False)

# 初始化媒体管理器
MediaManager.init()

# 3. 启动传感器
sensor.run()
print("传感器已启动")
print("Camera ready: manual exposure LCD")
print("=" * 50)

range = sensor.get_exposure_time_range()
if range:
    max_exp, min_exp = range
    print(f"曝光范围：{min_exp:.2f} us - {max_exp:.2f} us")
    print(f"         ({min_exp/1000:.2f} ms - {max_exp/1000:.2f} ms)")
else:
    print("无法获取曝光范围，使用默认值")
    min_exp = 1000   # 1ms
    max_exp = 33000  # 33ms

# 4. 获取当前设置的曝光时间
initial_exposure = sensor.exposure()
print(f"初始曝光时间：{initial_exposure} us)")

# 5. 主循环 - 演示曝光调整
frame_count = 0
exposure_step = 0
test_exposures = [
    2000,    # 2ms - 很暗
    5000,    # 5ms - 较暗
    10000,   # 10ms - 中等
    20000,   # 20ms - 较亮
    33000,   # 33ms - 很亮
]

print("\n开始曝光调整演示...")
print("每个曝光值显示 2 秒")
print("-" * 50)

try:
    while True:
        os.exitpoint()

        # 捕获通道 0 的图像
        img = sensor.snapshot(chn=CAM_CHN_ID_0)
        # 显示捕获的图像
        Display.show_image(img)

        # 每 60 帧（约 2 秒）调整一次曝光
        if frame_count % 60 == 0:
            # 获取当前曝光
            current_exp = sensor.exposure()
            current_ae = sensor.auto_exposure()

            print(f"\n[帧 {frame_count}] 自动曝光：{'开启' if current_ae else '关闭'}, 当前曝光：{current_exp:.2f} us")

            # 如果还没测试完所有曝光值
            if exposure_step < len(test_exposures):
                new_exp = test_exposures[exposure_step]
                print(f"  → 设置新曝光：{new_exp} us ({new_exp/1000:.1f} ms)")
                sensor.exposure(new_exp)
                exposure_step += 1
            else:
                # 所有曝光值测试完毕，回到第一个
                print("  → 所有曝光值已测试，重新开始...")
                exposure_step = 0

        frame_count += 1

except KeyboardInterrupt:
    print("\n\n用户中断演示")

finally:
    # 清理资源
    print("\n清理资源...")

    if isinstance(sensor, Sensor):
        sensor.stop()
        print("✓ 传感器已停止")

    Display.deinit()
    print("✓ 显示器已关闭")

    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)

    MediaManager.deinit()
    print("✓ 媒体缓冲区已释放")

    print("\n演示结束")
