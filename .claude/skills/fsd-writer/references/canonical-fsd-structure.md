# Canonical FSD Structure

FSDs are organized **by architectural layer**, not by document-section type. The
body mirrors the §2.4 component layering: each interface, feature, foundation
service, and cross-cutting concern is its **own self-contained chapter**, and the
chapters are grouped under unnumbered **Part** dividers that correspond to the
layers (L2 → L1 → L0 → cross-cutting → operations & verification).

This is the "Parts scheme." It replaces the older flat layout (one global
*Functional Requirements* section, one global *Interface Specifications* section,
phase-organized verification) — see **Migration from the flat layout** at the end
for the section-by-section correspondence. The scheme was proven on a
High-complexity production FSD before being adopted as the standard.

## Why layer-grouped

- **One structure end to end.** The FSD body, the §2.4 diagram, the generated
  coverage matrix, and the test-spec files all share the same per-component
  spine. A reader (or an agent) finds everything about one interface in one place.
- **Chapters are self-contained.** A component's requirements, protocol, schema,
  behavior, and failure modes live together — not scattered across a global FR
  list and a separate interfaces section that drift apart as the FSD evolves.
- **The test strategy falls out of the architecture.** Layer → tier mapping
  (the §x.0 Test Architecture / `references/test-architecture.md`) applies chapter
  by chapter.

---

## The skeleton

```markdown
# <Project Name> — Functional Specification Document (FSD)

<!-- ============ FRONT MATTER (ungrouped chapters: why / what / plan) ============ -->

## 1. System Overview
- Purpose; problem statement; users / stakeholders
- Goals & non-goals
- High-level system flow

## 2. System Architecture
### 2.1 Logical Architecture            (subsystems, data flow, runtime interactions)
### 2.2 Hardware / Platform Architecture (devices, nodes, servers; connectivity/power)
### 2.3 Software Architecture            (tasks/modules/services, boot, persistence, update model)
### 2.4 Component Layering               (THE SPINE — the body Parts mirror this)
- The layered stack with a strict one-way dependency (each layer depends only on
  layers below it): **L0 Foundation/platform** (shared infra we configure & use
  but don't implement/test — SDK/library clients, managed services) → **L1
  Interfaces** (external-facing modules whose wire/handler logic we own) → **L2
  Application logic** (the project's own decision functions).
- The L0-vs-L1 line is **ownership**: did we implement and test the protocol? A
  library/managed client to an external service = foundation; a hand-written
  decoder/driver/handler = interface.
- Include a layered component diagram (stacked layer boxes, components on one row
  per layer). See `references/test-architecture.md` for profiles (embedded /
  cloud / mobile), the diagram convention, the Mermaid layout gotcha, and the
  ASCII fallback.
- State the **source-layout convention** so the implementation mirrors these
  layers: each component maps to its **own module** (an interface is never folded
  into the consumer that uses it); lower layers never depend on higher ones (invert
  via a callback/registration hook wired at the composition root); each interface's
  pure core is extracted as a free function for the fast tier. The FSD advises how
  to code, not just what to build — see `references/test-architecture.md`.

## 3. Implementation Phases
### 3.1 Phase 1 — Infrastructure Foundation
### 3.2 Phase 2 — Core Functionality
### 3.3 Phase 3+ — Extensions / Enhancements
Each phase: Scope · Deliverables · Exit criteria · Dependencies.
(A phase delivers across layers; phases are a roadmap, read before the component
chapters.)

## 4. Risks, Assumptions & Dependencies
- Technical risks (likelihood, impact, mitigation)
- Assumptions (mark inferred items "(assumed)")
- External / environmental / regulatory dependencies & constraints

<!-- ============ BODY (Parts mirror the §2.4 layers; chapters numbered flat) ============ -->

# Part A — Application Logic (L2)

## 5. <Feature / decision function 1>
## 6. <Feature / decision function 2>
   (one chapter per L2 feature — see "Chapter-internal structure" below)

# Part B — Interfaces (L1)

## 7. <Interface 1>
## 8. <Interface 2>
   (one chapter per interface, INCLUDING single-consumer ones)

# Part C — Foundation / Transport (L0)

## 9.  <Foundation service 1>
## 10. <Foundation service 2>
   (one chapter per L0 service — what we configure & use; tested transitively)

# Part D — Cross-cutting Concerns

## 11. Device / Service Identity
## 12. Configuration Catalog
## 13. Logging / Observability
## 14. Error Handling
## 15. Security
## 16. Build & Tooling
   (concerns that span components — include those that apply; omit the rest)

# Part E — Operations & Verification

## 17. Operational Procedures
- A lifecycle **reading path** (flash/deploy → provision → operate → reconfigure
  → recover) that **references** the component chapters above. It is a path, not a
  parallel spec — do not restate component detail here.

## 18. Verification & Validation
### 18.0 Test Architecture
- Test tiers = cost-ordered execution environments; name per platform (embedded:
  host / target / bench; cloud: unit / integration / staging). Place each
  behaviour at the **lowest tier where its bug can manifest**.
- Map tiers to the §2.4 layers: L0 tested **transitively**; L1 = pure core at the
  fast tier + wire/flow above; L2 = fast tier as pure functions.
- Reference a **generated** component × tier coverage matrix (rows = §2.4
  components by layer, columns = tiers). See `references/test-architecture.md`.
### 18.1 Acceptance Tests
- End-to-end scenarios; performance / load / reliability (if applicable).
### 18.2 Traceability
- **Pointer to the generated coverage matrix and gap report** — NOT a hand-filled
  table. The FSD declares requirement→test linkage (via stable IDs in each
  chapter and in the test specs); the traceability tool computes covered/GAP.
  See "Traceability" below.

<!-- ============ BACK MATTER ============ -->

## Appendices
- Constants, magic numbers, configuration defaults; UUIDs, endpoints, topics,
  pinouts; timing/sequence descriptions; example logs, traces, payloads.

## Related
- `[[wikilinks]]` to dependency / peer docs (other FSDs, ADRs, runbooks).
- Path-style links (e.g. `[[<repo>/docs/foo]]`) for cross-project Obsidian-vault
  targets; bare names work within the repo. Omit if there are none yet.
```

---

## Chapter-internal structure

Each body chapter is **self-contained**: a reader finds the component's
requirements, interface, behavior, and failure modes in one place. Use the
sub-headings that apply; omit the rest. Keep depth at **four heading levels max**
(`####`) — Parts are unnumbered `#`, chapters are `##`, so a chapter has `###`
and `####` available.

**L2 — Application-logic chapter** (a feature / decision function):
- Purpose & scope
- Requirements (the FR/NFR this feature owns)
- Inputs & derivation (what it consumes from L1)
- Decision logic / algorithm / state machine
- Outputs & actions (what interfaces it drives)
- Failure modes & safe states
- Constants & tunables

**L1 — Interface chapter** (one external black-box peer):
- Purpose & peer (what it talks to)
- Requirements (the FR/NFR this interface owns)
- Protocol / wire format
- Message / data schema (fields, units, types, direction)
- Commands / opcodes (only if a custom protocol — omit otherwise)
- Handlers / flow
- Configuration
- Failure modes & recovery

**L0 — Foundation chapter** (shared infra we configure but don't own):
- Purpose & what we configure vs. what the library/service owns
- Requirements (usually NFR: availability, gating, ordering)
- Dependency & lifecycle (startup ordering, readiness gating)
- Failure / recovery (exercised **transitively** — no fast-tier tests of its own)

**Part D — Cross-cutting chapter**:
- Purpose
- Requirements
- Behavior spanning components (how the concern applies across the stack)

### Requirements live in their owning chapter

There is **no global Functional Requirements section**. Each requirement is stated
in the chapter of the component it constrains, with a **stable ID**:

- IDs are stable across evolve updates — never renumber unless explicitly asked.
- Group logically within the chapter; cross-reference other chapters' requirements
  by ID, never by restating them.

#### Two requirement conventions

Express requirements either way — pick one per project and use it consistently:

1. **FR/NFR items (default).** `FR-x.y` / `NFR-x.y [Must/Should/May]`, "shall"
   language, in the component chapter. Best for Small–Medium FSDs — human-readable
   and lightweight.
2. **Stable clause IDs + generated traceability (for large / high-assurance
   FSDs).** Every atomic, testable assertion gets a stable ID (e.g.
   `FSD-<section>-<slug>`) held in a registry; tests cite the ID, implementing code
   is tagged (`@fsd <id>`), and a tool generates the coverage matrix + gap report.
   Clauses carry status (pending / deprecated / testability) so deferred or
   non-mechanically-testable promises are tracked without inflating the gap count.
   Finer-grained than FR/NFR; proven on a 700+-clause production FSD.

Both satisfy the same contract: every requirement has a **stable ID**, lives in its
**component chapter**, is **referenced by ≥ 1 test**, and coverage is **generated**
(§x.2 Traceability) — never a hand-filled status table. The clause-ID system is the
heavier, more rigorous option; FR/NFR is the lightweight default. Do not mix the two
in one FSD.

---

## Traceability (generated, not hand-filled)

§18.2 must **point at generated artifacts**, mirroring §18.0 and
`references/test-architecture.md`:

- The FSD's job: every **Must**/**Should** FR & NFR is stated in its chapter with
  a stable ID, and the test specs reference those IDs. That is the linkage.
- The traceability tool crosses requirement→component→tier with test linkage to
  emit the **coverage matrix** (covered/total per component × tier) and a **gap
  report** (requirements with no test). Status is computed, never typed into the
  FSD.
- Do **not** hand-maintain a "Status: Covered / GAP" column in the FSD — it drifts
  from the code the moment a test changes. Reference the matrix path instead, e.g.:

  > Traceability is generated — see `tests/coverage-matrix.md` (component × tier)
  > and `tests/gaps.md` (uncovered requirements), produced by the traceability
  > tool from the requirement IDs in these chapters and the test specs.

- **Test specs mirror the chapters one-to-one** — one spec file per interface /
  feature / layer, sharing the chapter spine. Specs cite stable requirement/clause
  IDs, so reorganizing chapters never breaks linkage.

---

## Section Inclusion & Scaling

Not every Part or chapter applies to every project.

- **Always include:** §1 Overview; §2 Architecture **with 2.4 Component Layering +
  a layered diagram**; §3 Phases; §4 Risks; at least one body Part; **Part E** with
  §x.0 Test Architecture and the generated-traceability pointer.
- **Commands/Opcodes** sub-heading: only for embedded or custom protocols.
- **Cross-cutting chapters (Part D):** include those that apply (Security and Error
  Handling almost always; Build/Tooling, Identity, Config Catalog as relevant).
- **Omit empty chapters** rather than writing "N/A" — note the omission reason in a
  comment if it might confuse readers.

**One body Part per layer — scale the layer count to the system.** Parts A–C above
show the common three-layer case (L2 / L1 / L0), but the model is open-ended: a
system with more genuine layers gets **more body Parts, one per layer**, in
dependency order (application-most first → foundation last), still followed by the
cross-cutting Part and Part E. E.g. a system that splits application logic into
orchestration over domain logic, or inserts a shared-services layer, would carry
an extra Part for it. Add layers only where a real one-way dependency boundary
exists — see `references/test-architecture.md` ("Scale the layer count to the
system").

**Scale the Parts to complexity** (see `references/complexity-scaling.md`):

- **Low** (1–2 interfaces): the Part dividers add little — you may **drop the `#
  Part` headers** and list the few component chapters directly after the front
  matter, still in layer order (L2 → L1 → L0 → cross-cutting), then Part E.
- **Medium:** use the Part dividers; expect a handful of chapters per Part.
- **High:** full Parts scheme, every interface its own chapter, depth used to
  `####`.

Whatever the scale, keep **layer order** (application → interfaces → foundation →
cross-cutting → operations & verification) and **flat chapter numbering** across
the whole document.

---

## Migration from the flat layout

For older FSDs (and evolve-mode updates) written in the previous flat structure,
the correspondence is:

| Flat layout (old)                     | Parts scheme (new)                                             |
|---------------------------------------|----------------------------------------------------------------|
| §3 Implementation Phases              | §3 (unchanged, front matter)                                   |
| §5 Risks, Assumptions & Dependencies  | §4 Risks (front matter)                                        |
| §4 Functional Requirements (global)   | **dissolved** — each FR/NFR moves into its component's chapter |
| §6 Interface Specifications (global)  | **dissolved** — each interface becomes an L1 chapter (Part B)  |
| §6.4 Commands / Opcodes               | the relevant L1 interface chapter                             |
| §7 Operational Procedures             | §x Operational Procedures (Part E), now a reading path        |
| §8 Verification & Validation          | §x V&V (Part E); §8.0 → §x.0; §8.4 hand-filled table → pointer |
| §9 Troubleshooting / §10 Appendix     | Appendices (back matter)                                       |
| §11 Related                           | Related (back matter)                                         |

Reuse all existing FR/NFR/TC IDs verbatim during migration — only their location
and the surrounding grouping change, never the identifiers.
