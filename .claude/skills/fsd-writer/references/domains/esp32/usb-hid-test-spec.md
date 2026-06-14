# USB HID Test Specification for ESP32 Projects

Standard test cases for ESP32 USB Human Interface Device functionality (keyboard, mouse, gamepad). Copy relevant sections into project FSDs.

---

## 1. USB HID Requirements

### 1.1 USB Enumeration

| ID | Requirement | Priority |
|----|-------------|----------|
| HID-001 | Device SHALL enumerate as a USB HID device on the host | Must |
| HID-002 | USB descriptor SHALL match the intended HID type (keyboard/mouse/composite) | Must |
| HID-003 | Device SHALL be recognized without custom drivers on major OSes | Must |
| HID-004 | Device SHALL handle USB suspend and resume | Should |
| HID-005 | Device SHALL re-enumerate after reboot without host intervention | Should |

### 1.2 Keyboard HID

| ID | Requirement | Priority |
|----|-------------|----------|
| HID-010 | Device SHALL send standard USB HID keyboard reports | Must |
| HID-011 | Device SHALL support modifier keys (Shift, Ctrl, Alt, GUI) | Must |
| HID-012 | Device SHALL support multiple keyboard layouts | Should |
| HID-013 | Key-to-scancode mapping SHALL be correct for selected layout | Must |
| HID-014 | Device SHALL handle key repeat at host-configured rate | Should |
| HID-015 | Device SHALL send key release reports (no stuck keys) | Must |

### 1.3 HID Latency

| ID | Requirement | Priority |
|----|-------------|----------|
| HID-020 | Input-to-HID-report latency SHALL not exceed 50 ms | Must |
| HID-021 | Device SHALL sustain 60+ characters per second throughput | Should |
| HID-022 | No dropped or duplicate keystrokes under normal conditions | Must |

---

## 2. Functional Test Cases

### TC-HID-100: USB Enumeration

**Objective**: Verify device enumerates correctly as HID on all major OSes.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connect device via USB to Windows host | Recognized as HID keyboard |
| 2 | Check Device Manager | Listed under "Keyboards" |
| 3 | Repeat on macOS | Recognized, no driver prompt |
| 4 | Repeat on Linux | Recognized, `dmesg` shows HID device |
| 5 | Open text editor on each OS | Ready for input |
| 6 | Type test string | Characters appear correctly |

**Pass Criteria**: Enumeration succeeds on all three OSes without custom drivers.

### TC-HID-101: Keyboard Layout Accuracy

**Objective**: Verify correct character output for each supported layout.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select US layout | Layout set |
| 2 | Send "Hello, World! 123" | Exact match on host |
| 3 | Send special chars: `@#$%^&*()` | Correct for US layout |
| 4 | Switch to DE layout | Layout changed |
| 5 | Send "Über straße" | Correct with umlauts and ß |
| 6 | Send `@` (DE: AltGr+Q) | Correct scancode for DE |
| 7 | Switch to FR layout | Layout changed |
| 8 | Send "café résumé" | Correct with accents |

**Pass Criteria**: All characters correct for each layout, no mismatches.

### TC-HID-102: Modifier Keys and Shortcuts

**Objective**: Verify modifier keys work correctly.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Send Ctrl+C | Copy operation on host |
| 2 | Send Ctrl+V | Paste operation on host |
| 3 | Send Shift+A | Uppercase "A" |
| 4 | Send Alt+Tab (Windows) | Window switch |
| 5 | Send Cmd+Space (macOS) | Spotlight opens |
| 6 | Release all modifiers | No stuck keys |

**Pass Criteria**: All modifier combinations produce correct host actions.

### TC-HID-103: Typing Speed and Throughput

**Objective**: Verify sustained typing throughput.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Send 100-character string | All characters received |
| 2 | Measure total time | < 1.7 seconds (60 chars/s) |
| 3 | Send 500-character paragraph | All characters received |
| 4 | Verify no dropped characters | Input matches output exactly |
| 5 | Send rapid key sequences | No duplicates or drops |

**Pass Criteria**: >= 60 chars/s sustained, zero character loss.

---

## 3. Edge Case Test Cases

### EC-HID-200: USB Disconnect and Reconnect

**Objective**: Verify device handles USB cable disconnect/reconnect.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device connected and working | HID active |
| 2 | Unplug USB cable | Device loses host |
| 3 | Plug USB cable back in | Re-enumeration |
| 4 | Host recognizes device again | HID keyboard available |
| 5 | Type test string | Characters appear correctly |

**Pass Criteria**: Clean re-enumeration, no host-side issues, no stuck keys.

### EC-HID-201: USB Suspend and Resume

**Objective**: Verify device handles host sleep/wake.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device connected and working | HID active |
| 2 | Put host to sleep | USB suspended |
| 3 | Wake host | USB resumed |
| 4 | Type test string | Characters appear correctly |
| 5 | Verify no stuck modifiers | Clean state after resume |

**Pass Criteria**: Device resumes without re-enumeration, no stuck keys.

### EC-HID-202: Rapid Input While Host Busy

**Objective**: Verify device buffers input when host is slow to poll.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Host under heavy CPU load | Reduced USB poll rate |
| 2 | Send 50-character burst | All characters queued |
| 3 | Host catches up | All characters delivered |
| 4 | Verify order | Characters in correct sequence |

**Pass Criteria**: No character loss under host load, correct ordering.

### EC-HID-203: Stuck Key Prevention

**Objective**: Verify no keys remain "pressed" after errors.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Send key press + release | Character appears once |
| 2 | Send key press, then disconnect BLE (input source) | Key release sent |
| 3 | Reconnect BLE | No stuck keys on host |
| 4 | Send modifier press, then power cycle device | Modifier released on USB |
| 5 | Verify host input state | All keys released |

**Pass Criteria**: No stuck keys under any failure condition.

### EC-HID-204: Concurrent BLE Input and USB Output

**Objective**: Verify BLE-to-USB pipeline under load.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | BLE connected, USB connected | Both active |
| 2 | Send text via BLE NUS | Appears as HID on host |
| 3 | Send rapid BLE commands | All processed in order |
| 4 | Disconnect BLE mid-string | Partial string delivered, no crash |
| 5 | Reconnect BLE, send more | Continues working |

**Pass Criteria**: Clean pipeline, no corruption, handles BLE drops gracefully.

---

## 4. Test Environment Setup

### Required Equipment

- ESP32-S3 device with USB OTG support
- Test hosts: Windows, macOS, Linux
- BLE-capable phone (for BLE-to-HID input path)
- Text editor open on host for output verification
- USB protocol analyzer (optional)

### Verification Commands

```bash
# Linux: check USB HID enumeration
lsusb | grep -i "espressif\|keyboard"
dmesg | tail -20

# Linux: monitor HID input events
sudo evtest /dev/input/eventX

# macOS: check USB devices
system_profiler SPUSBDataType | grep -A5 "Keyboard"
```
