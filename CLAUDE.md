# Universal-ESP32-Tester

Raspberry Pi-based test instrument for ESP32 firmware: serial proxy (RFC2217), WiFi AP/STA, GPIO control, HTTP relay, all via REST API.

## Tech Stack

- **Runtime**: Python 3.9+ (Pi), Python 3.11 (devcontainer)
- **Frameworks**: Flask-like HTTP server (portal.py), pyserial (RFC2217), hostapd/dnsmasq (WiFi)
- **Testing**: pytest, ruff, mypy
- **Hardware**: Raspberry Pi Zero W (eth0 + wlan0), USB hub for serial slots

## Project Structure

```
pi/
  portal.py                   # Web portal + API + proxy supervisor (main entry)
  wifi_controller.py          # WiFi instrument (AP, STA, scan, relay)
  plain_rfc2217_server.py     # RFC2217 server with DTR/RTS passthrough
  install.sh                  # Pi installer
  config/slots.json           # Slot-to-port mapping
  udev/                       # udev rules for hotplug
  cw_beacon.py                # CW beacon — compat shim over signal_generator (GPCLK backend)
  signal_generator.py         # Unified RF source: Si5351 (I2C) with GPCLK fallback + optional PE4302 attenuator
  si5351.py                   # Si5351A I2C clock generator driver
  pe4302.py                   # PE4302 3-wire serial step attenuator driver
  gpclk.py                    # BCM2835/7 GPCLK hardware clock (GPIO 5/6)
  morse.py                    # Backend-agnostic Morse keyer
  bcm_gpio.py                 # Shared /dev/mem GPIO primitives
  systemd/                    # systemd service unit
pytest/
  workbench_driver.py   # WorkbenchDriver class for test scripts
  conftest.py                 # pytest fixtures
  workbench_test.py           # End-to-end workbench tests
docs/
  Embedded-Workbench-FSD.md  # Full functional specification
container/                    # Alternate devcontainer config
skills/esp32-test-harness/    # Claude Code skill
skills/cw-beacon/             # CW beacon skill (GPCLK Morse for DF testing)
```

## Commands

```bash
# Install on Pi
cd pi && bash install.sh

# Discover USB slot keys
rfc2217-learn-slots

# Run portal manually
python3 pi/portal.py

# Run tests
pip install -r requirements-dev.txt
pytest pytest/

# Lint
ruff check .
mypy --strict .
```

## Code Style

- Python: ruff for linting, mypy strict, format with ruff
- `snake_case` for functions and variables
- REST API endpoints under `/api/` namespace
- Slot-based identity: TCP ports tied to physical USB connectors, not devices

## Specifications

- `docs/Embedded-Workbench-FSD.md` -- Full functional specification (Embedded Workbench)

## Key Conventions

- 3 fixed slots (SLOT1-SLOT3) mapped to physical USB hub ports via `usb_prefix` in `workbench.json`
- Dual-USB boards (ESP32-S3 with sub-hub) map both interfaces to the same slot
- Portal runs on port 8080, serial RFC2217 on ports 4001-4003, GDB on 3333-3335
- WiFi modes: AP (Pi hosts 192.168.4.0/24) or STA (Pi joins DUT network)
- GPIO pin allowlist: `{5,6,12,13,16,17,18,19,20,21,22,23,24,25,26}`
- Always release GPIO pins after use: `gpio_set(pin, "z")`
- One RFC2217 client per serial device at a time
- ESP32-C3 reset: use `POST /api/serial/reset` or `--after=no-reset` with esptool
- Environment variable `SERIAL_PI=192.168.0.87` set in devcontainer
- Deploy portal to Pi: `scp pi/portal.py pi@192.168.0.87:/tmp/portal.py && ssh pi@192.168.0.87 'sudo cp /tmp/portal.py /usr/local/bin/rfc2217-portal && sudo systemctl restart rfc2217-portal'`
- Deploy debug_controller: `scp pi/debug_controller.py pi@192.168.0.87:/tmp/ && ssh pi@192.168.0.87 'sudo cp /tmp/debug_controller.py /usr/local/bin/debug_controller.py && sudo systemctl restart rfc2217-portal'`

## Flashing

- Flash via esptool over RFC2217 with `--after no-reset`, then `POST /api/serial/reset` to reboot.
- Stop debug before flash on native USB chips (serial + JTAG share USB).
- Classic ESP32 bootloader offset: `0x1000`. All newer chips (C3, S3, C6, H2): `0x0000`.
- Portal never opens serial devices directly — only the RFC2217 proxy holds the port.

## Auto-Detection

- Per-slot: detects chip type + JTAG source (own slot for built-in JTAG, probe slot for ESP-Prog, or none)
- `/api/devices` exposes `detected_chip`, `jtag_slot`, `debugging`, `is_probe` per slot
- Probe-only slots (FTDI VID `0403`, no DUT) are never auto-debugged

## Gotchas / Do Not

- Do NOT SSH into the Pi to interact with the workbench -- always use the HTTP API at :8080. The `WorkbenchDriver` in `pytest/workbench_driver.py` wraps all API calls. SSH is only for deploying code updates to `/usr/local/bin/rfc2217-portal`.
- Do NOT use `hard-reset` or `watchdog-reset` after modes with native USB chips -- use `no-reset` to avoid USB re-enumeration crashes on Pi Zero 2 W
- udev events require `systemd-run --no-block` to reach the portal process
- wlan0 is reserved for testing -- use eth0 (USB Ethernet) for LAN
- Only one client can connect to each RFC2217 port at a time
- Hotplug events are sandboxed by udev -- check rules if events stop arriving

## Host Access

See `remote-connections` skill for SSH, InfluxDB, Grafana, and Docker details.
