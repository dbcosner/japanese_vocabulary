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

### 3.1 Derive

**Derive** creates a new GCL from a previous CrowdAnki JSON export.

| Contract element | Requirement |
| --- | --- |
| Primary input | One source CrowdAnki JSON file |
| Supporting input | Import configuration, when required |
| Primary output | One valid versioned GCL |
| Authority after success | The new GCL |

Derive MUST NOT modify its source JSON.

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

**Update** revises an existing generated CrowdAnki JSON file to reflect changes in
its associated GCL.

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
- remove generated notes whose entries were removed from the GCL;
- require an explicit regeneration request before rewriting a previously generated
  entry whose reading, annotations, or other editorial metadata changed; and
- fail if it detects external changes to managed note fields or identities.

### 3.4 Separation of operations

- Derive MUST be usable without generating a deck.
- Generate MUST be usable with a valid manually created GCL; Derive in the same
  run MUST NOT be required.
- Update MUST be usable without repeating Derive.
- The source deck accepted by Derive and the generated deck accepted by Update
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

If multiple source notes yield the same exact annotated GCL entry, Derive MUST
retain the first occurrence and report later occurrences as duplicates rather
than write repeated GCL lines.

The generator MUST NOT assume that the initial-import field layout is also the
layout of the generated-deck template.

### 5.2 Ongoing maintenance

Once a GCL has been created, that GCL becomes the authoritative vocabulary list
for its deck. New vocabulary and editorial changes MUST be made in the GCL.

The generated CrowdAnki deck MUST be reproducible from:

- the GCL;
- the deck template;
- the generator version and configuration;
- any retained generation state required for preservation; and
- the approved content-generation process.

How generation state is represented remains an open question.

## 6. Workflows

### 6.1 Initial derivation and generation

The system MUST support this conceptual workflow:

1. Read an original CrowdAnki export.
2. Create a valid GCL containing the imported vocabulary.
3. Surface ambiguous or malformed imports for editorial resolution.
4. Conclude Derive with a valid GCL and report.
5. In a separate Generate operation, generate content for every resolved entry.
6. Validate the content and output deck.
7. Emit the complete generated CrowdAnki deck.

Completing Derive MUST NOT implicitly authorize Generate unless the invocation
explicitly requests both operations.

### 6.2 Incremental maintenance

The system MUST support this conceptual workflow:

1. Read the authoritative GCL.
2. Purge exact duplicate GCL entries while retaining separately annotated
   readings.
3. Read and verify the associated generated CrowdAnki JSON.
4. Classify new, unchanged, changed, removed, and explicitly regenerated entries.
5. Confirm that entries classified as existing will not be emitted as duplicate
   notes.
6. Generate and validate content only where required by the update policy.
7. Preserve previously generated cards byte-for-byte at the field-content level
   unless explicit regeneration was requested.
8. Report notes that will be removed because their GCL entries were removed.
9. Remove those notes from the proposed output.
10. Emit a valid updated deck and an Update report.

Reordering a GCL entry MUST NOT by itself cause content regeneration. The exact
identity and explicit-regeneration mechanisms are unresolved.

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
  and entry count for routine Derive, Generate, and Update work.
- **Extensibility**: the note model SHOULD permit future pronunciation and usage
  features without changing the meaning of existing fields.
