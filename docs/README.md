# Documentation

This directory defines an APKG-only Japanese vocabulary generation system.

| Document | Purpose |
| --- | --- |
| [Product specification](product-spec.md) | Goals, operations, and source-of-truth model |
| [APKG operations specification](deck-generation-spec.md) | Import, Populate, Generate, association, and atomicity |
| [Generation Control File specification](generation-control-file-spec.md) | GCL syntax, readings, annotations, and identity |
| [Card format specification](card-format-spec.md) | Fields, templates, HTML, and concealment |
| [Content generation specification](content-generation-spec.md) | Reading resolution, definitions, and examples |
| [Validation specification](validation-spec.md) | Required checks and regression coverage |
| [Batch workflow](batch-generation.md) | Local and paid command workflow |
| [Open questions and decisions](open-questions.md) | Historical design decisions still relevant to APKG |
| [Roadmap](roadmap.md) | Remaining work |

## Terms

- **Source APKG**: a native Anki package used only to seed a proposed GCL.
- **GCL**: the authoritative vocabulary inventory after editorial adoption.
- **Import review**: structured JSON identifying source notes that were not safe
  to import automatically.
- **Decisions file**: explicit source-specific cleanup instructions.
- **Population workspace**: `.batch/<deck-name>` cache and job state associated
  with one GCL and APKG output.
- **Generated APKG**: the derived native Anki package produced from a complete
  workspace.

## Workflow

```text
Source APKG ── Import ──▶ Proposed GCL + review
                              │
                        Reading resolution
                              │
                              ▼
                     Authoritative GCL
                              │
                          Populate
                              │
                              ▼
                       Cached card data
                              │
                          Generate
                              │
                              ▼
                        Native APKG
```
