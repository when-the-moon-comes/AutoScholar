# Paradigm: Cross-Domain Pairs

Surface 5-8 paper pairs (one from the user's home domain + one from
another field) where the **problem structures** look isomorphic. The
user judges whether the isomorphism is real.

## Output

`<workspace>/artifacts/cross_domain_pairs.jsonl`. One pair per line.

```json
{
  "card_id": "cross_<NN>",
  "ai_diversity_axis": "input_structure | objective | constraint | failure_mode | aggregation",
  "skeleton": "<= 250 chars; the abstract problem-structure both papers share",
  "home_paper": {
    "paper_id": "...",
    "title": "...",
    "year": 2024,
    "field": "string"
  },
  "foreign_paper": {
    "paper_id": "...",
    "title": "...",
    "year": 2024,
    "field": "string; must be != home_paper.field"
  },
  "isomorphism_hypothesis": "<= 250 chars; what would it mean if these are the same problem at different surface levels",
  "likely_break_point": "<= 200 chars; where the isomorphism is most likely to fail under scrutiny"
}
```

## Hard rules

- `home_paper.field` and `foreign_paper.field` must be different
  Semantic Scholar `fieldOfStudy` values. Same-field pairs are not
  cross-domain.
- The pairs must NOT share heavy surface-vocabulary overlap (e.g.
  both using "attention" is not isomorphism, it is a coincidence).
  AI verifies this by inspecting paper abstracts before
  hypothesizing.
- `likely_break_point` is mandatory and not optional — it is the
  field that turns this from a parlor trick into a research signal.
  If AI cannot identify a likely break point, the pair is too
  shallow; drop it.
- Diversity: at least 3 distinct values of `ai_diversity_axis`
  across the pair set.

## Retrieval pipeline

### Step 1 — Skeleton extraction (AI only, no API call)

AI reads the user's seed papers (the strongest DNA signal in the
profile) and extracts 1-2 sentence problem-structure skeletons for
each. The skeleton is a description of:

- input shape (what comes in, with what structure)
- objective (what is being predicted/decided/optimized)
- core difficulty (why a naive solution fails)

A skeleton must NOT mention the home domain by name.

Example: a domain-segmentation paper might yield the skeleton
"input is a structured signal where local cues are noisy but a global
context exists; objective is to assign a label to each location;
difficulty is that local cues are individually under-determined."

### Step 2 — Cross-domain candidate sweep

For each skeleton, generate 2-3 functional-vocabulary queries
(deliberately no domain words) and search across multiple
fieldsOfStudy.

```python
# TODO(user): wire to existing helpers
from autoscholar.semantic_crawl import SemanticCrawlConfig, SemanticQuery, crawl_semantic_queries

skeleton_queries = []
for sk_idx, sk in enumerate(skeletons):
    # TODO(ai): generate 2-3 functional queries per skeleton at synthesis time
    for q_idx, q in enumerate(sk["functional_queries"]):
        skeleton_queries.append(SemanticQuery(f"sk{sk_idx}_q{q_idx}", q))

# Use the existing client's bulk search with a fieldsOfStudy filter, OR do
# multiple relevance searches each restricted to one foreign field.
config = SemanticCrawlConfig(
    output=workspace / "artifacts" / "semantic_results.jsonl",
    failures=workspace / "artifacts" / "semantic_failures.jsonl",
    endpoint="bulk",
    limit=20,
    fields="paperId,title,year,abstract,citationCount,fieldsOfStudy,authors,venue",
    # TODO(user): pass the foreign fieldsOfStudy here. Suggested defaults:
    #   excluding home_field, prefer ["Biology", "Physics", "Sociology",
    #   "Psychology", "Economics", "Linguistics"]
    until_complete=True,
)
crawl_semantic_queries(skeleton_queries, config)
```

### Step 3 — Surface-vocabulary filter

Reject candidates whose top tokens overlap with the home-domain
vocabulary. Concretely: tokenize the abstract, drop stopwords, and
discard candidates where the home-domain vocabulary share is > 25%.

(Implementation note: reuse `tokenize` and `rules_stopwords` from
`src/autoscholar/citation/common.py` — the existing helpers already
handle this style of token comparison.)

### Step 4 — AI pairing

Send AI:

- The skeletons.
- For each skeleton, 5-10 surviving foreign-domain candidates with
  abstracts.
- The home-domain seed papers (these are the home_paper side).
- The user's `derived_traits` (engaging_keywords, engaging_axes).

Pairing prompt outline:

```
You are constructing Cross-Domain Pairs for a researcher.

INPUT
- Skeletons extracted from the user's home-domain seed papers.
- For each skeleton, foreign-domain candidate papers with abstracts.
- The home-domain seed papers as candidates for the home_paper side.

TASK
Produce 5-8 pairs (home_paper, foreign_paper) where the structural
isomorphism is non-obvious but defensible.

HARD CONSTRAINTS
- home_paper.field != foreign_paper.field (use Semantic Scholar
  fieldsOfStudy).
- Reject pairs whose isomorphism rests on shared surface vocabulary.
- For every pair, you MUST supply a likely_break_point. If you cannot
  identify one, drop the pair.
- Diversity: at least 3 distinct ai_diversity_axis values across
  the set.
- Aim for "surprising but plausible" cross-domain distance. Adjacent
  sub-fields are too close; literary-criticism-meets-computer-vision
  is too far.

OUTPUT
JSONL matching the schema in references/paradigm_cross_domain.md.
```

## Failure mode the user should know about

If most candidate pairs collapse to "both use attention" or "both use
graph neural networks", the surface-vocabulary filter was not strict
enough. The report should warn and suggest manually narrowing the
home-domain vocabulary list.

If AI cannot produce 5 valid pairs, the report should say
"isomorphism harvest is thin; consider adding 1-2 more diverse seed
papers and rerunning."

## Why this paradigm has the longest reaction half-life

A `partial` reaction here often takes weeks to mature into an idea —
much longer than the other paradigms. The `react` command should
record `partial` reactions but the skill should NOT prompt the user
for an immediate take. Instead, the report ends with: "leave partial
reactions open; revisit them in 1-2 weeks."
