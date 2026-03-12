# Paper Citation Workflow for Agents

## Purpose

This document is the operating guide for an agent working in this repository.

The agent's job is not to blindly fetch papers. The agent's job is to:

- understand the manuscript first
- identify claims that actually need outside support
- build and refine search queries
- keep noisy retrieval out of the evidence pool
- decide when recommendation expansion is warranted
- decide when another recommendation round is worthwhile
- decide when the real problem is the query rather than the current candidate set
- help produce a clean shortlist, a clean bibliography, and safe citation insertion


## Agent Role

The agent is responsible for judgment at every stage of the workflow.

The agent must:

- work at the claim level rather than the sentence count level
- prefer precision over volume once the evidence pool is usable
- avoid carrying weak or off-topic papers downstream just because they share keywords
- use recommendation expansion as a guided review tool, not as blind automation
- preserve manuscript meaning during citation insertion

The agent must not:

- search sentence by sentence without understanding the draft
- treat raw Semantic Scholar outputs as citation-ready
- assume that recommendation outputs automatically become part of the final claim recommendation list
- cite the manuscript's own empirical findings as if they were prior literature


## Current Repository Behavior

The current repository behavior matters for agent decisions:

- `paper/` is a per-paper workspace and is not versioned in the core repository
- `recommendation_auto_correct.py` produces separate correction artifacts for review
- recommendation expansion does not automatically overwrite `claim_recommended_citations.md`
- the agent must decide whether recommendation outputs are useful enough to influence downstream review


## Workspace and Artifacts

### Core manuscript files

- [paper.tex](/d:/pythonProject/AutoScholar/paper/paper.tex): main manuscript
- [references.bib](/d:/pythonProject/AutoScholar/paper/references.bib): final bibliography

### Intermediate workflow files

- [citation_claim_units.md](/d:/pythonProject/AutoScholar/paper/citation_claim_units.md): claim units needing support
- [search_keyword_prep.md](/d:/pythonProject/AutoScholar/paper/search_keyword_prep.md): prepared search queries
- [semantic_scholar_search.yaml](/d:/pythonProject/AutoScholar/paper/semantic_scholar_search.yaml): batch search config
- [semantic_scholar_raw_results.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results.jsonl): raw search output
- [semantic_scholar_raw_results_deduped.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results_deduped.jsonl): deduplicated search results
- [semantic_scholar_prescreen.md](/d:/pythonProject/AutoScholar/paper/semantic_scholar_prescreen.md): query-level prescreen report
- [semantic_scholar_recommendation_corrections.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_recommendation_corrections.jsonl): recommendation expansion output
- [semantic_scholar_recommendation_correction_report.md](/d:/pythonProject/AutoScholar/paper/semantic_scholar_recommendation_correction_report.md): recommendation expansion review report
- [claim_recommended_citations.md](/d:/pythonProject/AutoScholar/paper/claim_recommended_citations.md): final claim-level shortlist

### Scripts

- [batch_semantic_scholar_search.py](/d:/pythonProject/AutoScholar/scripts/batch_semantic_scholar_search.py)
- [dedupe_and_prescreen_semantic_scholar.py](/d:/pythonProject/AutoScholar/scripts/dedupe_and_prescreen_semantic_scholar.py)
- [recommendation_auto_correct.py](/d:/pythonProject/AutoScholar/scripts/recommendation_auto_correct.py)
- [generate_claim_recommendation_list.py](/d:/pythonProject/AutoScholar/scripts/generate_claim_recommendation_list.py)
- [generate_references_bib.py](/d:/pythonProject/AutoScholar/scripts/generate_references_bib.py)

### Rules and config

- optional [claim_recommendation_rules.yaml](/d:/pythonProject/AutoScholar/paper/claim_recommendation_rules.yaml): active per-paper exclusions, notes, weights
- fallback [claim_recommendation_rules.yaml](/d:/pythonProject/AutoScholar/config/claim_recommendation_rules.yaml): repository default exclusions, notes, weights
- [recommendation_auto_correct.yaml](/d:/pythonProject/AutoScholar/config/recommendation_auto_correct.yaml): correction triggers and settings


## End-to-End Workflow

The default operating order is:

1. read the draft and define citation scope
2. extract claim units
3. prepare searchable queries
4. run batch search
5. deduplicate and prescreen results
6. decide whether recommendation expansion is needed
7. run recommendation expansion when warranted
8. build the claim-level recommendation list
9. generate a clean bibliography
10. insert citations into the manuscript
11. run a post-insertion quality check


## Step 1: Read the Draft and Define Citation Scope

### Goal

Identify which manuscript statements need scholarly support.

### Inputs

- [paper.tex](/d:/pythonProject/AutoScholar/paper/paper.tex)

### Agent responsibilities

- read enough of the manuscript to understand argument structure
- identify background, theory, method, comparative, and policy claims that depend on outside literature
- exclude sentences that only report this paper's own findings
- exclude low-value units that do not need literature support

### Include

- background judgments in the introduction
- theory and conceptual framing
- method claims that rely on prior work
- case selection claims
- policy, planning, or governance claims that are not purely the paper's own result

### Exclude

- this paper's own result descriptions
- figure captions that only report this paper's outputs
- parameter settings that are fully self-contained
- raw source listings already identifiable by standard product names

### Output

- [citation_claim_units.md](/d:/pythonProject/AutoScholar/paper/citation_claim_units.md)

### Completion standard

The agent should stop this step only when every claim that needs support is captured once, and obvious non-claims have been filtered out.


## Step 2: Extract Claim Units

### Goal

Create a structured claim list that downstream tools can use.

### Inputs

- manuscript understanding from Step 1

### Agent responsibilities

- write each support-worthy claim as a separate unit
- keep each unit narrow enough to be searchable
- assign consistent `claim_id` values
- record section, source lines, claim type, and priority

### Required fields

- `claim_id`
- `section`
- `source_lines`
- `claim_text`
- `claim_type`
- `priority`

### Output

- [citation_claim_units.md](/d:/pythonProject/AutoScholar/paper/citation_claim_units.md)

### Completion standard

Each claim should be specific enough that the agent can later prepare 2 to 3 query variants without guessing what the claim is trying to prove.


## Step 3: Prepare Searchable Queries

### Goal

Turn each claim into a small, query-ready search set.

### Inputs

- [citation_claim_units.md](/d:/pythonProject/AutoScholar/paper/citation_claim_units.md)

### Agent responsibilities

- produce 2 to 3 English academic queries per claim
- vary specificity across query variants
- prefer stable academic phrases over natural-language sentences
- for case claims, keep at least one generic query and one case-localized query when useful
- for policy or planning claims, translate slogans into searchable academic terms
- record notes about expected precision problems or known ambiguity

### Query design rule

The agent may use advanced search syntax when it improves precision or recall, but should do so intentionally rather than decoratively.

Examples of justified use:

- exact phrase matching for highly specific concepts
- exclusion terms when a keyword is dominated by an off-topic subfield
- broader fallback variants when the precise query is too sparse

### Output

- [search_keyword_prep.md](/d:/pythonProject/AutoScholar/paper/search_keyword_prep.md)
- [semantic_scholar_search.yaml](/d:/pythonProject/AutoScholar/paper/semantic_scholar_search.yaml)

### Required fields for `search_keyword_prep.md`

The batch search parser expects a markdown table with these columns:

- `claim_id`
- `short_label`
- `core_keywords`
- `query_1`
- `query_2`
- `query_3`
- `notes`

`query_3` may be empty or `N/A`, but the column must still exist so the table shape stays stable.

### Completion standard

The query set should be diverse enough that one failed query does not collapse the whole claim.


## Step 4: Run Batch Search

### Goal

Run all prepared queries reproducibly and persist raw results.

### Inputs

- [search_keyword_prep.md](/d:/pythonProject/AutoScholar/paper/search_keyword_prep.md)
- [semantic_scholar_search.yaml](/d:/pythonProject/AutoScholar/paper/semantic_scholar_search.yaml)

### Canonical config shape

The agent should keep search settings in a single grouped YAML file rather than scattering flat keys or maintaining multiple variants.

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

Notes for the agent:

- `search.endpoint: relevance` is the safer default when the query set is small and precision-sensitive.
- bulk-only filters belong under `search.filters` and should only be enabled when `search.endpoint: bulk`.
- the script still reads older flat keys, but new or revised workspaces should use the grouped layout above.

### Run command

```powershell
python scripts\batch_semantic_scholar_search.py
```

### Agent responsibilities

- confirm that the search config matches the current paper workspace
- run the batch search in a resumable way
- treat retryable failures and rate limiting as normal
- decide whether a partial rerun is needed for failed or rewritten claims
- preserve query-level traceability so later review can see which papers came from which query

### Outputs

- [semantic_scholar_raw_results.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results.jsonl)
- [semantic_scholar_failures.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_failures.jsonl)

### Completion standard

The agent should move on only when the search run is stable enough that failures are either resolved, accepted as temporary noise, or isolated for later rerun.


## Step 5: Deduplicate and Prescreen Search Results

### Goal

Clean raw query outputs before they influence citation decisions.

### Inputs

- [semantic_scholar_raw_results.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results.jsonl)
- [citation_claim_units.md](/d:/pythonProject/AutoScholar/paper/citation_claim_units.md)

### Run command

```powershell
python scripts\dedupe_and_prescreen_semantic_scholar.py
```

### Agent responsibilities

- inspect the prescreen report claim by claim
- identify empty, weak, broad, or off-topic queries
- decide whether a query should later be excluded, rewritten, or tolerated as a weak backup
- identify papers that are clearly off-topic and should be excluded in the rules file
- update the active rules file with exclusions and notes when needed

### Active rules file

Prefer [claim_recommendation_rules.yaml](/d:/pythonProject/AutoScholar/paper/claim_recommendation_rules.yaml) when the paper workspace has one.

Otherwise use [claim_recommendation_rules.yaml](/d:/pythonProject/AutoScholar/config/claim_recommendation_rules.yaml).

### Outputs

- [semantic_scholar_raw_results_deduped.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results_deduped.jsonl)
- [semantic_scholar_prescreen.md](/d:/pythonProject/AutoScholar/paper/semantic_scholar_prescreen.md)

### Decision rule

If the prescreen report shows that the query set is fundamentally wrong, the agent should go back to Step 3 before using recommendation expansion.


## Step 6: Decide Whether Recommendation Expansion Is Needed

### Goal

Choose whether the current claim evidence pool is already good enough or whether Semantic Scholar recommendations should be used to expand it.

### Inputs

- [semantic_scholar_raw_results_deduped.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results_deduped.jsonl)
- [semantic_scholar_prescreen.md](/d:/pythonProject/AutoScholar/paper/semantic_scholar_prescreen.md)
- the active claim recommendation rules file

### Agent responsibilities

- identify claims with weak, mixed, or off-target retrieval
- decide whether the next best move is recommendation expansion or query rewrite
- prefer query rewrite when the best available seeds are already obviously wrong
- restrict expansion to selected claims when only part of the paper needs help

### Good reasons to expand

- a claim has one or two plausible seed papers but poor breadth
- a claim has mixed retrieval where some papers are clearly on-claim and others are noise
- the claim needs related literature beyond what the original keyword search surfaced

### Good reasons to rewrite instead

- the current result pool contains no trustworthy seeds
- all plausible seeds are only indirectly related to the claim
- the retrieval problem is clearly a vocabulary problem rather than a neighborhood-expansion problem


## Step 7: Run Agent-Guided Recommendation Expansion

### Goal

Use the Recommendations API as a guided expansion tool after the agent has selected seeds.

### Inputs

- [semantic_scholar_raw_results_deduped.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results_deduped.jsonl)
- the active claim recommendation rules file
- [recommendation_auto_correct.yaml](/d:/pythonProject/AutoScholar/config/recommendation_auto_correct.yaml)

### Run commands

Dry run:

```powershell
python scripts\recommendation_auto_correct.py --dry-run
```

Live run:

```powershell
python scripts\recommendation_auto_correct.py
```

Selected claims:

```powershell
python scripts\recommendation_auto_correct.py --claim-id C07 --claim-id C11
```

### Agent responsibilities

- choose seed papers that are truly on-claim rather than merely keyword-adjacent
- use `recommendation_auto_correct.yaml` seed controls when a claim needs explicit positive, negative, or blocked seeds
- exclude obviously irrelevant papers before the API call
- review the correction report after each live run
- decide whether another recommendation round is worthwhile
- decide whether to stop, rerun with better seeds, or go back to Step 3 to rewrite queries

### Seed control rule

The current seed control layer supports three selection modes:

- `auto`: use the script's automatic positive-seed ranking, while still honoring blocked and negative refs
- `hybrid`: use configured positive refs first, then auto-fill remaining positive seed slots
- `manual`: use only configured positive refs

Claim-level controls live under `seed.claim_overrides` in [recommendation_auto_correct.yaml](/d:/pythonProject/AutoScholar/config/recommendation_auto_correct.yaml) and support:

- `positive`
- `negative`
- `blocked`

Accepted seed references are:

- `paperId:<Semantic Scholar paper id>`
- `{paperId: "..."}`
- `{doi: "..."}`
- `{title: "...", year: 2021}`

Important constraint:

- negative seeds only affect the API request when `recommendations.method: positive_seed_list`
- if `recommendations.method: single_seed`, negative seeds are reported but ignored

### Important current behavior

This script writes separate correction artifacts only.

It does not automatically overwrite:

- [claim_recommended_citations.md](/d:/pythonProject/AutoScholar/paper/claim_recommended_citations.md)
- [semantic_scholar_raw_results_deduped.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results_deduped.jsonl)

The agent must therefore treat recommendation expansion as a review layer whose downstream effect is a workflow decision, not an automatic merge.

### Iteration rule

This step may be run multiple times for the same claim set.

### Stop conditions

- the top corrected candidates are strong enough for downstream review
- another round is unlikely to materially improve the candidate pool
- the candidate pool is still weak because the original query is wrong

### Outputs

- [semantic_scholar_recommendation_corrections.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_recommendation_corrections.jsonl)
- [semantic_scholar_recommendation_correction_report.md](/d:/pythonProject/AutoScholar/paper/semantic_scholar_recommendation_correction_report.md)


## Step 8: Build the Claim-Level Recommendation List

### Goal

Produce the manuscript-facing shortlist of citations for each claim.

### Inputs

- [semantic_scholar_raw_results_deduped.jsonl](/d:/pythonProject/AutoScholar/paper/semantic_scholar_raw_results_deduped.jsonl)
- the active claim recommendation rules file
- optionally [semantic_scholar_recommendation_correction_report.md](/d:/pythonProject/AutoScholar/paper/semantic_scholar_recommendation_correction_report.md) for manual review context

### Run command

```powershell
python scripts\generate_claim_recommendation_list.py
```

### Agent responsibilities

- maintain the rules file with excluded queries, excluded papers, claim notes, and scoring weights
- run the recommendation generator after the evidence pool is stable enough
- review the generated shortlist against the correction report when recommendation expansion was used
- decide whether the current shortlist is usable, still needs recommendation iteration, or requires query rewrite

### Active rules file

Prefer [claim_recommendation_rules.yaml](/d:/pythonProject/AutoScholar/paper/claim_recommendation_rules.yaml) when it exists for the current paper workspace.

Otherwise use [claim_recommendation_rules.yaml](/d:/pythonProject/AutoScholar/config/claim_recommendation_rules.yaml).

### Important current behavior

The current generator does not automatically ingest recommendation correction outputs.

The agent should therefore use the correction artifacts as review evidence rather than assuming automatic propagation into the final shortlist.

### Output

- [claim_recommended_citations.md](/d:/pythonProject/AutoScholar/paper/claim_recommended_citations.md)

### Completion standard

Each claim should end in one of three practical states:

- ready for insertion
- review before insertion
- rewrite query and rerun earlier steps


## Step 9: Generate a Clean BibTeX File

### Goal

Create a manuscript-ready bibliography instead of passing raw platform metadata downstream.

### Inputs

- the accepted evidence state from Step 8

### Run command

```powershell
python scripts\generate_references_bib.py
```

### Agent responsibilities

- run bibliography generation only after the recommendation list is stable enough
- inspect generated entries when metadata looks broken or incomplete
- keep discovery-platform metadata out of the final bibliography where possible

### Important current behavior

`generate_references_bib.py` rebuilds the selected paper set from deduplicated search results plus the active rules file.

It does not read a manually edited [claim_recommended_citations.md](/d:/pythonProject/AutoScholar/paper/claim_recommended_citations.md) as the source of truth.

If the agent made final accept/reject decisions during shortlist review, those decisions must be encoded in the active rules file before Step 9.

### Output

- [references.bib](/d:/pythonProject/AutoScholar/paper/references.bib)


## Step 10: Insert Citations Back into the Manuscript

### Goal

Add citations to the draft carefully and at the claim level.

### Inputs

- [paper.tex](/d:/pythonProject/AutoScholar/paper/paper.tex)
- [claim_recommended_citations.md](/d:/pythonProject/AutoScholar/paper/claim_recommended_citations.md)
- [references.bib](/d:/pythonProject/AutoScholar/paper/references.bib)

### Agent responsibilities

- insert citations only where a sentence genuinely depends on prior literature
- prefer 2 to 3 strong references over a long weak list
- prioritize introduction, conceptual framing, method justification, case comparison, and discussion claims
- preserve sentence meaning while inserting citations
- avoid blind search-and-replace behavior

### Working rule

Do not cite every sentence.

### Output

- updated [paper.tex](/d:/pythonProject/AutoScholar/paper/paper.tex)


## Step 11: Run a Post-Insertion Quality Check

### Goal

Make sure citation insertion did not damage the manuscript.

### Agent responsibilities

- verify that every `\cite{...}` key exists in [references.bib](/d:/pythonProject/AutoScholar/paper/references.bib)
- ensure citations do not appear in pure result-reporting sentences unless clearly justified
- ensure no Semantic Scholar URLs remain as final citation metadata
- inspect insertion hotspots manually
- remove or replace broken entries when bibliography encoding is unsafe

### Required checks

- count `\cite{...}` occurrences
- compare used citekeys against bibliography keys
- inspect suspicious or dense citation zones manually
- confirm bibliography and manuscript remain compatible with the current compile path


## Loop Rules

### Query rewrite loop

Go back to Step 3 when:

- prescreen shows the query set is fundamentally wrong
- recommendation expansion cannot find trustworthy seeds
- the same off-topic cluster keeps dominating retrieval

### Recommendation loop

Repeat Step 7 when:

- the seeds are good but the expanded set still looks incomplete
- the first recommendation round surfaced a better seed for a second round
- the evidence pool is improving materially across rounds

Stop recommendation looping when:

- the evidence pool has stabilized
- the marginal gain from another round is too small
- the real problem is query design, not local neighborhood expansion


## Minimal Reusable Workflow

For a new paper, the minimal repeatable workflow is:

1. create `paper/paper.tex`
2. extract claim units into `paper/citation_claim_units.md`
3. prepare queries in `paper/search_keyword_prep.md`
4. configure `paper/semantic_scholar_search.yaml`
5. run `python scripts\batch_semantic_scholar_search.py`
6. run `python scripts\dedupe_and_prescreen_semantic_scholar.py`
7. let the agent decide whether recommendation expansion is warranted
8. run `python scripts\recommendation_auto_correct.py` when warranted
9. rerun recommendation expansion or rewrite queries if needed
10. run `python scripts\generate_claim_recommendation_list.py`
11. run `python scripts\generate_references_bib.py`
12. insert `\cite{...}` manually into `paper/paper.tex`
13. run citation integrity checks
14. compile in the cloud if no local TeX environment exists


## Quality Standard

Good agent behavior:

- claim-level judgment instead of mechanical citation stuffing
- strong and relevant seeds before recommendation expansion
- willingness to rewrite queries when expansion is the wrong tool
- explicit separation between usable evidence and noisy retrieval
- final bibliography generation only after evidence review

Bad agent behavior:

- searching before understanding the manuscript
- trusting recommendation outputs without seed review
- forcing multiple recommendation rounds when the query is obviously wrong
- carrying aggregator artifacts into the final bibliography
- citing low-fit literature because it happens to share a keyword


## Compilation Notes

The compile order below assumes a `natbib` + `bibtex` manuscript setup.

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
