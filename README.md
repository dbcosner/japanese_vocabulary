# Japanese Vocabulary Deck Generation

This project builds native Anki `.apkg` decks for advanced Japanese vocabulary
study. Generation Control Files (GCLs) are the editorial source of truth;
generated decks are reproducible derived artifacts.

## Workflow

The workflow has three phases:

1. **Import** extracts a proposed GCL from an APKG and reports unsafe notes.
2. **Populate** creates or reuses validated card content for every GCL entry.
3. **Generate** builds the complete native APKG from the populated workspace.

### Filename convention

Published APKG filenames use lowercase ASCII snake_case:
`beyond_n1_vocabulary.apkg`, not `Beyond N1 Vocabulary.apkg` or
`beyond-n1-vocabulary.apkg`. Populate and Generate enforce this convention for
their `--deck` and `--output` paths.

The filesystem name is separate from the learner-facing Anki deck name. Use
`--deck-name "Beyond N1 Vocabulary"` for a natural display name while retaining
`--output beyond_n1_vocabulary.apkg`. Source APKGs supplied for Import are not
renamed and are exempt from this output convention.

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

Import reduces each source note to only a term and its reading. It removes
presentation content, parenthetical and editorial annotations, legacy
na-adjective markers, and other non-term material; normalizes GCL syntax; and
splits multiple forms or readings when their correspondence is mechanically
clear. Every emitted line is a complete `term[reading]` entry. Notes that cannot
be reduced confidently to that form are excluded and recorded in the review
file.

Explicit source-specific decisions can be applied reproducibly:

```bash
batch-generate import-apkg \
  --apkg path/to/source.apkg \
  --name my_vocabulary \
  --decisions path/to/import-decisions.json \
  --replace
```

### Resolve manually added readings

```bash
batch-generate prepare-readings \
  --gcl gcl/my_vocabulary_generation_control_file.txt
```

Submit and collect the prepared manifest with the normal `submit`, `status`, and
`collect` commands. Publication uses `apply-readings`. This stage is for bare
terms introduced through manual editing; APKG Import excludes source notes with
missing readings instead of placing them in the GCL.

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
allow repeated Anki imports to update the same logical deck. Note GUIDs are
deck-scoped so the same term can exist independently in N1 and N2, while the
template supplies one shared note-type ID for both decks. The Anki deck name
defaults to the logical output name (`n2_vocabulary.apkg` becomes
`N2 Vocabulary`) and may be overridden with `--deck-name`. Each generated deck
also receives a stable, deck-specific options preset containing Anki's default
settings, so its scheduling options can be changed after import without affecting
other decks.

For the Takoboto-derived deck in this repository:

```bash
batch-generate generate \
  --workspace .batch/takoboto_vocabulary \
  --template templates/japanese_vocabulary_deck_template.json \
  --output beyond_n1_vocabulary.apkg \
  --deck-name "Beyond N1 Vocabulary"
```

Its authoritative inventory is
`gcl/takoboto_generation_control_file.txt`. The completed population contains
3,875 validated cards.

### Clean up completed population jobs

The reusable content cache is `.batch/<deck-name>/cards/accepted.jsonl`.
Keep that file together with `project.json` and the final
`populate-report.json` when you want to regenerate a deck without repeating
paid content generation.

After `populate` reports `complete: true` and the APKG has been verified, the
workspace's `batches/`, `history/`, detailed findings, and generation receipt
files are transient and may be removed. They contain request payloads,
downloaded responses, superseded retries, or reproducible summaries; they are
not required by `generate`. The entire `.batch/` tree is ignored by Git because
it is local operational state.

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

Manually authored bare expressions may be appended temporarily for reading
resolution, but APKG Import never emits them. A GCL is not ready for population
or generation until every entry has been resolved.

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
├── docs/               Specifications and workflow documentation
├── gcl/                Generation Control Files
├── src/                Python package
├── templates/          APKG-neutral card templates
├── tests/              Regression tests
├── .batch/             Local population caches and Batch state
├── beyond_n1_vocabulary.apkg
├── n1_vocabulary.apkg  Generated N1 Anki deck
└── n2_vocabulary.apkg  Generated N2 Anki deck
```

See [docs/README.md](docs/README.md) for the complete documentation index.
