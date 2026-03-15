---
name: idf-flash
description: >
  Use when the user asks to build, flash, or monitor an ESP-IDF project on a
  **locally connected** ESP32 (direct USB cable, not via the ESP32 Workbench).
  Triggers on "flash", "upload", "build", "idf.py", "monitor", "serial console".
  Do NOT use this skill when the user mentions a "slot", "workbench", or
  "esp32-workbench.local" — use `esp32-workbench-serial-flashing` instead.
---

# ESP-IDF Build & Local Flash

Build ESP-IDF projects and flash to a locally connected ESP32 via USB.

> **If the device is on the ESP32 Workbench** (user mentions a slot, workbench,
> or remote Pi), use the `esp32-workbench-serial-flashing` skill instead.

## Build Commands

```bash
source /opt/esp-idf/export.sh
idf.py build                           # Build only
idf.py flash                           # Build (if needed) and flash
idf.py fullclean                       # Clean build directory
```

## Flash Size and Partition Tables

> **Flash size defaults to 4MB.** Use `CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y` in
> `sdkconfig.defaults` and `--flash_size 4MB` with esptool. Only use a
> different size when the actual flash is known (e.g. `esptool.py flash_id`
> or from the datasheet).

Partition tables must fit within the flash size. Two common layouts:

| File | Flash size | App partition size | Use when |
|------|-----------|-------------------|----------|
| `partitions-4mb.csv` | 4MB (default) | 1216K | Unknown or 4MB flash |
| `partitions.csv` | 8MB+ | 1536K | Flash confirmed > 4MB |

Set the partition table in `sdkconfig.defaults`:
```
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-4mb.csv"
```

## Local Flash (USB)

```bash
source /opt/esp-idf/export.sh
idf.py -p /dev/ttyUSB0 flash           # Flash to specific port
idf.py -p /dev/ttyUSB0 monitor         # Open serial monitor
idf.py -p /dev/ttyUSB0 flash monitor   # Flash and monitor
```

### esptool flags by device type

| Device | `--before` | `--after` |
|--------|-----------|----------|
| ESP32-S3 (ttyACM, native USB) | `usb_reset` | `hard_reset` |
| ESP32-C3 (ttyACM, native USB) | `usb_reset` | `watchdog_reset` |
| ESP32 (ttyUSB, UART bridge) | `default_reset` | `hard_reset` |

## Boot Mode

To put ESP32 in bootloader mode:
1. Hold **BOOT** button
2. Press **RESET** button
3. Release **RESET**, then **BOOT**

## Monitor Shortcuts

- `Ctrl+]` - Exit monitor
- `Ctrl+T` `Ctrl+H` - Show help
- `Ctrl+T` `Ctrl+R` - Reset target

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Failed to connect | Enter boot mode (BOOT+RESET sequence) |
| No serial port found | Check USB cable, `ls /dev/ttyUSB*` |
| Permission denied | `sudo usermod -aG dialout $USER`, re-login |
