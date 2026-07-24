# Japanese Vocabulary Deck Generation

This project creates CrowdAnki-compatible Japanese vocabulary decks designed for
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

Each generated card is intended to:

- show a hiragana reading on the front, with portions corresponding to kanji in
  bold;
- provide a concise Japanese definition suitable for a JLPT N1 learner;
- provide three to five natural Japanese example sentences;
- conceal the target vocabulary's original written form throughout the front; and
- reveal only the original vocabulary expression on the back.

Correct interpretation, natural Japanese, pedagogical value, consistency, and
maintainability guide content generation. When a reading or interpretation
remains ambiguous, the system is expected to request clarification rather than
guess.

## Core capabilities

The project will support three independent operations:

```text
Source CrowdAnki JSON ── Derive ──▶ GCL
                                      │
                                      ├── Generate ──▶ New CrowdAnki JSON
                                      │
Existing generated JSON ◀─────────────└── Update ───▶ Updated CrowdAnki JSON
```

### Derive

Create a UTF-8 GCL from a previous CrowdAnki JSON export. The source export is
authoritative only for this initial derivation.

### Generate

Create a complete new CrowdAnki JSON deck from a GCL and a compatible deck
template. Generate writes a CrowdAnki package directory whose JSON file has the
same base name as its containing directory. It may overwrite the package's JSON
file; it does not preserve content from that file.

### Update

Update an existing generated CrowdAnki JSON deck from changes to its associated
GCL. Update is intended to:

- generate cards for new entries;
- match existing entries before generation so an already generated entry is not
  duplicated;
- preserve unchanged cards and note identities;
- regenerate changed entries only when explicitly requested;
- remove notes for entries removed from the GCL; and
- fail rather than overwrite managed content edited outside the generator.

## Source-of-truth model

```text
Before GCL creation:  original CrowdAnki export
After GCL creation:   Generation Control File
Generated deck:       derived output
```

Once a GCL has been adopted, vocabulary additions and editorial changes belong in
that file. The original export is no longer consulted during routine Generate or
Update operations.

GCL entries may include generation-only annotations:

```text
遭う
一入[ひとしお]
静か(な)
～化
無～
```

- `[reading]` supplies an authoritative reading.
- `(な)` identifies a na-adjective.
- `～` identifies a prefix or suffix attachment point.

These annotations guide content generation and must not appear on generated
cards.

When a term has more than one plausible reading, the intended reading is recorded
with `[reading]`. Different requested readings of the same written expression are
separate GCL entries and produce separate cards. Newly requested entries are
appended to the end of an existing GCL.

## Technical overview

- Inputs and outputs use UTF-8.
- CrowdAnki JSON supplies the interchange format for source and generated decks.
- CrowdAnki import expects each generated JSON file to be inside a directory with
  the same base name.
- A generated note currently has four fields: `Reading`, `Definition`,
  `Examples`, and `Vocabulary`.
- Deck templates provide the CrowdAnki note model, card templates, CSS, and deck
  configuration.
- Stable entry identity and generation state will allow Update to match GCL
  entries to existing notes without relying on line numbers.
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
- [Open questions and decision log](docs/open-questions.md)

## Project status

The specifications are under active review. Several implementation decisions,
including stable identity, generation-state storage, command interfaces, and
quantitative large-file targets, remain open. This README is therefore tentative
and should evolve with the specifications and implementation.

The current proof-of-concept deck package contains 100 cards derived from the
first 100 entries of the N1 GCL as it stood at the time of that Update. The first
10 cards were preserved and 90 new cards were added without duplication:

[`n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json`](n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json)
