# File Contracts

Read this file before generating outputs for `idea-creation`.

## Workspace

Write all working files under `paper/`:

- `paper/seed_paper.md`
- `paper/parsed_paper.json`
- `paper/assumptions.json`
- `paper/paradigm_gap_check.json`
- `paper/innovation_candidates.json`
- `paper/novelty_verification.json`
- `paper/idea_cards.md`

## `paper/parsed_paper.json`

Goal: capture the seed paper's current framing in a form the later steps can challenge.

Required shape:

```json
{
  "title": "string",
  "domain": "string",
  "task": "string",
  "input_data_type": "string",
  "output_type": "string",
  "core_method": "string",
  "problem_formulation": "string",
  "claimed_contribution": "string"
}
```

Rules:

- Make `task` specific to the real paper, not just a broad area like "classification".
- Write `problem_formulation` as the actual structural setup, such as "closed-set multi-class classification over a fixed label space".
- If the user only supplies title plus abstract, note uncertainty in the generated content but still fill the schema.

## `paper/assumptions.json`

Goal: surface explicit and implicit assumptions in the seed paper.

Required shape:

```json
{
  "assumptions": [
    {
      "id": "A1",
      "lens": "LABEL SPACE",
      "assumption": "string",
      "how_it_manifests": "string",
      "implicit_or_explicit": "implicit"
    }
  ]
}
```

Required lenses to think across:

- `LABEL SPACE`
- `DATA AVAILABILITY`
- `TEMPORAL`
- `DISTRIBUTION`
- `SAMPLE STRUCTURE`
- `INFERENCE MODE`
- `RESOURCE OR DEPLOYMENT`
- `TASK GRANULARITY`

Quality target:

- Usually produce 8 to 15 assumptions.
- If fewer than 6 assumptions appear, go back and mine deeper.
- Favor assumptions that change the research problem when broken.

## `paper/paradigm_gap_check.json`

Goal: cross-check assumption mining against a standard axis list and catch blind spots.

Check all of these axes:

- `label_space`
- `supervision`
- `temporal`
- `distribution`
- `sample_structure`
- `task_granularity`
- `inference_mode`
- `deployment`
- `data_volume`

Required shape:

```json
{
  "covered_axes": ["label_space", "temporal"],
  "uncovered_axes": [
    {
      "axis": "sample_structure",
      "question": "string",
      "suggested_assumption_to_add": "string"
    }
  ]
}
```

Rule:

- If an uncovered axis reveals a meaningful missing assumption, append that assumption to `paper/assumptions.json` before generating candidates.

## `paper/innovation_candidates.json`

Goal: convert broken assumptions into concrete research directions.

Required shape:

```json
{
  "candidates": [
    {
      "id": "C1",
      "source_assumption_ids": ["A1"],
      "assumption_broken": "string",
      "innovation_direction": "string",
      "real_world_motivation": "string",
      "new_problem_formulation": "string",
      "core_technical_challenge": "string",
      "candidate_title": "string",
      "novelty_search_queries": [
        "string",
        "string"
      ]
    }
  ]
}
```

Prune candidates when:

- the broken assumption does not create a coherent research problem
- the direction is only an engineering optimization
- the assumption is too minor to change the paper's contribution

Target:

- Keep 5 to 10 candidates after pruning.

## `paper/novelty_verification.json`

Goal: estimate whether each candidate is sparse enough to justify follow-up.

Default execution path:

```powershell
python .agents\skills\idea-creation\scripts\verify_novelty.py
```

The script reads `paper/innovation_candidates.json` and uses the repository's `SemanticScholarApi` client.

Produced shape:

```json
{
  "generated_at": "2026-03-14T00:00:00+00:00",
  "verifications": [
    {
      "candidate_id": "C1",
      "candidate_title": "string",
      "total_papers_found": 3,
      "recent_papers_2022_plus": 1,
      "sparsity_rating": "HIGH",
      "top_existing_papers": [
        {
          "title": "string",
          "year": 2023,
          "citationCount": 12,
          "venue": "string"
        }
      ],
      "verdict": "PROCEED - very sparse, high novelty potential",
      "note": "string"
    }
  ]
}
```

Default sparsity rules:

- `HIGH`: fewer than 5 unique papers
- `MEDIUM`: 5 to 20 unique papers
- `LOW`: more than 20 unique papers

Interpretation:

- `HIGH` -> proceed
- `MEDIUM` -> investigate manually
- `LOW` -> deprioritize unless there is a very clear gap in the existing work

## `paper/idea_cards.md`

Goal: convert the shortlists into researcher-readable idea cards.

Only include:

- `HIGH` candidates
- `MEDIUM` candidates that remain credible after manual inspection

Required content per card:

- innovation direction
- assumption broken
- why the real world needs it
- new problem formulation
- core technical challenge
- literature density
- recommended next step
- candidate paper title

End the file with a summary table using these columns:

```markdown
| # | Direction | Assumption Broken | Sparsity | Recommended |
```
