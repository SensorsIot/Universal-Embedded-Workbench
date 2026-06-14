# Evolve Mode -- Detailed Behavior

When operating in evolve mode, the skill must follow these rules:

If the existing FSD is still in the older flat layout, do **not** silently
restructure it as a side effect of an unrelated delta — propose the migration to
the Parts scheme separately (see the migration map in
`references/canonical-fsd-structure.md`). Within the Parts scheme:

## What to Preserve

- All Part dividers, chapter headings, and numbering for unaffected chapters.
- All existing requirement IDs (FR/NFR items or stable clauses) -- never renumber
  unless explicitly asked.
- All existing test case / clause IDs.
- Prose in unaffected chapters -- do not rephrase or "improve" text that is not
  part of the delta.

## What to Update

- The component chapter(s) directly affected by the delta.
- Cross-references if chapter numbers shift (e.g., a new chapter inserted).
- The Risks & Assumptions section if the delta introduces new risks or invalidates
  existing assumptions.
- Note: the traceability matrix is **generated**, not edited here — re-run the
  traceability tool after the delta lands (see below).

## What to Add

- New requirements (FR/NFR items or clauses, matching the FSD's convention) go in
  the chapter of the component they constrain, taking the next available ID there.
  Do **not** create a global requirements section.
- A new component becomes a **new chapter under the correct layer Part** (L2/L1/L0/
  cross-cutting), placed in layer order; renumber following chapters.
- New phases get inserted in logical order; subsequent phases are renumbered.
- New test cases get the next available ID **in the spec file that mirrors the
  affected chapter**; they reference the FR/NFR/clause IDs they validate.

## What to Remove

- Requirements or chapters the delta explicitly deprecates or removes.
- Assumptions that are now confirmed or contradicted by the delta.
- Coverage for removed requirements falls out of the regenerated matrix — mark the
  clause/requirement deprecated (preserve the ID) rather than deleting silently, so
  historical results stay readable.

## Conflict Resolution

If the delta contradicts existing FSD content:
1. Flag the contradiction to the user via **AskUserQuestion**.
2. Do not silently overwrite -- get explicit confirmation.
3. Once resolved, update all affected chapters consistently, then regenerate the
   traceability matrix.
