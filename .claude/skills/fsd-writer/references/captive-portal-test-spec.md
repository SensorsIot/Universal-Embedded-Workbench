# Captive Portal Test Specification for ESP32 Projects

Standard test cases for ESP32 WiFi Access Point and captive portal provisioning. Copy relevant sections into project FSDs.

---

## 1. Captive Portal Requirements

### 1.1 WiFi Access Point Mode

| ID | Requirement | Priority |
|----|-------------|----------|
| AP-001 | System SHALL start AP mode when no valid WiFi config exists | Must |
| AP-002 | System SHALL start AP mode when CONFIG button held for 5 seconds | Must |
| AP-003 | AP SHALL use SSID format: `PROJECT-{MAC_LAST_4}` | Should |
| AP-004 | AP SHALL use open authentication for easy initial setup | May |
| AP-005 | AP SHALL assign IP 192.168.4.1 to clients via DHCP | Should |
| AP-006 | System MAY run AP and STA concurrently (fallback mode) | May |

### 1.2 Captive Portal

| ID | Requirement | Priority |
|----|-------------|----------|
| CP-001 | AP SHALL serve a captive portal web page on connection | Must |
| CP-002 | Portal SHALL redirect all HTTP traffic to the configuration page | Should |
| CP-003 | Portal SHALL allow WiFi network selection and credential entry | Must |
| CP-004 | Portal SHALL allow application-specific configuration | Should |
| CP-005 | Portal SHALL validate input before saving | Should |
| CP-006 | Configuration SHALL be saved to NVS before reboot | Must |

---

## 2. Functional Test Cases

### TC-CP-100: Captive Portal Configuration (First Boot)

**Objective**: Verify captive portal allows complete system configuration on first boot.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Power on device with empty NVS | AP mode activates automatically |
| 2 | Connect phone to AP (PROJECT-XXXX) | DHCP assigns IP |
| 3 | Open browser | Redirected to portal |
| 4 | Navigate to WiFi page | Available networks listed |
| 5 | Enter WiFi credentials | Form accepts input |
| 6 | Save configuration | Success message |
| 7 | Navigate to application settings page | Form displayed |
| 8 | Enter settings | Form accepts input |
| 9 | Save and reboot | System restarts |
| 10 | Verify WiFi connects | STA mode connected |

**Pass Criteria**: Configuration persists across reboot, WiFi connection established.

### TC-CP-101: Captive Portal via Button Press

**Objective**: Verify CONFIG button triggers AP mode while running.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device running in STA mode | Normal operation |
| 2 | Hold CONFIG button for 5 seconds | LED indication (if applicable) |
| 3 | AP mode activates | SSID visible |
| 4 | Connect and access portal | Portal accessible |
| 5 | Update WiFi credentials | New credentials saved |
| 6 | Save and reboot | Device connects to new network |

**Pass Criteria**: Button triggers AP mode, reconfiguration works.

### TC-CP-102: Portal Network Scan

**Objective**: Verify portal shows available WiFi networks.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter AP mode | Portal active |
| 2 | Open WiFi configuration page | Network scan starts |
| 3 | Verify network list | Available SSIDs displayed with signal strength |
| 4 | Select a network | SSID pre-filled |
| 5 | Enter password | Form accepts input |

**Pass Criteria**: Networks scanned and displayed, selection works.

---

## 3. Edge Case Test Cases

### EC-CP-200: WiFi Credential Change While Running

**Objective**: Verify system handles WiFi password change on the AP side.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | System connected to WiFi | Normal operation |
| 2 | Change AP password on router | Connection lost |
| 3 | System attempts reconnect | Auth failures logged |
| 4 | After N failures | AP mode activates (fallback) |
| 5 | Reconfigure via portal | New credentials saved |
| 6 | System reconnects | Normal operation restored |

**Pass Criteria**: Fallback to AP mode, reconfiguration possible.

### EC-CP-201: Simultaneous AP and STA Mode

**Objective**: Verify concurrent AP/STA operation for recovery scenarios.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | System in normal STA mode | Connected to WiFi |
| 2 | Hold CONFIG button 3 sec | AP mode starts (STA continues) |
| 3 | Connect phone to AP | Can access portal |
| 4 | Verify STA still connected | Application still running |
| 5 | Release CONFIG button | AP mode timeout (60s) |
| 6 | AP deactivates | STA-only mode |

**Pass Criteria**: Both modes functional simultaneously, clean transition.

### EC-CP-202: Portal Timeout

**Objective**: Verify AP mode auto-disables after inactivity.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger AP mode via button | AP active |
| 2 | Do not connect to AP | No client connected |
| 3 | Wait for timeout (e.g., 5 minutes) | AP mode deactivates |
| 4 | Device returns to STA mode | Reconnects to WiFi |

**Pass Criteria**: AP mode does not stay active indefinitely.

### EC-CP-203: Invalid Configuration Input

**Objective**: Verify portal rejects invalid input.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open portal WiFi page | Form displayed |
| 2 | Submit empty SSID | Validation error |
| 3 | Submit password < 8 chars | Validation error |
| 4 | Submit valid credentials | Accepted |

**Pass Criteria**: Invalid input rejected with user-friendly messages.

### EC-CP-204: Multiple Clients on AP

**Objective**: Verify portal handles multiple simultaneous clients.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | AP mode active | Portal serving |
| 2 | Connect phone 1 | Portal accessible |
| 3 | Connect phone 2 | Portal accessible |
| 4 | Both submit config simultaneously | One succeeds, one gets conflict |
| 5 | Device saves last valid config | Configuration consistent |

**Pass Criteria**: No crash, configuration remains consistent.

---

## 4. Test Environment Setup

### Required Equipment

- ESP32 device under test
- Phone or laptop for portal access
- WiFi router with configurable password
- Serial monitor for device logs

### Workbench Commands

```bash
# Enter captive portal via workbench
curl -X POST http://workbench.local:8080/api/wifi/enter-portal \
  -H 'Content-Type: application/json' -d '{"slot": "slot-1"}'

# Provision WiFi via workbench
curl -X POST http://workbench.local:8080/api/wifi/provision \
  -H 'Content-Type: application/json' \
  -d '{"ssid": "TestNetwork", "password": "testpass123"}'
```
