# Batch Generation Operator Guide

## 1. Purpose and safety boundary

`batch-generate` prepares and manages asynchronous OpenAI Batch API requests for
the **Populate** phase and reconciles accepted population data during the
**Generate** phase.

Only `submit` starts model processing that can incur API charges. It requires the
explicit `--confirm-cost` flag. The following commands are local or read-only with
respect to model generation:

- `prepare` modifies only local files and may remove exact duplicate GCL entries;
- `populate` incrementally prepares missing entries inside the associated
  `.batch/<deck-name>/` workspace and incorporates valid completed outputs;
- `seed-cache` strictly migrates a complete generated deck into a population
  cache without making an API call;
- `generate` performs the same offline population check and publishes only when
  every current GCL entry has accepted card data;
- `status` retrieves batch metadata;
- `collect` downloads already generated output; and
- `prepare-retry` and `merge-retry` locally prepare and reconcile rejected-only
  retries; and
- `apply` validates downloaded output and constructs the local CrowdAnki JSON.

The low-level `prepare`, `apply`, `apply-update`, `prepare-remainder`, and
`run-plan` commands remain available for compatibility and recovery. New
workflows SHOULD use `populate` and `generate`.

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

## 4. Import-stage reading normalization

Generate accepts only fully annotated GCL entries. For a legacy GCL containing
unannotated expressions—or a proposed GCL being created by Import—prepare a
reading-only batch locally:

```bash
batch-generate prepare-readings \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --work-dir .batch
```

Inspect `.batch/input_readings.jsonl`, then explicitly submit it:

```bash
batch-generate submit \
  --manifest .batch/manifest_readings.json \
  --confirm-cost
```

Check and collect the batch:

```bash
batch-generate status \
  --state .batch/state_readings.json

batch-generate collect \
  --state .batch/state_readings.json
```

Validate every result and atomically replace the GCL:

```bash
batch-generate apply-readings \
  --manifest .batch/manifest_readings.json \
  --output .batch/output_readings.jsonl \
  --report .batch/reading-normalization-report.json
```

The apply step preserves existing annotations, annotates the original position
with the first qualifying reading, appends other qualifying readings, and removes
exact duplicates exposed after resolution. It publishes nothing if any reading
requires review.

The applicator safely collapses duplicate returned readings and discards malformed
alternatives when at least one valid complete hiragana reading remains. It records
each action in `normalization_warnings`. A confirmed source typo can be corrected
without rerunning successful requests:

```bash
batch-generate apply-readings \
  --manifest .batch/manifest_readings.json \
  --output .batch/output_readings.jsonl \
  --report .batch/reading-normalization-report.json \
  --correction '妄動犬=盲導犬[もうどうけん]'
```

Corrections must name an existing source entry and provide a complete valid
annotated replacement. They are recorded in the normalization report.

This is a reusable Import stage, not a migration-only tool. Future Import
implementations MUST invoke the same preparation, validation, alternate-reading,
post-resolution deduplication, and atomic-publication behavior before declaring a
new GCL complete. The standalone commands remain available for legacy or manually
authored unresolved GCLs.

Future Update implementations MUST invoke this stage first whenever an editor has
appended unannotated vocabulary. Update must complete `prepare-readings`,
submission, collection, and `apply-readings` before it classifies additions,
removals, or unchanged cards. If every entry is already annotated, Update may
proceed directly to classification.

If the report contains review findings, the existing `prepare-retry`,
`merge-retry`, and `apply-readings` workflow can retry only those reading
requests while retaining successful responses.

Only the `submit --confirm-cost` step incurs API charges.

## 5. Proof-of-concept batch

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

## 6. Full generation

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

## 7. Publication and review rules

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

## 8. Retry only rejected cards

Do not repay for cards that already passed local validation. Prepare a retry from
the original manifest and its generation report:

```bash
batch-generate prepare-retry \
  --manifest .batch/manifest_000176_000200.json \
  --report pilot_crowdanki_deck/pilot_crowdanki_deck.generation-report.json \
  --work-dir .batch
```

Inspect `.batch/input_retry_000176_000200.jsonl`. It contains only findings from
the report. Each request includes the rejected card and its exact local
validation errors, and asks the model to preserve compliant fields while
repairing every rejection. `prepare-retry` refuses to create a generation retry
when the report does not identify the original output file, because repeating
the original prompt without repair context would be a blind retry.

Submit, check, and collect this smaller batch:

```bash
batch-generate submit \
  --manifest .batch/manifest_retry_000176_000200.json \
  --confirm-cost

batch-generate status \
  --state .batch/state_retry_000176_000200.json

batch-generate collect \
  --state .batch/state_retry_000176_000200.json
```

Merge the new records over their rejected counterparts while retaining every
previously accepted record:

```bash
batch-generate merge-retry \
  --base-output .batch/output_000176_000200.jsonl \
  --retry-manifest .batch/manifest_retry_000176_000200.json \
  --retry-output .batch/output_retry_000176_000200.jsonl \
  --merged-output .batch/output_merged_000176_000200.jsonl
```

Then apply the merged output with the original manifest:

```bash
batch-generate apply \
  --manifest .batch/manifest_000176_000200.json \
  --output .batch/output_merged_000176_000200.jsonl \
  --template templates/N1_vocabulary_-_CrowdAnki/deck.json \
  --deck-output pilot_crowdanki_deck/pilot_crowdanki_deck.json \
  --allow-partial
```

Retry preparation is local and free. Only its `submit --confirm-cost` step starts
new paid model work.

## 9. Staged synchronized Update

`apply-update` expands an existing generated deck through an explicit GCL prefix.
It is intended for verified staged construction; a deck built through only part
of the GCL is not the final complete deck.

Prepare entries 101–200 after verifying that the existing deck contains entries
1–100:

```bash
batch-generate prepare \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --work-dir .batch \
  --start 101 \
  --end 200
```

Submit, check, and collect the fresh manifest:

```bash
batch-generate submit \
  --manifest .batch/manifest_000101_000200.json \
  --confirm-cost

batch-generate status \
  --state .batch/state_000101_000200.json

batch-generate collect \
  --state .batch/state_000101_000200.json
```

Then preserve entries 1–100 and add the validated entries 101–200:

```bash
batch-generate apply-update \
  --manifest .batch/manifest_000101_000200.json \
  --output .batch/output_000101_000200.jsonl \
  --deck n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json \
  --through 200
```

Update matches existing notes using both annotation-free vocabulary and the
complete authoritative reading. It preserves matched note objects unchanged,
rejects ambiguous or unmatchable notes, prevents generated duplicates, reports
identified removals, validates all new cards, and atomically replaces the deck
only after the complete proposed prefix passes.

## 10. Unattended remainder generation

After validating an existing deck prefix, prepare every remaining GCL entry in
100-card batches without supplying ranges:

```bash
batch-generate prepare-remainder \
  --gcl gcl/n1_vocabulary_generation_control_file.txt \
  --deck n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json \
  --work-dir .batch \
  --batch-size 100
```

This is offline and free. It writes `.batch/remainder-plan.json`. Run or resume
the plan with:

```bash
batch-generate run-plan \
  --plan .batch/remainder-plan.json \
  --deck n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json \
  --max-repair-rounds 2 \
  --confirm-cost
```

The runner submits original batches concurrently, polls and collects them,
performs at most two error-aware repair rounds per rejected card, and persists
progress throughout. Valid cards are retained even when peers fail. Cards still
invalid after two repairs are written to `.batch/remainder-review.json`; they do
not block later valid cards. The final plan status is `completed` or
`completed_with_review`.

Keep the terminal open and the computer awake for fully unattended collection.
If the process is interrupted, run the identical command again. Remote Batch API
work continues while the computer is asleep or off, and saved local state avoids
resubmitting completed work.
