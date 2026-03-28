---
name: esp32-test-harness
description: Manipulate ESP32 DUT during automated tests using the Serial Portal and WiFi Tester infrastructure. Covers serial reset/monitor, NVS erase, captive portal triggering, and WiFi AP provisioning. Use when running tests, resetting the DUT, entering captive portal, provisioning WiFi, or monitoring serial output. Triggers on "test harness", "reset DUT", "captive portal test", "provision WiFi", "NVS erase", "clean state", "test setup".
---

# ESP32 Test Harness

How to manipulate the ESP32-C3 DUT during automated tests using the Serial Portal (192.168.0.87) and WiFi Tester infrastructure.

**Golden rule:** The Serial Portal and MQTT broker are always-on infrastructure. Tests NEVER start, stop, or restart them.

**Driver rule:** Always use `WiFiTesterDriver` from Python — never raw curl. This gives typed responses, proper error handling, and access to the slot `state` field.

---

## Test Execution Protocol

Every test case follows a strict 3-phase execution cycle. The Pi's test progress panel shows the current phase so the operator can follow along.

### The 3 Phases

| Phase | Panel Shows | What Happens |
|-------|-------------|-------------|
| **Preconditions** | `[TC-100] Preconditions: checking DUT reachable...` | Verify or establish each precondition from the test spec. If a precondition fails, try to establish it (e.g. start AP, wait for connection). If unrecoverable, FAIL the test. |
| **Execute** | `[TC-100] Step 2: Publish 3500 to wallbox topic` | Run each step from the test spec's step table, one by one. Check the expected result after each step. |
| **Result** | `TC-100: PASS` or `TC-100: FAIL - wallbox_power was 0` | Record PASS/FAIL/SKIP with details. |

### Panel API Calls

```python
# 1. Start a test session (once, at beginning of phase)
wt.test_start(spec="modbus-proxy-test-spec v4.1", phase="Phase 1: Functional Tests", total=76)

# 2. For each test case — 3 phases:

# Phase: Preconditions
wt.test_step("TC-100", "Basic Startup", "Preconditions: checking slot idle...")
# ... verify/establish preconditions ...
wt.test_step("TC-100", "Basic Startup", "Preconditions: verifying DUT reachable...")

# Phase: Execute
wt.test_step("TC-100", "Basic Startup", "Step 1: Power on ESP32-C3")
# ... perform step 1, check expected result ...
wt.test_step("TC-100", "Basic Startup", "Step 2: Observe serial log")
# ... perform step 2, check expected result ...

# Phase: Result
wt.test_result("TC-100", "Basic Startup", "PASS")
# or
wt.test_result("TC-100", "Basic Startup", "FAIL", "mqtt_connected was false after 15s")

# 3. End the session (once, at end of phase)
wt.test_end()
```

### Execution Rules

1. **Follow the test spec literally.** The test spec document is the script. Execute the preconditions, steps, and pass criteria exactly as written.
2. **One step at a time.** Update the panel before performing each action. The operator should see what's happening in real time.
3. **Preconditions are active.** Don't just check — establish. If the AP isn't running, start it. If NVS needs erasing, erase it. Only fail if the precondition is truly unrecoverable.
4. **Record baselines.** When the test spec says "record X as `Y_before`", capture the value and compare in the result phase.
5. **Never skip the panel update.** Every phase transition and every step must be visible on the panel.
6. **Produce a results document.** After running tests, write results to a markdown file with: test ID, name, result (PASS/FAIL/SKIP), details, and timestamps.
7. **Random test credentials for artificial networks.** When provisioning the DUT onto an isolated test AP, generate a random SSID/password per run. This proves the DUT used the provisioned credentials, not a cached network.
8. **All tests run on the artificial network.** Phase 1 covers all functional tests on the WiFi Tester's artificial network (no dependency on `private-2G` or home infrastructure). Phase 2 is reserved for long-duration / soak tests.

---

## Infrastructure

| Component | Address | Role |
|-----------|---------|------|
| Serial Portal | 192.168.0.87:8080 | RFC2217 serial proxy, WiFi/Serial API |
| DUT WiFi (test AP) | 192.168.4.x | DUT on WiFi Tester AP |
| DUT WiFi (portal) | 192.168.4.1 | DUT in captive portal AP mode |
| MQTT broker | 192.168.4.1:1883 | Mosquitto on Pi (via WiFi Tester AP) |

Slots are tied to physical USB connectors on the Pi, not to devices. **Always discover the DUT slot at runtime** using `wt.get_devices()` — never hardcode a slot label or port number.

### MQTT Broker (mosquitto on Pi)

The Pi at 192.168.0.87 runs a mosquitto MQTT broker. When the WiFi Tester AP is active, the broker is reachable by DUTs on the artificial network at **192.168.4.1:1883**.

| Property | Value |
|----------|-------|
| Host (from DUT on AP) | 192.168.4.1 |
| Host (from home network) | 192.168.0.87 |
| Port | 1883 |
| Username | admin |
| Password | admin |

**Service management (from dev machine):**
```bash
# Check status
ssh pi@192.168.0.87 sudo systemctl status mosquitto

# Restart
ssh pi@192.168.0.87 sudo systemctl restart mosquitto
```

**Quick tests (from dev machine on home network, or any host that can reach the AP):**
```bash
# Publish a test message
mosquitto_pub -h 192.168.4.1 -u admin -P admin -t test -m "hello"

# Subscribe to all topics (verbose)
mosquitto_sub -h 192.168.4.1 -u admin -P admin -t "#" -v
```

**Configuring the DUT to use the Pi broker:**

After WiFi provisioning (DUT connected to the WiFi Tester AP), send a `set_mqtt` command via MQTT to point the DUT at the Pi broker. This eliminates any dependency on home-network infrastructure.

```python
# Example: after DUT connects to test AP, configure its MQTT target
resp = wt.http_post(f"http://{dut_ip}/api/mqtt",
                     json_data={"host": "192.168.4.1", "port": 1883,
                                "user": "admin", "password": "admin"})
```

All functional tests (Phase 1) run entirely on the artificial network — the WiFi Tester AP plus the Pi's mosquitto broker. There is no dependency on `private-2G` or any home-network MQTT broker.

---

## 0. WiFi Tester Driver Setup

All test operations use `WiFiTesterDriver`. Set `PYTHONPATH` to import it:

```python
import sys
sys.path.insert(0, "/tmp/Universal-ESP32-Tester/pytest")
from wifi_tester_driver import WiFiTesterDriver

wt = WiFiTesterDriver("http://192.168.0.87:8080")
```

Or from bash one-liners:

```bash
PYTHONPATH=/tmp/Universal-ESP32-Tester/pytest python3 -c "
from wifi_tester_driver import WiFiTesterDriver
wt = WiFiTesterDriver('http://192.168.0.87:8080')
# ... operations ...
"
```

### Discover DUT Slot

```python
# Find which slot has a device present
devices = wt.get_devices()
dut = next(s for s in devices if s["present"])
SLOT = dut["label"]       # e.g. "SLOT1", "SLOT2", "SLOT3"
PORT = dut["url"]         # e.g. "$PORT"
```

### Driver Methods Reference

**Slot state & devices:**
```python
wt.get_devices()                          # list[dict] — all slots
wt.get_slot(SLOT)                         # dict — single slot by label
wt.wait_for_state(SLOT, "idle", timeout=30)  # poll until state matches
```

**Serial operations:**
```python
wt.serial_reset(SLOT)                     # dict — reset DUT, returns boot output
wt.serial_monitor(SLOT, pattern="WiFi connected", timeout=15)  # dict — wait for pattern
wt.enter_portal(SLOT, resets=3)            # dict — trigger captive portal
```

**WiFi management:**
```python
wt.get_mode()                              # dict — {"mode": "wifi-testing"}
wt.ap_start("TestAP-Modbus", "test12345")  # dict — start test AP
wt.ap_stop()                               # None
wt.ap_status()                             # dict — active, ssid, stations
wt.sta_join("MODBUS-Proxy-Setup", "", timeout=15)  # dict — join AP
wt.sta_leave()                             # None
wt.scan()                                  # dict — nearby networks
```

**HTTP relay (reach DUT on isolated network):**
```python
wt.http_get("http://192.168.4.1/api/status")         # Response
wt.http_post("http://192.168.4.1/api/wifi",
             json_data={"ssid": "TestAP-Modbus", "password": "test12345"})  # Response
```

**GPIO control (drive Pi GPIO pins wired to DUT — look up pin numbers in project FSD):**
```python
wt.gpio_set(pin, 0)       # Drive low
wt.gpio_set(pin, 1)       # Drive high
wt.gpio_set(pin, "z")     # Switch to input with pull-up — ALWAYS do this when done
wt.gpio_get()              # dict — active pins only, e.g. {"pins": {"17": {"direction": "output", "value": 0}}}
```

**Human interaction (for physical actions — cable changes, power cycles):**
```python
wt.human_interaction("Connect the USB cable and click Done", timeout=60)  # bool — blocks until Done/Cancel
```

**Activity log:**
```python
wt.get_log()                               # list[dict] — all entries
wt.get_log(since="2026-02-08T12:00:00")    # list[dict] — entries since timestamp
```

**Test progress panel (3-phase protocol — see "Test Execution Protocol" section):**
```python
wt.test_start(spec, phase, total)          # Start session — spec name, phase name, total test count
wt.test_step(test_id, name, step)          # Update panel — "Preconditions: ...", "Step N: ...", etc.
wt.test_result(test_id, name, result, details="")  # Record PASS/FAIL/SKIP
wt.test_end()                              # End session
```

---

## 1. Slot States

Each slot has an explicit `state` field visible in `get_slot()` and `get_devices()`:

| State | Meaning |
|-------|---------|
| `absent` | No device plugged into this USB slot |
| `idle` | Device present, proxy not running (available for operations) |
| `resetting` | Serial reset or enter-portal in progress |
| `monitoring` | Serial monitor capturing output |
| `flapping` | Device hotplug flapping detected |

### Check state

```python
slot = wt.get_slot(SLOT)
print(f"State: {slot['state']}, Present: {slot['present']}")
```

### Wait for state transition

```python
# Wait for reset to complete
wt.wait_for_state(SLOT, "idle", timeout=30)
```

---

## 2. Serial Operations

### 2.1 Reset DUT (normal boot)

**IMPORTANT:** If a Pi GPIO is wired to a DUT boot-mode pin (e.g. portal button), ensure it is in `"z"` state (input with pull-up) before resetting. This prevents the pin from floating LOW during the DTR/RTS reset pulse.

```python
wt.gpio_set(PI_PIN, "z")             # Input with pull-up — prevents float during reset
result = wt.serial_reset(SLOT)
print(result["output"])
```

The reset API stops the proxy, opens direct serial, sends DTR/RTS reset pulse, captures boot output, then restarts the proxy. Slot state goes `idle` → `resetting` → `idle`.

**JTAG reset (when debugging is active):**
When the workbench has an active OpenOCD session for the slot (auto-started for native USB chips), `serial_reset()` automatically uses JTAG reset instead of DTR/RTS. This avoids USB re-enumeration and flapping. No code changes needed — the API auto-selects the best method.

### 2.2 Monitor serial output

```python
# Read for 5s, no pattern matching
result = wt.serial_monitor(SLOT, timeout=5)
print(result["output"])

# Wait for specific pattern (returns immediately on match)
result = wt.serial_monitor(SLOT, pattern="WiFi connected", timeout=30)
if result["matched"]:
    print(f"Found: {result['line']}")
```

### 2.3 Flash via RFC2217

Flashing uses esptool directly (not through the driver). Get `PORT` from `wt.get_slot()["url"]`:

```bash
# PORT from driver discovery, e.g. "rfc2217://192.168.0.87:4002"

# ESP32-C3 (native USB)
python3 -m esptool --chip esp32c3 \
    --port "$PORT" \
    --before=usb-reset --after=watchdog-reset \
    write_flash 0x10000 firmware.bin

# Full flash (bootloader + partitions + firmware)
python3 -m esptool --chip esp32c3 \
    --port "$PORT" \
    --baud 921600 --before=usb-reset --after=watchdog-reset \
    write_flash --flash_mode dio --flash_size 4MB \
    0x0000 bootloader.bin 0x8000 partitions.bin 0x10000 firmware.bin
```

### 2.4 Known issue: C3 stuck in download mode

```bash
python3 -m esptool --chip esp32c3 \
    --port "$PORT" \
    --before=usb-reset --after=watchdog-reset chip_id
```

Use `--after=watchdog-reset` (NOT `hard-reset`) — system reset re-samples GPIO9.

---

## 3. NVS Erase (Clean State)

```bash
python3 -m esptool --chip esp32c3 \
    --port "$PORT" \
    --before=usb-reset --after=watchdog-reset \
    erase_region 0x9000 0x5000
```

After erase, the DUT resets and boots with:
- WiFi: `private-2G` (from credentials.h) — **only for initial setup, not for tests**
- MQTT: compiled default (see config.h) — reconfigure after WiFi provisioning via MQTT `set_mqtt` command to point at 192.168.4.1
- Boot count: 0
- Debug mode: off

---

## 4. Captive Portal

### 4.1 Trigger captive portal (GPIO — fully automated)

If the Pi has a GPIO wired to the DUT's portal button pin, driving it low during boot triggers captive portal mode — no human, no rapid resets.

**Look up from project FSD/config:** which Pi GPIO pin is wired to which DUT pin, the active level (usually LOW), and the serial output marker that confirms portal mode.

**IMPORTANT:** Always release GPIO back to input (`"z"`) when done. The `ok: true` response from `gpio_set` confirms the pin state — do not poll `gpio_get()` to verify.

```python
# Pin numbers from project FSD — example only, look these up per project
PI_PIN = 17        # Pi BCM pin wired to DUT portal button
PORTAL_MARKER = "CAPTIVE PORTAL MODE TRIGGERED"  # serial output to expect

try:
    wt.gpio_set(PI_PIN, 0)                # Hold DUT portal pin low
    result = wt.serial_reset(SLOT)         # Reset DUT — boots into portal
    assert any(PORTAL_MARKER in line for line in result["output"])
finally:
    wt.gpio_set(PI_PIN, "z")              # Input with pull-up — DUT pin returns to idle
```

**Fallback A** — human operator (if GPIO wiring unavailable):
```python
import threading
human = threading.Thread(target=wt.human_interaction,
    args=("Hold portal button on DUT, then click Done",),
    kwargs={"timeout": 60})
human.start()
wt.serial_reset(SLOT)
result = wt.serial_monitor(SLOT, pattern=PORTAL_MARKER, timeout=15)
assert result["matched"]
human.join()
```

**Fallback B** — rapid resets (firmware with boot-counter portal trigger):
```python
result = wt.enter_portal(SLOT, resets=3)
wt.wait_for_state(SLOT, "idle", timeout=30)
```

### 4.2 Interact with captive portal (via WiFi Tester)

```python
# Join the portal AP
wt.sta_join("MODBUS-Proxy-Setup", "", timeout=15)

# Access portal page
resp = wt.http_get("http://192.168.4.1/")
print(f"Status: {resp.status_code}, Body: {resp.text[:200]}")

# Scan for networks from portal
resp = wt.http_get("http://192.168.4.1/api/scan")
print(resp.json())

# Submit WiFi credentials through portal
resp = wt.http_post("http://192.168.4.1/api/wifi",
                     json_data={"ssid": "TestAP-Modbus", "password": "test12345"})
print(resp.json())

# Leave portal AP
wt.sta_leave()
```

### 4.3 Restore DUT from portal mode

**Option A** — Submit WiFi credentials via portal (see 4.2).

**Option B** — Erase NVS via serial (portal doesn't block serial):
```bash
python3 -m esptool --chip esp32c3 \
    --port "$PORT" \
    --before=usb-reset --after=watchdog-reset \
    erase_region 0x9000 0x5000
```

**Option C** — Wait for portal timeout (5 minutes), DUT reboots automatically.

---

## 5. WiFi AP Management

### 5.1 Start test AP

```python
result = wt.ap_start("TestAP-Modbus", "test12345")
print(f"AP IP: {result['ip']}")
```

### 5.2 Check AP status and connected stations

```python
status = wt.ap_status()
print(f"Active: {status['active']}, SSID: {status['ssid']}")
for sta in status.get("stations", []):
    print(f"  Station: {sta['mac']} @ {sta['ip']}")
```

### 5.3 Stop test AP

```python
wt.ap_stop()
```

### 5.4 Wait for DUT to connect to test AP

```python
# Start AP then wait for DUT station event
wt.ap_start("TestAP-Modbus", "test12345")
evt = wt.wait_for_station(timeout=30)
print(f"DUT connected: {evt}")
```

### 5.5 HTTP relay to DUT on test AP

When DUT is on the WiFi Tester's AP (192.168.4.x), use relay:

```python
# GET
resp = wt.http_get("http://192.168.4.6/api/status")
status = resp.json()
print(f"FW: {status['fw_version']}, Heap: {status['free_heap']}")

# POST
resp = wt.http_post("http://192.168.4.6/api/debug",
                     json_data={"enabled": True})
```

---

## 6. Common Test Workflows

### 6.1 Clean slate then verify

```python
wt = WiFiTesterDriver("http://192.168.0.87:8080")

# Flash + erase NVS (via bash/esptool)
# Then verify via driver:
slot = wt.get_slot(SLOT)
assert slot["state"] == "idle"
assert slot["present"] is True
```

### 6.2 Captive portal test cycle (GPIO — fully automated)

```python
wt = WiFiTesterDriver("http://192.168.0.87:8080")
# Look up pin numbers and markers from project FSD
PI_PIN = ...           # Pi BCM GPIO wired to DUT portal button
PORTAL_MARKER = ...    # Serial output confirming portal mode
PORTAL_SSID = ...      # DUT's portal AP SSID
PORTAL_PASS = ...      # DUT's portal AP password

# 1. Trigger captive portal via GPIO
try:
    wt.gpio_set(PI_PIN, 0)                 # Hold DUT portal pin low
    result = wt.serial_reset(SLOT)          # Reset → boots into portal
    assert any(PORTAL_MARKER in l for l in result["output"])
finally:
    wt.gpio_set(PI_PIN, "z")               # Input with pull-up — DUT pin returns to idle

# 2. Join the portal AP
wt.sta_join(PORTAL_SSID, PORTAL_PASS, timeout=15)

# 3. Test portal page
resp = wt.http_get("http://192.168.4.1/")
assert resp.status_code == 200

# 4. Submit credentials
resp = wt.http_post("http://192.168.4.1/api/wifi",
                     json_data={"ssid": "TestAP", "password": "test12345"})
wt.sta_leave()

# 5. Start test AP and wait for DUT to connect with new credentials
wt.ap_start("TestAP", "test12345")
evt = wt.wait_for_station(timeout=30)
```

### 6.3 WiFi disconnect test cycle

```python
wt = WiFiTesterDriver("http://192.168.0.87:8080")

# 1. DUT on test AP
wt.ap_start("TestAP-Modbus", "test12345")
# (DUT connects via NVS creds)

# 2. Drop the AP
wt.ap_stop()
import time; time.sleep(5)

# 3. Bring AP back
wt.ap_start("TestAP-Modbus", "test12345")

# 4. Wait for reconnection
evt = wt.wait_for_station(timeout=30)
print(f"Reconnected: {evt}")
```

### 6.4 Reset DUT and verify normal boot

```python
wt = WiFiTesterDriver("http://192.168.0.87:8080")

# Single reset (no GPIO held → normal boot)
wt.serial_reset(SLOT)

# Verify normal boot via serial
result = wt.serial_monitor(SLOT, pattern="WiFi connected", timeout=30)
assert result["matched"]
```

---

## 7. State Detection (Serial Lifeline)

**Serial is the lifeline.** Never rely on WiFi/HTTP to check if the C3 is running — WiFi may not be up.

### 7.1 Detect state from serial monitor

```python
result = wt.serial_monitor(SLOT, timeout=5)
output = "\n".join(result.get("output", []))

if "waiting for download" in output:
    print("DOWNLOAD MODE — recover with esptool --after=watchdog-reset")
elif "SPI_FAST_FLASH_BOOT" in output:
    print("RUNNING — normal boot")
else:
    print("UNKNOWN — may need reflash")
```

### 7.2 State table

| Serial output | State | Action needed |
|--------------|-------|---------------|
| `boot:0x7 (DOWNLOAD...)` + `waiting for download` | **Download mode** | Run esptool with `--after=watchdog-reset` |
| `boot:0xc (SPI_FAST_FLASH_BOOT)` + app messages | **Running** | Normal |
| No output at all | **Unknown** | Check baud rate (115200), close stale RFC2217 sessions, try `wt.serial_reset(SLOT)` first. If still silent, reflash with serial-enabled build |

### 7.3 Direct pyserial via RFC2217 (fallback only)

Only use when the driver API is insufficient:

```python
import serial, time
ser = serial.serial_for_url(PORT, do_not_open=True)  # PORT from wt.get_slot()
ser.baudrate = 115200
ser.timeout = 2
ser.dtr = False   # CRITICAL: prevents download mode on C3
ser.rts = False   # CRITICAL: prevents reset
ser.open()
deadline = time.time() + 5
while time.time() < deadline:
    data = ser.read(1024)
    if data:
        print(data.decode('utf-8', errors='replace'), end='', flush=True)
ser.close()
```

---

## 8. GPIO Control

The Serial Portal can drive Pi GPIO pins to control DUT hardware signals (e.g. hold a pin low during boot to trigger a specific mode). GPIO wiring varies per project.

**Before using GPIO:** Read the project's FSD and hardware docs to find:
1. Which Pi BCM pin is wired to which DUT pin
2. The active level (LOW or HIGH) and the DUT's pull-up/pull-down configuration
3. When the DUT samples the pin (boot only? continuous?)
4. The serial output marker that confirms the expected behavior

### 8.1 Pin allowlist

Only these Pi BCM pins can be controlled via the API:
```
{5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26}
```

### 8.2 API

```python
wt.gpio_set(pin, 0)       # Drive low
wt.gpio_set(pin, 1)       # Drive high
wt.gpio_set(pin, "z")     # Switch to input with pull-up
wt.gpio_get()              # Read active pin states (driven pins only)
```

- `ok: true` confirms the operation — do not poll `gpio_get()` to verify.
- Pins released with `"z"` disappear from `gpio_get()` response.

### 8.3 Rules

1. **Release to input when done.** Call `gpio_set(pin, "z")` when the test session is finished.
2. **Use try/finally.** Ensure release even on test failure.
3. **No redundant verification.** Trust the `ok: true` response. Do not read back the pin state after setting it.

### 8.4 Patterns

**Hold during reset (e.g. force a boot mode):**
```python
try:
    wt.gpio_set(pin, 0)               # Hold DUT pin in active state
    result = wt.serial_reset(SLOT)     # Reset DUT — boots with pin held
    # Check result["output"] for expected serial marker
finally:
    wt.gpio_set(pin, "z")             # Input with pull-up when done
```

**Pulse (toggle briefly):**
```python
import time
try:
    wt.gpio_set(pin, 0)
    time.sleep(0.1)
finally:
    wt.gpio_set(pin, "z")
```
