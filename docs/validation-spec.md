# Validation Specification

## 1. Validation stages

A conforming implementation MUST validate each capability independently.

Derive MUST validate:

1. source JSON encoding and CrowdAnki structure;
2. source note field availability;
3. conversion completeness; and
4. the completed GCL.

Generate MUST validate:

1. GCL encoding and syntax;
2. linguistic interpretation and generated content;
3. field formatting and target concealment; and
4. the completed new CrowdAnki deck.

Update MUST validate:

1. the GCL and existing generated deck;
2. GCL-to-deck association;
3. entry classification and external drift;
4. added or regenerated content;
5. identity and preservation; and
6. the completed updated CrowdAnki deck.

Checks that can detect unsafe output MUST run before replacing a last known-good
deck.

## 2. GCL validation

For each file, validation MUST verify:

- valid UTF-8;
- a supported version header;
- unambiguous version 1 entry syntax;
- non-empty vocabulary after annotation removal;
- supported annotation order and multiplicity;
- full-width affix placeholders;
- absence of unsupported control characters; and
- any adopted duplicate, whitespace, and normalization policy.

## 3. Content validation

For each note, validation MUST verify:

- `Reading`, `Definition`, `Examples`, and `Vocabulary` are present and non-empty;
- the resolved reading agrees with a supplied authoritative reading;
- reading text contains only hiragana after HTML is removed;
- bold markup is balanced;
- kanji-corresponding reading portions are bold and original kana portions are
  not incorrectly bold;
- the definition is Japanese and addresses the intended sense;
- exactly three to five distinct examples are present;
- examples use the intended word or affix naturally;
- GCL annotations do not occur in any field; and
- no placeholder, generation instruction, mojibake, or uncertainty text remains.

Some linguistic checks require expert or model-assisted review and cannot be
reduced to character matching. Automated checks MUST NOT be presented as proof of
native-level naturalness.

## 4. Concealment validation

The rendered front MUST be inspected, not merely the raw template.

Validation MUST confirm that:

- the `Vocabulary` field is not referenced by the front template;
- no original target occurrence appears visibly in `Reading`, `Definition`, or
  `Examples`;
- inflected target occurrences are concealed;
- affix occurrences inside words are concealed;
- replacement forms are hiragana and bold; and
- HTML escaping cannot cause hidden markup or attributes to reveal the target.

Substring scanning MAY support this validation but MUST account for contextual
false positives and false negatives. It MUST NOT replace linguistic review where
the target’s inflected boundary is ambiguous.

## 5. Deck validation

The completed JSON MUST be parsed and checked for:

- top-level CrowdAnki deck type and required properties;
- a resolvable note model;
- the expected four field definitions in order;
- a valid question and answer template;
- four fields in every generated note;
- matching `note_model_uuid` values;
- unique valid note GUIDs;
- absence of the template test note;
- absence of unintended media references; and
- note counts reflecting removal of every note whose GCL entry was removed.

At least one representative card SHOULD be rendered or imported in a test
environment before a new template version is accepted.

## 6. Incremental validation

An incremental run MUST compare its proposed output with prior generated content.
It MUST verify that:

- unchanged entries retain the same GUID;
- unchanged entries retain identical four-field content;
- new entries do not collide with existing identities;
- explicitly regenerated entries are clearly reported; and
- changed entries are preserved unless explicitly selected for regeneration;
- notes corresponding to removed GCL entries are reported and absent from the
  proposed output;
- unmatchable entries stop publication; and
- external changes to managed fields or identities stop publication.

## 7. Scale and resilience validation

The test suite MUST include representative large files for Derive, Generate, and
Update. It MUST verify:

- complete note and entry counts;
- absence of quadratic matching behavior;
- progress reporting for long-running operations;
- correct failure on a configured resource limit;
- no partial artifact is published after cancellation, invalid content, resource
  exhaustion, or simulated write failure; and
- the previous generated deck remains recoverable after interrupted Update.

The quantitative definition of a representative large file remains open.

## 8. Severity and failure behavior

At minimum, reports MUST distinguish:

- **error**: output would be invalid, ambiguous, misleading, or violate
  preservation; and
- **warning**: output may be acceptable but merits editorial review.

Errors MUST prevent the affected card from being emitted as complete. Whether one
error prevents the entire deck from being written is an open question.

Each finding MUST include:

- a stable error code;
- severity;
- file and line or note identity;
- the relevant entry without corrupting its Unicode;
- a concise explanation; and
- a suggested corrective action when one is known.

## 9. Minimum acceptance scenarios

A release test suite MUST include:

- Derive from a valid source export without generating a deck;
- Generate from a manually authored valid GCL without a source export;
- replacement of an existing Generate output with a completely new generated
  deck;
- Update of an associated generated deck without repeating Derive;
- rejection of an unrelated or incompatible deck supplied to Update;
- a normal kanji-plus-okurigana word such as `遭う`;
- a supplied reading such as `一入[ひとしお]`;
- a na-adjective such as `静か(な)`;
- a prefix and a suffix;
- two entries sharing a written form but having different supplied readings;
- malformed brackets;
- ASCII `~` in place of `～`;
- ambiguous reading escalation;
- target concealment in an inflected example;
- preservation after inserting and reordering GCL entries; and
- preservation and reporting of a changed entry without an explicit regeneration
  request;
- regeneration of that entry when explicitly requested;
- reported removal of a note whose entry was removed from the GCL;
- detection of external edits to a managed generated-note field;
- interruption safety for each operation; and
- rejection of the template’s placeholder test note in production output.
