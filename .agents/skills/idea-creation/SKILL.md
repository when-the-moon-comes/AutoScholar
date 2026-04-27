---
name: idea-creation
description: "Generate structured CS or AI research ideas from a seed paper by running two parallel tracks: Context Substitution (break deployment assumptions) and Insight Transfer (extract and transfer the paper's real insight). Produce dual-track idea cards, convergence signals, and novelty verification using the local AutoScholar Semantic Scholar API client. Use when a user wants seed-paper-based ideation, paradigm-shift brainstorming, or novelty-checked paper concepts without changing the paper-search backend."
---

# Idea Creation

## Overview

Run two independent idea-generation tracks and merge them into one candidate set:

- `Track A / Context Substitution`: break the seed paper's deployment assumptions
- `Track B / Insight Transfer`: extract the seed paper's real intellectual discovery and test where that principle transfers

Use both tracks. Do not reduce Track B to "apply method X to domain Y."

## Workflow

1. Create `paper/` if it does not exist.
2. Save the seed input to `paper/seed_paper.md`.
3. If the source is a PDF, run the repository helper at `scripts/pdf_to_text.py` first.
4. Read `references/file-contracts.md` before writing any outputs.
5. Produce `paper/parsed_paper.json`.
6. Produce `paper/core_insights.json` for Track B.
7. Produce `paper/assumptions.json` for Track A.
8. Produce `paper/paradigm_gap_check.json` and backfill any meaningful missing assumptions.
9. Produce `paper/innovation_candidates.json` with `track_a_candidates` and `track_b_candidates`.
10. Mark `convergence_with` when both tracks independently land on the same target domain.
11. Run `python .agents/skills/idea-creation/scripts/verify_novelty.py`.
12. Produce `paper/idea_cards.md` with track labels, a surfaced-paper-links section on every card, and one machine-readable AutoScholar handoff block per card.

## Track Rules

- Track A should stay close to the seed paper's territory and create new problems by changing deployment or data assumptions.
- Track B should start from what the paper actually discovered, especially counter-intuitive findings and non-obvious design choices.
- Reject Track B candidates when the transfer prerequisites do not truly hold.
- Treat convergence as a strong signal. If a Track A and Track B candidate independently target the same domain, surface that explicitly.

## Search Rule

Use the repository-local Semantic Scholar client through this script:

```powershell
python .agents\skills\idea-creation\scripts\verify_novelty.py
```

The script imports `SemanticScholarApi/api.py`. Do not add OpenAlex, Crossref, Google Scholar scraping, or another search backend unless the user explicitly asks for it.

For Track B:

- provide `principle_level_search_queries`
- evaluate both task-level and principle-level sparsity
- allow a Track B candidate to survive even when the target task is crowded, as long as the principle transfer remains sparse

## Quality Bar

- Extract at least 2 core insights and 1 counter-intuitive design choice.
- Mine at least 8 assumptions. If you find fewer than 6, keep digging.
- Check all 9 paradigm axes.
- Make every Track B card state exactly why the transfer prerequisites hold.
- Run novelty verification for every candidate instead of guessing sparsity.
- Attach surfaced paper links from Semantic Scholar to every final card.
- Exclude or clearly deprioritize `LOW`-sparsity candidates.
- Include a convergence section when any Track A and Track B pair share a target domain.
- Include a summary table at the end of `paper/idea_cards.md`.

## Output Discipline

Read exact file contracts from `references/file-contracts.md`.

Prefer these output states:

- `parsed_paper.json`: precise and specific
- `core_insights.json`: intellectually substantive
- `assumptions.json`: broad and explicit
- `innovation_candidates.json`: dual-track, pruned, and convergence-aware
- `novelty_verification.json`: evidence-backed and track-aware
- `idea_cards.md`: ready to reuse as paper-motivation drafts
