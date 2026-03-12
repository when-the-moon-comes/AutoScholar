# AutoScholar

AutoScholar is a tool-oriented repository for adding citations to academic paper drafts.

It is built around a claim-first workflow:

1. extract citation-worthy claims from a draft
2. prepare search queries
3. batch-search Semantic Scholar
4. deduplicate and prescreen results
5. run agent-guided recommendation expansion when needed
6. generate claim-level recommendation lists
7. generate a clean BibTeX file
8. insert citations back into the manuscript


## What This Repo Contains

### Core search capability

- [SemanticScholarApi/api.py](/d:/pythonProject/AutoScholar/SemanticScholarApi/api.py)
- [.agents/skills/semantic_scholar_api/SKILL.md](/d:/pythonProject/AutoScholar/.agents/skills/semantic_scholar_api/SKILL.md)

### Reusable scripts

- [batch_semantic_scholar_search.py](/d:/pythonProject/AutoScholar/scripts/batch_semantic_scholar_search.py)
  Batch Semantic Scholar search runner driven by YAML.
- [dedupe_and_prescreen_semantic_scholar.py](/d:/pythonProject/AutoScholar/scripts/dedupe_and_prescreen_semantic_scholar.py)
  Deduplicates raw query results and generates a prescreen report.
- [generate_claim_recommendation_list.py](/d:/pythonProject/AutoScholar/scripts/generate_claim_recommendation_list.py)
  Builds claim-level citation recommendations from prescreened search results.
- [recommendation_auto_correct.py](/d:/pythonProject/AutoScholar/scripts/recommendation_auto_correct.py)
  Agent-guided recommendation expansion step for weak or mixed retrieval claims.
- [generate_references_bib.py](/d:/pythonProject/AutoScholar/scripts/generate_references_bib.py)
  Generates a manuscript-ready `references.bib`.

### Reusable configuration

- [claim_recommendation_rules.yaml](/d:/pythonProject/AutoScholar/config/claim_recommendation_rules.yaml)
  Query exclusions, paper exclusions, and claim notes for recommendation generation.
- [recommendation_auto_correct.yaml](/d:/pythonProject/AutoScholar/config/recommendation_auto_correct.yaml)
  Trigger thresholds and recommendation expansion settings.

### Workflow documentation

- [PAPER_WORKFLOW.md](/d:/pythonProject/AutoScholar/PAPER_WORKFLOW.md)
  Full end-to-end workflow and reuse pattern.


## Repository Philosophy

This repository is intended to be a tool repository, not a paper-content repository.

That means:

- scripts and workflow documents should be versioned
- per-paper working files should stay outside the core repo history
- temporary or paper-specific artifacts should be ignored

The current [\.gitignore](/d:/pythonProject/AutoScholar/.gitignore) ignores the whole `paper/` workspace.


## Minimal Usage Pattern

Prepare a paper workspace locally, then run the pipeline in order.

### 1. Search

```powershell
python scripts\batch_semantic_scholar_search.py
```

Canonical `paper/semantic_scholar_search.yaml` structure:

```yaml
paths:
  input: search_keyword_prep.md
  output: semantic_scholar_raw_results.jsonl
  failures: semantic_scholar_failures.jsonl

run:
  claim_ids: []
  dry_run: false

search:
  endpoint: relevance
  limit: 10
  timeout: 30
  fields: paperId,title,year,authors,url,abstract,citationCount,influentialCitationCount,venue,externalIds,isOpenAccess,openAccessPdf
  filters:
    sort:
    publication_types: []
    open_access_pdf:
    min_citation_count:
    publication_date_or_year:
    year:
    venue:
    fields_of_study: []

execution:
  mode: single_thread
  single_thread:
    workers: 1
    max_retries: 30
    retry_delay: 1.0
    pause_seconds: 1.0
  multi_thread:
    workers: 8
    max_retries: 30
    retry_delay: 1.0
    pause_seconds: 0.0
```

The script still accepts older flat keys for backward compatibility, but the grouped structure above is now the intended single-file layout.

### 2. Deduplicate and prescreen

```powershell
python scripts\dedupe_and_prescreen_semantic_scholar.py
```

### 3. Expand with Recommendations when retrieval is weak or mixed

This step is now treated as part of the main review workflow rather than a disconnected add-on.

The intended operating pattern is:

- the agent reviews prescreened search results claim by claim
- the agent selects trustworthy seed papers and excludes obviously irrelevant papers first
- the agent runs `recommendation_auto_correct.py`
- the agent decides whether another recommendation round is warranted or whether the underlying query should be rewritten instead

Dry run:

```powershell
python scripts\recommendation_auto_correct.py --dry-run
```

Live run:

```powershell
python scripts\recommendation_auto_correct.py
```

### 4. Build claim recommendations

```powershell
python scripts\generate_claim_recommendation_list.py
```

You can also pass a different rules file:

```powershell
python scripts\generate_claim_recommendation_list.py config\claim_recommendation_rules.yaml
```

### 5. Generate BibTeX

```powershell
python scripts\generate_references_bib.py
```


## Expected Workspace Layout

The current scripts assume a per-paper working directory named `paper/` with files such as:

- `paper/paper.tex`
- `paper/citation_claim_units.md`
- `paper/search_keyword_prep.md`
- `paper/semantic_scholar_search.yaml`
- `paper/semantic_scholar_raw_results.jsonl`

These files are intentionally treated as working artifacts rather than core repository assets.


## Notes

- No local LaTeX environment is required for the search and recommendation pipeline.
- The Semantic Scholar workflow can run without an API key, but rate limiting should be expected.
- Recommendation expansion should be agent-reviewed before each live run; seed choice is part of the workflow, not a blind automation step.
- Recommendation expansion can be run multiple times for the same claim set until the evidence pool stabilizes or the agent decides the query set must be rewritten.
- Recommendation output should always be reviewed before citation insertion.
- Search aggregators are discovery tools, not formal publication venues; generated `.bib` files should not preserve Semantic Scholar URLs as final citation metadata.


## Next Improvements

- make all script input/output paths configurable rather than implicitly tied to `paper/`
- add a dedicated citation-insertion audit script
- add richer BibTeX field completion beyond `author/title/year/journal/doi`
- provide a clean starter template for a new paper workspace
