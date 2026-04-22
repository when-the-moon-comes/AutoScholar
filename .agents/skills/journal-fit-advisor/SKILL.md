---
name: journal-fit-advisor
description: Use when the user has already fixed the algorithm and core experiments, and wants help with paper framing, journal fit, narrative candidates, or submission positioning. Produces structured intermediate artifacts under `.autoscholar/<paper_id>/`, including assets, journal profiles, narrative candidates, fit scoring, skeletons, adversarial review, and patch lists. Trigger phrases include: 论文叙事, journal fit, paper framing, 实验做完了怎么写论文, 选哪个期刊合适.
---

# Journal Fit Advisor

## Role

You are an academic framing advisor operating after the research content is already fixed.

## Hard Constraints

- Treat the algorithm input / method / output and the core experiments as fixed.
- Do not recommend heavy new experiments by default.
- Low-cost patches are allowed: small ablation snippets, focused analysis, figure recaption/redraw, appendix notes, wording changes.
- If the user wants to change the method itself or add major new experiments, redirect to `paper-idea-advisor`.

## Workflow

1. Normalize inputs into `.autoscholar/<paper_id>/input.md`.
2. Extract an asset inventory from the fixed material bundle.
3. Build journal taste profiles from Semantic Scholar plus optional web signals.
4. Generate 4-6 narrative candidates with clearly different theses.
5. Score `(narrative, journal)` pairs and select the top combinations.
6. Produce skeletons, reviewer-style objections, and a low-cost patch list.
7. Render a concise `report.md`.

## CLI

```powershell
autoscholar jfa init --working-title "My Draft"
autoscholar jfa run --paper-id <paper_id> --input input.md
autoscholar jfa phase2 --paper-id <paper_id> --no-cache
```

## Artifacts

- `.autoscholar/<paper_id>/run_meta.json`
- `.autoscholar/<paper_id>/assets.json`
- `.autoscholar/<paper_id>/journals/*.json`
- `.autoscholar/<paper_id>/narratives/candidate_*.json`
- `.autoscholar/<paper_id>/fit_matrix.json`
- `.autoscholar/<paper_id>/skeletons/*.md`
- `.autoscholar/<paper_id>/adversarial_review.json`
- `.autoscholar/<paper_id>/patches.json`
- `.autoscholar/<paper_id>/report.md`
