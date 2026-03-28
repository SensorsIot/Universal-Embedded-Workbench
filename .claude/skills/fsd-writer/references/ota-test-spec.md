# OTA Test Specification for ESP32 Projects

Standard test cases for ESP32 Over-The-Air firmware update functionality. Copy relevant sections into project FSDs.

---

## 1. OTA Requirements

### 1.1 OTA Update Mechanism

| ID | Requirement | Priority |
|----|-------------|----------|
| OTA-001 | Device SHALL support firmware update via HTTP download | Must |
| OTA-002 | Device SHALL verify firmware integrity before applying (checksum/signature) | Must |
| OTA-003 | Device SHALL use dual OTA partitions (A/B scheme) | Must |
| OTA-004 | Device SHALL rollback to previous firmware on boot failure | Must |
| OTA-005 | Device SHALL report current firmware version via API or BLE | Should |
| OTA-006 | Device SHALL log OTA progress (download %, verification, apply) | Should |
| OTA-007 | OTA update SHALL be triggerable via HTTP endpoint or BLE command | Must |

### 1.2 OTA Safety

| ID | Requirement | Priority |
|----|-------------|----------|
| OTA-010 | Device SHALL NOT apply firmware smaller than minimum valid size | Must |
| OTA-011 | Device SHALL reject firmware built for wrong chip/project | Must |
| OTA-012 | Device SHALL continue normal operation during download phase | Should |
| OTA-013 | Device SHALL complete or abort cleanly — no partial writes to flash | Must |

---

## 2. Functional Test Cases

### TC-OTA-100: Successful OTA Update

**Objective**: Verify end-to-end OTA firmware update.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Check current firmware version | Version A displayed |
| 2 | Upload new firmware to server | File available for download |
| 3 | Trigger OTA update | Download starts |
| 4 | Monitor progress | Progress logged (10%, 50%, 100%) |
| 5 | Download completes | Integrity check passes |
| 6 | Device reboots | Automatic reboot |
| 7 | Check firmware version | Version B displayed |
| 8 | Verify all features working | Normal operation |

**Pass Criteria**: Update completes, correct version running, all features operational.

### TC-OTA-101: OTA Rollback on Bad Firmware

**Objective**: Verify automatic rollback when new firmware fails to boot.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Running stable firmware V1 | Normal operation |
| 2 | Flash intentionally broken firmware via OTA | Download and apply |
| 3 | Device reboots into new firmware | Boot fails or crashes |
| 4 | Watchdog or boot count triggers rollback | Reverts to V1 |
| 5 | Device reboots again | V1 running |
| 6 | Verify stable operation | All features working |

**Pass Criteria**: Automatic rollback, no manual intervention needed, device recoverable.

### TC-OTA-102: OTA Version Reporting

**Objective**: Verify firmware version is correctly reported.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Query version via HTTP `/status` | Version string returned |
| 2 | Query version via BLE (if supported) | Same version string |
| 3 | Perform OTA update | New version applied |
| 4 | Query version again | Updated version string |

**Pass Criteria**: Version always reflects running firmware accurately.

---

## 3. Edge Case Test Cases

### EC-OTA-200: Network Loss During OTA Download

**Objective**: Verify OTA handles download interruption safely.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start OTA download | Progress at 0% |
| 2 | At ~50%, disconnect WiFi | Download interrupted |
| 3 | Check device state | No crash, error logged |
| 4 | Device continues normal operation | Previous firmware running |
| 5 | Restore WiFi | Connection restored |
| 6 | Retry OTA | Download restarts from 0% |
| 7 | Download completes | Update applied successfully |

**Pass Criteria**: No brick, previous firmware intact, retry succeeds.

### EC-OTA-201: Power Loss During OTA Write

**Objective**: Verify device recovers from power loss during flash write.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start OTA update | Writing to flash |
| 2 | Cut power during write phase | Power lost |
| 3 | Restore power | Device boots |
| 4 | Check firmware | Previous firmware runs (A/B scheme) |
| 5 | Retry OTA | Update succeeds |

**Pass Criteria**: A/B partition scheme prevents brick, previous firmware boots.

### EC-OTA-202: Invalid Firmware Rejection

**Objective**: Verify device rejects invalid firmware files.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Attempt OTA with random binary | Rejected — invalid magic bytes |
| 2 | Attempt OTA with wrong chip firmware | Rejected — chip mismatch |
| 3 | Attempt OTA with truncated file | Rejected — size/checksum fail |
| 4 | Attempt OTA with oversized file | Rejected — exceeds partition |
| 5 | Device still running | Original firmware intact |

**Pass Criteria**: All invalid files rejected, device unaffected.

### EC-OTA-203: OTA During Active Operation

**Objective**: Verify device continues operating during OTA download.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device actively processing data | Normal operation |
| 2 | Trigger OTA download in background | Download starts |
| 3 | Monitor main application | Continues operating |
| 4 | Check for increased latency | Acceptable degradation |
| 5 | Download completes | Device reboots |
| 6 | New firmware running | Operation resumes |

**Pass Criteria**: No data loss during download phase, acceptable performance impact.

### EC-OTA-204: Repeated OTA Updates

**Objective**: Verify device handles many sequential OTA updates.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Perform OTA update V1 → V2 | Success |
| 2 | Perform OTA update V2 → V3 | Success |
| 3 | Perform OTA update V3 → V4 | Success |
| 4 | Repeat 5 more times | All succeed |
| 5 | Check free heap and NVS | No resource degradation |

**Pass Criteria**: No flash wear issues, no memory leaks across updates.

---

## 4. Test Environment Setup

### Required Equipment

- ESP32 device under test
- HTTP server hosting firmware files (workbench provides this)
- WiFi connectivity between device and server
- Serial monitor for progress and error logs

### Workbench OTA Commands

```bash
# Upload firmware to workbench
curl -X POST http://workbench.local:8080/api/firmware/upload \
  -F "project=my-project" -F "file=@build/firmware.bin"

# Trigger OTA on device via HTTP relay
curl -X POST http://workbench.local:8080/api/wifi/http \
  -H 'Content-Type: application/json' \
  -d '{"method":"POST","url":"http://192.168.4.2/ota","headers":{"Content-Type":"application/json"},"body":"...", "timeout":60}'

# Monitor progress via UDP logs
curl "http://workbench.local:8080/api/udplog?limit=50"
```
