---
name: autoscholar
description: Use when the user wants to operate AutoScholar as a unified skill-first toolkit for citation workflows, workspace setup, idea evaluation, report rendering, or choosing which AutoScholar capability to combine next.
---

# AutoScholar

Use this skill as the entry point for the repository.

## What It Covers

- workspace initialization and validation
- citation workflow routing
- layered handout generation
- idea-evaluation workflow routing
- report rendering from structured artifacts
- choosing the right AutoScholar sub-skill

## Routing

- For claim-first literature support and bibliography work, use `citation-workflow`.
- For domain handouts or three-layer research briefings, use `handout`.
- For evaluating a research direction or idea from evidence, use `idea-evaluation`.
- For evidence-grounded long-form feasibility or deep-dive reports, use `report-authoring`.
- For low-level Semantic Scholar lookups or debugging, use `semantic-scholar-api`.

## Operating Model

- Prefer the `autoscholar` CLI over ad hoc scripts.
- Prefer explicit workspaces created with `autoscholar workspace init`.
- Treat JSONL/JSON/YAML artifacts as the source of truth.
- Treat Markdown reports as rendered outputs, not inputs.

## Quick Start

```powershell
autoscholar workspace init D:\workspaces\demo --template citation-paper --reports-lang zh
autoscholar workspace doctor --workspace D:\workspaces\demo
autoscholar semantic paper CorpusID:123
autoscholar util pdf-to-text D:\papers\sample.pdf
```

## References

- For workspace layout and manifest conventions, read `references/workspaces.md`.
