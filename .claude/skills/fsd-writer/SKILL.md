---
name: fsd-writer
description: >
  Generates or updates a Functional Specification Document (FSD), mainly
  for ESP32 projects. Converts rough project descriptions into structured FSDs with
  requirements, test cases, and traceability. Supports initial generation
  and incremental evolution. Triggers on "FSD", "fsd", "write FSD",
  "create FSD", "generate FSD", "new FSD", "update FSD", "evolve FSD",
  "functional spec", "specification document".
---

# FSD Writer Skill

A general-purpose skill that turns a rough, unstructured project description into
a structured Functional Specification Document (FSD) in Markdown, or surgically
updates an existing FSD with new requirements, corrections, or expansions.

## 1. Purpose

This skill:

- Generates a canonical FSD from a rough description (**initial mode**).
- Updates or expands an existing FSD using a delta description (**evolve mode**).
- Dynamically adjusts depth and verbosity based on inferred system complexity.
- Ensures full requirement traceability (FR / NFR <-> test coverage).
- Surfaces risks, assumptions, and constraints as first-class content.
- Produces deterministic, agent-consumable Markdown.

It supports embedded systems, networking, SDR, IoT, cloud backends, mobile apps,
multi-service orchestrations, and hybrid hardware/software projects.

## 2. Invocation

### 2.1 Mode A — Initial Generation

Start a new FSD from scratch.

```
/fsd-writer
<rough description text>
```

Behavior:
1. Parse the rough description.
2. Ask clarifying questions if critical information is missing (Section 5).
3. Infer complexity tier (Section 6).
4. Generate the complete FSD (Section 7).
5. Write the file (Section 10).

### 2.2 Mode B — Evolve Existing FSD

Update, expand, refactor, or correct an already existing FSD.

```
/fsd-writer update <path-to-existing-fsd>
<delta description — changes, additions, clarifications, new constraints>
```

If no path is given, search the project for an existing FSD:
1. Check `Documents/*-fsd.md`
2. Check `Documents/*-FSD.md`
3. Check `docs/*-fsd.md`
4. Check project root for `*-fsd.md`

Behavior:
1. Read the existing FSD in full using the **Read** tool.
2. Parse the delta description.
3. Ask clarifying questions only if the delta introduces architectural ambiguity.
4. Apply changes surgically — preserve all unaffected sections verbatim.
5. Regenerate only the sections affected by the delta.
6. Maintain numbering, cross-references, and the traceability matrix automatically.
7. Write the updated file using the **Edit** tool (preferred) or **Write** tool
   (if changes are too extensive for surgical edits).

## 3. Tool Usage

This skill uses the following Claude Code tools:

| Tool | When |
|------|------|
| **Read** | Read existing FSD (evolve mode), read project files for context |
| **Glob** | Find existing FSD files, scan project structure for architecture clues |
| **Grep** | Search for protocols, frameworks, dependencies in project source |
| **Write** | Create new FSD file (initial mode) or full rewrite |
| **Edit** | Surgical updates to existing FSD sections (evolve mode) |
| **AskUserQuestion** | Clarifying questions when critical info is missing |
| **Task** (Explore) | Deep codebase exploration when the project has existing source code |

### 3.1 Context Gathering (Before Generation)

Before writing the FSD, the skill should gather context from the project when
source code exists:

1. **Glob** for project structure — `**/*.c`, `**/*.h`, `**/*.py`, `**/*.ts`,
   `**/Cargo.toml`, `**/package.json`, `**/CMakeLists.txt`, `**/go.mod`, etc.
2. **Grep** for protocols and frameworks — BLE, WiFi, MQTT, HTTP, gRPC, REST,
   WebSocket, LoRa, OCPP, etc.
3. **Read** key config files — `sdkconfig.defaults`, `platformio.ini`,
   `docker-compose.yml`, `Makefile`, build configs.
4. Use findings to pre-fill architecture sections and reduce clarifying questions.

### 3.2 Evolve Mode — Diff Discipline

When updating an existing FSD:

- **Never regenerate the entire file.** Only touch sections affected by the delta.
- Use the **Edit** tool with precise `old_string` / `new_string` pairs.
- If a delta adds a new phase, insert it and renumber subsequent phases.
- If a delta adds new FRs, assign the next available FR number in the correct group.
- Always update the traceability matrix when FRs or tests change.
- If the delta invalidates existing content, remove or revise it — do not leave
  contradictions.

## 4. Interaction Model (Clarifying Questions)

### 4.1 When to Ask

The skill must ask clarifying questions when critical architecture-affecting
information is missing. "Critical" means it affects:

- System architecture or component decomposition
- Protocol selection (BLE vs WiFi vs LoRa vs cellular)
- Interface definitions (API style, command format)
- Safety or regulatory constraints
- Multi-phase decomposition
- Hardware or platform selection
- External integrations (MQTT broker, cloud service, Home Assistant, etc.)

### 4.2 How to Ask

Use the **AskUserQuestion** tool with:
- 1-3 precise questions per round (never a wall of questions)
- Multiple-choice options where possible (with sensible defaults)
- Questions phrased to unblock the FSD, not to explore nice-to-haves

Example:

```
Questions:
1. "How does the device connect?" → Options: WiFi, BLE, LoRa, Cellular, USB only
2. "Do you need OTA firmware updates?" → Options: Yes (WiFi), Yes (BLE DFU), No
3. "Who is the primary operator?" → Options: End user, Installer/technician, Automated backend
```

### 4.3 When to Infer Instead of Asking

The skill may silently infer reasonable defaults when:
- The detail does not significantly change high-level architecture, AND
- The cost of being wrong is low.

Safe inferences:
- "web API" mentioned → assume HTTP + JSON
- "logs" mentioned → assume structured logging to console / file / serial
- "dashboard" mentioned → describe generic "dashboard system" without naming tools
- "database" mentioned without type → assume PostgreSQL for relational, SQLite for embedded

When inferring, mark the inference in the FSD with `(assumed)` or group them in
**Section 5: Risks, Assumptions & Dependencies**.

## 5. Complexity Scaling Rules

The skill dynamically scales FSD depth based on inferred system complexity (Low / Medium / High). Complexity is inferred from component count, protocol count, external integrations, real-time constraints, and domain.

For the full complexity tiers table, complexity signals, and per-section scaling behavior matrix, read `references/complexity-scaling.md`.

## 6. Information Extraction & Inference Rules

Given the rough description, the skill must extract or infer the following:

### 6.1 Project Name

Derive a short, descriptive name:
- "ESP32 BLE HID Keyboard"
- "Solar-Aware EV Charging Controller"
- "LoRa Mailbox Notifier"

### 6.2 System Purpose & Goals

Extract in 2-4 sentences: what problem is solved, for whom, in what environment.

### 6.3 System Components

Identify major components:
- Hardware / platforms (MCU, SBC, server, cloud)
- Software services / apps / daemons
- User-facing components (mobile app, web UI, CLI)
- External integrations (Home Assistant, OCPP backend, MQTT broker)

If components are implied but not explicit, infer and mark as assumptions.

### 6.4 Functional Requirements (FR)

Convert each described behavior into FR-x.y items:
- Group logically (Communication, Data Processing, User Interaction, Safety)
- Assign priority: **Must** / **Should** / **May**
- Use "shall" language: "The system shall..."

Example:
> "Device sends sensor readings every minute and on threshold events."

Becomes:
- **FR-1.1** [Must]: The device shall send periodic sensor measurements at a
  configurable interval (default: 60 s).
- **FR-1.2** [Must]: The device shall send an immediate measurement when a
  threshold condition is met.

### 6.5 Non-Functional Requirements (NFR)

Extract or infer key NFRs with priorities:
- Performance (latency, throughput)
- Reliability / uptime
- Accuracy / precision
- Scalability
- Power consumption (embedded)
- Security and privacy (authentication, encryption, access control)

### 6.6 Interfaces & Data Models

From the description and answers:
- Identify protocols (BLE, WiFi, USB HID, HTTP, MQTT, LoRa, OCPP, etc.)
- Describe endpoints, characteristics, topics, commands
- Define payload structures (fields, units, types)
- Specify direction (client -> server, device -> cloud, etc.)

### 6.7 Phases

At minimum define:
- **Phase 1**: Infrastructure / Foundation
- **Phase 2**: Core Functional Features
- **Phase 3+** (optional): Optimization, UX, analytics, etc.

Each phase must include: Scope, Deliverables, Exit Criteria, Dependencies.

### 6.8 Operational Procedures

Extract or infer:
- Deployment / flashing / installation
- Configuration / provisioning
- Normal operation workflows
- Failure recovery (reset, re-provisioning, safe-mode)

If not covered in the description, provide a generic but plausible set for the
domain.

### 6.9 Verification & Validation

From extracted requirements:
- Create test cases that verify FRs and critical NFRs
- Organize by phase and feature area
- Use structured format: Objective, Preconditions, Steps, Expected Result
- Build the traceability matrix (Section 8)

## 7. Canonical FSD Structure

All generated or updated FSDs must conform to the canonical structure (Sections 1-10: System Overview, Architecture, Phases, Requirements, Risks, Interfaces, Operational Procedures, V&V, Troubleshooting, Appendix). For the full template with all subsections and section inclusion rules, read `references/canonical-fsd-structure.md`.

## 8. Traceability Matrix (Mandatory)

Every FSD must contain a traceability matrix in Section 8.4.

Rules:
- Every FR and NFR with priority **Must** or **Should** must appear in >= 1 test.
- Every test case must reference the FR(s) / NFR(s) it validates.
- Requirements with no test coverage must be flagged as `GAP`.
- **May**-priority requirements may have test coverage but it is not mandatory.
- When updating an FSD (evolve mode), the matrix must be regenerated to reflect
  any added, removed, or changed requirements and tests.

## 9. Formatting & Style Rules

- Output pure Markdown — no HTML tags.
- Use heading levels exactly as defined in Section 7.
- Use bullet lists for requirements; tables for tests, interfaces, and diagnostics.
- Use concise, unambiguous engineering language.
- Use **"shall"** for requirements ("The system shall...").
- Use **"must"** for constraints ("The device must operate on 3.3V").
- Avoid marketing language, filler, and subjective qualifiers.
- Keep requirement IDs stable across evolve updates — never renumber existing IDs
  unless explicitly asked to refactor numbering.
- Use `(assumed)` inline for inferred details.

## 10. Output File Naming & Location

### 10.1 Default Location

If the user does not specify a target path:

```
Documents/<project-name-kebab-case>-fsd.md
```

Create the `Documents/` directory if it does not exist.

Examples:
- `Documents/esp32-ble-hid-keyboard-fsd.md`
- `Documents/solar-ev-charging-controller-fsd.md`
- `Documents/lora-mailbox-notifier-fsd.md`

### 10.2 Explicit Path

If the user provides a path, use it exactly. Do not relocate or rename the file.

### 10.3 Evolve Mode

When updating, write to the same file that was read. Confirm the path before
writing if it was auto-detected.

## 11. Example Output Snippet

For a complete example FSD snippet (medium-complexity BLE HID Keyboard project) showing expected tone, structure, and detail level, read `references/example-output.md`.

## 12. Evolve Mode -- Detailed Behavior

When updating an existing FSD, follow strict rules for what to preserve, update, add, and remove. Key principles: never renumber existing IDs, always update the traceability matrix, flag contradictions before overwriting. For the complete evolve mode rules (preserve/update/add/remove/conflict resolution), read `references/evolve-mode.md`.

## 13. Quality Checklist

After generating or updating an FSD, the skill must verify:

- [ ] Every **Must** and **Should** FR/NFR appears in the traceability matrix.
- [ ] Every traceability row with no test is marked `GAP`.
- [ ] No `<placeholder>` or `TODO` text remains (flag to user if unresolvable).
- [ ] Section numbering is sequential with no gaps.
- [ ] All phases have scope, deliverables, and exit criteria.
- [ ] The file has been written to the correct path.
- [ ] (Evolve mode) Unaffected sections are identical to the original.

Report any checklist failures to the user before finalizing.

## 14. Standard Test Libraries

Include standard test cases in the FSD based on detected project features.
Tests are conditionally included — scan the FSD and source code for detection
patterns, then pull in the matching test specs from `references/`.

### Feature Detection

| Feature | Detection Patterns | Test Spec | Include |
|---------|-------------------|-----------|---------|
| **WiFi STA** | `WiFi.begin`, `esp_wifi_connect`, "STA mode" | `wifi-test-spec.md` | WIFI-001–005, EC-100–101, EC-110–111, EC-115 |
| **Captive Portal** | `WiFi.softAP`, "captive portal", "AP mode" | `captive-portal-test-spec.md` | AP-001–006, CP-001–006, TC-CP-100–102 |
| **MQTT** | `PubSubClient`, `esp_mqtt`, "MQTT broker" | `mqtt-test-spec.md` | MQTT-001–031, TC-MQTT-100–103 |
| **BLE** | `NimBLE`, `esp_ble`, `BLEDevice`, "BLE", "GATT" | `ble-test-spec.md` | BLE-001–032, TC-BLE-100–103 |
| **BLE NUS** | `NUS`, `6E400001`, "Nordic UART" | `ble-test-spec.md` | BLE-020–023, TC-BLE-101 |
| **OTA** | `esp_ota`, `httpUpdate`, "firmware update", "OTA" | `ota-test-spec.md` | OTA-001–013, TC-OTA-100–102 |
| **USB HID** | `tinyusb`, `tusb_`, "HID", "keyboard", "USB device" | `usb-hid-test-spec.md` | HID-001–022, TC-HID-100–103 |
| **NVS** | `Preferences`, `nvs_`, "NVS", "stored credentials" | `nvs-test-spec.md` | NVS-001–024, TC-NVS-100–103 |
| **Watchdog** | `esp_task_wdt`, `TWDT`, "watchdog" | `watchdog-test-spec.md` | WDT-001–022, TC-WDT-100–102 |
| **Logging** | `ESP_LOG`, `udp_log`, "UDP logging", "serial log" | `logging-test-spec.md` | LOG-001–026, TC-LOG-100–103 |
| **Ethernet** | `W5500`, `ETH.begin`, "dual network" | `wifi-test-spec.md` | TEST-001–005, EC-100 |

### Workflow

1. Scan the FSD requirements and source code for detection patterns above
2. For each detected feature, read the corresponding `references/*.md` file
3. Copy relevant requirements, functional tests, and edge cases into the FSD
4. Update project-specific placeholders (SSIDs, IPs, timeouts, etc.)
5. Add all included tests to the traceability matrix (Section 8.4)

### Test Spec References

| File | Coverage |
|------|----------|
| [references/wifi-test-spec.md](references/wifi-test-spec.md) | WiFi STA connection, signal, DHCP, ethernet test mode |
| [references/captive-portal-test-spec.md](references/captive-portal-test-spec.md) | AP mode, captive portal, provisioning, credential change |
| [references/mqtt-test-spec.md](references/mqtt-test-spec.md) | Broker connection, pub/sub, QoS, LWT, reconnect, buffering |
| [references/ble-test-spec.md](references/ble-test-spec.md) | BLE advertising, GATT, NUS, pairing, coexistence |
| [references/ota-test-spec.md](references/ota-test-spec.md) | OTA download, rollback, integrity, power loss recovery |
| [references/usb-hid-test-spec.md](references/usb-hid-test-spec.md) | USB enumeration, keyboard layouts, latency, stuck key prevention |
| [references/nvs-test-spec.md](references/nvs-test-spec.md) | Config persistence, factory reset, corruption recovery, credentials |
| [references/watchdog-test-spec.md](references/watchdog-test-spec.md) | Software/hardware WDT, memory watchdog, false trigger prevention |
| [references/logging-test-spec.md](references/logging-test-spec.md) | Serial logging, UDP logging, log levels, crash capture |
