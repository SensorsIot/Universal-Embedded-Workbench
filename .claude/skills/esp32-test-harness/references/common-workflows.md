# Common Test Workflows

## Clean slate then verify

```python
wt = WorkbenchDriver("http://192.168.0.87:8080")

# Flash + erase NVS (via bash/esptool)
# Then verify via driver:
slot = wt.get_slot(SLOT)
assert slot["state"] == "idle"
assert slot["present"] is True
```

## Captive portal test cycle (GPIO -- fully automated)

```python
wt = WorkbenchDriver("http://192.168.0.87:8080")
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

## WiFi disconnect test cycle

```python
wt = WorkbenchDriver("http://192.168.0.87:8080")

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

## Reset DUT and verify normal boot

```python
wt = WorkbenchDriver("http://192.168.0.87:8080")

# Single reset (no GPIO held → normal boot)
wt.serial_reset(SLOT)

# Verify normal boot via serial
result = wt.serial_monitor(SLOT, pattern="WiFi connected", timeout=30)
assert result["matched"]
```
