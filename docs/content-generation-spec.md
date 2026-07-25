# Content Generation Specification

## 1. Inputs and outputs

For each valid GCL entry, content generation MUST produce:

- a hiragana reading with formatting that identifies portions corresponding to
  kanji;
- one concise Japanese definition;
- one to five natural Japanese example sentences, normally three; and
- the annotation-free original vocabulary expression.

All generated content MUST correspond to one resolved reading and interpretation.

## 2. Reading resolution

### 2.1 Authoritative reading

Every valid GCL entry supplies `[reading]`:

- it MUST be treated as authoritative;
- the definition and examples MUST be generated for that reading and its intended
  interpretation; and
- the generator MUST NOT substitute a more common reading.

If the supplied reading is incompatible with the expression or still permits
materially different interpretations, processing requires clarification.

### 2.2 Import-time reading resolution

Import MUST determine the reading of each proposed expression before publishing
the GCL. Generate and Update MUST NOT perform this inference.

If multiple readings are established in contemporary Japanese, the generator MUST
create a separate entry and card for each reading that:

- occurs often enough to be pedagogically useful;
- supports a clear, non-contrived Japanese definition;
- supports at least one natural contemporary example and normally supports three;
  and
- is a reading of the expression as presented, rather than only a bound reading
  in unrelated compounds.

The most common qualifying reading MUST annotate the proposed entry. Other
qualifying readings MUST be appended to the end of the GCL.

The generator MUST exclude a reading when it is archaic, obsolete, markedly
uncommon, or so contextually marginal that satisfying the example requirements
would produce unnatural or contrived sentences. Dictionary recognition alone is
not sufficient for inclusion.

If it remains genuinely uncertain whether a reading qualifies, or if multiple
interpretations within one reading would produce materially different
learner-facing content, the generator MUST NOT guess. It MUST emit a clarification
request identifying:

- the entry and line number;
- the plausible readings or interpretations, when known; and
- the information needed to resolve the ambiguity.

For a reading-only clarification, Import MUST present the plausible
qualifying readings in a deliberate order. The editor may select one reading or
use the `全` response defined in `generation-control-file-spec.md` to request cards
for every offered reading. Each resulting card MUST be generated for its own
reading and interpretation.

When multiple entries are presented together, each MUST appear on its own numbered
prompt line. Responses MUST be interpreted one line at a time in the same order,
as defined by the GCL specification.

The same rule applies to ambiguous prefixes and suffixes.

### 2.3 Reading presentation

- The displayed reading MUST contain hiragana only, apart from required HTML
  formatting.
- Katakana readings MUST be converted to their natural hiragana equivalents for
  display.
- Reading segments corresponding to kanji in the target expression MUST be bold.
- Reading segments corresponding to original hiragana, including okurigana, MUST
  remain normal weight.
- Kanji and katakana MUST NOT appear in the displayed reading.

Examples:

```text
遭う     → <b>あ</b>う
食べる   → <b>た</b>べる
美味しい → <b>おい</b>しい
```

When the mapping between surface characters and reading segments is not
linguistically defensible, the entry MUST be flagged for review rather than
formatted through a guess.

## 3. Definition

The definition MUST:

- be entirely in Japanese;
- be suitable for a JLPT N1 learner;
- explain the relevant meaning rather than merely list synonyms;
- be concise while remaining sufficient to distinguish the intended sense;
- mention important usage restrictions, register, or construction constraints
  when they materially affect correct use; and
- correspond specifically to the resolved reading and interpretation.

If a target occurrence would otherwise appear in the definition, its written form
MUST be replaced with the appropriate hiragana reading in bold. The original
written target form MUST never be revealed on the front.

## 4. Example sentences

Each entry MUST have one to five examples. The generator SHOULD produce exactly
three examples by default.

One or two examples MAY be used only when the term has a narrowly constrained
usage and further examples would be contrived or essentially duplicate an example
already provided.

Four or five examples MAY be used when additional examples are needed to
demonstrate distinct common meanings, constructions, collocations, registers, or
other productive use patterns. Extra examples MUST NOT be added merely to reach
the maximum.

When the count is not three, generation metadata MUST include a concise rationale
for using fewer or more examples. This rationale is operational metadata and MUST
NOT appear on the card.

Each example MUST:

- be a complete, natural Japanese sentence or naturally complete utterance;
- use standard Japanese orthography except for the concealed target occurrence;
- demonstrate the resolved meaning and grammatical behavior;
- use a realistic context; and
- replace every target occurrence with its correctly inflected hiragana form,
  bolding only the portion that represents the target.

Across the examples, the generator SHOULD vary context and sentence structure
where natural. It SHOULD avoid repetitive frames, dictionary-example clichés, and
sentences designed only to exhibit grammar.

Naturalness takes precedence over mechanical variation.

## 5. Part-of-speech guidance

### 5.1 Verbs

Examples SHOULD use natural conjugational variety. Inflected target occurrences
MUST remain concealed and MUST retain grammatically required endings.

### 5.2 I-adjectives

Examples SHOULD demonstrate natural adjectival or predicate use as appropriate to
the intended sense.

### 5.3 Nouns

Examples SHOULD use varied, idiomatic constructions rather than repeatedly using
the same copular frame.

When a noun commonly participates in either of these productive constructions,
the example set SHOULD demonstrate the applicable construction:

- `Nの…`, where the noun naturally modifies or relates to a following noun; and
- `Nする`, including naturally conjugated forms such as `Nした`, `Nしている`, or
  `Nしない`, where the noun functions as a suru-verb.

If both constructions are common and useful for the target sense, the examples
SHOULD normally include at least one natural instance of each. If only one is
established, the generator MUST NOT invent the other. Naturalness and the intended
sense take precedence over satisfying a fixed pattern.

The target noun itself MUST remain replaced by bold hiragana in these
constructions. Following particles, including `の`, and conjugated forms of
`する` MUST remain visible in normal Japanese orthography.

### 5.4 Na-adjectives

For entries marked `(な)`:

- examples SHOULD include attributive `～な` use and predicate or noun-like use
  when both are natural for the entry;
- the literal GCL annotation MUST NOT be copied into a field; and
- the grammatical `な` MAY and normally will appear when required by a sentence.

Natural Japanese takes precedence over satisfying both usage patterns.

### 5.5 Prefixes and suffixes

For affix entries:

- the definition MUST explain the affix’s function rather than describe it as a
  standalone word;
- examples MUST embed it within authentic words;
- the entire occurrence of the target affix within those words MUST be replaced
  by its hiragana reading in bold; and
- the placeholder `～` MUST NOT appear on the card.

## 6. Target concealment

The front MUST not reveal the target expression in its original written form.
Concealment applies to:

- the reading field;
- the definition;
- every example;
- visible HTML attributes or labels rendered on the front; and
- inflected or embedded occurrences, including occurrences inside words for
  affixes.

Replacement MUST be contextual. A generator MUST NOT blindly replace unrelated
homographs or substrings.

## 7. Language quality

Definitions and examples MUST read as though written or carefully edited by a
native speaker. They SHOULD favor pedagogically useful distinctions and authentic
contexts. They MUST NOT contain mojibake, unsupported placeholders, editorial
instructions, uncertainty markers, or generation commentary.
