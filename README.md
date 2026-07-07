# Universal ESP32 Workbench

**Plug in any ESP32. Serial and debug are ready instantly. No configuration needed.**

A Raspberry Pi that turns into a complete remote test instrument for ESP32 devices. Plug boards into its USB hub and control everything -- serial, debug, WiFi, BLE, GPIO, SDR, signal generation, firmware updates -- over the network through a single HTTP API (or the MCP server).

Zero-config by design: on boot the portal walks the Pi's USB hub topology and pre-creates one slot per usable hub port (`SLOT1`, `SLOT2`, ...), each mapped to a physical USB connector. The number of slots is determined by the host — typically 3–4 on a Pi Zero 2 W with hub, 4 on a Pi 3B+, 4 on a Pi 4B, 4 on a Pi 5. Slots are always visible in the web UI even when empty. Plug in a device and it automatically maps to the correct slot by USB path, gets a serial port, chip identification, and OpenOCD for GDB debugging. Dual-USB boards (ESP32-S3 with sub-hub) are handled transparently -- both interfaces map to the same slot.

---

## Features

- **Remote serial (RFC2217)** — every USB slot as a network serial port; works with esptool, PlatformIO, ESP-IDF, any pyserial tool.
- **Remote GDB / JTAG debug** — OpenOCD auto-starts per chip (C3/C6/H2/S3 USB-JTAG, dual-USB, ESP-Prog).
- **Flashing** — over USB (RFC2217, or **local-Pi esptool** for CP2102/CH340/CH9102 bridge boards) and **over-the-air** (`POST /api/ota`, espota relayed to deployed on-LAN boards).
- **SDR receiver (RTL-SDR + rtl_433)** — decode / analyze / rtl_power captures, phased `acquire`, a live rtl_433 console, "AI Sherlock" record→reverse-engineer, an rtl_433 device database, and dongle recovery.
- **Signal generator (Si5351 / GPCLK + PE4302)** — continuous carrier, Morse/CW beacon, retune, step attenuation.
- **WiFi test instrument** — SoftAP (optionally NAT-bridged to the LAN), station mode, scan, HTTP relay, and captive-portal provisioning of WiFiManager DUTs.
- **MQTT test broker** — on-demand mosquitto so DUTs on the WiFi AP can run pub/sub integration tests without internet.
- **BLE proxy** — scan / connect / write via the Pi's Bluetooth radio.
- **GPIO control** — drive boot/reset pins to force download mode, simulate buttons.
- **UDP log receiver**, **OTA firmware repository**, and **test-progress + operator-interaction** tracking.
- **Web portal** — live dashboard of slots, WiFi, logs, and test progress.
- **pytest driver** (`WorkbenchDriver`) — all of the above from test scripts.
- **MCP interface** — the entire API as ~60 MCP tools for Claude Code / Desktop.

Setup is in **[Installation](#installation)**; day-to-day operation in **[Usage](#usage)**. The complete HTTP API and MCP tool reference lives in the FSD, **[Appendix D](docs/Embedded-Workbench-FSD.md#appendix-d-http-api--mcp-reference)**.

---

## Installation

### Pi service and skills

The workbench has two installable components:

1. **Pi service** — runs on a Raspberry Pi, exposes the REST API and proxies serial, JTAG, WiFi, BLE, GPIO, SDR, and the signal generator. Install once per workbench.
2. **Claude Code skills** — project skills under `.claude/skills/` that teach Claude Code how to drive the workbench (PlatformIO/ESP-IDF lifecycle, test harness, signal generator, SDR receiver, FSD writer, etc.). Install on every developer machine that uses Claude Code with the workbench.

The Pi service and the skills are independent — you can install either alone.

**Pi service** (on the Raspberry Pi):

```bash
git clone https://github.com/SensorsIot/Universal-Embedded-Workbench.git
cd Universal-Embedded-Workbench/pi
sudo bash install.sh
```

The installer sets up all dependencies (pyserial, hostapd, dnsmasq, bleak, esptool, OpenOCD, rtl-sdr/rtl-433, mosquitto), copies scripts to `/usr/local/bin/`, creates data directories, and starts the portal as a systemd service.

**Skills** (on each dev machine that drives the workbench):

```bash
git clone https://github.com/SensorsIot/Universal-Embedded-Workbench.git /tmp/uew
mkdir -p .claude/skills
cp -r /tmp/uew/.claude/skills/. .claude/skills/
rm -rf /tmp/uew
```

`.claude/skills/` is project-scoped (loaded only for the current repo). Use `~/.claude/skills/` instead to install globally. Skills include the PlatformIO / ESP-IDF lifecycle, test harness, WiFi/BLE/MQTT control, serial + UDP logging, signal generator, SDR receiver, test tracking, and the FSD writer. Most `workbench-*` skills assume the Pi is reachable at `workbench.local` (or the IP in `SERIAL_PI`) — override `SERIAL_PI` in your shell/devcontainer if your network differs. Claude Code loads skills at session start, so restart your session after copying.

### Hardware

| Component | Purpose |
|-----------|---------|
| **Raspberry Pi** (any model) | Runs the portal. Needs onboard WiFi + Bluetooth. Auto-detects model and USB topology. |
| **USB Ethernet adapter** (Pi Zero 2 W only) | Wired LAN on eth0 (wlan0 is reserved for WiFi testing). Pi 3/4/5 have built-in Ethernet. |
| **USB hub** (Pi Zero 2 W only) | Connect multiple ESP32 boards. Pi 3/4/5 already have 4 USB ports. |
| **RTL-SDR dongle** (optional) | 433/315/868 MHz receive gateway (`rtl_433`). |
| **Si5351 + PE4302** (optional) | RF signal source + step attenuator. |
| **Jumper wires** (optional) | Pi GPIO to DUT GPIO for automated boot mode / reset control |

**Auto-detection:** The portal walks `/sys/bus/usb/devices/` on startup, finds every downstream USB hub, and creates one slot per hub port. Ports occupied by non-serial devices (USB Ethernet, storage) are filtered out, so only ESP32-usable ports become slots. TCP ports are auto-assigned as `4001 + slot_index`, GDB ports as `3333 + slot_index`.

Some Pi boards advertise more hub ports than are physically wired to USB-A jacks. From sysfs alone these unwired "phantom" ports are indistinguishable from empty wired jacks, so the portal keeps a small per-model phantom table keyed on `/proc/device-tree/model` (`_PHANTOM_PORTS_BY_MODEL` in `pi/portal.py`). Add an entry there if you find a new phantom on a model not yet listed.

| Pi model | Expected slots | Notes |
|----------|---------------|-------|
| Pi Zero 2 W + external hub | 3–4 (external hub ports minus ethernet) | Tested |
| Pi 3 B+ | 4 | Phantom port `0:1.4` filtered via model table (tested on Rev 1.3) |
| Pi 4 B | 2 USB2 + 2 USB3 slots | Same kernel API, expected to work |
| Pi 5 | Up to 4 slots on XHCI | Same kernel API, expected to work |

No config file is needed for auto-detection. Custom overrides (labels, specific TCP/GDB ports, GPIO pins, debug probes) go in `/etc/rfc2217/workbench.json` — see [Configuration](#configuration-workbenchjson-optional). GPIO wiring is optional; without it the workbench still provides serial and debug for every plugged-in device.

### Network

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

| Port | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| 8080 | TCP/HTTP | Clients -> Pi | Web portal, REST API, firmware downloads |
| 4001+ | TCP/RFC2217 | Clients -> Pi | Serial connections (auto-assigned per device) |
| 3334+ | TCP/GDB | Clients -> Pi | GDB connections (`3333 + slot_index`) |
| 4444+ | TCP/telnet | Clients -> Pi | OpenOCD telnet (`4443 + slot_index`) |
| 5555 | UDP | ESP32 -> Pi | Debug log receiver |
| 1883 | TCP/MQTT | DUTs -> Pi | Test broker (when started) |

---

## Usage

Everything below is driven through the HTTP API on port 8080 — directly, through the `WorkbenchDriver`, or through the MCP tools. See **[HTTP API](#http-api)** and **[MCP](#mcp)** at the end of this chapter.

### Plug in and go

1. Plug an ESP32 into any USB port on the Pi's hub. It's auto-detected within seconds.
2. Query what's connected:

```bash
curl http://workbench.local:8080/api/devices | jq
```

The response lists every slot with its serial URL, chip info, debug status, and USB devices:

```json
{
  "slots": [
    {
      "label": "SLOT1", "state": "idle", "running": true,
      "url": "rfc2217://workbench.local:4001",
      "detected_chip": "esp32s3", "debugging": true, "debug_gdb_port": 3333,
      "devnodes": ["/dev/ttyACM0", "/dev/ttyACM1"]
    },
    { "label": "SLOT2", "state": "absent", "running": false }
  ]
}
```

3. Flash and debug — see below. Everything auto-restarts after a flash: the workbench detects the USB re-enumeration and brings serial and debug back up automatically.

### Serial

Each USB hub port maps to a slot (`SLOT1`, ...) via USB path. One RFC2217 client at a time per device. Works with esptool, PlatformIO, ESP-IDF, and any pyserial tool. On plug/unplug, udev notifies the portal and the proxy starts/stops automatically.

```python
# Serial monitor over RFC2217 (Python)
import serial
ser = serial.serial_for_url("rfc2217://workbench.local:4001", baudrate=115200)
```

```ini
# PlatformIO (platformio.ini)
[env:esp32]
monitor_port = rfc2217://workbench.local:4001
```

**Reset behavior:**

| Chip | USB Interface | Device Node | Reset | Caveat |
|------|--------------|-------------|-------|--------|
| ESP32, ESP32-S2 | UART bridge (CP2102, CH340) | `/dev/ttyUSB*` | DTR/RTS toggle | Reliable |
| ESP32-C3, ESP32-S3 | Native USB-Serial/JTAG | `/dev/ttyACM*` | DTR/RTS toggle | Linux asserts DTR+RTS on port open → download mode during early boot; the Pi adds a 2 s delay before opening to avoid this |

### Flashing

```bash
# Over RFC2217 (binaries stay on host, no SCP needed)
esptool --port rfc2217://workbench.local:4001 --chip esp32c3 \
  --before default-reset --after no-reset \
  write-flash 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 firmware.bin

# Reboot into the new firmware
curl -X POST http://workbench.local:8080/api/serial/reset \
  -H "Content-Type: application/json" -d '{"slot":"SLOT1"}'
```

For a **classic ESP32 behind a USB-serial bridge** (CP2102/CH340/CH9102) whose auto-reset can't be driven through RFC2217, flash locally on the Pi with `POST /api/flash` (`bin@<offset>` file parts) instead.

**Over-the-air:** for a board already **deployed on the LAN** (off the USB slots) that a client can't reach directly — e.g. a NAT'd container that can't accept ArduinoOTA's reverse connection — the workbench relays an OTA push. (A host on the LAN can OTA the board directly and doesn't need this.)

```bash
curl -X POST http://workbench.local:8080/api/ota \
  -F target=192.168.0.176 -F firmware=@.pio/build/<env>/firmware.bin
```

### GDB / JTAG debug

OpenOCD starts **automatically** on plug-in. The workbench auto-detects the chip and exposes the GDB port in `/api/devices`. Serial and JTAG coexist on the same USB connection.

```bash
riscv32-esp-elf-gdb build/project.elf \
  -ex "target extended-remote workbench.local:3333" -ex "monitor reset halt"
```

| Approach | Chips | Extra Hardware |
|----------|-------|:-:|
| USB JTAG (auto) | C3, C6, H2, S3 (native USB) | None |
| Dual-USB | S3 (two USB ports) | None |
| ESP-Prog | All variants | ESP-Prog + cable |

Verified USB-JTAG TAP IDs: C3 `0x00005c25`, C6 `0x0000dc25`, H2 `0x00010c25`, S3 `0x120034e5`. Classic ESP32 without USB JTAG uses an ESP-Prog probe configured in `workbench.json`.

### WiFi test instrument

The Pi's **wlan0** radio acts as a programmable AP or station, isolated from eth0.

- **AP mode** — SoftAP with any SSID/password; DUTs on `192.168.4.x`, Pi at `192.168.4.1`, DHCP + DNS included. Optionally NAT-bridged to the LAN for internet + broker reach.
- **STA mode** — join a DUT's captive-portal AP to test provisioning; `enter-portal` provisions a WiFiManager DUT onto the workbench AP.
- **HTTP relay** — proxy HTTP requests through wlan0 to devices on the WiFi network.
- **Scan** — list nearby networks. AP and STA are mutually exclusive.

### GPIO control

Drive Pi GPIO pins to simulate button presses or force boot mode (hold a pin LOW during reset). **Allowed pins (BCM):** 5, 6, 12, 13, 16–27. Always release with `"z"` when done — a pin left LOW prevents the DUT from booting.

| Pi GPIO (BCM) | DUT Pin | Function |
|---------------|---------|----------|
| 17 | EN/RST | Hardware reset (active LOW) |
| 18 | GPIO0 (ESP32) / GPIO9 (C3) | Boot mode select (LOW = download mode) |

### BLE proxy

The Pi's onboard Bluetooth scans for, connects to, and writes raw bytes to BLE peripherals (BLE-to-HTTP bridge, one connection at a time). Bluetooth must be powered on: `sudo rfkill unblock bluetooth && sudo hciconfig hci0 up && sudo bluetoothctl power on`.

### Signal generator

Unified RF source with programmable frequency, attenuation, and optional Morse keying, auto-selecting between two backends:

- **Si5351** (I²C on GPIO 2/3) — 8 kHz–160 MHz, three channels (CLK0–CLK2), fractional synthesis. Preferred when detected.
- **GPCLK** (BCM hardware clock on GPIO 5/6) — 122 kHz–250 MHz, integer dividers. Always available, no extra hardware.

An optional **PE4302** step attenuator (0–31.5 dB, GPIO 6/12/13) sits in the RF path. Both backends share a Morse keyer, so any carrier can be CW-keyed (DF beacons, sensitivity tests). Without a `morse` argument the carrier runs continuous.

Wiring — Si5351: SDA=GPIO2, SCL=GPIO3; PE4302: LE=GPIO6, CLK=GPIO12, DATA=GPIO13; GPCLK: GPIO5 or GPIO6.

### SDR receiver

An RTL-SDR dongle behind `rtl_433` receives and decodes 433/315/868 MHz OOK/FSK devices (remotes, weather sensors, TPMS) — the receive-side counterpart to the signal generator.

- **Captures** — `capture` (rtl_433 decode → records + RSSI), `analyze` (raw pulse timing + RSSI, decode-independent), `power` (`rtl_power` peak/mean).
- **Phased `acquire`** — locate → level → decode → classify.
- **Live console** — a persistent `rtl_433` streaming into a sequence-numbered ring buffer the client fast-polls.
- **AI Sherlock** — record a session of button presses, then reverse-engineer the timing / preamble / per-key field.
- **Device database** — `rtl_433.conf` flex decoders (installed to `/etc/rtl_433/`) name a reverse-engineered remote.
- **Dongle recovery** — USB reset for a wedged RTL-SDR.

One dongle, one user: one-shot captures and the live console are mutually exclusive.

### MQTT test broker

An on-demand mosquitto broker (open, port 1883, reachable at both `192.168.4.1` and the Pi's LAN IP) for MQTT integration tests — DUTs on the WiFi AP publish/subscribe without internet. Start / stop / status via the API.

### UDP logging & OTA firmware repository

- **UDP log receiver** — listens on **UDP 5555** for ESP32 debug output; essential when the USB port is occupied (e.g. an S3 running as a USB HID keyboard). Buffered (last 2000 lines), filterable by source IP and time.
- **OTA firmware repository** — serves `.bin` files at `http://workbench.local:8080/firmware/<project>/<file>.bin` (suitable as ESP-IDF `esp_https_ota` URLs).

```bash
# 1. Upload firmware   2. Trigger OTA via HTTP relay   3. Watch UDP logs
curl -X POST http://workbench.local:8080/api/firmware/upload -F "project=demo" -F "file=@build/demo.bin"
curl -X POST http://workbench.local:8080/api/wifi/http -H "Content-Type: application/json" \
  -d '{"method":"POST","url":"http://192.168.4.15/ota"}'
curl http://workbench.local:8080/api/udplog?source=192.168.4.15
```

### Test automation & web portal

- **Test progress** — push live session start/step/result/end to the web portal for operator visibility.
- **Human interaction** — block a test script until an operator confirms a physical action (a modal on the Pi's display).
- **Web portal** at `http://<pi-ip>:8080` — a dashboard of every slot (state, detected chip, debug status, USB devices), WiFi state, activity log, test progress, and the interaction modal.

### pytest driver

```bash
pip install -e Universal-Embedded-Workbench/pytest
```

```python
from workbench_driver import WorkbenchDriver
wt = WorkbenchDriver("http://workbench.local:8080")

wt.serial_reset("SLOT1")
wt.serial_monitor("SLOT1", pattern="WiFi connected", timeout=30)

wt.ap_start("TestAP", "password123")
station = wt.wait_for_station(timeout=30)
wt.http_get(f"http://{station['ip']}/api/status")
wt.ap_stop()

wt.siggen_start(freq_hz=3_571_000, morse={"message": "VVV DE TEST", "wpm": 15, "repeat": True})
wt.siggen_stop()

wt.sdr_capture(freq_hz=433_920_000, duration_s=10)      # decode window
wt.ble_scan(name_filter="iOS-Keyboard")
wt.test_start(spec="Firmware v2.1", phase="Integration", total=10)
```

### curl examples

```bash
curl http://workbench.local:8080/api/devices | jq                       # discovery
curl -X POST .../api/serial/reset -d '{"slot":"SLOT1"}'                  # reset
curl -X POST .../api/wifi/ap_start -d '{"ssid":"TestAP","password":"secret"}'
curl -X POST .../api/gpio/set -d '{"pin":18,"value":0}'                  # hold boot pin LOW
curl -X POST .../api/siggen/start -d '{"freq_hz":3500000,"backend":"si5351"}'
curl -X POST .../api/sdr/capture -d '{"freq_hz":433920000,"duration_s":10}'
curl -X POST .../api/ble/scan -d '{"timeout":5,"name_filter":"iOS-Keyboard"}'
```

### HTTP API

The workbench is driven entirely by a JSON HTTP API on `:8080` (no auth; every response carries `"ok"`). The examples above and the `WorkbenchDriver` all wrap it.

**Full endpoint reference → [FSD Appendix D](docs/Embedded-Workbench-FSD.md#appendix-d-http-api--mcp-reference).**

### MCP

An MCP server (`mcp/workbench_mcp.py`) exposes the whole API as **~60 MCP tools**, so an MCP client (Claude Code, Claude Desktop) can drive the bench directly. It's a thin stdio proxy that runs on the client machine and reaches the bench via `WORKBENCH_URL`.

- **Setup (Claude Code + Desktop) → [`mcp/README.md`](mcp/README.md)**
- **Tool reference → [FSD Appendix D](docs/Embedded-Workbench-FSD.md#appendix-d-http-api--mcp-reference)**

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Device not detected | Bad USB cable / unpowered hub | Try a data-capable cable; check `lsusb` on the Pi |
| Connection refused on serial | Proxy not running | Check `:8080`; verify the device in `/api/devices` |
| Timeout during flash | Proxy not released | Use `POST /api/flash` — it manages proxy lifecycle |
| `Wrong boot mode (0x13)` flashing a bridge board | RFC2217 can't drive DTR/RTS reset | Use `POST /api/flash` (local-Pi esptool) |
| Port busy | Another client connected | RFC2217 = 1 client; close the other |
| USB flapping (rapid connect/disconnect) | Erased/corrupt flash, boot loop | Portal auto-recovers via GPIO; `POST /api/serial/recover` to force |
| Slot in `download_mode` | Device in bootloader | Flash, then `POST /api/serial/release` to reboot |
| ESP32-C3 stuck in download mode | DTR asserted on open | `POST /api/serial/reset` |
| GDB won't connect | OpenOCD not started (classic ESP32 w/o USB JTAG) | Check `/api/devices` for `debugging:true`; needs an ESP-Prog in `workbench.json` |
| BLE scan finds nothing | Bluetooth powered off | `sudo rfkill unblock bluetooth && sudo hciconfig hci0 up && sudo bluetoothctl power on` |
| SDR reads noise / no signal | Near-field AGC overload, or wedged dongle | Fixed `gain`; `POST /api/sdr/reset` (reboot the Pi if sample loss persists) |
| Stale slot data | Device unplugged mid-session | Auto-cleans on unplug; else `sudo systemctl restart rfc2217-portal` |

---

## Reference

### Project structure

```
pi/
  portal.py                  Main HTTP server, proxy supervisor, all API endpoints
  wifi_controller.py         WiFi AP/STA/scan/relay backend
  ble_controller.py          BLE scan/connect/write backend (bleak)
  signal_generator.py        Unified RF source: Si5351 (I2C) + optional PE4302, GPCLK fallback
  sdr_controller.py          RTL-SDR receiver: rtl_433 decode/analyze/power/acquire, live console
  si5351.py / pe4302.py / gpclk.py / morse.py   RF driver primitives
  mqtt_controller.py         On-demand mosquitto test broker
  debug_controller.py        GDB debug manager (OpenOCD lifecycle, probe allocation)
  plain_rfc2217_server.py    RFC2217 serial proxy with DTR/RTS passthrough
  bcm_gpio.py                Shared /dev/mem GPIO primitives
  install.sh                 One-command installer
  config/                    workbench.json, signalgen.json, sdr.json, rtl_433.conf
  scripts/                   udev/dnsmasq callbacks + espota.py (used by /api/ota)
  udev/ · systemd/           Hotplug rules · service unit
pytest/
  workbench_driver.py        Python test driver (WorkbenchDriver class)
  conftest.py · workbench_test.py
mcp/
  workbench_mcp.py           MCP server (API → ~60 tools); README.md, requirements.txt
docs/
  Embedded-Workbench-FSD.md  Full functional specification (Appendix D = API/MCP reference)
```

### Configuration: workbench.json (optional)

Slots are **auto-detected** on startup — no config file is required. Only create `/etc/rfc2217/workbench.json` to rename slots, force specific TCP/GDB ports, wire GPIO boot/reset pins, or register an ESP-Prog probe. Print a ready-to-paste config from currently plugged devices with `ssh pi@workbench.local sudo rfc2217-learn-slots`.

```json
{
  "gpio_boot": 18,
  "gpio_en": 17,
  "slots": [
    {"label": "SLOT1", "usb_prefix": "0:1.1", "tcp_port": 4001, "gdb_port": 3333, "openocd_telnet_port": 4444}
  ],
  "debug_probes": [
    {"label": "PROBE1", "type": "esp-prog", "interface_config": "interface/ftdi/esp_ftdi.cfg", "bus_port": "1-1.4:1.0"}
  ]
}
```

| Field | Description |
|-------|-------------|
| `gpio_boot` / `gpio_en` | Pi BCM GPIO wired to DUT BOOT/GPIO0/GPIO9 and EN/RST. Omit if not wired. |
| `slots[].label` | Slot name shown in the UI |
| `slots[].usb_prefix` | USB path prefix (e.g. `"0:1.1"`). Auto-detected if omitted. |
| `slots[].tcp_port` / `gdb_port` / `openocd_telnet_port` | Default to `4000+i` / `3332+i` / `4443+i`. |
| `debug_probes[]` | ESP-Prog/FT2232H probe definitions. Omit if using USB JTAG only. |

The signal generator has a separate `/etc/rfc2217/signalgen.json` (I²C bus, PE4302 pins, Si5351 address); the SDR has `/etc/rfc2217/sdr.json`. Defaults match the documented wiring — edit only if you wired things differently.

---

## License

MIT
