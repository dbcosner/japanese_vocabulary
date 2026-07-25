# CrowdAnki Operations Specification

## 1. Scope

The public workflow defines three phases:

- **Import**: source CrowdAnki JSON to a deduplicated, disambiguated GCL;
- **Populate**: GCL entries to validated, reusable card information; and
- **Generate**: the current GCL plus populated card information to the complete
  desired deck.

Generate creates the deck when it does not exist and reconciles an associated
existing deck when it does. The Update behavior described below is therefore an
internal Generate reconciliation mode retained for compatibility, not a
separate public phase.

Each phase MUST retain its own validation boundary, report, and success or
failure status.

## 2. Import operation

### 2.1 Inputs and preconditions

Import accepts one source CrowdAnki JSON file. The source:

- MUST be valid UTF-8 JSON;
- MUST represent a supported CrowdAnki deck structure; and
- MUST contain notes whose import field mapping is known.

For each source note:

- `fields` MUST exist and contain at least one element;
- `fields[0]` MUST supply the candidate vocabulary expression;
- `fields[1]`, when present, MAY inform an annotation or clarification but MUST
  NOT be copied mechanically into learner-facing content; and
- malformed or ambiguous notes MUST be reported with enough context to identify
  them.

The source MAY be large. Import MUST NOT rely on interactive copying of notes or
loading the JSON into a text editor.

### 2.2 Output

Import MUST create one versioned UTF-8 GCL conforming to
`generation-control-file-spec.md`. Imported ordering SHOULD follow source note
ordering until the ordering policy is decided.

Import MUST NOT:

- modify or replace the source JSON;
- create learner-facing definitions or examples;
- retain the source JSON as the authority after editorial adoption of the GCL; or
- silently omit a source note.

Its report MUST reconcile source-note count with created entries, entries skipped
as exact duplicates, entries skipped under another approved rule, and errors.
Before publication, Import MUST deduplicate the proposed GCL. When exact
duplicates are encountered, Import MUST retain the first occurrence
and omit later occurrences from the proposed GCL.

Import MUST apply the reading-resolution rules in `content-generation-spec.md`.
It MUST annotate the existing entry with the first qualifying reading, append
other qualifying readings to the end of the proposed GCL, and exclude archaic,
uncommon, or unnatural alternatives under the established policy. When reliable
resolution is not possible, Import MUST emit the numbered clarification workflow
defined in `generation-control-file-spec.md` and MUST NOT publish an unresolved
GCL as complete.

The Batch reading-resolution capability used to normalize an existing unresolved
GCL is also the required reusable reading-resolution stage for future Import
operations. It MUST NOT be removed after the current GCL has been normalized.

After resolving all readings, Import MUST perform a second exact deduplication
pass over the complete annotated entries. Import MUST publish no entry without
exactly one complete hiragana `[reading]`.

After initial import, any later requested vocabulary additions MUST be
appended to the end of the authoritative GCL as required by
`generation-control-file-spec.md`.

### 2.3 Atomicity

Import MUST write and validate a proposed GCL before publishing it to the requested
path. Failure or interruption MUST NOT leave a partial GCL presented as valid.

## 3. Generate operation

### 3.1 Inputs

Generate accepts:

- one valid authoritative GCL;
- one compatible CrowdAnki deck template;
- generation configuration; and
- the approved content-generation mechanism.

Generate MUST NOT require the source JSON from which the GCL may have been
derived.

Before any content generation, Generate MUST purge exact duplicate GCL lines,
publish the cleaned GCL, and validate it. Entries that differ by `[reading]`,
`(な)`, or affix annotation are distinct and MUST be retained.
Generate MUST reject any entry without a complete authoritative `[reading]`.

### 3.2 Template use

Generate MUST treat the deck template separately from an Import source. It MUST
preserve required template structures, including:

- deck and configuration objects;
- note model and field definitions;
- card templates;
- CSS; and
- other required CrowdAnki properties.

Generated notes MUST reference the template’s note-model UUID. The sample note in
the current template contains test placeholders and MUST NOT appear in production
output.

The policy for deck, configuration, note-model, and template UUIDs is unresolved.

### 3.3 Processing and output

Generate MUST:

1. parse and validate the complete GCL;
2. resolve or report every ambiguous entry according to the stop policy;
3. produce content for every eligible entry;
4. validate every generated field;
5. construct one note per distinct eligible GCL entry;
6. validate the complete CrowdAnki object; and
7. publish output only when the run satisfies the adopted error policy.

Output MUST contain no test note, partial placeholder content, or editorial
annotation. Generate creates a complete new artifact. If its requested output path
already exists, Generate MUST overwrite that file with the complete newly
generated deck. It MUST NOT inspect or preserve the existing file as though it
were an Update input.

Overwrite publication MUST occur only after the replacement deck has been
completely written and validated. A write failure MUST NOT leave a truncated file
at the requested path.

### 3.4 Package naming and layout

CrowdAnki import requires a deck JSON file to reside in a directory whose name
matches the JSON filename without `.json`.

Version 1 GCL filenames MUST follow:

```text
<deck-name>_generation_control_file.txt
```

Generate MUST derive:

```text
<deck-name>_crowdanki_deck/
└── <deck-name>_crowdanki_deck.json
```

The package directory MUST be created at the project root. The shared
`generated/` container proposed earlier is not part of the current layout.

For example:

```text
gcl/n1_vocabulary_generation_control_file.txt
    ↓
n1_vocabulary_crowdanki_deck/
└── n1_vocabulary_crowdanki_deck.json
```

Generate MUST reject a GCL filename that does not match the version 1 naming
pattern unless an explicit future specification defines another mapping. Generate
MUST create the package directory when it does not exist and overwrite the JSON
file when it does.

## 4. Update operation

### 4.1 Inputs and association

Update accepts:

- one valid authoritative GCL;
- one existing generated deck package associated with that GCL;
- required generation state;
- a compatible template and configuration; and
- the approved content-generation mechanism.

Before changing anything, Update MUST resolve every unannotated entry through the
same retained Batch-backed reading-resolution stage used by Import. It MUST
atomically publish a fully annotated, post-resolution-deduplicated GCL before
classifying entries or changing the deck. If resolution requires a paid Batch,
Update MUST pause for explicit cost confirmation and resume only after the
results have been collected and validated.

After reading resolution, Update MUST verify GCL-to-deck association and template,
note-model, and state compatibility. The association mechanism is unresolved.

Before association-based entry classification, Update MUST purge exact duplicate
GCL lines, publish the cleaned GCL, and validate it. Separately annotated readings
MUST remain separate entries.

The original source JSON used by Import is not an Update input unless it is also,
independently, the verified associated generated deck. Update MUST NOT confuse the
source import field contract with the four-field generated-note contract.

### 4.2 Classification

Classification MUST operate on the deduplicated GCL.

Update MUST classify entries as at least:

- new;
- previously generated and unchanged;
- changed;
- explicitly selected for regeneration;
- absent from the GCL; or
- ambiguous or unmatchable.

Classification MUST occur before content generation. An entry that matches an
existing generated-note identity MUST NOT also be classified as new. Matching by
written vocabulary alone is insufficient because separately annotated readings
of the same written expression are distinct entries.

Update MUST first match a generated note by the stable identity established by
Generate. Learner-facing `Vocabulary` and `Reading` fields MAY be used only as a
legacy fallback when stable identity is absent. A fallback match MUST be unique;
zero or multiple candidates are unmatchable and MUST stop publication. This
ordering is required because affix entries can share visible fields with
standalone entries and legacy field content can contain an earlier generation
error.

### 4.3 Application

Update MUST generate content only for new or explicitly regenerated entries.
Previously generated unchanged entries MUST retain their existing field contents
and stable card identity.

Update MUST emit at most one note for each distinct GCL entry identity. When the
associated deck already contains that identity, Update MUST preserve or explicitly
regenerate the existing note rather than append a duplicate.

If a legacy GCL or associated deck contains repeated copies of one exact entry,
Update MUST preserve the note corresponding to the first GCL occurrence and
remove later redundant notes. It MUST report the cleanup.

A changed annotation can change interpretation and MUST NOT be treated as harmless
formatting. A changed previously generated entry MUST NOT be regenerated unless
the entry is explicitly selected for regeneration. Without that request, Update
MUST preserve the existing note and report the pending editorial change.

For every existing generated note whose identity is absent from the GCL, Update
MUST report the note as scheduled for removal and MUST remove it from the proposed
generated JSON. The removal report MUST be available before the proposed output
is published.

Update MUST report unmatchable entries and MUST NOT silently rewrite or delete
their notes.

Update MUST append new note objects to the deck's in-memory `notes` array, then
emit a complete CrowdAnki JSON file, not a patch fragment or raw textual append.
It MUST validate the complete proposed deck before publication.

Update MUST preserve the package naming and layout contract. It MUST read and
replace the JSON file inside the associated package directory rather than create a
bare JSON file elsewhere.

### 4.4 External drift

Update MUST detect externally modified managed fields or identities when prior
state makes detection possible. If it detects such drift, Update MUST fail and
MUST NOT publish an updated deck. The failure report MUST identify each affected
note and field or identity property.

### 4.5 Atomicity

Update MUST preserve the existing valid generated JSON until the proposed update
has been completely written and validated. Its replacement strategy MUST support
recovery from interruption or write failure.

## 5. Identity and preservation

An entry identity mechanism MUST:

- remain stable when unrelated entries are inserted or reordered;
- distinguish identical written forms with different readings or metadata;
- match an unchanged entry to its existing generated note;
- prevent accidental duplication; and
- serve both Generate and Update.

Identity MUST distinguish entries such as `脅かす[おどかす]` and
`脅かす[おびやかす]`, even though both produce `脅かす` in the `Vocabulary`
field.

Generate MUST establish the identity information required by later Update.
Physical line number MUST NOT participate in stable identity. The canonical
complete annotated GCL entry is the identity key. Generate MUST derive the note
GUID deterministically from that key under one fixed, versioned namespace so
Update can recover identity without relying on mutable learner-facing fields.
Changing this namespace or derivation is a migration that MUST be versioned and
must preserve an explicit mapping from old identities.

## 6. Large-file requirements

For every operation:

- note and entry matching MUST use an indexed or equivalently scalable approach
  and MUST NOT perform an all-pairs scan;
- implementations SHOULD avoid redundant full representations of large JSON;
- progress SHOULD identify phase and processed/total count when available;
- cancellation or failure MUST leave published inputs and last known-good outputs
  intact; and
- validation MUST scale consistently with the operation.

A streaming parser MAY be used. Quantitative size and memory requirements remain
to be decided.

## 7. Generated package requirements

Generate and Update outputs MUST:

- use a package directory and JSON file with identical base names;
- reside at the project root;
- be valid UTF-8 JSON representing a CrowdAnki `Deck`;
- contain exactly the notes represented by the GCL after required removals,
  additions, duplicate cleanup, and explicit regeneration;
- use the four specified fields in the correct order;
- assign each note to the intended note-model UUID;
- contain unique valid note GUIDs;
- preserve Japanese and HTML without mojibake or double escaping; and
- be published without destroying the last known-good output on failure.

Pretty-printing and JSON key order are implementation choices unless required for
reproducible diffs.

## 8. Operation reports

Every operation MUST emit a report identifying itself as Import, Generate, or
Update and containing:

- input and output paths and detected versions;
- the number and text of exact duplicate GCL entries removed during preflight;
- relevant processed, imported, created, preserved, regenerated, duplicate-cleaned,
  and failed counts;
- clarification requests;
- validation failures with source references; and
- whether output was published.

A report MUST NOT claim success when required output is incomplete.
