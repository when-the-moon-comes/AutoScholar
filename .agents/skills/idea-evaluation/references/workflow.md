# Idea Evaluation Workflow Reference

## Inputs

- `inputs/idea_source.md`
- citation workflow artifacts, especially `artifacts/selected_citations.jsonl`
- `configs/idea_evaluation.yaml`

## Outputs

- `artifacts/idea_assessment.json`
- `artifacts/evidence_map.json`
- `reports/feasibility.md`
- `reports/deep_dive.md`
- `artifacts/report_validation.json`

## Assessment Shape

The assessment record contains:

- `idea_id`
- `title`
- `summary`
- `scores`
- `risks`
- `recommendation`
- `evidence`
- `next_actions`

Use the rendered reports as drafts for further model-guided refinement.
Validate final-facing reports with `autoscholar report validate`.
