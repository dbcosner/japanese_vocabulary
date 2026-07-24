# CrowdAnki Operations Specification

## 1. Scope

This specification defines three operations:

- **Derive**: source CrowdAnki JSON to GCL;
- **Generate**: GCL to a new generated CrowdAnki deck package; and
- **Update**: GCL plus its associated generated deck package to an updated
  package.

An interface MAY compose operations, but each operation MUST retain its own
validation boundary, report, and success or failure status.

## 2. Derive operation

### 2.1 Inputs and preconditions

Derive accepts one source CrowdAnki JSON file. The source:

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

The source MAY be large. Derive MUST NOT rely on interactive copying of notes or
loading the JSON into a text editor.

### 2.2 Output

Derive MUST create one versioned UTF-8 GCL conforming to
`generation-control-file-spec.md`. Imported ordering SHOULD follow source note
ordering until the ordering policy is decided.

Derive MUST NOT:

- modify or replace the source JSON;
- create learner-facing definitions or examples;
- retain the source JSON as the authority after editorial adoption of the GCL; or
- silently omit a source note.

Its report MUST reconcile source-note count with created entries, entries skipped
under an approved rule, and errors.

After initial derivation, any later requested vocabulary additions MUST be
appended to the end of the authoritative GCL as required by
`generation-control-file-spec.md`.

### 2.3 Atomicity

Derive MUST write and validate a proposed GCL before publishing it to the requested
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

### 3.2 Template use

Generate MUST treat the deck template separately from a Derive source. It MUST
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

Before changing anything, Update MUST verify GCL-to-deck association and template,
note-model, and state compatibility. The association mechanism is unresolved.

The original source JSON used by Derive is not an Update input unless it is also,
independently, the verified associated generated deck. Update MUST NOT confuse the
source import field contract with the four-field generated-note contract.

### 4.2 Classification

Update MUST classify entries as at least:

- new;
- previously generated and unchanged;
- changed;
- explicitly selected for regeneration;
- removed from the GCL; or
- ambiguous or unmatchable.

Classification MUST occur before content generation. An entry that matches an
existing generated-note identity MUST NOT also be classified as new. Matching by
written vocabulary alone is insufficient because separately annotated readings
of the same written expression are distinct entries.

### 4.3 Application

Update MUST generate content only for new or explicitly regenerated entries.
Previously generated unchanged entries MUST retain their existing field contents
and stable card identity.

Update MUST emit at most one note for each distinct GCL entry identity. When the
associated deck already contains that identity, Update MUST preserve or explicitly
regenerate the existing note rather than append a duplicate.

A changed annotation can change interpretation and MUST NOT be treated as harmless
formatting. A changed previously generated entry MUST NOT be regenerated unless
the entry is explicitly selected for regeneration. Without that request, Update
MUST preserve the existing note and report the pending editorial change.

For every entry removed from the GCL, Update MUST report the corresponding note as
scheduled for removal and MUST remove it from the proposed generated JSON. The
removal report MUST be available before the proposed output is published.

Update MUST report unmatchable entries and MUST NOT silently rewrite or delete
their notes.

Update MUST emit a complete CrowdAnki JSON file, not a patch fragment. It MUST
validate the complete proposed deck before publication.

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
Physical line number alone MUST NOT be used as stable identity. The identity key,
GUID algorithm, and state store remain open questions.

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
- contain exactly the intended generated notes after required GCL removals;
- use the four specified fields in the correct order;
- assign each note to the intended note-model UUID;
- contain unique valid note GUIDs;
- preserve Japanese and HTML without mojibake or double escaping; and
- be published without destroying the last known-good output on failure.

Pretty-printing and JSON key order are implementation choices unless required for
reproducible diffs.

## 8. Operation reports

Every operation MUST emit a report identifying itself as Derive, Generate, or
Update and containing:

- input and output paths and detected versions;
- relevant processed, created, preserved, regenerated, removed, and failed counts;
- clarification requests;
- validation failures with source references; and
- whether output was published.

A report MUST NOT claim success when required output is incomplete.
