# CanMV K230 Changelog

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
