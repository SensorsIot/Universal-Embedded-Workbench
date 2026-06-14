# FSD Writing Guide (Steps 8-10)

Detailed instructions for writing the Operations / Verification & Validation /
Appendix chapters with workbench-specific content. The fsd-writer FSD uses the
layer-grouped Parts scheme, so locate these by role/title (under Part E / back
matter), not by a fixed section number.

## Step 8: Write the Operational Procedures chapter (Workbench Operations)

Replace the **Operational Procedures** chapter (under Part E) with
workbench-specific operational content. This chapter becomes a standalone
**operations guide** -- how to interact with the device through the workbench. It
contains no test cases.

If the fsd-writer left a generic Operational Procedures chapter, replace it
entirely. The workbench operations are the operational procedures for this project.

### 8a. Hardware setup

Query the workbench for hardware details:
```bash
curl -s http://workbench.local:8080/api/devices | jq .
curl -s http://workbench.local:8080/api/info | jq .
```

Record: slot label, TCP port, RFC2217 URL, device state.

**Check for dual-USB hub boards:** If the board occupies two slots (onboard USB hub exposing both JTAG and UART), identify which slot is which:
- Espressif USB-Serial/JTAG (`303a:1001`) -> **JTAG slot** (flash here)
- CH340/CP2102 UART bridge (`1a86:55d3` / `10c4:ea60`) -> **UART slot** (console output here)

Write a hardware table and a project-specific values table:

```markdown
### Hardware Setup

| What | Where |
|------|-------|
| ESP32 USB | Workbench slot <N>, serial at `rfc2217://workbench.local:<PORT>` |
| Workbench host | `workbench.local:8080` |
| UDP log sink | `workbench.local:5555` |
| OTA firmware URL | `http://workbench.local:8080/firmware/<project>/<project>.bin` |

#### Project-Specific Values

| Value | Setting |
|-------|---------|
| WiFi portal SSID | `<SSID>` (device SoftAP name when no credentials stored) |
| Workbench AP SSID | `WB-TestAP` |
| Workbench AP password | `wbtestpass` |
| BLE device name | `<NAME>` |
| NVS namespace | `<NS>` |
| NUS RX characteristic | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
```

**Important:** Fill in all actual values from the firmware source -- never leave `<placeholder>` in the final FSD.

### 8b. Flashing

Document the project-specific esptool command for serial flashing via RFC2217. Reference the `esp-idf-handling` skill for download mode, crash-loop recovery, and dual-USB hub details.

### 8c. WiFi provisioning

WiFi provisioning is a prerequisite for most operations (OTA, UDP logs, HTTP endpoints). Document it as a complete two-phase procedure with filled-in project values.

**Three values are involved -- document all three clearly:**

| Value | What it is | Where it's defined |
|-------|-----------|-------------------|
| Device portal SSID | The SoftAP name the device broadcasts when it has no WiFi credentials | `wifi_prov.c` -> `AP_SSID` |
| Workbench AP SSID | The WiFi network the workbench creates for the device to join | Passed in `enter-portal` request |
| Workbench AP password | Password for the workbench's AP | Passed in `enter-portal` request |

**Always document both phases:**
1. **Ensure device is in AP mode** -- BLE WiFi reset if previously provisioned, skip if freshly flashed
2. **Provision via captive portal** -- `enter-portal` with all three values filled in, serial monitor for confirmation

Include the enter-portal failure diagnostic steps (check AP mode, check WiFi scan, check activity log).

### 8d. BLE commands

Document how to scan, connect, and send each opcode. Write a command reference table:

```markdown
| Opcode | Hex example | Description | Expected log |
|--------|-------------|-------------|--------------|
| `0x01 <count>` | `0103` | Backspace | `"BACKSPACE x3"` |
| ... | ... | ... | ... |
```

Include one example `curl` write command. This is reference material -- test cases go in the Testing chapter.

### 8e. OTA updates

Document the complete OTA workflow:
1. Upload firmware to the workbench (`/api/firmware/upload`)
2. Trigger OTA via BLE (`CMD_OTA` opcode) or via HTTP (`POST /ota` through relay)
3. Monitor result via serial

### 8f. HTTP endpoints

Document the device's HTTP endpoints and how to reach them via the workbench HTTP relay (`/api/wifi/http`). Typical endpoints: `/status`, `/ota`.

### 8g. Log monitoring

Document the two log methods (serial monitor and UDP logs) with example commands. This is the "how" -- when to use which method goes in the Appendix.

## Step 9: Write the Verification & Validation chapter (Testing)

Replace the **Verification & Validation** chapter (under Part E) with workbench
test cases. This chapter contains **only test cases** -- verification tables with
pass/fail criteria. It does not repeat operational procedures from the
Operational Procedures chapter.

Preserve the chapter's **§x.0 Test Architecture** and its **generated-traceability
pointer** (the matrix/gap-report reference — never a hand-filled status table);
replace the phase verification tables with workbench-specific test procedures.

### 9a. Phase verification tables

For each implementation phase, write a table:

```markdown
### Phase N Verification

| Step | Feature | Test procedure | Success criteria |
|------|---------|---------------|-----------------|
| 1 | <feature> | <brief description, reference workbench chapter> | <expected output> |
```

**Rules:**
- Every FSD feature must appear in exactly one phase verification table
- Test procedures **reference** operations from the Operational Procedures chapter (e.g., "Provision WiFi (see WiFi Provisioning)") -- they don't duplicate curl commands
- Every step must have concrete, observable success criteria -- no vague "verify it works"
- Include the hex data for BLE commands inline (e.g., "BLE write `024869`") since that's test-specific

## Step 10: Write the Troubleshooting and Appendix content

Replace the **Troubleshooting** and **Appendices** content (back matter) with
workbench-specific diagnostics and reference material.

### 10a. Logging strategy

Document when to use each log method:

```markdown
### Logging Strategy

| Situation | Method | Why |
|-----------|--------|-----|
| Verify boot output | Serial monitor | Captures UART before WiFi is up |
| Monitor BLE commands | UDP logs | Non-blocking, works while device runs |
| Capture crash output | Serial monitor | Only UART captures panic handler output |
```

### 10b. Troubleshooting

Add a failure-to-diagnostic-to-fix mapping table covering likely failure modes:

```markdown
### Troubleshooting

| Test failure | Diagnostic | Fix |
|-------------|-----------|-----|
| Serial monitor shows no output | Check `/api/devices` | Device absent or flapping |
| enter-portal times out | Check serial for AP mode | BLE `CMD_WIFI_RESET` first |
| ... | ... | ... |
```
