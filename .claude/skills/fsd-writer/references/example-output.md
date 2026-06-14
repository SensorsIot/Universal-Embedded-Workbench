# Example FSD Output

The following snippet demonstrates the expected tone, structure, and level of
detail for a medium-complexity project, written in the **layer-grouped Parts
scheme** (see `references/canonical-fsd-structure.md`). Note how each component is
a self-contained chapter under a layer Part, requirements live inside the chapter
they constrain, and traceability is a pointer to a generated matrix — not a
hand-filled table.

```markdown
# ESP32 BLE HID Keyboard — Functional Specification Document (FSD)

## 1. System Overview

The ESP32-S3 BLE HID Keyboard System enables a smartphone app to transmit text
commands via BLE to an ESP32-S3 microcontroller, which converts them into USB HID
keyboard events for any connected host computer. It eliminates Bluetooth keyboard
pairing on the host side and provides deterministic, low-latency input suitable
for accessibility tools, automation, and assistive typing.

**Goals:** reliable BLE→HID translation < 50 ms; layouts US/DE/FR; OTA over WiFi.
**Non-goals:** not a general BLE-to-USB bridge; no media keys in Phase 1-2.
**Users:** end users needing assistive input; installers who flash & provision.

## 2. System Architecture

### 2.1 Logical Architecture
Smartphone app → (BLE NUS) → ESP32-S3 → (USB HID) → host computer. A WiFi path
serves OTA and a `/status` endpoint.

### 2.2 Hardware / Platform Architecture
ESP32-S3 (USB-OTG), powered from the host USB bus.

### 2.3 Software Architecture
FreeRTOS tasks: BLE rx, HID tx, WiFi/OTA. Config + layout in NVS.

### 2.4 Component Layering
(stacked layer diagram — application on top, foundation at the bottom)
- **L2 Application logic:** Text→HID translation; layout selection.
- **L1 Interfaces:** BLE NUS handler; USB HID report builder; HTTP status/OTA handler.
- **L0 Foundation:** NimBLE stack; TinyUSB stack; WiFi; OTA partition/rollback; NVS.

## 3. Implementation Phases
- **Phase 1 — Foundation:** BLE link up, USB HID enumerated. Exit: host sees a keyboard.
- **Phase 2 — Core:** text→HID translation, layouts, OTA. Exit: end-to-end typing + OTA rollback.

## 4. Risks, Assumptions & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| HID descriptor rejected by host OS | Medium | High | Test macOS/Windows/Linux in Phase 2 |
| BLE drop mid-entry | Low | Medium | Reconnect + buffering |

**Assumptions:** host provides 500 mA USB bus power (assumed); iOS primary, Android deferred (assumed).
**Dependencies:** ESP-IDF v5.x TinyUSB; NimBLE.

# Part A — Application Logic (L2)

## 5. Text → HID Translation

**Purpose.** Convert a received UTF-8 text string into a sequence of USB HID
keyboard reports for the active layout.

**Requirements.**
- **FR-5.1** [Must]: The device shall convert received text into USB HID reports
  and deliver them to the host within 50 ms of receipt.
- **FR-5.2** [Should]: The device shall apply the active keyboard layout when
  mapping characters to keycodes.
- **NFR-5.1** [Must]: Per-character translation latency shall not exceed 50 ms
  under normal operation.

**Decision logic.** For each rune: look up (keycode, modifier) in the active
layout table → emit key-down report → emit key-up report. Unmappable runes are
dropped and counted (see §13 Logging).

**Failure modes.** Empty/oversized string → ignored; layout table missing →
fall back to US.

## 6. Layout Selection

**Purpose.** Select the active layout (US/DE/FR) and persist it.
- **FR-6.1** [Should]: The device shall accept a layout-selection command over BLE
  and persist the choice across reboot.

# Part B — Interfaces (L1)

## 7. BLE NUS Interface

**Purpose & peer.** Receives text and commands from the smartphone app over the
Nordic UART Service.
- **FR-7.1** [Must]: The device shall accept text input via BLE NUS from a
  connected smartphone.

**Schema.** RX characteristic: UTF-8 bytes (text) or a `CMD:` prefixed control
line (e.g. `CMD:LAYOUT=DE`). Direction: phone → device.
**Failure modes.** Malformed `CMD:` → NAK log line, no state change.

## 8. USB HID Interface

**Purpose & peer.** Presents a standard boot-keyboard to the host; emits reports.
- **FR-8.1** [Must]: The device shall enumerate as a USB HID boot keyboard.

**Schema.** 8-byte boot report (modifier, reserved, 6 keycodes). Direction: device → host.

## 9. HTTP Status & OTA Interface

- **FR-9.1** [Must]: The device shall accept OTA firmware uploads over WiFi.
- **FR-9.2** [Should]: The device shall report firmware version at `GET /status`.

# Part C — Foundation / Transport (L0)

## 10. WiFi / OTA Platform

**Purpose.** ESP-IDF WiFi + OTA partition scheme; we configure and use it, we do
not implement it. Tested **transitively** via §9.
- **NFR-10.1** [Must]: The device shall roll back to the previous partition on a
  failed OTA boot.

## 11. BLE & USB Stacks

NimBLE and TinyUSB — configured, not owned. Exercised transitively via §7/§8.

# Part D — Cross-cutting Concerns

## 12. Security
- **NFR-12.1** [Should]: OTA images shall be signature-verified before activation.

## 13. Logging / Observability
Serial structured logs; dropped-rune and BLE-NAK counters.

# Part E — Operations & Verification

## 14. Operational Procedures
Flash (§3 Phase 1) → pair app over BLE (§7) → type (§5) → update via OTA (§9/§10
rollback on failure). Recovery: hold BOOT 5 s to clear NVS layout (§6).

## 15. Verification & Validation

### 15.0 Test Architecture
Tiers: **host** (layout-table mapping, report builder — pure functions),
**target** (BLE rx, USB enumeration, OTA), **bench** (real phone + real host).
L0 (WiFi/BLE/USB stacks) tested transitively; L1 pure cores at host tier, wire/flow
at target; L2 translation at host tier.

### 15.1 Acceptance Tests
End-to-end: type a paragraph in each layout on macOS/Windows/Linux; OTA + forced
rollback.

### 15.2 Traceability
Generated — see `tests/coverage-matrix.md` (component × tier) and `tests/gaps.md`
(uncovered requirements), produced by the traceability tool from the FR/NFR IDs in
these chapters and the test specs. Not hand-maintained.

## Appendix
Constants: MAX_TEXT_LEN, report rate, OTA partition names, `/status` JSON shape.
```
