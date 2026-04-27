# Report Authoring Reference

## Required Inputs

- `inputs/idea_source.md`
- `artifacts/selected_citations.jsonl`
- `artifacts/idea_assessment.json`
- `artifacts/evidence_map.json`

## Output Surface

- `reports/feasibility.md`
- `reports/deep_dive.md`
- `artifacts/report_validation.json`

## Feasibility Expectations

- explain the current recommendation
- explain why the direction is still worth pursuing
- state the main gaps and risks
- recommend how to narrow the framing
- cite claim-level evidence and top papers

## Deep-Dive Expectations

- give a one-page conclusion
- map each major claim to its evidence strength
- recommend a framing boundary
- recommend method and experiment priorities
- distinguish what the paper can claim from what it should avoid claiming
- include a reference digest of the top evidence papers

## Validation Surface

- The report should mention enough claim IDs to remain traceable.
- The report should mention enough top evidence paper titles to remain auditable.
- Missing required section headings is a hard failure.
