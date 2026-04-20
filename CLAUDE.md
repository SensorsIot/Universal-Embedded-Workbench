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
  config/signalgen.json       # Signal generator config (Si5351 I2C, PE4302 pins)
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

- Always release GPIO pins after use: `gpio_set(pin, "z")`
- Environment variable `SERIAL_PI=192.168.0.87` set in devcontainer
- Deploy portal to Pi: `scp pi/portal.py pi@192.168.0.87:/tmp/portal.py && ssh pi@192.168.0.87 'sudo cp /tmp/portal.py /usr/local/bin/rfc2217-portal && sudo systemctl restart rfc2217-portal'`
- Deploy debug_controller: `scp pi/debug_controller.py pi@192.168.0.87:/tmp/ && ssh pi@192.168.0.87 'sudo cp /tmp/debug_controller.py /usr/local/bin/debug_controller.py && sudo systemctl restart rfc2217-portal'`

All functional behavior (slot auto-detect, flashing, GPIO API, signal generator, WiFi modes, GDB debug, RFC2217 semantics, etc.) is specified in `docs/Embedded-Workbench-FSD.md`. Don't restate it here.

## Gotchas / Do Not

- Do NOT SSH into the Pi to interact with the workbench -- always use the HTTP API at :8080. The `WorkbenchDriver` in `pytest/workbench_driver.py` wraps all API calls. SSH is only for deploying code updates to `/usr/local/bin/rfc2217-portal`.

## Host Access

See `remote-connections` skill for SSH, InfluxDB, Grafana, and Docker details.
