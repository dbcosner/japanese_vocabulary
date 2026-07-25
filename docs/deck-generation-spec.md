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
- remove presentation HTML and ignore non-GCL metadata;
- normalize GCL syntax, including U+007E `~` and `(な)`;
- retain the first exact duplicate and report later occurrences;
- write a proposed UTF-8 GCL atomically; and
- write a structured import-review report for every note that could not be
  imported safely.

Ambiguous structures MUST be flagged rather than guessed. These include multiple
expressions, unsupported parentheticals, editorial instructions, corrupt fields,
and unusable or multiple offered readings outside established affix logic.
A separate decisions file MAY authorize source-specific deterministic cleanup.

An unresolved proposed GCL is not authoritative until reading resolution succeeds
and the completed file passes GCL validation.

## 3. Populate

Populate accepts one resolved GCL and one logical APKG output path. It creates a
deck-specific workspace under `.batch/<deck-name>/`.

The workspace MUST record:

- the absolute GCL and APKG output paths;
- a stable project ID used for Anki deck and model identifiers;
- the current GCL hash;
- accepted card records keyed by stable GCL identity; and
- pending and completed Batch jobs.

Populate MUST reuse valid cached cards. Reordering an unchanged GCL entry MUST NOT
cause regeneration. Missing, invalid, or changed entries MAY create new offline
Batch requests.

## 4. Generate

Generate accepts:

- one complete populated workspace;
- one APKG-neutral card template; and
- one `.apkg` output path.

Generate MUST refuse incomplete, stale, or invalid workspaces. It MUST create one
note for each current GCL entry, use stable deck/model/note identifiers, and
atomically replace the requested APKG.

The generated package MUST:

- contain the expected note and card counts;
- use the fields and templates defined by `card-format-spec.md`;
- contain no GCL annotations in learner-facing fields; and
- remain reproducible from the GCL, accepted cache, template, and project ID.

## 5. Association and preservation

`project.json` is the durable association between a GCL, its accepted cache, and
its APKG output. Syntax-only migrations MAY preserve legacy identities through an
explicit compatibility mapping. Such migrations MUST validate every cached card,
update stored hashes, and create a recoverable backup before publication.

## 6. Atomicity

Import and Generate MUST write temporary files and replace final artifacts only
after validation. A failure MUST NOT expose a partial GCL, review report, cache,
or APKG as complete.
