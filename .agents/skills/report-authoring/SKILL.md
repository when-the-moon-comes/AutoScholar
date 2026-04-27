---
name: report-authoring
description: Use when AutoScholar already has idea-evaluation evidence artifacts and the task is to produce or validate final-facing feasibility or deep-dive reports, especially when the user cares about output quality more than internal workflow details.
---

# Report Authoring

Use this skill after the evidence pipeline is already in place.

## Workflow

1. Confirm the workspace already has `artifacts/selected_citations.jsonl`.
2. Run `autoscholar idea assess` to refresh `idea_assessment.json` and `evidence_map.json`.
3. Render the target report.
4. Validate the rendered report before treating it as final.
5. If validation fails or the narrative still looks weak, tighten the claims and evidence first rather than broadening the prose.

## Commands

```powershell
autoscholar idea assess --workspace <dir>
autoscholar report render --workspace <dir> --kind feasibility
autoscholar report render --workspace <dir> --kind deep-dive
autoscholar report validate --workspace <dir> --kind feasibility
autoscholar report validate --workspace <dir> --kind deep-dive
```

## Working Rules

- Treat `artifacts/evidence_map.json` as the report-facing evidence packet.
- Treat rendered Markdown as output, not as upstream truth.
- Prefer narrowing the paper claim over inflating the prose when evidence is mixed.
- Use direct support papers for main claims and adjacent support papers for motivation, framing, and evaluation design.

## References

- Read `references/workflow.md` for the section-level expectations and validation surface.
