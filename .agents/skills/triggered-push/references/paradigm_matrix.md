# Paradigm: Method × Scenario Matrix

Build a 2D grid of (method family) × (deployment scenario), fill it
with paper density labels, and let AI annotate the conspicuous
empty cells.

## Output

`<workspace>/artifacts/matrix.json` (single file, not JSONL).

```json
{
  "schema_version": "1",
  "domain": "string",
  "generated_at": "ISO-8601",
  "dimensions": {
    "methods": [
      {"id": "M1", "label": "string", "ai_rationale": "<= 150 chars"}
    ],
    "scenarios": [
      {"id": "S1", "label": "string", "ai_rationale": "<= 150 chars",
       "is_non_standard": true}
    ]
  },
  "cells": [
    {
      "cell_id": "M1xS1",
      "method_id": "M1",
      "scenario_id": "S1",
      "query_used": "string",
      "paper_count": 12,
      "max_citations": 340,
      "density": "dense | sparse | empty | unknown",
      "top_papers": [
        {"paper_id": "...", "title": "...", "year": 2024, "citation_count": 120}
      ],
      "ai_diversity_axis": "saturation | adjacency | gap | mismatch",
      "ai_void_note": "<= 200 chars; only present when density in {sparse, empty}"
    }
  ],
  "ai_synthesis_summary": "3-5 sentences naming the 3-5 cells that look most worth a human reaction"
}
```

## Hard rules

- Methods dimension: 5 to 8 items, by **mechanism** not by paper
  family. ("Diffusion-based generation" passes. "Stable Diffusion
  variants" fails.)
- Scenarios dimension: 5 to 8 items. **At least 3 must be
  non-standard.** Non-standard means: not a default benchmark in the
  domain, but a deployment condition real users care about.
  Examples: rare-data, online-adaptive, constrained-compute,
  multimodal-fusion-required, long-tail, regulated-environment.
- AI picks both dimensions itself. Do not solicit user input on
  dimensions — the user has no domain panorama.
- After the grid is filled, AI must NOT brand any cell as
  "opportunity" or "promising". AI only labels density and
  writes a void_note for sparse/empty cells. The user decides what
  resonates.

## Retrieval pipeline

### Step 1 — AI proposes dimensions

Before any retrieval, AI generates the methods × scenarios layout
based on:

- The user's seed papers.
- The user's `derived_traits.engaging_keywords`.
- A few seed search results to confirm the domain vocabulary.

Optional warm-up call (1 query, cheap):

```python
# TODO(user): wire to existing client
from autoscholar.integrations import SemanticScholarClient

with SemanticScholarClient() as client:
    warmup = client.search_papers(
        query=f"{domain} survey methods",
        limit=10,
        fields="title,abstract,year",
    )
```

Send the warmup abstracts + seed papers to AI with the dimension-
picking prompt:

```
You are designing a Method × Scenario matrix for a researcher.

INPUT
- Domain: <DOMAIN>
- The user's seed papers and notes.
- 10 survey-style abstracts from the domain (warmup).

TASK
Output 5-8 method-family labels and 5-8 scenario labels, with a
one-line rationale for each.

HARD CONSTRAINTS
- Method labels classify by mechanism, not by paper family.
- At least 3 scenarios must be non-standard (not a default benchmark).
- Avoid scenarios with information abundance — they fill the table
  trivially. Bias toward scenarios where benchmark coverage is
  uneven.

OUTPUT
JSON: {"methods": [...], "scenarios": [...]}, matching the dimensions
sub-schema in references/paradigm_matrix.md.
```

### Step 2 — Cell-filling crawl

For each (method, scenario) pair, build a query and run a relevance
search. Cap total queries at 32 by default (`max_queries_per_run`
configurable) — 8x8 = 64 is too slow for first runs.

```python
# TODO(user): wire to existing helpers
from autoscholar.semantic_crawl import SemanticCrawlConfig, SemanticQuery, crawl_semantic_queries

queries = []
for m in methods:
    for s in scenarios:
        cell_id = f"{m['id']}x{s['id']}"
        query_text = f"{m['label']} {s['label']} {domain}"
        queries.append(SemanticQuery(cell_id, query_text))

config = SemanticCrawlConfig(
    output=workspace / "artifacts" / "semantic_results.jsonl",
    failures=workspace / "artifacts" / "semantic_failures.jsonl",
    endpoint="relevance",
    limit=10,
    fields="paperId,title,year,abstract,citationCount",
    until_complete=True,
    max_queries=32,  # checkpoint half the matrix per run by default
    pause_seconds=1.0,
)
crawl_semantic_queries(queries, config)
```

The `max_queries=32` cap means a fresh first run fills 32 cells; a
re-run resumes the remaining 32. Both runs share the same checkpoint
files because the query_id (cell_id) is stable.

### Step 3 — Density labeling

Pure-statistics, no LLM:

```python
def label_density(paper_count: int, max_citations: int) -> str:
    if paper_count == 0:
        return "empty"
    if paper_count >= 8 and max_citations >= 50:
        return "dense"
    if paper_count <= 3 or max_citations < 10:
        return "sparse"
    return "dense"  # mid range defaults to dense; only sparse/empty earn a void_note
```

Cells whose query did not complete (still in failures) get
`density="unknown"` and AI does not annotate them.

### Step 4 — AI void-note pass

Only sparse and empty cells get a void_note. Send AI the cell
metadata and the top papers (if any) for those cells, plus the full
dimension labels and rationales, and ask:

```
For each {sparse, empty} cell, write a void_note (<= 200 chars) that
states a *conjecture* about why this cell is empty. Choose one of:

- saturation: the question is solved or trivial in this combination
- adjacency: neighbors are dense, so this gap may be an oversight
- gap: a hard but unaddressed problem lives here
- mismatch: the method and scenario are structurally incompatible

Pick ONE label per cell as ai_diversity_axis. Do NOT recommend the
cell. Do NOT use the word "opportunity". Just describe the void.
```

### Step 5 — Synthesis summary

Finally, AI writes a 3-5 sentence summary naming the 3-5 cells
that struck AI as most ambiguous or curious. This is AI's
own reaction (distinct from the user's), and serves as a sanity check
on the filling — if AI has nothing to say, the matrix is
probably under-filled.

## Failure mode the user should know about

If 100% of cells come back `dense`, the dimensions were chosen too
permissively. The report should say "matrix is saturated; rerun with
narrower scenario definitions."

If 100% of cells come back `empty`, the dimensions don't match the
domain vocabulary at all. The report should say "matrix is
under-matched; rerun with broader scenario definitions."
