# NVS Test Specification for ESP32 Projects

Standard test cases for ESP32 Non-Volatile Storage functionality (configuration persistence, credentials, factory reset). Copy relevant sections into project FSDs.

---

## 1. NVS Requirements

### 1.1 Configuration Storage

| ID | Requirement | Priority |
|----|-------------|----------|
| NVS-001 | Device SHALL store configuration parameters in NVS | Must |
| NVS-002 | Configuration SHALL persist across reboots and power cycles | Must |
| NVS-003 | Device SHALL use default values when NVS is empty or corrupt | Must |
| NVS-004 | Device SHALL log configuration values at startup | Should |

### 1.2 Credential Storage

| ID | Requirement | Priority |
|----|-------------|----------|
| NVS-010 | WiFi credentials SHALL be stored encrypted in NVS | Must |
| NVS-011 | API keys and tokens SHALL be stored encrypted in NVS | Must |
| NVS-012 | Credentials SHALL NOT appear in serial logs or debug output | Must |

### 1.3 Factory Reset

| ID | Requirement | Priority |
|----|-------------|----------|
| NVS-020 | Device SHALL support factory reset (erase all NVS config) | Must |
| NVS-021 | Factory reset SHALL be triggerable by button hold (5+ seconds) | Should |
| NVS-022 | Factory reset SHALL be triggerable via BLE or HTTP command | Should |
| NVS-023 | After factory reset, device SHALL enter provisioning mode (AP) | Must |
| NVS-024 | Factory reset SHALL NOT erase calibration data (if applicable) | May |

---

## 2. Functional Test Cases

### TC-NVS-100: Configuration Persistence Across Reboot

**Objective**: Verify NVS configuration survives reboot.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Configure device via portal | Settings saved |
| 2 | Read back configuration | Values match input |
| 3 | Reboot device | Device restarts |
| 4 | Read configuration again | Values still match |
| 5 | Power cycle device (remove power) | Cold boot |
| 6 | Read configuration again | Values still match |

**Pass Criteria**: Configuration identical before and after reboot/power cycle.

### TC-NVS-101: Default Values on First Boot

**Objective**: Verify device uses sensible defaults when NVS is empty.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Erase NVS partition | NVS cleared |
| 2 | Boot device | Device starts |
| 3 | Check serial log | Default values logged |
| 4 | Verify device enters provisioning mode | AP mode active |
| 5 | Configure via portal | Settings saved |
| 6 | Reboot | Configured values used |

**Pass Criteria**: Clean first boot with defaults, no crash on empty NVS.

### TC-NVS-102: Factory Reset via Button

**Objective**: Verify factory reset erases configuration and enters provisioning.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device configured and running | Normal operation |
| 2 | Hold CONFIG button for 5 seconds | LED indication (if applicable) |
| 3 | Release button | Factory reset triggered |
| 4 | Check serial log | "Factory reset" logged |
| 5 | Device reboots | Enters AP mode |
| 6 | Previous WiFi credentials gone | Must reconfigure |
| 7 | Previous settings gone | Defaults active |

**Pass Criteria**: Full configuration erasure, device enters provisioning mode.

### TC-NVS-103: Factory Reset via Command

**Objective**: Verify factory reset via BLE or HTTP command.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device configured and running | Normal operation |
| 2 | Send factory reset command (BLE or HTTP) | Command acknowledged |
| 3 | Device reboots | Automatic restart |
| 4 | Device enters AP mode | Provisioning active |
| 5 | All settings cleared | Must reconfigure |

**Pass Criteria**: Remote factory reset works, same result as button reset.

---

## 3. Edge Case Test Cases

### EC-NVS-200: NVS Corruption Recovery

**Objective**: Verify device recovers from corrupt NVS.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device running with configuration | Normal operation |
| 2 | Corrupt NVS partition (via esptool) | NVS invalid |
| 3 | Reboot device | NVS init fails |
| 4 | Check device behavior | Falls back to defaults |
| 5 | Device enters provisioning mode | AP mode active |
| 6 | Reconfigure via portal | New config saved |
| 7 | Reboot | Normal operation restored |

**Pass Criteria**: No crash on corrupt NVS, graceful fallback to defaults.

### EC-NVS-201: NVS Full / Storage Exhaustion

**Objective**: Verify device handles full NVS partition.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Write many large entries to NVS | NVS fills up |
| 2 | Attempt to write configuration | Write fails gracefully |
| 3 | Error logged | "NVS full" or similar |
| 4 | Existing configuration still readable | Previous data intact |
| 5 | Erase NVS and reconfigure | Normal operation restored |

**Pass Criteria**: No crash, existing data preserved, error reported.

### EC-NVS-202: Power Loss During NVS Write

**Objective**: Verify NVS integrity after power loss during write.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger configuration save | NVS write in progress |
| 2 | Cut power during write | Power lost |
| 3 | Restore power | Device boots |
| 4 | Check NVS state | Either old or new value (not corrupt) |
| 5 | Device operates normally | No crash from partial write |

**Pass Criteria**: NVS transactional writes prevent corruption.

### EC-NVS-203: Credential Security Verification

**Objective**: Verify credentials are not exposed in logs or debug output.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Configure WiFi with password "secret123" | Credentials saved |
| 2 | Monitor all serial output during boot | No plaintext password |
| 3 | Monitor serial during WiFi connect | No plaintext password |
| 4 | Query status endpoint | No credentials in response |
| 5 | Read NVS raw bytes (esptool) | Encrypted or obfuscated |

**Pass Criteria**: Credentials never appear in plaintext in any output.

### EC-NVS-204: Configuration Update While Running

**Objective**: Verify live configuration update takes effect.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device running with config A | Normal operation |
| 2 | Update config to B via portal | New values saved |
| 3 | Device applies new config | Behavior changes (or reboot) |
| 4 | Verify new config active | Config B in effect |
| 5 | Reboot device | Config B persists |

**Pass Criteria**: Configuration update takes effect, persists across reboot.

---

## 4. Test Environment Setup

### Required Equipment

- ESP32 device under test
- Serial monitor for log verification
- esptool for NVS manipulation
- Phone/laptop for portal access

### NVS Commands

```bash
# Erase NVS partition
esptool.py --port <PORT> erase_region 0x9000 0x6000

# Read NVS partition (for inspection)
esptool.py --port <PORT> read_flash 0x9000 0x6000 nvs_dump.bin

# Parse NVS dump
python3 -m esp_idf_nvs_partition_gen --input nvs_dump.bin
```
