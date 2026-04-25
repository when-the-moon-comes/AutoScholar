# File Contracts

Read this file before generating outputs for `idea-creation`.

## Workspace

Write all working files under `paper/`:

- `paper/seed_paper.md`
- `paper/parsed_paper.json`
- `paper/core_insights.json`
- `paper/assumptions.json`
- `paper/paradigm_gap_check.json`
- `paper/innovation_candidates.json`
- `paper/novelty_verification.json`
- `paper/idea_cards.md`

## `paper/parsed_paper.json`

Goal: capture the seed paper's current framing tightly enough that both tracks can reason from it.

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
  "claimed_contribution": "string",
  "key_ablation_findings": "string"
}
```

Rules:

- Make `task` specific to the real paper, not a generic area label.
- Write `problem_formulation` as the actual structural setup.
- Fill `key_ablation_findings` carefully. Track B depends on it.

## `paper/core_insights.json`

Goal: extract what the paper actually discovered, not just what it claimed.

Required shape:

```json
{
  "insights": [
    {
      "id": "I1",
      "counter_intuitive_finding": "string",
      "abstract_principle": "string",
      "transfer_prerequisites": [
        "string"
      ],
      "candidate_transfer_domains": [
        "string"
      ]
    }
  ],
  "counter_intuitive_design_choices": [
    {
      "id": "D1",
      "choice": "string",
      "why_it_works": "string",
      "transferable_claim": "string"
    }
  ]
}
```

Quality target:

- Usually produce 2 to 4 insights.
- Usually produce 1 to 3 design choices.
- If only 1 weak insight appears, re-read ablations and discussion before proceeding.

## `paper/assumptions.json`

Goal: surface explicit and implicit assumptions behind the seed paper's deployment context.

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

## `paper/paradigm_gap_check.json`

Goal: cross-check Track A against a standard paradigm axis list and catch blind spots.

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

- If an uncovered axis reveals a meaningful missing assumption, append it to `paper/assumptions.json` before generating candidates.

## `paper/innovation_candidates.json`

Goal: merge Track A and Track B candidates into one file.

Required shape:

```json
{
  "track_a_candidates": [
    {
      "id": "CA1",
      "track": "A",
      "source_assumption_ids": ["A1"],
      "assumption_broken": "string",
      "innovation_direction": "string",
      "real_world_motivation": "string",
      "new_problem_formulation": "string",
      "core_technical_challenge": "string",
      "candidate_title": "string",
      "novelty_search_queries": [
        "string"
      ]
    }
  ],
  "track_b_candidates": [
    {
      "id": "CB1",
      "track": "B",
      "source_insight_id": "I1",
      "principle_being_transferred": "string",
      "target_domain": "string",
      "transfer_justification": "string",
      "innovation_direction": "string",
      "real_world_motivation": "string",
      "new_problem_formulation": "string",
      "core_technical_challenge": "string",
      "candidate_title": "string",
      "convergence_with": "CA1",
      "novelty_search_queries": [
        "string"
      ],
      "principle_level_search_queries": [
        "string"
      ]
    }
  ]
}
```

Rules:

- Use `track_a_candidates` for Context Substitution outputs.
- Use `track_b_candidates` for Insight Transfer outputs.
- Track B should include `principle_level_search_queries`. If they are omitted, the verification script falls back to `novelty_search_queries`, but the quality bar is not met.
- Use `convergence_with` only when a Track A and Track B candidate independently target the same domain.

Prune candidates when:

- the idea is only an engineering optimization
- the transfer prerequisites do not genuinely hold
- the candidate is structurally incoherent

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
      "candidate_id": "CB1",
      "track": "B",
      "candidate_title": "string",
      "convergence_with": "CA3",
      "autoscholar_queries": [
        "string"
      ],
      "seed_paper_ids": [
        "paperId_xxx"
      ],
      "total_papers_found": 12,
      "recent_papers_2022_plus": 4,
      "sparsity_rating": "MEDIUM",
      "top_existing_papers": [
        {
          "paperId": "paperId_xxx",
          "title": "string",
          "year": 2024,
          "citationCount": 8,
          "venue": "string",
          "url": "https://www.semanticscholar.org/paper/..."
        }
      ],
      "principle_level_search": {
        "query_source": "explicit",
        "queries_run": [
          {
            "query": "string",
            "status": "ok",
            "paper_count": 2
          }
        ],
        "total_papers_found": 2,
        "recent_papers_2022_plus": 1,
        "sparsity_rating": "HIGH",
        "top_existing_papers": [
          {
            "paperId": "paperId_yyy",
            "title": "string",
            "year": 2023,
            "citationCount": 4,
            "venue": "string",
            "url": "https://www.semanticscholar.org/paper/..."
          }
        ],
        "seed_paper_ids": [
          "paperId_yyy"
        ]
      },
      "verdict": "PROCEED - task area is active, but this principle transfer remains sparse",
      "note": "string"
    }
  ]
}
```

Interpretation:

- Track A verdicts come from task-level sparsity only.
- Track B verdicts use both task-level and principle-level evidence.
- A crowded task area does not automatically kill a Track B candidate if the principle transfer remains sparse.

## `paper/idea_cards.md`

Goal: convert the shortlists into researcher-readable idea cards.

Only include:

- `HIGH` candidates
- `MEDIUM` candidates that remain credible after manual inspection

Required content per card:

- track label
- innovation direction
- assumption broken or principle being transferred
- why the real world needs it
- new problem formulation
- core technical challenge
- literature density
- verdict
- candidate paper title
- surfaced papers section with Semantic Scholar links copied from `novelty_verification.json`

Required machine-readable block per card:

```json
{
  "candidate_id": "CB1",
  "track": "B",
  "status": "PROCEED",
  "autoscholar_queries": [
    "query1",
    "query2"
  ],
  "seed_paper_ids": [
    "paperId_xxx"
  ]
}
```

Required end sections:

- `Convergence Signals` when any Track A and Track B pair share a target domain
- `Summary Table` with columns `ID`, `Track`, `Direction`, `Sparsity`, and `Verdict`

Suggested surfaced-papers rendering per card:

```markdown
**Surfaced Papers**
- Paper Title (2024, Venue) - https://www.semanticscholar.org/paper/...
- Another Paper (2023, Venue) - https://www.semanticscholar.org/paper/...
```
