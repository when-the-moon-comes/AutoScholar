---
name: idea-creation
description: Generate assumption-driven CS or AI research ideas from a seed paper, produce structured idea cards, and verify novelty with the local AutoScholar Semantic Scholar API client. Use when a user wants seed-paper-based ideation, assumption mining, paradigm-shift brainstorming, or literature sparsity checks without introducing a new paper search backend.
---

# Idea Creation

## Overview

Turn a seed paper into structured research directions by extracting its current problem framing, mining hidden assumptions, breaking high-value assumptions, and verifying novelty against Semantic Scholar.

Keep the generative steps agentic. Keep the paper-search step inside this repository's existing Semantic Scholar integration.

## Workflow

1. Create `paper/` if it does not exist.
2. Save the seed input to `paper/seed_paper.md`.
3. If the user starts from PDF, run the repository helper at `scripts/pdf_to_text.py` first, then copy the relevant text into `paper/seed_paper.md`.
4. Read `references/file-contracts.md` before writing any outputs.
5. Produce `paper/parsed_paper.json`.
6. Produce `paper/assumptions.json`.
7. Produce `paper/paradigm_gap_check.json`. If this reveals a meaningful missing assumption, append it to `paper/assumptions.json` before continuing.
8. Produce `paper/innovation_candidates.json`.
9. Run `python .agents/skills/idea-creation/scripts/verify_novelty.py` for novelty verification. This is the default Step 5 path because it reuses `SemanticScholarApi/api.py`.
10. Produce `paper/idea_cards.md` using only `HIGH` candidates and manually justified `MEDIUM` candidates.
11. Present `paper/idea_cards.md` and explain how the outputs can flow into the existing AutoScholar citation pipeline.

## Search Rule

Use the repository-local Semantic Scholar client for novelty verification:

```powershell
python .agents\skills\idea-creation\scripts\verify_novelty.py
```

Do not add OpenAlex, Crossref, Google Scholar scraping, or another paper-search wrapper unless the user explicitly asks to change the backend.

When the user wants deeper follow-up literature work, feed these outputs into the existing AutoScholar workflow:

- `candidate_title` -> seed wording for `search_keyword_prep.md`
- `novelty_search_queries` -> initial query set
- `top_existing_papers` -> seed candidates for `recommendation_auto_correct.py`

## Quality Bar

- Mine at least 8 assumptions. If you find fewer than 6, keep digging.
- Check all 9 paradigm axes.
- Make each candidate domain-grounded, not just algorithmically fashionable.
- Run novelty verification instead of guessing sparsity.
- Exclude or clearly deprioritize `LOW`-sparsity candidates.
- Include a summary table in `paper/idea_cards.md`.

## Output Discipline

Read exact file contracts from `references/file-contracts.md`.

Prefer these output states:

- `parsed_paper.json`: tight and concrete
- `assumptions.json`: broad and explicit
- `innovation_candidates.json`: pruned to coherent research problems
- `novelty_verification.json`: evidence-backed, not speculative
- `idea_cards.md`: readable enough to reuse as paper-motivation drafts
