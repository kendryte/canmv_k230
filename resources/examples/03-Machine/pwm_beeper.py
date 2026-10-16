# Passive buzzer (beeper) PWM frequency-sweep example.
# Connect a passive buzzer to BEEP_PIN and it sweeps from 500 Hz up to 5 kHz,
# stepping every 500 ms. Modify BEEP_PIN to match your wiring.

import time
from machine import PWM

BEEP_PIN   = 43
DUTY       = 50           # 50% duty cycle
START_FREQ = 500          # 500 Hz
STOP_FREQ  = 5000         # 5 kHz
STEP_FREQ  = 500          # frequency increment per step (Hz)
STEP_MS    = 500          # hold each frequency for 500 ms


def main():
    print("=== Beeper PWM Sweep Test ===")
    print("  GPIO%d  %d → %d Hz  %dms/step  Ctrl+C to stop" %
          (BEEP_PIN, START_FREQ, STOP_FREQ, STEP_MS))

    # Use pin-direct constructor — the driver handles FPIOA mapping internally
    pwm = PWM(BEEP_PIN, freq=START_FREQ, duty=DUTY)

    freq = START_FREQ

    try:
        while True:
            print("  freq = %d Hz" % freq)
            pwm.freq(freq)
            time.sleep_ms(STEP_MS)

            freq += STEP_FREQ
            if freq > STOP_FREQ:
                freq = START_FREQ
    except KeyboardInterrupt:
        pwm.duty(0)
        pwm.deinit()
        print("\n  Stopped.")


if __name__ == "__main__":
    main()
