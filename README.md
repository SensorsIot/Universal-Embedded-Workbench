# Universal ESP32 Workbench

**Plug in any ESP32. Serial and debug are ready instantly. No configuration needed.**

A Raspberry Pi that turns into a complete remote test instrument for ESP32 devices. Plug boards into its USB hub and control everything -- serial, debug, WiFi, BLE, GPIO, firmware updates -- over the network through a single HTTP API.

Zero-config by design: on boot the portal walks the Pi's USB hub topology and pre-creates one slot per usable hub port (`SLOT1`, `SLOT2`, ...), each mapped to a physical USB connector. The number of slots is determined by the host — typically 3–4 on a Pi Zero 2 W with hub, 4 on a Pi 3B+, 4 on a Pi 4B, 4 on a Pi 5. Slots are always visible in the web UI even when empty. Plug in a device and it automatically maps to the correct slot by USB path, gets a serial port, chip identification, and OpenOCD for GDB debugging. Dual-USB boards (ESP32-S3 with sub-hub) are handled transparently -- both interfaces map to the same slot.

---

## Quick Start

### Installation

```bash
git clone https://github.com/SensorsIot/Universal-Embedded-Workbench.git
cd Universal-Embedded-Workbench/pi
sudo bash install.sh
```

That's it. The installer sets up all dependencies (pyserial, hostapd, dnsmasq, bleak, esptool, OpenOCD), copies scripts to `/usr/local/bin/`, creates data directories, and starts the portal as a systemd service.

### Plug In and Go

1. Plug an ESP32 into any USB port on the Pi's hub.
2. The workbench auto-detects it within seconds.
3. Query the API to see what's connected:

```bash
curl http://workbench.local:8080/api/devices | jq
```

The response includes all 3 slots with serial URLs, chip info, debug status, and USB devices:

```json
{
  "slots": [
    {
      "label": "SLOT1",
      "state": "idle",
      "running": true,
      "url": "rfc2217://workbench.local:4001",
      "detected_chip": "esp32s3",
      "debugging": true,
      "debug_chip": "esp32s3",
      "debug_gdb_port": 3333,
      "devnodes": ["/dev/ttyACM0", "/dev/ttyACM1"],
      "usb_devices": [
        {"product": "USB JTAG/serial debug unit", "vid_pid": "303a:1001"},
        {"product": "USB Single Serial", "vid_pid": "1a86:55d3"}
      ]
    },
    { "label": "SLOT2", "state": "absent", "running": false, "detected_chip": null },
    { "label": "SLOT3", "state": "absent", "running": false, "detected_chip": null }
  ]
}
```

4. Flash firmware via RFC2217 (binaries stay on your machine):

```bash
esptool --port rfc2217://workbench.local:4001 --chip esp32c3 \
  --before default-reset --after no-reset \
  write-flash 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 firmware.bin
```

5. Connect GDB to the auto-started OpenOCD:

```bash
riscv32-esp-elf-gdb build/project.elf \
  -ex "target extended-remote workbench.local:3333" \
  -ex "monitor reset halt"
```

Everything auto-restarts after a flash -- the workbench detects the USB re-enumeration and brings serial and debug back up automatically.

---

## Hardware Setup

### What You Need

| Component | Purpose |
|-----------|---------|
| **Raspberry Pi** (any model) | Runs the portal. Needs onboard WiFi + Bluetooth. Auto-detects model and USB topology. |
| **USB Ethernet adapter** (Pi Zero 2 W only) | Wired LAN on eth0 (wlan0 is reserved for WiFi testing). Pi 3/4/5 have built-in Ethernet. |
| **USB hub** (Pi Zero 2 W only) | Connect multiple ESP32 boards. Pi 3/4/5 already have 4 USB ports. |
| **Jumper wires** (optional) | Pi GPIO to DUT GPIO for automated boot mode / reset control |

**Auto-detection:** The portal walks `/sys/bus/usb/devices/` on startup, finds every downstream USB hub, and creates one slot per hub port. Ports occupied by non-serial devices (USB Ethernet, storage) are filtered out, so only ESP32-usable ports become slots. TCP ports are auto-assigned as `4001 + slot_index`, GDB ports as `3333 + slot_index`.

Some Pi boards advertise more hub ports than are physically wired to USB-A jacks. From sysfs alone these unwired "phantom" ports are indistinguishable from empty wired jacks, so the portal keeps a small per-model phantom table keyed on `/proc/device-tree/model` (`_PHANTOM_PORTS_BY_MODEL` in `pi/portal.py`). Add an entry there if you find a new phantom on a model not yet listed.

| Pi model | Expected slots | Notes |
|----------|---------------|-------|
| Pi Zero 2 W + external hub | 3–4 (external hub ports minus ethernet) | Tested |
| Pi 3 B+ | 4 | Phantom port `0:1.4` filtered via model table (tested on Rev 1.3) |
| Pi 4 B | 2 USB2 + 2 USB3 slots | Same kernel API, expected to work |
| Pi 5 | Up to 4 slots on XHCI | Same kernel API, expected to work |

No config file is needed for auto-detection. Custom overrides (labels, specific TCP/GDB ports, GPIO pins, debug probes) can be provided via `/etc/rfc2217/workbench.json`.

GPIO wiring is optional. Without it, the workbench still provides serial and debug for every plugged-in device. GPIO is only needed if you want scripts to reset the DUT, force download mode, or trigger captive portal boot from the Pi.

### Network Topology

```
 LAN (192.168.0.x)
       |
       | eth0 (wired)
       v
  Raspberry Pi ---- wlan0 (WiFi test AP: 192.168.4.x)
  workbench.local      hci0  (Bluetooth LE)
       |             UDP :5555 (log receiver)
       | USB hub (internal on Pi 3/4/5, external on Zero)
       |
  +----+----+----+----+
  |    |    |    |
 :4001 :4002 :4003 :4004  ← auto-assigned (4001 + slot index)
 SLOT1 SLOT2 SLOT3 SLOT4  ← one per detected hub port
```

eth0 carries all management traffic (HTTP API, RFC2217 serial). wlan0 is dedicated to WiFi testing. They never overlap.

### Network Ports

| Port | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| 8080 | TCP/HTTP | Clients -> Pi | Web portal, REST API, firmware downloads |
| 4001+ | TCP/RFC2217 | Clients -> Pi | Serial connections (auto-assigned per device) |
| 3334+ | TCP/GDB | Clients -> Pi | GDB connections (`3333 + slot_index`) |
| 4444+ | TCP/telnet | Clients -> Pi | OpenOCD telnet (`4443 + slot_index`) |
| 5555 | UDP | ESP32 -> Pi | Debug log receiver |
| 5888 | UDP | Clients <-> Pi | Discovery beacon |

---

## Services

### 1. Remote Serial (RFC2217)

Each physical USB hub port is mapped to a slot (`SLOT1`, `SLOT2`, ...) via USB path prefix. Slots are auto-detected from the Pi's USB topology on startup; the count matches the number of wired ports for that model (see the hardware table above). An optional `workbench.json` can override labels or pin specific TCP/GDB ports. The same port always gets the same slot label and TCP port. Dual-USB boards (ESP32-S3 with built-in hub) expose multiple interfaces on the same slot. One RFC2217 client at a time per device.

Works with esptool, PlatformIO, ESP-IDF, and any pyserial-based tool.

**What happens on plug/unplug:** udev detects the event, notifies the portal, and the RFC2217 proxy starts or stops automatically. No manual intervention needed.

**ESP32 reset behavior:**

| Chip | USB Interface | Device Node | Reset Method | Caveat |
|------|--------------|-------------|--------------|--------|
| ESP32, ESP32-S2 | External UART bridge (CP2102, CH340) | `/dev/ttyUSB*` | DTR/RTS toggle | Reliable, no issues |
| ESP32-C3, ESP32-S3 | Native USB-Serial/JTAG | `/dev/ttyACM*` | DTR/RTS toggle | Linux asserts DTR+RTS on port open, which puts the chip into download mode during early boot. The Pi adds a 2-second delay before opening the port to avoid this. |

### 2. Remote GDB Debugging

OpenOCD starts **automatically** when a device is plugged in. The workbench auto-detects the chip type and exposes the GDB port in `/api/devices`. Serial and JTAG coexist on the same USB connection.

| Approach | Chips | Extra Hardware | Serial During Debug |
|----------|-------|:-:|:-:|
| USB JTAG (auto) | C3, C6, H2, S3 (native USB) | None | Yes |
| Dual-USB | S3 (two USB ports) | None | Yes + app USB |
| ESP-Prog | All variants | ESP-Prog + cable | Yes |

**Verified chips (USB JTAG):**

| Chip | JTAG TAP ID | OpenOCD Config |
|------|------------|----------------|
| ESP32-C3 | `0x00005c25` | `board/esp32c3-builtin.cfg` |
| ESP32-C6 | `0x0000dc25` | `board/esp32c6-builtin.cfg` |
| ESP32-H2 | `0x00010c25` | `board/esp32h2-builtin.cfg` |
| ESP32-S3 | `0x120034e5` | `board/esp32s3-builtin.cfg` |

For classic ESP32 boards without USB JTAG, the workbench automatically uses an ESP-Prog probe if one is configured in `workbench.json`.

### 3. WiFi Test Instrument

The Pi's **wlan0** radio acts as a programmable WiFi access point or station, isolated from the wired LAN on eth0.

- **AP mode** -- start a SoftAP with any SSID/password. DUTs connect to `192.168.4.x`, Pi is at `192.168.4.1`. DHCP and DNS included.
- **STA mode** -- join a DUT's captive portal AP as a station to test provisioning flows.
- **HTTP relay** -- proxy HTTP requests through the Pi's radio to devices on its WiFi network.
- **Scan** -- list nearby WiFi networks to verify a DUT's AP is broadcasting.

AP and STA are mutually exclusive -- starting one stops the other.

### 4. GPIO Control

Drive Pi GPIO pins from test scripts to simulate button presses on the DUT. The most common use: hold a pin LOW during reset to force the DUT into a specific boot mode (captive portal, factory reset, etc.).

**Allowed pins (BCM numbering):** 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27

**Important:** Always release pins when done by setting them to `"z"` (high-impedance input). A pin left driven LOW will prevent the DUT from booting normally.

**Standard wiring (optional -- only if you want GPIO control):**

| Pi GPIO (BCM) | Pin # | DUT Pin | Function |
|---------------|-------|---------|----------|
| 17 | 11 | EN/RST | Hardware reset (active LOW) |
| 18 | 12 | GPIO0 (ESP32) / GPIO9 (ESP32-C3) | Boot mode select (active LOW = download mode) |
| 27 | 13 | -- | Spare 1 |
| 22 | 15 | -- | Spare 2 |

### 5. UDP Log Receiver

Listens on **UDP port 5555** for debug log output from ESP32 devices. Essential when the USB port is occupied (e.g., ESP32-S3 running as USB HID keyboard) and you can't use a serial monitor.

Logs are buffered (last 2000 lines) and available via the HTTP API, filterable by source IP and timestamp.

### 6. OTA Firmware Repository

Serves firmware binaries over HTTP so ESP32 devices can perform OTA updates from the local network. Upload a `.bin` file, then point the ESP32's OTA URL to:

```
http://workbench.local:8080/firmware/<project-name>/<filename>.bin
```

### 7. BLE Proxy

Uses the Pi's **onboard Bluetooth radio** to scan for, connect to, and send raw bytes to BLE peripherals. The Pi acts as a BLE-to-HTTP bridge. One BLE connection at a time.

**Prerequisite:** Bluetooth must be powered on:
```bash
sudo rfkill unblock bluetooth
sudo hciconfig hci0 up
sudo bluetoothctl power on
```

### 8. Signal Generator (Si5351 + PE4302, with GPCLK fallback)

Unified RF source with programmable frequency, attenuation, and optional Morse keying. Auto-selects between two backends:

- **Si5351** (I²C clock generator on GPIO 2/3) — 8 kHz to 160 MHz, three independent channels (CLK0–CLK2), precise fractional synthesis. Preferred when detected on I²C.
- **GPCLK** (BCM2835 hardware clock on GPIO 5/6) — 122 kHz to 250 MHz in integer-divider steps from 500 MHz PLLD. Always available, no extra hardware.

The Si5351 backend programs active CLK outputs at the lowest drive-current
setting, 2 mA. Use the PE4302 path for precise RF level control.

Optional **PE4302** digital step attenuator (0–31.5 dB in 0.5 dB steps) can sit in the RF path, controlled via 3-wire serial on GPIO 6/12/13. Works with either backend. If not installed, attenuation calls return a clean error.

Both backends share a Morse keyer, so you can key any carrier with a CW message — useful for direction-finder beacons, sensitivity tests, or field-day practice. Without a `morse` argument, the carrier runs continuous.

**Wiring:**
- Si5351: SDA=GPIO2 (pin 3), SCL=GPIO3 (pin 5), VCC=3.3V (pin 1), GND (pin 9)
- PE4302: LE=GPIO6 (pin 31), CLK=GPIO12 (pin 32), DATA=GPIO13 (pin 33), VCC=3.3V/5V
- GPCLK: output on GPIO5 (pin 29) or GPIO6 (pin 31)

### 9. Test Automation

- **Test progress tracking** -- push live test session updates to the web portal.
- **Human interaction requests** -- block a test script until an operator confirms a physical action.

### 10. Web Portal

A browser-based dashboard at **http://pi-ip:8080** showing all 3 serial slots, WiFi state, activity log, test progress, and human interaction modal. Each slot card shows:
- Connection status (RUNNING / IDLE / ABSENT / RECOVERING / DOWNLOAD MODE)
- Detected chip type (e.g., ESP32-C6) when identified via JTAG
- Debug status (active GDB port or idle)
- USB devices on this physical port (including non-serial devices like HID keyboards)
- Device node, PID

---

## Usage

### Flash Firmware

```bash
# Flash via RFC2217 (binaries stay on host, no SCP needed)
esptool --port rfc2217://workbench.local:4001 --chip esp32c3 \
  --before default-reset --after no-reset \
  write-flash 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 firmware.bin

# Reboot device into new firmware
curl -X POST http://workbench.local:8080/api/serial/reset \
  -H "Content-Type: application/json" -d '{"slot":"SLOT1"}'
```

### Serial Monitor

```bash
# Python
import serial
ser = serial.serial_for_url("rfc2217://workbench.local:4001", baudrate=115200)
```

```ini
# PlatformIO (platformio.ini)
[env:esp32]
monitor_port = rfc2217://workbench.local:4001
```

### pytest Driver

```bash
pip install -e Universal-Embedded-Workbench/pytest
```

```python
from workbench_driver import WorkbenchDriver

wt = WorkbenchDriver("http://workbench.local:8080")

# Serial
wt.serial_reset("SLOT1")
result = wt.serial_monitor("SLOT1", pattern="WiFi connected", timeout=30)

# WiFi
wt.ap_start("TestAP", "password123")
station = wt.wait_for_station(timeout=30)
resp = wt.http_get(f"http://{station['ip']}/api/status")
wt.ap_stop()

# GPIO -- trigger captive portal mode (requires wiring)
try:
    wt.gpio_set(18, 0)                   # Hold DUT boot pin LOW
    wt.gpio_set(17, 0)                   # Pull EN/RST LOW (reset)
    time.sleep(0.1)
    wt.gpio_set(17, "z")                 # Release reset -- DUT boots into portal
finally:
    wt.gpio_set(18, "z")                 # Always release boot pin

# GDB debug -- auto-started on plug-in, just check what's available
status = wt.debug_status()

# Optional: manually override debug (not normally needed)
info = wt.debug_start()    # auto-detect slot + chip
wt.debug_stop()

# UDP logs
logs = wt.udplog(source="192.168.0.121")
wt.udplog_clear()

# OTA firmware
wt.firmware_upload("my-project", "build/firmware.bin")

# BLE
devices = wt.ble_scan(name_filter="iOS-Keyboard")
wt.ble_connect(devices[0]["address"])
wt.ble_write("6e400002-b5a3-f393-e0a9-e50e24dcca9e", b"\x02Hello")
wt.ble_disconnect()

# Signal generator — continuous carrier
wt.siggen_start(freq_hz=3_500_000, backend="si5351")
wt.siggen_atten(db=12.0)                 # attenuate via PE4302
wt.siggen_freq(freq_hz=7_100_000)        # retune without stopping
wt.siggen_stop()

# Signal generator — Morse beacon (auto-selects Si5351 if available)
wt.siggen_start(freq_hz=3_571_000,
                morse={"message": "VVV DE TEST", "wpm": 15, "repeat": True})
wt.siggen_stop()

# Test progress
wt.test_start(spec="Firmware v2.1", phase="Integration", total=10)
wt.test_step("TC-001", "WiFi Connect", "Joining AP...")
wt.test_result("TC-001", "WiFi Connect", "PASS")
wt.test_end()
```

### OTA Firmware Update Workflow

```bash
# 1. Upload firmware to the workbench
curl -X POST http://workbench.local:8080/api/firmware/upload \
  -F "project=ios-keyboard" -F "file=@build/ios-keyboard.bin"

# 2. Trigger OTA on the ESP32 via HTTP relay
curl -X POST http://workbench.local:8080/api/wifi/http \
  -H "Content-Type: application/json" \
  -d '{"method":"POST","url":"http://192.168.4.15/ota"}'

# 3. Monitor progress via UDP logs
curl http://workbench.local:8080/api/udplog?source=192.168.4.15
```

### curl Examples

```bash
# Check connected devices
curl http://workbench.local:8080/api/devices | jq

# Serial reset
curl -X POST http://workbench.local:8080/api/serial/reset \
  -H "Content-Type: application/json" -d '{"slot":"SLOT1"}'

# Start WiFi AP
curl -X POST http://workbench.local:8080/api/wifi/ap_start \
  -H "Content-Type: application/json" -d '{"ssid":"TestAP","password":"secret"}'

# GPIO: hold boot pin LOW, pulse reset, release
curl -X POST http://workbench.local:8080/api/gpio/set \
  -H "Content-Type: application/json" -d '{"pin":18,"value":0}'
curl -X POST http://workbench.local:8080/api/gpio/set \
  -H "Content-Type: application/json" -d '{"pin":17,"value":0}'
sleep 0.1
curl -X POST http://workbench.local:8080/api/gpio/set \
  -H "Content-Type: application/json" -d '{"pin":17,"value":"z"}'
curl -X POST http://workbench.local:8080/api/gpio/set \
  -H "Content-Type: application/json" -d '{"pin":18,"value":"z"}'

# Get UDP logs
curl http://workbench.local:8080/api/udplog?source=192.168.0.121&limit=50

# Upload firmware
curl -X POST http://workbench.local:8080/api/firmware/upload \
  -F "project=ios-keyboard" -F "file=@build/ios-keyboard.bin"

# BLE: scan, connect, write, disconnect
curl -X POST http://workbench.local:8080/api/ble/scan \
  -H "Content-Type: application/json" -d '{"timeout":5,"name_filter":"iOS-Keyboard"}'
curl -X POST http://workbench.local:8080/api/ble/connect \
  -H "Content-Type: application/json" -d '{"address":"1C:DB:D4:84:58:CE"}'
curl -X POST http://workbench.local:8080/api/ble/write \
  -H "Content-Type: application/json" \
  -d '{"characteristic":"6e400002-b5a3-f393-e0a9-e50e24dcca9e","data":"0248656c6c6f"}'
curl -X POST http://workbench.local:8080/api/ble/disconnect

# Signal generator — continuous carrier at 3.5 MHz on Si5351
curl -X POST http://workbench.local:8080/api/siggen/start \
  -H "Content-Type: application/json" \
  -d '{"freq_hz": 3500000, "backend": "si5351"}'

# Signal generator — Morse-keyed beacon (auto-selects Si5351 if present, else GPCLK)
curl -X POST http://workbench.local:8080/api/siggen/start \
  -H "Content-Type: application/json" \
  -d '{"freq_hz": 3571000, "morse": {"message": "VVV DE TEST", "wpm": 15, "repeat": true}}'

# Set attenuation (requires PE4302 in RF path)
curl -X POST http://workbench.local:8080/api/siggen/atten \
  -H "Content-Type: application/json" -d '{"db": 12.5}'

# Retune without restarting
curl -X POST http://workbench.local:8080/api/siggen/freq \
  -H "Content-Type: application/json" -d '{"freq_hz": 7100000}'

# Stop
curl -X POST http://workbench.local:8080/api/siggen/stop
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Device not detected | Bad USB cable, unpowered hub, or device not enumerating | Try a different cable (data-capable, not charge-only). Check `lsusb` on the Pi. |
| Connection refused on serial port | Proxy not running | Check portal at :8080; verify device shows in `/api/devices` |
| Timeout during flash | Proxy not released | Use `POST /api/flash` — it manages proxy lifecycle |
| Port busy | Another client connected | Close the other connection first (RFC2217 = 1 client) |
| Stale slot data | Device was unplugged during an active debug or serial session | The workbench cleans up automatically on unplug. If stale, restart the portal: `sudo systemctl restart rfc2217-portal` |
| USB flapping (rapid connect/disconnect) | Erased/corrupt flash, boot loop | Portal auto-recovers: unbinds USB, enters download mode via GPIO. Check slot state in `/api/devices`. Manual trigger: `POST /api/serial/recover` |
| Slot stuck in `recovering` | Recovery thread running | Wait for `download_mode` (GPIO) or `idle` (no-GPIO). Takes 10-80s depending on retry count |
| Slot in `download_mode` | Device waiting in bootloader | Flash firmware, then `POST /api/serial/release` to reboot |
| ESP32-C3 stuck in download mode | DTR asserted on port open | Use `POST /api/serial/reset` to reboot the device |
| GDB won't connect | OpenOCD may not have started (classic ESP32 without USB JTAG) | Check `/api/devices` for `debugging: true`. Classic ESP32 needs an ESP-Prog configured in `workbench.json` |
| DUT not connecting to AP | Wrong WiFi credentials in DUT | Verify AP is running: `curl .../api/wifi/ap_status` |
| BLE scan finds nothing | Bluetooth powered off | `sudo rfkill unblock bluetooth && sudo hciconfig hci0 up && sudo bluetoothctl power on` |
| No UDP logs appearing | ESP32 not sending to correct IP/port | Verify firmware log host is `workbench.local:5555` |
| GPIO pin has no effect | Wrong BCM pin number or not wired | Verify wiring; only BCM pins in the allowlist work |

---

## API Reference

All endpoints are served from `http://<pi-ip>:8080`. No authentication. All requests and responses use JSON (except the firmware upload/download which use multipart form-data and raw binary). Every response includes an `"ok": true|false` field; errors add `"error": "..."`.

Sub-chapters:
[1. Device Discovery](#1-device-discovery) · [2. Serial Management](#2-serial-management) · [3. GDB Debug](#3-gdb-debug) · [4. WiFi Instrument](#4-wifi-instrument) · [5. BLE Proxy](#5-ble-proxy) · [6. GPIO Control](#6-gpio-control) · [7. UDP Log](#7-udp-log) · [8. Firmware Repository](#8-firmware-repository) · [9. Signal Generator](#9-signal-generator) · [10. Test Progress](#10-test-progress) · [11. Human Interaction](#11-human-interaction) · [12. Activity Log](#12-activity-log)

---

### 1. Device Discovery

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | List all slots with status, RFC2217 URL, detected chip, debug port, USB device info |
| GET | `/api/info` | Pi IP, hostname, total slot count, portal uptime |

**GET /api/devices** response:

```json
{
  "slots": [
    {
      "label": "SLOT1",
      "state": "idle",
      "present": true,
      "running": true,
      "url": "rfc2217://workbench.local:4001",
      "tcp_port": 4001,
      "devnode": "/dev/ttyACM0",
      "detected_chip": "esp32s3",
      "jtag_slot": "SLOT1",
      "debugging": true,
      "debug_gdb_port": 3333,
      "is_probe": false,
      "usb_devices": [
        {"product": "USB JTAG/serial debug unit", "vid_pid": "303a:1001"}
      ]
    }
  ]
}
```

`state` is one of `absent`, `idle`, `monitoring`, `resetting`, `debugging`, `recovering`, `download_mode`.

---

### 2. Serial Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/serial/reset` | Reset device via DTR/RTS `{"slot"}` → `{"ok", "output": ["boot line", ...]}` |
| POST | `/api/serial/monitor` | Wait for pattern on serial output `{"slot", "pattern?", "timeout?"}` → `{"ok", "matched", "line", "output"}` |
| POST | `/api/serial/recover` | Manual flap recovery trigger `{"slot"}` |
| POST | `/api/serial/release` | Release BOOT GPIO and reboot device after download-mode flash `{"slot"}` |
| POST | `/api/enter-portal` | Join DUT's captive portal AP, submit WiFi creds, then restart local AP `{"portal_ssid?", "ssid", "password?"}` |
| POST | `/api/start` | Manually start proxy for a slot |
| POST | `/api/stop` | Manually stop proxy for a slot |
| POST | `/api/hotplug` | udev hotplug event (internal — called by udev rule) |

**Flashing workflow:**

1. Connect esptool over RFC2217 using the URL from `/api/devices`
2. Use `--before=default-reset --after=no-reset` to avoid USB re-enumeration
3. After flash: `POST /api/serial/reset` to reboot into the new firmware
4. Verify with `POST /api/serial/monitor` matching a boot string

---

### 3. GDB Debug

Auto-started on device plug-in for chips with USB JTAG or configured ESP-Prog probes. These endpoints manually override auto-detection.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/debug/start` | Start OpenOCD `{"slot?", "chip?", "probe?"}` → `{"ok", "slot", "chip", "gdb_port", "telnet_port"}` |
| POST | `/api/debug/stop` | Stop OpenOCD `{"slot?"}` |
| GET | `/api/debug/status` | Debug state per slot |
| GET | `/api/debug/group` | Slot groups and roles (dual-USB ESP32-S3) |
| GET | `/api/debug/probes` | Available ESP-Prog probes |

GDB connects with `target extended-remote workbench.local:<gdb_port>`.

---

### 4. WiFi Instrument

Controls the Pi's wlan0 radio. Access Point and Station modes are mutually exclusive.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/wifi/mode` | Current mode (`wifi-testing` or `serial-interface`) |
| POST | `/api/wifi/mode` | Switch mode `{"mode"}` |
| POST | `/api/wifi/ap_start` | Start SoftAP `{"ssid", "password?", "channel?"}` → `{"ok", "ip"}` |
| POST | `/api/wifi/ap_stop` | Stop SoftAP |
| GET | `/api/wifi/ap_status` | `{"active", "ssid", "channel", "stations": [{"mac", "ip"}, ...]}` |
| POST | `/api/wifi/sta_join` | Join a WiFi network `{"ssid", "password?"}` → `{"ok", "ip", "gateway"}` |
| POST | `/api/wifi/sta_leave` | Disconnect from WiFi network |
| GET | `/api/wifi/scan` | Scan nearby WiFi networks |
| POST | `/api/wifi/http` | HTTP relay through the Pi's wlan0 radio `{"method", "url", "headers?", "body?"}` |
| GET | `/api/wifi/events` | Long-poll for station events `?timeout=` |

---

### 5. BLE Proxy

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ble/scan` | Scan for peripherals `{"timeout?", "name_filter?"}` → list of `{"address", "name", "rssi"}` |
| POST | `/api/ble/connect` | Connect by MAC address `{"address"}` |
| POST | `/api/ble/disconnect` | Disconnect current connection |
| GET | `/api/ble/status` | `{"state": "idle"|"scanning"|"connected", "address?"}` |
| POST | `/api/ble/write` | Write to a GATT characteristic `{"characteristic", "data", "response?"}` (data as hex string) |

One BLE connection at a time. Requires `rfkill unblock bluetooth`.

---

### 6. GPIO Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/gpio/set` | Drive pin `{"pin": 17, "value": 0 | 1 | "z"}` |
| GET | `/api/gpio/status` | State of all actively driven pins |

Allowlist: `{16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27}`. Others are reserved (I²C, GPCLK, PE4302). Always release with `"value": "z"` when done.

---

### 7. UDP Log

Listens on UDP port 5555 for log messages from ESP32 devices.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/udplog` | `?since=&source=&limit=` — fetch buffered log lines |
| DELETE | `/api/udplog` | Clear the log buffer |

---

### 8. Firmware Repository

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/firmware/<project>/<file>` | Download binary (used by ESP32 OTA clients) |
| GET | `/api/firmware/list` | List all available firmware files |
| POST | `/api/firmware/upload` | Upload binary (multipart form-data: `project` + `file`) |
| DELETE | `/api/firmware/delete` | Delete a file `{"project", "filename"}` |

Files served under `http://<pi-ip>:8080/firmware/...` are suitable as ESP-IDF `esp_https_ota` download URLs.

---

### 9. Signal Generator

Auto-selecting RF source (Si5351 via I²C or GPCLK on GPIO 5/6) with optional PE4302 attenuator. Morse-keyed or continuous.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/siggen/start` | Start carrier `{"freq_hz", "backend?", "channel?", "pin?", "atten_db?", "morse?"}` |
| POST | `/api/siggen/stop` | Stop carrier |
| POST | `/api/siggen/freq` | Retune active carrier `{"freq_hz", "channel?"}` |
| POST | `/api/siggen/atten` | Set PE4302 attenuation in dB `{"db": 0..31.5}` |
| GET | `/api/siggen/status` | Active state + hardware detection (`si5351`, `gpclk`, `pe4302`) |
| GET | `/api/siggen/frequencies` | Achievable frequencies in range `?low=&high=&backend=` |

**Body fields for `/api/siggen/start`:**

| Field | Type | Description |
|-------|------|-------------|
| `freq_hz` | number | Carrier frequency (8 kHz–160 MHz for Si5351, 122 kHz–250 MHz for GPCLK) |
| `backend` | `"auto"` (default), `"si5351"`, `"gpclk"` | `auto` prefers Si5351 when detected |
| `channel` | 0, 1, 2 | Si5351 output (CLK0–CLK2) |
| `pin` | 5, 6 | GPCLK pin |
| `atten_db` | 0–31.5 | Initial PE4302 attenuation |
| `morse` | `{"message", "wpm?", "repeat?"}` | Key the carrier with Morse instead of continuous tone |

---

### 10. Test Progress

Lets test scripts push live session state to the web portal for operator visibility.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/test/update` | Push start/step/result/end (see body schemas below) |
| GET | `/api/test/progress` | Current session state for UI polling |

**`POST /api/test/update` body variants:**

- Start: `{"spec": "<name>", "phase": "<label>", "total": <n>}`
- Step: `{"current": {"id", "name", "step", "manual?"}}`
- Result: `{"result": {"id", "name", "result": "PASS"|"FAIL"|"SKIP", "details?"}}`
- End: `{"end": true}`

---

### 11. Human Interaction

Blocks a test script until the operator confirms a physical action on the Pi.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/human-interaction` | Show modal on the web UI and block until confirmed `{"message", "timeout?"}` |
| GET | `/api/human/status` | Is an interaction pending? |
| POST | `/api/human/done` | Confirm the pending interaction (operator action) |
| POST | `/api/human/cancel` | Cancel the pending interaction |

---

### 12. Activity Log

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/log` | Recent activity entries `?since=<iso-timestamp>` |

---

## Project Structure

```
pi/
  portal.py                  Main HTTP server, proxy supervisor, all API endpoints
  wifi_controller.py         WiFi AP/STA/scan/relay backend
  ble_controller.py          BLE scan/connect/write backend (bleak)
  signal_generator.py        Unified RF source: Si5351 (I2C) + optional PE4302, GPCLK fallback
  si5351.py                  Si5351A I2C clock generator driver
  pe4302.py                  PE4302 3-wire serial step attenuator driver
  gpclk.py                   BCM2835/7 GPCLK hardware clock (GPIO 5/6)
  morse.py                   Backend-agnostic Morse keyer
  bcm_gpio.py                Shared /dev/mem GPIO primitives
  debug_controller.py        GDB debug manager (OpenOCD lifecycle, probe allocation)
  plain_rfc2217_server.py    RFC2217 serial proxy with DTR/RTS passthrough
  install.sh                 One-command installer
  config/workbench.json      Slot/GPIO/debug probe config
  config/signalgen.json      Signal generator config (I2C bus, PE4302 pins)
  scripts/                   udev and dnsmasq callback scripts
  udev/                      Hotplug rules
  systemd/                   Service unit file

pytest/
  workbench_driver.py  Python test driver (WorkbenchDriver class)
  conftest.py                Fixtures and CLI options
  workbench_test.py          End-to-end workbench tests

docs/
  Embedded-Workbench-FSD.md  Full functional specification
```

---

## Configuration Reference: workbench.json (optional)

Slots are **auto-detected** on startup — no config file is required. Only create `/etc/rfc2217/workbench.json` if you want to:
- Rename slots (e.g., `"OLED Test Jig"` instead of `"SLOT1"`)
- Force specific TCP/GDB ports
- Wire GPIO boot/reset pins for download-mode recovery
- Register an ESP-Prog debug probe

Use `rfc2217-learn-slots` to print a ready-to-paste config based on currently plugged devices:

```bash
ssh pi@workbench.local sudo rfc2217-learn-slots
```

Example:

```json
{
  "gpio_boot": 18,
  "gpio_en": 17,
  "slots": [
    {"label": "SLOT1", "usb_prefix": "0:1.1", "tcp_port": 4001, "gdb_port": 3333, "openocd_telnet_port": 4444},
    {"label": "SLOT2", "usb_prefix": "0:1.3", "tcp_port": 4002, "gdb_port": 3334, "openocd_telnet_port": 4445},
    {"label": "SLOT3", "usb_prefix": "0:1.4", "tcp_port": 4003, "gdb_port": 3335, "openocd_telnet_port": 4446}
  ],
  "debug_probes": [
    {"label": "PROBE1", "type": "esp-prog", "interface_config": "interface/ftdi/esp_ftdi.cfg", "bus_port": "1-1.4:1.0"}
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `gpio_boot` | int | Pi BCM GPIO wired to DUT BOOT/GPIO0/GPIO9. Omit if not wired. |
| `gpio_en` | int | Pi BCM GPIO wired to DUT EN/RST. Omit if not wired. |
| `slots[].label` | string | Slot name shown in UI |
| `slots[].usb_prefix` | string | USB path prefix (e.g. `"0:1.1"` matches hub port 1). Auto-detected if omitted. |
| `slots[].tcp_port` | int | RFC2217 TCP port. Defaults to `4000 + slot_index`. |
| `slots[].gdb_port` | int | OpenOCD GDB port. Defaults to `3332 + slot_index`. |
| `slots[].openocd_telnet_port` | int | OpenOCD telnet port. Defaults to `4443 + slot_index`. |
| `debug_probes[]` | array | ESP-Prog/FT2232H probe definitions. Omit if using USB JTAG only. |

**Separate config for the signal generator** lives at `/etc/rfc2217/signalgen.json` (I²C bus, PE4302 pins, Si5351 address). Defaults match the wiring documented in Service 8 — edit only if you wired things differently.

---

## License

MIT
