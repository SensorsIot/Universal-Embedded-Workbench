# Logging Test Specification for ESP32 Projects

Standard test cases for ESP32 logging and debug output functionality (serial, UDP, log levels). Copy relevant sections into project FSDs.

---

## 1. Logging Requirements

### 1.1 Serial Logging

| ID | Requirement | Priority |
|----|-------------|----------|
| LOG-001 | Device SHALL output structured log messages via serial (UART/USB) | Must |
| LOG-002 | Log messages SHALL include timestamp and component tag | Should |
| LOG-003 | Device SHALL log boot sequence with firmware version | Must |
| LOG-004 | Device SHALL log all state transitions (WiFi, BLE, MQTT connect/disconnect) | Should |
| LOG-005 | Device SHALL support configurable log levels (ERROR, WARN, INFO, DEBUG) | Should |

### 1.2 UDP Logging

| ID | Requirement | Priority |
|----|-------------|----------|
| LOG-010 | Device SHALL send log messages via UDP to a configurable host:port | Should |
| LOG-011 | UDP logging SHALL work in parallel with serial logging | Must |
| LOG-012 | UDP log destination SHALL be configurable via NVS or captive portal | Should |
| LOG-013 | Device SHALL continue operating normally if UDP target is unreachable | Must |
| LOG-014 | UDP log format SHALL match serial log format | Should |

### 1.3 Strategic Log Points

| ID | Requirement | Priority |
|----|-------------|----------|
| LOG-020 | Device SHALL log WiFi connection events (connect, disconnect, IP assigned) | Must |
| LOG-021 | Device SHALL log MQTT connection events and publish confirmations | Should |
| LOG-022 | Device SHALL log BLE connection and disconnection events | Should |
| LOG-023 | Device SHALL log OTA progress (start, %, complete, error) | Must |
| LOG-024 | Device SHALL log watchdog health check status | Should |
| LOG-025 | Device SHALL log free heap at boot and periodically | Should |
| LOG-026 | Device SHALL log error conditions with sufficient context for diagnosis | Must |

---

## 2. Functional Test Cases

### TC-LOG-100: Serial Boot Log

**Objective**: Verify device outputs structured boot log.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Power on device | Boot sequence starts |
| 2 | Monitor serial output | Firmware version logged |
| 3 | Check log format | Timestamp + tag + message |
| 4 | WiFi connects | Connection event logged |
| 5 | MQTT connects (if applicable) | Connection event logged |
| 6 | Normal operation | Periodic status messages |

**Pass Criteria**: Boot sequence fully logged with correct format.

### TC-LOG-101: UDP Log Delivery

**Objective**: Verify UDP logs reach the configured target.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Configure UDP log target (workbench IP:5555) | Setting saved |
| 2 | Boot device | WiFi connects |
| 3 | Check workbench UDP log endpoint | Boot messages received |
| 4 | Trigger state change (e.g., MQTT connect) | Event logged via UDP |
| 5 | Compare UDP log with serial log | Content matches |

**Pass Criteria**: UDP logs received, format matches serial, all events captured.

### TC-LOG-102: Log Level Filtering

**Objective**: Verify log level configuration filters output correctly.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set log level to ERROR | Only errors shown |
| 2 | Trigger a warning condition | Not logged |
| 3 | Trigger an error condition | Logged |
| 4 | Set log level to DEBUG | All messages shown |
| 5 | Verify verbose output | Debug details visible |
| 6 | Set log level to INFO (default) | INFO and above shown |

**Pass Criteria**: Log level correctly filters output at each setting.

### TC-LOG-103: State Transition Logging

**Objective**: Verify all major state transitions are logged.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Boot device | Boot log with version |
| 2 | WiFi connects | "WiFi connected, IP: x.x.x.x" |
| 3 | MQTT connects | "MQTT connected to broker" |
| 4 | Disconnect WiFi | "WiFi disconnected" |
| 5 | WiFi reconnects | "WiFi reconnected" |
| 6 | BLE client connects | "BLE connected: AA:BB:CC:DD:EE:FF" |
| 7 | BLE client disconnects | "BLE disconnected" |
| 8 | Trigger OTA | "OTA start", progress, "OTA complete" |

**Pass Criteria**: Every state transition produces a log entry.

---

## 3. Edge Case Test Cases

### EC-LOG-200: UDP Target Unreachable

**Objective**: Verify device operates normally when UDP log target is down.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Configure UDP logging to unreachable host | Setting saved |
| 2 | Boot device | Device starts normally |
| 3 | Monitor serial log | Serial logging works |
| 4 | Verify no crash or hang | Device fully operational |
| 5 | Start UDP listener on target | Logs start arriving |

**Pass Criteria**: UDP failure does not affect device operation.

### EC-LOG-201: High-Volume Logging

**Objective**: Verify logging handles rapid message bursts.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set log level to DEBUG | Verbose output |
| 2 | Trigger rapid state changes | Many log messages |
| 3 | Monitor free heap | Stable, no leak |
| 4 | Check serial output | No garbled messages |
| 5 | Check UDP output | Messages delivered (some may drop) |
| 6 | Set log level back to INFO | Normal volume |

**Pass Criteria**: No memory leak, serial output intact, UDP best-effort.

### EC-LOG-202: Log Output During OTA

**Objective**: Verify logging continues during firmware update.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start OTA update | Download begins |
| 2 | Monitor serial during download | Progress logged (10%, 50%, 100%) |
| 3 | Monitor UDP during download | Progress received |
| 4 | OTA completes, device reboots | "OTA complete, rebooting" logged |
| 5 | New firmware boots | Boot log with new version |

**Pass Criteria**: OTA progress visible via both serial and UDP.

### EC-LOG-203: Crash Log Capture

**Objective**: Verify crash information is captured and accessible.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger crash (test firmware or known bug) | Panic handler runs |
| 2 | Monitor serial output | Backtrace printed |
| 3 | Device reboots | Reset reason logged |
| 4 | Check reset reason | "rst:0xc" or panic indicator |
| 5 | Previous crash info logged (if implemented) | Crash context available |

**Pass Criteria**: Crash produces diagnostic output, reset reason distinguishable.

### EC-LOG-204: Log Persistence Across Reboot

**Objective**: Verify log configuration persists.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set log level to DEBUG | Setting saved to NVS |
| 2 | Reboot device | Device restarts |
| 3 | Check log level | Still DEBUG |
| 4 | Set UDP target IP | Setting saved |
| 5 | Reboot | UDP logging to configured target |

**Pass Criteria**: Log settings persist across reboots.

---

## 4. Test Environment Setup

### Required Equipment

- ESP32 device under test
- Serial monitor (idf.py monitor or pio device monitor)
- UDP log receiver (workbench provides this on port 5555)
- Network connectivity for UDP testing

### Workbench Commands

```bash
# View UDP logs from device
curl "http://workbench.local:8080/api/udplog?limit=50"

# View UDP logs filtered by source
curl "http://workbench.local:8080/api/udplog?source=192.168.4.2&limit=20"

# Clear UDP log buffer
curl -X DELETE http://workbench.local:8080/api/udplog

# Serial monitor via workbench
curl -X POST http://workbench.local:8080/api/serial/monitor \
  -H 'Content-Type: application/json' \
  -d '{"slot": "slot-1", "pattern": "ERROR\\|WARN", "timeout": 30}'
```
