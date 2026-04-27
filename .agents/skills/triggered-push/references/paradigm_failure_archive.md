# Paradigm: Failure Archive

Surface 5-10 directions in the domain that were once promising but
have gone quiet, with the abandonment reasons classified as **era-
dependent** (likely revivable) or **permanent** (genuinely closed).

## Output

`<workspace>/artifacts/failure_archive.jsonl`. One archive entry per
line.

```json
{
  "card_id": "failure_<NN>",
  "ai_diversity_axis": "method | data | evaluation | framing | infra",
  "direction_name": "<= 80 chars; what the direction was called",
  "peak_period": {"start_year": 2014, "end_year": 2017},
  "peak_papers": [
    {"paper_id": "...", "title": "...", "year": 2015, "citation_count": 412}
  ],
  "abandonment": {
    "year_estimate": 2020,
    "reasons": [
      {
        "reason": "<= 200 chars",
        "category": "era_dependent | permanent",
        "evidence_papers": [{"paper_id": "...", "title": "...", "year": 2019}]
      }
    ]
  },
  "current_condition_changes": [
    "<= 150 chars each; concrete things that exist now but did not at peak"
  ],
  "ai_synthesis_note": "1-2 sentences; why this is genuinely abandoned, not silently absorbed into mainstream"
}
```

## Hard rules

- A direction is **NOT** a failure if its essence has been absorbed
  into a successor framework. The synthesis must filter these out.
- At least one reason per card must be classified as `era_dependent`
  for the card to be useful (else nothing for the user to react to).
- `current_condition_changes` must be specific. "Compute is better
  now" fails. "Pretrained 100M-param backbones are now standard"
  passes.
- If `era_dependent` reasons cover 0 cards, the report should say
  so and recommend `controversy` instead.

## Retrieval pipeline

### Step 1 — Historical stars

Bulk-search the domain with a citation-count sort and a year window
that ends 5+ years ago.

```python
# TODO(user): wire to existing helpers
from autoscholar.semantic_crawl import SemanticCrawlConfig, SemanticQuery, crawl_semantic_queries

queries = [SemanticQuery("history_stars", domain)]
config = SemanticCrawlConfig(
    output=workspace / "artifacts" / "semantic_results.jsonl",
    failures=workspace / "artifacts" / "semantic_failures.jsonl",
    endpoint="bulk",
    limit=50,
    fields="paperId,title,year,abstract,citationCount,venue,authors",
    sort="citationCount:desc",
    year=f"{NOW_YEAR - 15}-{NOW_YEAR - 5}",
    until_complete=True,
)
crawl_semantic_queries(queries, config)
```

### Step 2 — Citation timeline

For each historical star, fetch its forward citations and bucket by
year.

```python
# TODO(user): wire to existing client
from autoscholar.integrations import SemanticScholarClient

with SemanticScholarClient() as client:
    citations = client.get_paper_citations(
        paper_id=star_paper_id,
        fields="paperId,year",
    )
year_buckets = collections.Counter(c.get("year") for c in citations if c.get("year"))
```

### Step 3 — Abandonment scoring

Compute a peak year and a recent decay ratio.

```python
peak_year, peak_count = max(year_buckets.items(), key=lambda x: x[1])
recent_count = sum(year_buckets[y] for y in range(NOW_YEAR - 1, NOW_YEAR + 1))
decay_ratio = recent_count / peak_count if peak_count > 0 else 0
is_abandoned_candidate = decay_ratio < 0.20 and peak_count >= 30
```

Keep candidates with `is_abandoned_candidate == True`.

### Step 4 — Critique sweep

For each abandoned candidate, search for retrospective or critical
papers.

```python
# TODO(user): wire to existing client
critique_payloads = client.search_papers(
    query=f"{star_paper_topic} reconsidered limitations negative results",
    limit=8,
    fields="paperId,title,year,abstract,citationCount",
)
```

### Step 5 — Absorption check (critical)

A direction may have died because it was absorbed into a successor.
That is success, not failure. Use the recent literature to detect
absorption:

```python
# TODO(user): wire to existing client
absorption_check = client.search_papers(
    query=f"{star_paper_topic} extension generalization unified",
    limit=10,
    fields="paperId,title,year,abstract,citationCount",
)
```

Forward this list to AI with an explicit instruction: *if the
recent papers contain a successor that includes the old direction as
a special case, mark the candidate as "absorbed" and drop it.*

### Step 6 — AI synthesis

Send AI:

- The abandonment candidates with their citation timelines.
- The critique payloads.
- The absorption-check payloads.
- The user's seed papers and engaging_axes / boring_axes.
- A list of "now-standard infrastructure" the user knows about (pulled
  from `seed_papers.md`; if absent, use a generic list: pretrained
  language models, foundation backbones, large compute, public
  large-scale datasets).

Synthesis prompt outline:

```
You are constructing a Failure Archive for a researcher.

INPUT
- Candidates of the form (historical_star_paper, citation_timeline,
  critique_papers, absorption_check_papers).
- The user's seed papers and engaging/boring axes.
- A list of "now-standard infrastructure".

TASK
Produce 5 to 10 archive entries, each describing one abandoned
direction with peak period, abandonment reasons, and condition
changes.

HARD CONSTRAINTS
- If absorption_check_papers contain a successor that subsumes the
  direction, drop the candidate. Note this in synthesis_note for at
  most 2 examples to inform the user.
- Each reason must be tagged era_dependent or permanent.
- Era_dependent reasons require a specific condition_change that is
  concrete (not "compute is better now").
- Diversity: across the entry set, at least 3 distinct values of
  ai_diversity_axis.

OUTPUT
JSONL matching the schema in references/paradigm_failure_archive.md.
```

## Failure mode the user should know about

If most candidates fail the absorption check, the domain is one where
old ideas tend to be eaten by general frameworks. The report header
should say "this domain has high absorption — the failure archive may
be thin; consider `cross-domain` instead."
