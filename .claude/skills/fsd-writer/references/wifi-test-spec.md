# WiFi Test Specification for ESP32 Projects

Standard test cases for ESP32 WiFi STA functionality. Copy relevant sections into project FSDs.

---

## 1. WiFi Requirements

### 1.1 WiFi Station Mode (STA)

| ID | Requirement | Priority |
|----|-------------|----------|
| WIFI-001 | System SHALL connect to configured WiFi network in STA mode | Must |
| WIFI-002 | WiFi credentials SHALL be stored encrypted in NVS | Must |
| WIFI-003 | System SHALL automatically reconnect on WiFi disconnect | Must |
| WIFI-004 | System SHALL log WiFi connection status changes | Should |
| WIFI-005 | System SHALL support WPA2/WPA3 authentication | Must |

### 1.2 Test Mode (WiFi + Ethernet)

| ID | Requirement | Priority |
|----|-------------|----------|
| TEST-001 | System SHALL support a "Test mode" configurable via captive portal or NVS | Should |
| TEST-002 | In Test mode, server SHALL listen on ALL interfaces (ETH + WiFi) | Should |
| TEST-003 | In Test mode, clients MAY connect via WiFi instead of Ethernet | May |
| TEST-004 | Test mode SHALL be indicated via serial log and status messages | Should |
| TEST-005 | Test mode allows full operation without Ethernet hardware connected | Should |

---

## 2. Edge Case Test Cases

### EC-100: Network Disconnect During Active Session

**Objective**: Verify system handles network interruption gracefully.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Active session running | Data publishing |
| 2 | Disconnect network cable/WiFi | Connection lost |
| 3 | Session continues locally | Local operation maintained |
| 4 | Wait 30 seconds | Reconnection attempts logged |
| 5 | Restore network | Reconnects |
| 6 | Session state restored | Operation continues |

**Pass Criteria**: Automatic recovery, no data loss.

### EC-101: WiFi Disconnect During Operation

**Objective**: Verify WiFi loss does not affect other network operations.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Session active | Application layer publishing via WiFi |
| 2 | Disable WiFi AP | WiFi connection lost |
| 3 | Other interfaces continue | Ethernet communication OK |
| 4 | Messages queued | Buffer fills |
| 5 | Re-enable WiFi AP | WiFi reconnects |
| 6 | Queued messages sent | Application layer catches up |

**Pass Criteria**: Other interfaces unaffected, application layer recovers automatically.

### EC-110: WiFi Signal Strength Degradation

**Objective**: Verify system handles weak WiFi signal gracefully.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Normal operation | RSSI > -60 dBm |
| 2 | Increase distance to AP | RSSI decreases |
| 3 | Monitor at -70 dBm | Connection maintained |
| 4 | Monitor at -80 dBm | Possible packet loss |
| 5 | Monitor at -85 dBm | Reconnection attempts |
| 6 | Return to normal range | Connection stabilizes |

**Pass Criteria**: No crash, graceful degradation, automatic recovery.

### EC-111: WiFi AP Channel Congestion

**Objective**: Verify system handles congested WiFi environment.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connect to AP on channel 6 | Normal operation |
| 2 | Enable multiple interfering APs | Increased latency |
| 3 | Monitor message delivery | Messages delivered (slower) |
| 4 | Monitor reconnection behavior | May reconnect occasionally |
| 5 | Disable interfering APs | Performance returns to normal |

**Pass Criteria**: No data loss, eventual delivery of all messages.

### EC-115: DHCP Lease Expiry

**Objective**: Verify system handles DHCP lease renewal.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Set short DHCP lease (60s) | System gets IP |
| 2 | Wait for lease expiry | Renewal attempt |
| 3 | Verify IP maintained | Same or new IP |
| 4 | Verify application connection | Reconnects if IP changed |
| 5 | Normal operation continues | No user intervention needed |

**Pass Criteria**: Automatic lease renewal, connection recovery.

---

## 3. Test Environment Setup

### Required Equipment

- ESP32 device under test
- WiFi router with configurable settings
- Network analyzer (Wireshark optional)

### Network Configuration Template

```
WiFi Network: TestNetwork
Password: testpassword123
DHCP Range: 192.168.1.100-200
```

### Monitoring Commands

```bash
# Monitor ESP32 serial output
idf.py monitor
# or
pio device monitor

# Check WiFi signal strength
iw dev wlan0 link
```
