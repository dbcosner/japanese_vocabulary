# Open Questions and Decision Log

This file records behavior that has not yet been authorized. Implementations MUST
surface these cases rather than silently commit the project to a difficult-to-reverse
choice.

When a question is decided, record the decision, date, rationale, and affected
specifications, then update those specifications.

## Q1. Comments and blank lines

**Question:** May blank lines and comments appear after the GCL header?

**Current evidence:** The existing file has a version comment and one blank line
before its entries.

**Decision needed:** Define comment syntax, whether inline comments exist, and
whether blank lines are ignored.

## Q2. Whitespace and Unicode normalization

**Question:** Should leading/trailing whitespace be rejected or trimmed, and
should text be normalized to NFC?

**Risk:** Silent normalization can merge intentionally distinct source forms or
make diffs surprising.

## Q3. ASCII and full-width affix markers

**Question:** Should ASCII `~` be accepted and canonicalized to `～`, or rejected?

**Current evidence:** The GCL contains both forms, including `~箇月` and `~ヶ月`,
while the project instructions define `～`.

## Q4. Duplicate entries

**Question:** What constitutes a duplicate, and should exact duplicates fail,
warn, or intentionally produce multiple cards?

Distinct supplied readings for the same written form MUST remain distinguishable.

## Q5. Stable entry and note identity

**Question:** What stable key links a GCL entry to a generated note?

The decision must cover:

- identical vocabulary with distinct readings;
- metadata changes;
- entry reordering;
- CrowdAnki GUID generation; and
- migration if the identity scheme changes.

## Q6. Generation-state storage

**Question:** Is preservation state derived from the last generated deck, stored
in a separate manifest, or represented in GCL metadata?

The state must be reviewable, recoverable, and safe to update atomically.

## Q7. Explicit regeneration

**Question:** How does an editor request regeneration of one entry, a selection,
or a whole deck?

The mechanism should make destructive rewrites deliberate and visible in the run
report.

## Q8. Changed and removed entries

**Question:** What happens when an entry’s annotations change or an entry is
removed from the GCL?

**Status:** Resolved by D01 and D02.

## Q9. Ambiguity and error scope

**Question:** Does one unresolved entry stop the whole run, or may other entries
be generated while no final deck is emitted?

The original instruction says to stop processing and request clarification; the
desired scope of “stop” needs definition.

## Q10. Example field serialization

**Question:** How are examples separated inside `Examples`?

Candidates include `<div>` elements, paragraphs, or `<br>` separators. The choice
must support reliable counting and clean Anki rendering.

## Q11. CrowdAnki UUID policy

**Question:** Which template UUIDs are preserved, regenerated per deck, or shared?

The decision must cover deck, deck configuration, note model, and template UUIDs,
as well as note GUIDs.

## Q12. Ordering

**Question:** Must generated note order match the GCL, and should initial GCL order
match the source deck?

Reordering alone must not regenerate content.

## Q13. Output and backup policy

**Question:** What paths and naming rules apply to generated decks, reports,
manifests, temporary files, and backups?

## Q14. Source deck versus deck template selection

**Question:** How are the original import deck and output template selected for
each of the three intended decks?

The source-deck two-field import contract differs from the current four-field
output template and must be explicit in configuration.

## Q15. Supporting information from `fields[1]`

**Question:** What forms of supporting information are recognized, and how may
they influence GCL annotations?

It must not override an explicit editor decision or leak directly into generated
content without validation.

## Q16. Linguistic review mechanism

**Question:** Which dictionaries, language models, human review steps, and
provenance records are required or permitted?

The mechanism must honor supplied readings, provide natural Japanese, and avoid
guessing under ambiguity.

## Q17. GCL-to-generated-deck association

**Question:** How does Update prove that a GCL and an existing generated JSON file
belong together?

Candidates include a sidecar manifest, embedded metadata, a configuration record,
or a stable deck identifier combined with an entry-state index. The association
must survive file renaming and movement when practical and must reject an
unrelated deck.

## Q18. External edits to generated JSON

**Question:** If managed note fields or identities were edited outside the
generator, should Update fail, preserve those edits, or offer explicit
reconciliation?

**Status:** Resolved by D03.

## Q19. Generate output collision

**Question:** If Generate targets a path that already exists, must it fail, create
a versioned filename, or allow an explicit overwrite option?

**Status:** Resolved by D04.

## Q20. Quantitative scale requirements

**Question:** What source size, GCL entry count, generated-deck size, memory
ceiling, and acceptable runtime define required large-file support?

Until measured targets are chosen, implementations must avoid quadratic matching,
document observed limits, report progress, and preserve outputs on failure.

## Q21. Operation interface and composition

**Question:** How are Derive, Generate, and Update invoked, and may one command
explicitly compose Derive followed by Generate?

The interface must keep inputs, outputs, reports, and failures separable by
operation.

## Decision record template

```text
### Decision DNN: Short title

- Date:
- Status: accepted | superseded
- Decision:
- Rationale:
- Affected specifications:
- Supersedes:
```

### Decision D01: Removed GCL entries remove generated notes

- Date: 2026-07-24
- Status: accepted
- Decision: Update reports and removes a generated note when its associated entry
  has been removed from the authoritative GCL.
- Rationale: The GCL is the source of truth for generated deck membership.
- Affected specifications: `product-spec.md`, `deck-generation-spec.md`,
  `validation-spec.md`
- Supersedes: unresolved removal portion of Q8

### Decision D02: Changed entries require explicit regeneration

- Date: 2026-07-24
- Status: accepted
- Decision: A reading, annotation, or other editorial change to a previously
  generated entry does not regenerate its content unless regeneration is
  explicitly requested.
- Rationale: Previously generated cards remain stable unless the editor deliberately
  requests regeneration.
- Affected specifications: `product-spec.md`, `deck-generation-spec.md`,
  `validation-spec.md`
- Supersedes: Q7 and the changed-entry portion of Q8, except that the interface for
  requesting regeneration remains open

### Decision D03: External drift causes Update to fail

- Date: 2026-07-24
- Status: accepted
- Decision: If managed fields or note identities in the associated generated JSON
  were edited outside the system, Update fails with a drift report and does not
  publish output.
- Rationale: The generator must not silently overwrite external changes or support
  a reconciliation subsystem in the initial project.
- Affected specifications: `product-spec.md`, `deck-generation-spec.md`,
  `validation-spec.md`
- Supersedes: Q18

### Decision D04: Generate overwrites its output path

- Date: 2026-07-24
- Status: accepted
- Decision: Generate replaces an existing file at its requested output path with
  a complete newly generated deck.
- Rationale: A simple overwrite contract keeps Generate small and avoids defensive
  output management. Generate remains distinct from Update and does not preserve
  content from the replaced file.
- Affected specifications: `product-spec.md`, `deck-generation-spec.md`,
  `validation-spec.md`
- Supersedes: Q19
