# Roadmap

This roadmap is informative, not normative. A roadmap item becomes required only
after it is specified in the normative documents.

## Phase 1: Specification decisions

- Resolve the remaining GCL syntax questions, especially comments, normalization,
  and ASCII `~`.
- Select a stable entry identity and CrowdAnki GUID strategy.
- Define state storage, explicit-regeneration controls, and atomic output.
- Define example-field HTML and error scope.

## Phase 2: Core generation

- Implement Import for large source CrowdAnki exports, including deduplication
  and disambiguation.
- Parse and validate GCL version 1.
- Implement Generate independently of Import.
- Resolve readings and generate advanced Japanese content.
- Build notes from the current four-field template.
- Validate target concealment and CrowdAnki structure.

## Phase 3: Safe maintenance

- Implement Update independently of Import.
- Verify GCL-to-generated-deck association.
- Detect new, unchanged, changed, and absent-from-GCL entries.
- Detect external drift in managed generated content.
- Preserve unchanged fields and identities.
- Support deliberate per-entry and full regeneration.
- Produce reviewable generation reports and state updates.
- Add regression tests for all minimum acceptance scenarios.

## Phase 4: Pronunciation enhancements

Potential additions:

- pitch-accent notation;
- native-speaker or synthesized audio; and
- pronunciation notes.

Any supplied `[reading]` MUST remain authoritative for pronunciation-related
features.

## Phase 5: Lexical enrichment

Potential additions:

- frequency information;
- register notes;
- collocations;
- usage notes; and
- source or editorial provenance.

These features should use new fields or structured metadata rather than changing
the meaning of the four current fields.

## Phase 6: Editorial tooling

Potential additions:

- a GCL linter and formatter;
- a clarification review queue;
- side-by-side card previews;
- controlled regeneration diffs; and
- import/export verification against a test Anki profile.
