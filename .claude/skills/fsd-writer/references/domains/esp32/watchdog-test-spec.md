# Watchdog Test Specification for ESP32 Projects

Standard test cases for ESP32 watchdog timer functionality (software and hardware). Copy relevant sections into project FSDs.

---

## 1. Watchdog Requirements

### 1.1 Software Watchdog

| ID | Requirement | Priority |
|----|-------------|----------|
| WDT-001 | System SHALL implement a software watchdog monitoring all critical tasks | Must |
| WDT-002 | Watchdog timeout SHALL be configurable (default: 60 seconds) | Should |
| WDT-003 | System SHALL log health check status periodically | Should |
| WDT-004 | System SHALL reboot automatically on watchdog timeout | Must |
| WDT-005 | Watchdog SHALL NOT false-trigger during normal operations (WiFi reconnect, OTA) | Must |

### 1.2 Hardware Watchdog

| ID | Requirement | Priority |
|----|-------------|----------|
| WDT-010 | Hardware watchdog SHALL be enabled as failsafe for software watchdog | Should |
| WDT-011 | Hardware watchdog timeout SHALL be longer than software timeout | Must |
| WDT-012 | Hardware watchdog SHALL trigger system panic and reboot if software WDT fails | Must |

### 1.3 Memory Watchdog

| ID | Requirement | Priority |
|----|-------------|----------|
| WDT-020 | System SHALL monitor free heap memory | Should |
| WDT-021 | System SHALL log warning when heap drops below warning threshold | Should |
| WDT-022 | System SHALL reboot preventively when heap drops below critical threshold | Should |

---

## 2. Functional Test Cases

### TC-WDT-100: Software Watchdog — Task Timeout Detection

**Objective**: Verify software watchdog detects hung tasks and recovers.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | System running normally | All tasks healthy |
| 2 | Monitor serial log | Health checks every 5 seconds |
| 3 | Simulate task hang (test firmware) | Stop task heartbeat updates |
| 4 | Wait for timeout (60+ seconds) | Software watchdog triggers |
| 5 | Check serial log | "Task timeout — triggering reboot" |
| 6 | System reboots automatically | ESP.restart() called |
| 7 | After reboot | Normal operation resumes |
| 8 | Verify WiFi reconnects | Connection restored |

**Pass Criteria**: Hung task detected within timeout + margin, automatic recovery via reboot.

### TC-WDT-101: Hardware Watchdog Recovery

**Objective**: Verify hardware watchdog provides failsafe recovery.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | System running normally | Hardware WDT active |
| 2 | Check serial log at startup | "Hardware WDT initialized" message |
| 3 | Monitor normal operation | WDT fed every health check cycle |
| 4 | If watchdog task itself hangs | Hardware WDT triggers after timeout |
| 5 | System panic and reboot | Automatic hardware recovery |
| 6 | After reboot | Normal operation restored |

**Pass Criteria**: Hardware watchdog provides failsafe recovery if software watchdog fails.

### TC-WDT-102: Memory Watchdog

**Objective**: Verify system reboots before memory exhaustion causes crash.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | System running normally | Heap above threshold |
| 2 | Monitor heap via serial | free_heap values logged |
| 3 | Simulate memory pressure | Allocate memory (test firmware) |
| 4 | Heap drops below warning threshold | "Low heap" warning logged |
| 5 | Heap drops below critical threshold | "Critical heap — triggering reboot" |
| 6 | System reboots automatically | Preventive recovery |
| 7 | After reboot | Memory recovered, normal operation |

**Pass Criteria**: Critical memory exhaustion triggers preventive reboot before crash.

---

## 3. Edge Case Test Cases

### EC-WDT-200: Watchdog Stability During WiFi Disconnect

**Objective**: Verify watchdog does not false-trigger during normal WiFi reconnection.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | System running, WiFi connected | Watchdog task active |
| 2 | Disable WiFi AP | Connection lost |
| 3 | Wait 5 minutes | Extended disconnect period |
| 4 | Monitor serial log | Health checks continue (every 5s) |
| 5 | No watchdog resets | System remains stable |
| 6 | Re-enable WiFi AP | Connection restored |
| 7 | Application reconnects | Normal operation resumes |

**Pass Criteria**: Watchdog operates independently of WiFi state, no false triggers.

### EC-WDT-201: Watchdog During OTA Update

**Objective**: Verify watchdog does not interfere with OTA updates.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start OTA firmware update | Upload begins |
| 2 | Monitor watchdog during upload | WDT continues to be fed |
| 3 | Update takes > 60 seconds | No watchdog timeout |
| 4 | Update completes | Success, system reboots |
| 5 | New firmware starts | Watchdog initializes |
| 6 | Normal operation | All healthy |

**Pass Criteria**: OTA update completes without watchdog interference.

### EC-WDT-202: Watchdog During MQTT Reconnect Storm

**Objective**: Verify watchdog remains stable during rapid MQTT reconnect cycles.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | System connected to MQTT | Normal operation |
| 2 | Broker goes up/down rapidly (10 cycles) | Reconnect storm |
| 3 | Monitor watchdog | Health checks continue |
| 4 | No false triggers | System stable throughout |
| 5 | Broker stabilizes | MQTT reconnects |

**Pass Criteria**: Reconnect churn does not exhaust resources or trigger watchdog.

### EC-WDT-203: Watchdog Recovery Count

**Objective**: Verify system tracks watchdog-triggered reboots.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Force watchdog trigger (test firmware) | System reboots |
| 2 | Check boot reason on restart | "WDT reset" in reset reason |
| 3 | Verify reset counter (if implemented) | Counter incremented |
| 4 | Normal reboot (power cycle) | Different reset reason |

**Pass Criteria**: Watchdog resets are distinguishable from normal reboots.

---

## 4. Test Environment Setup

### Required Equipment

- ESP32 device under test (with test firmware that can simulate hangs)
- Serial monitor for watchdog logs
- WiFi AP for disconnect testing
- MQTT broker for reconnect testing

### Monitoring

```bash
# Watch for watchdog events in serial output
# Look for: "health check", "watchdog", "WDT", "reboot", "rst:0x"

# Check reset reason after boot
# rst:0x1  — power-on reset
# rst:0x3  — software reset (ESP.restart)
# rst:0xc  — RTC WDT reset (watchdog)
# rst:0xf  — brownout reset
```
