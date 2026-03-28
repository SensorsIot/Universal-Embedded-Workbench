---
name: workbench-integration
description: >
  Integrates an ESP32 project with the Universal ESP32 Workbench. Adds firmware
  modules (UDP logging, WiFi provisioning, OTA, BLE command handling, strategic
  log messages), updates build config, then writes the Workbench operations,
  Testing, and Appendix chapters into the project's existing FSD.
  Triggers on "integrate workbench", "add workbench", "workbench integration",
  "set up project", "add testing", "add tester".
---

# ESP32 Workbench Integration

This is a procedure. When triggered, read the project's existing FSD, integrate
the firmware with the workbench infrastructure (UDP logging, OTA, BLE command
handling, strategic log messages), then write the operational, testing, and
appendix chapters into the FSD.

**Prerequisite:** The project must already have an FSD with at least a System
Overview and Functional Requirements section. Use the `fsd-writer` skill first
to generate one from a rough description if needed.

The workbench provides the **test infrastructure**. This skill adds both the
**firmware integration** (modules the workbench needs to interact with the
device) and the **FSD documentation** (operational guide, test plan,
troubleshooting).

## FSD Document Structure

This skill operates on FSDs produced by the `fsd-writer` skill, which uses
this canonical numbered structure:

```
# <Project Name> — Functional Specification Document (FSD)
## 1. System Overview                    ← pre-existing (read-only)
## 2. System Architecture                ← pre-existing (read-only)
## 3. Implementation Phases              ← pre-existing (read-only)
## 4. Functional Requirements            ← pre-existing (read-only)
## 5. Risks, Assumptions & Dependencies  ← pre-existing (read-only)
## 6. Interface Specifications           ← pre-existing (read-only)
## 7. Operational Procedures             ← REPLACED by this skill with workbench-specific content
## 8. Verification & Validation          ← REPLACED by this skill with workbench test cases
## 9. Troubleshooting Guide              ← REPLACED by this skill with workbench diagnostics
## 10. Appendix                          ← REPLACED by this skill with logging strategy + constants
```

**Sections 1–6** are written by the `fsd-writer` skill and contain system
overview, architecture, phases, requirements, risks, and interfaces. This skill
reads them to extract features, phases, and constants but does not modify them.

**Sections 7–10** are written (or replaced) by this skill with workbench-specific
operational procedures, test cases, troubleshooting, and appendix content.

Steps 1–7 handle firmware integration. Steps 8–12 write FSD sections 7–10.

## Template Reference

All template code lives in `Universal-ESP32-Workbench/test-firmware/`. When adding modules, copy from these templates and customize project-specific values:

| Module | Template source | Customization |
|--------|----------------|---------------|
| `udp_log.c/.h` | `test-firmware/main/udp_log.c` | None (universal) |
| `wifi_prov.c/.h` | `test-firmware/main/wifi_prov.c` | Change `AP_SSID`. |
| `portal.html` | `test-firmware/main/portal.html` | Change `<title>` and `<h1>` |
| `ota_update.c/.h` | `test-firmware/main/ota_update.c` | Change `OTA_DEFAULT_URL` |
| `ble_nus.c/.h` | `test-firmware/main/ble_nus.c` | Change BLE device name |
| `http_server.c/.h` | `test-firmware/main/http_server.c` | Add project-specific endpoints |
| `nvs_store.c/.h` | `test-firmware/main/nvs_store.c` | Change `NVS_NAMESPACE` |
| `dns_server/` | `test-firmware/components/dns_server/` | None (copy entire dir) |
| `partitions.csv` | `test-firmware/partitions.csv` | None (dual OTA layout) |
| `sdkconfig.defaults` | `test-firmware/sdkconfig.defaults` | Reference for required options |
| `app_main.c` | `test-firmware/main/app_main.c` | Reference for init order only |

## Workbench Compatibility Contract

The workbench actively drives the device through BLE commands, HTTP relay, captive portal automation, and serial/UDP log parsing. The firmware must conform to two contracts:

- **Contract 1: Required Log Messages** -- 17 exact format strings the workbench greps for (e.g. `"Init complete"`, `"STA got IP"`, `"OTA succeeded"`). Missing or reformatted strings break workbench detection.
- **Contract 2: Required Process Flows** -- WiFi provisioning (SoftAP captive portal), WiFi reset (BLE-triggered), OTA (HTTP `/ota` endpoint), BLE commands (NimBLE NUS), and the canonical boot sequence.

For the complete log pattern table, process flow sequences, and compatibility validation rules, read `references/compatibility-contract.md`.

## Procedure

### Step 1: Identify project

Find the project's FSD path and firmware root directory. Confirm:
- What chip is being used (ESP32, ESP32-S3, etc.)
- Where the firmware source lives (e.g. `main/` directory)
- The project name

### Step 2: Parse FSD — extract features and build checklist

Read the entire FSD (produced by the `fsd-writer` skill). Extract features from
**Section 4 (Functional Requirements)**, phases from **Section 3 (Implementation
Phases)**, interfaces from **Section 6 (Interface Specifications)**, and
architecture details from **Section 2 (System Architecture)**.

Build a feature checklist:

```
NEEDS_WIFI        → if project uses WiFi
NEEDS_BLE         → if project uses BLE
NEEDS_BLE_NUS     → if project uses Nordic UART Service
NEEDS_OTA         → if project supports firmware updates
NEEDS_MQTT        → if project uses MQTT
NEEDS_UDP_LOG     → always yes when NEEDS_WIFI=yes
NEEDS_CMD_HANDLER → if NEEDS_BLE_NUS=yes
OTA_TRIGGER       → ble / http / both
```

Record project-specific values:
- WiFi AP SSID for captive portal (e.g. `"KB-Setup"`)
- BLE device name (e.g. `"iOS-KB"`)
- OTA URL (e.g. `"http://esp32-workbench.local:8080/firmware/ios-keyboard/ios-keyboard.bin"`)
- NVS namespace
- Any project-specific command opcodes

### Step 3: Audit firmware code

Inventory the project's source files. For each module in the template reference table, check:
- Does the file exist?
- Does it contain the required log patterns?
- Does it match the template's API signatures?

Also check:
- `CMakeLists.txt` — are all sources listed in SRCS? Are all PRIV_REQUIRES present?
- `sdkconfig.defaults` — are required options set?
- `partitions.csv` — does it have OTA slots (if NEEDS_OTA)?
- `app_main.c` — what's the init order? Is "Init complete" the last log?
- `components/dns_server/` — does it exist (if NEEDS_WIFI)?

### Step 4: Add missing modules (Enforce Contract 2)

Follow this decision tree. For each missing module, copy from
`workbench-test/main/` and customize. These templates implement the exact process
flows required by the **Workbench Compatibility Contract** (Contract 2) — WiFi
captive portal, BLE NUS command protocol, OTA via HTTP endpoint, and the
canonical boot sequence:

```
Does the project use WiFi? --NO--> Skip WiFi, UDP, OTA
  |YES
  v
Has udp_log.c? --YES--> Check log message exists
  |NO --> Copy from workbench-test
  v
Has wifi_prov.c? --YES--> Check AP_SSID, check wifi_prov_reset()
  |NO --> Copy from workbench-test, customize AP_SSID
  v
Needs OTA? --NO--> Skip
  |YES
  v
Has ota.c? --YES--> Check OTA_DEFAULT_URL, check log messages
  |NO --> Copy from workbench-test, customize URL
         Ensure partitions.csv has OTA slots
  v
Uses BLE? --NO--> Skip BLE modules
  |YES
  v
Has ble_nus.c? --YES--> Check device name
  |NO --> Copy from workbench-test, customize name
  v
Has cmd_handler.c? --YES--> Check CMD_OTA + CMD_WIFI_RESET exist
  |NO --> Copy from workbench-test, add project-specific opcodes
  v
Has heartbeat task? --YES--> Check "alive" pattern
  |NO --> Add to app_main.c
  v
Has "Init complete"? --YES--> Done
  |NO --> Add to end of app_main()
```

When copying files:
- Read the template source from workbench-test
- Customize project-specific values (AP_SSID, BLE name, OTA URL, NVS namespace)
- Add or remove project-specific opcodes in cmd_handler
- Write the customized file to the project

### Step 5: Enforce Contract 1 — Required Log Messages

Check every required log pattern from the **Workbench Compatibility Contract**
(Contract 1) table. For each missing pattern:
- Add the exact log statement at the correct location
- Use the exact format string — the workbench skills grep for these patterns
- Do not paraphrase, reformat, or localize the strings
- These are infrastructure, not debug aids — they must survive any "clean up
  logging" refactors

### Step 6: Update build config

Update the project's build configuration:

**CMakeLists.txt** — add new source files to SRCS, add any missing PRIV_REQUIRES:
- `nvs_flash`, `esp_wifi`, `esp_netif`, `esp_event` (WiFi)
- `esp_http_server`, `esp_http_client`, `esp_https_ota` (OTA)
- `bt` (BLE)
- `dns_server`, `lwip` (captive portal)
- `esp_app_format`, `app_update` (OTA + status endpoint)
- `json` (OTA HTTP endpoint)
- Add `EMBED_FILES "portal.html"` if wifi_prov uses captive portal

**partitions.csv** — copy from `test-firmware/` (`partitions-4mb.csv` for 4MB flash, `partitions.csv` for 8MB+). See `esp-idf-handling` skill for flash size and partition table rules.

**sdkconfig.defaults** — verify required options are set (NimBLE, partition table, flash size, etc.). See `esp-idf-handling` skill for flash size defaults.

**dns_server component** — copy `workbench-test/components/dns_server/` if project needs captive portal but doesn't have it

### Step 7: Update app_main.c

Ensure the canonical init order:
1. NVS init (with erase-on-corrupt fallback)
2. Boot count increment
3. `esp_netif_init()` + `esp_event_loop_create_default()`
4. `udp_log_init("esp32-workbench.local", 5555)`
5. Register IP event handler for HTTP server
6. `wifi_prov_init()`
7. `ble_nus_init(cmd_handler_on_rx)`
8. Heartbeat task (`alive_task`)
9. `ESP_LOGI(TAG, "Init complete, running event-driven")`

The exact implementation can vary, but the order must be: NVS → netif → UDP → WiFi → BLE → cmd handler → heartbeat → "Init complete".

### Step 8: Write "7. Operational Procedures" (Workbench Operations)

Replace `## 7. Operational Procedures` in the FSD with workbench-specific operational content covering: hardware setup, flashing, WiFi provisioning, BLE commands, OTA updates, HTTP endpoints, and log monitoring. This section becomes a standalone operations guide with no test cases.

### Step 9: Write "8. Verification & Validation" (Testing)

Replace `## 8. Verification & Validation` with workbench test cases. Write phase verification tables where every FSD feature appears in exactly one table, test procedures reference Section 7 (not duplicate), and every step has concrete success criteria.

### Step 10: Write "9. Troubleshooting Guide" and "10. Appendix"

Replace with workbench-specific diagnostics (logging strategy, failure-to-fix mapping table).

For detailed templates, markdown examples, and rules for Steps 8-10, read `references/fsd-writing-guide.md`.

### Step 11: Build verification

```bash
cd <project-root> && idf.py build
```

Fix any compilation errors. Common issues:
- Missing PRIV_REQUIRES in CMakeLists.txt
- Missing `#include` directives
- Function signature mismatches between header and implementation

### Step 12: Summary report

List what was added/changed:
- New files copied from workbench-test (with customizations noted)
- Modified files (what changed)
- Build result
- Any issues found and fixed

## Completeness Checklist

After completing all steps, verify:

**Firmware integration (Steps 1–7):**
- [ ] Every module needed by the feature checklist exists
- [ ] Every required log pattern is present
- [ ] CMakeLists.txt has all sources and dependencies
- [ ] app_main.c follows the canonical init order
- [ ] "Init complete" is the last log message in app_main()

**Section 7 — Operational Procedures (Step 8):**
- [ ] Hardware table documents all slots (including dual-USB if applicable)
- [ ] All project-specific values are filled in (no `<placeholder>` the AI must guess)
- [ ] WiFi provisioning includes all three values: `portal_ssid`, `ssid`, `password`
- [ ] WiFi provisioning documents both phases (ensure AP mode + provision via portal)
- [ ] BLE command reference table covers every opcode
- [ ] OTA workflow covers upload + both trigger methods (BLE and HTTP)
- [ ] HTTP endpoints documented with relay examples
- [ ] Section 7 works as a standalone operations guide

**Section 8 — Verification & Validation (Step 9):**
- [ ] Every FSD feature appears in a phase verification table
- [ ] Every implementation phase has a verification table
- [ ] Test procedures reference (not duplicate) Section 7
- [ ] Every test step has concrete success criteria

**Sections 9 & 10 — Troubleshooting & Appendix (Step 10):**
- [ ] Logging strategy explains when to use serial monitor vs UDP logs
- [ ] Troubleshooting covers likely failure modes

**Build (Step 11):**
- [ ] Project builds cleanly with `idf.py build`

## Workbench Skills Reference

| Skill | Key endpoints | What it enables |
|-------|-------------|-----------------|
| `esp32-tester-serial` | `GET /api/devices`, `POST /api/serial/reset` | Device discovery, remote flashing (esptool via RFC2217), GPIO download mode, crash-loop recovery |
| `esp32-tester-udplog` | `POST /api/serial/monitor`, `GET /api/udplog` | Serial monitor with pattern matching, UDP log collection, boot/crash capture |
| `esp32-tester-wifi` | `POST /api/enter-portal`, `GET /api/wifi/ap_status`, `GET /api/wifi/scan`, `POST /api/wifi/http`, `GET /api/wifi/events` | Captive portal provisioning, AP control, WiFi on/off testing, HTTP relay, event monitoring |
| `esp32-tester-gpio` | `POST /api/gpio/set`, `GET /api/gpio/status` | Boot mode control, hardware reset, button simulation, GPIO probe |
| `esp32-tester-ota` | `POST /api/firmware/upload`, `GET /api/firmware/list`, `POST /api/wifi/http` | Firmware upload/serve, OTA trigger via HTTP relay |
| `esp32-tester-ble` | `POST /api/ble/scan`, `POST /api/ble/connect`, `POST /api/ble/write`, `POST /api/ble/disconnect` | BLE scan, connect, GATT write, remote BLE testing |
