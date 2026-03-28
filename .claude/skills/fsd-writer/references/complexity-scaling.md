# Complexity Scaling Rules

The skill dynamically scales the FSD depth based on inferred system complexity.

## Complexity Tiers

| Tier | Characteristics | Target Length | Phases |
|------|----------------|---------------|--------|
| **Low** | Single MCU/service, simple data flows, 1-2 interfaces | 3-5 pages | 1-2 |
| **Medium** | MCU + app, or multi-service, OTA, 2-4 protocols | 6-12 pages | 2-3 |
| **High** | Distributed system, multi-protocol, real-time constraints, regulatory | 15-25+ pages | 3-5 |

## Complexity Signals

Infer complexity from:
- Number of distinct components (devices, services, apps)
- Number of protocols (BLE, WiFi, MQTT, HTTP, LoRa, OCPP, Modbus, etc.)
- Number of external integrations (cloud, Home Assistant, third-party APIs)
- Presence of real-time constraints or safety requirements
- Domain (SDR, energy systems, medical -> automatically higher complexity)
- Multi-user or multi-tenant requirements

## Scaling Behavior

| FSD Section | Low | Medium | High |
|------------|-----|--------|------|
| System Overview | Brief paragraph | Full section | Full + stakeholder analysis |
| Architecture | Single diagram description | Logical + platform + software | All subsections, detailed |
| Phases | 1-2 phases, brief | 2-3 phases, full exit criteria | 3-5 phases, dependencies mapped |
| Requirements | 5-15 FRs, 3-5 NFRs | 15-30 FRs, 5-10 NFRs | 30+ FRs, 10+ NFRs, constraints |
| Risks & Assumptions | Bullet list | Table with mitigations | Full risk register |
| Interfaces | Inline descriptions | Tables per protocol | Full schemas, sequence descriptions |
| Operational Procedures | Bullet steps | Numbered procedures | Detailed with recovery paths |
| V&V | Checklist | Phase-based test tables | Full traceability matrix + acceptance |
| Troubleshooting | 3-5 common issues | Symptom-cause-fix table | Categorized diagnostic guide |
| Appendix | Constants only | Constants + examples | Constants + schemas + diagrams + logs |
