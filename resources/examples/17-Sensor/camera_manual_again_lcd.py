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

sensor_name, modes = Sensor.list_mode(id=sensor_id)
print(f"传感器：{sensor_name}")

# 根据模式列表选择合适的分辨率
if modes:
    for mode in modes:
        print(f"{mode['width']}x{mode['height']}@{mode['fps']}fps")
        
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

# ==================== 模拟增益 (Again) 控制演示 ====================

# 1. 获取增益范围
print("=" * 50)
print("模拟增益 (Again) 控制演示")
print("=" * 50)

#关闭自动调节曝光和增益功能，不然手动设置可能无效
sensor.auto_exposure(False)
# 初始化媒体管理器
MediaManager.init()

# 2. 启动传感器
sensor.run()
print("传感器已启动")
print("Camera ready: manual gain LCD")
print("=" * 50)

# 获取传感器支持的增益范围
gain_range = sensor.get_again_range()
if gain_range:
    sensor_min = gain_range['min']
    sensor_max = gain_range['max']
    step_gain = gain_range['step']
    print(f"传感器增益范围：{sensor_min:.2f} - {sensor_max:.2f}")
    print(f"传感器步进值：{step_gain:.6f}")
else:
    print("无法获取增益范围")

# 设置演示用的增益范围：1 到 20，步长为 1
DEMO_MIN_GAIN = 1
DEMO_MAX_GAIN = 20
DEMO_STEP = 1

# 确保演示范围在传感器支持范围内
min_gain = max(DEMO_MIN_GAIN, sensor_min)
max_gain = min(DEMO_MAX_GAIN, sensor_max)

print(f"\n演示增益范围：{min_gain:.2f} - {max_gain:.2f}")
print(f"演示步进值：{DEMO_STEP}")

# 3. 获取当前设置的增益
initial_gain = sensor.again()
if initial_gain:
    print(f"初始增益：{initial_gain.gain[0]:.2f}")
else:
    print("无法获取初始增益")

# 4. 主循环 - 演示增益调整
frame_count = 0
current_gain_value = min_gain
gain_direction = 1  # 1 = 增加，-1 = 减少

print("\n开始增益调整演示...")
print(f"从 {min_gain:.2f} 开始，按步长 {DEMO_STEP} 递增/递减")
print("-" * 50)

try:
    while True:
        os.exitpoint()

        # 捕获通道 0 的图像
        img = sensor.snapshot(chn=CAM_CHN_ID_0)
        # 显示捕获的图像
        Display.show_image(img)

        # 每 60 帧（约 2 秒）调整一次增益
        if frame_count % 60 == 0:
            # 获取当前增益
            current_gain = sensor.again()

            if current_gain:
                print(f"\n[帧 {frame_count}] 当前增益：{current_gain.gain[0]:.2f}")
            else:
                print(f"\n[帧 {frame_count}]")

            # 设置新增益值
            print(f"  → 设置增益：{current_gain_value:.2f}")
            sensor.again(current_gain_value)

            # 计算下一个增益值（按步长递增/递减）
            current_gain_value += DEMO_STEP * gain_direction

            # 检查是否超出范围，如果超出则改变方向
            if current_gain_value >= max_gain:
                current_gain_value = max_gain
                gain_direction = -1
                print(f"  → 达到最大增益 ({max_gain:.2f})，开始递减")
            elif current_gain_value <= min_gain:
                current_gain_value = min_gain
                gain_direction = 1
                print(f"  → 达到最小增益 ({min_gain:.2f})，开始递增")

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
