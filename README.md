# Japanese Vocabulary Deck Generation

This project builds native Anki `.apkg` decks for advanced Japanese vocabulary
study. Generation Control Files (GCLs) are the editorial source of truth;
generated decks are reproducible derived artifacts.

## Workflow

The workflow has three phases:

1. **Import** extracts a proposed GCL from an APKG and reports unsafe notes.
2. **Populate** creates or reuses validated card content for every GCL entry.
3. **Generate** builds the complete native APKG from the populated workspace.

### Import an APKG

```bash
batch-generate import-apkg \
  --apkg path/to/source.apkg \
  --name my_vocabulary
```

This writes:

```text
gcl/my_vocabulary_generation_control_file.txt
gcl/my_vocabulary_generation_control_file.import-review.json
```

Import preserves clean embedded readings, normalizes GCL syntax, removes
presentation markup, deduplicates exact entries, and keeps unresolved expressions
for reading resolution. Ambiguous structures are excluded and recorded in the
review file rather than guessed.

Explicit source-specific decisions can be applied reproducibly:

```bash
batch-generate import-apkg \
  --apkg path/to/source.apkg \
  --name my_vocabulary \
  --decisions path/to/import-decisions.json \
  --replace
```

### Resolve missing readings

```bash
batch-generate prepare-readings \
  --gcl gcl/my_vocabulary_generation_control_file.txt
```

Submit and collect the prepared manifest with the normal `submit`, `status`, and
`collect` commands. Publication uses `apply-readings`.

### Populate the cache

Population preparation is local and makes no paid API call:

```bash
batch-generate populate \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --deck n1_vocabulary.apkg
```

Completed Batch outputs are incorporated by running `populate` again. The cache
is stored under `.batch/<deck-name>/` and is keyed by stable GCL identity, so
unchanged entries are reused after reordering or regeneration.

### Generate the APKG

```bash
batch-generate generate \
  --workspace .batch/n1_vocabulary \
  --template templates/japanese_vocabulary_deck_template.json \
  --output n1_vocabulary.apkg
```

Generate is local. It refuses incomplete or stale workspaces and atomically
replaces the requested APKG. Stable project, model, deck, and note identifiers
allow repeated Anki imports to update the same logical deck. The Anki deck name
defaults to the logical output name (`n2_vocabulary.apkg` becomes
`N2 Vocabulary`) and may be overridden with `--deck-name`.

## GCL syntax

Version 1 GCLs are UTF-8 text:

```text
# GCL Version: 1

遭う[あう]
静か[しずか]
~化[か]
無~[む]
```

- `[reading]` is the authoritative complete hiragana reading.
- `~` is ASCII U+007E and marks an open prefix or suffix position.

Part-of-speech behavior, including adjectival-noun usage, is inferred during
content generation rather than encoded in the GCL.

New bare expressions may be appended temporarily, but a GCL is not ready for
population or generation until every entry has been resolved.

## Card format

Each generated note has four fields:

1. `Reading`
2. `Definition`
3. `Examples`
4. `Vocabulary`

The front conceals the written target and emphasizes the portions of the
hiragana reading corresponding to kanji. The back reveals the original written
expression. Definitions and examples are generated in Japanese.

## Safety

- Import, preparation, cache reuse, validation, and APKG generation are local.
- Batch submission requires `--confirm-cost`.
- Source APKGs are never modified.
- Import ambiguity is recorded in a separate review artifact.

## Repository layout

```text
.
├── apkg_exports/       Source APKGs and import review artifacts
├── docs/               Specifications and workflow documentation
├── gcl/                Generation Control Files
├── src/                Python package
├── templates/          APKG-neutral card templates
├── tests/              Regression tests
├── .batch/             Local population caches and Batch state
└── n1_vocabulary.apkg  Generated native Anki deck
```

See [docs/README.md](docs/README.md) for the complete documentation index.
