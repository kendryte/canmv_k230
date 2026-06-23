# CanMV K230 Changelog

## CanMV K230 SDK Release Notes v1.7

We are pleased to announce the release of **CanMV K230 v1.7**. This release improves boot speed, expands board and display support, adds OpenCV and MicroPython API improvements, updates AI and audio examples, and brings continued RT-Smart, MPP, HAL, USB, storage, and security improvements across the platform.

### 🚀 Key Highlights

* **Faster Boot:** Optimized boot time in both U-Boot and RT-Smart.
* **New Board & Memory Support:** Added support for `k230d_canmv_lushanpi_lite`, `k230_canmv_mrt`, `k230d_canmv_labplus_ai_camera_v2`, DongshanPI LPDDR4, and DongshanPI 2GB DDR configurations.
* **OpenCV & MicroPython API Expansion:** Added OpenCV support, more OpenCV functions and examples, OpenCV/OpenMV comparison scripts, LSM6DSM MicroPython API support, and improved generated CanMV API stubs.
* **AI & Vision Examples:** Update nncase runtime to 2.11.0, Added optimized AI code and post-processing examples for YOLOv8, YOLO11, and YOLO26 classification, detection, segmentation, OBB, and pose tasks.
* **Audio & Media Improvements:** Optimized AEC, PDM audio, PDM noise reduction, AI/RTSP handling, ISP functions, DSI/HDMI timing, I8080 display, SPI/QSPI LCD panels, and OV13850 support.
* **RT-Smart, HAL & Security:** Added OTG, dual CDC, HID, exFAT, SDIO HS200, PMU, FFT, GZIP, PUFs security, `posix_fallocate`, `pthread_get_tid`, and improved GPIO/FPIOA/thread/system handling.

---

### 📦 Component Updates

#### 1. CanMV Core

* **OpenCV & Vision:** Added OpenCV support, more OpenCV functions and examples, OpenCV/OpenMV comparison scripts, and safer OpenCV function handling by removing unsafe `exec()` usage.
* **MicroPython APIs:** Added LSM6DSM MicroPython API support, `tid` function support for retrieving thread IDs, `recv_available` for USB serial, and improved UART/USB-GS write and ioctl handling.
* **Sensor & Display:** Added snapshot failure handling and optional auto-reboot behavior in `Sensor`, object-tree snapshot functionality, ST7789 panel support, LT9611 HDMI timing updates, OSD layer buffer pool fixes, and improved display mode/resolution handling in examples.
* **AI & Examples:** Added optimized CanMV AI code, YOLO post-processing encapsulation and examples for classification/detection/segmentation/OBB/pose tasks, updated drawing examples to `draw_string_advanced`, and added filesystem block-size benchmark tests.
* **Developer Tooling:** Added scripts to generate/update CanMV port stub documentation from C API analysis, improved `gen_canmv_stubs.py` formatting, typing imports, macro handling, module stub generation, and network-interface stub overrides.
* **Build & Runtime:** Added K230 CanMV MRT and K230D CanMV LushanPi Lite configurations, improved build dependency ordering, Makefile resource syncing, IDE debug output, script-running checks, SHA256 implementation, and RVV HAL memory operation usage.

[🔗 Full Changelog](https://github.com/kendryte/canmv_k230/compare/v1.6...v1.7)

#### 2. MPP (Media Process Platform)

* **Audio:** Optimized AEC, optimized PDM audio, added PDM noise reduction, and improved PDM driver cache queue overflow handling.
* **Display & Connector:** Added DSI lane-rate support, pixel-clock correction improvements, I8080 interface support, SPI panel framework improvements, NV3030B QSPI LCD support, MRT MIPI ST7701 initialization, LT9611 custom/VESA HDMI timings, and refined HDMI timing calculation.
* **Sensors & ISP:** Added OV13850 support, fixed IMX335 initialization/reinitialization issues, added mirror/flip support for IMX335/BF3238/SC123SG, added ISP scene switching, and added list-mode/again-range APIs.
* **AI & Video Pipeline:** Optimized AI code to fix memory leak and RTSP issues, enhanced VPU exit cleanup, added SDMA channel reservation APIs, improved virtual display timing, and added validation for virtual display ioctl parameters.
* **Bug Fixes:** Fixed Yahboom ST7701 backlight polarity, updated LCKFB initialization for LushanPi Lite compatibility, fixed I2C transfer return casting, handled DSI command failures as non-fatal, and removed unused connector/WBC includes.

[🔗 Full Changelog](https://github.com/canmv-k230/mpp/compare/canmv-v1.6...canmv-v1.7)

#### 3. RT-Smart (Kernel)

* **Boot & Board Support:** Improved boot time, added K230D OTG support, added K230D CanMV LushanPi Lite configuration, K230 CanMV MRT support, K230D LabPlus AI Camera v2 support, and low-power configuration for `k230d_labplus_ai_camera*`.
* **USB, HID & Drivers:** Added dual CDC ports, HID support for Cherry USB devices, built-in GPIO MSH test commands, PMU driver, ACodec headphone detection, FFT driver, GZIP decompression driver, Synopsys DesignWare SSI private register definitions, and improved DWC2 DMA buffer handling.
* **Storage & Filesystem:** Enabled exFAT in FatFs, added `dfs_elm` preallocation through `f_expand`, added second MMC card mounting, added SDIO0 HS200 support, and improved SDIO PHY delay, bus width, erase group size, and SD status handling.
* **Network & System:** Increased LWIP configuration parameters, increased WLAN password length to 64 bytes, disabled automatic Wi-Fi connection by default, improved AI module initialization/logging, enhanced user fault logs with thread IDs, and improved watchdog behavior.
* **Security:** Added secure boot trusted preload handling and validation, preserved OTP byte-order contracts for PUFS RT/CDE drivers, and refactored PUF firmware CDE operations to use RVV memory routines.
* **Bug Fixes:** Fixed timer handling in `clock_nanosleep` and `nanosleep`, improved partition management and MBR/GPT alignment, added GPIO spinlock support, improved USB host validation, and moved the RISC-V user IRQ frame to the thread kernel stack before signal handling.

[🔗 Full Changelog](https://github.com/canmv-k230/rtsmart/compare/canmv-v1.6...canmv-v1.7)

#### 4. RT-Smart Libraries

* **New Libraries & HAL:** Added `libpeer`, cJSON support, PMU HAL, GZIP decompression driver, HID input driver, FFT driver, and PUFs asymmetric cryptography/cipher/hash/HMAC/CMAC/security configuration support.
* **Syscall & Runtime:** Added `posix_fallocate`, `pthread_get_tid`, mutex retry sleep support, improved linker script section alignment and TLS support, and updated `nncase` runtime to 2.11.0 with kmodels moved to a separate repository.
* **Driver Improvements:** Added GPIO mutex locking for thread safety, streamlined GPIO/FPIOA pin validation, improved input auto-reconnect, optimized small-size `memcpy`/`memset` handling, and refactored watchdog control APIs with `wdt_stop` deprecation notice.
* **Bug Fixes:** Fixed return type issues and corrected FFT ioctl type definitions.

[🔗 Full Changelog](https://github.com/canmv-k230/k230_rtsmart_lib/compare/canmv-v1.6...canmv-v1.7)

#### 5. U-Boot & Board Support

* **Boot:** Improved boot speed.
* **Storage:** Fixed `k230_parse_toc` handling for erased SPI-NAND TOC slots.
* **Board & Memory Support:** Added DongshanPI LPDDR4 configuration, DongshanPI 2GB DDR support, K230D LushanPi Lite board configuration and device tree, K230 CanMV MRT defconfig, K230D LabPlus AI Camera v2 support, and low-power configuration for `k230d_labplus_ai_camera*`.
* **Security:** Added SM4 IV length definition, updated decryption logic, and added PUFsecurity ECP micro-program implementation.

[🔗 Full Changelog](https://github.com/canmv-k230/u-boot/compare/canmv-v1.6...canmv-v1.7)

---

### 🛠 Bug Fixes & Improvements

* **Stability:** Improved boot time, watchdog behavior, thread exit handling, poll-error handling, VPU exit cleanup, DWC2 DMA buffer handling, USB host validation, and AI/RTSP memory handling.
* **Display & Camera:** Added and fixed ST7789, LT9611, ST7701, NV3030B QSPI LCD, I8080, DSI lane-rate, HDMI timing, OV13850, IMX335, and board-specific panel support.
* **MicroPython & Tooling:** Added OpenCV APIs and examples, improved generated stub documentation, improved UART/USB serial handling, and added additional API/test scripts.
* **Storage & Filesystem:** Added exFAT, file preallocation, SDIO HS200, second MMC mounting, SPI-NAND TOC handling, and filesystem benchmark coverage.
* **Security:** Added PUFs/PUFsecurity support, OTP contract fixes, Secure Boot trusted preload validation, and related HAL/driver improvements.
* **Performance:** Added RVV memory operation usage in image processing, PUF firmware, and HAL routines; optimized PDM/AEC audio paths and boot flow.

---

### 🔗 Repository Links

* [[canmv_k230](https://github.com/kendryte/canmv_k230/releases/tag/v1.7)](https://github.com/kendryte/canmv_k230/releases/tag/v1.7)
* [[rtsmart](https://github.com/canmv-k230/rtsmart/releases/tag/canmv-v1.7)](https://github.com/canmv-k230/rtsmart/releases/tag/canmv-v1.7)
* [[mpp](https://github.com/canmv-k230/mpp/releases/tag/canmv-v1.7)](https://github.com/canmv-k230/mpp/releases/tag/canmv-v1.7)
* [[k230_rtsmart_lib](https://github.com/canmv-k230/k230_rtsmart_lib/releases/tag/canmv-v1.7)](https://github.com/canmv-k230/k230_rtsmart_lib/releases/tag/canmv-v1.7)
* [[u-boot](https://github.com/canmv-k230/u-boot/releases/tag/canmv-v1.7)](https://github.com/canmv-k230/u-boot/releases/tag/canmv-v1.7)

**Full Changelog**: https://github.com/kendryte/canmv_k230/compare/v1.6...v1.7

---

## 🚀 CanMV K230 v1.6 Release Notes

We are excited to announce the release of **CanMV K230 v1.6**! 

A major highlight of this release is the introduction of **MPP private pool support**, which significantly streamlines the architecture and makes interacting with the media module much more convenient for developers. Additionally, this version brings heavy performance optimizations using RISC-V Vector (RVV) extensions across the system, expanded AI task capabilities, and deeper LVGL UI integration.

---

### 🧠 CanMV Core

* **New Features**
  * Introduced a new **dual-camera AI example**.
  * Added **manual focus API** to the `sensor` module.
  * Integrated **unit testing and fuzz testing** for the CanMV source.
  * Added support for new boards and panels: **k230d_canmv_mini**.

* **Improvements**
  * **Media Module / MPP:** Migrated to the new MPP architecture featuring **private pool support**, drastically simplifying user-level media module interactions.
  * **UVC Enhancements:** Accelerated UVC host format conversion using **RVV instructions**, and added support for additional UVC GUID formats.
  * **LVGL Integration:** Enhanced FPS tracking and display in the UI. Added support for rendering sensor images directly into LVGL widgets, and introduced a `pixel_format` argument for `media.Display.show_image`.
  * Enabled **3DNR** by default for improved image quality.

* **Bug Fixes**
  * Fixed issues with **WBC + RTSP** pipelines.
  * Refactored virtual display handling and corrected pixel format mapping for 32-bit color formats.
  * Fixed LVGL initialization and de-initialization memory leaks.

---

### 🎥 Media Processing Platform (MPP)

* **New Features**
  * Added **sensor manual exposure API**.
  * Implemented a hardware timer for Video Output (VO) to fine-tune update timing.

* **Improvements**
  * Synchronized with SDK to accelerate UVC host format conversion using RVV.
  * Added fuzz and unit test directories.

* **Bug Fixes**
  * Fixed **3DNR** `mmz` allocation failure.
  * Corrected **gc2093** CSI1 mode AE mapping indices and adjusted 960p mode FPS to 90.
  * Fixed VO boundary checks and rotation bits-per-pixel (BPP) logic.

---

### ⚙️ RT-Smart OS

* **New Features**
  * Added microsecond precision time handling by utilizing the hardware timer (`cpu_ticks_ms`).
  * Added support for **Sitronix CF1124** touch driver.
  * Added USB host class **NCM** and **CH397** support.

* **Improvements**
  * Accelerated **SPI driver** memory allocation and data transfer utilizing RVV optimized functions.
  * Accelerated **UVC host memcpy** with RVV and integrated profiling tools.
  * Increased maximum **WLAN password length** from 32 to 64 bytes.
  * Updated FPIOA and GPIO pin configuration limits to use dynamic constants based on RTC support.

* **Bug Fixes**
  * Fixed PMU IOMUX IO_SEL to use the correct bits per the K230 TRM.
  * Fixed `drv_touch` interrupt enable/disable logic and increased the message buffer.
  * Fixed RT-Smart syscall dispatch to correctly translate Linux riscv64 `munmap`/`exit` numbers.
  * Added bus names and DTS hints to I2C timeout logs for better debugging.

---

### 📚 RT-Smart Libraries

* **New Features**
  * Added **HID keyboard event API** header.
  * Integrated **Tuya SDK** (base `0208bade`).
  * Added new **RVV operations** support.

* **Improvements**
  * Allowed users to set the alpha channel when creating an LVGL display.
  * Streamlined pin validation in GPIO and FPIOA drivers.

* **Bug Fixes**
  * Fixed `lv_display_set_buffers` to use the correct buffer size.
  * Fixed MQTT library build issues.
  * Corrected `drv_gpio_toggle` to cast the current value to `gpio_pin_value_t`.

---

### 🛠️ U-Boot & Board Support

* **New Features & Hardware Support**
  * Added board configurations for **k230d_canmv_mini** and **Wondermk**.

* **Improvements**
  * Increased the timeout for **MMC SD operations** and enabled weak pull-up resistors for better SD card stability.
  * Optimized CI workflow build times with parallel make executions.

---

### 📈 Full Changelog Links

* [canmv](https://github.com/kendryte/canmv_k230/compare/v1.5-legacy...v1.6)
* [mpp](https://github.com/canmv-k230/mpp/compare/canmv-v1.5...canmv-v1.6)
* [rtsmart](https://github.com/canmv-k230/rtsmart/compare/canmv-v1.5...canmv-v1.6)
* [u-boot](https://github.com/canmv-k230/u-boot/compare/canmv-v1.5...canmv-v1.6)
* [k230_rtsmart_lib](https://github.com/canmv-k230/k230_rtsmart_lib/compare/canmv-v1.5...canmv-v1.6)

## CanMV K230 SDK Release Notes v1.5-legacy

This is a **Legacy/Baseline release**. It captures the stable state of the CanMV K230 RTOS environment (based on RTOS SDK v0.6 submodules) before a major transition in the codebase.

If your project requires the current workflow and submodule structure, please use this version. Future releases will introduce significant changes that may not be backward compatible.

### 📌 Release Overview

This version synchronizes all core submodules (rtsmart, mpp, u-boot, etc.) to the **rtos-v0.6** milestone, providing a feature-complete environment for AI, media processing, and RTOS development on the K230.

#### Submodule Version Mapping

* **RT-Smart Kernel:** `rtos-v0.6`
* **MPP (Media Process Platform):** `rtos-v0.6`
* **RT-Smart Libs:** `rtos-v0.6`
* **RT-Smart Examples:** `rtos-v0.6`
* **U-Boot:** `rtos-v0.6`

---

### 🚀 Key Features in this Legacy Baseline

#### 1. Media Process Platform (MPP) Enhancements

* **Audio 3A Integration:** Added support for Acoustic Echo Cancellation (AEC), Automatic Noise Suppression (ANS), and Automatic Gain Control (AGC).
* **New Codecs:** Support for G.711A/U audio encoding and decoding.
* **Video Encoding (VENC):** Added multi-channel encoding demos and support for rotation, mirroring, and OSD (VENC_2D).
* **Video Input (VICAP):** Enabled hardware-level scaling and cropping for multi-channel output.

#### 2. RT-Smart Kernel & Drivers

* **New Hardware Support:** Support for the **K230D** (SIP version) and `k230d_evb` board.
* **Display:** Added support for `nt35516` and `nt35532` panels.
* **New Drivers:** Added `onewire` (DS18x20), `ws2812` (RGB LEDs), and improved CDC/EC200M (4G) support.
* **System:** Added `romfs` support and `statfs` syscall for better filesystem management.

#### 3. Software Libraries & AI Examples

* **Vision Functions:** Introduced `cv_lite` with support for corner detection, undistortion, and rectangle drawing.
* **Networking:** Integrated the `mqttclient` library for IoT applications.
* **New Demos:** Added AI + RTSP streaming examples and a media pipeline demo for saving encoded video to the small core.

---

### 🛠 Stability & Bug Fixes

* Fixed USB CDC 100ms stall and potential kernel crashes during `lsusb`.
* Optimized I2C transfer reliability and fixed touch screen interrupt handling.
* Improved memory management and task scheduling stability in the RT-Smart kernel.

---

### ⚠️ Important Notice for Developers

This version is tagged as **legacy** because it represents the "end of an era" for the current SDK structure.

* **Current Projects:** If you are in the middle of a product cycle, stay on this version.
* **New Projects:** Be aware that the next major version will likely feature a different repository structure or breaking API changes.

### 🔗 Repository Resources

* [SDK Source (Main)](https://github.com/kendryte/canmv_k230/releases/tag/v1.5-legacy)
* [RTOS SDK Submodules](https://github.com/kendryte/k230_rtos_sdk/releases/tag/rtos-v0.6)
* [Pre-built Images](https://github.com/kendryte/canmv_k230/releases/tag/v1.5-legacy/) (Link to your specific download portal if applicable)

## 🚀 CanMV K230 v1.4 Release Notes

We are proud to announce the **v1.4** release of the **CanMV K230** platform!

---

### 🧠 CanMV Core

* **New Features**

  * Added **onewire ds18x20** support.
  * Added **cv\_lite module** with new vision functions (corners, undistort, rects, etc.).
  * Added multiple new demos: **AI+RTSP, WBC RTSP, ws2812**.
  * Added support for new panels **nt35516** and **nt35532**.
  * Added **DHT sensor support**.

* **Improvements**

  * Optimized **MJPEG encoding** and encoder stream handling.
  * Enhanced `machine.*` modules (UART, PWM, I2C, Timer, Pin, reset/bootloader).
  * Improved LVGL, VFS, GC, IDE resource management, and examples.

* **Bug Fixes**

  * Multiple fixes in `aidemo`, `lvgl`, `Timer`, `ADC`, `PWM`, `UART`, and `I2C`.
  * Fixed IDE file save/delete issues.

[🔗 View detailed changes](https://github.com/canmv-k230/canmv/compare/v1.3...v1.4)

---

### 🎥 Media Processing Platform (MPP)

* **New Features**

  * Added new panel: **nt35532**.
  * Added **autofocus** support (dw9714p).
  * Added GitLab CI auto-release support.

* **Improvements**

  * Updated panel timings, connector drivers.

* **Bug Fixes**

  * Fixed **MIPI DSI timing** calculation.
  * Fixed **sensor bf3238** mode list.

[🔗 View detailed changes](https://github.com/canmv-k230/mpp/compare/rtos-v0.5...canvm-v1.4)

---

### ⚙️ RT-Smart OS

* **New Features**

  * Added new driver: **onewire ds18x20**.
  * Added new board config: **k230d\_evb**.
  * Enabled **romfs** support.
  * Added syscall: **statfs**.
  * Added **OSD enable/disable** and **VO debug tool**.

* **Improvements**

  * Updated UART, I2C, SPI, PWM, WS2812, FPIOA, and netmgmt drivers.
  * Adapted CDC and EC200M to the serial framework.
  * Changed ethernet hostname to **canmv\_xxxx**.

* **Bug Fixes**

  * Fixed drv\_touch, lwp\_pmutex, USB CDC 100ms stall, PWM, fpioa, and malloc handling.
  * Fixed `lsusb -t` crashed.

[🔗 View detailed changes](https://github.com/canmv-k230/rtsmart/compare/rtos-v0.5...canvm-v1.4)

---

### 📚 RT-Smart Libraries

* **New Features**

  * Added **syscall for mq**.
  * Added **drv\_ws2812**, **statfs**, **reset/reset\_to\_bootloader**, and **netmgmt HAL**.
  * Added **mqttclient 3rd-party library**.

* **Improvements**

  * Enhanced drivers (UART, PWM, ADC, I2C, GPIO, FPIOA).
  * Added WLAN STA support for **open SSIDs**.

* **Bug Fixes**

  * Fixed UART, PWM, and FPIOA bugs.
  * Fixed mqttclient build failure.
  * Added `pthread_mutex_lock` fix.

[🔗 View detailed changes](https://github.com/canmv-k230/k230_rtsmart_lib/compare/rtos-v0.5...canvm-v1.4)

---

### 🛠️ U-Boot Bootloader

* **New Features**

  * Improved boot speed.
  * Updated prebuilt builds.

* **Improvements**

  * Updated board configs for **k230d\_evb** and **junroc**.
  * Updated labplus\_1956 GPIO/I2C defaults.

* **Bug Fixes**

  * Fixed GitHub Action push issue.

[🔗 View detailed changes](https://github.com/canmv-k230/u-boot/compare/rtos-v0.5...canvm-v1.4)

---

### 📈 Full Changelog

* [canmv](https://github.com/canmv-k230/canmv/compare/v1.3...v1.4)
* [mpp](https://github.com/canmv-k230/mpp/compare/rtos-v0.5...canvm-v1.4)
* [rtsmart](https://github.com/canmv-k230/rtsmart/compare/rtos-v0.5...canvm-v1.4)
* [u-boot](https://github.com/canmv-k230/u-boot/compare/rtos-v0.5...canvm-v1.4)
* [k230\_rtsmart\_lib](https://github.com/canmv-k230/k230_rtsmart_lib/compare/rtos-v0.5...canvm-v1.4)

## 🚀 CanMV K230 v1.3 Release Notes

We are proud to announce the **v1.3** release of the **CanMV K230** platform! This release brings together all the improvements from `v1.3-rc` and `v1.3-rc2`, featuring enhanced hardware support, critical bug fixes, and new tools to streamline development on the K230 SoC.

---

### 🧠 CanMV Core

* **MicroPython Integration**:

  * Improved hardware abstraction with expanded module support.
  * Fixed HAL transmit data error.
* **Peripheral Fixes**:

  * Fixed `machine.I2C` not raising errors on failed transfers.
  * Corrected `machine.FPIOA` pin function mapping bugs.
* **Display Enhancements**:

  * Improved compatibility and performance with various display interfaces.
* **Stability**:

  * Addressed sensor initialization and memory management issues.

[🔗 View detailed changes](https://github.com/canmv-k230/canmv/compare/canmv-v1.2.2...canmv-v1.3)

---

### 🎥 Media Processing Platform (MPP)

* **Video Encoding**:

  * Added `kd_mapi_venc_request_idr` to allow IDR frame generation.
* **Image Handling**:

  * Enhanced mirror and flip functionality for better image control.

[🔗 View detailed changes](https://github.com/canmv-k230/mpp/compare/canmv-v1.2.2...canmv-v1.3)

---

### ⚙️ RT-Smart OS

* **Driver Improvements**:

  * Fixed I2C transfer timeout.
  * Resolved issues with RTL8189 AP mode.
* **System Improvements**:

  * Enhanced memory management and task scheduling.
* **Peripheral Support**:

  * Extended support for I2C, SPI, and other interfaces.
* **Filesystem**:

  * Improved reliability and performance under edge workloads.

[🔗 View detailed changes](https://github.com/canmv-k230/rtsmart/compare/canmv-v1.2.2...canmv-v1.3)

---

### 🛠️ U-Boot Bootloader

* **New Hardware Support**:

  * Added support for the `k230d_evb` board.
* **Boot Enhancements**:

  * Faster boot process and better boot stability.

[🔗 View detailed changes](https://github.com/canmv-k230/u-boot/compare/canmv-v1.2.2...canmv-v1.3)

---

### 📚 `k230_rtsmart_lib` (New Component)

A new library package for RT-Smart apps:

* Simplifies application development on RT-Smart OS.
* Promotes reusable logic and streamlined integration.

[🔗 Explore the repository](https://github.com/canmv-k230/k230_rtsmart_lib)

---

### 🧪 Tooling

* **Image Generator Update**:

  * Added support for new `kdimg` format for firmware images.
    ([PR #6](https://github.com/kendryte/canmv_k230/pull/6) by [@kendryte747](https://github.com/kendryte747))

---

### 📈 Full Changelog

* [canmv\_k230](https://github.com/kendryte/canmv_k230/compare/canmv-v1.2.2...canmv-v1.3)
* [canmv](https://github.com/canmv-k230/canmv/compare/canmv-v1.2.2...canmv-v1.3)
* [mpp](https://github.com/canmv-k230/mpp/compare/canmv-v1.2.2...canmv-v1.3-rc)
* [rtsmart](https://github.com/canmv-k230/rtsmart/compare/canmv-v1.2.2...canmv-v1.3)
* [u-boot](https://github.com/canmv-k230/u-boot/compare/canmv-v1.2.2...canmv-v1.3-rc)

---

We recommend all users upgrade to **v1.3** to benefit from improved performance, broader hardware compatibility, and a more robust development experience.

For issues, feedback, or contributions, visit our [GitHub organization](https://github.com/kendryte/canmv_k230).

## v1.2.2

Version 1.2.2 introduces minor bug fixes and new features to enhance functionality and performance.

### New Features

#### **RT-Smart**
- Enhanced the `tsensor` driver with mutex support for improved concurrency and stability.

#### **CanMV**
- Added support for a new MIPI panel with a resolution of 368x552.
- Introduced the `machine.chipid` and `machine.temperature` APIs for accessing unique device identifiers and temperature data.
- Implemented `os.urandom` for generating random bytes and `os.statvfs` for retrieving filesystem statistics.

### Bug Fixes

#### **RT-Smart**
- Resolved an issue where the MTP could not monitor the `data` partition effectively.

#### **CanMV**
- Fixed a bug that caused sensor snapshot failures when the sensor channel was bound to display.

## v1.2.1

Version 1.2.1 is a minor bug fix for v1.2

### Bug Fixes

- **CanMV**:
  - Fix sensor and display release vb, now can remove try and catch block
  - Fix machine.I2C

## v1.2

Version 1.2 brings several new features, improvements, and bug fixes to the project. This update focuses on RTOS support, new hardware support, and various enhancements across the CanMV, RT-Smart, MPP, and U-Boot components.

### Project Updates

- **RTOS Only SDK**: Added support for RTOS-only SDK build sample code and AI demo compile support.
- **New Board Support**: Added support for board **ATK-DNK230D**.

### New Features

- **CanMV**:
  - Added **soft I2C support** for software-driven I2C communication.
  - Added **SPI LCD driver** support for SPI-based LCD displays.
  - Integrated **Audio 3A support** for improved audio processing.
  - Expanded **hardware support** with new boards, including **ATK-DNK230D**.
  - Added **MIPI DSI debugger support** for debugging MIPI DSI displays.
  - Introduced new **machine.TOUCH module** for touchscreen functionality.
  - New board type format added to display **board memory size**.

- **RT-Smart**:
  - Added **dynamic memory size detection** support.
  - Integrated support for **4G module (EC200M)**.
  - Added **probe support for touch devices**, including a new driver for **CHCS5XXX**.
  - Introduced **FPIOA driver** for flexible I/O array support.
  - Added **USB host split** support.
  - Improved project structure to allow users to **specify custom app folder**.
  - Added support for **resizing GPT partitions**.

- **MPP**:
  - Added **MIPI DSI debugger support** for debugging MIPI DSI displays.
  - Added support for new **sensor models (bf3238, sc132gs)**.
  - Added support for new **2.4-inch, 480x640 LCD** display.
  - Added **build sample support** for MPP.

- **U-Boot**:
  - Added **dynamic memory size detection**.
  - Integrated support for new **boards** including **ATK-DNK230D**.
  - Enhanced **Kburn OTP support**.

### Bug Fixes

- **CanMV**:
  - Fixed **sensor MCM mode error**.
  - Fixed **LVGL pixel format** handling issue.
  - Resolved **SPI driver** issues.
  - Fixed **UART driver** communication problems.
  - Corrected **machine.PWM duty** cycle error.
  - Fixed **NN image inference error**.

- **RT-Smart**:
  - Fixed issues with **SPI driver**.
  - Corrected **I2C driver** issues.
  - Resolved **UART driver** bugs.
  - Fixed **CherryUSB** functionality.

- **MPP**:
  - Fixed **sensor register configuration** for **GC2093**, **OV5647**, and **IMX335**.
  - Fixed **LCD timing** for 3.5-inch 480x800 ST7701 display.

## v1.1

Version 1.1 is a complete overhaul for the K230 platform, designed to be more user-friendly and development-oriented.

### Project Updates

- **Repo Management**: Subprojects are now managed with `repo`.
- **Dependencies**: Linux dependencies have been removed.
- **Build System**: Introduction of a new compilation system.
- **Board Support**: Added support for new boards, including DonshanPI, LCKFB, and others.

### New Features

- **CanMV**:
  - Added support for WS2812 LEDs via GPIO.
  - Network support: Ethernet and Wi-Fi.
  - New board support: DonshanPI, LCKFB, etc.
  - Added support for a new display panel: ILI9806.
  - Audio module update: Added volume control capabilities.
  
- **RT-Smart**:
  - Automatic partition creation and mounting to `/data`.
  - Project management via Kconfig.
  - Added support for WS2812 LEDs via GPIO.
  - Added support for I2C slave mode.
  - Ethernet-over-USB support with RTL8152.
  - WLAN support: RTL8189 and CYW43xx.
  - Added support for NTP (Network Time Protocol).

- **MPP (Multi-Processor Platform)**:
  - Sensor driver framework updated, now support GC2093, OV5647, and IMX335.
  - Updated screen driver framework.

- **U-Boot**:
  - New `kburn` tool, no longer dependent on DRAM.
  - Added support for new boards: DonshanPI, LCKFB, and more.

### Bug Fixes

- **CanMV**:
  - Fixed IOMUX pins (36, 37).
  - Released UART3 for user access.

- **RT-Smart**:
  - Fixed missing I2C, SPI, and UART device nodes.
