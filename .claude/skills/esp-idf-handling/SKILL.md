---
name: esp-idf-handling
description: >
  Complete ESP-IDF lifecycle: project setup, build, flash, monitor, and OTA.
  Automatically detects whether a workbench is available or the device is
  connected locally via USB. Covers sdkconfig, partition tables, esptool,
  RFC2217 remote flashing, GPIO download mode, OTA updates, crash recovery,
  and flapping. Triggers on "flash", "build", "upload", "idf.py", "monitor",
  "serial console", "slot", "workbench", "esptool", "OTA", "erase",
  "download mode", "crash loop", "flapping", "bricked", "menuconfig",
  "set-target", "sdkconfig", "partition".
---

# ESP-IDF Handling

Complete lifecycle for ESP-IDF projects — from project creation to flashing
and monitoring. Automatically adapts to local USB or remote workbench.

## Step 1: Detect Environment

Determine whether a workbench is available or the device is local.

```bash
curl -s http://workbench.local:8080/api/info
```

- **Response received** → workbench is available, use remote flashing (RFC2217/OTA)
- **Connection refused / timeout** → try the discovery script:
  ```bash
  sudo python3 .claude/skills/esp-idf-handling/discover-workbench.py --hosts
  ```
- **Still no response** → no workbench, use local USB flashing

## Step 2: Project Setup

```bash
source /opt/esp-idf/export.sh
idf.py create-project <name>           # Create new project
idf.py set-target esp32s3              # Set target chip (esp32, esp32s3, esp32c3, etc.)
idf.py menuconfig                      # Interactive configuration (writes sdkconfig)
```

### sdkconfig.defaults

Put persistent config in `sdkconfig.defaults` (not `sdkconfig` which is generated):

```
CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-4mb.csv"
```

## Step 3: Build

```bash
source /opt/esp-idf/export.sh
idf.py build                           # Build
idf.py fullclean                       # Clean build directory
```

## Flash Size and Partition Tables

> **Flash size defaults to 4MB.** Use `CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y` in
> `sdkconfig.defaults` and `--flash_size 4MB` with esptool. Only use a
> different size when the actual flash is known (e.g. `esptool.py flash_id`
> or from the datasheet).

| File | Flash size | App partition size | Use when |
|------|-----------|-------------------|----------|
| `partitions-4mb.csv` | 4MB (default) | 1216K | Unknown or 4MB flash |
| `partitions.csv` | 8MB+ | 1536K | Flash confirmed > 4MB |

## Step 4a: Flash — Local USB

When the device is connected directly via USB (no workbench).

```bash
source /opt/esp-idf/export.sh
idf.py -p /dev/ttyUSB0 flash           # Flash to specific port
idf.py -p /dev/ttyUSB0 monitor         # Open serial monitor
idf.py -p /dev/ttyUSB0 flash monitor   # Flash and monitor
```

### esptool flags by device type

| Device | `--before` | `--after` |
|--------|-----------|----------|
| All chips (via `/api/flash`) | `default-reset` | `no-reset` |
| ESP32 (local USB, ttyUSB) | `default-reset` | `hard-reset` |
| ESP32-C3/S3 (local USB, ttyACM) | `default-reset` | `no-reset` |

**Note:** On the workbench, use `--after no-reset` and call
`POST /api/serial/reset` after flash to reboot the device. Stop debug
before flashing native USB chips (serial + JTAG share USB).

### Boot mode (manual)

1. Hold **BOOT** button
2. Press **RESET** button
3. Release **RESET**, then **BOOT**

## Step 4b: Flash — Workbench (RFC2217)

When a workbench is available. Use serial flashing when:
- Device has **no firmware** (blank/bricked/first flash)
- Firmware **lacks OTA support**
- You need to **erase NVS** or flash a **bootloader/partition table**
- Device has **no WiFi connectivity**

### Discover devices and slot

Slots are mapped to physical USB hub ports via prefix matching (configured in `workbench.json`). There are 3 fixed slots: SLOT1 (:4001), SLOT2 (:4002), SLOT3 (:4003). Always read the slot info from `/api/devices` to verify the device is present.

```bash
curl -s http://workbench.local:8080/api/devices | jq .
```

Response fields per slot: `label`, `state`, `url` (RFC2217, auto-assigned port), `present`, `running`, `detected_chip`.

### Flash via RFC2217

Flashing uses esptool from the host through the RFC2217 proxy. Binaries
stay on the host — no SCP needed. Use `--after no-reset` to avoid USB
re-enumeration, then reboot via the API.

**Bootloader offsets:** Classic ESP32 → `0x1000`, all newer chips (C3/S3/C6/H2) → `0x0000`.

```bash
# Get the RFC2217 URL
SLOT_URL=$(curl -s http://workbench.local:8080/api/devices | jq -r '.slots[0].url')

# Flash (binaries stay on host)
esptool --port "$SLOT_URL" --chip esp32c3 \
  --before default-reset --after no-reset \
  write-flash --flash-mode dio --flash-size 4MB \
  0x0000 bootloader.bin 0x8000 partition-table.bin 0x10000 firmware.bin

# Reboot device into new firmware
curl -X POST http://workbench.local:8080/api/serial/reset \
  -H "Content-Type: application/json" -d '{"slot":"SLOT1"}'
```

### Workbench API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/devices` | List all slots with state, device node, RFC2217 URL |
| GET | `/api/info` | System info (host IP, hostname, slot counts) |
| POST | `/api/serial/reset` | Hardware reset via DTR/RTS pulse, returns boot output |
| POST | `/api/serial/recover` | Manual flap recovery trigger `{"slot": "slot-1"}` |
| POST | `/api/serial/release` | Release GPIO after flashing, reboot into firmware `{"slot": "slot-1"}` |

### Serial reset

```bash
curl -X POST http://workbench.local:8080/api/serial/reset \
  -H 'Content-Type: application/json' \
  -d '{"slot": "slot-1"}'
```

### Slot states

| State | Meaning | Can flash? |
|-------|---------|------------|
| `absent` | No USB device | No |
| `idle` | Ready | Yes (via RFC2217) |
| `resetting` | Reset in progress | No |
| `monitoring` | Monitor active | No |
| `flapping` | USB storm, recovery failed or pending | No |
| `recovering` | USB unbound, recovery in progress | No |
| `download_mode` | GPIO holding BOOT LOW, device stable in bootloader | Yes (direct serial on Pi) |

## Step 4c: Flash — Workbench OTA

Use OTA when the device already runs firmware with an OTA HTTP endpoint and
is on the WiFi network. Faster than serial and doesn't block the serial port.

```bash
# 1. Upload firmware to workbench
curl -X POST http://workbench.local:8080/api/firmware/upload \
  -F "project=my-project" \
  -F "file=@build/firmware.bin"

# 2. Verify upload
curl -s http://workbench.local:8080/api/firmware/list | jq .

# 3. Trigger OTA on the ESP32 via HTTP relay
OTA_BODY=$(echo -n '{"url":"http://workbench.local:8080/firmware/my-project/firmware.bin"}' | base64)
curl -X POST http://workbench.local:8080/api/wifi/http \
  -H 'Content-Type: application/json' \
  -d "{\"method\": \"POST\", \"url\": \"http://192.168.4.2/ota\", \"headers\": {\"Content-Type\": \"application/json\"}, \"body\": \"$OTA_BODY\", \"timeout\": 30}"

# 4. Monitor OTA progress via UDP logs
curl "http://workbench.local:8080/api/udplog?limit=50"
```

### Firmware repository management

```bash
# List all uploaded firmware
curl http://workbench.local:8080/api/firmware/list

# Delete a firmware file
curl -X DELETE http://workbench.local:8080/api/firmware/delete \
  -H 'Content-Type: application/json' \
  -d '{"project": "my-project", "filename": "firmware.bin"}'

# Download URL for ESP32: http://workbench.local:8080/firmware/<project>/<filename>
```

## Step 5: Monitor

```bash
# Local
idf.py -p /dev/ttyUSB0 monitor

# Workbench — via serial monitor API (see workbench-logging skill)
# or via UDP logs
curl "http://workbench.local:8080/api/udplog?limit=50"
```

### Monitor shortcuts

- `Ctrl+]` — Exit monitor
- `Ctrl+T` `Ctrl+H` — Show help
- `Ctrl+T` `Ctrl+R` — Reset target

## GPIO Download Mode (Workbench)

When DTR/RTS reset doesn't work (no auto-download circuit), use GPIO.

### Pin mapping

| Pi GPIO | ESP32 Pin | Function |
|---------|-----------|----------|
| GPIO17 | EN | **RST** — pull LOW to reset |
| GPIO18 | GPIO0 | **BOOT** — hold LOW during reset to enter download mode |

Allowed BCM pins: `5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27`

### Enter download mode

```bash
# 1. Hold BOOT LOW
curl -X POST http://workbench.local:8080/api/gpio/set \
  -H 'Content-Type: application/json' -d '{"pin": 18, "value": 0}'
sleep 1
# 2. Pull EN LOW (reset)
curl -X POST http://workbench.local:8080/api/gpio/set \
  -H 'Content-Type: application/json' -d '{"pin": 17, "value": 0}'
sleep 0.2
# 3. Release EN HIGH (ESP32 exits reset, samples BOOT=LOW → download mode)
curl -X POST http://workbench.local:8080/api/gpio/set \
  -H 'Content-Type: application/json' -d '{"pin": 17, "value": 1}'
sleep 0.5
# 4. Release BOOT HIGH
curl -X POST http://workbench.local:8080/api/gpio/set \
  -H 'Content-Type: application/json' -d '{"pin": 18, "value": 1}'
```

### Flash after GPIO download mode

```bash
sleep 5  # Wait for USB re-enumeration
esptool.py --port "rfc2217://workbench.local:<PORT>?ign_set_control" \
  --chip esp32s3 --before=no_reset write_flash @flash_args
```

### GPIO probe — auto-detect board capabilities

Not all boards have EN/BOOT wired to Pi GPIOs. Run once per board:

| GPIO probe output | USB reset output | Board type |
|-------------------|-----------------|------------|
| `boot:0x23` (DOWNLOAD) | — | **GPIO-controlled** — Pi GPIOs wired to EN/BOOT |
| No output / normal boot | `rst:0x15` | **USB-controlled** — use DTR/RTS |
| No output | No output | No control — check wiring or wrong slot |

**Dual-USB hub boards** have onboard auto-download circuit — GPIO wiring not needed.

## Crash-Loop Recovery (Workbench)

When firmware crashes on boot (repeated `rst:0xc (RTC_SW_CPU_RST)` with backtraces),
use the `/api/flash` endpoint to reflash working firmware. The portal handles proxy
lifecycle safely. If the device is completely unresponsive, use GPIO download mode
(if available) or reflash directly on the Pi with the portal stopped.

## Flapping & Automatic Recovery (Workbench)

Empty or corrupt flash can cause USB connection cycling (`flapping` state).
The portal actively recovers by unbinding USB and re-entering download mode.

### With GPIO

```
State flow: flapping → recovering → download_mode → (flash firmware) → idle
```

After portal reaches `download_mode`, upload and flash on the Pi:

```bash
scp build/bootloader/bootloader.bin build/partition_table/partition-table.bin \
    build/ota_data_initial.bin build/*.bin pi@workbench.local:/tmp/
ssh pi@workbench.local "python3 -m esptool --chip esp32s3 --port /dev/ttyACM1 \
  write_flash --flash_mode dio --flash_size 4MB \
  0x0 /tmp/bootloader.bin 0x8000 /tmp/partition-table.bin \
  0xf000 /tmp/ota_data_initial.bin 0x20000 /tmp/firmware.bin"
```

Then release GPIO:

```bash
curl -X POST http://workbench.local:8080/api/serial/release \
  -H 'Content-Type: application/json' -d '{"slot": "slot-1"}'
```

### Without GPIO

```
State flow: flapping → recovering → idle (if stable) or flapping (retry, up to 2x)
```

After 2 failed attempts, flash directly on the Pi with `esptool --before=usb_reset`.

### Manual recovery trigger

```bash
curl -X POST http://workbench.local:8080/api/serial/recover \
  -H 'Content-Type: application/json' -d '{"slot": "slot-1"}'
```

## Troubleshooting

### Local USB

| Issue | Solution |
|-------|----------|
| Failed to connect | Enter boot mode (BOOT+RESET sequence) |
| No serial port found | Check USB cable, `ls /dev/ttyUSB*` or `ls /dev/ttyACM*` |
| Permission denied | `sudo usermod -aG dialout $USER`, re-login |

### Workbench

| Problem | Fix |
|---------|-----|
| Slot shows `absent` | Check USB cable, re-seat device |
| `flapping` state | Recovery should start automatically; if stuck, `POST /api/serial/recover` |
| `recovering` state | USB unbound, recovery in progress — wait for `download_mode` or `idle` |
| `download_mode` state | Flash firmware on the Pi, then `POST /api/serial/release` |
| esptool can't connect | Use `POST /api/flash` — never call esptool over RFC2217 directly |
| Device crash-looping | Reflash via `POST /api/flash` with working firmware |
| Board occupies two slots | Onboard USB hub — identify JTAG vs UART via `udevadm info` |

### OTA

| Problem | Fix |
|---------|-----|
| Upload fails | Use `-F` flags (multipart), not `-d` |
| ESP32 can't download firmware | Device must reach workbench; check WiFi |
| OTA trigger times out | Check device's OTA endpoint URL; increase timeout |
