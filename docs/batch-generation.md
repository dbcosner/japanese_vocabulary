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
  --manifest .batch/reading-normalization/manifest.json \
  --confirm-cost
```

Use `status` and `collect`, then validate and publish:

```bash
batch-generate apply-readings \
  --manifest <manifest.json> \
  --output <output.jsonl> \
  --report <report.json>
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

## APKG generation

```bash
batch-generate generate \
  --workspace .batch/n1_vocabulary \
  --template templates/n1_vocabulary_deck_template.json \
  --output n1_vocabulary.apkg
```

Generation is local and atomically overwrites the requested APKG. It fails if the
GCL changed after population, the accepted cache is incomplete, a card is
invalid, or the output is not `.apkg`.

## Syntax migration

An associated workspace may be migrated without changing cached identities:

```bash
batch-generate migrate-gcl-syntax \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --workspace .batch/n1_vocabulary
```

The migration validates every record, updates hashes, preserves deterministic
GUIDs, and writes a recovery backup before publication.
