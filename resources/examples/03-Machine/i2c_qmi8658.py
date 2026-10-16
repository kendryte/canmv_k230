# QMI8658A 6-axis IMU example (accelerometer + gyroscope + temperature, I2C)
#
# Wiring (defaults below, modify the pin constants to match your setup):
#   SCL -> GPIO44 (IIC3_SCL)
#   SDA -> GPIO45 (IIC3_SDA)
#
# QMI8658A I2C address: 0x6A (AD0=0) or 0x6B (AD0=1)

import time
import ustruct
from machine import FPIOA, I2C

# --- QMI8658A register map ---
QMI8658_WHO_AM_I    = 0x00   # expected: 0x05
QMI8658_CTRL1       = 0x02   # accelerometer config
QMI8658_CTRL2       = 0x03   # gyroscope config
QMI8658_CTRL3       = 0x04   # sensor function config
QMI8658_CTRL5       = 0x06   # data processing config
QMI8658_CTRL7       = 0x08   # enable control
QMI8658_CTRL8       = 0x09   # handshake/interrupt mapping control
QMI8658_RST_RESULT  = 0x4D   # reset result register
QMI8658_RESET       = 0x60   # soft reset (write 0xB0)
QMI8658_TEMP_L      = 0x33
QMI8658_AX_L        = 0x35
QMI8658_GX_L        = 0x3B

# CTRL7 bits
CTRL7_ACC_ENABLE = 0x01
CTRL7_GYR_ENABLE = 0x02
CTRL1_ADDR_AI    = 0x40

# --- Config (modify to match your wiring) ---
I2C_BUS    = 3          # IIC3
I2C_SCL    = 44         # GPIO44
I2C_SDA    = 45         # GPIO45
I2C_FREQ   = 400_000    # 400 kHz


class QMI8658A:
    def __init__(self, i2c, addr=0x6A):
        self.i2c = i2c
        self.addr = addr

    def _read_reg(self, reg, n=1):
        return self.i2c.readfrom_mem(self.addr, reg, n)

    def _read_u8(self, reg):
        return self._read_reg(reg, 1)[0]

    def _write_reg(self, reg, data):
        if isinstance(data, int):
            data = bytes([data])
        self.i2c.writeto_mem(self.addr, reg, data)

    def who_am_i(self):
        return self._read_reg(QMI8658_WHO_AM_I, 1)[0]

    def soft_reset(self):
        """Write 0xB0 to RESET register, then wait for sensor recovery."""
        self._write_reg(QMI8658_RESET, 0xB0)
        time.sleep_ms(20)

        # Reference driver polls 0x4D for 0x80 after reset.
        for _ in range(50):  # ~500 ms timeout
            if self._read_u8(QMI8658_RST_RESULT) == 0x80:
                break
            time.sleep_ms(10)

    def configure(self,
                  acc_odr=3,       # 1000 Hz
                  acc_range=0,     # ±2g
                  gyr_odr=3,       # 896.8 Hz
                  gyr_range=5):    # ±512 dps
        """
        ODR:  0=8k, 1=4k, 2=2k, 3=1k, 4=500, 5=250, 6=125, 7=62.5 Hz
        acc_range: 0=±2g, 1=±4g, 2=±8g, 3=±16g
        gyr_range: 0=±16, 1=±32, 2=±64, 3=±128, 4=±256, 5=±512, 6=±1024, 7=±2048 dps
        """
        # CTRL1: enable address auto-increment, little-endian output
        self._write_reg(QMI8658_CTRL1, CTRL1_ADDR_AI)

        # CTRL2: accel config: [6:4]=range, [3:0]=odr
        self._write_reg(QMI8658_CTRL2, ((acc_range & 0x07) << 4) | (acc_odr & 0x0F))

        # CTRL3: gyro config: [6:4]=range, [3:0]=odr
        self._write_reg(QMI8658_CTRL3, ((gyr_range & 0x07) << 4) | (gyr_odr & 0x0F))

        # CTRL8: use STATUS_INT.bit7 as CTRL9 handshake (reference default)
        self._write_reg(QMI8658_CTRL8, 0x80)

        # CTRL5: no low-pass filter
        self._write_reg(QMI8658_CTRL5, 0x00)

        # CTRL7: enable both accel and gyro (write this LAST)
        self._write_reg(QMI8658_CTRL7, CTRL7_ACC_ENABLE | CTRL7_GYR_ENABLE)

        time.sleep_ms(30)  # allow sensor to start sampling

    def get_accel_g(self):
        """Read accelerometer in g units (±2g range)."""
        return self._read_xyz(QMI8658_AX_L, 16384.0)

    def get_gyro_dps(self):
        """Read gyroscope in degrees per second (±512 dps range)."""
        return self._read_xyz(QMI8658_GX_L, 64.0)

    def _read_xyz(self, base_reg, scale):
        # Read byte-by-byte to work even if burst auto-increment is not active.
        data = bytes([self._read_u8(base_reg + i) for i in range(6)])
        x, y, z = ustruct.unpack('<hhh', data)
        return x / scale, y / scale, z / scale

    def get_temperature(self):
        """Read temperature in Celsius."""
        raw = ustruct.unpack('<h', self._read_reg(QMI8658_TEMP_L, 2))[0]
        # Approximate conversion; calibrated offset varies per device
        return raw / 256.0


def main():
    print("=== QMI8658A 6-Axis IMU Test ===")

    # 1. Init I2C
    print("\n[1] Initializing IIC%d (SCL=GPIO%d, SDA=GPIO%d)..." % (I2C_BUS, I2C_SCL, I2C_SDA))
    fpioa = FPIOA()
    fpioa.set_function(I2C_SCL, FPIOA.IIC3_SCL)
    fpioa.set_function(I2C_SDA, FPIOA.IIC3_SDA)
    i2c = I2C(I2C_BUS, freq=I2C_FREQ)

    # 2. Scan I2C bus and auto-detect QMI8658A address
    devices = i2c.scan()
    print("[2] I2C scan result: %s" % [hex(d) for d in devices])

    detected = [a for a in (0x6A, 0x6B) if a in devices]
    if not detected:
        print("ERROR: QMI8658A not found at 0x6A or 0x6B! Check wiring.")
        return
    addr = detected[0]
    print("    Detected QMI8658A at 0x%02X" % addr)

    # 3. Init sensor
    print("\n[3] Initializing QMI8658A...")
    imu = QMI8658A(i2c, addr=addr)
    imu.soft_reset()

    whoami = imu.who_am_i()
    print("    WHO_AM_I = 0x%02X (expected 0x05)" % whoami)
    if whoami != 0x05:
        print("    WARNING: Unexpected WHO_AM_I value!")

    imu.configure()
    print("    Sensor configured: Accel ±2g / Gyro ±512dps @ 1000Hz")

    # 4. Read loop
    print("\n[4] Streaming IMU data (Ctrl+C to stop)...")
    print("    {:>12} {:>12} {:>12} | {:>12} {:>12} {:>12} | {:>8}".format(
          "AccX(g)", "AccY(g)", "AccZ(g)",
          "GyrX(dps)", "GyrY(dps)", "GyrZ(dps)", "Temp(C)"))

    try:
        while True:
            ax, ay, az = imu.get_accel_g()
            gx, gy, gz = imu.get_gyro_dps()
            temp = imu.get_temperature()

            print("    {:>12.4f} {:>12.4f} {:>12.4f} | {:>12.2f} {:>12.2f} {:>12.2f} | {:>8.2f}".format(
                  ax, ay, az, gx, gy, gz, temp))

            time.sleep_ms(200)
    except KeyboardInterrupt:
        print("\n\n    Stopped by user.")


if __name__ == "__main__":
    main()
