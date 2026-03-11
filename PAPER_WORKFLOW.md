# Paper Citation Workflow

## Purpose

This document captures the end-to-end workflow used in this repository to add scholarly citations to a draft paper and generate a usable BibTeX file. It is intended as a reusable template for future paper writing projects.

The workflow is designed for this pattern:

- start from a draft `.tex` paper with weak or missing citations
- extract claim-level citation needs first
- search papers in batches through Semantic Scholar
- filter noisy search results before they reach the manuscript
- generate a clean `.bib`
- insert citations back into the manuscript with manual judgment


## Core Principle

Do not start by blindly searching for papers sentence by sentence.

The correct order is:

1. understand the paper
2. extract claims that truly need external support
3. prepare targeted search queries
4. search in batches
5. deduplicate and prescreen results
6. recommend citations at the claim level
7. build a clean bibliography
8. insert citations back into the text
9. run a post-insertion quality check


## Repository Structure

### Manuscript

- [paper.tex](/d:/pythonProject/AutoScholar/paper/paper.tex): main manuscript
- [references.bib](/d:/pythonProject/AutoScholar/paper/references.bib): final bibliography

### Intermediate citation workflow files

- [citation_claim_units.md](/d:/pythonProject/AutoScholar/paper/citation_claim_units.md): claim units that need scholarly support
- [search_keyword_prep.md](/d:/pythonProject/AutoScholar/paper/search_keyword_prep.md): query-ready keywords and search strings
- [semantic_scholar_search.yaml](/d:/pythonProject/AutoScholar/paper/semantic_scholar_search.yaml): batch search configuration
- [semantic_scholar_raw_results.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results.jsonl): raw search output
- [semantic_scholar_raw_results_deduped.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results_deduped.jsonl): deduplicated raw results
- [semantic_scholar_prescreen.md](/d:/pythonProject/AutoScholar/paper/semantic_scholar_prescreen.md): query-level prescreen report
- [claim_recommended_citations.md](/d:/pythonProject/AutoScholar/paper/claim_recommended_citations.md): final claim-level recommendation list

### Scripts

- [batch_semantic_scholar_search.py](/d:/pythonProject/AutoScholar/scripts/batch_semantic_scholar_search.py): batch Semantic Scholar search runner
- [dedupe_and_prescreen_semantic_scholar.py](/d:/pythonProject/AutoScholar/scripts/dedupe_and_prescreen_semantic_scholar.py): query deduplication and prescreen
- [generate_claim_recommendation_list.py](/d:/pythonProject/AutoScholar/scripts/generate_claim_recommendation_list.py): claim-level recommendation generator
- [generate_references_bib.py](/d:/pythonProject/AutoScholar/scripts/generate_references_bib.py): clean `.bib` generator


## Step 1: Read the Draft and Define Citation Scope

### Goal

Identify which parts of the paper need external literature support.

### Include

- background judgments in the introduction
- methodological claims that rely on prior literature
- theory and conceptual framing
- case selection claims
- policy or governance propositions that are not purely the author's own empirical result

### Exclude

- this paper's own result descriptions
- figure captions that only report this paper's outputs
- parameter settings that are self-contained unless they rely on prior method literature
- raw data source listings already identifiable by official product names

### Output

- [citation_claim_units.md](/d:/pythonProject/AutoScholar/paper/citation_claim_units.md)

### Recommended format

Each row should contain:

- `claim_id`
- `section`
- `source_lines`
- `claim_text`
- `claim_type`
- `priority`


## Step 2: Convert Claims into Searchable Queries

### Goal

Convert each claim into 2 to 3 English academic queries.

### Rules

- use stable academic phrases, not full sentences
- prepare multiple query variants for each claim
- prefer English keywords even if the paper draft is bilingual
- for case claims, keep one generic query and one case-localized query
- for policy claims, convert slogans into searchable academic terms

### Output

- [search_keyword_prep.md](/d:/pythonProject/AutoScholar/paper/search_keyword_prep.md)

### Minimum fields

- `claim_id`
- `short_label`
- `core_keywords`
- `query_1`
- `query_2`
- `query_3` if needed
- `notes`


## Step 3: Batch Search Semantic Scholar

### Goal

Run all prepared queries in a reproducible batch process.

### Configuration

The batch search is controlled by [semantic_scholar_search.yaml](/d:/pythonProject/AutoScholar/paper/semantic_scholar_search.yaml).

Current script supports two modes:

- `single_thread`
- `multi_thread`

Both are treated as aggressive acquisition modes rather than conservative rate-window waiting modes.

### Run command

```powershell
python scripts\batch_semantic_scholar_search.py
```

### Input

- [search_keyword_prep.md](/d:/pythonProject/AutoScholar/paper/search_keyword_prep.md)

### Outputs

- [semantic_scholar_raw_results.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results.jsonl)
- [semantic_scholar_failures.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_failures.jsonl)

### Notes

- no API key is required, but rate limiting will occur
- the workflow assumes retryable failures are normal
- the runner must support resumability and query-level persistence
- the runner must not depend on a single uninterrupted run


## Step 4: Deduplicate and Prescreen Search Results

### Goal

Do not move raw search results directly into the paper.

The raw query set must first be cleaned at the query level.

### Run command

```powershell
python scripts\dedupe_and_prescreen_semantic_scholar.py
```

### Outputs

- [semantic_scholar_raw_results_deduped.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results_deduped.jsonl)
- [semantic_scholar_prescreen.md](/d:/pythonProject/AutoScholar/paper/semantic_scholar_prescreen.md)

### Prescreen logic

- deduplicate repeated successful query records
- mark empty or weak-result queries
- exclude known off-topic queries
- surface query-level problems before claim-level recommendation

### Typical statuses

- `keep`
- `review`
- `rewrite`
- `exclude`


## Step 5: Build Claim-Level Recommendation Lists

### Goal

Move from query-level results to claim-level recommended citations.

### Run command

```powershell
python scripts\generate_claim_recommendation_list.py
```

### Output

- [claim_recommended_citations.md](/d:/pythonProject/AutoScholar/paper/claim_recommended_citations.md)

### Selection logic

- exclude known noisy queries
- exclude obviously off-topic papers
- rank by topical fit, support across queries, and citation signal
- keep a `review` status for claims whose evidence pool is still mixed

### Important principle

Recommendation is not the same as automatic insertion.

This file is a shortlist for manuscript use, not a final truth set.


## Step 6: Generate a Clean BibTeX File

### Goal

Create a manuscript-ready `.bib` instead of a raw metadata dump.

### Run command

```powershell
python scripts\generate_references_bib.py
```

### Output

- [references.bib](/d:/pythonProject/AutoScholar/paper/references.bib)

### Current cleaning rules

- remove `Semantic Scholar` URLs
- retain `doi` where available
- infer `@article`, `@incollection`, `@inproceedings`, or `@book`
- normalize citekeys
- clean non-ASCII artifacts in cited entries for safer `BibTeX` compilation

### Important note

Search platforms are discovery tools, not formal publication venues.

The `.bib` should reflect scholarly citation norms, not the search platform's URL structure.


## Step 7: Insert Citations Back into the Manuscript

### Goal

Add citations back into the paper carefully, at the claim level.

### Working rule

Do not cite every sentence.

Insert citations only where the sentence makes a claim that depends on prior literature, theory, method precedent, comparative context, or policy literature.

### Priority order

1. introduction background claims
2. conceptual framing
3. method justification
4. case selection and comparative claims
5. discussion and policy claims

### Current manuscript

- [paper.tex](/d:/pythonProject/AutoScholar/paper/paper.tex)

### Current status in this repository

- major citation-bearing sections already have citations inserted
- insertion was done manually rather than by blind automated replacement


## Step 8: Post-Insertion Quality Check

### Goal

Ensure citation insertion did not damage the manuscript.

### Required checks

- all `\cite{...}` keys exist in [references.bib](/d:/pythonProject/AutoScholar/paper/references.bib)
- inserted citations do not land inside pure result-reporting sentences unless clearly justified
- no Semantic Scholar URLs remain in the bibliography
- used bibliography entries are safe for the chosen compile path
- no sentence meaning was accidentally changed during insertion

### Current practical checks used in this repository

- count `\cite{...}` occurrences
- compare unique citekeys against BibTeX keys
- inspect insertion hotspots manually
- remove or replace cited entries with broken encoding


## Compilation Notes

This manuscript currently uses `natbib`, not `biblatex`.

The compile order should be:

```text
xelatex paper.tex
bibtex paper
xelatex paper.tex
xelatex paper.tex
```

Required conditions:

- [paper.tex](/d:/pythonProject/AutoScholar/paper/paper.tex) and [references.bib](/d:/pythonProject/AutoScholar/paper/references.bib) must stay in the same directory
- `\bibliography{references}` must point to `references.bib`


## Recommended Quality Standard for Future Papers

### Good practice

- cite at the claim level, not mechanically at fixed sentence intervals
- use 2 to 3 strong references rather than 5 weak ones
- separate theory claims from method claims from policy claims
- keep noisy search outputs out of the manuscript
- generate the bibliography only after prescreen and recommendation

### Bad practice

- searching before understanding the paper
- inserting citations directly from raw search hits
- leaving aggregator URLs in the final `.bib`
- citing your own empirical results as though they were prior literature
- using low-fit literature just because it shares a keyword


## Minimal Reusable Workflow

For a new paper, the minimal repeatable workflow is:

1. create `paper/paper.tex`
2. extract claim units into `paper/citation_claim_units.md`
3. prepare queries in `paper/search_keyword_prep.md`
4. configure `paper/semantic_scholar_search.yaml`
5. run `python scripts\batch_semantic_scholar_search.py`
6. run `python scripts\dedupe_and_prescreen_semantic_scholar.py`
7. run `python scripts\generate_claim_recommendation_list.py`
8. run `python scripts\generate_references_bib.py`
9. insert `\cite{...}` manually into `paper/paper.tex`
10. run citation integrity checks
11. compile in the cloud if no local TeX environment exists


## What Should Be Improved Next Time

This workflow is already usable, but future iterations should improve these parts:

- preserve an untouched manuscript snapshot before citation insertion
- add a dedicated citation-insertion audit script
- enrich BibTeX fields beyond `author/title/year/journal/doi`
- add a manuscript-level report showing which claims are still weakly supported
- separate high-confidence citations from provisional discussion citations


## Summary

This repository now implements a repeatable citation workflow:

- claim extraction
- keyword preparation
- batch search
- deduplication
- prescreen
- claim-level recommendation
- clean bibliography generation
- careful manuscript insertion
- post-insertion verification

This should be treated as the default paradigm for future paper citation work in this project.
