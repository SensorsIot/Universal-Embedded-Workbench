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

### Configure platformio.ini

```ini
upload_port = rfc2217://workbench.local:4001?ign_set_control
monitor_port = rfc2217://workbench.local:4001?ign_set_control
```

### Or via command line

```bash
pio run -t upload --upload-port 'rfc2217://workbench.local:4001?ign_set_control'
pio device monitor --port 'rfc2217://workbench.local:4001?ign_set_control'
```

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
