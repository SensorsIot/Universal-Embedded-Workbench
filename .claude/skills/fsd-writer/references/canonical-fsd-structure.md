# Canonical FSD Structure

All generated or updated FSDs must conform to this structure:

```markdown
# <Project Name> — Functional Specification Document (FSD)

## 1. System Overview
- Purpose
- Problem statement
- Users / stakeholders
- Goals & non-goals
- High-level system flow

## 2. System Architecture
### 2.1 Logical Architecture
- Subsystems
- Data flow
- Runtime interactions

### 2.2 Hardware / Platform Architecture
- Devices, nodes, servers
- Key hardware / runtime platforms
- Connectivity and power (if relevant)

### 2.3 Software Architecture
- Tasks / modules / services
- Boot sequence (if applicable)
- Persistence / storage
- Update model (OTA, rollout strategy, etc.)

## 3. Implementation Phases
### 3.1 Phase 1 — Infrastructure Foundation
### 3.2 Phase 2 — Core Functionality
### 3.3 Phase 3+ — Extensions / Enhancements

Each phase includes:
- Scope (what is included)
- Deliverables (artifacts, running features)
- Exit criteria (tests passed, demos, metrics)
- Dependencies (on previous phases or external factors)

## 4. Functional Requirements
### 4.1 Functional Requirements (FR)
- FR-x.y [Must/Should/May]: requirement text

### 4.2 Non-Functional Requirements (NFR)
- NFR-x.y [Must/Should/May]: requirement text

### 4.3 Constraints
- Technological, regulatory, environmental constraints

## 5. Risks, Assumptions & Dependencies
- Technical risks (with likelihood, impact, mitigation)
- Assumptions (mark items inferred by this skill with "(assumed)")
- External dependencies
- Environmental constraints
- Regulatory constraints

## 6. Interface Specifications
### 6.1 External Interfaces
- APIs, protocols, user-facing interfaces

### 6.2 Internal Interfaces
- Inter-module / inter-service communication

### 6.3 Data Models / Schemas
- Key entities, message formats, payload schemas

### 6.4 Commands / Opcodes
- (If embedded or custom protocol — omit section if not applicable)

## 7. Operational Procedures
- Deployment / installation / flashing
- Provisioning / configuration
- Normal operation workflows
- Maintenance procedures
- Recovery procedures (factory reset, re-provisioning, safe-mode)

## 8. Verification & Validation
### 8.1 Phase 1 Verification
| Test ID | Feature | Procedure | Success Criteria |
|---------|---------|-----------|-----------------|

### 8.2 Phase 2 Verification
| Test ID | Feature | Procedure | Success Criteria |
|---------|---------|-----------|-----------------|

### 8.3 Acceptance Tests
- End-to-end scenarios
- Performance / load / reliability tests (if applicable)

### 8.4 Traceability Matrix
| Requirement | Priority | Test Case(s) | Status |
|------------|----------|-------------|--------|
| FR-1.1     | Must     | TC-1.1, TC-1.2 | Covered |
| NFR-2.1    | Should   | TC-5.1      | Covered |
| FR-3.4     | Must     | ---         | GAP    |

## 9. Troubleshooting Guide
| Symptom | Likely Cause | Diagnostic Steps | Corrective Action |
|---------|-------------|-----------------|-------------------|

## 10. Appendix
- Constants, magic numbers, configuration defaults
- UUIDs, endpoints, topics, pinouts
- Timing diagrams, sequence descriptions
- Example logs, traces, payloads
```

## Section Inclusion Rules

Not every section applies to every project. The skill must:

- **Always include**: Sections 1, 2, 3, 4, 5, 7, 8 (with traceability matrix)
- **Include if applicable**: Section 6.4 (Commands/Opcodes) -- only for embedded or
  custom protocols
- **Include if complexity >= Medium**: Section 9 (Troubleshooting), full Appendix
- **Include if complexity = High**: All sections, fully expanded
- **Omit empty sections** rather than writing "N/A" -- but note the omission reason
  in a comment if it might confuse readers
