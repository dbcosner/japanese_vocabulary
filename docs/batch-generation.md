# Batch and APKG Workflow

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -e .
```

Copy `.env.example` to `.env` and provide an API key only when paid Batch
submission is needed.

## Import

```bash
batch-generate import-apkg \
  --apkg apkg_exports/source.apkg \
  --name source_vocabulary
```

Review the generated `*.import-review.json`. If a source package needs explicit
cleanup, record it in a decisions JSON file and rerun with `--decisions` and
`--replace`.

## Reading resolution

Prepare unresolved GCL entries locally:

```bash
batch-generate prepare-readings \
  --gcl gcl/source_vocabulary_generation_control_file.txt
```

Start a paid job only with explicit acknowledgement:

```bash
batch-generate submit \
  --manifest .batch/manifest_readings.json \
  --confirm-cost
```

Use `status` and `collect`, then validate and publish:

```bash
batch-generate apply-readings \
  --manifest .batch/manifest_readings.json \
  --output .batch/output_readings.jsonl \
  --report .batch/reading-report.json
```

## Population

```bash
batch-generate populate \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --deck n1_vocabulary.apkg
```

This command is local. It validates collected output, incorporates accepted cards,
and prepares only missing requests. Submit prepared manifests separately with
`--confirm-cost`, collect them, and rerun `populate` until `complete` is true.

Rejected cards may be isolated with `prepare-retry`; a completed retry may be
combined with the base output using `merge-retry`.

`prepare` is the lower-level range-oriented request generator:

```bash
batch-generate prepare \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --start 1 \
  --end 100 \
  --work-dir .batch/manual
```

It writes a standalone input and manifest but does not associate collected cards
with a population workspace. The normal end-to-end workflow should use
`populate`.

## APKG generation

```bash
batch-generate generate \
  --workspace .batch/n1_vocabulary \
  --template templates/japanese_vocabulary_deck_template.json \
  --output n1_vocabulary.apkg
```

The template is reusable across proficiency levels and does not contain a deck
name. Generate derives the default Anki deck name from the logical deck key
established by `populate`; pass `--deck-name "Custom Name"` to override it.

Generation is local and atomically overwrites the requested APKG. It fails if the
GCL changed after population, the accepted cache is incomplete, a card is
invalid, or the output is not `.apkg`.

## Decisions-file format

The optional decisions JSON currently recognizes:

```json
{
  "rules": {
    "split_comparisons": true,
    "strip_parentheticals_except_na": true,
    "strip_editorial_labels": true,
    "split_equivalent_spellings": true
  },
  "note_overrides": {
    "1234567890": ["語彙[ごい]"],
    "1234567891": null
  }
}
```

Override keys are source Anki note IDs as strings. An array supplies exact GCL
entries; `null` drops that source note. Unknown rule keys are currently ignored.

## CLI command summary

| Command | Network or cost behavior |
| --- | --- |
| `import-apkg` | Local |
| `prepare-readings` | Local request preparation |
| `apply-readings` | Local validation and GCL publication |
| `populate` | Local cache validation and request preparation |
| `generate` | Local APKG generation |
| `prepare` | Local standalone range preparation |
| `prepare-retry` | Local repair-request preparation |
| `merge-retry` | Local JSONL merge |
| `submit` | Networked and potentially paid; requires `--confirm-cost` |
| `status` | Networked status refresh |
| `collect` | Networked result download after completion |
