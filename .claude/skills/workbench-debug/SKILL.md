---
name: workbench-debug
description: Remote GDB debugging of ESP32 devices via the workbench. Covers USB JTAG (C3/S3), dual-USB (S3 two-port), and ESP-Prog (FT2232H) approaches. Use when setting up JTAG debugging, connecting GDB, configuring OpenOCD, or troubleshooting debug connections. Triggers on "GDB", "JTAG", "debug", "OpenOCD", "breakpoint", "ESP-Prog", "step through", "debug session".
---

# Workbench GDB Debugging

Remote GDB debugging of ESP32 devices through the workbench Pi. OpenOCD runs on the Pi, GDB connects from the container over TCP.

**Architecture:**
```
[Container]              [Pi (workbench)]           [ESP32]
  GDB ──── TCP :3333 ────── OpenOCD ──── USB JTAG ──────── CPU
                             (or)
                           OpenOCD ──── ESP-Prog ── JTAG pins
```

---

## Three Approaches

| Approach | Chips | Extra Hardware | Serial During Debug |
|----------|-------|:-:|:-:|
| **USB JTAG** (FR-024) | C3, S3 (native USB only) | None | Yes |
| **Dual-USB** (FR-025) | S3 (two USB connectors) | None | Yes + app USB |
| **ESP-Prog** (FR-026) | All ESP32 variants | ESP-Prog (~$15) + cable | Yes |

---

## Auto-Debug (Zero Config)

OpenOCD starts **automatically** when a device is plugged in or at boot. No API call needed.

**How it works:**
1. Device hotplugged → serial proxy starts → auto-detect tries OpenOCD configs
2. Chip identified via JTAG TAP ID → OpenOCD starts on the assigned GDB port
3. If USB JTAG fails (e.g. classic ESP32), falls back to ESP-Prog probe if available
4. GDB port reported in `/api/devices` response

**Check debug status:**
```bash
curl http://workbench.local:8080/api/devices
# Look for: "debugging": true, "debug_chip": "esp32s3", "debug_gdb_port": 3335
```

**Manual override (optional -- only needed to force-stop or force-start):**
```bash
# Force stop (won't auto-restart until next hotplug)
curl -X POST http://workbench.local:8080/api/debug/stop -d '{}'

# Force start with specific chip
curl -X POST http://workbench.local:8080/api/debug/start \
  -d '{"chip": "esp32c3"}'
```

---

## JTAG Reset (Preferred When Available)

When a debug session is active, the workbench automatically uses **JTAG reset** instead of DTR/RTS serial reset. This is transparent — the same `/api/serial/reset` API is used.

**Why JTAG reset is better:**
- No USB re-enumeration (device node stays stable)
- No flapping risk
- No 2-second boot delay
- Works even when serial port is unresponsive
- Can halt the CPU to stop boot loops

**Via OpenOCD telnet (manual):**
```bash
# Soft reset (chip reboots normally)
echo "reset run" | nc 192.168.0.87 4446

# Halt CPU (stops execution immediately)
echo "halt" | nc 192.168.0.87 4446

# Reset and halt (for debugging from first instruction)
echo "reset halt" | nc 192.168.0.87 4446
```

**Via workbench API (automatic):**
```bash
# Uses JTAG reset when debug session is active, DTR/RTS otherwise
curl -X POST http://workbench.local:8080/api/serial/reset \
  -H "Content-Type: application/json" -d '{"slot": "slot-1"}'
```

**Availability:**
| Scenario | JTAG reset? |
|----------|:-:|
| C3/S3/C6/H2 with native USB | Yes (auto-started) |
| Classic ESP32 + ESP-Prog | Yes (when probe wired) |
| Classic ESP32 without ESP-Prog | No — DTR/RTS fallback |

---

## Prerequisites

OpenOCD is pre-installed on the Pi:
```
/usr/local/bin/openocd-esp32           # binary
/usr/local/share/openocd-esp32/scripts/ # config files
```

If missing, run `install.sh` or manually:
```bash
# On Pi (aarch64)
wget https://github.com/espressif/openocd-esp32/releases/download/v0.12.0-esp32-20260304/openocd-esp32-linux-arm64-0.12.0-esp32-20260304.tar.gz
tar xzf openocd-esp32-linux-arm64-*.tar.gz
sudo cp openocd-esp32/bin/openocd /usr/local/bin/openocd-esp32
sudo mkdir -p /usr/local/share/openocd-esp32
sudo cp -r openocd-esp32/share/openocd/scripts /usr/local/share/openocd-esp32/scripts
```

---

## 1. USB JTAG (ESP32-C3 / ESP32-S3 with Native USB)

### Identify the device

The device must show as `303a:1001` (Espressif USB JTAG/serial debug unit).
Boards with CH340/CP2102 UART bridges do NOT support USB JTAG.

```bash
# Check from Pi
ssh pi@192.168.0.87 "lsusb -d 303a:1001"
# → Bus 001 Device 066: ID 303a:1001 Espressif USB JTAG/serial debug unit
```

USB interface layout (no kernel unbind needed):
- Interface 0: CDC-ACM serial → `/dev/ttyACM*` (RFC2217 proxy)
- Interface 1: CDC Data
- Interface 2: Vendor Specific (**unclaimed** — OpenOCD uses via libusb)

### Chip auto-detection

USB PID `303a:1001` is the same for C3 and S3. The JTAG TAP ID identifies the chip:

| TAP ID | Chip | Architecture | Config |
|--------|------|-------------|--------|
| `0x00005c25` | ESP32-C3 | RISC-V single-core | `esp32c3-builtin.cfg` |
| `0x00010c25` | ESP32-H2 | RISC-V single-core | `esp32h2-builtin.cfg` |
| `0x0000dc25` | ESP32-C6 | RISC-V single-core | `esp32c6-builtin.cfg` |
| `0x120034e5` | ESP32-S3 | Xtensa dual-core | `esp32s3-builtin.cfg` |

### Start OpenOCD manually (for testing)

```bash
# ESP32-C3
ssh pi@192.168.0.87 "openocd-esp32 -s /usr/local/share/openocd-esp32/scripts \
  -f board/esp32c3-builtin.cfg \
  -c 'gdb port 3333' -c 'telnet port 4444' -c 'bindto 0.0.0.0'"

# ESP32-S3
ssh pi@192.168.0.87 "openocd-esp32 -s /usr/local/share/openocd-esp32/scripts \
  -f board/esp32s3-builtin.cfg \
  -c 'gdb port 3333' -c 'telnet port 4444' -c 'bindto 0.0.0.0'"
```

### Connect GDB from container

```bash
# C3 (RISC-V)
riscv32-esp-elf-gdb build/project.elf \
  -ex "target extended-remote 192.168.0.87:3333" \
  -ex "monitor reset halt"

# S3 (Xtensa)
xtensa-esp32s3-elf-gdb build/project.elf \
  -ex "target extended-remote 192.168.0.87:3333" \
  -ex "monitor reset halt"
```

### Connect via OpenOCD telnet (quick test)

```python
import socket, time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('192.168.0.87', 4444))
time.sleep(0.5)
banner = s.recv(4096)  # telnet negotiation + "Open On-Chip Debugger"
s.sendall(b'halt\n')
time.sleep(1)
print(s.recv(4096).decode('latin-1'))  # "Target halted, PC=0x..."
s.sendall(b'resume\n')
time.sleep(0.5)
s.close()
```

### Serial coexistence

Serial (RFC2217) and JTAG use separate USB interfaces. Both work
simultaneously — `printf` output visible in serial monitor while GDB
is connected. No proxy stop needed.

---

## 2. Dual-USB (ESP32-S3 with Two USB Ports)

Some S3 boards expose both USB controllers:

| Port | Controller | Function |
|------|-----------|----------|
| USB-Serial/JTAG | Debug controller | Serial + JTAG (same as approach 1) |
| USB-OTG | Peripheral | Application USB (HID, CDC, MSC) |

Both ports connect to the Pi's USB hub (2 hub ports per DUT). All three
functions (serial, JTAG, app USB) work simultaneously.

Same OpenOCD commands as approach 1 — the debug port uses `esp32s3-builtin.cfg`.

---

## 3. ESP-Prog (External FT2232H Probe)

### JTAG pin wiring

| ESP-Prog | Signal | ESP32 | ESP32-C3 | ESP32-S3 |
|----------|--------|-------|----------|----------|
| Pin 4 | TCK | GPIO13 | GPIO4 | GPIO39 |
| Pin 8 | TDI | GPIO12 | GPIO5 | GPIO40 |
| Pin 6 | TDO | GPIO15 | GPIO6 | GPIO41 |
| Pin 2 | TMS | GPIO14 | GPIO7 | GPIO42 |
| Pin 3,5,7 | GND | GND | GND | GND |

### Unbind FTDI channel A

The Linux `ftdi_sio` driver claims both FT2232H channels as serial ports.
Channel A (JTAG) must be released before OpenOCD can use it:

```bash
# Find the USB bus ID
ssh pi@192.168.0.87 "lsusb -d 0403:6010"
# → Bus 001 Device 020: ID 0403:6010 ... FT2232C/D/H

# Unbind channel A (interface 0)
ssh pi@192.168.0.87 "echo '1-1.4:1.0' | sudo tee /sys/bus/usb/drivers/ftdi_sio/unbind"
# Channel B (/dev/ttyUSB1) remains for UART
```

### Start OpenOCD with ESP-Prog

```bash
ssh pi@192.168.0.87 "openocd-esp32 -s /usr/local/share/openocd-esp32/scripts \
  -f interface/ftdi/esp_ftdi.cfg \
  -f target/esp32.cfg \
  -c 'gdb port 3333' -c 'telnet port 4444' -c 'bindto 0.0.0.0'"
```

Replace `target/esp32.cfg` with the appropriate target:
- `target/esp32.cfg` — classic ESP32
- `target/esp32c3.cfg` — ESP32-C3
- `target/esp32s3.cfg` — ESP32-S3

### Classic ESP32 caveat: GPIO12 strapping pin

JTAG TDI is GPIO12, which selects flash voltage at boot. If HIGH at
power-on, the chip configures 1.8V flash (crashes on 3.3V boards).

**Fix:** Burn `VDD_SDIO` eFuse to force 3.3V:
```bash
## Port is auto-assigned — read it from /api/devices (the "url" field)
espefuse.py --port rfc2217://192.168.0.87:<PORT> set_flash_voltage 3.3V
```

---

## VS Code Integration

### launch.json (C3 / RISC-V)
```json
{
  "type": "cppdbg",
  "request": "launch",
  "program": "${workspaceFolder}/build/project.elf",
  "miDebuggerPath": "riscv32-esp-elf-gdb",
  "miDebuggerServerAddress": "192.168.0.87:3333",
  "setupCommands": [
    {"text": "set remote hardware-breakpoint-limit 2"},
    {"text": "monitor reset halt"}
  ]
}
```

### launch.json (S3 / Xtensa)
```json
{
  "type": "cppdbg",
  "request": "launch",
  "program": "${workspaceFolder}/build/project.elf",
  "miDebuggerPath": "xtensa-esp32s3-elf-gdb",
  "miDebuggerServerAddress": "192.168.0.87:3333",
  "setupCommands": [
    {"text": "set remote hardware-breakpoint-limit 2"},
    {"text": "monitor reset halt"}
  ]
}
```

### PlatformIO (platformio.ini)
```ini
debug_tool = esp-builtin
debug_server =
debug_port = 192.168.0.87:3333
```

---

## API Endpoints (when implemented)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/debug/start | Start OpenOCD `{"slot", "chip?", "probe?"}` |
| POST | /api/debug/stop | Stop OpenOCD `{"slot"}` |
| GET | /api/debug/status | Debug state for all slots |
| GET | /api/debug/group | Slot groups (dual-USB) |
| GET | /api/debug/probes | Available ESP-Prog probes |

These endpoints are specified in the FSD (FR-024/025/026) but not yet
implemented in portal.py.

**Note:** `POST /api/debug/start` and `POST /api/debug/stop` are optional overrides -- OpenOCD starts automatically when a device is plugged in. No API call is needed for normal use. All parameters are optional; the workbench auto-detects slot, chip, and probe.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `could not find or open device!` | Wrong config (C3 vs S3) or device not connected | Check `lsusb -d 303a:1001` |
| `JTAG scan chain interrogation failed: all ones` | JTAG cable not connected (ESP-Prog) | Wire TCK/TDI/TDO/TMS + GND |
| `UNEXPECTED: 0x00005c25` with S3 config | Device is actually a C3 | Use `esp32c3-builtin.cfg` |
| `UNEXPECTED: 0x120034e5` with C3 config | Device is actually an S3 | Use `esp32s3-builtin.cfg` |
| SLOT flapping after debug | OpenOCD halt/resume caused USB re-enum | `POST /api/serial/recover` or manual hotplug |
| `ftdi_sio` blocks OpenOCD | ESP-Prog channel A claimed by kernel | Unbind: `echo <busid>:1.0 > .../ftdi_sio/unbind` |
| GDB connection refused | OpenOCD not running or wrong port | Check `telnet 192.168.0.87 4444` first |
| Flash voltage crash (classic ESP32) | GPIO12/TDI HIGH at boot | Burn VDD_SDIO eFuse to 3.3V |
| No `303a:1001` in lsusb | Board uses CH340/CP2102 bridge, not native USB | Use ESP-Prog (FR-026) instead |
| Auto-debug didn't start | Chip not detected or flapping | Check `journalctl -u rfc2217-portal` for `auto-detect` messages |
| GDB port not in /api/devices | Auto-detect still running | Wait 10-15s after hotplug, then check again |

---

## Available Board Configs

```bash
# List all ESP32 configs on the Pi
ssh pi@192.168.0.87 "ls /usr/local/share/openocd-esp32/scripts/board/esp32*"
```

Key configs:
- `board/esp32c3-builtin.cfg` — C3 via USB JTAG
- `board/esp32s3-builtin.cfg` — S3 via USB JTAG
- `board/esp32c3-ftdi.cfg` — C3 via ESP-Prog
- `board/esp32s3-ftdi.cfg` — S3 via ESP-Prog
- `board/esp32-wrover-kit-3.3v.cfg` — Classic ESP32 via ESP-Prog
