# Product Specification

## 1. Purpose

The project creates native Anki APKG decks for advanced Japanese vocabulary
study. A manually curated Generation Control File (GCL) is the authoritative
inventory; generated APKG files are derived artifacts.

## 2. Goals

The system MUST:

- import vocabulary candidates from native `.apkg` packages;
- surface unsafe imports in a structured review file;
- resolve and validate authoritative readings;
- cache validated card content by stable GCL identity;
- generate deterministic native `.apkg` decks; and
- preserve unchanged cards and identifiers across ordinary regeneration.

## 3. Operations

### Import

Input: one source `.apkg`, a requested GCL name, and optional explicit decisions.

Output: one proposed GCL and one import-review JSON file. Import does not generate
learner-facing definitions or examples.

### Populate

Input: one resolved GCL and its logical APKG output path.

Output: a durable `.batch/<deck-name>` workspace containing accepted cards and
any offline Batch requests needed for missing entries.

### Generate

Input: one complete populated workspace and an APKG-neutral template.

Output: one complete `.apkg`, atomically replacing an existing output when
requested.

## 4. Source of truth

Before GCL creation, the source APKG is authoritative only for constructing the
proposal. After editorial adoption, the GCL is authoritative for membership,
ordering, written forms, readings, affix markers, and na-adjective markers.

The accepted cache is authoritative only for generated card content associated
with the current GCL identities. The generated APKG is never an editorial source.

## 5. Safety and review

The application MUST NOT silently omit, split, repair, or reinterpret ambiguous
source notes. Canonical import behavior records them in the import-review file.
Source-specific decisions MUST be explicit and reproducible.

Paid Batch submission requires explicit cost confirmation. Import, preparation,
validation, cache reuse, and APKG generation are local operations.

## 6. Quality

Generated cards MUST satisfy `card-format-spec.md` and
`content-generation-spec.md`. GCLs MUST satisfy
`generation-control-file-spec.md`. Operation boundaries and artifacts MUST
satisfy `deck-generation-spec.md` and `validation-spec.md`.
