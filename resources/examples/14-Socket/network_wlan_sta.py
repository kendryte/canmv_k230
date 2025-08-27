import network
import time

SSID = "TEST"
PASSWORD = "12345678"

sta = network.WLAN(network.STA_IF)

sta.connect(SSID, PASSWORD)

timeout = 10  # 单位：秒
start_time = time.time()

while not sta.isconnected():
    if time.time() - start_time > timeout:
        print("连接超时")
        break
    time.sleep(1)  # 请稍等片刻再连接

print(sta.ifconfig())

print(sta.status())

# 这里的断开网络，只是一个测试。实际应用可不断开
sta.disconnect()
print("断开连接")
print(sta.status())
