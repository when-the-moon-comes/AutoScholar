# AutoScholar

AutoScholar is a tool-oriented repository for adding citations to academic paper drafts.

It is built around a claim-first workflow:

1. extract citation-worthy claims from a draft
2. prepare search queries
3. batch-search Semantic Scholar
4. deduplicate and prescreen results
5. generate claim-level recommendation lists
6. generate a clean BibTeX file
7. insert citations back into the manuscript


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
- [generate_references_bib.py](/d:/pythonProject/AutoScholar/scripts/generate_references_bib.py)
  Generates a manuscript-ready `references.bib`.

### Reusable configuration

- [claim_recommendation_rules.yaml](/d:/pythonProject/AutoScholar/config/claim_recommendation_rules.yaml)
  Query exclusions, paper exclusions, and claim notes for recommendation generation.

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

### 2. Deduplicate and prescreen

```powershell
python scripts\dedupe_and_prescreen_semantic_scholar.py
```

### 3. Build claim recommendations

```powershell
python scripts\generate_claim_recommendation_list.py
```

You can also pass a different rules file:

```powershell
python scripts\generate_claim_recommendation_list.py config\claim_recommendation_rules.yaml
```

### 4. Generate BibTeX

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
- Recommendation output should always be reviewed before citation insertion.
- Search aggregators are discovery tools, not formal publication venues; generated `.bib` files should not preserve Semantic Scholar URLs as final citation metadata.


## Next Improvements

- make all script input/output paths configurable rather than implicitly tied to `paper/`
- add a dedicated citation-insertion audit script
- add richer BibTeX field completion beyond `author/title/year/journal/doi`
- provide a clean starter template for a new paper workspace
