# Validation Specification

## 1. Import validation

Import MUST validate:

- the APKG ZIP structure and collection database;
- note-model field mappings;
- source note reconciliation;
- canonical GCL syntax;
- exact duplicate handling;
- explicit decisions-file structure; and
- atomic publication of the proposed GCL and review JSON.

Every skipped or unsafe source note MUST appear in the review report with source
identity, original material, and a reason.

## 2. GCL validation

A complete GCL MUST have:

- the exact version header;
- UTF-8 encoding;
- one entry per nonempty content line;
- one complete hiragana `[reading]` per entry;
- canonical ASCII U+007E `~` placeholders;
- canonical `(な)` markers;
- no unsupported parentheses, brackets, control characters, or exact duplicates;
  and
- no learner-facing or editorial prose.

Syntax cleanup MUST preserve source order and stable entry identity where an
approved compatibility migration applies.

## 3. Population validation

Populate MUST verify:

- the workspace belongs to the requested GCL and logical APKG;
- the GCL hash and entry count;
- cached record identity and exact `gcl_entry`;
- all card fields through `validate_card`;
- pending job manifests and collected output integrity; and
- that only missing or invalid cards are prepared.

A workspace is complete only when every current GCL entry has exactly one valid
accepted card and no findings.

## 4. APKG generation validation

Generate MUST verify before publication:

- a complete and current population workspace;
- a valid APKG-neutral template;
- stable deck and model identifiers;
- one valid cached card per GCL entry; and
- an `.apkg` output extension.

Regression tests SHOULD open the generated collection database and confirm:

- note count equals GCL entry count;
- card count equals expected template output;
- the GUID set equals deterministic GCL identities;
- field ordering and card templates are correct; and
- repeated generation retains stable identifiers.

## 5. Required regression coverage

Tests MUST cover:

- legacy and modern APKG collection formats;
- import review and decisions files;
- tilde and na-adjective normalization;
- exact duplicate removal;
- missing and multiple readings;
- reading-resolution expansion and post-resolution deduplication;
- cache reuse after insertion or reordering;
- incomplete workspace rejection;
- APKG generation with stable IDs;
- target concealment and HTML validation;
- retry preparation and merge behavior;
- cost-confirmation guards; and
- syntax migration with cache/GUID preservation.
