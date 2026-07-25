# Batch Generation Operator Guide

## 1. Purpose and safety boundary

`batch-generate` prepares and manages asynchronous OpenAI Batch API requests for
the **Generate** operation.

Only `submit` starts model processing that can incur API charges. It requires the
explicit `--confirm-cost` flag. The following commands are local or read-only with
respect to model generation:

- `prepare` modifies only local files and may remove exact duplicate GCL entries;
- `status` retrieves batch metadata;
- `collect` downloads already generated output; and
- `apply` validates downloaded output and constructs the local CrowdAnki JSON.

The automated tests use fake clients and temporary files. They never instantiate
the OpenAI client or make network requests.

## 2. Installation

Install Python 3.11 or newer, open Bash in the project root, and create an
isolated environment:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -e .
```

Create the required local credential file:

```bash
cp .env.example .env
```

Open `.env` in an editor and replace the placeholder:

```dotenv
OPENAI_API_KEY=replace-with-your-openai-api-key
```

The CLI reads the key only from `.env` in the current directory. It does not use
an operating-system environment variable as a fallback. `.env` is ignored by Git;
`.env.example` is committed and contains no credential.

## 3. Cost-free tests

```bash
python -m unittest discover -s tests -v
```

These tests cover GCL deduplication, JSONL preparation, the paid-action guard,
submission and status behavior through a fake client, collection, card
validation, review-item rejection, atomic publication, and removal of the
template placeholder note.

## 4. Proof-of-concept batch

Prepare entries 176 through 200 without contacting OpenAI:

```bash
batch-generate prepare \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --work-dir .batch \
  --start 176 \
  --end 200
```

Inspect the generated manifest and JSONL before submission. Preparation performs
the mandatory exact-duplicate GCL cleanup and records removed duplicates in the
manifest.

Submit only after reviewing the request file:

```bash
batch-generate submit \
  --manifest .batch/manifest_000176_000200.json \
  --confirm-cost
```

The command saves a state file containing the batch ID. The terminal may then be
closed and the computer may be shut down.

Check status later:

```bash
batch-generate status \
  --state .batch/state_000176_000200.json
```

After the status becomes `completed`, download the results:

```bash
batch-generate collect \
  --state .batch/state_000176_000200.json
```

Build a proof deck:

```bash
batch-generate apply \
  --manifest .batch/manifest_000176_000200.json \
  --output .batch/output_000176_000200.jsonl \
  --template templates/N1_vocabulary_-_CrowdAnki/deck.json \
  --deck-output pilot_crowdanki_deck/pilot_crowdanki_deck.json \
  --allow-partial
```

`--allow-partial` is required because a pilot manifest does not cover the complete
GCL. It must not be used for final publication.

## 5. Full generation

After accepting the pilot, omit `--start` and `--end` to prepare every deduplicated
GCL entry:

```bash
batch-generate prepare \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --work-dir .batch
```

Submit, check, and collect it using the resulting `000001` manifest and state
filenames. Apply the complete result without `--allow-partial`:

```bash
batch-generate apply \
  --manifest .batch/manifest_000001_001666.json \
  --output .batch/output_000001_001666.jsonl \
  --template templates/N1_vocabulary_-_CrowdAnki/deck.json \
  --deck-output n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json
```

Use the actual ending index printed by `prepare`; the example `001666` is not a
permanent assumption.

## 6. Publication and review rules

`apply` publishes no deck when:

- an output request is missing, duplicated, unexpected, or failed;
- a response requests editorial review;
- the reading or card fields fail mechanical validation;
- the written target is exposed on the front;
- an alternate reading must first be appended to the GCL;
- the manifest covers only part of the GCL without explicit pilot authorization;
  or
- the output directory and JSON filename do not have the same base name.

Findings are written beside the requested deck as
`<deck>.generation-report.json`. Correct the GCL or generation input, prepare a
new batch for the affected entries, and do not treat a partial artifact as the
final deck.
