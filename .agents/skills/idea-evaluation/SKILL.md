---
name: idea-evaluation
description: Use when the user wants to evaluate a research idea or direction with structured evidence, using AutoScholar workspaces, citation artifacts, heuristic scorecards, feasibility reports, and deep-dive report drafts.
---

# Idea Evaluation

Use this skill for AutoScholar's first analysis workflow: research idea evaluation.

## Workflow

1. Initialize an `idea-evaluation` workspace.
2. Fill `inputs/idea_source.md` with the idea framing.
3. Build claims and queries in structured artifacts.
4. Run the citation workflow to collect evidence.
5. Run `autoscholar idea assess`.
6. Use `report-authoring` when the task is to produce final-facing feasibility or deep-dive reports.
7. Render and validate feasibility and deep-dive reports.

## Commands

```powershell
autoscholar workspace init <dir> --template idea-evaluation --reports-lang zh
autoscholar citation search --workspace <dir>
autoscholar citation prescreen --workspace <dir>
autoscholar citation correct --workspace <dir>
autoscholar citation shortlist --workspace <dir>
autoscholar idea assess --workspace <dir>
autoscholar report render --workspace <dir> --kind feasibility
autoscholar report render --workspace <dir> --kind deep-dive
autoscholar report validate --workspace <dir> --kind feasibility
autoscholar report validate --workspace <dir> --kind deep-dive
```

## Working Rules

- `artifacts/idea_assessment.json` is the machine-readable source of truth.
- The CLI produces heuristic structured assessments and report drafts.
- The model or user can refine the final narrative, but not by treating Markdown reports as the upstream source.

## References

- Read `references/workflow.md` for the expected input and output pattern.
