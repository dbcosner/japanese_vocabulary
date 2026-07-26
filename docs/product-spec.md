# Product Specification

## 1. Purpose

The project creates native Anki APKG decks for advanced Japanese vocabulary
study. A manually curated Generation Control File (GCL) is the authoritative
inventory; generated APKG files are derived artifacts.

## 2. Goals

The system MUST:

- import vocabulary candidates from native `.apkg` packages;
- reduce imported notes to complete term-and-reading GCL entries, discarding
  source content that is not part of either;
- surface unsafe imports in a structured review file;
- resolve and validate authoritative readings;
- cache validated card content by stable GCL identity;
- generate deterministic native `.apkg` decks; and
- preserve unchanged cards and identifiers across ordinary regeneration.

## 3. Operations

### Import

Input: one source `.apkg`, a requested GCL name, and optional explicit decisions.

Output: one proposed GCL and one import-review JSON file. Import does not generate
learner-facing definitions or examples. Every imported GCL entry contains only a
term, an optional affix marker, and one complete reading. Import excludes rather
than emits any source note that cannot be reduced confidently to that form.

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
ordering, written forms, readings, and affix markers. Part-of-speech behavior is
inferred during content generation.

The accepted cache is authoritative only for generated card content associated
with the current GCL identities. The generated APKG is never an editorial source.

## 5. Safety and review

The application MUST deterministically strip presentation content and source
annotations that are not part of a term or reading. It MAY split clearly aligned
forms or readings without review. It MUST NOT guess when reduction is ambiguous;
such notes are omitted from the proposed GCL and recorded in the import-review
file. Source-specific decisions for genuine outliers MUST be explicit and
reproducible.

Paid Batch submission requires explicit cost confirmation. Import, preparation,
validation, cache reuse, and APKG generation are local operations.

## 6. Quality

Generated cards MUST satisfy `card-format-spec.md` and
`content-generation-spec.md`. GCLs MUST satisfy
`generation-control-file-spec.md`. Operation boundaries and artifacts MUST
satisfy `deck-generation-spec.md` and `validation-spec.md`.
