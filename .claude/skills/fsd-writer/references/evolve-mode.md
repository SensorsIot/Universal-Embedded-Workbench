# Evolve Mode -- Detailed Behavior

When operating in evolve mode, the skill must follow these rules:

## What to Preserve

- All section headings and numbering for unaffected sections.
- All existing FR/NFR IDs -- never renumber unless explicitly asked.
- All existing test case IDs.
- Prose in unaffected sections -- do not rephrase or "improve" text that is not
  part of the delta.

## What to Update

- Sections directly affected by the delta description.
- The traceability matrix (always -- to reflect any FR/test changes).
- Cross-references if section numbers shift (e.g., new phase inserted).
- The Risks & Assumptions section if the delta introduces new risks or invalidates
  existing assumptions.

## What to Add

- New FRs/NFRs get the next available ID in their group.
- New phases get inserted in logical order; subsequent phases are renumbered.
- New test cases get the next available TC-x.y ID.
- New traceability rows are appended to the matrix.

## What to Remove

- Requirements or sections the delta explicitly deprecates or removes.
- Assumptions that are now confirmed or contradicted by the delta.
- Traceability rows for removed requirements (mark as "Removed" rather than
  deleting, to maintain audit trail).

## Conflict Resolution

If the delta contradicts existing FSD content:
1. Flag the contradiction to the user via **AskUserQuestion**.
2. Do not silently overwrite -- get explicit confirmation.
3. Once resolved, update all affected sections consistently.
