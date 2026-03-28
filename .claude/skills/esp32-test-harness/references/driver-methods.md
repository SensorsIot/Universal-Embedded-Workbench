# WiFiTesterDriver Methods Reference

## Slot state & devices

```python
wt.get_devices()                          # list[dict] — all slots
wt.get_slot(SLOT)                         # dict — single slot by label
wt.wait_for_state(SLOT, "idle", timeout=30)  # poll until state matches
```

## Serial operations

```python
wt.serial_reset(SLOT)                     # dict — reset DUT, returns boot output
wt.serial_monitor(SLOT, pattern="WiFi connected", timeout=15)  # dict — wait for pattern
wt.enter_portal(SLOT, resets=3)            # dict — trigger captive portal
```

## WiFi management

```python
wt.get_mode()                              # dict — {"mode": "wifi-testing"}
wt.ap_start("TestAP-Modbus", "test12345")  # dict — start test AP
wt.ap_stop()                               # None
wt.ap_status()                             # dict — active, ssid, stations
wt.sta_join("MODBUS-Proxy-Setup", "", timeout=15)  # dict — join AP
wt.sta_leave()                             # None
wt.scan()                                  # dict — nearby networks
```

## HTTP relay (reach DUT on isolated network)

```python
wt.http_get("http://192.168.4.1/api/status")         # Response
wt.http_post("http://192.168.4.1/api/wifi",
             json_data={"ssid": "TestAP-Modbus", "password": "test12345"})  # Response
```

## GPIO control (drive Pi GPIO pins wired to DUT -- look up pin numbers in project FSD)

```python
wt.gpio_set(pin, 0)       # Drive low
wt.gpio_set(pin, 1)       # Drive high
wt.gpio_set(pin, "z")     # Switch to input with pull-up — ALWAYS do this when done
wt.gpio_get()              # dict — active pins only, e.g. {"pins": {"17": {"direction": "output", "value": 0}}}
```

## Human interaction (for physical actions -- cable changes, power cycles)

```python
wt.human_interaction("Connect the USB cable and click Done", timeout=60)  # bool — blocks until Done/Cancel
```

## Activity log

```python
wt.get_log()                               # list[dict] — all entries
wt.get_log(since="2026-02-08T12:00:00")    # list[dict] — entries since timestamp
```

## Test progress panel (3-phase protocol)

```python
wt.test_start(spec, phase, total)          # Start session — spec name, phase name, total test count
wt.test_step(test_id, name, step)          # Update panel — "Preconditions: ...", "Step N: ...", etc.
wt.test_result(test_id, name, result, details="")  # Record PASS/FAIL/SKIP
wt.test_end()                              # End session
```
