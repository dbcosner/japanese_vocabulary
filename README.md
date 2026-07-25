# Japanese Vocabulary Deck Generation

This project creates Japanese vocabulary decks designed for
advanced vocabulary acquisition through pronunciation, Japanese definitions, and
natural example sentences.

The project is currently specification-first. Its intended behavior is documented
in [`docs/`](docs/README.md); the implementation and command-line interface have
not yet been finalized.

## Project intentions

The project is intended to maintain three Japanese vocabulary decks through
simple, manually curated **Generation Control Files** (GCLs). Generated
CrowdAnki JSON files are derived artifacts rather than editorial sources of
truth.

## Three-phase workflow

The primary workflow has three phases:

1. **Import** converts a source deck into its Generation Control File (GCL).
2. **Populate** creates and reuses validated card data for the GCL.
3. **Generate** reconciles the current GCL into a final deck.

Create and Update are not separate phases. Generate creates a missing deck or
updates an associated existing deck to the complete desired GCL state. Existing
notes are preserved, new notes are added, duplicates are removed, and notes
whose terms were removed from the GCL are removed.

Population artifacts are isolated by logical deck:

```text
.batch/
└── <deck-name>/
    ├── project.json
    ├── populate-report.json
    ├── cards/
    │   └── accepted.jsonl
    └── batches/
        └── <source-range>/
            ├── input_<range>.jsonl
            ├── manifest_<range>.json
            ├── state_<range>.json
            └── output_<range>.jsonl
```

`project.json` records the durable GCL/deck association. Individual manifests
record the GCL hash used for that particular request. The accepted-card cache is
keyed by deterministic GCL-entry identity, so inserting or reordering entries
does not repopulate unchanged cards.

Prepare population work without making a paid API call:

```bash
batch-generate populate \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --deck n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json
```

After the prepared batches have been submitted and collected with the existing
`submit`, `status`, and `collect` commands, rerun `populate` to validate and
incorporate completed outputs into `cards/accepted.jsonl`.

Generate CrowdAnki JSON from the populated workspace:

```bash
batch-generate generate \
  --workspace .batch/n1_vocabulary \
  --format crowdanki \
  --template templates/N1_vocabulary_-_CrowdAnki/deck.json \
  --output n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json
```

Generate an `.apkg` from the same workspace:

```bash
batch-generate generate \
  --workspace .batch/n1_vocabulary \
  --format apkg \
  --template templates/N1_vocabulary_-_CrowdAnki/deck.json \
  --output n1_vocabulary.apkg
```

Generate validates the GCL snapshot and every accepted card before publishing.
It refuses incomplete, stale, or invalid workspaces. CrowdAnki generation
reconciles an existing JSON deck while preserving stable note metadata; APKG
generation rebuilds the package with deterministic deck, model, and note
identifiers so repeated imports update the same logical notes.

For a one-time migration from a previously generated complete CrowdAnki deck,
`seed-cache` reconstructs the accepted-card cache from the deck's four fields.
It publishes nothing unless every current GCL entry matches exactly one note and
all reconstructed cards pass the normal validation rules:

```bash
batch-generate seed-cache \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --deck n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json
```

Each generated card is intended to:

- show a hiragana reading on the front, with portions corresponding to kanji in
  bold;
- provide a concise Japanese definition suitable for a JLPT N1 learner;
- normally provide three natural Japanese example sentences, while allowing one
  to five when natural coverage requires fewer or more;
- conceal the target vocabulary's original written form throughout the front; and
- reveal only the original vocabulary expression on the back.

Examples should also expose productive grammar: nouns that commonly occur before
`の` or combine with `する` should demonstrate those constructions naturally.

Correct interpretation, natural Japanese, pedagogical value, consistency, and
maintainability guide content generation. When a reading or interpretation
remains ambiguous, the system is expected to request clarification rather than
guess.

## Core capabilities

The project will support three independent operations:

```text
Source CrowdAnki JSON ── Import ──▶ GCL
                                      │
                                      ├── Generate ──▶ New CrowdAnki JSON
                                      │
Existing generated JSON ◀─────────────└── Update ───▶ Updated CrowdAnki JSON
```

### Import

Create a UTF-8 GCL from a previous CrowdAnki JSON export. Import deduplicates the
proposed entries and resolves readings and interpretations under the established
disambiguation policy before publishing the GCL. The source export is
authoritative only for this initial import.

Reading resolution is a retained Import capability. The same Batch-backed stage
used to normalize a legacy GCL is reused whenever a future Import produces
unresolved expressions.

### Generate

Create a complete new CrowdAnki JSON deck from a GCL and a compatible deck
template. Generate writes a CrowdAnki package directory whose JSON file has the
same base name as its containing directory. It may overwrite the package's JSON
file; it does not preserve content from that file.

### Update

Update an existing generated CrowdAnki JSON deck from its associated GCL. Update
is intended to:

- generate cards for new entries;
- match existing entries before generation so an already generated entry is not
  duplicated;
- preserve unchanged cards and note identities;
- regenerate changed entries only when explicitly requested;
- remove notes whose entries disappear from the GCL;
- fail rather than overwrite managed content edited outside the generator.

The current Batch tooling also supports staged prefix expansion. A declared
`--through` boundary preserves matching existing notes and adds validated missing
notes through that GCL position. Such a prefix deck is an intermediate artifact,
not the final complete deck.

## Source-of-truth model

```text
Before GCL creation:  original CrowdAnki export
After GCL creation:   Generation Control File
Generated deck:       derived output
```

Once a GCL has been adopted, vocabulary additions and editorial changes belong in
that file. The original export is no longer consulted during routine Generate or
Update operations.

To add vocabulary, an editor may append bare expressions to the end of the GCL.
Update begins by resolving those additions to complete `[reading]` annotations,
appending other qualifying readings, and deduplicating before it compares the GCL
with the deck. The deck is not modified until that reading stage succeeds.

GCL entries may include generation-only annotations:

```text
遭う[あう]
一入[ひとしお]
静か[しずか](な)
～化[か]
無～[む]
```

- `[reading]` supplies an authoritative reading.
- `(な)` identifies a na-adjective.
- `～` identifies a prefix or suffix attachment point.

These annotations guide content generation and must not appear on generated
cards.

Every GCL entry records one complete authoritative `[reading]`. Different
qualifying readings of the same written expression are separate GCL entries and
produce separate cards. Import resolves these readings before publishing the GCL;
Generate and Update reject unresolved entries. Newly requested entries are
resolved and appended to the end of an existing GCL.

Exact duplicate GCL lines are not separate vocabulary entries. Deduplication keeps
the first occurrence, removes later occurrences, and preserves the order of all
remaining entries.

Import performs this deduplication before publishing its GCL; Generate and Update
perform it as a GCL preflight step.
Because `[reading]` is part of the entry, separately annotated readings are not
duplicates.

## Technical overview

- Inputs and outputs use UTF-8.
- CrowdAnki JSON supplies the interchange format for source and generated decks.
- CrowdAnki import expects each generated JSON file to be inside a directory with
  the same base name.
- A generated note currently has four fields: `Reading`, `Definition`,
  `Examples`, and `Vocabulary`.
- Deck templates provide the CrowdAnki note model, card templates, CSS, and deck
  configuration.
- Stable entry identity derives from the complete annotated GCL entry, allowing
  Update to match entries without relying on mutable line numbers.
- Large files are expected. Processing should avoid quadratic entry matching,
  report progress for long operations, and publish outputs atomically.
- The detailed validation contract covers GCL syntax, linguistic content, target
  concealment, note identity, CrowdAnki structure, and interruption safety.

## Repository layout

```text
.
├── docs/        Project specifications and decision log
├── gcl/         Generation Control Files
├── templates/   CrowdAnki deck templates
└── <deck>_crowdanki_deck/
    └── <deck>_crowdanki_deck.json
```

Generated deck packages currently live at the project root. For example:

```text
gcl/n1_vocabulary_generation_control_file.txt
    ↓
n1_vocabulary_crowdanki_deck/
└── n1_vocabulary_crowdanki_deck.json
```

Start with the [documentation index](docs/README.md). Important specifications
include:

- [Product specification](docs/product-spec.md)
- [Generation Control File specification](docs/generation-control-file-spec.md)
- [Content generation specification](docs/content-generation-spec.md)
- [Card format specification](docs/card-format-spec.md)
- [CrowdAnki operations specification](docs/deck-generation-spec.md)
- [Validation specification](docs/validation-spec.md)
- [Batch generation operator guide](docs/batch-generation.md)
- [Open questions and decision log](docs/open-questions.md)

## Batch generation tooling

The repository includes a resumable Python Batch API client with `prepare`,
`submit`, `status`, `collect`, and `apply` commands. Only `submit` can start paid
model processing, and it requires an explicit `--confirm-cost` acknowledgement.
The test suite uses local fake clients and cannot create a billable batch.

See the [Batch generation operator guide](docs/batch-generation.md) for
installation, cost-free tests, a 25-card pilot, and the full-generation workflow.

## Project status

The specifications are under active review. Several implementation decisions,
including stable identity, generation-state storage, command interfaces, and
quantitative large-file targets, remain open. This README is therefore tentative
and should evolve with the specifications and implementation.

The N1 GCL has been deduplicated and is being expanded with explicitly resolved
readings. The current proof-of-concept deck package contains 100 cards derived
from its first 100 entries. The first 10 cards were preserved and 90 new cards
were added without duplication:

[`n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json`](n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json)
