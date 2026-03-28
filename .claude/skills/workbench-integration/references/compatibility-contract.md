# Workbench Compatibility Contract

The workbench is not a passive observer -- it actively drives the device through
BLE commands, HTTP relay, captive portal automation, and serial/UDP log parsing.
For this to work, the firmware **must** conform to two contracts:

## Contract 1: Required Log Messages

The workbench skills detect device state by grepping serial and UDP log output
for specific format strings. These are **not optional debug messages** -- they are
**required infrastructure**. If a log message is missing or uses a different
format string, the corresponding workbench skill will fail to detect the event.

The firmware must emit these exact strings at the specified locations:

| Pattern | Workbench skill that needs it | Where | Why the workbench needs it |
|---------|-------------------------------|-------|---------------------------|
| `"Init complete"` | serial monitor | End of app_main() | Confirms boot finished; workbench waits for this before proceeding |
| `"alive %lu"` | serial monitor | Heartbeat task | Proves device is running, not hung |
| `"OTA succeeded"` / `"OTA failed"` | OTA skill | OTA task | Confirms OTA result; workbench blocks until one appears |
| `"OTA update requested"` | BLE skill | cmd_handler | Confirms BLE OTA command was received |
| `"WiFi reset requested"` | BLE skill | cmd_handler | Confirms BLE WiFi reset command was received |
| `"WiFi credentials erased"` | WiFi skill | wifi_prov_reset() | Confirms NVS wipe before reboot into AP mode |
| `"INSERT: %.*s"`, `"ENTER"`, `"BACKSPACE x%d"` | UDP log skill | cmd_handler | Verifies BLE text commands are being processed |
| `"UDP logging -> %s:%d"` | logging skill | udp_log_init() | Confirms UDP log channel is active |
| `"No WiFi credentials"` | WiFi skill | wifi_prov_init() | Confirms device will enter AP mode (no stored creds) |
| `"AP mode: SSID='%s'"` | WiFi skill | WiFi AP start | Workbench detects AP name to drive captive portal |
| `"Portal page requested"` | WiFi skill | portal_get_handler() | Confirms workbench HTTP request reached the portal |
| `"Credentials saved"` | WiFi skill | connect_post_handler() | Confirms portal form submission succeeded |
| `"STA mode, connecting to '%s'"` | WiFi skill | start_sta() | Confirms device is attempting WiFi connection |
| `"STA got IP"` | WiFi skill | wifi_event_handler() | Confirms device joined the network; workbench proceeds |
| `"STA disconnect, retry"` | WiFi skill | wifi_event_handler() | Diagnoses WiFi connection failures |
| `"BLE NUS initialized"` | BLE skill | BLE init | Confirms BLE is ready; workbench can start scanning |

Step 5 of the procedure ensures every required pattern exists in the firmware.

## Contract 2: Required Process Flows

The workbench automates device operations by driving specific sequences. The
firmware **must implement these flows exactly as described** -- alternative
implementations (e.g., BLE-based provisioning instead of captive portal,
SmartConfig instead of SoftAP) are not compatible with the workbench.

### WiFi Provisioning Flow (Captive Portal)

The workbench drives this exact sequence:

```
1. Device boots with no WiFi credentials
   -> firmware logs "No WiFi credentials"
   -> firmware starts SoftAP with configured SSID
   -> firmware logs "AP mode: SSID='<SSID>'"

2. Workbench connects to device's SoftAP (via enter-portal)
   -> workbench sends HTTP GET to portal page
   -> firmware logs "Portal page requested"
   -> workbench submits credentials via POST
   -> firmware logs "Credentials saved"

3. Device switches to STA mode
   -> firmware logs "STA mode, connecting to '<SSID>'"
   -> on success: firmware logs "STA got IP"
   -> on failure: firmware logs "STA disconnect, retry" (with backoff)
```

The firmware must use: SoftAP -> captive portal (HTTP) -> NVS credential storage ->
STA connect. The `wifi_prov.c` template implements this exactly.

### WiFi Reset Flow (BLE-triggered)

```
1. Workbench sends CMD_WIFI_RESET via BLE NUS
   -> firmware logs "WiFi reset requested"
   -> firmware erases WiFi credentials from NVS
   -> firmware logs "WiFi credentials erased"
   -> firmware reboots
   -> device enters AP mode (see provisioning flow above)
```

### OTA Update Flow

```
1. Workbench uploads firmware binary to its HTTP server
2. Workbench triggers OTA via one of:
   a. BLE: sends CMD_OTA via NUS -> firmware logs "OTA update requested"
   b. HTTP relay: POST to device's /ota endpoint
3. Device downloads firmware from workbench URL
   -> on success: firmware logs "OTA succeeded", reboots
   -> on failure: firmware logs "OTA failed", stays on current firmware
```

The firmware must expose an HTTP `/ota` endpoint that accepts
`{"url": "<firmware-url>"}` and performs esp_https_ota (or esp_http_ota).
The `ota.c` template implements this exactly.

### BLE Command Protocol (NUS)

```
1. Workbench scans for device by BLE name
2. Workbench connects to device's NUS service
3. Workbench writes binary commands to NUS RX characteristic:
   - Each command starts with a 1-byte opcode
   - Followed by opcode-specific payload
4. Device logs each command execution via UDP/serial
```

The firmware must use NimBLE with Nordic UART Service. The `ble_nus.c` and
`cmd_handler.c` templates implement this exactly.

### Boot Sequence

The firmware must initialize in this order:
NVS -> netif/event loop -> UDP log -> WiFi provisioning -> BLE -> heartbeat ->
"Init complete"

This order ensures: UDP logging is ready before WiFi events fire, WiFi is up
before BLE (which may trigger WiFi reset), and "Init complete" is the last
message (so the workbench knows init is done).

## Compatibility Validation

In **Step 2** (Parse FSD), after extracting features, the skill must check for
compatibility conflicts:

| Conflict | Detection | Resolution |
|----------|-----------|------------|
| FSD specifies BLE provisioning instead of captive portal | FR mentions "BLE provisioning" or "SmartConfig" | Flag to user: workbench requires captive portal flow |
| FSD specifies MQTT-based OTA instead of HTTP | FR mentions MQTT OTA trigger | Flag to user: workbench requires HTTP `/ota` endpoint |
| FSD specifies custom BLE protocol instead of NUS | Interface spec shows non-NUS UUIDs | Flag to user: workbench requires NUS for BLE commands |
| No WiFi mentioned | Feature checklist NEEDS_WIFI=no | UDP logging and OTA are unavailable; document serial-only workflow |

If the project's architecture conflicts with a required flow, the skill must
**ask the user** whether to adapt the project or document a limited-compatibility
mode.
