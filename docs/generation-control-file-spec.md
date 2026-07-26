# Generation Control File Specification

## 1. Purpose

A Generation Control File (GCL) is the authoritative vocabulary inventory for
one logical APKG deck. This document describes version 1 as implemented.

## 2. Filename and encoding

`import-apkg` creates:

```text
<deck-name>_generation_control_file.txt
```

The requested name must be a filename component, not a path. Other commands
accept an explicit GCL path and do not enforce its filename.

GCLs are UTF-8 text. Reading accepts UTF-8 with or without a BOM and recognizes
LF or CRLF line endings. Atomic publication always writes UTF-8 without a BOM and
uses LF endings.

## 3. Header, comments, blanks, and whitespace

Files created by this project begin with:

```text
# GCL Version: 1
```

The current parser treats every blank line and every line whose trimmed form
begins with `#` as non-entry text. It does not currently reject an absent or
different header. Entry parsing trims leading and trailing whitespace in memory.
When deduplication or syntax normalization rewrites the file, retained entries are
published in trimmed form.

Callers SHOULD use the exact version header and SHOULD NOT use arbitrary comments
because stricter version validation may be added later.

## 4. Entries

A complete entry is:

```text
<expression>[<reading>]
```

It contains:

- a nonempty written expression;
- exactly one complete hiragana reading in square brackets; and
- optionally one ASCII U+007E `~` at the beginning or end.

Examples:

```text
遭う[あう]
静か[しずか]
~化[か]
無~[む]
```

Square brackets and unsupported parentheses cannot occur in an expression.

An unresolved proposed GCL may temporarily contain a bare expression.
`prepare-readings` accepts this state. `populate`, `prepare`, and `generate`
require every entry to match the complete annotated grammar.

## 5. Canonical syntax cleanup

Before reading entries, the parser:

- normalizes U+FF5E `～` and U+301C `〜` to ASCII U+007E `~`;
- removes legacy terminal `(な)` and `（な）` markers; and
- removes later exact duplicate entry lines.

If either normalization or deduplication occurs, the cleaned GCL is atomically
rewritten. Deduplication retains the first occurrence and reports each removed
entry and former physical line number.

Different readings of the same expression are different identities. A standalone
expression and an affix form are also different identities.

## 6. Reading resolution

`prepare-readings` submits only entries that do not already match the complete
annotated grammar. Each result must echo the source `gcl_entry` and provide:

- `status`: `resolved` or `needs_review`;
- `issue`: an explanation when review is required; and
- `readings`: a list of complete hiragana readings.

`apply-readings` validates exact request/output reconciliation. The first valid
reading replaces the unresolved expression in its existing position. Additional
valid readings are appended to the end in returned order. Duplicate or malformed
readings are reported as normalization warnings. The completed entries are
deduplicated again before atomic publication.

If any result needs review, is missing, is unexpected, or has no valid reading,
the command writes its report and leaves the GCL unchanged. An explicit
`--correction SOURCE=ANNOTATED_ENTRY` may replace one unresolved source with a
complete annotated entry.

## 7. Part of speech

Part of speech is not encoded in the GCL. Content generation infers common
grammatical behavior, including adjectival-noun usage, from the expression.
During APKG import, a source trailing literal `な`, `(な)`, or `（な）` is
removed. Other parenthetical source text is reviewable unless an explicit
decisions file authorizes its removal.

## 8. Affix placeholder

A leading `~` marks a suffix and a trailing `~` marks a prefix:

```text
~化[か]
無~[む]
```

The placeholder is removed from the `Vocabulary` field. Generated definitions
describe the affix function, and examples embed the affix in complete natural
words. A placeholder in the reading is removed during APKG import.

## 9. Identity

Entry identity is the SHA-256-derived key of the complete canonical annotated
entry. It does not include line number. Deterministic Anki note GUIDs use the
same canonical entry.

Consequently:

- reordering does not change identity;
- changing an expression, reading, or affix marker changes identity.

## 10. Current parser errors

Processing stops when:

- there are no vocabulary entries;
- a command requiring resolved entries encounters a bare or malformed entry;
- brackets, parentheses, reading characters, or annotation order do not match the
  implemented grammar; or
- an operation-specific hash or identity check fails.

Malformed-entry errors include a preview using entry order. Exact duplicates are
cleaned and reported rather than treated as fatal.
