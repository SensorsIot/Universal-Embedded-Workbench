# State Detection (Serial Lifeline)

**Serial is the lifeline.** Never rely on WiFi/HTTP to check if the C3 is running -- WiFi may not be up.

## Detect state from serial monitor

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

## State table

| Serial output | State | Action needed |
|--------------|-------|---------------|
| `boot:0x7 (DOWNLOAD...)` + `waiting for download` | **Download mode** | Run esptool with `--after=watchdog-reset` |
| `boot:0xc (SPI_FAST_FLASH_BOOT)` + app messages | **Running** | Normal |
| No output at all | **Unknown** | Check baud rate (115200), close stale RFC2217 sessions, try `wt.serial_reset(SLOT)` first. If still silent, reflash with serial-enabled build |

## Direct pyserial via RFC2217 (fallback only)

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
