---
name: esp-pio-handling
description: >
  Complete PlatformIO lifecycle: build, upload, and monitor ESP32 firmware.
  Automatically detects whether a workbench is available or the device is
  connected locally via USB. Covers platformio.ini configuration, RFC2217
  remote upload, environment selection, and serial monitor.
  Triggers on "pio", "platformio", "pio run", "pio upload", "platformio.ini".
---

# PlatformIO Handling

Complete lifecycle for PlatformIO ESP32 projects — build, upload, and monitor.
Automatically adapts to local USB or remote workbench.

## Step 1: Detect Environment

Determine whether a workbench is available or the device is local.

```bash
curl -s http://workbench.local:8080/api/info
```

- **Response received** → workbench available, use RFC2217 remote upload
- **Connection refused / timeout** → try the discovery script:
  ```bash
  sudo python3 .claude/skills/esp-pio-handling/discover-workbench.py --hosts
  ```
- **Still no response** → no workbench, use local USB upload

## Step 2: Build

```bash
pio run                    # Build default environment
pio run -e esp32dev        # Build specific environment
pio run -t clean           # Clean build
```

If there are multiple environments in `platformio.ini`, ask which one to build
or build all.

After build:
- Parse any compilation errors, map to source files, suggest fixes
- On success, show firmware size (RAM/Flash usage)
- Check for missing libraries in `lib_deps`

## Step 3a: Upload — Local USB

When the device is connected directly via USB.

```bash
pio device list                         # Find connected devices
pio run -t upload                       # Upload to default environment
pio run -e esp32dev -t upload           # Upload to specific environment
pio device monitor                      # Open serial monitor
pio run -t upload && pio device monitor # Upload and monitor
```

## Step 3b: Upload — Workbench (RFC2217)

When a workbench is available. Check the portal for slot-to-port assignments:

```bash
curl -s http://workbench.local:8080/api/devices | jq '.slots[] | {label, url, state}'
```

### Preferred: `POST /api/flash` (Pi-side esptool)

The portal stops the proxy, runs esptool directly on the Pi against the
local devnode, then restarts the proxy. Use this whenever your client is
not on the same LAN as the workbench — RFC2217's `SET_CONTROL` roundtrip
is too slow to keep esptool's auto-reset window open from a high-latency
path.

PlatformIO emits a single `firmware.bin` plus the bootloader and
partition table in `.pio/build/<env>/`. Upload them with the explicit
`bin@<offset>` form:

```bash
cd .pio/build/<env>
curl -s -X POST http://workbench.local:8080/api/flash \
  -F slot=SLOT1 -F chip=esp32 -F baud=921600 \
  -F 'bin@0x1000=@bootloader.bin' \
  -F 'bin@0x8000=@partitions.bin' \
  -F 'bin@0x10000=@firmware.bin' \
  | jq .
```

Bootloader offsets: classic ESP32 → `0x1000`, all newer chips
(C3/S3/C6/H2) → `0x0000`. Optional fields: `flash_mode` (default `dio`),
`flash_freq` (`40m`), `flash_size` (`keep`), `erase=1` to erase whole
flash before writing. Response: `{"ok": ..., "output": "<esptool
stdout+stderr>", "returncode": N}`.

### Fallback: direct RFC2217 upload (LAN clients only)

```ini
upload_port = rfc2217://workbench.local:4001
monitor_port = rfc2217://workbench.local:4001
```

```bash
pio run -t upload --upload-port 'rfc2217://workbench.local:4001?ign_set_control'
pio device monitor --port 'rfc2217://workbench.local:4001?ign_set_control'
```

## Step 3c: Upload — Classic ESP32 behind a USB-serial bridge (local flash)

If `pio run -t upload` over RFC2217 fails with **`Wrong boot mode detected (0x13)`**,
the board is a classic ESP32 behind a USB-serial bridge (CP2102 / CH340 / CH9102):
its external DTR/RTS auto-reset can't be driven reliably through the RFC2217 proxy.
(Native-USB C3/S3/C6/H2 chips strap internally and flash fine over RFC2217 — this does
not apply to them.)

Flash locally on the Pi via `POST /api/flash`, which runs esptool on the workbench
against the local devnode (stops the proxy, flashes, restarts it). Use the helper:

```bash
pio run                                   # build first
python3 <skill>/workbench-flash.py \
  --host workbench.local:8080 --slot SLOT3 --chip esp32
```

It gathers `bootloader.bin`, `partitions.bin`, `boot_app0.bin`, and `firmware.bin`
from `.pio/build/<env>/` and POSTs them as multipart (part name = hex offset). Or call
the endpoint directly:

```bash
curl -X POST http://workbench.local:8080/api/flash \
  -F slot=SLOT3 -F chip=esp32 -F baud=460800 \
  -F '0x1000=@.pio/build/<env>/bootloader.bin' \
  -F '0x8000=@.pio/build/<env>/partitions.bin' \
  -F '0xe000=@<framework>/tools/partitions/boot_app0.bin' \
  -F '0x10000=@.pio/build/<env>/firmware.bin'
```

Response: `{"ok": bool, "returncode": int, "log": "..."}`. No `/api/serial/reset` needed
— esptool hard-resets into the new firmware. Refused if a debug session is active.

## Step 4: Monitor

```bash
# Local
pio device monitor

# Workbench — via RFC2217
pio device monitor --port 'rfc2217://workbench.local:4001?ign_set_control'

# Workbench — via UDP logs (non-blocking)
curl "http://workbench.local:8080/api/udplog?limit=50"
```

## Boot Mode

If upload fails, put ESP32 in bootloader mode:
1. Hold **BOOT** button
2. Press **RESET** button
3. Release **RESET**, then **BOOT**

## Troubleshooting

### Local USB

| Issue | Solution |
|-------|----------|
| No device found | Check USB cable, `pio device list` |
| Permission denied | `sudo usermod -a -G dialout $USER`, re-login |
| Upload timeout | Enter boot mode (BOOT+RESET sequence) |

### Workbench (RFC2217)

| Issue | Solution |
|-------|----------|
| Connection refused | Check portal at `http://workbench.local:8080`; verify device state is `idle` |
| Timeout during flash | Use `--no-stub` flag; check network |
| Port busy | Close other terminal/tool using the same RFC2217 port |
| `Wrong boot mode detected (0x13)` | Classic ESP32 behind a USB-serial bridge — RFC2217 auto-reset can't enter the bootloader. Flash locally via `POST /api/flash` (see Step 3c / `workbench-flash.py`). |
