# Validation Specification

## 1. Validation stages

A conforming implementation MUST validate each capability independently.

Derive MUST validate:

1. source JSON encoding and CrowdAnki structure;
2. source note field availability;
3. conversion completeness; and
4. the completed GCL.

Generate MUST validate:

1. GCL preflight deduplication;
2. GCL encoding and syntax after cleanup;
3. linguistic interpretation and generated content;
4. field formatting and target concealment; and
5. the completed new CrowdAnki deck package.

Update MUST validate:

1. GCL preflight deduplication;
2. the cleaned GCL and existing generated deck;
3. GCL-to-deck association;
4. entry classification and external drift;
5. added or regenerated content;
6. identity and preservation; and
7. the completed updated CrowdAnki deck package.

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
- canonical ASCII `(な)` markers rather than full-width parentheses;
- bracket-form readings rather than whitespace-separated inline readings;
- absence of unsupported control characters; and
- absence of exact duplicate annotated-entry lines; and
- any adopted whitespace and normalization policy.

When validating an operation that adds requested entries to an existing GCL,
validation MUST confirm that the new entries follow the previously final entry and
that existing entries were not reordered.

## 3. Content validation

For each note, validation MUST verify:

- `Reading`, `Definition`, `Examples`, and `Vocabulary` are present and non-empty;
- the resolved reading agrees with a supplied authoritative reading;
- every automatically included alternate reading supports three to five natural,
  non-contrived contemporary examples;
- no automatically included reading is merely archaic, obsolete, markedly
  uncommon, or limited to unrelated compounds;
- reading text contains only hiragana after HTML is removed;
- bold markup is balanced;
- kanji-corresponding reading portions are bold and original kana portions are
  not incorrectly bold;
- the definition is Japanese and addresses the intended sense;
- exactly three to five distinct examples are present;
- examples use the intended word or affix naturally;
- examples for nouns demonstrate commonly productive `Nの…` and `Nする`
  constructions where applicable, without inventing an unsupported construction;
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

- a containing directory whose name equals the JSON filename without `.json`;
- a package name correctly derived from the GCL filename;
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
- an already generated entry is represented by exactly one note after Update;
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
- generation of
  `n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json` from
  `gcl/n1_vocabulary_generation_control_file.txt`;
- rejection of a generated JSON file whose containing directory has a different
  name;
- replacement of an existing Generate output with a completely new generated
  deck;
- Update of an associated generated deck without repeating Derive;
- expansion of a 10-note deck to the first 100 GCL entries by preserving the
  original 10 identities and adding exactly 90 notes;
- a repeated Update request that adds no duplicate notes;
- deduplication that retains the first exact GCL entry, removes all later exact
  occurrences, and preserves remaining order;
- Generate and Update preflight deduplication that retains separately annotated
  readings such as `縁[ふち]` and `縁[えん]`;
- distinct notes and GUIDs for one written expression with two authoritative
  readings;
- a `全` clarification response that annotates the existing entry with the first
  offered reading and appends all remaining readings to the end of the GCL;
- a multiline clarification response whose lines map to prompts in order,
  including multiple `全` responses and rejection of a mismatched line count;
- automatic expansion into all common contemporary readings while excluding an
  uncommon variant that would require contrived examples;
- rejection of an unrelated or incompatible deck supplied to Update;
- a normal kanji-plus-okurigana word such as `遭う`;
- a supplied reading such as `一入[ひとしお]`;
- a na-adjective such as `静か(な)`;
- a noun that commonly precedes `の`, a suru-noun, and a noun that naturally
  demonstrates both constructions;
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
