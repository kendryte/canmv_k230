# LSM6DSM 6-Axis IMU Sensor Example
#
# Usage:
#   acce = LSM6DSM('acce')    # or LSM6DSM(LSM6DSM.ACCE)
#   gyro = LSM6DSM('gyro')    # or LSM6DSM(LSM6DSM.GYRO)
#   temp = LSM6DSM('temp')    # or LSM6DSM(LSM6DSM.TEMP)
#   step = LSM6DSM('step')    # or LSM6DSM(LSM6DSM.STEP)
#   data = imu.read()
#   imu.deinit()

from machine import LSM6DSM
import time

print("=== LSM6DSM IMU Sensor Test ===\n")

# --- Accelerometer ---
# At rest on flat surface: x≈0, y≈0, z≈1000 (or -1000 depending on orientation)
print("--- Accelerometer (mG) ---")
acce = LSM6DSM('acce')
print(acce)
for i in range(5):
    x, y, z = acce.read()
    print("  [%d] x: %6d, y: %6d, z: %6d mG" % (i, x, y, z))
    time.sleep_ms(100)
acce.deinit()

# --- Gyroscope ---
# At rest: all values should be close to 0
# Kernel 'sensor' cmd prints dps but the values are actually mdps (label bug)
print("\n--- Gyroscope ---")
gyro = LSM6DSM(LSM6DSM.GYRO)
print(gyro)
for i in range(5):
    x, y, z = gyro.read()
    print("  [%d] x: %7d mdps (%5.1f dps), y: %7d mdps (%6.1f dps), z: %7d mdps (%5.1f dps)"
          % (i, x, x/1000.0, y, y/1000.0, z, z/1000.0))
    time.sleep_ms(100)
gyro.deinit()

# --- Temperature ---
print("\n--- Temperature ---")
temp = LSM6DSM(LSM6DSM.TEMP)
print(temp)
for i in range(3):
    t = temp.read()
    print("  [%d] %.2f C" % (i, t))
    time.sleep_ms(500)
temp.deinit()

# --- Step Counter ---
print("\n--- Step Counter ---")
step = LSM6DSM('step')
print(step)
for i in range(3):
    s = step.read()
    print("  [%d] steps: %d" % (i, s))
    time.sleep_ms(500)
step.deinit()

print("\nLSM6DSM test complete.")
