from media.display import *
from media.media import *
from media.sensor import *
import time, os, sys, gc
from machine import TOUCH
from machine import Pin
from machine import FPIOA
import cv_lite
import os

#显示的宽高
DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

#视频分辨率
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480

sensor=None

# 初始化并配置sensor
PRESS_KEY_NUM = 53
PRESS_KEY_VAL = 0
brd=os.uname()[-1]
if brd=="k230_canmv_lckfb":
    #按键GPIO Number，根据硬件修改
    PRESS_KEY_NUM = 53
    PRESS_KEY_VAL = 1
elif brd=="k230_canmv_01studio":
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

FONT_X = int(DISPLAY_WIDTH/2-50)
FONT_Y = int(DISPLAY_HEIGHT/2-10)


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

def media_init():
    global sensor,IMG_SAVE_PATH
    try:
        os.stat(IMG_SAVE_PATH)
    except:
        mkdir_p(IMG_SAVE_PATH)

    # 根据硬件选择显示的方法，默认为IDE显示
    # use LCD for display
    Display.init(Display.ST7701, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, to_ide = True, osd_num=1)

    sensor = Sensor(fps=30)
    sensor.reset()
    sensor.set_framesize(w=VIDEO_WIDTH, h=VIDEO_HEIGHT,chn=CAM_CHN_ID_0)
    sensor.set_pixformat(Sensor.RGB888)
    sensor.set_framesize(w=VIDEO_WIDTH, h=VIDEO_HEIGHT, chn=CAM_CHN_ID_2)
    sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)

    sensor.run()
    start_logo=image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.ARGB8888)
    start_logo.draw_string_advanced(30, 30, 32,"Please wait...", color=(255,0, 255, 255))
    Display.show_image(start_logo)
    time.sleep(3)
    cal_grab_rect()

def cal_grab_rect():
    global grab_x, grab_y, grab_w, grab_h

    if VIDEO_WIDTH > VIDEO_HEIGHT:
        grab_h = int(VIDEO_HEIGHT*6/7)
        grab_y = int((VIDEO_HEIGHT - grab_h)/2)
        grab_w = grab_h
        grab_x = int((VIDEO_WIDTH - grab_w)/2)
    else:
        grab_w = int(VIDEO_WIDTH*6/7)
        grab_x = int((VIDEO_WIDTH - grab_w)/2)
        grab_h = grab_w
        grab_y = int((VIDEO_HEIGHT - grab_h)/2)

    print("cal_grab_rect x: " + str(grab_x) + ",y: " + str(grab_y) + ",w: " + str(grab_w) + ",h: " + str(grab_h))

def media_deinit():
    global sensor
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    sensor.stop()
    time.sleep_ms(50)
    Display.deinit()

def save_file(img_0):
    global save_num
    img_name = IMG_SAVE_NAME_BEGIN + str(save_num) + ".jpg"
    cv_lite.save_image(IMG_SAVE_PATH + img_name,[VIDEO_HEIGHT,VIDEO_WIDTH],img_0.to_numpy_ref().copy())
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

def index_init():
    global save_num
    for file in os.listdir(IMG_SAVE_PATH):
        if file is None:
            break
        if file.startswith(IMG_SAVE_NAME_BEGIN):
            index = file.split('_')[1]
            index = int(index.split('.')[0])
            if save_num <= index:
                save_num = index + 1
    print("index_init start " + str(save_num))

def key_handle(img):
    global KEY, grab_x, grab_y, grab_w, grab_h
    if KEY.value()==PRESS_KEY_VAL:   #按键被按下
        time.sleep_ms(10) #消除抖动
        if KEY.value()==PRESS_KEY_VAL: #确认按键被按下
            img_name = save_file(img)
            img.draw_string_advanced(FONT_X, FONT_Y, 100, img_name, color = (0, 0, 255),)
            img.draw_rectangle(grab_x, grab_y, grab_w, grab_h, color = (255, 0, 0), thickness = 2, fill = False)
            Display.show_image(img)
            time.sleep(1.5)
            while KEY.value() == PRESS_KEY_VAL: #检测按键是否松开
                pass
    else:
        img.draw_rectangle(grab_x, grab_y, grab_w, grab_h, color = (255, 0, 0), thickness = 2, fill = False)
        Display.show_image(img) #显示图片

if __name__=="__main__":
    try:
        media_init()
        gpio_init()
        index_init()
        while True:
            img = sensor.snapshot() #拍摄一张图
            key_handle(img)
            time.sleep_ms(10)
    except BaseException as e:
        import sys
        sys.print_exception(e)
    media_deinit()
    gc.collect()
