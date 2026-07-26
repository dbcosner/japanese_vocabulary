# Open Questions and Decisions

## Accepted decisions

### D1: The GCL is authoritative

After import and editorial adoption, vocabulary membership, ordering, spelling,
reading, and affix status belong in the GCL. Part-of-speech behavior is inferred
during content generation. Generated APKGs are derived artifacts.

### D2: Stable identity uses the canonical annotated entry

The complete canonical GCL entry is the stable identity key. Physical line number
is not part of identity, so reordering alone does not regenerate content.

### D3: Exact duplicates retain the first occurrence

Deduplication preserves the first exact annotated entry, removes later
occurrences, preserves relative order, and reports every removal.

### D4: Reading resolution may expand entries

The first qualifying common reading remains in the expression’s original
position. Additional qualifying readings are appended in offered order. Archaic,
obsolete, markedly uncommon, compound-only, and contrived readings are excluded.

### D5: Import ambiguity is reviewed, not guessed

Unsafe APKG notes are recorded in a structured review file. Canonical import does
not silently split contrasted terms, equivalent spellings, unsupported
parentheticals, editorial labels, or uncertain multiple readings. Explicit
source-specific decisions may authorize deterministic cleanup.

### D6: Canonical syntax

- The affix placeholder is ASCII tilde U+007E (`~`).
- Recognized tilde variants normalize to `~`.
- Legacy `(な)`, `（な）`, and source trailing literal `な` markers are removed.
- Adjectival-noun behavior is inferred during content generation.
- Optional particles and editorial prose are not GCL annotations.

### D7: Native APKG is the only deck format

Import accepts native APKG packages and Generate emits native APKG packages.
Deck/model/note identifiers are deterministic. The population workspace records
the durable association among the GCL, accepted cache, and APKG output.

### D8: Paid actions require confirmation

Import, preparation, validation, cache reuse, and APKG generation are local.
Submitting a Batch job requires explicit `--confirm-cost`.

## Remaining questions

- Should import field aliases be configurable outside code?
- What Unicode normalization policy should apply beyond defined syntax markers?
- Should optional audio, pitch accent, or frequency data live in generated fields
  or separate metadata?
- What progress and memory guarantees should apply to very large APKG files?
- How should import-review decisions be promoted into reusable user profiles
  without making source-specific guesses canonical?
