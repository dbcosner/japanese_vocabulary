# Validation Specification

## 1. Import validation

Import MUST validate:

- the APKG ZIP structure and collection database;
- note-model field mappings;
- source note iteration and field extraction;
- canonicalization of imported GCL entries;
- exclusion of any result that is not a complete term plus hiragana reading;
- exact duplicate handling;
- complete decisions-file note overrides; and
- separate atomic publication of the proposed GCL and review JSON.

Every successfully inspected note that cannot be reduced deterministically to a
complete term and reading, and is not handled by an explicit override, MUST
appear in the review report. Routine removal of non-term metadata, clear
splitting, and duplicate reporting do not constitute review findings. Fatal
archive, database, model, or required-field errors stop Import instead.

## 2. GCL validation

A complete GCL used by Populate or Generate MUST have:

- UTF-8 encoding;
- at least one entry after blank and `#` lines are ignored;
- one complete hiragana `[reading]` per entry;
- canonical ASCII U+007E `~` placeholders;
- no legacy `(な)` or `（な）` markers;
- no unsupported parentheses, brackets, control characters, or exact duplicates;
  and
- no text outside the implemented annotated-entry grammar.

The current parser does not enforce the version header or reject arbitrary
comment lines. Project-authored files nevertheless use the exact
`# GCL Version: 1` header.

Syntax cleanup MUST preserve source order.

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
- a template containing exactly one nonempty note model and at least one card
  template;
- derivable stable deck and model identifiers;
- one valid cached card per GCL entry; and
- an `.apkg` output extension.

Regression tests open generated collection databases and confirm:

- note count equals GCL entry count;
- card count equals expected template output;
- the GUID set equals deterministic GCL identities;
- repeated generation retains stable identifiers.

## 5. Required regression coverage

Tests MUST cover:

- legacy and modern APKG collection formats;
- import review and decisions files;
- tilde normalization and legacy na-adjective-marker removal;
- exact duplicate removal;
- missing and multiple readings;
- reading-resolution expansion and post-resolution deduplication;
- cache reuse after insertion or reordering;
- APKG generation with stable IDs;
- target concealment and HTML validation;
- retry preparation and merge behavior;
- cost-confirmation guards.
