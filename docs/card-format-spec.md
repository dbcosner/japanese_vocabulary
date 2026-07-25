# Card Format Specification

## 1. Note model

The current deck template defines one note model with four fields in this order:

| Ordinal | Field | Purpose |
| ---: | --- | --- |
| 0 | `Reading` | Hiragana reading with kanji-corresponding portions bold |
| 1 | `Definition` | Concise Japanese explanation |
| 2 | `Examples` | One to five Japanese example sentences, normally three |
| 3 | `Vocabulary` | Original expression with GCL annotations removed |

A generated note MUST populate all four fields. Field names and order MUST match
the selected deck template.

## 2. Front

The front MUST render, in order:

1. `Reading`
2. `Definition`
3. `Examples`

The current template uses:

```html
<section class="reading">
{{Reading}}
</section>

<section class="definition">
{{Definition}}
</section>

<section class="examples">
{{Examples}}
</section>
```

The `Vocabulary` field MUST NOT be referenced by the front template.

## 3. Back

The answer side MUST retain the front, render an answer separator, and then show
only the `Vocabulary` field as new answer content:

```html
{{FrontSide}}

<hr id="answer">

<section class="vocabulary">
{{Vocabulary}}
</section>
```

`Vocabulary` MUST equal the original GCL expression after removal of:

- `[reading]`;
- `(な)`; and
- a leading or trailing affix placeholder.

It MUST otherwise preserve the intended written expression.

## 4. Field markup

- Bold target readings MUST use consistent HTML supported by Anki.
- The current normative representation is `<b>…</b>`.
- Generated fields MUST NOT include Markdown bold markers.
- Markup MUST be balanced and safe to insert into Anki note fields.
- Any literal HTML-significant characters originating in content MUST be escaped
  unless they are deliberate supported markup.

APKG generation wraps each example in its own `<div>` and joins those elements
with line breaks. This keeps examples individually readable and does not expose
`Vocabulary`.

## 5. Reading field

Ignoring HTML tags, `Reading` MUST:

- contain hiragana only;
- contain no kanji or katakana;
- contain no GCL annotation; and
- represent the resolved pronunciation.

Every reading segment attributable to kanji MUST be enclosed in `<b>` tags.
Original kana and okurigana MUST not be bold merely because they are part of the
word.

## 6. Definition and Examples fields

- Both fields MAY contain standard Japanese orthography.
- Neither field may expose a target occurrence in its original written form.
- Replaced target portions MUST be hiragana and enclosed in `<b>` tags.
- `Examples` MUST visibly contain one to five distinct examples. It SHOULD contain
  exactly three unless the content-generation specification justifies fewer or
  more.

## 7. Styling and compatibility

The current template CSS defines `.card`, `.reading`, `.definition`, `.examples`,
and `.vocabulary`. A generator SHOULD preserve the template’s note model, card
template, and CSS rather than reconstructing them.

Future fields MAY be added for pitch accent, audio, frequency, register,
collocations, or usage notes. Such additions MUST:

- preserve the semantics of the four current fields;
- keep the written vocabulary concealed on the front unless a later specification
  explicitly changes that learning design; and
- continue to honor an authoritative `[reading]`.
