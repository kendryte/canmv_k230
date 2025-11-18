# Camera Example
import time, os, sys

from media.sensor import *
from media.display import *
from media.media import *

from machine import FPIOA, Pin, SPI, SPI_LCD

sensor = None

def init_spi_lcd(width = 320, height = 240):
    fpioa = FPIOA()

    fpioa.set_function(19, FPIOA.GPIO19)
    pin_cs = Pin(19, Pin.OUT, pull=Pin.PULL_NONE, drive=15)
    pin_cs.value(1)

    fpioa.set_function(20, FPIOA.GPIO20)
    pin_dc = Pin(20, Pin.OUT, pull=Pin.PULL_NONE, drive=15)
    pin_dc.value(1)

    fpioa.set_function(44, FPIOA.GPIO44, pu = 1)
    pin_rst = Pin(44, Pin.OUT, pull=Pin.PULL_UP, drive=15)

    # spi
    #    fpioa.set_function(14, fpioa.QSPI0_CS0)
    fpioa.set_function(15, fpioa.QSPI0_CLK)
    fpioa.set_function(16, fpioa.QSPI0_D0)
    #    fpioa.set_function(17, fpioa.QSPI0_D1)

    spi1 = SPI(1,baudrate=1000*1000*50, polarity=1, phase=1, bits=8)

    lcd = SPI_LCD(spi1, pin_dc, pin_cs, pin_rst)

    lcd.configure(width, height, hmirror = False, vflip = True, bgr = False)

    img = lcd.init()

    return lcd, img

try:
    print("camera_test")

    # construct a Sensor object with default configure
    sensor = Sensor()
    # sensor reset
    sensor.reset()
    # set hmirror
    # sensor.set_hmirror(False)
    # sensor vflip
    # sensor.set_vflip(False)

    # set chn0 output size
    sensor.set_framesize(width = 320, height = 240)
    # set chn0 output format
    sensor.set_pixformat(Sensor.RGB565)

    lcd , _ = init_spi_lcd()



    # sensor start run
    sensor.run()

    fps_clock = time.clock()

    fps = 0.0

    while True:
        os.exitpoint()

        fps_clock.tick()

        img = sensor.snapshot()
        img.draw_string_advanced(0,0,16, f"{fps : .3f}", color = (255, 0, 0))
        lcd.show(img)

        fps = fps_clock.fps()
except KeyboardInterrupt as e:
    print("user stop: ", e)
except BaseException as e:
    import sys
    sys.print_exception(e)
finally:
    # sensor stop run
    if isinstance(sensor, Sensor):
        sensor.stop()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # release media buffer

