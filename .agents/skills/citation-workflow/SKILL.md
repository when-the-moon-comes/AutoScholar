---
name: citation-workflow
description: Use when the user wants claim-first scholarly citation support, including structured claims and queries, Semantic Scholar search, prescreening, recommendation correction, shortlist generation, and BibTeX output.
---

# Citation Workflow

Use this skill for AutoScholar's claim-first citation workflow.

## Workflow

1. Create or inspect a workspace.
2. Fill `artifacts/claims.jsonl` and `artifacts/queries.jsonl`.
3. Run search.
4. Run prescreen.
5. Run recommendation correction if retrieval is weak or mixed.
6. Run shortlist generation.
7. Generate BibTeX.
8. Render reports when needed.

## Commands

```powershell
autoscholar citation search --workspace <dir>
autoscholar citation prescreen --workspace <dir>
autoscholar citation correct --workspace <dir>
autoscholar citation shortlist --workspace <dir>
autoscholar citation bib --workspace <dir>
autoscholar report render --workspace <dir> --kind prescreen
autoscholar report render --workspace <dir> --kind shortlist
```

## Working Rules

- Claims and queries must be structured JSONL.
- Query-level exclusion and paper-level exclusion belong in `configs/citation_rules.yaml`.
- Recommendation correction produces additional evidence candidates but does not directly overwrite the shortlist.
- `artifacts/selected_citations.jsonl` is the source for BibTeX generation.

## References

- Read `references/workflow.md` for the detailed operating pattern.
