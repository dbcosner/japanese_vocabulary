# APKG Operations Specification

## 1. Scope

The public workflow has three phases:

1. **Import** extracts a proposed Generation Control File (GCL) from an Anki
   `.apkg`.
2. **Populate** creates and caches validated card content for every resolved GCL
   entry.
3. **Generate** creates a complete native Anki `.apkg` from a populated workspace.

Native APKG is the only supported deck interchange and publication format.

## 2. Import

Import accepts one `.apkg` containing a readable Anki collection database and
note models whose vocabulary and reading fields can be identified.

Import MUST:

- leave the source package unchanged;
- preserve source note order where practical;
- reduce every successfully imported source note to only a written term and its
  complete hiragana reading;
- remove presentation HTML, parenthetical and editorial annotations, and other
  non-term metadata that can be discarded deterministically;
- normalize GCL syntax, including U+007E `~`, and remove legacy na-adjective
  markers;
- split multiple expressions or readings into separate entries when the source
  provides a clear, mechanically aligned mapping;
- emit only complete `<term>[<reading>]` entries and never a bare expression;
- retain the first exact duplicate and report later occurrences;
- write a proposed UTF-8 GCL atomically; and
- write a structured import-review report for every successfully inspected note
  that required review, was deduplicated, or used an explicit decision.

Only notes that cannot be reduced confidently to a term and reading are excluded
and flagged for review. These include missing or unusable readings, corrupt
fields, and multiple expressions whose readings cannot be aligned. Routine
presentation text, parentheticals, editorial labels, tilde variants, and legacy
part-of-speech markers are cleanup inputs, not review conditions. A separate
decisions file MAY resolve genuine source-specific outliers.
Unreadable archives, databases, models, or required fields abort Import before
proposal publication.

An imported proposed GCL contains no unresolved entries and becomes authoritative
after editorial adoption and GCL validation. Reading resolution remains available
for bare expressions introduced through manual GCL authoring.

## 3. Populate

Populate accepts one resolved GCL and one logical APKG output path. It creates a
deck-specific workspace under `.batch/<deck-name>/`.

The workspace MUST record:

- the absolute GCL and APKG output paths;
- a stable project ID used for Anki deck and model identifiers;
- the current GCL hash;
- accepted card records keyed by stable GCL identity; and
- any pending and completed Batch job artifacts that currently exist.

Populate MUST reuse valid cached cards. Reordering an unchanged GCL entry MUST NOT
cause regeneration. Missing, invalid, or changed entries MAY create new offline
Batch requests.

## 4. Generate

Generate accepts:

- one complete populated workspace;
- one APKG-neutral card template; and
- one `.apkg` output path;
- optionally, an explicit Anki deck name.

The template MUST NOT determine the deck name. Generate uses the explicit
override when supplied; otherwise it derives a display name from the logical deck
key established by Populate.

Generate validates the project hash, cache identity set, and every cached card
before writing. It MUST refuse incomplete, stale, or invalid workspaces, create
one note for each current GCL entry, use stable deck/model/note identifiers, and
atomically replace the requested APKG.

The generated package MUST:

- contain the expected note and card counts;
- use the fields and templates defined by `card-format-spec.md`;
- contain no GCL annotations in learner-facing fields; and
- remain reproducible from the GCL, accepted cache, template, and project ID.

## 5. Association and preservation

`project.json` is the durable association between a GCL, its accepted cache, and
its APKG output.

## 6. Atomicity

Import writes the proposed GCL and review JSON through separate atomic
replacements. Generate writes a temporary APKG and replaces the final output only
after package construction succeeds. Cache and metadata files also use atomic
replacement, but a multi-file operation is not a transactional filesystem commit.
