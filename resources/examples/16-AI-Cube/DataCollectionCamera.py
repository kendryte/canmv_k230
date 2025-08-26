from media.display import *
from media.media import *
from media.sensor import *
import time, os, sys, gc
from machine import TOUCH
from machine import Pin
from machine import FPIOA

#显示的宽高
DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

#采集图片的分辨率
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080

brd = os.uname()[-1]
if brd == "k230_canmv_01studio":
    PRESS_KEY_NUM = 21
    PRESS_KEY_VAL = 0
elif brd == "k230_canmv_lckfb":
    PRESS_KEY_NUM = 53
    PRESS_KEY_VAL = 1
else:
    #按键GPIO Number，根据硬件修改
    PRESS_KEY_NUM = 21
    PRESS_KEY_VAL = 0

del brd

#保存图片的起始编号，可以修改
save_num = 0

#数据采集标准框，采集的物体最好在这个框框内
grab_x = 0
grab_y = 0
grab_w = 0
grab_h = 0

#保存图片的位置和图片名称开头，根据需要修改
IMG_SAVE_PATH="/sdcard/examples/data/"
IMG_SAVE_NAME_BEGIN="1_"

LOGO_FILE="/sdcard/examples/16-AI-Cube/logo.jpg"

def cal_grab_rect():
    global grab_x, grab_y, grab_w, grab_h

    frame_w = DISPLAY_WIDTH
    frame_h = DISPLAY_HEIGHT

    if frame_w > frame_h:
        grab_h = int(frame_h * 6 / 7)
        grab_y = int((frame_h - grab_h) / 2)
        grab_w = grab_h
        grab_x = int((frame_w - grab_w) / 2)
    else:
        grab_w = int(frame_w * 6 / 7)
        grab_x = int((frame_w - grab_w) / 2)
        grab_h = grab_w
        grab_y = int((frame_h - grab_h) / 2)

    print("cal_grab_rect x: {}, y: {}, w: {}, h: {}".format(grab_x, grab_y, grab_w, grab_h))

def media_init():
    global sensor
    # 根据硬件选择显示的方法，默认为IDE显示
    # use LCD for display
    Display.init(Display.ST7701, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, to_ide = True, osd_num=1)

    # use hdmi for display
    # Display.init(Display.LT9611, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, to_ide = True, osd_num=1)

    # use IDE for display
    #Display.init(Display.VIRT, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, fps = 60, to_ide = True)

    sensor = Sensor(fps=30)
    sensor.reset()

    sensor_width = sensor.width(None)
    sensor_height = sensor.height(None)
    # 设置采集图片的分辨率
    sensor.set_framesize(w=VIDEO_WIDTH, h=VIDEO_HEIGHT,chn=CAM_CHN_ID_0)
    sensor.set_pixformat(Sensor.RGB888)

    # 设置显示的分辨率, 使用与采集相同的分辨率来做resize
    sensor.set_framesize(w=DISPLAY_WIDTH, h=DISPLAY_HEIGHT, chn=CAM_CHN_ID_2)
    sensor.set_pixformat(Sensor.RGB888, chn=CAM_CHN_ID_2)

    MediaManager.init()
    sensor.run()

    cal_grab_rect()

def media_deinit():
    global sensor
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    sensor.stop()
    time.sleep_ms(50)
    Display.deinit()
    MediaManager.deinit()

def save_file(img_0):
    global save_num
    img_1 = img_0.to_jpeg()
    img_name = IMG_SAVE_NAME_BEGIN + str(save_num) + ".jpg"
    img_1.save(IMG_SAVE_PATH + img_name, quality = 99)
    print("save img " + IMG_SAVE_PATH + img_name)
    save_num += 1
    gc.collect()
    return img_name

def gpio_init():
    global KEY
    fpioa = FPIOA()
    fpioa.set_function(PRESS_KEY_NUM, FPIOA.GPIO0 + PRESS_KEY_NUM)

    if PRESS_KEY_VAL == 0:
        KEY=Pin(PRESS_KEY_NUM, Pin.IN, Pin.PULL_UP) #构建KEY对象
    else:
        KEY=Pin(PRESS_KEY_NUM, Pin.IN, Pin.PULL_DOWN)
    del fpioa

def show_logo():
    logo_img = image.Image(LOGO_FILE)
    print("show logo w: " + str(logo_img.width()) + ", h: " + str(logo_img.height()))
    Display.show_image(logo_img.to_rgb888())
    time.sleep(2)

def mkdir_p(path):
    parts = path.strip('/').split('/')
    current = ''
    for part in parts:
        current += '/' + part
        try:
            os.mkdir(current)
        except OSError as e:
            if e.args[0] == 17:  # EEXIST
                continue
            elif e.args[0] == 2:  # ENOENT
                raise OSError("Parent directory missing: " + current)
            else:
                raise

def index_init():
    global save_num

    try:
        os.stat(IMG_SAVE_PATH)
    except:
        mkdir_p(IMG_SAVE_PATH)

    for file in os.listdir(IMG_SAVE_PATH):
        if file is None:
            break
        if file.startswith(IMG_SAVE_NAME_BEGIN):
            index = file.split('_')[1]
            index = int(index.split('.')[0])
            if save_num <= index:
                save_num = index + 1
    print("index_init start " + str(save_num))

def key_handle(img_save, img_display):
    global KEY

    wait_key = False
    if KEY.value()==PRESS_KEY_VAL:   #按键被按下
        time.sleep_ms(10) #消除抖动
        if KEY.value()==PRESS_KEY_VAL: #确认按键被按下
            print('Save')
            wait_key = True
            img_name = save_file(img_save)
            img_display.draw_string_advanced(0, 0, 48, f"Save: {img_name}", color = (0, 0, 255))

    img_display.draw_rectangle(grab_x, grab_y, grab_w, grab_h, color = (255, 0, 0), thickness = 2, fill = False)

    Display.show_image(img_display) #显示图片

    if wait_key: #如果按键被按下
        time.sleep(0.5)
        while KEY.value() == PRESS_KEY_VAL: #检测按键是否松开
            pass

try:
    media_init()
    gpio_init()
    index_init()
    show_logo()
    while True:
        img_save = sensor.snapshot(chn=CAM_CHN_ID_0)
        img_display = sensor.snapshot(chn=CAM_CHN_ID_2)
        key_handle(img_save, img_display)
        time.sleep_ms(10)
except BaseException as e:
    import sys
    sys.print_exception(e)
media_deinit()
gc.collect()
