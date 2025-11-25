import os, time
from machine import FPIOA, I2C, TOUCH, Pin

fpioa = FPIOA()
# touch int
fpioa.set_function(2, FPIOA.GPIO2)
# touch rst
fpioa.set_function(3, FPIOA.GPIO3)

# touch i2c
i2c2=I2C(2, scl = 11, sda = 12)
# print(i2c2.scan())

#touch = TOUCH(1, i2c = i2c2)
touch = TOUCH(1, i2c = i2c2, rst = 2, int = 3)
# touch = TOUCH(1, i2c = i2c3, rst = 2, int = 3, range_x = 480, range_y = 800)

print(touch)

while True:
    point = touch.read(5)

    if len(point):
        print(point)
    time.sleep(0.1)
