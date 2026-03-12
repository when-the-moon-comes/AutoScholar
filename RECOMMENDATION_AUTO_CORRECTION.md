# Recommendation Auto-Correction

## Purpose

This repository now includes a standalone extension layer for claims whose Semantic Scholar
keyword retrieval is weak, mixed, or off-target.

It does not replace the existing search pipeline. It adds a second-stage expansion step that:

1. reads the current claim-level recommendation state
2. detects claims that likely need correction
3. selects a small number of seed papers from the existing result pool
4. calls the Semantic Scholar Recommendations API for those seeds
5. merges recommended papers back into a ranked correction candidate list


## What It Does Not Do

- it does not modify existing search results
- it does not rewrite queries automatically
- it does not overwrite the current `claim_recommended_citations.md`
- it does not change any of the four existing workflow scripts

This is an additive review layer only.


## New Files

- [recommendation_auto_correct.py](/d:/pythonProject/AutoScholar/scripts/recommendation_auto_correct.py)
  Standalone correction runner.
- [recommendation_auto_correct.yaml](/d:/pythonProject/AutoScholar/config/recommendation_auto_correct.yaml)
  Default config for trigger thresholds, seed policy, and output paths.


## Default Inputs

By default, the correction runner reads:

- `paper/citation_claim_units.md`
- `paper/semantic_scholar_raw_results_deduped.jsonl`
- `paper/claim_recommendation_rules.yaml`

The rules file is intentionally paper-specific because correction quality depends heavily on
query exclusions, paper exclusions, and claim notes already built during prescreening.


## Default Outputs

When run live, the script writes:

- `paper/semantic_scholar_recommendation_corrections.jsonl`
- `paper/semantic_scholar_recommendation_correction_report.md`

The JSONL is for downstream tooling. The Markdown report is for manual review.


## Trigger Logic

A claim enters the correction pass if at least one of these conditions is met:

- current claim recommendation status is `weak`
- current claim recommendation status is `review`
- the claim has a manual note in `claim_recommendation_rules.yaml`
- the claim has no usable non-excluded query records
- the current recommendation stage surfaces too few selected papers
- no selected paper has enough cross-query support
- the claim has only a small number of low-citation candidates

These thresholds are configurable in `config/recommendation_auto_correct.yaml`.


## Seed Selection Logic

The script only uses existing retrieved papers as seeds.

Seed papers must:

- survive current paper exclusion rules
- have a valid `paperId`
- have enough textual overlap with the claim and query context

The highest-ranked eligible seeds are passed to the Recommendations API.


## Candidate Ranking Logic

After expansion, candidates are ranked by:

1. whether they are supported by both query retrieval and recommendations
2. query support count
3. recommendation support count
4. textual overlap with the claim
5. textual overlap with the query context
6. influential citations
7. citations
8. year

This keeps the correction pass grounded in the existing claim-first retrieval flow rather than
blindly trusting citation counts.


## Statuses

- `pending_api`: dry-run mode found a trigger and valid seeds, but no API call was made
- `rewrite_needed`: no trustworthy seed paper was found; rewrite the query instead
- `corrected_ready`: correction produced strong enough top candidates
- `corrected_review`: correction helped, but the claim still needs manual inspection
- `blocked`: recommendations did not return usable improvement


## Run Commands

Dry run:

```powershell
python scripts\recommendation_auto_correct.py --dry-run
```

Live run with default config:

```powershell
python scripts\recommendation_auto_correct.py
```

Run only selected claims:

```powershell
python scripts\recommendation_auto_correct.py --claim-id C07 --claim-id C11
```

Use a different config:

```powershell
python scripts\recommendation_auto_correct.py config\recommendation_auto_correct.yaml
```


## Recommended Workflow Position

The intended order is:

1. `python scripts\batch_semantic_scholar_search.py`
2. `python scripts\dedupe_and_prescreen_semantic_scholar.py`
3. `python scripts\recommendation_auto_correct.py`
4. `python scripts\generate_claim_recommendation_list.py`
5. `python scripts\generate_references_bib.py`

If a claim ends up as `rewrite_needed`, fix the underlying query set and rerun the normal
search pipeline for that claim rather than forcing recommendation-based expansion.
