# BLE Test Specification for ESP32 Projects

Standard test cases for ESP32 Bluetooth Low Energy functionality. Copy relevant sections into project FSDs.

---

## 1. BLE Requirements

### 1.1 BLE Advertising & Connection

| ID | Requirement | Priority |
|----|-------------|----------|
| BLE-001 | Device SHALL advertise with a discoverable name | Must |
| BLE-002 | Device SHALL accept BLE connections from authorized clients | Must |
| BLE-003 | Device SHALL support at least one simultaneous BLE connection | Must |
| BLE-004 | Device SHALL disconnect gracefully on timeout or client request | Must |
| BLE-005 | Device SHALL resume advertising after disconnection | Must |
| BLE-006 | Device SHALL log BLE connection and disconnection events | Should |

### 1.2 GATT Services

| ID | Requirement | Priority |
|----|-------------|----------|
| BLE-010 | Device SHALL expose GATT services matching its functional role | Must |
| BLE-011 | GATT characteristics SHALL support read/write/notify as specified | Must |
| BLE-012 | Notifications SHALL be sent within 100 ms of data change | Should |
| BLE-013 | Device SHALL handle invalid GATT writes with appropriate error codes | Must |

### 1.3 Nordic UART Service (NUS)

| ID | Requirement | Priority |
|----|-------------|----------|
| BLE-020 | Device SHALL implement NUS (6E400001-B5A3-F393-E0A9-E50E24DCCA9E) | Must |
| BLE-021 | NUS RX characteristic SHALL accept writes up to MTU size | Must |
| BLE-022 | NUS TX characteristic SHALL send notifications for outgoing data | Must |
| BLE-023 | Device SHALL handle fragmented messages across multiple BLE packets | Should |

### 1.4 BLE Security

| ID | Requirement | Priority |
|----|-------------|----------|
| BLE-030 | Device SHALL support BLE pairing when security is required | Should |
| BLE-031 | Device SHALL reject unauthorized access to protected characteristics | Must |
| BLE-032 | Bonding information SHALL persist across reboots (stored in NVS) | Should |

---

## 2. Functional Test Cases

### TC-BLE-100: BLE Discovery and Connection

**Objective**: Verify device is discoverable and accepts connections.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Power on device | BLE advertising starts |
| 2 | Scan with phone/tool | Device name visible in scan results |
| 3 | Connect to device | Connection established |
| 4 | Enumerate services | Expected GATT services listed |
| 5 | Disconnect | Clean disconnection |
| 6 | Verify advertising resumes | Device visible in scan again |

**Pass Criteria**: Discovery, connection, service enumeration, and reconnection all succeed.

### TC-BLE-101: NUS Data Transfer

**Objective**: Verify bidirectional data transfer via Nordic UART Service.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connect to device | BLE connection established |
| 2 | Subscribe to NUS TX notifications | Notifications enabled |
| 3 | Write test string to NUS RX | Device receives data |
| 4 | Device processes and responds | TX notification received |
| 5 | Send 200-byte payload | Fragmented across BLE packets |
| 6 | Verify complete message received | All fragments reassembled |

**Pass Criteria**: Bidirectional data transfer works, fragmentation handled correctly.

### TC-BLE-102: GATT Read/Write Operations

**Objective**: Verify GATT characteristic read and write operations.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connect to device | Connection established |
| 2 | Read a readable characteristic | Value returned |
| 3 | Write to a writable characteristic | Write acknowledged |
| 4 | Read back written value | Updated value returned |
| 5 | Write invalid data (wrong length/format) | Error response returned |
| 6 | Write to read-only characteristic | Write rejected |

**Pass Criteria**: All GATT operations behave according to characteristic properties.

### TC-BLE-103: BLE Notification Latency

**Objective**: Verify notifications are sent within latency requirements.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connect and subscribe to notifications | Notifications enabled |
| 2 | Trigger data change on device | Notification sent |
| 3 | Measure time from change to notification | < 100 ms |
| 4 | Trigger 10 rapid changes | All notifications received |
| 5 | Verify ordering | Notifications in correct order |

**Pass Criteria**: Notification latency < 100 ms, no lost or reordered notifications.

---

## 3. Edge Case Test Cases

### EC-BLE-200: BLE Disconnect During Data Transfer

**Objective**: Verify system handles mid-transfer disconnection gracefully.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connect to device | BLE connected |
| 2 | Begin sending large payload | Transfer in progress |
| 3 | Force disconnect (walk out of range or kill app) | Connection lost |
| 4 | Check device state | No crash, error logged |
| 5 | Device resumes advertising | Discoverable again |
| 6 | Reconnect and retry | Transfer succeeds |

**Pass Criteria**: No crash, clean recovery, advertising resumes.

### EC-BLE-201: Multiple Rapid Connect/Disconnect Cycles

**Objective**: Verify device handles connection churn without resource leaks.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connect to device | Connected |
| 2 | Immediately disconnect | Disconnected |
| 3 | Repeat 20 times rapidly | All cycles complete |
| 4 | Check free heap | No significant memory loss |
| 5 | Final connect and data transfer | Works normally |

**Pass Criteria**: No memory leak, no crash, device remains functional.

### EC-BLE-202: BLE Range Limits

**Objective**: Verify behavior at BLE range boundary.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connected at 1 m | Stable connection |
| 2 | Move to 5 m | Connection maintained |
| 3 | Move to 10 m | Possible packet loss |
| 4 | Move to 15+ m | Connection may drop |
| 5 | Return to 1 m | Reconnects automatically |

**Pass Criteria**: Graceful degradation, automatic recovery when in range.

### EC-BLE-203: Concurrent BLE and WiFi Operation

**Objective**: Verify BLE and WiFi coexistence on shared radio.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | WiFi connected, BLE advertising | Both active |
| 2 | Connect BLE client | BLE connected, WiFi stable |
| 3 | Transfer data on both channels | Both operate |
| 4 | Heavy WiFi traffic (OTA update) | BLE latency may increase |
| 5 | OTA completes | BLE connection maintained or recovers |

**Pass Criteria**: Both radios functional, no crashes from coexistence.

### EC-BLE-204: BLE Bonding Persistence

**Objective**: Verify bonding survives reboot.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Pair and bond with device | Bonding stored |
| 2 | Reboot device | Device restarts |
| 3 | Reconnect from bonded client | Connection without re-pairing |
| 4 | Factory reset device | Bonding cleared |
| 5 | Reconnect attempt | Pairing required again |

**Pass Criteria**: Bonding persists across reboots, cleared on factory reset.

---

## 4. Test Environment Setup

### Required Equipment

- ESP32 device under test
- BLE-capable phone or computer (nRF Connect recommended)
- BLE sniffer (optional, for packet analysis)
- Serial monitor for device logs

### Monitoring Commands

```bash
# Workbench BLE scan
curl -X POST http://workbench.local:8080/api/ble/scan \
  -H 'Content-Type: application/json' -d '{"timeout": 5}'

# Connect and write via workbench
curl -X POST http://workbench.local:8080/api/ble/write \
  -H 'Content-Type: application/json' \
  -d '{"address": "AA:BB:CC:DD:EE:FF", "service": "6e400001-...", "char": "6e400002-...", "data": "test"}'
```
