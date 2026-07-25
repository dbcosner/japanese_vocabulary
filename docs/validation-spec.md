# Validation Specification

## 1. Validation stages

A conforming implementation MUST validate each capability independently.

Import MUST validate:

1. source JSON encoding and CrowdAnki structure;
2. source note field availability;
3. conversion completeness;
4. deduplication of proposed entries;
5. reading and interpretation resolution, including clarification outcomes; and
6. the completed GCL.

Generate MUST validate:

1. GCL preflight deduplication;
2. GCL encoding and syntax after cleanup;
3. linguistic interpretation and generated content;
4. field formatting and target concealment; and
5. the completed new CrowdAnki deck package.

Update MUST validate:

1. pre-classification reading resolution for every unannotated manual addition;
2. GCL preflight and post-resolution deduplication;
3. the fully annotated cleaned GCL and existing generated deck;
4. GCL-to-deck association;
5. entry classification and external drift;
6. added or regenerated content;
7. identity and preservation; and
8. the completed updated CrowdAnki deck package.

Checks that can detect unsafe output MUST run before replacing a last known-good
deck.

## 2. GCL validation

For each file, validation MUST verify:

- valid UTF-8;
- a supported version header;
- unambiguous version 1 entry syntax;
- non-empty vocabulary after annotation removal;
- supported annotation order and multiplicity;
- exactly one complete hiragana `[reading]` on every entry;
- ASCII U+007E affix placeholders;
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
- the response's request-entry and resolved-entry values each equal the complete
  canonical GCL entry exactly, including `[reading]`, `~`, and `(な)`;
- the displayed reading, after HTML removal, equals the authoritative reading
  and does not omit or add okurigana or a na-adjective reading suffix;
- the definition and every example use the sense belonging to the authoritative
  reading rather than a homographic sense belonging to another reading;
- every Import-resolved alternate reading supports at least one natural,
  non-contrived contemporary example and normally supports three;
- no automatically included reading is merely archaic, obsolete, markedly
  uncommon, or limited to unrelated compounds;
- reading text contains only hiragana after HTML is removed;
- bold markup is balanced;
- kanji-corresponding reading portions are bold and original kana portions are
  not incorrectly bold;
- the definition is Japanese and addresses the intended sense;
- one to five distinct examples are present;
- exactly three examples are used by default;
- a one- or two-example set is accompanied by generation metadata explaining why
  further examples would be contrived or essentially duplicative;
- a four- or five-example set is accompanied by generation metadata identifying
  the additional common use patterns being demonstrated;
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
- no original target occurrence appears as a substring of a larger word or
  compound in those fields;
- inflected target occurrences are concealed;
- affix occurrences inside words are concealed;
- replacement forms are hiragana and bold; and
- HTML escaping cannot cause hidden markup or attributes to reveal the target.

Substring scanning MAY support this validation but MUST account for contextual
false positives and false negatives. It MUST NOT replace linguistic review where
the target’s inflected boundary is ambiguous.

The exact annotation-free target scan is mandatory even for a one-character
target. A match inside a compound is an error, not a contextual false positive,
because it still exposes the answer. Error reports SHOULD name the field and
matching containing text so a retry can rephrase it directly.

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
- note counts reflecting removal of notes absent from the GCL plus newly added or
  explicitly regenerated notes.

At least one representative card SHOULD be rendered or imported in a test
environment before a new template version is accepted.

## 6. Incremental validation

An incremental run MUST compare its proposed output with prior generated content.
It MUST verify that:

- stable generated-note identity is used before learner-facing field matching;
- unchanged entries retain the same GUID;
- unchanged entries retain identical four-field content;
- an already generated entry is represented by exactly one note after Update;
- new entries do not collide with existing identities;
- explicitly regenerated entries are clearly reported; and
- changed entries are preserved unless explicitly selected for regeneration;
- notes absent from the GCL are reported and omitted from the proposed output;
- unmatchable entries stop publication; and
- external changes to managed fields or identities stop publication.

## 7. Scale and resilience validation

The test suite MUST include representative large files for Import, Generate, and
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

- Import from a valid source export without generating a deck;
- Import-time deduplication that retains the first exact proposed entry and
  reports later source-note duplicates;
- Import-time disambiguation that annotates the first qualifying reading, appends
  other qualifying readings, and pauses for unresolved interpretations;
- Generate from a manually authored valid GCL without a source export;
- generation of
  `n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json` from
  `gcl/n1_vocabulary_generation_control_file.txt`;
- rejection of a generated JSON file whose containing directory has a different
  name;
- replacement of an existing Generate output with a completely new generated
  deck;
- Update of an associated generated deck without repeating Import;
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
- a noncanonical tilde variant in place of ASCII U+007E `~`;
- ambiguous reading escalation;
- target concealment in an inflected example;
- target concealment inside compounds, including `器` in `容器`, `志` in `意志`,
  and `影` in `影響`;
- exact resolved-entry preservation for na-adjectives, including the terminal
  `(な)` marker;
- rejection of a card whose definition uses a homographic sense from a different
  reading, such as treating `柄[え]` as the pattern sense `がら`;
- rejection of a displayed reading that does not equal the authoritative reading
  after HTML removal;
- correction of an entry that becomes an exact duplicate of an earlier entry,
  with one retained GCL entry and no duplicate generated note;
- repeated Update matching by stable GUID when two entries have the same
  annotation-free vocabulary and displayed reading;
- preservation after inserting and reordering GCL entries; and
- preservation and reporting of a changed entry without an explicit regeneration
  request;
- regeneration of that entry when explicitly requested;
- reported removal of an existing note whose entry is absent from the GCL;
- detection of external edits to a managed generated-note field;
- interruption safety for each operation; and
- rejection of the template’s placeholder test note in production output.
