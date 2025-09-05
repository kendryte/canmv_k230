from machine import Pin, FPIOA, I2C_Slave
import time
import os

# 实例化 FPIOA
fpioa = FPIOA()
# 设置 Pin14 为 GPIO输出模式，用于通知主机有数据更新，初始化为输出高电平
fpioa.set_function(14, FPIOA.GPIO14)
pin = Pin(14, Pin.OUT, pull=Pin.PULL_UP, drive=7)
pin.value(1)

# 设置I2C2的iomux，gpio11为SCL，gpio12为SDA
fpioa.set_function(11, FPIOA.IIC2_SCL, pu = 1)
fpioa.set_function(12, FPIOA.IIC2_SDA, pu = 1)


# I2C 从设备 ID 列表
device_id = I2C_Slave.list()
print("Find I2C slave device:", device_id)

# 构造 I2C 从设备，设备地址为 0x10，模拟 EEPROM 映射的内存大小为 20 字节
i2c_slave = I2C_Slave(device_id[0], addr=0x10, mem_size=20)

# 等待主设备发送数据，并读取映射内存中的值
last_dat = i2c_slave.readfrom_mem(0, 20)
dat = last_dat
while dat == last_dat:
    dat = i2c_slave.readfrom_mem(0, 20)
    time.sleep_ms(1)
    os.exitpoint()

# 等待总线数据传输完毕
time.sleep_ms(100)

print(dat.hex())

i2c_slave.writeto_mem(0, dat)
# 通知主机数据已经写入成功
pin.value(0)
time.sleep_ms(1000)
