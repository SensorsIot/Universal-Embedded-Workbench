---
name: test-designer
description: Design FSD-driven functional test cases with bidirectional traceability — every spec clause maps to ≥1 test, every test claims the source lines it exercises (via `@fsd` tags in the code), and an optional coverage check verifies those lines actually ran. Produces test spec documents, a machine-readable traceability matrix, and a gap report (orphaned clauses / orphaned tests / orphaned code). Use when the user wants to build a test suite from an existing FSD, audit whether existing tests cover an FSD, generate a traceability matrix linking spec ↔ test ↔ code, or close gaps between documented behavior and tested behavior. Triggers on "design test cases from FSD", "trace tests to code", "build traceability matrix", "FSD coverage tests", "test coverage of spec", "functional coverage audit", "trace FSD".
---

# test-designer

Design functional test cases for a project that has an FSD, with bidirectional traceability:

- **Forward** — every FSD clause → ≥1 test → claimed source lines (via `@fsd` tags).
- **Backward** — every production-code branch → ≥1 FSD clause (or it surfaces as a gap).
- **Verifiable** — an optional coverage check (gcov/lcov, coverage.py, c8) confirms each test's claimed lines actually executed.

This skill **designs and documents** tests. It does not implement, run, or instrument them. That separation keeps the skill framework-agnostic.

## When to use

- Building a test suite from an FSD that has none.
- Auditing an existing test suite for coverage gaps against an FSD.
- Producing a traceability matrix for compliance, certification, or review.
- Finding production code with no documented justification (the backward arrow).

## When NOT to use

- The project has no FSD. Use `fsd-writer` first.
- The user wants to run tests or write test code. This skill stops at the spec/matrix.
- The user wants pure code branch coverage with no FSD link. Point them at gcov directly.

## Inputs

Ask the user (via AskUserQuestion if not supplied):

1. **FSD path(s)** — one or more Markdown files.
2. **Source tree path(s)** — root(s) of the implementation (e.g. `smartmeterReader/src/`).
3. **Existing matrix?** — path to a prior `traceability.yaml` for incremental updates, or empty for a fresh build.
4. **Output root** — defaults to `tests/` under the project root.

## Pipeline

Five phases, in order. Each writes its outputs to disk so the run is resumable. Use TaskCreate to track them when the FSD is large.

### Phase 1 — Enumerate the FSD

Walk every chapter. Extract atomic clauses — one per decision point or promise. Skip narrative prose. Assign stable IDs of the form `FSD-<section>-<short-slug>`.

A clause that promises multiple things ("403 → red+green LED → retry 60s") is split into sub-clauses with suffixed IDs:

```
FSD-5.2-403-status     "Provisioning returns HTTP 403"
FSD-5.2-403-led        "LED set to red+green alternating on 403"
FSD-5.2-403-retry      "Retry every 60s after 403"
```

For each clause record:

```yaml
- id: FSD-5.2-403-led
  text: "LED set to red+green alternating on 403"
  source_section: "§5.2"
  testability: host | target | bench-only | philosophical
  kind: positive | negative | boundary | state-transition | error
  pending: false   # true when the clause itself is TBD in the FSD
```

`testability`:
- **host** — pure logic, testable in a host build (parsers, JSON, control math).
- **target** — needs the chip or a faithful simulator (NVS, WiFi reconnect, Modbus client).
- **bench-only** — requires real external hardware (real meter, real inverter).
- **philosophical** — a promise that cannot be tested mechanically ("secure by design"). No test will be written; flagged in the gap report.

#### Controllability — why a clause lands at a tier, and how to move it

The tier follows from whether we can **create the condition** and **observe the
result** for the external device the clause's interface talks to. Resolve it per
device:

- **Drive** — we command the device through the real channel (publish / request /
  write) → the clause can sit at the tier where that channel runs.
- **Feed** — the device can't be commanded, so we supply its *inbound* data through
  a built-in test hook (a **seam**: synthesized input on host, a fake-data build
  flag on target). Most "we reject / handle a bad X" failure modes are Feed.
- **Emulate** — substitute a fake device *outside* the SUT (bench).
- **Observe** — real device, uncommandable: watch-only validation, not provocation.
- **Rig** — driven by the test infrastructure (link drop, reboot, power-cycle).
- Application-logic clauses own no device; they **inherit** the controllability of
  the interfaces they orchestrate.

**Difficulty changes *where* a clause is tested, not *whether*.** If a clause's
natural tier is uncontrollable (can't drive or observe the real device), do **not**
mark it `bench-only` and drop the failure mode — add a seam to *Feed* synthesized
inputs and relocate it to `host`/`target`. `bench-only` is a last resort for clauses
that genuinely need real hardware to manifest, never an excuse to skip a failure
mode. **Coverage shows a line ran, not that it's right** — every test's *Pass*
criterion must assert the correct result, not merely that the branch executed.

Save to `<output_root>/clauses.yaml`.

### Phase 2 — Design tests

For each clause with `testability ≠ philosophical` and `pending = false`, propose ≥1 test. Invoke the `create-test-spec` skill per clause cluster (typically one cluster per FSD chapter) so the per-test format stays consistent with the rest of the codebase.

Enforce:

- **One positive test minimum** per clause.
- **A negative test** for every clause containing reject/deny/forbid semantics (e.g. §18.3 OTA-from-non-VPN, §21.6 unknown driver id).
- **Boundary tests** at each numeric edge the spec implies (`= 0`, `= max`, `> max`, `< min`).
- **A state-transition test** for each row of every state/failure-mode table (e.g. §19.9, §20.7, Appendix D).

Test IDs follow `TC-<area>-<nn>[-<qualifier>]`:

```
TC-PROV-04           positive
TC-PROV-04-neg       negative variant
TC-NULL-07-zero      boundary at max_export_w = 0
TC-NULL-07-rated     boundary at max_export_w = RATED_W
TC-NULL-07-over      boundary at max_export_w > RATED_W
```

Write specs under `<output_root>/specs/<chapter-slug>.md`.

### Phase 3 — Tag-driven mapping

For each test, identify the file:line range(s) it claims to exercise by grepping the source tree for `@fsd <FSD-id>` markers.

**Tag format** — language-appropriate block or line comment placed at or immediately above the implementing branch:

```c
/* @fsd FSD-5.2-403-led */
if (status == 403) {
    led_set(LED_RED_GREEN_ALT);
}
```

```python
# @fsd FSD-21.6.1-bad-driver
if driver_id not in INVERTER_DRIVERS:
    return jsonify(error="unknown driver"), 400
```

Rules:

1. Grep every source root for `@fsd FSD-` markers. Parse the ID, file path, and line number. A tag covers its block up to the next closing brace / dedent / blank line — record the start and end lines.
2. For each clause, list every source range tagged with its ID. Multiple tags per clause are allowed (clause covers multiple branches).
3. For clauses with no tag, emit a "tag missing" item in the gap report. **Never invent a mapping.** The skill may propose where a tag belongs, but never inserts one — placement is a human decision.
4. For source files in the configured roots containing zero `@fsd` tags, list them in the gap report's backward-arrow section.

Record each test as:

```yaml
- id: TC-PROV-04
  fsd: [FSD-5.2-403-led, FSD-5.2-403-retry]
  source:
    - { path: smartmeterReader/src/provision_client.c, start: 142, end: 168 }
  tier: host
  kind: negative
  spec_path: tests/specs/provisioning.md#tc-prov-04
```

Save to `<output_root>/traceability.yaml`.

### Phase 4 — Gap report

Write `<output_root>/gaps.md` with four sections:

1. **Clauses without tests** — every `FSD-*` ID that no `TC-*` cites. Link to the FSD section anchor.
2. **Tests without source** — every `TC-*` whose `source` is empty (the clause has no `@fsd` tag in the code yet). For each, propose a likely insertion point based on the FSD's Implementation Layout section (e.g. §19.10 lists `nulleinspeisung.c` for §19 work).
3. **Source without clause (backward arrow)** — production files in the configured roots with no `@fsd` tag anywhere. Two verdicts the developer must pick per file:
   - "Add a clause to the FSD" — behavior exists but is undocumented.
   - "Delete the code" — orphaned implementation.
   
   The skill surfaces the choice; the developer makes it.
4. **Pending and philosophical** — clauses marked `pending: true` (FSD-side TBDs like §19.12, §20.10) or `testability: philosophical`. Listed so they aren't mistaken for gaps.

### Phase 5 (optional) — Coverage check

If the user has a coverage report (gcov `.info`, lcov, coverage.py JSON), emit `<output_root>/coverage-check.py`:

- For each `TC-*` in `traceability.yaml`, read its claimed source ranges.
- Parse the coverage data.
- Fail (exit 1) if any claimed line is uncovered after the test run.

The script is generated once; the user wires it into CI. If the user has no coverage tooling yet, skip this phase and note it in the run summary.

## Outputs

| Artifact | Path | Purpose |
|---|---|---|
| Clause inventory | `<output_root>/clauses.yaml` | Phase 1 enumeration |
| Test specs | `<output_root>/specs/*.md` | Human-readable test design |
| Traceability matrix | `<output_root>/traceability.yaml` | Machine-readable trace |
| Gap report | `<output_root>/gaps.md` | Four orphan lists |
| Coverage check | `<output_root>/coverage-check.py` | Optional CI gate |

## Interaction with other skills/agents

- **`fsd-writer`** — produces or updates the FSD this skill consumes. No coordination required; the FSD format is the shared contract.
- **`create-test-spec`** — invoked by Phase 2 once per clause cluster. Do not duplicate its logic.
- **`fsd-compliance-checker`** (agent) — runs *after* the matrix exists; verifies code at each claimed `source` range actually implements the cited clause. This skill produces the input that agent consumes.
- **`code-reviewer`** / **`code-review`** — can be configured to flag PRs that add code under a tracked path without a corresponding `@fsd` tag.

## Conventions

- **Stable IDs.** Never renumber. New clauses get the next free `FSD-<section>-<slug>` slot. Obsolete clauses are marked `deprecated: true` in `clauses.yaml`, never deleted, so historical test results stay readable.
- **Atomic clauses.** Multi-part promises are split, as in the §5.2 example above.
- **Tag-driven only.** No LLM-inferred mappings. The contract is: a clause is covered iff a `@fsd` tag exists in production code. The CI gate is deterministic and reviewable.
- **Source roots are explicit.** Only paths the user listed as source roots participate in the backward-arrow analysis. Generated code, vendored libraries, and test code itself are out of scope.

## Failure modes to anticipate

- **Untestable promises** — flag as `philosophical`; do not pretend.
- **Branches needing fault injection** — OOM, watchdog reset, brownout. Tier them as `target` with a `requires: [fault-injection]` field; do not claim host-testability.
- **TBD / open items in the FSD** — sections like "Status: TBD" or "Open Design Questions" are not implementable yet. Record as `pending: true` with no tests; revisit when the FSD resolves them.
- **Utility functions matching many clauses** — a CRC helper or JSON formatter may carry multiple `@fsd` tags or none, depending on whether its caller is the right place to tag. The matrix is many-to-many; this is fine.
- **Tags on the wrong branch** — a `@fsd FSD-5.2-403-led` tag above the 200-OK path is a real bug. The `fsd-compliance-checker` agent catches these; this skill does not.

## Example session shape

```
User:  design tests from smartmeterReader/Documentation/smart-meter-decoder-fsd.md
Skill: → asks: source roots? existing matrix? output root?
User:  smartmeterReader/src/, no existing matrix, tests/
Skill: → Phase 1: extracted 187 clauses across §1–§21 + Appendix D
                  (12 philosophical, 23 pending — see gaps.md §4)
       → Phase 2: designed 243 tests (167 positive, 41 negative, 35 boundary)
                  written to tests/specs/{decoder,provisioning,ota,
                  wireguard,nulleinspeisung,divert,status-portal,appendix-d}.md
       → Phase 3: grepped 47 source files for @fsd tags
                  124 clauses tagged, 28 untagged
                  9 files have zero @fsd tags
       → Phase 4: gaps.md written
                  • 28 clauses without tests (tags missing in code)
                  • 0 tests without source mapping
                  • 9 backward-arrow source files for review
                  • 35 pending/philosophical entries
       → Phase 5: skipped (no coverage report supplied)
```

The 28 untagged clauses become the developer's next pass: insert `@fsd` tags at the matching code sites, re-run the skill, watch the gap shrink. The 9 backward-arrow files become a review item: document or delete.
