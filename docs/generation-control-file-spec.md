# Generation Control File Specification

## 1. Purpose

A Generation Control File (GCL) is the authoritative, manually curated inventory
for one vocabulary deck. GCL annotations guide generation but are not learner-facing
content.

This document defines GCL version 1.

## 2. File naming

A version 1 GCL filename MUST follow:

```text
<deck-name>_generation_control_file.txt
```

`<deck-name>` MUST be non-empty and SHOULD use lowercase ASCII letters, digits,
and underscores for portable paths. The name determines the generated CrowdAnki
package name as defined in `deck-generation-spec.md`.

Example:

```text
n1_vocabulary_generation_control_file.txt
```

## 3. Encoding and line handling

- A GCL MUST be encoded as UTF-8.
- A generator MUST accept UTF-8 with or without a byte-order mark.
- A generator MUST recognize LF and CRLF line endings.
- A generator MUST treat the file as Unicode text and MUST NOT reinterpret UTF-8
  bytes using a legacy encoding.
- A generator MUST preserve Japanese characters exactly except for any Unicode
  normalization policy adopted through `open-questions.md`.
- Leading or trailing whitespace on an entry is not currently defined and MUST be
  reported rather than silently removed.

## 4. Version header

The current repository GCL begins with:

```text
# GCL Version: 1
```

For version 1:

- the first non-empty line MUST be exactly `# GCL Version: 1`;
- the header is metadata and MUST NOT create a vocabulary entry;
- a blank line MAY follow the version header;
- an absent, malformed, or unsupported version header MUST stop processing before
  content generation; and
- no other comment syntax is defined.

Whether arbitrary comments and blank lines within the entry list are allowed is
an open question. Until resolved, an implementation MUST report them rather than
assign them vocabulary semantics.

## 5. Entry structure

After the header, each content-bearing line represents one entry:

```text
<annotated-entry>
```

An annotated entry contains:

- one target vocabulary expression;
- optionally one authoritative reading in square brackets;
- optionally the literal marker `(な)`; and
- optionally one affix placeholder at the beginning or end.

Examples:

```text
遭う
一入[ひとしお]
静か(な)
一入[ひとしお](な)
～化
無～
```

The annotations MUST be removed to derive the target vocabulary displayed on the
back. Annotation text MUST NOT appear in generated fields.

### 5.1 Adding entries

When an editor requests a new GCL entry, the entry MUST be appended after the
existing final entry in the file. It MUST NOT be inserted beside a related
spelling, reading, part of speech, or semantic group.

Changing annotations on an existing entry is an edit to that entry, not an
addition, and does not move it. This rule applies prospectively; it does not
require earlier additions to be reordered.

### 5.2 Exact duplicate entries

Two entries are exact duplicates when their complete annotated-entry lines are
identical as Unicode strings under the adopted normalization policy.

- A valid GCL MUST NOT contain exact duplicate entries.
- The complete annotated-entry line is the comparison key. Different `[reading]`
  annotations make entries distinct and MUST NOT be removed as duplicates.
- A standalone expression and its prefix or suffix form are distinct.
- Deduplication MUST retain the first occurrence, remove every later exact
  occurrence, and preserve the relative order of all retained entries.
- A deduplication report MUST identify the removed entry text and its former line
  number.

Deduplication is editorial cleanup, not card regeneration. If a removed duplicate
was already represented by a redundant generated note, Update MUST remove that
redundant note while preserving the note associated with the retained first
occurrence.

Generate and Update MUST run this deduplication process as a mandatory GCL
preflight step before parsing entries for generation, matching identities, or
classifying changes. The cleaned GCL MUST be validated before the requested
operation proceeds.

## 6. Authoritative reading

Syntax:

```text
<expression>[<reading>]
```

Rules:

- `<reading>` MUST be non-empty.
- A supplied reading MUST be treated as authoritative.
- The reading annotation MUST occur after the expression and before `(な)`, when
  both are present.
- At most one reading annotation is permitted per entry.
- The reading SHOULD be written entirely in hiragana. Any other script MUST be
  flagged for editorial review until an explicit policy is adopted.
- Square brackets that are part of an expression are not supported in version 1.

Entries with the same written expression and different authoritative readings are
distinct editorial entries, for example:

```text
縁[ふち]
縁[えん]
```

The generator MUST generate each according to its supplied reading. How these
entries receive stable distinct identities remains unresolved.

For an unannotated entry with multiple qualifying readings under
`content-generation-spec.md`, the generator MUST annotate the existing entry with
the most common qualifying reading and append each remaining qualifying reading
as a separate entry. Archaic, obsolete, markedly uncommon, compound-only, or
contrived-example readings MUST NOT be appended.

When clarification produces an additional desired reading rather than replacing
the intended reading of an existing entry, the additional reading MUST be
represented as a separate annotated entry and appended according to section 5.1.
It MUST NOT overwrite the existing reading.

### 6.1 All-readings clarification response

When the generator asks an editor to choose among multiple possible readings, the
editor MAY respond with the single character:

```text
全
```

`全` means that the editor wants a separate GCL entry and generated card for every
reading offered in that clarification request.

The generator MUST:

1. apply the first offered reading to the existing entry using `[reading]`;
2. preserve that entry at its current position;
3. create one annotated entry for each remaining offered reading; and
4. append those additional entries, in offered order, to the end of the GCL.

The generator MUST NOT treat `全` as vocabulary content or as a reading.

### 6.2 Ordered multiline clarification responses

When a clarification request contains multiple ambiguous entries, the editor will
respond with exactly one non-empty response line per ambiguous entry. Response
line order MUST correspond to prompt order:

```text
prompt 1 ↔ response line 1
prompt 2 ↔ response line 2
…
```

Each response line MUST contain either one offered reading or `全`. The generator
MUST validate the response-line count before changing the GCL. It MUST stop and
request correction if a line is missing, extra, empty, or cannot be matched
unambiguously.

When more than one line contains `全`, all alternate entries MUST be collected and
appended to the end of the GCL in this order:

1. prompt order; then
2. offered-reading order within each prompt, excluding the first reading applied
   to the existing entry.

## 7. Na-adjective marker

Syntax:

```text
<expression>(な)
<expression>[<reading>](な)
```

Rules:

- `(な)` identifies the entry as an adjectival noun (na-adjective).
- It MUST occur only at the end of the line.
- It MUST NOT be treated as part of the target vocabulary or reading.
- It MUST NOT appear verbatim in any generated field merely because it is an
  annotation.
- Parentheses used for other purposes are not supported in version 1.
- Version 1 uses ASCII parentheses exactly as `(な)`. Full-width `（な）` MUST be
  normalized to `(な)` before processing.

## 8. Affix placeholder

Syntax:

```text
～<expression>
<expression>～
```

Rules:

- A leading `～` marks a suffix.
- A trailing `～` marks a prefix.
- The marker describes an open attachment position; it is not target vocabulary.
- The marker MUST be removed from the `Vocabulary` field.
- Generated definitions MUST describe the affix’s function.
- Examples MUST show the affix in natural, complete words.
- An entry with both a leading and trailing placeholder is invalid in version 1.

Version 1 defines only full-width `～`. During GCL cleanup, ASCII `~` MUST be
normalized to `～` and reported. Newly authored ASCII `~` SHOULD be rejected so
the canonical form remains visible to the editor.

## 9. Legacy inline reading and usage forms

Version 1 does not permit a reading separated from an expression by whitespace or
an optional-particle marker in parentheses.

- A legacy form such as `来る　きたる` MUST be rewritten as `来る[きたる]`.
- A legacy form such as `故（に）` MUST be rewritten as `故[ゆえ]`.
- Natural examples MAY demonstrate grammatical forms such as `故に`; optional
  particles are content-generation concerns, not GCL annotations.

## 10. Parsing result

For each valid line, the parser MUST expose at least:

| Property | Meaning |
| --- | --- |
| `source_line` | Original line text |
| `line_number` | One-based physical line number |
| `vocabulary` | Expression after all annotations are removed |
| `authoritative_reading` | Supplied reading, or absent |
| `is_na_adjective` | Whether `(な)` is present |
| `affix_type` | `prefix`, `suffix`, or absent |

`vocabulary` MUST be non-empty after annotation removal.

## 11. Invalid entries

The parser MUST reject or stop on:

- malformed or unmatched brackets or parentheses;
- empty vocabulary or reading;
- repeated reading or na-adjective annotations;
- annotations in an unsupported order;
- unsupported comment-like lines;
- unsupported affix syntax;
- an exact duplicate annotated-entry line;
- control characters other than permitted line endings and encoding markers; or
- any line that cannot be parsed unambiguously.

Errors MUST include the file, physical line number, original line, and reason.

Duplicate behavior, whitespace rules, normalization, and whether all parse errors
are collected in one run are specified as open questions.
