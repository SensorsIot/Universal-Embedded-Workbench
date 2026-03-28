# Universal ESP32 Workbench

**Plug in any ESP32. Serial and debug are ready instantly. No configuration needed.**

A Raspberry Pi that turns into a complete remote test instrument for ESP32 devices. Plug boards into its USB hub and control everything -- serial, debug, WiFi, BLE, GPIO, firmware updates -- over the network through a single HTTP API.

Zero-config by design: the portal pre-creates 3 fixed slots (SLOT1--SLOT3) at boot, each mapped to a physical USB hub port. Slots are always visible in the web UI even when empty. Plug in a device and it automatically maps to the correct slot by USB path, gets a serial port, chip identification, and OpenOCD for GDB debugging. Dual-USB boards (ESP32-S3 with sub-hub) are handled transparently -- both interfaces map to the same slot.

---

## Quick Start

### Installation

```bash
git clone https://github.com/SensorsIot/Universal-ESP32-Workbench.git
cd Universal-ESP32-Workbench/pi
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
  -ex "target extended-remote workbench.local:3335" \
  -ex "monitor reset halt"
```

Everything auto-restarts after a flash -- the workbench detects the USB re-enumeration and brings serial and debug back up automatically.

---

## Hardware Setup

### What You Need

| Component | Purpose |
|-----------|---------|
| **Raspberry Pi** (Zero W, 3, 4, or 5) | Runs the portal. Needs onboard WiFi + Bluetooth. |
| **USB Ethernet adapter** | Wired LAN on eth0 (wlan0 is reserved for WiFi testing) |
| **USB hub** | Connect multiple ESP32 boards |
| **Jumper wires** (optional) | Pi GPIO to DUT GPIO for automated boot mode / reset control |

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
       | USB hub
       |
  +----+----+----+
  |    |    |    |
 :4001 :4002 :4003
 SLOT1 SLOT2 SLOT3
```

eth0 carries all management traffic (HTTP API, RFC2217 serial). wlan0 is dedicated to WiFi testing. They never overlap.

### Network Ports

| Port | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| 8080 | TCP/HTTP | Clients -> Pi | Web portal, REST API, firmware downloads |
| 4001+ | TCP/RFC2217 | Clients -> Pi | Serial connections (auto-assigned per device) |
| 3335+ | TCP/GDB | Clients -> Pi | GDB connections (auto-assigned per device) |
| 5555 | UDP | ESP32 -> Pi | Debug log receiver |
| 5888 | UDP | Clients <-> Pi | Discovery beacon |

---

## Services

### 1. Remote Serial (RFC2217)

Each physical USB hub port is mapped to a fixed slot (SLOT1--SLOT3) via USB path prefix in `workbench.json`. The same port always gets the same slot label and TCP port. Dual-USB boards (ESP32-S3 with built-in hub) expose multiple interfaces on the same slot. One RFC2217 client at a time per device.

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

### 8. CW Beacon (Morse Transmitter)

Generates a **Morse-keyed RF carrier** on GPIO 5 or GPIO 6 using the BCM2835 hardware clock generator (GPCLK). Designed for direction finder testing on the 80m amateur band (3.5-4.0 MHz). No additional hardware -- just a wire antenna on the GPIO pin.

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
pip install -e Universal-ESP32-Workbench/pytest
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

# CW beacon
wt.cw_start(freq=3_571_000, message="VVV DE TEST", wpm=12)
wt.cw_stop()

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

# CW beacon
curl -X POST http://workbench.local:8080/api/cw/start \
  -H "Content-Type: application/json" \
  -d '{"freq": 3571000, "message": "VVV DE TEST", "wpm": 12}'
curl http://workbench.local:8080/api/cw/frequencies?low=3500000&high=4000000
curl -X POST http://workbench.local:8080/api/cw/stop
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

### Serial

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | List all devices with status, serial URLs, and debug ports |
| GET | `/api/info` | Pi IP, hostname, device counts |
| POST | `/api/hotplug` | Receive udev hotplug event (internal) |
| POST | `/api/start` | Manually start proxy for a slot |
| POST | `/api/stop` | Manually stop proxy for a slot |
| POST | `/api/serial/reset` | Reset device via DTR/RTS |
| POST | `/api/serial/monitor` | Read serial output with pattern match |
| POST | `/api/serial/recover` | Manual flap recovery trigger `{"slot"}` |
| POST | `/api/serial/release` | Release GPIO after flashing, reboot into firmware `{"slot"}` |
| POST | `/api/enter-portal` | Connect to DUT's captive portal SoftAP, submit WiFi creds, start local AP `{"portal_ssid?", "ssid", "password?"}` |

### WiFi

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/wifi/ap_start` | Start SoftAP `{"ssid", "password?", "channel?"}` |
| POST | `/api/wifi/ap_stop` | Stop SoftAP |
| GET | `/api/wifi/ap_status` | AP status, SSID, connected stations |
| POST | `/api/wifi/sta_join` | Join a WiFi network as station `{"ssid", "password?"}` |
| POST | `/api/wifi/sta_leave` | Disconnect from WiFi network |
| GET | `/api/wifi/scan` | Scan for nearby WiFi networks |
| POST | `/api/wifi/http` | HTTP relay through Pi's radio `{"method", "url", "headers?", "body?"}` |
| GET | `/api/wifi/events` | Event queue with long-poll `?timeout=` |
| GET | `/api/wifi/mode` | Current operating mode |
| POST | `/api/wifi/mode` | Switch mode `{"mode": "wifi-testing"|"serial-interface"}` |

### GPIO

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/gpio/set` | Drive pin `{"pin": 17, "value": 0|1|"z"}` |
| GET | `/api/gpio/status` | Read state of all actively driven pins |

### UDP Log

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/udplog` | Get buffered log lines `?since=&source=&limit=` |
| DELETE | `/api/udplog` | Clear the log buffer |

### Firmware

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/firmware/<project>/<file>` | Download binary (used by ESP32 OTA client) |
| GET | `/api/firmware/list` | List all available firmware files |
| POST | `/api/firmware/upload` | Upload binary (multipart: `project` + `file`) |
| DELETE | `/api/firmware/delete` | Delete a file `{"project", "filename"}` |

### BLE

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ble/scan` | Scan for peripherals `{"timeout?", "name_filter?"}` |
| POST | `/api/ble/connect` | Connect by address `{"address"}` |
| POST | `/api/ble/disconnect` | Disconnect current connection |
| GET | `/api/ble/status` | Connection state (`idle` / `scanning` / `connected`) |
| POST | `/api/ble/write` | Write hex bytes `{"characteristic", "data", "response?"}` |

### GDB Debug

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/debug/start` | Override: manually start OpenOCD `{"slot", "chip?", "probe?"}` |
| POST | `/api/debug/stop` | Override: manually stop OpenOCD `{"slot"}` |
| GET | `/api/debug/status` | Debug state for all slots |
| GET | `/api/debug/group` | Slot groups and roles (dual-USB) |
| GET | `/api/debug/probes` | Available debug probes (ESP-Prog) |

### CW Beacon

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cw/start` | Start Morse beacon `{"freq", "message", "wpm?", "pin?", "repeat?"}` |
| POST | `/api/cw/stop` | Stop beacon |
| GET | `/api/cw/status` | Current beacon state |
| GET | `/api/cw/frequencies` | List achievable frequencies `?low=&high=` |

### Test / Other

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/test/update` | Push test session start/step/result/end |
| GET | `/api/test/progress` | Poll current test session state |
| POST | `/api/human-interaction` | Block until operator confirms `{"message", "timeout?"}` |
| GET | `/api/human/status` | Check if a human interaction is pending |
| POST | `/api/human/done` | Confirm the pending interaction |
| POST | `/api/human/cancel` | Cancel the pending interaction |
| GET | `/api/log` | Activity log `?since=` |

---

## Project Structure

```
pi/
  portal.py                  Main HTTP server, proxy supervisor, all API endpoints
  wifi_controller.py         WiFi AP/STA/scan/relay backend
  ble_controller.py          BLE scan/connect/write backend (bleak)
  cw_beacon.py               CW beacon (GPCLK Morse transmitter for DF testing)
  debug_controller.py        GDB debug manager (OpenOCD lifecycle, probe allocation)
  plain_rfc2217_server.py    RFC2217 serial proxy with DTR/RTS passthrough
  install.sh                 One-command installer
  config/workbench.json      Optional hardware config (GPIO pins, debug probes)
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

## Configuration Reference: workbench.json

The config file at `/etc/rfc2217/workbench.json` maps physical USB hub ports to fixed slot labels and assigns GPIO pins and debug probes.

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
| `gpio_boot` | int or null | Pi BCM GPIO pin wired to DUT BOOT/GPIO0/GPIO9. Omit if not wired. |
| `gpio_en` | int or null | Pi BCM GPIO pin wired to DUT EN/RST. Omit if not wired. |
| `slots` | array | Fixed slot definitions mapping USB hub ports to labels and network ports. |
| `slots[].label` | string | Slot name shown in UI (e.g., `"SLOT1"`) |
| `slots[].usb_prefix` | string | USB path prefix from udev `ID_PATH` (e.g., `"0:1.1"` matches `0:1.1:1.0` and `0:1.1.4:1.0`). Discover with `udevadm info -q property -n /dev/ttyACMx`. |
| `slots[].tcp_port` | int | RFC2217 TCP port for this slot |
| `slots[].gdb_port` | int | GDB port for OpenOCD |
| `slots[].openocd_telnet_port` | int | OpenOCD telnet port |
| `debug_probes` | array | ESP-Prog probe definitions. Omit or leave empty if using USB JTAG only. |
| `debug_probes[].label` | string | Human-readable probe name |
| `debug_probes[].type` | string | Probe type (`"esp-prog"`) |
| `debug_probes[].interface_config` | string | OpenOCD interface config file |
| `debug_probes[].bus_port` | string | USB bus-port path to identify the probe |

---

## License

MIT
