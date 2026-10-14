import os
import time

BASE_DIR = "/data"
FILE_PATH = BASE_DIR + "/bench.bin"

TOTAL_SIZE = 8 * 1024 * 1024   # 8MB

# sweep: 1KiB → 1MiB
BLOCK_SIZES = [
    1024, 2048, 4096,
    8*1024, 16*1024, 32*1024,
    64*1024, 128*1024, 256*1024, 512*1024,
    1024*1024
]


def remove_file(path):
    try:
        os.remove(path)
    except:
        pass


def write_test(path, total_size, block_size):
    buf = b'\x55' * block_size
    written = 0

    start = time.ticks_ms()

    with open(path, "wb") as f:
        while written < total_size:
            f.write(buf)
            written += block_size

    end = time.ticks_ms()
    elapsed = time.ticks_diff(end, start) / 1000

    speed = (total_size / (1024 * 1024)) / max(elapsed, 0.001)
    return speed


def read_test(path, block_size):
    total = 0

    start = time.ticks_ms()

    with open(path, "rb") as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            total += len(data)

    end = time.ticks_ms()
    elapsed = time.ticks_diff(end, start) / 1000

    speed = (total / (1024 * 1024)) / max(elapsed, 0.001)
    return speed


def run_sweep():
    print("Block Size Sweep Benchmark")
    print("Path:", FILE_PATH)
    print("Total size:", TOTAL_SIZE // (1024 * 1024), "MB\n")

    print("{:>8} | {:>10} | {:>10}".format("Block", "Write MB/s", "Read MB/s"))
    print("-" * 36)

    try:
        for bs in BLOCK_SIZES:
            remove_file(FILE_PATH)

            w = write_test(FILE_PATH, TOTAL_SIZE, bs)
            r = read_test(FILE_PATH, bs)

            if bs < 1024:
                label = "{}B".format(bs)
            else:
                label = "{}KB".format(bs // 1024)

            print("{:>8} | {:>10.2f} | {:>10.2f}".format(label, w, r))
    finally:
        remove_file(FILE_PATH)


run_sweep()

# Block Size Sweep Benchmark
# Path: /data/bench.bin
# Total size: 8 MB
# 
#    Block | Write MB/s |  Read MB/s
# ------------------------------------
#      1KB |       0.41 |       2.23
#      2KB |       0.87 |       3.75
#      4KB |       1.82 |       6.18
#      8KB |       3.24 |       9.35
#     16KB |       8.09 |      11.70
#     32KB |      10.11 |      14.06
#     64KB |      10.14 |      14.04
#    128KB |      10.13 |      15.16
#    256KB |      10.15 |      15.37
#    512KB |       9.94 |      14.92
#   1024KB |      10.17 |      15.10
