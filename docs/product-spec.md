# Product Specification

## 1. Purpose

The system converts Japanese vocabulary lists derived from CrowdAnki exports into
new CrowdAnki decks optimized for learning through pronunciation, Japanese
explanation, contextual examples, and delayed revelation of the written form.

Generated decks are derived artifacts. They are not the editorial source of
truth.

## 2. Goals

The system MUST:

- maintain each deck through a human-editable UTF-8 Generation Control File;
- generate advanced, natural Japanese learning content for each entry;
- conceal the original written form on the front of every card;
- reveal only the original vocabulary expression on the back;
- preserve previously generated cards during incremental maintenance unless
  regeneration is explicitly requested;
- maintain at most one GCL entry for each exact annotated-entry line;
- stop and request clarification when the intended reading or interpretation
  cannot be determined reliably; and
- produce CrowdAnki-compatible JSON based on a defined deck template.

## 3. Required capabilities

The system MUST implement three independently invocable and testable operations.

### 3.1 Import

**Import** creates a new GCL from a previous CrowdAnki JSON export.

| Contract element | Requirement |
| --- | --- |
| Primary input | One source CrowdAnki JSON file |
| Supporting input | Import configuration, when required |
| Primary output | One valid versioned GCL |
| Authority after success | The new GCL |

Import MUST deduplicate proposed GCL entries and resolve ambiguous readings and
interpretations according to the GCL and content-generation specifications before
publishing the GCL. Import MUST NOT modify its source JSON.

### 3.2 Generate

**Generate** creates a new CrowdAnki JSON file from a GCL.

| Contract element | Requirement |
| --- | --- |
| Primary input | One authoritative GCL |
| Supporting input | One deck template and generation configuration |
| Primary output | One new generated CrowdAnki deck package |
| Authority after success | The GCL remains authoritative |

Generate MUST produce a complete deck; it is not an update of the original source
export.

Before parsing entries for content generation, Generate MUST purge exact duplicate
GCL lines according to `generation-control-file-spec.md`.

### 3.3 Update

**Update** synchronizes an existing generated CrowdAnki JSON file with its
associated GCL. It adds new entries, removes notes whose entries are absent, and
MAY regenerate selected existing entries when explicitly requested.

| Contract element | Requirement |
| --- | --- |
| Primary inputs | One authoritative GCL and its associated generated JSON |
| Supporting input | Generation state, template, and configuration as required |
| Primary output | One updated generated CrowdAnki deck package |
| Authority after success | The GCL remains authoritative |

Update MUST preserve previously generated content and stable note identity where
the update policy requires preservation. It MUST NOT treat the original import
deck as the continuing source of truth.

Update MUST:

- purge exact duplicate GCL lines before classifying entries;
- match proposed entries against existing generated-note identities before
  generating content and MUST NOT create a second note for an entry that has
  already been generated;
- remove generated notes whose entries are absent from the GCL;
- require an explicit regeneration request before rewriting a previously generated
  entry whose reading, annotations, or other editorial metadata changed; and
- fail if it detects external changes to managed note fields or identities.

### 3.4 Separation of operations

- Import MUST be usable without generating a deck.
- Generate MUST be usable with a valid manually created GCL; Import in the same
  run MUST NOT be required.
- Update MUST be usable without repeating Import.
- The source deck accepted by Import and the generated deck accepted by Update
  have different roles and MAY use different note models.
- A failure MUST be reported as belonging to the operation in which it occurred.

## 4. Non-goals for the current version

The current version does not require:

- pitch-accent data;
- audio;
- frequency rankings;
- register, collocation, or extended usage fields;
- automatic synchronization with Anki;
- automatic rewriting of previously generated content; or
- a particular command-line or graphical interface.

These exclusions do not prevent a conforming implementation from having an
interface, but interface behavior MUST NOT weaken the specifications.

## 5. Source-of-truth model

### 5.1 Initial import

For a source deck that conforms to the initial-import contract:

- `fields[0]` MUST be treated as the original vocabulary expression.
- `fields[1]`, when present and non-empty, MAY be used as supporting editorial
  information.
- The source deck is authoritative only while constructing the initial GCL.

If multiple source notes yield the same exact annotated GCL entry, Import MUST
retain the first occurrence and report later occurrences as duplicates rather
than write repeated GCL lines.

Import MUST apply the reading-resolution and disambiguation rules in
`content-generation-spec.md`. It MUST annotate resolved readings, append
additional qualifying readings in the established order, and omit archaic,
uncommon, or unnatural alternatives under that policy. It MUST stop for editorial
clarification when the policy does not permit a reliable decision.
It MUST publish no unannotated entry and MUST deduplicate the complete annotated
entries again after reading resolution.

The generator MUST NOT assume that the initial-import field layout is also the
layout of the generated-deck template.

### 5.2 Ongoing maintenance

Once a GCL has been created, that GCL becomes the authoritative vocabulary list
for its deck. New vocabulary and editorial changes MUST be made in the GCL.
An editor may append bare expressions as temporary working additions. Update
MUST resolve and atomically annotate those additions before treating the GCL as
operation-ready or classifying deck changes.

The generated CrowdAnki deck MUST be reproducible from:

- the GCL;
- the deck template;
- the generator version and configuration;
- any retained generation state required for preservation; and
- the approved content-generation process.

How generation state is represented remains an open question.

## 6. Workflows

### 6.1 Initial import and generation

The system MUST support this conceptual workflow:

1. Read an original CrowdAnki export.
2. Create a proposed GCL containing the imported vocabulary.
3. Surface ambiguous or malformed imports for editorial resolution.
4. Deduplicate the proposed GCL and resolve or report ambiguous readings and
   interpretations.
5. Verify that every entry has exactly one complete authoritative reading,
   deduplicate again after resolution, and conclude Import with a valid GCL and
   report.
6. In a separate Generate operation, generate content for every resolved entry.
7. Validate the content and output deck.
8. Emit the complete generated CrowdAnki deck.

Completing Import MUST NOT implicitly authorize Generate unless the invocation
explicitly requests both operations.

### 6.2 Incremental maintenance

The system MUST support this conceptual workflow:

1. Read the authoritative GCL.
2. Resolve every unannotated manual addition, append qualifying alternate
   readings, and deduplicate the resulting annotated entries.
3. Atomically publish and validate the fully resolved GCL.
4. Read and verify the associated generated CrowdAnki JSON.
5. Classify new, unchanged, changed, absent-from-GCL, and explicitly regenerated
   entries.
6. Confirm that entries classified as existing will not be emitted as duplicate
   notes.
7. Generate and validate content only where required by the update policy.
8. Preserve previously generated cards byte-for-byte at the field-content level
   unless explicit regeneration was requested.
9. Report and remove existing notes whose identities are absent from the GCL.
10. Append new note objects to the proposed deck's `notes` array.
11. Validate and atomically replace the complete JSON file; Update MUST NOT append
    raw text to a JSON file.
12. Emit a valid updated deck and an Update report.

Reordering a GCL entry MUST NOT by itself cause content regeneration. Entry
identity is the complete canonical annotated GCL entry and does not contain its
line number. The explicit-regeneration mechanism remains unresolved.

Generate MUST replace an existing file at its requested output path. This
replacement is intentional Generate behavior and MUST NOT be interpreted as
Update.

Generated deck packages MUST use the directory and filename convention defined in
`deck-generation-spec.md`. CrowdAnki import compatibility requires the JSON file
to reside in a directory with the same base name.

## 7. Large-input behavior

All three operations MUST be safe for the largest supported project files.
Implementations MUST:

- document any input-size, note-count, memory, or runtime limits;
- avoid unnecessary duplicate in-memory copies of an entire deck;
- avoid quadratic matching of GCL entries and generated notes;
- provide progress information for operations that are not near-instantaneous;
- publish outputs transactionally so interruption does not corrupt an existing
  GCL or generated deck; and
- report resource exhaustion without presenting a partial artifact as complete.

Whether bounded-memory streaming is mandatory, and what quantitative targets
apply, remain open questions.

## 8. Decision priorities

When an approved specification does not settle a decision, the following order
MUST guide resolution:

1. correct interpretation of the intended vocabulary;
2. natural Japanese;
3. pedagogical value for an advanced learner;
4. consistency across the deck; and
5. long-term maintainability.

These priorities do not authorize guessing. Material linguistic uncertainty MUST
be surfaced for clarification.

## 9. Quality attributes

- **Correctness**: content MUST reflect the intended reading and meaning.
- **Naturalness**: Japanese MUST read as if written by a proficient native
  speaker.
- **Traceability**: validation errors MUST identify the deck and GCL entry.
- **Determinism of preservation**: unchanged entries MUST remain unchanged during
  Update.
- **Recoverability**: no operation MUST overwrite the sole copy of an input or a
  last known-good output without a recoverable replacement strategy.
- **Scalability**: processing time SHOULD grow approximately linearly with note
  and entry count for routine Import, Generate, and Update work.
- **Extensibility**: the note model SHOULD permit future pronunciation and usage
  features without changing the meaning of existing fields.
