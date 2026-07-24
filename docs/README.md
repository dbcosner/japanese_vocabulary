# Japanese Vocabulary Deck Specifications

This directory defines the required behavior of the Japanese vocabulary deck
generation project. The project produces CrowdAnki-compatible decks for advanced
Japanese vocabulary study.

## Authority

These specifications are authoritative for generated behavior. In case of a
conflict:

1. A more specific specification takes precedence over a general one.
2. Accepted decisions recorded in `open-questions.md` take precedence over older
   wording elsewhere and MUST be incorporated into the affected specification.
3. Until an open question is resolved, an implementation MUST NOT silently choose
   behavior that could alter vocabulary interpretation or previously generated
   cards.

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are used
as normative requirement terms.

## Specification index

| Document | Scope |
| --- | --- |
| [Product specification](product-spec.md) | Purpose, scope, authority, and workflows |
| [Generation Control File specification](generation-control-file-spec.md) | GCL encoding, syntax, parsing, and annotations |
| [Content generation specification](content-generation-spec.md) | Readings, definitions, examples, and linguistic quality |
| [Card format specification](card-format-spec.md) | Note fields, front/back rendering, and target concealment |
| [CrowdAnki operations specification](deck-generation-spec.md) | Derive, Generate, Update, scalability, and preservation |
| [Validation specification](validation-spec.md) | Acceptance checks and failure reporting |
| [Open questions](open-questions.md) | Unresolved product and implementation decisions |
| [Roadmap](roadmap.md) | Non-binding future capabilities |

## Terminology

- **Source deck**: an original CrowdAnki JSON export used to seed a GCL during
  initial import.
- **Deck template**: the CrowdAnki structure that supplies the generated deck's
  note model, card template, CSS, and deck configuration.
- **Generation Control File (GCL)**: the manually curated, authoritative list of
  vocabulary entries for one deck.
- **GCL entry**: one vocabulary expression plus optional generation annotations.
- **Target vocabulary**: the written Japanese expression obtained after removing
  GCL annotations.
- **Target occurrence**: use of the target vocabulary in a definition or example,
  including an inflected form whose target portion is identifiable.
- **Generated card**: a CrowdAnki note and its rendered card produced from one GCL
  entry.
- **Derive operation**: creation of a GCL from a source CrowdAnki JSON file.
- **Generate operation**: creation of a new generated CrowdAnki JSON file from a
  GCL and deck template.
- **Update operation**: revision of an associated generated CrowdAnki JSON file to
  reflect its authoritative GCL.
- **Associated generated deck**: a generated CrowdAnki JSON file that can be
  reliably identified as belonging to a particular GCL.
- **Generated deck package**: a directory containing one primary CrowdAnki JSON
  file and any future package assets. The directory and JSON file have the same
  base name.
- **Previously generated entry**: an entry that the generator can reliably match
  to an existing generated card using the project’s eventual identity mechanism.
- **Editorial annotation**: GCL metadata such as `[reading]` or `(な)` that guides
  generation but is never card content.

## Current repository artifacts

- `gcl/n1_vocabulary_generation_control_file.txt` is a deduplicated version 1 GCL
  that is being expanded with explicitly resolved readings.
- `templates/N1_vocabulary_-_CrowdAnki/deck.json` is the current generated-deck
  template and defines the fields `Reading`, `Definition`, `Examples`, and
  `Vocabulary`.
- `n1_vocabulary_crowdanki_deck/n1_vocabulary_crowdanki_deck.json` is the package
  path derived from that GCL name. The current proof-of-concept package contains
  100 notes.

Repository artifacts do not override these specifications merely because they
exist. Differences MUST be reported and deliberately reconciled.

## Capability model

The project has three first-class capabilities:

```text
Source CrowdAnki JSON ── Derive ──▶ GCL
                                      │
                                      ├── Generate ──▶ New generated JSON
                                      │
Associated generated JSON ◀───────────└── Update ───▶ Updated generated JSON
```

The three operations have separate contracts and MUST be usable and testable
independently. Their normative behavior is defined in
[deck-generation-spec.md](deck-generation-spec.md).
