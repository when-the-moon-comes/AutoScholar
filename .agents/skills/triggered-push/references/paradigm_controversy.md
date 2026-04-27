# Paradigm: Controversy Map

Surface 5-8 propositions where researchers in the domain are actively
disagreeing, with representative papers on each side and a recent clash
point.

## Output

`<workspace>/artifacts/controversy_cards.jsonl`. One card per line.

```json
{
  "card_id": "controversy_<NN>",
  "ai_diversity_axis": "mechanism | evaluation | framing | scope | data",
  "proposition": "<= 200 chars; a propositional statement, not a topic",
  "side_a": {
    "claim": "<= 100 chars",
    "representative_papers": [
      {"paper_id": "...", "title": "...", "year": 2024}
    ]
  },
  "side_b": {
    "claim": "<= 100 chars",
    "representative_papers": [...]
  },
  "last_clash": {
    "paper_id": "...",
    "title": "...",
    "year": 2024,
    "challenge_summary": "<= 200 chars; what the paper said that contradicts the other side"
  },
  "ai_synthesis_note": "1-2 sentences; why this is a real fight, not a topical difference"
}
```

## Hard rules

- 5 distinct values of `ai_diversity_axis` minimum across the card
  set. If only 3 axes appear, drop down to 5 cards rather than ship
  a homogeneous 8.
- Both sides must have at least one paper from the last 3 years.
- Both sides must be defensible. Reject "good vs. bad" or "old vs.
  modern" framings — those are not controversies, they are progress.
- If after retrieval AI cannot construct 5 valid cards, the report
  should say so and recommend running `failure-archive` instead.

## Retrieval pipeline

### Step 1 — Candidate sweep

Use `crawl_semantic_queries` (already in your repo) with these queries.
Keep crawl signature stable across reruns so checkpoints work.

```python
# TODO(user): wire this to the existing helper in src/autoscholar/semantic_crawl.py
from autoscholar.semantic_crawl import (
    SemanticCrawlConfig, SemanticQuery, crawl_semantic_queries,
)

queries = [
    SemanticQuery("controversy_debate", f"{domain} debate"),
    SemanticQuery("controversy_critique", f"{domain} critique limitations"),
    SemanticQuery("controversy_contradicts", f"{domain} contradicts findings"),
    SemanticQuery("controversy_rebuttal", f"{domain} rebuttal comment reply"),
    SemanticQuery("controversy_overclaim", f"{domain} overclaim reconsidered"),
]
config = SemanticCrawlConfig(
    output=workspace / "artifacts" / "semantic_results.jsonl",
    failures=workspace / "artifacts" / "semantic_failures.jsonl",
    endpoint="relevance",
    limit=15,
    fields="paperId,title,year,abstract,citationCount,authors",
    until_complete=True,
    pause_seconds=1.0,
)
crawl_semantic_queries(queries, config)
```

### Step 2 — Citation graph for clash detection

For each candidate paper from Step 1 with `citationCount >= 20`, fetch
its citations and keep only those from the last 3 years.

```python
# TODO(user): wire this to your existing client
from autoscholar.integrations import SemanticScholarClient

with SemanticScholarClient() as client:
    citations = client.get_paper_citations(
        paper_id=candidate_id,
        fields="paperId,title,year,abstract,authors",
    )
recent_citations = [c for c in citations if (c.get("year") or 0) >= NOW_YEAR - 3]
```

This gives AI pairs of the form `(seminal_paper, recent_citation)`.

### Step 3 — Heuristic challenge filter

Before sending to AI synthesis, apply a cheap text filter to
`recent_citations`. Keep only those whose title or abstract contains
**at least one** of these signal phrases:

```
challenge, contradict, fails to, revisit, reconsider, comment on,
reply to, rebuttal, overclaim, does not, no evidence, contrary,
inconsistent, refute
```

This reduces the synthesis context drastically. Yes it has false
negatives — that is acceptable, the goal is throughput not recall.

### Step 4 — AI synthesis

Send AI:

- The filtered `(seminal, challenger)` pairs (max 30).
- The user's seed papers.
- The user's `derived_traits.engaging_axes` (lean toward) and
  `boring_axes` (avoid).

Synthesis prompt outline:

```
You are constructing a Controversy Map for a researcher.

INPUT
- A list of (seminal_paper, recent_challenger_paper) pairs from the
  domain "<DOMAIN>".
- The user's seed papers and their notes.
- The user's engaging_axes and boring_axes from prior reactions.

TASK
Produce 5 to 8 controversy cards, where each card is a propositional
disagreement (X claims P, Y claims not-P) supported by at least one
recent paper on each side.

HARD CONSTRAINTS
- Each card must occupy a distinct diversity_axis from
  {mechanism, evaluation, framing, scope, data}.
- Reject "old vs new" or "method A outperforms method B" framings.
  Those are progress, not controversy.
- If you cannot find a paper from the last 3 years on BOTH sides,
  drop the card.
- Lean toward the user's engaging_axes; deprioritize but do not erase
  the boring_axes.

OUTPUT
JSONL matching the schema in references/paradigm_controversy.md.
Include a one-line ai_synthesis_note explaining why each is a
real fight rather than a topical preference.
```

## Failure mode the user should know about

If commercial vs academic framings dominate the candidates (e.g.
"industry uses A, academia uses B"), this is not a real controversy —
it is a deployment-constraint difference. Skip those pairs in
synthesis. The skill should warn in the report when ≥30% of candidates
were dropped for this reason.
