# Serial Portal — Functional Specification Document

## 1. Overview

### 1.1 Purpose

Combined serial interface and WiFi test instrument running on a single
Raspberry Pi Zero W.  The serial interface exposes USB serial devices to
network clients via RFC2217 protocol with event-driven hotplug and slot-based
port assignment.  The WiFi workbench uses the Pi's onboard wlan0 radio as a
test instrument — starting SoftAP, joining networks, scanning, relaying HTTP,
and reporting station events — all controlled over the same HTTP API.

### 1.2 System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Network (192.168.0.x)                           │
└──────────────────────────────────────────────────────────────────────────┘
       │  eth0 (USB Ethernet)                          │
       │                                               │
       ▼                                               ▼
┌─────────────────────────┐              ┌─────────────────────────────────┐
│  Serial Portal Pi       │              │  VM Host (192.168.0.160)        │
│  esp32-workbench.local           │              │                                 │
│                         │              │  ┌─────────────────────┐        │
│  ┌───────────┐          │              │  │ Container A         │        │
│  │ SLOT1     │──────────┼─ :4001 ──────┼──│ rfc2217://:4001     │        │
│  └───────────┘          │              │  └─────────────────────┘        │
│  ┌───────────┐          │              │  ┌─────────────────────┐        │
│  │ SLOT2     │──────────┼─ :4002 ──────┼──│ Container B         │        │
│  └───────────┘          │              │  │ rfc2217://:4002     │        │
│  ┌───────────┐          │              │  └─────────────────────┘        │
│  │ SLOT3     │──────────┼─ :4003       │                                 │
│  └───────────┘          │              └─────────────────────────────────┘
│                         │
│  ┌───────────────────┐  │
│  │ WiFi Workbench    │  │
│  │ wlan0 (onboard)   │  │
│  │  AP: 192.168.4.1  │  │
│  │  STA / Scan       │  │
│  └───────────────────┘  │
│                         │                    ┌──────────────────┐
│  ┌───────────────────┐  │                    │  ESP32 DUT       │
│  │ BLE Proxy         │  │◄ ─ BLE (GATT) ─ ─ │  iOS-Keyboard    │
│  │ hci0 (onboard)    │  │                    │  BLE peripheral  │
│  │  Scan / Connect   │  │                    └──────────────────┘
│  │  Write GATT chars │  │
│  └───────────────────┘  │                    ┌──────────────────┐
│                         │                    │  ESP32 DUT       │
│  ┌───────────────────┐  │◄ ─ UDP :5555 ─ ─ ─│  debug logs      │
│  │ UDP Log Receiver  │  │                    └──────────────────┘
│  │  Port 5555        │  │
│  └───────────────────┘  │
│                         │
│  ┌───────────────────┐  │
│  │ Firmware Repo     │  │─── GET /firmware/<project>/<file>.bin
│  │ /var/lib/.../fw   │  │
│  └───────────────────┘  │
│                         │
│  Web Portal ────────────┼─ :8080
└─────────────────────────┘
```

### 1.3 Hardware

| Component | Details |
|-----------|---------|
| Raspberry Pi Zero W | esp32-workbench.local, onboard wlan0 radio |
| USB Hub | 3-port hub connected to single USB port |
| USB Ethernet adapter | eth0 — wired LAN for management and serial traffic |
| Devices | ESP32, Arduino, or any USB serial device |
| GPIO wiring | Pi GPIO 17 → DUT EN/RST (reset, active LOW); Pi GPIO 18 → DUT GPIO0/GPIO9 (boot select, active LOW); Pi GPIO 27 → Spare 1; Pi GPIO 22 → Spare 2 |

### 1.4 Operating Modes

The system operates in one of two modes at any time:

| Mode | Default | eth0 | wlan0 | Serial | WiFi Workbench |
|------|---------|------|-------|--------|-------------|
| **WiFi-Testing** | Yes | LAN (management + serial) | Test instrument (AP/STA/scan) | Active | Active |
| **Serial Interface** | No | LAN (management + serial) | Joins WiFi for additional LAN | Active | Disabled |

- **WiFi-Testing** (default): eth0 provides wired LAN connectivity.  wlan0 is
  dedicated to the WiFi test instrument — it can start a SoftAP, join external
  networks, scan, and relay HTTP.  Both serial slots and WiFi workbench are active.

- **Serial Interface**: wlan0 joins a user-specified WiFi network to provide
  wireless LAN connectivity (useful when no wired Ethernet is available).
  Serial slots remain active.  WiFi workbench endpoints return an error.

Mode is switched via `POST /api/wifi/mode` or the web UI toggle.

### 1.5 Components

| Component | Location | Purpose |
|-----------|----------|---------|
| portal.py (rfc2217-portal) | /usr/local/bin/rfc2217-portal | Web UI, HTTP API, proxy supervisor, hotplug handler, WiFi API, BLE API, UDP log, firmware serving |
| wifi_controller.py | /usr/local/bin/wifi_controller.py | WiFi instrument backend (AP, STA, scan, relay, events) |
| ble_controller.py | /usr/local/bin/ble_controller.py | BLE proxy backend (scan, connect, write GATT characteristics via bleak) |
| plain_rfc2217_server.py | /usr/local/bin/plain_rfc2217_server.py | RFC2217 server with direct DTR/RTS passthrough (all devices) |
| rfc2217-udev-notify.sh | /usr/local/bin/rfc2217-udev-notify.sh | Posts udev events to portal API |
| wifi-lease-notify.sh | /usr/local/bin/wifi-lease-notify.sh | Posts dnsmasq DHCP lease events to portal API |
| rfc2217-learn-slots | /usr/local/bin/rfc2217-learn-slots | Slot configuration helper |
| 99-rfc2217-hotplug.rules | /etc/udev/rules.d/ | udev rules for hotplug |
| slots.json | /etc/rfc2217/slots.json | Slot-to-port mapping |
| esp32_workbench_driver.py | pytest/ | HTTP test driver for the WiFi instrument |
| conftest.py | pytest/ | Pytest fixtures and CLI options |
| test_instrument.py | pytest/ | WiFi workbench self-tests (WT-xxx) |
| cw_beacon.py | /usr/local/bin/cw_beacon.py | CW beacon engine (GPCLK hardware clock + Morse keying) |
| debug_controller.py | /usr/local/bin/debug_controller.py | GDB debug manager (OpenOCD lifecycle, probe allocation) |

### 1.6 State Model

The system provides two independent services — Serial and WiFi — each with
its own state machine.  Serial operates per slot; WiFi operates on wlan0.

**Serial Service (per slot):**

| State | Description |
|-------|-------------|
| Absent | No USB device in this slot |
| Idle | Device present, proxy running, no active operation |
| Flashing | External tool (esptool) using RFC2217 proxy — reset/monitor blocked |
| Resetting | DTR/RTS reset in progress — proxy stopped, direct serial in use |
| Monitoring | Reading serial output for pattern matching |
| Flapping | USB connect/disconnect cycling detected — recovery failed or pending |
| Recovering | USB unbound, recovery in progress (GPIO or backoff) |
| Download Mode | GPIO holding BOOT LOW, device stable in bootloader — ready to flash |
| Debugging | OpenOCD running for this slot — GDB clients can connect; RFC2217 proxy stopped (FR-024) or running (FR-025/026) |

State transitions:

| From | To | Trigger |
|------|----|---------|
| Absent | Idle | Hotplug add + proxy start |
| Idle | Absent | Hotplug remove |
| Idle | Flashing | External RFC2217 client connects (esptool) |
| Flashing | Idle | Client disconnects, proxy restarts via hotplug |
| Idle | Resetting | `POST /api/serial/reset` — stops proxy, opens direct serial, sends DTR/RTS |
| Resetting | Idle | Reset complete, proxy restarts via hotplug |
| Idle | Monitoring | `POST /api/serial/monitor` — reads serial via RFC2217 (non-exclusive) |
| Monitoring | Idle | Pattern matched or timeout expired |
| Idle | Flapping | 6+ hotplug events in 30s |
| Flapping | Recovering | Active recovery started (USB unbind) |
| Recovering | Download Mode | GPIO recovery succeeds (BOOT held LOW) |
| Recovering | Idle | No-GPIO rebind succeeds (device stable) |
| Recovering | Flapping | No-GPIO rebind fails (flapping resumes, up to 4 retries) |
| Download Mode | Idle | `POST /api/serial/release` (BOOT released, EN pulsed) |
| Flapping | Idle | Cooldown expires passively (fallback) |
| Idle | Debugging | `POST /api/debug/start` — starts OpenOCD (FR-024/025/026) |
| Debugging | Idle | `POST /api/debug/stop` — stops OpenOCD, restarts proxy |

**WiFi Service (wlan0):**

| State | Description |
|-------|-------------|
| Idle | wlan0 not in use for testing |
| Captive | wlan0 joined DUT's portal AP as STA (Pi at 192.168.4.x, DUT at 192.168.4.1) |
| AP | wlan0 running test AP (Pi at 192.168.4.1, DUT connects at 192.168.4.x) |

State transitions:

| From | To | Trigger |
|------|----|---------|
| Idle | Captive | `POST /api/wifi/sta_join` to DUT's captive portal AP |
| Captive | Idle | `POST /api/wifi/sta_leave` |
| Idle | AP | `POST /api/wifi/ap_start` |
| Captive | AP | `POST /api/wifi/ap_start` (stops STA, starts AP) |
| AP | Idle | `POST /api/wifi/ap_stop` |
| AP | Captive | `POST /api/wifi/sta_join` (stops AP, joins network) |

**Note:** Serial-interface mode (wlan0 for LAN) is a separate operating mode
that disables the WiFi test service entirely (see §1.4).

---

## 2. Definitions

| Entity | Description |
|--------|-------------|
| **Slot** | One physical connector position on the USB hub |
| **slot_key** | Stable identifier for physical port topology (derived from udev `ID_PATH`) |
| **devnode** | Current tty device path (e.g., `/dev/ttyACM0`) — may change on reconnect |
| **proxy** | RFC2217 server process for a serial device: `plain_rfc2217_server.py` for all devices (direct DTR/RTS passthrough) |
| **seq** (sequence) | Global monotonically increasing counter, incremented on every hotplug event |
| **Mode** | Operating mode: `wifi-testing` (wlan0 = instrument) or `serial-interface` (wlan0 = LAN) |

### Key Principle: Slot-Based Identity

The system keys on physical connector position, NOT on `/dev/ttyACMx`
(changes on reconnect), serial number (two identical boards would conflict),
or VID/PID (not unique).

`slot_key` = udev `ID_PATH` ensures:
- Same physical connector → same TCP port (always)
- Device can be swapped → same TCP port
- Two identical boards → different TCP ports (different slots)

---

## 3. Serial Interface

### FR-001 — Event-Driven Hotplug

**Plug flow:**
1. udev emits `add` event for the serial device
2. udev rule invokes `rfc2217-udev-notify.sh` via `systemd-run --no-block`
3. Notify script sends `POST /api/hotplug` with `{action, devnode, id_path, devpath}`
4. Portal determines `slot_key` from `id_path` (or `devpath` fallback)
5. Portal increments global `seq_counter`, records event metadata on the slot
6. Portal spawns a background thread that acquires the slot lock, waits for the device to settle, then starts the proxy bound to `devnode` on the configured TCP port
7. Slot state becomes `running=true`, `present=true`

**Unplug flow:**
1. udev emits `remove` event
2–4. Same notification path as plug
5. Portal increments `seq_counter`, records metadata
6. Portal stops the proxy process in a **background thread** (non-blocking,
   so the single-threaded HTTP server can immediately process the subsequent
   `add` event from USB re-enumeration)
7. Slot state becomes `running=false`, `present=false`

**USB re-enumeration (esptool reset/flash):**
When esptool performs a watchdog reset or flash operation, the ESP32-C3's
USB-Serial/JTAG controller disconnects and reconnects.  This triggers a
`remove` → `add` hotplug sequence.  The portal handles this automatically:
the proxy is stopped on `remove` and restarted on `add` (with the 2s
ttyACM boot delay).  No manual intervention is required.

**Boot scan:** On startup, portal scans `/dev/ttyACM*` and `/dev/ttyUSB*`,
queries `udevadm info` for each, and starts proxies for any device matching a
configured slot.

### FR-002 — Slot Configuration

Static configuration maps `slot_key` → `{label, tcp_port}`.

Configuration file: `/etc/rfc2217/slots.json`

```json
{
  "slots": [
    {"label": "SLOT1", "slot_key": "platform-3f980000.usb-usb-0:1.1:1.0", "tcp_port": 4001},
    {"label": "SLOT2", "slot_key": "platform-3f980000.usb-usb-0:1.3:1.0", "tcp_port": 4002},
    {"label": "SLOT3", "slot_key": "platform-3f980000.usb-usb-0:1.4:1.0", "tcp_port": 4003}
  ]
}
```

### FR-003 — Serial API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/devices | List all slots with status |
| POST | /api/hotplug | Receive udev hotplug event (add/remove) |
| POST | /api/start | Manually start proxy for a slot |
| POST | /api/stop | Manually stop proxy for a slot |
| GET | /api/info | Pi IP, hostname, slot counts |
| POST | /api/serial/reset | Reset device via DTR/RTS (FR-008) |
| POST | /api/serial/monitor | Read serial output with pattern match (FR-009) |

**GET /api/devices** returns:

```json
{
  "slots": [
    {
      "label": "SLOT1",
      "slot_key": "platform-...-usb-0:1.1:1.0",
      "tcp_port": 4001,
      "present": true,
      "running": true,
      "devnode": "/dev/ttyACM0",
      "pid": 1234,
      "url": "rfc2217://esp32-workbench.local:4001",
      "seq": 5,
      "last_action": "add",
      "last_event_ts": "2026-02-05T12:34:56+00:00",
      "last_error": null,
      "flapping": false,
      "state": "idle"
    }
  ],
  "host_ip": "esp32-workbench.local",
  "hostname": "esp32-workbench.local"
}
```

**POST /api/hotplug** body: `{action, devnode, id_path, devpath}`.

**POST /api/start** body: `{slot_key, devnode}`.

**POST /api/stop** body: `{slot_key}`.

### FR-004 — Serial Traffic Logging

- Serial traffic is observable via RFC2217 clients (e.g. pyserial).

### FR-005 — Web Portal (Serial Section)

- Display all 3 slots (always visible, even if empty)
- Show slot status: RUNNING / PRESENT / EMPTY
- Show current devnode and PID when running
- Copy RFC2217 URL to clipboard (hostname and IP variants)
- Start/stop individual slots
- Display connection examples

### FR-006 — ESP32-C3 Native USB-Serial/JTAG Support

ESP32-C3 (and ESP32-S3) chips with native USB use a built-in USB-Serial/JTAG
controller that maps to `/dev/ttyACM*` on Linux (CDC ACM class).  This differs
fundamentally from UART bridge chips (CP2102, CH340 → `/dev/ttyUSB*`) in how
DTR/RTS signals are interpreted.

#### 6.1 USB-Serial/JTAG Signal Mapping

| Signal | GPIO | Function |
|--------|------|----------|
| DTR | GPIO9 | Boot strap: DTR=1 → GPIO9 LOW → **download mode** |
| RTS | CHIP_EN | Reset: RTS=1 → chip held in **reset** |

The Linux `cdc_acm` kernel driver asserts **both DTR=1 and RTS=1** in
`acm_port_activate()` on every port open.  This puts the chip into download
mode during the boot-sensitive phase.

#### 6.2 Proxy Selection

The portal uses `plain_rfc2217_server.py` for **all** device types:

| devnode | Device Type | Server |
|---------|-------------|--------|
| `/dev/ttyACM*` | Native USB (CDC ACM) | `plain_rfc2217_server.py` |
| `/dev/ttyUSB*` | UART bridge (CP2102/CH340) | `plain_rfc2217_server.py` |

`plain_rfc2217_server.py` passes DTR/RTS directly to the serial port — esptool
on the client side implements the correct reset sequences for each chip type.

#### 6.3 Controlled Boot Sequence (plain_rfc2217_server.py)

When `plain_rfc2217_server.py` opens the serial port, it performs a controlled
boot sequence to ensure the chip boots in SPI mode (not download mode):

```python
ser = serial.serial_for_url(port, do_not_open=True, exclusive=False)
ser.timeout = 3
ser.dtr = False   # Pre-set: GPIO9 HIGH (SPI boot)
ser.rts = False   # Pre-set: not in reset
ser.open()
# Linux cdc_acm still asserts DTR+RTS on open, but pyserial immediately
# applies the pre-set values in _reconfigure_port()

# Clear HUPCL to prevent DTR assertion on close
attrs = termios.tcgetattr(ser.fd)
attrs[2] &= ~termios.HUPCL
termios.tcsetattr(ser.fd, termios.TCSANOW, attrs)

ser.dtr = False   # GPIO9 HIGH — select SPI boot
time.sleep(0.1)   # Let USB-JTAG controller latch DTR=0
ser.rts = False   # Release reset — chip boots normally
time.sleep(0.1)
```

#### 6.4 Device Settle Check (ttyACM)

For ttyACM devices, `wait_for_device()` checks only that the device node
exists — it does **not** call `os.open()`, because opening the port would
assert DTR/RTS and put the chip into download mode:

```python
def wait_for_device(devnode, timeout=5.0):
    is_native_usb = devnode and "ttyACM" in devnode
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(devnode):
            if is_native_usb:
                return True  # Don't open — avoids DTR reset
            # ttyUSB: probe with open as before
            try:
                fd = os.open(devnode, os.O_RDWR | os.O_NONBLOCK)
                os.close(fd)
                return True
            except OSError:
                pass
        time.sleep(0.1)
    return False
```

#### 6.5 Hotplug Boot Delay (ttyACM)

When a ttyACM device is hotplugged (USB re-enumeration after reset/flash),
the portal delays proxy startup by `NATIVE_USB_BOOT_DELAY_S` (2 seconds)
to allow the chip to boot past the download-mode-sensitive phase before the
proxy opens the serial port:

```python
NATIVE_USB_BOOT_DELAY_S = 2

def _bg_start(s=slot, lk=lock, dn=devnode):
    if dn and "ttyACM" in dn:
        time.sleep(NATIVE_USB_BOOT_DELAY_S)
    with lk:
        # ... start proxy
```

#### 6.6 Reset Types (Core vs System)

| Reset Type | Mechanism | Re-samples GPIO9? | Result on USB-Serial/JTAG |
|------------|-----------|-------------------|---------------------------|
| Core reset | RTS toggle (DTR/RTS sequence) | **No** | Stays in current boot mode |
| System reset | Watchdog timer (RTC WDT) | **Yes** | Boots based on physical pin state |

**Critical:** After entering download mode, only a **system reset** (watchdog)
can return the chip to SPI boot mode.  Core reset (RTS toggle) keeps the chip
in download mode because GPIO9 is not re-sampled.

#### 6.7 Flashing via RFC2217

Flashing works via RFC2217 through `plain_rfc2217_server` for all device
types.  No SSH to the Pi is needed — esptool's DTR/RTS sequences pass
through directly.

**ESP32-C3 (native USB, ttyACM):**

```bash
python3 -m esptool --chip esp32c3 \
  --port "rfc2217://esp32-workbench.local:4001" \
  --before=usb-reset --after=watchdog-reset \
  write_flash 0x10000 firmware.bin
```

**Classic ESP32 (UART bridge, ttyUSB):**

```bash
python3 -m esptool --chip esp32 \
  --port "rfc2217://esp32-workbench.local:4001" \
  --before=default-reset --after=hard-reset \
  write_flash 0x10000 firmware.bin
```

**Key esptool flags by device type:**

| Device | `--before` | `--after` |
|--------|-----------|----------|
| ESP32-C3 (ttyACM, native USB) | `usb_reset` | `watchdog_reset` |
| ESP32-S3 (ttyACM, native USB) | `usb_reset` | `hard_reset` |
| ESP32 (ttyUSB, UART bridge) | `default_reset` | `hard_reset` |

**Note:** A harmless RFC2217 parameter negotiation error may appear at the
end of flashing — the flash and reset still complete successfully.

**Recovering a crash-looping device (native USB):**

When an ESP32-S3 or ESP32-C3 enters a firmware crash loop (continuous panic
reboots with `rst:0xc`), the device keeps re-enumerating on USB.  Despite the
crash loop, `esptool.py --before=usb_reset` can still connect during the brief
window between reboots.  Use `erase_flash` to wipe the bad firmware and stop
the loop:

```bash
esptool.py --port "rfc2217://esp32-workbench.local:<PORT>?ign_set_control" \
  --chip esp32s3 --before=usb_reset erase_flash
```

After erasing, the device boots to an empty flash (prints `invalid header:
0xffffffff` repeatedly) and is ready for a clean reflash.  A serial reset
(`POST /api/serial/reset`) will show `rst:0x15 (USB_UART_CHIP_RESET)` with
`boot:0x28 (SPI_FAST_FLASH_BOOT)`, confirming the device is responsive and
USB DTR/RTS control works.

#### 6.8 RFC2217 Client Best Practices (ttyACM)

When connecting to an ESP32-C3 via RFC2217, the client must prevent DTR
assertion during connection negotiation:

```python
ser = serial.serial_for_url('rfc2217://esp32-workbench.local:4001', do_not_open=True)
ser.baudrate = 115200
ser.timeout = 2
ser.dtr = False   # CRITICAL: prevents download mode
ser.rts = False   # CRITICAL: prevents reset
ser.open()
```

**Never** use `serial.Serial('rfc2217://...')` directly — it opens the port
immediately and the RFC2217 negotiation may toggle DTR/RTS.

### FR-008 — Serial Reset

Reset a device via DTR/RTS signals, providing a clean boot cycle without
requiring SSH access to the Pi.

**Endpoint:** `POST /api/serial/reset`

**Request body:**
```json
{"slot": "SLOT2"}
```

**Procedure:**
1. Stop the RFC2217 proxy for the slot
2. Open direct serial (`/dev/ttyACMx`) with `dtr=False, rts=False`
3. Send DTR/RTS reset pulse: DTR=1, RTS=1 for 50ms, then release both
4. Wait for device to boot — read serial until first output line or 5s timeout
5. Close serial connection
6. Wait `NATIVE_USB_BOOT_DELAY_S` (2s), then restart the proxy (DTR/RTS reset
   does not cause USB re-enumeration, so hotplug won't restart it automatically)

**Response:**
```json
{"ok": true, "output": ["ESP-ROM:esp32c3-api1-20210207", "Boot count: 1"]}
```

**Error:** Returns `{"ok": false, "error": "..."}` if slot not found, device
not present, or serial open fails.

**Used by:** flapping recovery (FR-007), integration tests

### FR-009 — Serial Monitor

Read serial output from a device, optionally waiting for a pattern match.
Uses the RFC2217 proxy (non-exclusive) so the proxy stays running.

**Endpoint:** `POST /api/serial/monitor`

**Request body:**
```json
{"slot": "SLOT2", "pattern": "Boot count", "timeout": 10}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| slot | string | Yes | — | Slot label (e.g. "SLOT2") |
| pattern | string | No | null | Substring to match in serial output |
| timeout | number | No | 10 | Max seconds to wait |

**Procedure:**
1. Connect to the slot's RFC2217 proxy (non-exclusive read)
2. Read serial lines until pattern is matched or timeout expires
3. Return all captured output and match result

**Response (pattern matched):**
```json
{"ok": true, "matched": true, "line": "Boot count: 1", "output": ["ESP-ROM:...", "Boot count: 1"]}
```

**Response (timeout, no pattern):**
```json
{"ok": true, "matched": false, "line": null, "output": ["line1", "line2"]}
```

**Used by:** flapping recovery (FR-007), test verification

### FR-007 — USB Flap Detection & Recovery

When a device enters a boot loop (crash → reboot → crash every ~2-3s), the
Pi sees rapid USB connect/disconnect cycles.  Without protection, the portal
spawns a new proxy thread for every "add" event, and the udev event flood
(246+ disconnects observed) can make a 416MB Pi unreachable via SSH.

#### 7.1 Detection

```python
FLAP_WINDOW_S = 30       # Look at events within this window
FLAP_THRESHOLD = 6       # 6 events in 30s = 3 connect/disconnect cycles
FLAP_COOLDOWN_S = 10     # Cooldown before recovery attempt
FLAP_MAX_RETRIES = 2     # Max no-GPIO recovery attempts
```

Each slot tracks `_event_times[]` — timestamps of recent hotplug events.
When the count within the window exceeds the threshold, the slot enters
`flapping=true` state and active recovery begins immediately.

#### 7.2 USB Unbind — Stopping the Storm

On flap detection, the portal **unbinds the USB device at the kernel level**
by writing the sysfs device name (e.g. `1-1.1.2`) to
`/sys/bus/usb/drivers/usb/unbind`.  This immediately stops the event storm —
no more udev events, no more hotplug notifications.

The slot_key (e.g. `platform-3f980000.usb-usb-0:1.1.2:1.0`) is parsed to
extract the sysfs USB device name using `rfind("usb-")` to skip the
controller name.

While `_recovering=true`, all hotplug events for the slot are **ignored**
(early exit in the handler).  This prevents the unbind's own synthetic udev
remove event from interfering with recovery state.

#### 7.3 Recovery — GPIO Path

For slots with `gpio_boot` and optionally `gpio_en` configured in
`slots.json`, the portal performs automatic GPIO-based recovery:

1. Wait `FLAP_COOLDOWN_S` (10s) for hardware to settle
2. Hold BOOT/GPIO0 LOW via `gpio_boot` pin (forces download mode)
3. Pulse EN/RST via `gpio_en` pin if configured (clean reset)
4. Rebind USB (`/sys/bus/usb/drivers/usb/bind`) — device enumerates
   in download mode (stable, no crash loop)
5. State → `download_mode`; BOOT stays held LOW

The device is now stable in the bootloader.  Flash firmware directly on
the Pi (the RFC2217 proxy is not running in this state):

```bash
ssh pi@esp32-workbench.local "python3 -m esptool --chip esp32s3 --port /dev/ttyACM1 \
  write_flash 0x0 bootloader.bin 0x8000 partition-table.bin \
  0xf000 ota_data_initial.bin 0x20000 app.bin"
```

After flashing, release GPIO and reboot:

```
POST /api/serial/release {"slot": "SLOT1"}
```

This sets BOOT to high-Z (input with pull-up), pulses EN for a clean
reboot, and transitions the slot back to `idle`.

#### 7.4 Recovery — No-GPIO Path

For slots without GPIO pins, the portal uses exponential backoff:

1. Wait fixed `FLAP_COOLDOWN_S` (10s) — corrupt flash won't self-heal,
   so increasing the delay is pointless
2. Clear `_recovering`, rebind USB
3. If flapping resumes → hotplug handler detects → another recovery cycle
4. After `FLAP_MAX_RETRIES` (2) failed attempts → state stays `flapping`
   with error "needs manual intervention"
5. Flash directly on the Pi (`esptool --before=usb_reset write_flash ...`)
6. Once booted, flapping flag auto-clears on next `/api/devices` poll
   (stale events age out of `_event_times` within `FLAP_WINDOW_S`)

#### 7.5 Manual Recovery

```
POST /api/serial/recover {"slot": "SLOT1"}
```

Resets the retry counter and starts a fresh recovery cycle.  Works even
when the slot is not currently flapping.

#### 7.6 API Fields

`/api/devices` exposes per-slot recovery state:

| Field | Type | Description |
|-------|------|-------------|
| `recovering` | bool | USB unbound, recovery thread running |
| `recover_retries` | int | No-GPIO attempt counter (0-2) |
| `has_gpio` | bool | Slot has `gpio_boot` configured |
| `gpio_boot` | int/null | Pi BCM pin for BOOT/GPIO0 |
| `gpio_en` | int/null | Pi BCM pin for EN/RST |

#### 7.7 Slot Configuration

```json
{"label": "SLOT1", "slot_key": "...", "tcp_port": 4001, "gpio_boot": 18, "gpio_en": 17}
```

`gpio_boot` and `gpio_en` are optional per slot.  Slots without them use
the no-GPIO backoff path.

#### 7.8 Web UI

| State | Badge | Visual |
|-------|-------|--------|
| `flapping` | Red "FLAPPING" | Warning + "Retry Recovery" button |
| `recovering` | Amber "RECOVERING" (pulsing) | Progress message |
| `download_mode` | Green "DOWNLOAD MODE" | "Release & Reboot" button |

Polling interval reduced from 2s to 5s to lower load on resource-constrained Pi.

---

## 4. WiFi Service

### FR-010 — API Summary

Complete API for both Serial and WiFi services.  WiFi workbench endpoints (all
except `/api/wifi/mode` and `/api/wifi/ping`) return `{"ok": false, "error":
"WiFi testing disabled (Serial Interface mode)"}` when the system is in
serial-interface mode.

| Method | Endpoint | Description |
|--------|----------|-------------|
| **Serial** | | |
| GET | /api/devices | List all slots with status |
| POST | /api/hotplug | Receive udev hotplug event (add/remove) |
| POST | /api/start | Manually start proxy for a slot |
| POST | /api/stop | Manually stop proxy for a slot |
| GET | /api/info | Pi IP, hostname, slot counts |
| POST | /api/serial/reset | Reset device via DTR/RTS (FR-008) |
| POST | /api/serial/monitor | Read serial output with pattern match (FR-009) |
| **WiFi** | | |
| GET | /api/wifi/ping | Version and uptime |
| GET | /api/wifi/mode | Current operating mode |
| POST | /api/wifi/mode | Switch operating mode |
| POST | /api/wifi/ap_start | Start SoftAP (WiFi state → AP) |
| POST | /api/wifi/ap_stop | Stop SoftAP (WiFi state → Idle) |
| GET | /api/wifi/ap_status | AP status, SSID, channel, stations |
| POST | /api/wifi/sta_join | Join WiFi network as station (WiFi state → Captive) |
| POST | /api/wifi/sta_leave | Disconnect from WiFi network (WiFi state → Idle) |
| GET | /api/wifi/scan | Scan for WiFi networks |
| POST | /api/wifi/http | HTTP relay through Pi's radio |
| GET | /api/wifi/events | Event queue (long-poll supported) |
| POST | /api/wifi/lease_event | Receive dnsmasq lease callback |
| **Human Interaction** | | |
| POST | /api/human-interaction | Block until operator confirms a physical action (FR-017) |
| GET | /api/human/status | Check if a human interaction request is pending |
| POST | /api/human/done | Operator confirms action complete (wakes blocked request) |
| POST | /api/human/cancel | Operator or test script cancels request |
| **GPIO** | | |
| POST | /api/gpio/set | Drive a Pi GPIO pin low/high or release to input (FR-018) |
| GET | /api/gpio/status | Read state of all actively driven GPIO pins (FR-018) |
| **Test Progress** | | |
| POST | /api/test/update | Push test session start, step, result, or end (FR-019) |
| GET | /api/test/progress | Poll current test session state (FR-019) |
| **GDB Debug** | | |
| POST | /api/debug/start | Start OpenOCD for a slot (FR-024/025/026) |
| POST | /api/debug/stop | Stop OpenOCD, release slot/probe (FR-024/025/026) |
| GET | /api/debug/status | Debug state for all slots (FR-024/025/026) |
| GET | /api/debug/group | Slot groups and roles — dual-USB (FR-025) |
| GET | /api/debug/probes | Available debug probes — ESP-Prog (FR-026) |
| **CW Beacon** | | |
| POST | /api/cw/start | Start Morse-keyed GPCLK carrier (FR-023) |
| POST | /api/cw/stop | Stop CW beacon (FR-023) |
| GET | /api/cw/status | Current beacon state (FR-023) |
| GET | /api/cw/frequencies | List achievable GPCLK frequencies in a range (FR-023) |
| **Composite** | | |
| GET | /api/log | Activity log (timestamped entries, filterable with `?since=`) |
| POST | /api/enter-portal | Ensure device is connected to workbench AP — provision via captive portal if needed |

#### Enter-Portal Composite Operation

`POST /api/enter-portal` ensures a DUT is connected to the workbench's WiFi AP.
If the device already has credentials it connects directly.  If not, the
workbench joins the device's captive portal SoftAP, fills in its own AP
credentials, and waits for the device to reboot and connect.

**Request body:**
```json
{"portal_ssid": "iOS-Keyboard-Setup", "ssid": "TestAP", "password": "testpass123"}
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `portal_ssid` | Yes | The device's captive portal SoftAP name |
| `ssid` | Yes | Workbench AP SSID (filled into portal form, used to start AP) |
| `password` | Yes | Workbench AP password (filled into portal form, used to start AP) |

**Procedure:**
1. Ensure the workbench's AP is running with `ssid`/`password` (start it if not)
2. Wait for the DUT to connect to the workbench AP (short timeout)
3. If connected → done (device already has credentials)
4. If not connected → device is in captive portal mode:
   a. Join the DUT's captive portal SoftAP (`portal_ssid`)
   b. Make an HTTP request, follow the captive portal redirect
   c. Parse the portal HTML form, fill in `ssid` and `password`
   d. Submit the form
   e. Disconnect from the DUT's SoftAP
   f. Wait for the DUT to reboot and connect to the workbench AP

Each step is logged to the activity log.  Progress is observable via
`GET /api/log?since=<ts>`.

**Response:** `{"ok": true}` on success; `{"ok": false, "error": "..."}` on
failure (e.g., unable to join SoftAP, portal form not found)

### FR-011 — AP Mode

The Pi's wlan0 runs hostapd + dnsmasq to create a SoftAP:

- **SSID/password/channel** configurable per `POST /api/wifi/ap_start`
- **IP addressing:** AP IP is `192.168.4.1/24`
- **DHCP range:** `192.168.4.2` – `192.168.4.20`, 1-hour leases
- **Station tracking:** dnsmasq calls `wifi-lease-notify.sh` on DHCP events
  (add/old/del), which posts to `POST /api/wifi/lease_event`.  The portal
  maintains an in-memory station table `{mac, ip}` and emits STA_CONNECT /
  STA_DISCONNECT events.
- **AP status** (`GET /api/wifi/ap_status`): returns `{active, ssid, channel, stations[]}`
- Starting AP while AP is already running restarts with new configuration
- AP and STA are mutually exclusive — starting one stops the other

### FR-012 — Captive Mode (STA)

Join an external WiFi network (typically a DUT's captive portal AP) using
wpa_supplicant + DHCP:

- `POST /api/wifi/sta_join` with `{ssid, pass, timeout}`
- Portal writes wpa_supplicant.conf (with `ctrl_interface=` prepended for
  `wpa_cli` compatibility), starts wpa_supplicant, polls `wpa_cli status`
  until `wpa_state=COMPLETED`, then obtains IP via `dhcpcd -1 -4` (or
  `dhclient`/`udhcpc` fallback)
- Stale wpa_supplicant control sockets (`/var/run/wpa_supplicant/wlan0`) are
  cleaned up before each start to prevent "ctrl_iface exists" errors
- Returns `{ip, gateway}` on success; raises error on timeout or no IP
- `POST /api/wifi/sta_leave` disconnects and releases DHCP
- STA and AP are mutually exclusive — starting STA stops the AP

### FR-013 — WiFi Scan

- `GET /api/wifi/scan` uses `iw dev wlan0 scan -u`
- Returns `{networks: [{ssid, rssi, auth}, ...]}` sorted by signal strength
- `auth` is one of: `OPEN`, `WPA`, `WPA2`, `WEP`
- Scan works while AP is running (the AP's own SSID is excluded from results)

### FR-014 — HTTP Relay

Proxy HTTP requests through the Pi's radio so tests can reach devices on the
WiFi side of the network:

- `POST /api/wifi/http` with `{method, url, headers, body, timeout}`
- Request body is base64-encoded; response body is returned base64-encoded
- Returns `{status, headers, body}`
- Works in both AP mode (reaching devices at 192.168.4.x) and STA mode
  (reaching the external network)

### FR-015 — Event System

- Events: `STA_CONNECT` (mac, ip, hostname) and `STA_DISCONNECT` (mac)
- `GET /api/wifi/events` drains the event queue
- Long-poll: `GET /api/wifi/events?timeout=N` blocks up to N seconds if queue
  is empty, returning immediately when an event arrives

### FR-016 — Mode Switching

- `POST /api/wifi/mode` with `{mode, ssid?, pass?}`
- Switching to `serial-interface` requires `ssid` (and optional `pass`);
  stops any active AP/STA, then joins the specified WiFi network via
  wpa_supplicant + DHCP on wlan0
- Switching to `wifi-testing` disconnects wlan0 from WiFi, returns wlan0 to
  instrument duty
- Mode switch failure (e.g., can't join WiFi) reverts to `wifi-testing`
- `GET /api/wifi/mode` returns `{mode}` (and `ssid`, `ip` when in
  serial-interface mode)
- While in serial-interface mode, workbench endpoints (`ap_start`, `ap_stop`,
  `sta_join`, `sta_leave`, `scan`, `http`) return a guard error

### FR-017 — Human Interaction Request

Some test steps require physical actions that cannot be automated — pressing a
button, connecting a cable, power-cycling a device, repositioning an antenna.
The human interaction endpoint lets test scripts request operator assistance via
the web UI and block until the action is confirmed.

**Endpoint:** `POST /api/human-interaction`

**Request body:**
```json
{"message": "Connect the USB cable to port 2 and click Done", "timeout": 120}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| message | string | Yes | — | Free-text instruction displayed to operator |
| timeout | number | No | 120 | Max seconds to wait for confirmation |

**Behaviour:**

1. Server stores the message and creates a `threading.Event`
2. Server blocks the HTTP response on `event.wait(timeout)`
3. Web UI polls `GET /api/human/status` (every 2s via existing refresh loop)
   and shows a pulsing orange modal overlay with the message text
4. Operator performs the action, then clicks **Done** (`POST /api/human/done`)
   or **Cancel** (`POST /api/human/cancel`)
5. Done/Cancel sets the event — the blocked handler wakes and returns immediately
6. If timeout expires before confirmation, handler returns with `timeout: true`

**Response (confirmed):**
```json
{"ok": true, "confirmed": true}
```

**Response (cancelled):**
```json
{"ok": true, "confirmed": false}
```

**Response (timeout):**
```json
{"ok": true, "confirmed": false, "timeout": true}
```

**Concurrency:** Only one request can be pending at a time. A second request
while one is active returns `409 Conflict`. The portal uses
`ThreadingHTTPServer` so the blocked handler does not prevent other API
requests from being served.

**Driver method:**
```python
wt.human_interaction("Press the reset button and click Done", timeout=60)
# Returns True if confirmed, False if cancelled or timed out
```

**Activity log:** Each request, confirmation, cancellation, and timeout is
logged to the activity log.

### FR-018 — GPIO Control

Drive Pi GPIO pins from test scripts to control DUT hardware signals — for
example, holding DUT GPIO 2 low during boot to trigger captive portal mode
without requiring the rapid-reset approach or physical button presses.

**Pin allowlist:** Only these Pi GPIO pins may be controlled:

```
{5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27}
```

Requests for pins outside this set return HTTP 400.

**Pin values:** Only use LOW (`0`) and HIGH (`1`).  Release = drive HIGH.

#### 18.1 Endpoints

**`POST /api/gpio/set`** — Drive a GPIO pin

Request body:
```json
{"pin": 17, "value": 0}
```

| Field | Type | Required | Values | Description |
|-------|------|----------|--------|-------------|
| pin | int | Yes | See allowlist | Pi BCM GPIO pin number |
| value | int | Yes | `0`, `1` | 0 = drive low, 1 = drive high |

Response:
```json
{"ok": true, "pin": 17, "value": 0}
```

**`GET /api/gpio/status`** — Read state of all actively driven pins

Response:
```json
{"ok": true, "pins": {"17": {"direction": "output", "value": 0}}}
```

All driven pins appear in the response.

#### 18.2 Implementation

- **Lazy init:** `gpiod.Chip("/dev/gpiochip0")` is opened on first use
- **Thread-safe:** All GPIO operations are serialized via `_gpio_lock`
- **gpiod v2 API:** Uses `gpiod.line.Direction.OUTPUT`,
  `gpiod.line.Value.ACTIVE`/`INACTIVE`, `request_lines()`, `set_value()`,
  `get_value()`, `release()`
- **Resource management:** Pins remain driven until explicitly changed

#### 18.3 Captive Portal via GPIO

GPIO control provides an alternative approach to triggering captive portal
mode on the DUT (complementary to `POST /api/enter-portal` which handles
the WiFi provisioning flow after the device is already in portal mode):

1. `POST /api/gpio/set` `{"pin": 18, "value": 0}` — hold DUT boot pin (GPIO0) LOW
2. `POST /api/gpio/set` `{"pin": 17, "value": 0}` — pull DUT EN/RST LOW (reset)
3. Wait 100ms, then `POST /api/gpio/set` `{"pin": 17, "value": 1}` — release reset HIGH; DUT boots into portal mode
4. Verify captive portal from serial output (look for `CAPTIVE PORTAL MODE TRIGGERED` or `AP Started:`)
5. `POST /api/gpio/set` `{"pin": 18, "value": 1}` — release boot pin HIGH

The `ok: true` response from `/api/gpio/set` confirms the pin is driven —
there is no need to poll `/api/gpio/status` to verify.

**Driver methods:**
```python
wt.gpio_set(18, 0)           # Hold DUT boot pin (GPIO0) LOW
wt.gpio_set(17, 0)           # Pull EN/RST LOW (reset)
time.sleep(0.1)
wt.gpio_set(17, 1)           # Release reset HIGH — DUT boots into portal mode
# Check serial output for portal confirmation
wt.gpio_set(18, 1)           # Release boot pin HIGH
```

### FR-019 — Test Progress Tracking

Test scripts can push live progress updates to the portal web UI so
operators can monitor test execution without a terminal.

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/test/update | Push session start, step updates, results, or end |
| GET | /api/test/progress | Poll current test session state |

**Session lifecycle:**

1. `POST /api/test/update` with `{spec, phase, total}` — start session
2. `POST /api/test/update` with `{current: {id, name, step, manual}}` — update current test
3. `POST /api/test/update` with `{result: {id, name, result, details}}` — record result (PASS/FAIL/SKIP)
4. `POST /api/test/update` with `{end: true}` — end session

**Driver methods:**
```python
wt.test_start("Modbus Proxy v1.4", "Integration", total=58)
wt.test_step("TC-001", "WiFi Connect", "Joining AP...", manual=False)
wt.test_result("TC-001", "WiFi Connect", "PASS")
wt.test_end()
```

### FR-020 — UDP Log Receiver

ESP32 devices send debug logs over UDP (since their USB port is often
occupied by HID or other functions).  The Pi listens for these UDP log
packets and makes them available through the HTTP API and web UI.

**Configuration:**

| Constant | Value |
|----------|-------|
| UDP_LOG_PORT | `5555` (env: `UDP_LOG_PORT`) |
| UDP_LOG_MAX_LINES | `2000` |

**Behaviour:**

1. Portal spawns a background thread with a UDP socket bound to `0.0.0.0:5555`
2. Each received datagram is decoded as UTF-8, split by newlines
3. Lines are stored in a `collections.deque(maxlen=2000)` with timestamps
   and source IP
4. Lines are also forwarded to the activity log via `log_activity()`
5. The UDP socket thread is daemon — it exits when the portal exits

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/udplog | Retrieve buffered UDP log lines |
| DELETE | /api/udplog | Clear the UDP log buffer |

**GET /api/udplog** query parameters:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| since | float | 0 | Only return lines with timestamp > since |
| source | string | (all) | Filter by source IP address |
| limit | int | 200 | Max lines to return |

**Response:**
```json
{
  "ok": true,
  "lines": [
    {"ts": 1740000000.123, "source": "192.168.0.121", "line": "I (12345) wifi_mgr: Connected"},
    {"ts": 1740000000.456, "source": "192.168.0.121", "line": "I (12346) ble_nus: Client connected"}
  ]
}
```

**Driver methods:**
```python
logs = wt.udplog(since=0, source="192.168.0.121", limit=100)
wt.udplog_clear()
```

**Implementation notes:**
- Thread-safe: deque operations are atomic; timestamp+source stored per entry
- Non-blocking: UDP recv in a loop with 1s timeout for clean shutdown
- ESP32 remote_log.c sends to the configured host:port (default esp32-workbench.local:5555)

### FR-021 — OTA Firmware Repository

The Pi serves firmware binaries over HTTP so ESP32 devices can perform
OTA updates from the local network.  This eliminates the need for
internet access or external hosting during development and testing.

**Configuration:**

| Constant | Value |
|----------|-------|
| FIRMWARE_DIR | `/var/lib/rfc2217/firmware` (env: `FIRMWARE_DIR`) |

**Directory layout:**
```
/var/lib/rfc2217/firmware/
├── ios-keyboard/
│   └── ios-keyboard.bin
├── modbus-proxy/
│   └── modbus-proxy.bin
└── ...
```

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /firmware/`<project>`/`<filename>` | Download firmware binary (used by ESP32 OTA) |
| GET | /api/firmware/list | List all available firmware files |
| POST | /api/firmware/upload | Upload a firmware binary |
| DELETE | /api/firmware/delete | Delete a firmware file |

**GET /firmware/`<project>`/`<filename>`**

Serves the raw binary file with `Content-Type: application/octet-stream`.
This is the URL the ESP32 OTA client points to, e.g.:
```
http://esp32-workbench.local:8080/firmware/ios-keyboard/ios-keyboard.bin
```

Path traversal is rejected (no `..` allowed in project or filename).

**GET /api/firmware/list** response:
```json
{
  "ok": true,
  "files": [
    {"project": "ios-keyboard", "filename": "ios-keyboard.bin", "size": 1048576, "modified": "2026-02-25T10:00:00+00:00"}
  ]
}
```

**POST /api/firmware/upload** body (multipart/form-data):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| project | string | Yes | Project subdirectory name |
| file | file | Yes | The firmware binary |

**Response:**
```json
{"ok": true, "project": "ios-keyboard", "filename": "ios-keyboard.bin", "size": 1048576}
```

**DELETE /api/firmware/delete** body:
```json
{"project": "ios-keyboard", "filename": "ios-keyboard.bin"}
```

**Driver methods:**
```python
files = wt.firmware_list()
wt.firmware_upload("ios-keyboard", "/path/to/ios-keyboard.bin")
wt.firmware_delete("ios-keyboard", "ios-keyboard.bin")
# ESP32 OTA URL: http://esp32-workbench.local:8080/firmware/ios-keyboard/ios-keyboard.bin
```

**End-to-end OTA workflow:**

The workbench supports a complete remote OTA workflow for ESP32 devices
connected to its WiFi AP.  The HTTP relay (`POST /api/wifi/http`) bridges
the LAN and WiFi AP networks, allowing OTA to be triggered from any
client on the LAN.

1. **Upload firmware** to the workbench's OTA repository:
   ```
   POST /api/firmware/upload  (multipart: project=ios-keyboard, file=ios-keyboard.bin)
   ```
2. **Verify** the firmware is downloadable at the serving URL:
   ```
   GET /firmware/ios-keyboard/ios-keyboard.bin
   ```
3. **Trigger OTA** on the ESP32 via the HTTP relay:
   ```
   POST /api/wifi/http  {"method":"POST", "url":"http://192.168.4.15/ota"}
   ```
   The ESP32 must expose a `POST /ota` endpoint that calls `esp_ota_ops`
   to download from `http://esp32-workbench.local:8080/firmware/<project>/<file>.bin`.
4. **Monitor progress** via UDP logs:
   ```
   GET /api/udplog?source=192.168.4.15
   ```
   The ESP32 logs OTA progress (download bytes, partition writes, reboot)
   which the workbench captures on UDP port 5555.

**Prerequisites for the ESP32 device:**
- Connected to the workbench's WiFi AP (via `POST /api/enter-portal` or manual provisioning)
- HTTP server running with a `POST /ota` trigger endpoint
- OTA URL configured to point at the workbench's firmware repository

**Implementation notes:**
- Path traversal protection: reject `..` in both project and filename
- Directory auto-creation: project subdirectory created on first upload
- install.sh creates `/var/lib/rfc2217/firmware` with appropriate permissions
- Binary serving uses chunked reads (8 KB blocks) to avoid loading large
  files into memory

### FR-022 — BLE Proxy

The Pi's onboard Bluetooth radio acts as a BLE Central (client) that can
scan for, connect to, and send commands to BLE peripherals.  This enables
remote control of BLE devices (e.g., sending keystrokes to an ESP32
running the iOS-Keyboard firmware) from test scripts or AI agents via the
HTTP API.

The Pi is a **dumb BLE-to-HTTP bridge** — it handles only scan, connect,
disconnect, status, and raw byte writes.  All higher-level protocol logic
(command encoding, text diffing, chunking) is the responsibility of the
caller.

**Dependencies:**
- `bleak>=0.20.0` (Python async BLE library, uses BlueZ on Linux)
- BlueZ 5.43+ (standard on Raspberry Pi OS)

**Configuration:**

| Constant | Value |
|----------|-------|
| BLE_SCAN_TIMEOUT | `5.0` seconds (env: `BLE_SCAN_TIMEOUT`) |

**State model:**

| State | Description |
|-------|-------------|
| Idle | No BLE activity |
| Scanning | Actively scanning for BLE peripherals |
| Connected | Connected to a BLE peripheral |

State transitions:

| From | To | Trigger |
|------|----|---------|
| Idle | Scanning | `POST /api/ble/scan` |
| Scanning | Idle | Scan completes (timeout) |
| Idle | Connected | `POST /api/ble/connect` |
| Connected | Idle | `POST /api/ble/disconnect` or remote disconnect |

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/ble/scan | Scan for BLE peripherals, return list |
| POST | /api/ble/connect | Connect to a BLE peripheral by address |
| POST | /api/ble/disconnect | Disconnect from current peripheral |
| GET | /api/ble/status | Connection state and device info |
| POST | /api/ble/write | Write raw bytes to a GATT characteristic |

**POST /api/ble/scan** body (optional):
```json
{"timeout": 5.0, "name_filter": "iOS-Keyboard"}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| timeout | float | 5.0 | Scan duration in seconds |
| name_filter | string | (none) | Only return devices whose name contains this string |

**Response:**
```json
{
  "ok": true,
  "devices": [
    {"address": "1C:DB:D4:84:58:CC", "name": "iOS-Keyboard", "rssi": -45}
  ]
}
```

**POST /api/ble/connect** body:
```json
{"address": "1C:DB:D4:84:58:CC"}
```

**Response:**
```json
{
  "ok": true,
  "address": "1C:DB:D4:84:58:CC",
  "name": "iOS-Keyboard",
  "services": [
    {
      "uuid": "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
      "characteristics": [
        {"uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e", "properties": ["write", "write-without-response"]},
        {"uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e", "properties": ["notify"]}
      ]
    }
  ]
}
```

**POST /api/ble/disconnect** — no body required.

**Response:**
```json
{"ok": true}
```

**GET /api/ble/status** response:
```json
{
  "ok": true,
  "state": "connected",
  "address": "1C:DB:D4:84:58:CC",
  "name": "iOS-Keyboard"
}
```

States: `"idle"`, `"scanning"`, `"connected"`.

**POST /api/ble/write** body:
```json
{"characteristic": "6e400002-b5a3-f393-e0a9-e50e24dcca9e", "data": "024865 6c6c6f", "response": true}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| characteristic | string | Yes | Target GATT characteristic UUID |
| data | string | Yes | Hex-encoded bytes to write |
| response | bool | No (default true) | Use write-with-response (true) or write-without-response (false) |

**Response:**
```json
{"ok": true, "bytes_written": 6}
```

**Error responses:**

| Condition | HTTP | Response |
|-----------|------|----------|
| Not connected | 409 | `{"ok": false, "error": "not connected"}` |
| Already connected | 409 | `{"ok": false, "error": "already connected to 1C:DB:D4:84:58:CC"}` |
| Device not found | 404 | `{"ok": false, "error": "device not found"}` |
| Write failed | 500 | `{"ok": false, "error": "write failed: ..."}` |
| Invalid hex data | 400 | `{"ok": false, "error": "invalid hex data"}` |

**Driver methods:**
```python
devices = wt.ble_scan(timeout=5.0, name_filter="iOS-Keyboard")
info = wt.ble_connect("1C:DB:D4:84:58:CC")
status = wt.ble_status()
wt.ble_write("6e400002-b5a3-f393-e0a9-e50e24dcca9e", bytes([0x02]) + b"Hello")
wt.ble_disconnect()
```

**Implementation notes:**
- `ble_controller.py` runs its own `asyncio` event loop in a background
  thread (bleak is async, portal is sync)
- Module-level lock (`_lock`) serializes all BLE operations
- Connection state tracked in module globals: `_client`, `_address`, `_name`
- Disconnect callback updates state automatically on remote disconnect
- Scan results are ephemeral (not cached)
- Only one BLE connection at a time (Raspberry Pi hardware limitation
  with single radio)

### FR-023 — CW Beacon (GPCLK Morse Transmitter)

Generate a Morse-keyed RF carrier on the Pi's GPIO using the BCM2835 hardware
clock generator.  Designed for direction finder testing on the 80m amateur band
(3.5–4.0 MHz).  No additional hardware required — a wire antenna on the GPIO
pin is sufficient for short-range radiation.

#### 23.1 Principle

The BCM2835 has hardware clock generators (GPCLK) that produce square waves
from PLLD (500 MHz) divided by an integer.  Morse keying switches the GPIO
pin function between ALT0 (clock output) and INPUT (high-Z) — the oscillator
runs continuously, giving clean on/off keying with no phase glitches.

#### 23.2 Available Pins

| GPIO | Physical Pin | Clock |
|------|:------------:|-------|
| 5 | 29 | GPCLK1 |
| 6 | 31 | GPCLK2 |

**Note:** GPIO 5 and 6 are shared with the gpiod-based GPIO control (FR-018).
Do not use both CW beacon and `POST /api/gpio/set` on the same pin
simultaneously.

#### 23.3 Frequency Selection

Frequencies are determined by integer division of PLLD (500 MHz).  Only
discrete frequencies are achievable — no fractional divider is used, so the
output is jitter-free but the frequency resolution is ~25–30 kHz in the 80m
band.

Representative 80m band frequencies:

| Divider | Frequency (MHz) |
|---------|-----------------|
| 125 | 4.000 |
| 130 | 3.846 |
| 135 | 3.704 |
| 139 | 3.597 |
| 140 | 3.571 |
| 142 | 3.521 |

Use `GET /api/cw/frequencies?low=&high=` to list all achievable frequencies
in any range.

#### 23.4 Morse Timing

PARIS standard: 50 dit-lengths per word.  Dit duration = 1.2 / WPM seconds.

| Element | Duration |
|---------|----------|
| Dit | 1 unit |
| Dah | 3 units |
| Inter-element gap | 1 unit |
| Inter-character gap | 3 units |
| Inter-word gap | 7 units |

WPM is configurable from 1 to 60.

#### 23.5 Endpoints

**`POST /api/cw/start`** — Start CW beacon

Request body:
```json
{"pin": 5, "freq": 3571000, "message": "VVV DE TEST", "wpm": 12, "repeat": true}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| freq | int | Yes | — | Target frequency in Hz (snapped to nearest integer divider) |
| message | string | Yes | — | Morse message text |
| wpm | int/float | No | 15 | Words per minute (PARIS), 1–60 |
| pin | int | No | 5 | GPIO pin (5 = GPCLK1, 6 = GPCLK2) |
| repeat | bool | No | true | Loop message continuously |

Response:
```json
{"ok": true, "pin": 5, "freq_hz": 3571428.57, "divider": 140, "message": "VVV DE TEST", "wpm": 12, "repeat": true}
```

`freq_hz` is the actual output frequency (may differ from requested `freq`
due to integer divider snapping).

**`POST /api/cw/stop`** — Stop CW beacon.  No body required.

**`GET /api/cw/status`** — Current beacon state (active, pin, freq_hz,
divider, message, wpm, repeat).

**`GET /api/cw/frequencies?low=&high=`** — List all achievable integer-divider
frequencies in a range.  Defaults to 3.5–4.0 MHz.

#### 23.6 Implementation

- **`cw_beacon.py`**: Standalone module imported by portal.py
- **Register access**: `/dev/mem` mmap to GPIO and clock manager registers
  (requires root — portal runs as root via systemd).  Peripheral base is
  auto-detected from `/proc/device-tree/soc/ranges` (works on all Pi models:
  BCM2835 = `0x20000000`, BCM2837/Pi Zero 2 W = `0x3F000000`)
- **Keying method**: GPIO function select toggle (ALT0 ↔ INPUT) — clock
  generator runs continuously, pin connects/disconnects
- **Thread model**: Single daemon thread per beacon; starting a new beacon
  stops the previous one
- **Shutdown**: Clock generator stopped and pin released to INPUT on stop or
  portal shutdown

#### 23.7 Driver Methods

```python
wt.cw_start(freq=3_571_000, message="VVV DE TEST", wpm=12)
wt.cw_status()     # {"active": True, "freq_hz": 3571428.57, ...}
wt.cw_stop()
wt.cw_frequencies(low=3_500_000, high=4_000_000)  # list of {divider, freq_hz}
```

### FR-024 — GDB Debug: USB JTAG (ESP32-C3/S3 Single-Port)

Remote GDB debugging for ESP32-C3 and ESP32-S3 boards that expose a built-in
USB-Serial/JTAG controller on their native USB port.  The same USB cable
already used for serial also carries JTAG — no additional hardware required.

#### 24.1 Principle

ESP32-C3 and ESP32-S3 chips contain a USB-Serial/JTAG controller that
exposes **two USB interfaces** on a single cable:

| USB Interface | Linux Driver | Function |
|---------------|-------------|----------|
| Interface 0 | `cdc_acm` → `/dev/ttyACM*` | Serial console (current RFC2217 proxy) |
| Interface 1 | libusb (userspace) | JTAG debug (OpenOCD) |

OpenOCD communicates with the JTAG interface via libusb, completely
independent of the serial interface.  The portal starts OpenOCD for a slot
and exposes the GDB Remote Serial Protocol (RSP) on a per-slot TCP port.
Remote containers connect GDB to that port — no USB/JTAG drivers needed on
the client side.

#### 24.2 Supported Chips

| Chip | USB JTAG | Condition |
|------|:--------:|-----------|
| ESP32-C3 | Yes | Board must use native USB (not CP2102/CH340 bridge) |
| ESP32-S3 | Yes | Board must use native USB (not CH340 hub bridge) |
| ESP32 (classic) | No | No USB JTAG — use FR-026 (ESP-Prog) |
| ESP32-S2 | No | USB-OTG only, no built-in JTAG controller |

**Note:** Some S3 boards (e.g. boards with built-in CH340 USB hub) route
USB through a UART bridge chip instead of the S3's native USB-Serial/JTAG
controller.  These boards appear as VID `1a86` (QinHeng) rather than
`303a` (Espressif) and do NOT support USB JTAG.  Only boards where the
S3's native USB D+/D- lines connect directly to the USB connector expose
the JTAG interface.

#### 24.3 Chip Auto-Detection

All chips with native USB-Serial/JTAG share the same USB PID (`303a:1001`),
so the chip type **cannot** be determined from USB enumeration alone.
However, the JTAG TAP ID read during OpenOCD's scan chain interrogation
uniquely identifies the chip architecture:

| JTAG TAP ID | Manufacturer | Architecture | Chip | Verified |
|-------------|-------------|-------------|------|:---:|
| `0x00005c25` | Espressif (`0x612`) | RISC-V single-core | ESP32-C3 | Yes |
| `0x00010c25` | Espressif (`0x612`) | RISC-V single-core | ESP32-H2 | Yes |
| `0x0000dc25` | Espressif (`0x612`) | RISC-V single-core | ESP32-C6 | Yes |
| `0x120034e5` | Tensilica (`0x272`) | Xtensa dual-core | ESP32-S3 | Yes |

**Auto-detection strategy:** The portal can attempt OpenOCD with a candidate
config.  If the TAP ID mismatches, try the other config.  Alternatively,
accept `chip` as an optional parameter — if omitted, probe both configs.

#### 24.4 USB Interface Layout

The native USB-Serial/JTAG controller exposes three USB interfaces:

| Interface | Class | Linux Driver | Purpose |
|-----------|-------|-------------|---------|
| 0 | CDC-ACM | `cdc_acm` → `/dev/ttyACM*` | Serial console (RFC2217 proxy) |
| 1 | CDC Data | `cdc_acm` | Serial data channel |
| 2 | Vendor Specific | **none** (unclaimed) | JTAG (OpenOCD via libusb) |

**Key finding:** Interface 2 (JTAG) is **not claimed** by any kernel driver.
OpenOCD accesses it directly via libusb without needing `unbind` or
`detach_kernel_driver`.  This means serial (RFC2217) and JTAG (OpenOCD) can
coexist on the same physical USB connection without any driver manipulation.

This differs from the ESP-Prog (FR-026) where the `ftdi_sio` kernel driver
claims both FTDI channels and channel A must be explicitly unbound.

#### 24.5 Software Dependencies

**On the Pi:**
- `esp-openocd` v0.12.0+ — Espressif's fork (not upstream OpenOCD).  Required
  for ESP32 flash drivers, reset sequences, and USB JTAG support.
- **Prebuilt binary:** download `openocd-esp32-linux-arm64-*.tar.gz` from
  [espressif/openocd-esp32 releases](https://github.com/espressif/openocd-esp32/releases).
  The `install.sh` script handles this automatically.
- Installation path: `/usr/local/bin/openocd-esp32`
- Scripts path: `/usr/local/share/openocd-esp32/scripts/`
- Target configs: `board/esp32c3-builtin.cfg`, `board/esp32s3-builtin.cfg`
- **Must pass** `-s /usr/local/share/openocd-esp32/scripts` to OpenOCD

**On the remote container (developer side):**
- `riscv32-esp-elf-gdb` (for C3) or `xtensa-esp32s3-elf-gdb` (for S3)
  — included in ESP-IDF toolchain
- No special drivers or USB access needed — pure TCP connection

#### 24.6 Configuration

| Constant | Default | Env Override | Description |
|----------|---------|-------------|-------------|
| GDB_PORT_BASE | 3333 | `GDB_PORT_BASE` | First GDB RSP port (per-slot: +0, +1, +2) |
| OPENOCD_TELNET_BASE | 4444 | `OPENOCD_TELNET_BASE` | First OpenOCD telnet port |
| OPENOCD_EXE | `/usr/local/bin/openocd-esp32` | `OPENOCD_EXE` | Path to esp-openocd binary |

**Slot configuration** (`slots.json` extension):
```json
{
  "slots": [
    {
      "label": "SLOT1",
      "slot_key": "platform-...",
      "tcp_port": 4001,
      "gdb_port": 3333,
      "openocd_telnet_port": 4444
    }
  ]
}
```

#### 24.7 State Model Extension

New slot state `Debugging` added to the Serial Service state machine:

| State | Description |
|-------|-------------|
| Debugging | OpenOCD running — GDB clients can connect; RFC2217 proxy stopped |

State transitions:

| From | To | Trigger |
|------|----|---------|
| Idle | Debugging | `POST /api/debug/start` — stops proxy, starts OpenOCD |
| Debugging | Idle | `POST /api/debug/stop` — stops OpenOCD, restarts proxy |
| Debugging | Debugging | Hotplug events suppressed (USB re-enumeration during JTAG reset is normal) |

**Mutual exclusion:** A slot in `Debugging` state rejects `serial/reset`,
`serial/monitor`, and `enter-portal` requests.  Flashing via esptool is
blocked — the chip's CPU is under OpenOCD control.

#### 24.8 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/debug/start | Start OpenOCD for a slot, expose GDB port |
| POST | /api/debug/stop | Stop OpenOCD, release slot back to serial |
| GET | /api/debug/status | Debug state for all slots |

**POST /api/debug/start** body:
```json
{"slot": "SLOT1", "chip": "esp32c3"}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| slot | string | Yes | — | Slot label |
| chip | string | Yes | — | Chip type: `esp32c3` or `esp32s3` |

**Response:**
```json
{
  "ok": true,
  "slot": "SLOT1",
  "gdb_port": 3333,
  "telnet_port": 4444,
  "chip": "esp32c3",
  "gdb_target": "target extended-remote esp32-workbench.local:3333"
}
```

**POST /api/debug/stop** body:
```json
{"slot": "SLOT1"}
```

**Response:**
```json
{"ok": true, "slot": "SLOT1"}
```

**GET /api/debug/status** response:
```json
{
  "ok": true,
  "slots": {
    "SLOT1": {"debugging": true, "chip": "esp32c3", "gdb_port": 3333, "pid": 5678},
    "SLOT2": {"debugging": false}
  }
}
```

**Error responses:**

| Condition | HTTP | Response |
|-----------|------|----------|
| Slot not found | 404 | `{"ok": false, "error": "slot not found"}` |
| Device not present | 409 | `{"ok": false, "error": "no device in SLOT1"}` |
| Already debugging | 409 | `{"ok": false, "error": "SLOT1 already in debug mode"}` |
| Not debugging (on stop) | 200 | `{"ok": true}` (idempotent) |
| OpenOCD failed to start | 500 | `{"ok": false, "error": "openocd failed: ..."}` |
| Unsupported chip | 400 | `{"ok": false, "error": "chip 'esp32' has no USB JTAG — use ESP-Prog"}` |

#### 24.9 OpenOCD Lifecycle

**Start sequence:**
1. Validate slot is `Idle` and device is present
2. RFC2217 proxy may remain running (serial and JTAG use separate USB
   interfaces — see §24.4).  Stopping the proxy is optional and depends
   on whether exclusive serial access is needed during debug.
3. Launch `openocd-esp32` as subprocess:
   ```
   openocd-esp32 -s /usr/local/share/openocd-esp32/scripts \
     -f board/{chip}-builtin.cfg \
     -c "gdb port {gdb_port}" \
     -c "telnet port {telnet_port}" \
     -c "bindto 0.0.0.0"
   ```
4. Wait up to 5s for OpenOCD to bind (poll TCP port)
5. Set slot state to `Debugging`, record PID

**Stop sequence:**
1. Send SIGTERM to OpenOCD process
2. Wait up to 5s for exit
3. Set slot state to `Idle`
4. Restart RFC2217 proxy via simulated hotplug

**Hotplug during debug:** USB re-enumeration events (from JTAG-initiated
resets) are logged but do NOT trigger proxy restarts while in `Debugging`
state.  OpenOCD manages USB reconnection internally.

#### 24.10 Serial Console During Debug

**Verified:** Serial console and JTAG debugging coexist on the same physical
USB connection.  The native USB-Serial/JTAG controller exposes serial
(Interface 0, `cdc_acm`) and JTAG (Interface 2, unclaimed) as separate
USB interfaces.  The RFC2217 proxy can remain running while OpenOCD uses
the JTAG interface — developers can see `printf` output alongside GDB.

This eliminates the originally anticipated need to stop the serial proxy
during debug sessions for native USB-Serial/JTAG devices.

#### 24.11 Driver Methods

```python
# Start debug session
info = wt.debug_start("SLOT1", chip="esp32c3")
print(f"GDB port: {info['gdb_port']}")
# → Connect GDB: target extended-remote esp32-workbench.local:3333

# Check status
status = wt.debug_status()

# Stop debug session (restarts RFC2217 proxy)
wt.debug_stop("SLOT1")
```

#### 24.12 IDE Integration (Client Side)

**VS Code (launch.json):**
```json
{
  "type": "cppdbg",
  "request": "launch",
  "program": "${workspaceFolder}/build/project.elf",
  "miDebuggerPath": "riscv32-esp-elf-gdb",
  "miDebuggerServerAddress": "esp32-workbench.local:3333",
  "setupCommands": [
    {"text": "set remote hardware-breakpoint-limit 2"},
    {"text": "monitor reset halt"}
  ]
}
```

**Command-line GDB:**
```bash
riscv32-esp-elf-gdb build/project.elf \
  -ex "target extended-remote esp32-workbench.local:3333" \
  -ex "monitor reset halt"
```

**PlatformIO (platformio.ini):**
```ini
debug_tool = esp-builtin
debug_server =
  # empty — use remote server instead
debug_port = esp32-workbench.local:3333
```

---

### FR-025 — GDB Debug: Dual-USB (ESP32-S3 Two-Port)

Remote GDB debugging for ESP32-S3 boards that break out **both** USB
connectors — USB-OTG and USB-Serial/JTAG.  This is the optimal debug
configuration: serial console, JTAG debugger, and application USB all run
simultaneously with zero contention.

#### 25.1 Principle

The ESP32-S3 has two independent USB controllers:

| USB Port | Controller | Hub Port | Function |
|----------|-----------|----------|----------|
| USB-Serial/JTAG | Dedicated debug | SLOT*n* | Serial console (RFC2217) + JTAG (OpenOCD) |
| USB-OTG | Full-speed peripheral | SLOT*n*-APP | Application USB (HID, CDC, MSC, etc.) |

Both ports plug into the Pi's USB hub, consuming **two hub ports per DUT**.
The serial/JTAG port runs RFC2217 AND OpenOCD simultaneously because they
use separate USB endpoints.  The OTG port provides the DUT's actual USB
function (e.g., HID keyboard, CDC serial, mass storage).

#### 25.2 Key Advantage: No Contention

Unlike FR-024 (single-port), the RFC2217 proxy does NOT need to stop during
debugging.  All three functions coexist:

| Function | USB Port | Simultaneous |
|----------|----------|:---:|
| Serial console (RFC2217) | Serial/JTAG | Yes |
| GDB debugging (OpenOCD) | Serial/JTAG | Yes |
| Application USB | OTG | Yes |

This means:
- `printf` debugging and GDB breakpoints work at the same time
- Test scripts can interact with the DUT's USB function while debugging
- No state machine changes — the slot stays in `Idle` while OpenOCD runs

#### 25.3 Supported Boards

Only ESP32-S3 boards that break out **both** USB connectors:

| Board | USB-Serial/JTAG | USB-OTG | Dual-USB |
|-------|:---:|:---:|:---:|
| ESP32-S3-DevKitC-1 (v1.1+) | Yes | Yes | Yes |
| ESP32-S3-DevKitM-1 | Yes | No | No |
| Custom boards with both ports | Yes | Yes | Yes |

ESP32-C3 boards do not have USB-OTG — they have only one USB port.

#### 25.4 Slot Pairing

Two hub ports belong to the same DUT.  Configuration uses a `slot_group`:

```json
{
  "slots": [
    {
      "label": "SLOT1",
      "slot_key": "platform-...-usb-0:1.1:1.0",
      "tcp_port": 4001,
      "gdb_port": 3333,
      "openocd_telnet_port": 4444,
      "group": "DUT1",
      "role": "debug"
    },
    {
      "label": "SLOT1-APP",
      "slot_key": "platform-...-usb-0:1.2:1.0",
      "tcp_port": 4002,
      "group": "DUT1",
      "role": "application"
    }
  ]
}
```

The `group` field links the two slots.  The `role` field identifies which
USB port is which:
- `debug` — USB-Serial/JTAG port (serial + JTAG)
- `application` — USB-OTG port (DUT's USB function)

#### 25.5 Endpoints

Same endpoints as FR-024 (`/api/debug/start`, `/api/debug/stop`,
`/api/debug/status`), plus:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/debug/group | Show slot groups and their roles |

**POST /api/debug/start** — same as FR-024.  The portal automatically
identifies the `debug`-role slot within the group.

**GET /api/debug/group** response:
```json
{
  "ok": true,
  "groups": {
    "DUT1": {
      "debug": {"label": "SLOT1", "tcp_port": 4001, "gdb_port": 3333, "present": true},
      "application": {"label": "SLOT1-APP", "tcp_port": 4002, "present": true}
    }
  }
}
```

#### 25.6 OpenOCD Lifecycle

Same as FR-024 §24.7, except:
- The RFC2217 proxy is **NOT stopped** when OpenOCD starts (serial and JTAG
  coexist on separate USB endpoints)
- Slot state remains `Idle` — no `Debugging` state needed
- OpenOCD is tracked as a parallel process alongside the RFC2217 proxy

#### 25.7 Application USB Port

The application USB port (SLOT*n*-APP) appears as whatever USB device class
the DUT firmware implements.  Common cases:

| DUT USB Class | Linux Device | Workbench Use |
|---------------|-------------|---------------|
| CDC-ACM (serial) | `/dev/ttyACM*` | Second RFC2217 proxy (data channel) |
| HID (keyboard/mouse) | `/dev/hidraw*` | Capture HID reports |
| MSC (mass storage) | `/dev/sd*` | Mount filesystem |
| Custom vendor | — | Raw USB via libusb |

The RFC2217 proxy on the APP slot proxies CDC-ACM output.  For non-serial
USB classes, the portal does not proxy — the application port is available
for direct use or future extensions.

#### 25.8 Driver Methods

```python
# Discover slot groups
groups = wt.debug_groups()
dut1 = groups["DUT1"]
print(f"Debug serial: rfc2217://...:{dut1['debug']['tcp_port']}")
print(f"App USB: rfc2217://...:{dut1['application']['tcp_port']}")

# Start debug (serial proxy stays running)
info = wt.debug_start("SLOT1", chip="esp32s3")

# Now you have all three simultaneously:
#   - Serial console via RFC2217 on port 4001
#   - GDB via port 3333
#   - App USB via RFC2217 on port 4002

wt.debug_stop("SLOT1")
```

#### 25.9 Hub Port Planning

The Pi Zero 2 W has a single USB 2.0 port driving an external hub.  With
dual-USB boards consuming 2 ports each:

| Hub Ports | DUTs | Remaining |
|-----------|------|-----------|
| 3-port hub | 1 DUT + 1 port for USB Ethernet | None |
| 4-port hub | 1 DUT + USB Ethernet + 1 spare | — |
| 7-port hub | 3 DUTs + USB Ethernet | None |

A larger hub is recommended for dual-USB debugging.

---

### FR-026 — GDB Debug: ESP-Prog External Probe

Remote GDB debugging using an ESP-Prog (FT2232H) external debug probe for
**any ESP32 variant** — including the classic ESP32 which has no USB JTAG.
The probe connects to the DUT's JTAG pins via a ribbon cable and to the Pi's
USB hub for OpenOCD control.

#### 26.1 Principle

The ESP-Prog is Espressif's reference debug probe based on the FTDI FT2232H
dual-channel chip:

| Channel | Function |
|---------|----------|
| Channel A | JTAG (TCK, TDI, TDO, TMS) |
| Channel B | UART (TX, RX) — optional serial console |

The probe plugs into the Pi's USB hub and connects to the DUT via a 10-pin
JTAG header or individual wires.  OpenOCD uses the `ftdi` driver with
ESP-Prog-specific configuration.

**Key advantage:** Serial and JTAG are on completely separate physical
connections — the DUT's USB serial (RFC2217) and the probe's JTAG operate
simultaneously with zero contention.

#### 26.2 Supported Chips

All ESP32 variants with accessible JTAG pins:

| Chip | JTAG Pins (TCK/TDI/TDO/TMS) | Notes |
|------|------------------------------|-------|
| ESP32 (classic) | 13 / 12 / 15 / 14 | Conflicts with SD card interface; GPIO12 is a strapping pin |
| ESP32-C3 | 4 / 5 / 6 / 7 | Cannot use USB JTAG and pin JTAG simultaneously |
| ESP32-S2 | 39 / 40 / 41 / 42 | — |
| ESP32-S3 | 39 / 40 / 41 / 42 | Prefer USB JTAG (FR-024) unless pins are already wired |
| ESP32-C6 | 4 / 5 / 6 / 7 | Same as C3 |
| ESP32-H2 | 4 / 5 / 6 / 7 | Same as C3 |

**Requirement:** The DUT board must expose the JTAG pins on a header or
test points.  Many production modules do not — check the board's schematic.

#### 26.3 Hardware Setup

| Component | Description |
|-----------|-------------|
| ESP-Prog | ~$15, Espressif reference probe (FT2232H-based) |
| JTAG cable | 10-pin ribbon or 4 jumper wires (TCK, TDI, TDO, TMS + GND) |
| USB cable | ESP-Prog → Pi USB hub (consumes 1 hub port) |

**Wiring (ESP-Prog JTAG header to DUT):**

| ESP-Prog Pin | Signal | DUT Pin (varies by chip) |
|-------------|--------|--------------------------|
| 1 | VDD (3.3V) | 3.3V (optional, for probe power sensing) |
| 2 | TMS | Chip-specific (see §26.2) |
| 3 | GND | GND |
| 4 | TCK | Chip-specific |
| 5 | GND | GND |
| 6 | TDO | Chip-specific |
| 7 | GND | GND |
| 8 | TDI | Chip-specific |
| 9 | GND | GND |
| 10 | NC | — |

#### 26.4 Software Dependencies

**On the Pi:**
- `esp-openocd` — same binary as FR-024
- Target configs: `board/esp32-wrover-kit-1.8v.cfg` (classic ESP32),
  `interface/ftdi/esp32_devkitj_v1.cfg` (ESP-Prog interface), etc.
- `libftdi1` and `libudev-dev` for FTDI device access
- udev rule for non-root FTDI access (or run OpenOCD as root)

#### 26.5 Configuration

The ESP-Prog is configured as a **shared resource** — not tied to a specific
slot.  The portal tracks which slot's DUT is connected to the probe.

```json
{
  "debug_probes": [
    {
      "label": "PROBE1",
      "type": "esp-prog",
      "usb_serial": "FT2232H-A",
      "interface_config": "interface/ftdi/esp32_devkitj_v1.cfg"
    }
  ]
}
```

| Constant | Default | Description |
|----------|---------|-------------|
| PROBE_GDB_PORT | 3333 | GDB RSP port for the probe |
| PROBE_TELNET_PORT | 4444 | OpenOCD telnet port for the probe |

#### 26.6 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/debug/start | Start OpenOCD via ESP-Prog for a slot |
| POST | /api/debug/stop | Stop OpenOCD, release probe |
| GET | /api/debug/status | Debug state (probe and slot info) |
| GET | /api/debug/probes | List available debug probes |

**POST /api/debug/start** body:
```json
{"slot": "SLOT1", "chip": "esp32", "probe": "PROBE1"}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| slot | string | Yes | — | Slot label (identifies which DUT) |
| chip | string | Yes | — | Chip type: `esp32`, `esp32c3`, `esp32s3`, etc. |
| probe | string | No | first available | Probe label |

**Response:**
```json
{
  "ok": true,
  "slot": "SLOT1",
  "probe": "PROBE1",
  "chip": "esp32",
  "gdb_port": 3333,
  "telnet_port": 4444,
  "gdb_target": "target extended-remote esp32-workbench.local:3333"
}
```

**GET /api/debug/probes** response:
```json
{
  "ok": true,
  "probes": [
    {"label": "PROBE1", "type": "esp-prog", "in_use": false, "slot": null}
  ]
}
```

#### 26.7 OpenOCD Lifecycle

**Start sequence:**
1. Validate probe is available and slot has a device
2. **Unbind channel A from `ftdi_sio`** — the Linux kernel claims both
   FT2232H channels as serial ports.  Channel A (JTAG) must be released
   to libusb before OpenOCD can use it:
   ```bash
   echo '{bus}-{port}:1.0' > /sys/bus/usb/drivers/ftdi_sio/unbind
   ```
   Channel B (UART, `/dev/ttyUSB1`) remains bound for optional serial use.
3. Launch OpenOCD:
   ```
   openocd-esp32 -s /usr/local/share/openocd-esp32/scripts \
     -f interface/ftdi/esp32_devkitj_v1.cfg \
     -f target/esp32.cfg \
     -c "gdb port 3333" \
     -c "telnet port 4444" \
     -c "bindto 0.0.0.0"
   ```
4. Wait up to 5s for OpenOCD to bind
5. Mark probe as in-use, record slot assignment

**Stop sequence:**
1. SIGTERM → OpenOCD
2. Rebind channel A to `ftdi_sio` (restore `/dev/ttyUSB0`)
3. Release probe, clear slot assignment

**Key difference from FR-024:** The RFC2217 proxy is NOT stopped.  The probe
uses the JTAG pins, not the USB serial connection.  Serial console remains
available throughout the debug session.

#### 26.8 Simultaneous Serial + Debug

This is a primary advantage of the ESP-Prog approach:

| Connection | Path | Available During Debug |
|-----------|------|:---:|
| Serial console | USB → RFC2217 → ttyACM/ttyUSB | Yes |
| GDB debugger | ESP-Prog → JTAG pins → OpenOCD → TCP | Yes |
| esptool flash | USB → RFC2217 → ttyACM/ttyUSB | No (CPU halted at breakpoint) |

Developers can see `printf` output in the serial console while
single-stepping through code in GDB.

#### 26.9 Classic ESP32 JTAG Caveats

**GPIO12 strapping pin:** On the classic ESP32, JTAG TDI is GPIO12, which
is also the flash voltage selection strapping pin.  If GPIO12 is HIGH at
boot, the chip configures 1.8V flash — which causes a crash on boards with
3.3V flash.

**Mitigations:**
- Burn the `VDD_SDIO` eFuse to force 3.3V flash (permanent, one-time)
- Use `openocd -c "reset_config none"` to prevent OpenOCD from toggling
  signals during connection
- Ensure the probe's TDI line is LOW or floating at DUT power-up

**JTAG eFuse:** On some ESP32 variants, the JTAG interface can be
permanently disabled by burning the `JTAG_DISABLE` eFuse.  Production-fused
chips cannot be debugged regardless of probe.

#### 26.10 Driver Methods

```python
# List probes
probes = wt.debug_probes()

# Start debug via ESP-Prog (serial stays running)
info = wt.debug_start("SLOT1", chip="esp32", probe="PROBE1")

# Serial + debug coexist:
wt.serial_monitor("SLOT1", pattern="WiFi connected", timeout=10)
# Meanwhile: GDB connected on port 3333

wt.debug_stop("SLOT1")
```

#### 26.11 Compatible Alternatives to ESP-Prog

| Probe | Chip | OpenOCD Driver | JTAG Speed | Notes |
|-------|------|---------------|-----------|-------|
| ESP-Prog | FT2232H | `ftdi` | 20 MHz | Reference probe, recommended |
| Generic FT2232H board | FT2232H | `ftdi` | 20 MHz | Requires custom `ftdi_vid_pid` |
| FT232H (single-channel) | FT232H | `ftdi` | 20 MHz | No UART channel |
| Segger J-Link | — | `jlink` | 15 MHz | Expensive but very reliable |
| Tigard | FT2232H | `ftdi` | 20 MHz | Multi-protocol, open-source |

All alternatives use the same portal API — only the OpenOCD interface config
changes.

---

## 5. Web Portal

The portal serves a single-page HTML UI at `GET /` (port 8080):

- **Serial slot cards** — one card per configured slot showing label, status
  badge (RUNNING/PRESENT/EMPTY), devnode, PID, and copyable RFC2217 URL
- **WiFi Workbench section** — mode toggle (WiFi-Testing / Serial Interface),
  AP status (SSID, channel, station count), and mode-specific information
- **Mode toggle** — clicking "Serial Interface" prompts for SSID/password;
  clicking "WiFi-Testing" switches back immediately
- **Activity Log** — scrollable log panel showing timestamped entries for
  hotplug events, WiFi workbench operations (sta_join, sta_leave, scan, HTTP
  relay), and enter-portal sequence steps.  Entries are categorised (info,
  ok, error, step) with colour coding.  "Enter Captive Portal" button
  triggers `POST /api/enter-portal` to connect to a DUT's captive portal
  SoftAP and submit WiFi credentials.  "Clear" button resets the display.  Log is polled every
  2 seconds via `GET /api/log?since=<last_ts>`.
- **Human interaction modal** — full-screen dark overlay with pulsing orange
  border, shown when a test script posts a human interaction request.
  Displays the operator instruction text with Done and Cancel buttons.
  Polled via `GET /api/human/status` as part of the auto-refresh cycle.
- **Test progress panel** — shown when a test session is active.  Displays
  spec name, phase, progress bar, current test step, and completed results
  (PASS/FAIL/SKIP with colour badges).  Polled via `GET /api/test/progress`.
- **Auto-refresh** — every 2 seconds via `setInterval`, fetches
  `/api/devices`, `/api/wifi/mode`, `/api/wifi/ap_status`, `/api/log`,
  `/api/human/status`, and `/api/test/progress`
- **Title** — shows `{hostname} — Serial Portal` when hostname is available

---

## 6. Non-Functional Requirements

### 6.1 Must Tolerate

| Scenario | How Handled |
|----------|-------------|
| `/dev/ttyACM0` → `/dev/ttyACM1` renaming | slot_key unchanged (based on physical port) |
| Duplicate udev events | API idempotency, per-slot locking |
| "Remove after add" races (USB reset) | Per-slot locking serializes operations; sequence counter aids diagnostics |
| Two identical boards | Different slot_keys (different physical connectors) |
| Hub/Pi reboot | Static config preserves port assignments; boot scan starts proxies |

### 6.2 Determinism

- Same physical connector → same TCP port (always)
- Configuration survives reboots
- No dynamic port assignment

### 6.3 Reliability

- Portal API must be idempotent
- Actions serialized per slot (threading.Lock)
- Stale events prevented via per-slot locking; sequence counter for observability

### 6.4 WiFi Mutual Exclusivity

- AP and STA are mutually exclusive — starting one stops the other
- Mode guard prevents workbench endpoints from running in serial-interface mode;
  guarded endpoints return HTTP 200 with `{"ok": false, "error": "WiFi testing
  disabled (Serial Interface mode)"}`

### 6.5 Edge Cases

| Case | Behavior |
|------|----------|
| Two identical boards | Works — different slot_keys (different physical connectors) |
| Device re-enumeration (USB reset) | Per-slot locking serializes add/remove; background thread restart is safe |
| Duplicate events | Idempotency prevents flapping |
| Unknown slot_key | Portal tracks the slot (present, seq) but does not start a proxy; logged for diagnostics |
| Hub topology changed | Must re-learn slots and update config |
| Dual-USB hub board | Board exposes onboard hub with JTAG + UART interfaces — occupies two slots (see §6.6) |
| Device not ready | Settle checks with timeout, then fail with `last_error` |
| ttyACM DTR trap | `wait_for_device()` skips `os.open()` for ttyACM; proxy uses controlled boot sequence (FR-006) |
| Boot loop (USB flapping) | Portal auto-recovers: unbinds USB, enters download mode via GPIO (FR-007). For slots without GPIO: exponential backoff with 4 retries. Manual trigger: `POST /api/serial/recover` |
| ESP32-C3 stuck in download mode | Run esptool on Pi with `--after=watchdog-reset` to trigger system reset (FR-006.6) |
| udev PrivateNetwork blocking curl | udev runs RUN+ handlers in a network-isolated sandbox (`PrivateNetwork=yes`). Direct `curl` to localhost silently fails. Fix: wrap the notify script with `systemd-run --no-block` in the udev rule so it runs outside the sandbox. |

### 6.6 Dual-USB Hub Boards

Some ESP32-S3 development boards contain an **onboard USB hub** that exposes
two USB interfaces through a single cable:

| Interface | USB ID | Purpose | Slot role |
|-----------|--------|---------|-----------|
| USB-Serial/JTAG | Espressif `303a:1001` | Flashing (esptool), DTR/RTS reset | **JTAG slot** |
| USB-to-UART bridge | e.g. CH340 `1a86:55d3`, CP2102 `10c4:ea60` | UART0 console output | **UART slot** |

These boards occupy **two slots** in the workbench configuration because the hub
presents two independent `ttyACM` (or `ttyUSB`) devices with distinct `ID_PATH`
values.  Both paths share a common hub parent — e.g. `usb-0:1.1.2:1.0` and
`usb-0:1.1.4:1.0` both descend from the hub at `usb-0:1.1`.

**Identifying which slot is which:**

```bash
# On the Pi — check each ttyACM device:
udevadm info -q property /dev/ttyACM0 | grep ID_SERIAL
# "Espressif" → JTAG slot (flash via this slot's RFC2217 URL)
# "1a86", "CH340", "CP210x" → UART slot (serial console output here)
```

**Operational rules for dual-USB hub boards:**

1. **Flashing:** always use the JTAG slot's RFC2217 URL with esptool
2. **Serial console (monitor/reset):** use the UART slot — this is where
   `ESP_LOGI` output appears when `CONFIG_ESP_CONSOLE_UART_DEFAULT=y`
3. **Serial reset via JTAG slot:** sends DTR/RTS signals through the
   USB-Serial/JTAG controller, which triggers the onboard auto-download
   circuit (reset + boot mode select).  This resets the chip but the
   resulting boot output appears on the UART slot, not the JTAG slot
4. **GPIO control:** these boards typically have GPIO0/EN connected to the
   onboard auto-download circuit, so external Pi GPIO wiring for reset/boot
   mode may not be needed — DTR/RTS on the JTAG slot suffices

**Slot configuration example:**

```json
{
  "slots": [
    {"label": "SLOT1", "slot_key": "platform-3f980000.usb-usb-0:1.1.2:1.0", "tcp_port": 4001},
    {"label": "SLOT2", "slot_key": "platform-3f980000.usb-usb-0:1.1.4:1.0", "tcp_port": 4002}
  ]
}
```

Where SLOT1 is the JTAG interface and SLOT2 is the UART bridge.  Label
convention: append `-jtag` and `-uart` to the label when documenting for
clarity.

### 6.7 GPIO Control Probe — Auto-Detecting Board Capabilities

Not all boards have their EN/BOOT pins wired to the Pi's GPIO headers.
Dual-USB hub boards have an onboard auto-download circuit that handles
reset and boot mode via DTR/RTS on the USB-Serial/JTAG interface, making
external GPIO wiring unnecessary.  Single-USB boards **may or may not**
have GPIO wires connected.

The workbench can auto-detect whether a board responds to Pi GPIO control
using a two-step probe:

#### Probe Algorithm

**CRITICAL:** Only use LOW (`0`) and HIGH (`1`) on EN and BOOT pins.  Release = drive HIGH.

```
Step 1: Try GPIO-based download mode entry
  1a. Drive Pi GPIO18 LOW (BOOT pin)
  1b. Wait 1 second (let pin settle)
  1c. Drive Pi GPIO17 LOW (EN/RST — assert reset)
  1d. Wait 200ms
  1e. Drive Pi GPIO17 HIGH (release reset — ESP32 samples BOOT pin now)
  1f. Wait 500ms
  1g. Drive Pi GPIO18 HIGH (release BOOT)
  1h. Monitor slot serial output for 3 seconds
  1i. Check for USB disconnect/reconnect in dmesg or boot mode in serial:
      - USB re-enumeration or "DOWNLOAD" boot mode → GPIO controls this board ✓
      - No USB event and no output → GPIO has no effect, go to Step 2

Step 2: Try USB DTR/RTS reset (fallback)
  2a. POST /api/serial/reset on the slot
  2b. Check boot output:
      - Got output with rst type indicating hardware reset → USB reset works
      - No output → slot may be wrong type or device not responding
```

#### Interpreting Results

| GPIO probe result | USB reset result | Conclusion |
|-------------------|-----------------|------------|
| DOWNLOAD mode | — | **GPIO-controlled board** — Pi GPIOs are wired to EN/BOOT |
| No effect | Hardware reset output | **USB-controlled board** — no GPIO wiring; use DTR/RTS via serial reset |
| No effect | No output | **No control available** — check wiring, or board may be on a different slot |
| DOWNLOAD mode | Also works | GPIO wired AND USB works — prefer USB (less invasive) |

#### Key Indicators in Serial Output

- **Reset reason (`rst:`)**: `0x1` = power-on, `0x3` = software, `0xc` = RTC watchdog/panic,
  `0x15` = USB_UART_CHIP_RESET (DTR/RTS hardware reset)
- **Boot mode (`boot:`)**: `0x23` or `0x03` = DOWNLOAD mode (GPIO probe succeeded),
  `0x28` or `0x29` = SPI_FAST_FLASH_BOOT (normal boot)

#### Caveats

1. **Only use LOW (`0`) and HIGH (`1`) on EN/BOOT pins.**  Release = drive HIGH.
2. **Firmware crash loops** produce continuous `rst:0xc` resets that can mask a
   GPIO-triggered reset.  For reliable probing, first erase flash
   (`esptool.py erase_flash`) so the board sits idle in bootloader, or flash
   known-good firmware that boots cleanly.
3. **Dual-USB hub boards** always respond to USB DTR/RTS on the JTAG slot.
   The GPIO probe will show no effect on these boards (GPIOs not connected
   to the onboard auto-download circuit).
4. The probe only needs to be run once per physical board — the result is
   stable and can be cached in the slot configuration.

---

## 7. Test Cases

### 7.1 Serial Tests

| ID | Name | Pass Criteria |
|----|------|---------------|
| TC-001 | Plug into SLOT3 | SLOT3 shows `running=true`, `devnode` set, `tcp_port=4003` within 5 s |
| TC-002 | Unplug from SLOT3 | SLOT3 shows `running=false`, `devnode=null` within 2 s |
| TC-003 | Replug into SLOT3 | SLOT3 `running=true`, same `tcp_port=4003`, devnode may differ |
| TC-004 | Two identical boards | Both running on different TCP ports (4001, 4002) |
| TC-005 | USB reset race | No "stuck stopped" state; per-slot locking serializes events |
| TC-006 | Devnode renaming | Original device still on SLOT1's port (4001) after renumbering |
| TC-007 | Boot persistence | Same slots get same ports after reboot |
| TC-008 | Unknown slot | Portal logs "unknown slot_key", no crash |

### 7.2 WiFi Workbench Tests

Tests are implemented in `pytest/test_instrument.py` and run via:
```
pytest test_instrument.py --wt-url http://<pi-ip>:8080
```

Add `--run-dut` to include tests that require a WiFi device under test.

| ID | Name | Category | Requires DUT |
|----|------|----------|:------------:|
| WT-100 | Ping response | Basic Protocol | No |
| WT-104 | Rapid commands | Basic Protocol | No |
| WT-200 | Start AP | SoftAP | No |
| WT-201 | Start open AP | SoftAP | No |
| WT-202 | Stop AP | SoftAP | No |
| WT-203 | Stop when not running | SoftAP | No |
| WT-204 | Restart AP new config | SoftAP | No |
| WT-205 | AP status when running | SoftAP | No |
| WT-206 | AP status when stopped | SoftAP | No |
| WT-207 | Max SSID length (32) | SoftAP | No |
| WT-208 | Channel selection | SoftAP | No |
| WT-300 | Station connect event | Station Events | Yes |
| WT-301 | Station disconnect event | Station Events | Yes |
| WT-302 | Station in AP status | Station Events | Yes |
| WT-303 | IP matches event | Station Events | Yes |
| WT-400 | Join open network | STA Mode | Yes |
| WT-401 | Join WPA2 network | STA Mode | Yes |
| WT-402 | Wrong password | STA Mode | Yes |
| WT-403 | Nonexistent SSID | STA Mode | No |
| WT-404 | Leave STA | STA Mode | Yes |
| WT-405 | AP stops during STA | STA Mode | Yes |
| WT-500 | GET request | HTTP Relay | Yes |
| WT-501 | POST with body | HTTP Relay | Yes |
| WT-502 | Custom headers | HTTP Relay | Yes |
| WT-503 | Connection refused | HTTP Relay | No* |
| WT-504 | Request timeout | HTTP Relay | No* |
| WT-505 | Large response | HTTP Relay | Yes |
| WT-506 | HTTP via STA mode | HTTP Relay | Yes |
| WT-600 | Scan finds networks | WiFi Scan | No |
| WT-601 | Scan returns fields | WiFi Scan | No |
| WT-602 | Own AP excluded | WiFi Scan | No |
| WT-603 | Scan while AP running | WiFi Scan | No |

| WT-700 | Human interaction confirm | Human Interaction | No |
| WT-701 | Human interaction cancel | Human Interaction | No |
| WT-702 | Human interaction timeout | Human Interaction | No |
| WT-703 | Concurrent request rejected | Human Interaction | No |
| WT-800 | GPIO set low | GPIO Control | No |
| WT-801 | GPIO set high | GPIO Control | No |
| WT-802 | GPIO release to input | GPIO Control | No |
| WT-803 | GPIO status shows active pins | GPIO Control | No |
| WT-804 | GPIO disallowed pin rejected | GPIO Control | No |
| WT-805 | GPIO invalid value rejected | GPIO Control | No |
| WT-806 | GPIO captive portal trigger | GPIO Control | Yes |
| WT-900 | Test progress start session | Test Progress | No |
| WT-901 | Test progress step update | Test Progress | No |
| WT-902 | Test progress result recording | Test Progress | No |
| WT-903 | Test progress end session | Test Progress | No |
| WT-1000 | UDP log receive single line | UDP Log | Yes |
| WT-1001 | UDP log receive from multiple sources | UDP Log | Yes |
| WT-1002 | UDP log filter by source | UDP Log | Yes |
| WT-1003 | UDP log filter by since | UDP Log | Yes |
| WT-1004 | UDP log clear | UDP Log | No |
| WT-1005 | UDP log buffer overflow (>2000 lines) | UDP Log | Yes |
| WT-1100 | Firmware upload | OTA Firmware | No |
| WT-1101 | Firmware list | OTA Firmware | No |
| WT-1102 | Firmware download | OTA Firmware | No |
| WT-1103 | Firmware delete | OTA Firmware | No |
| WT-1104 | Firmware path traversal rejected | OTA Firmware | No |
| WT-1105 | ESP32 OTA from Pi firmware repo | OTA Firmware | Yes |
| WT-1200 | BLE scan finds devices | BLE Proxy | Yes |
| WT-1201 | BLE scan with name filter | BLE Proxy | Yes |
| WT-1202 | BLE connect to device | BLE Proxy | Yes |
| WT-1203 | BLE status shows connected | BLE Proxy | Yes |
| WT-1204 | BLE write to characteristic | BLE Proxy | Yes |
| WT-1205 | BLE disconnect | BLE Proxy | Yes |
| WT-1206 | BLE write when not connected | BLE Proxy | No |
| WT-1207 | BLE double connect rejected | BLE Proxy | Yes |
| WT-1300 | CW beacon start and status | CW Beacon | No |
| WT-1301 | CW beacon stop | CW Beacon | No |
| WT-1302 | CW beacon frequency list | CW Beacon | No |
| WT-1303 | CW beacon invalid pin rejected | CW Beacon | No |
| WT-1304 | CW beacon replaces previous | CW Beacon | No |
| WT-1400 | Debug start (USB JTAG) | Debug: USB JTAG | Yes |
| WT-1401 | Debug stop restores serial | Debug: USB JTAG | Yes |
| WT-1402 | Debug status | Debug: USB JTAG | Yes |
| WT-1403 | Debug reject absent slot | Debug: USB JTAG | No |
| WT-1404 | Debug reject unsupported chip | Debug: USB JTAG | No |
| WT-1405 | Debug reject duplicate start | Debug: USB JTAG | Yes |
| WT-1406 | Hotplug suppressed during debug | Debug: USB JTAG | Yes |
| WT-1500 | Dual-USB group discovery | Debug: Dual-USB | Yes |
| WT-1501 | Debug start with serial coexist | Debug: Dual-USB | Yes |
| WT-1502 | Application USB port accessible | Debug: Dual-USB | Yes |
| WT-1503 | Serial monitor during debug | Debug: Dual-USB | Yes |
| WT-1600 | Probe list | Debug: ESP-Prog | No |
| WT-1601 | Debug start via probe | Debug: ESP-Prog | Yes |
| WT-1602 | Debug stop releases probe | Debug: ESP-Prog | Yes |
| WT-1603 | Serial available during probe debug | Debug: ESP-Prog | Yes |
| WT-1604 | Probe busy rejected | Debug: ESP-Prog | Yes |
| WT-1605 | Classic ESP32 via probe | Debug: ESP-Prog | Yes |

\* WT-503/504 require a running AP (wifi_network fixture) but not a physical DUT.

---

## 8. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-05 | Claude | Initial FSD (serial only) |
| 1.1 | 2026-02-05 | Claude | Implemented serial-based port assignment |
| 1.2 | 2026-02-05 | Claude | Testing complete for serial-based approach |
| 2.0 | 2026-02-05 | Claude | Major rewrite: event-driven slot-based architecture |
| 3.0 | 2026-02-05 | Claude | Portal v3: direct hotplug handling, in-memory seq + locking, systemd-run udev |
| 4.0 | 2026-02-07 | Claude | WiFi Workbench integration: combined Serial + WiFi FSD, two operating modes, appendices for technical details |
| 5.0 | 2026-02-07 | Claude | ESP32-C3 native USB support: FR-006 (ttyACM handling, plain RFC2217 server, controlled boot sequence, USB reset types, flashing via SSH), FR-007 (USB flap detection), updated edge cases and device settle checks |
| 5.1 | 2026-02-08 | Claude | plain_rfc2217_server for ALL devices (ttyACM and ttyUSB); esp_rfc2217_server deprecated; flashing via RFC2217 works for both chip types (no SSH needed); updated proxy selection, flashing docs, deliverables |
| 5.3 | 2026-02-08 | Claude | Activity log system (`GET /api/log`, `POST /api/enter-portal` for captive portal trigger via rapid resets); WiFi workbench fixes (stale wpa_supplicant socket cleanup, `ctrl_interface=` in wpa_passphrase output, `dhcpcd` DHCP client support); activity logging for hotplug events and WiFi workbench operations; activity log UI panel with colour-coded entries |
| 5.2 | 2026-02-08 | Claude | Removed esp_rfc2217_server.py and serial_proxy.py (no longer installed); proxy auto-restart after esptool USB re-enumeration (background stop_proxy, BrokenPipeError fix, curl timeout 10s); FR-004 logging removed; updated deliverables |
| 6.0 | 2026-02-08 | Claude | Service separation — Serial and WiFi as independent services with state models (§1.6); serial reset (FR-008) and serial monitor (FR-009) as first-class API operations; flapping recovery via active reset; WiFi section renamed to WiFi Service with states Idle/Captive/AP; enter-portal rewritten as composite serial operation; consolidated API table (FR-010) |
| 6.1 | 2026-02-09 | Claude | Human interaction request (FR-017): blocking endpoint for test steps requiring physical operator actions; pulsing orange UI modal; ThreadingHTTPServer for concurrent requests; driver `human_interaction()` method; WT-700–703 test cases |
| 6.2 | 2026-02-09 | Claude | GPIO control (FR-018): drive Pi GPIO pins from test scripts to control DUT hardware signals (e.g. hold GPIO 2 low during boot for captive portal trigger); pin allowlist, lazy gpiod init, release-to-input lifecycle; WT-800–806 test cases. Test progress tracking (FR-019): live test session updates pushed to web UI; WT-900–903 test cases |
| 7.0 | 2026-02-25 | Claude | Three new services: UDP log receiver (FR-020) for ESP32 remote debug logs on port 5555; OTA firmware repository (FR-021) for serving .bin files to ESP32 OTA clients; BLE proxy (FR-022) for scan/connect/write to BLE peripherals via HTTP API using bleak. New deliverable: `ble_controller.py`. WT-1000–1207 test cases |
| 7.1 | 2026-03-15 | Claude | Hostname renamed Serial1 → esp32-workbench; all references updated to esp32-workbench.local. UDP discovery beacon added to portal.py (port 5888) — containers can discover the workbench automatically. Skills consolidated from 14 → 9: merged flash skills into `esp-idf-handling` (auto-detects local vs workbench), PIO skills into `esp-pio-handling`, FSD + WiFi tests into `fsd-writer` with 9 test spec libraries (WiFi, captive portal, MQTT, BLE, OTA, USB HID, NVS, watchdog, logging). Removed `esp32-` prefix from workbench service skills. `fsd-writer` renamed from `esp32-fsd-writer` to be project-agnostic |
| 8.0 | 2026-03-27 | Claude | Remote GDB debugging — three variants: FR-024 USB JTAG (C3/S3 single-port, OpenOCD via built-in USB-Serial/JTAG), FR-025 Dual-USB (S3 two-port, serial+JTAG+app USB simultaneously), FR-026 ESP-Prog (external FT2232H probe for all ESP32 variants including classic). New `Debugging` slot state, `debug_controller.py` module, 5 API endpoints, slot groups for dual-USB, probe allocation for ESP-Prog. WT-1400–1605 test cases (18 tests). TASK-130–155 |
| 7.2 | 2026-03-27 | Claude | CW beacon (FR-023): Morse-keyed RF carrier via BCM2835 GPCLK hardware on GPIO 5/6 for direction finder testing; PLLD 500 MHz integer divider for jitter-free 80m band output; PARIS-standard Morse timing 1–60 WPM; cw_beacon.py module; 4 API endpoints; driver methods cw_start/stop/status/frequencies; WT-1300–1304 test cases |

---

## Appendix A: Technical Details

### A.1 Slot Key Derivation

```python
def get_slot_key(udev_env):
    """Derive slot_key from udev environment variables."""
    # Preferred: ID_PATH (stable across reboots)
    if 'ID_PATH' in udev_env and udev_env['ID_PATH']:
        return udev_env['ID_PATH']

    # Fallback: DEVPATH (less stable but usable)
    if 'DEVPATH' in udev_env:
        return udev_env['DEVPATH']

    raise ValueError("Cannot determine slot_key: no ID_PATH or DEVPATH")
```

### A.2 Sequence Counter

The portal owns a single global monotonic `seq_counter` in memory (no files
on disk).  Every hotplug event increments the counter and stamps the affected
slot:

```python
# Module-level state (in portal.py)
seq_counter: int = 0

# Inside _handle_hotplug:
seq_counter += 1
slot["seq"] = seq_counter
slot["last_action"] = action       # "add" or "remove"
slot["last_event_ts"] = datetime.now(timezone.utc).isoformat()
```

The sequence number provides a total ordering of events for diagnostics.
Because the portal processes hotplug requests serially per slot (via per-slot
locks), stale-event races are prevented by locking rather than by comparing
counters.

### A.3 API Idempotency

**POST /api/start semantics:**
- If slot running with same devnode: return OK (no restart)
- If slot running with different devnode: restart cleanly
- If slot not running: start
- Never fails if already in desired state

**POST /api/stop semantics:**
- If slot not running: return OK
- If running: stop
- Never fails if already in desired state

### A.4 Per-Slot Locking

Portal serializes operations per slot using in-memory `threading.Lock` objects:

```python
# Each slot dict holds its own lock (created at config load time)
slot["_lock"] = threading.Lock()

# Usage (e.g., inside hotplug add handler):
with slot["_lock"]:
    stop_proxy(slot)   # stop old proxy if running
    start_proxy(slot)  # start new proxy
```

No file-based locks or `/run/rfc2217/locks/` directory is used.

### A.5 Device Settle Checks

The portal's `start_proxy` function performs settle checks inline (no separate
handler).  It polls the device node before launching the proxy:

```python
def wait_for_device(devnode, timeout=5.0):
    """Wait for device to be usable (called inside portal)."""
    is_native_usb = devnode and "ttyACM" in devnode
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(devnode):
            if is_native_usb:
                return True  # Don't open — avoids DTR reset (see FR-006)
            try:
                fd = os.open(devnode, os.O_RDWR | os.O_NONBLOCK)
                os.close(fd)
                return True
            except OSError:
                pass
        time.sleep(0.1)
    return False
```

**ttyACM devices:** Only checks file existence — `os.open()` is skipped
because the Linux `cdc_acm` driver asserts DTR+RTS on open, which puts
ESP32-C3 native USB devices into download mode (see FR-006.4).

**ttyUSB devices:** Probes with `os.open()` as before — UART bridge chips
are not affected by DTR on open.

If the device does not settle within the timeout, the slot's `last_error` is
set and the proxy is not started.

### A.6 udev Rules

```
# /etc/udev/rules.d/99-rfc2217-hotplug.rules
# Notify portal of USB serial add/remove events.
# systemd-run escapes udev's PrivateNetwork sandbox so curl can reach localhost.

ACTION=="add", SUBSYSTEM=="tty", KERNEL=="ttyACM*", RUN+="/usr/bin/systemd-run --no-block /usr/local/bin/rfc2217-udev-notify.sh %E{ACTION} %E{DEVNAME} %E{ID_PATH} %E{DEVPATH}"
ACTION=="remove", SUBSYSTEM=="tty", KERNEL=="ttyACM*", RUN+="/usr/bin/systemd-run --no-block /usr/local/bin/rfc2217-udev-notify.sh %E{ACTION} %E{DEVNAME} %E{ID_PATH} %E{DEVPATH}"
ACTION=="add", SUBSYSTEM=="tty", KERNEL=="ttyUSB*", RUN+="/usr/bin/systemd-run --no-block /usr/local/bin/rfc2217-udev-notify.sh %E{ACTION} %E{DEVNAME} %E{ID_PATH} %E{DEVPATH}"
ACTION=="remove", SUBSYSTEM=="tty", KERNEL=="ttyUSB*", RUN+="/usr/bin/systemd-run --no-block /usr/local/bin/rfc2217-udev-notify.sh %E{ACTION} %E{DEVNAME} %E{ID_PATH} %E{DEVPATH}"
```

The udev notify script posts a JSON payload to the portal:

```bash
#!/bin/bash
# /usr/local/bin/rfc2217-udev-notify.sh
# Args: ACTION DEVNAME ID_PATH DEVPATH

curl -m 10 -s -X POST http://127.0.0.1:8080/api/hotplug \
  -H 'Content-Type: application/json' \
  -d "{\"action\":\"$1\",\"devnode\":\"$2\",\"id_path\":\"${3:-}\",\"devpath\":\"$4\"}" \
  || true
```

### A.7 WiFi Lease Notify Script

dnsmasq calls this script on DHCP lease events (add/old/del):

```bash
#!/bin/sh
# /usr/local/bin/wifi-lease-notify.sh
# Args: ACTION MAC IP HOSTNAME

curl -s -X POST -H "Content-Type: application/json" \
     -d "{\"action\":\"${1}\",\"mac\":\"${2}\",\"ip\":\"${3}\",\"hostname\":\"${4:-}\"}" \
     --max-time 2 "http://127.0.0.1:8080/api/wifi/lease_event" >/dev/null 2>&1 || true
```

### A.8 systemd Service

The portal runs as a long-lived systemd service.  udev events are delivered
via `systemd-run` and the notify script (see A.6).

```ini
# /etc/systemd/system/rfc2217-portal.service
[Unit]
Description=RFC2217 Portal
After=network.target

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/rfc2217-portal
Restart=on-failure
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### A.9 Network Ports

| Port | Protocol | Service |
|------|----------|---------|
| 8080 | TCP/HTTP | Web portal, REST API, firmware downloads |
| 4001 | TCP/RFC2217 | SLOT1 serial proxy |
| 4002 | TCP/RFC2217 | SLOT2 serial proxy |
| 4003 | TCP/RFC2217 | SLOT3 serial proxy |
| 5555 | UDP | ESP32 debug log receiver |
| 5888 | UDP | Discovery beacon responder |

### A.10 WiFi Configuration Constants

| Constant | Value |
|----------|-------|
| WLAN_IF | `wlan0` (env: `WIFI_WLAN_IF`) |
| AP_IP | `192.168.4.1` |
| AP_NETMASK | `255.255.255.0` |
| AP_SUBNET | `192.168.4.0/24` |
| DHCP_RANGE_START | `192.168.4.2` |
| DHCP_RANGE_END | `192.168.4.20` |
| DHCP_LEASE_TIME | `1h` |
| WORK_DIR | `/tmp/wifi-workbench` |
| VERSION | `1.0.0-pi` |

---

## Appendix B: Slot Learning Workflow

### B.1 Tool: rfc2217-learn-slots

```bash
$ rfc2217-learn-slots
Plug a device into the USB hub connector you want to identify...

Detected device:
  DEVNAME:  /dev/ttyACM0
  ID_PATH:  platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.3:1.0
  DEVPATH:  /devices/platform/scb/fd500000.pcie/.../ttyACM0
  BY-PATH:  /dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.3:1.0

Add this to /etc/rfc2217/slots.json:
  {"label": "SLOT?", "slot_key": "platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.3:1.0", "tcp_port": 400?}
```

### B.2 Initial Setup Procedure

1. Start with empty `slots.json`
2. Plug device into first hub connector
3. Run `rfc2217-learn-slots`, note the `ID_PATH`
4. Add to config as SLOT1 with `tcp_port: 4001`
5. Repeat for each hub connector
6. Restart portal service

---

## Appendix C: Implementation Tasks & Deliverables

### C.1 Tasks

**Serial:**
- [x] TASK-001: Create slot-based configuration loader
- [x] TASK-002: Implement sequence counter in portal
- [x] TASK-003: Implement per-slot locking (threading.Lock)
- [x] TASK-004: Implement POST /api/hotplug endpoint
- [x] TASK-005: Implement device settle checks in start_proxy
- [x] TASK-006: Create rfc2217-udev-notify.sh script
- [x] TASK-007: Create 99-rfc2217-hotplug.rules (systemd-run based)
- [x] TASK-008: Create rfc2217-learn-slots tool
- [x] TASK-009: Update web UI to show slot-based view
- [x] TASK-010: Boot scan for already-plugged devices
- [ ] TASK-011: Test all test cases
- [ ] TASK-012: Deploy to Serial Pi (esp32-workbench.local)

**Serial Services (v6.0):**
- [ ] TASK-050: Implement `POST /api/serial/reset` (FR-008)
- [ ] TASK-051: Implement `POST /api/serial/monitor` (FR-009)
- [ ] TASK-052: Rewrite enter-portal as composite serial operation
- [ ] TASK-053: Update flapping recovery to use serial reset (FR-007.3)

**Native USB (ESP32-C3):**
- [x] TASK-030: Create plain_rfc2217_server.py for ttyACM devices
- [x] TASK-031: Auto-detect ttyACM vs ttyUSB and select proxy server
- [x] TASK-032: Controlled boot sequence in plain_rfc2217_server.py
- [x] TASK-033: Skip os.open() in wait_for_device() for ttyACM
- [x] TASK-034: Add NATIVE_USB_BOOT_DELAY_S hotplug delay for ttyACM
- [x] TASK-035: USB flap detection (FLAP_WINDOW/THRESHOLD/COOLDOWN)
- [x] TASK-036: Flap detection UI (red FLAPPING badge + warning)

**WiFi:**
- [x] TASK-020: Implement wifi_controller.py (AP, STA, scan, relay, events)
- [x] TASK-021: Add WiFi API routes to portal.py
- [x] TASK-022: Implement mode switching (wifi-testing / serial-interface)
- [x] TASK-023: Create wifi-lease-notify.sh for dnsmasq callbacks
- [x] TASK-024: Create esp32_workbench_driver.py (HTTP test driver)
- [x] TASK-025: Create conftest.py + test_instrument.py (WT-xxx tests)
- [x] TASK-026: Add WiFi section to web UI with mode toggle
- [x] TASK-027: Activity log system (deque, `log_activity()`, `GET /api/log`)
- [x] TASK-028: Enter-portal endpoint (`POST /api/enter-portal`, rapid-reset via serial)
- [x] TASK-029: Activity log UI panel with enter-portal button
- [x] TASK-040: WiFi Workbench stale wpa_supplicant socket cleanup
- [x] TASK-041: wpa_passphrase ctrl_interface fix for wpa_cli compatibility

**Human Interaction (v6.1):**
- [x] TASK-060: Implement `POST /api/human-interaction` with blocking Event (FR-017)
- [x] TASK-061: Implement `GET /api/human/status`, `POST /api/human/done`, `POST /api/human/cancel`
- [x] TASK-062: Human interaction modal in web UI (pulsing orange overlay, Done/Cancel)
- [x] TASK-063: Switch to `ThreadingHTTPServer` for concurrent request handling
- [x] TASK-064: Add `human_interaction()` method to `esp32_workbench_driver.py`
- [x] TASK-065: Add `Cache-Control: no-cache` to UI HTML response

**GPIO Control (v6.2):**
- [x] TASK-070: Implement `POST /api/gpio/set` with pin allowlist and gpiod v2 API (FR-018)
- [x] TASK-071: Implement `GET /api/gpio/status` for active pin readback (FR-018)
- [x] TASK-072: Add `gpio_set()` and `gpio_get()` methods to `esp32_workbench_driver.py`
- [ ] TASK-073: Implement WT-800–806 GPIO test cases in `test_instrument.py`

**Test Progress (v6.2):**
- [x] TASK-080: Implement `POST /api/test/update` and `GET /api/test/progress` (FR-019)
- [x] TASK-081: Test progress panel in web UI (progress bar, current step, results)
- [x] TASK-082: Add `test_start/step/result/end()` methods to `esp32_workbench_driver.py`
- [ ] TASK-083: Implement WT-900–903 test progress test cases

**UDP Log Receiver (v7.0):**
- [ ] TASK-090: Implement UDP socket listener thread in portal.py (FR-020)
- [ ] TASK-091: Implement `GET /api/udplog` and `DELETE /api/udplog` endpoints
- [ ] TASK-092: Add `udplog()` and `udplog_clear()` methods to `esp32_workbench_driver.py`
- [ ] TASK-093: Implement WT-1000–1005 UDP log test cases

**OTA Firmware Repository (v7.0):**
- [ ] TASK-100: Create firmware directory and path-safe file serving (FR-021)
- [ ] TASK-101: Implement `GET /firmware/<project>/<filename>` binary serving
- [ ] TASK-102: Implement `GET /api/firmware/list`, `POST /api/firmware/upload`, `DELETE /api/firmware/delete`
- [ ] TASK-103: Add `firmware_list/upload/delete()` methods to `esp32_workbench_driver.py`
- [ ] TASK-104: Update install.sh to create firmware directory
- [ ] TASK-105: Implement WT-1100–1105 firmware test cases

**BLE Proxy (v7.0):**
- [ ] TASK-110: Create `ble_controller.py` with asyncio event loop thread (FR-022)
- [ ] TASK-111: Implement BLE scan with optional name filter
- [ ] TASK-112: Implement BLE connect/disconnect with state tracking
- [ ] TASK-113: Implement BLE write to GATT characteristic
- [ ] TASK-114: Add BLE API routes to portal.py (`/api/ble/*`)
- [ ] TASK-115: Add `ble_scan/connect/disconnect/status/write()` methods to `esp32_workbench_driver.py`
- [ ] TASK-116: Update install.sh to install bleak dependency
- [ ] TASK-117: Implement WT-1200–1207 BLE proxy test cases

**CW Beacon (v7.2):**
- [x] TASK-120: Implement `cw_beacon.py` (GPCLK register access, Morse engine, thread model)
- [x] TASK-121: Add CW beacon API endpoints to portal.py (`/api/cw/start`, `stop`, `status`, `frequencies`)
- [x] TASK-122: Add `cw_start/stop/status/frequencies()` methods to driver
- [x] TASK-123: Deploy to Pi and verify API endpoints
- [x] TASK-124: Implement WT-1300–1304 CW beacon test cases

**GDB Debug: USB JTAG (v8.0):**
- [x] TASK-130: Install esp-openocd (aarch64) on Pi
- [ ] TASK-131: Add `Debugging` state to slot state machine
- [ ] TASK-132: Implement `POST /api/debug/start` and `POST /api/debug/stop`
- [ ] TASK-133: Implement `GET /api/debug/status`
- [ ] TASK-134: Suppress hotplug proxy restarts during `Debugging` state
- [ ] TASK-135: Add `gdb_port` and `openocd_telnet_port` to slots.json schema
- [ ] TASK-136: Add `debug_start/stop/status()` methods to driver
- [ ] TASK-137: Implement WT-1400–1406 USB JTAG debug test cases

**GDB Debug: Dual-USB (v8.0):**
- [ ] TASK-140: Implement slot grouping (`group` and `role` fields in slots.json)
- [ ] TASK-141: Implement `GET /api/debug/group` endpoint
- [ ] TASK-142: Allow OpenOCD + RFC2217 to coexist on `debug`-role slots
- [ ] TASK-143: Add `debug_groups()` method to driver
- [ ] TASK-144: Implement WT-1500–1503 Dual-USB debug test cases

**GDB Debug: ESP-Prog (v8.0):**
- [ ] TASK-150: Add `debug_probes` configuration to slots.json
- [ ] TASK-151: Implement probe discovery and allocation
- [ ] TASK-152: Implement `GET /api/debug/probes` endpoint
- [ ] TASK-153: OpenOCD launch with FTDI interface config
- [ ] TASK-154: Add `debug_probes()` method to driver
- [ ] TASK-155: Implement WT-1600–1605 ESP-Prog debug test cases

### C.2 Deliverables

| Deliverable | Description |
|-------------|-------------|
| `portal.py` | HTTP server with serial slot management, WiFi API, BLE API, UDP log, firmware serving, process supervision, hotplug handling |
| `wifi_controller.py` | WiFi instrument backend (hostapd, dnsmasq, wpa_supplicant, iw, HTTP relay) |
| `ble_controller.py` | BLE proxy backend (bleak, scan, connect, write to GATT characteristics) |
| `plain_rfc2217_server.py` | RFC2217 server with direct DTR/RTS passthrough (all devices) |
| `rfc2217-udev-notify.sh` | Posts udev events to portal API via curl |
| `wifi-lease-notify.sh` | Posts dnsmasq DHCP lease events to portal API |
| `rfc2217-learn-slots` | CLI tool to discover slot_key for physical connectors |
| `99-rfc2217-hotplug.rules` | udev rules using systemd-run to invoke notify script |
| `rfc2217-portal.service` | systemd unit for the portal |
| `slots.json` | Slot configuration file |
| `esp32_workbench_driver.py` | HTTP driver for running WT-xxx tests against the instrument |
| `conftest.py` | Pytest fixtures (`esp32_workbench`, `wifi_network`, `--wt-url`, `--run-dut`) |
| `test_instrument.py` | Self-tests (WT-100 through WT-1304) |
| `cw_beacon.py` | CW beacon engine — GPCLK hardware clock + Morse keying for DF testing |
| `debug_controller.py` | GDB debug manager — OpenOCD lifecycle, probe allocation, slot state coordination |
