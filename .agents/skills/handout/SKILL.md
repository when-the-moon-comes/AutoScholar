---
name: handout
description: Use when the user wants an evidence-grounded research handout for a domain, especially a layered handout at terminology, landscape, or tension depth. Trigger for requests to enter a new research field, generate domain lecture notes, build a three-layer briefing, produce interactive study questions, or create completion tests using AutoScholar Semantic Scholar retrieval.
---

# Handout

Use this skill to create layered research handouts from Semantic Scholar evidence.

## Levels

- `terminology`: 第 1 层，术语骨架。Produce 20-40 core concepts, precise definitions, and close-term distinctions. Do not write representative-work surveys or timelines.
- `landscape`: 第 2 层，地貌图。Produce 3-5 method families, benchmark/metric environment, nonlinear 5-8 year timeline, and representative people/labs.
- `tension`: 第 3 层，张力地图。Produce open disputes, claimed-vs-actual progress gaps, abandoned directions, and unstated community problems. Add confidence to every judgment.

## Workflow

1. Ask for or infer the domain and level. If the user says only “讲义” and gives no level, default to `landscape`.
2. Run checkpointed retrieval:

```powershell
autoscholar handout init "<domain>" --level <terminology|landscape|tension>
```

Use `--output-dir <dir>` when the user wants a specific workspace. By default, handout retrieval runs checkpoint rounds until every query completes. Successful Semantic Scholar queries are stored in `artifacts/semantic_results.jsonl` and failures in `artifacts/semantic_failures.jsonl`, so re-running the same command after interruption resumes from the checkpoints.

For rate limits, slow the run rather than deleting artifacts:

```powershell
autoscholar handout init "<domain>" --level landscape --max-queries 1 --round-delay 300
```

Use `--single-pass` to do only one checkpoint pass. Use `--max-rounds <n>` to cap one command invocation while keeping checkpoints reusable.

3. Read the generated `reports/handout.md`.
4. Synthesize the final handout from the evidence pool. Keep the selected level explicit and do not blend all three levels into a generic survey.
5. Include an interaction section and a completion-test section in the final output.

## Level Rules

For `terminology`:

- Length target: 2000-4000 Chinese characters.
- Center the handout on distinctions, not definitions alone.
- Include a close-term matrix where misuse would change paper interpretation.
- Completion test: the reader can understand an arbitrary abstract without searching terms.

For `landscape`:

- Length target: 5000-10000 Chinese characters.
- Select 30-50 references at most; do not list everything.
- Organize by method family, evaluation setup, nonlinear timeline, and people/labs.
- Completion test: the reader can follow about 70% of a domain talk and place a new paper in a family.

For `tension`:

- Length target: 4000-8000 Chinese characters.
- Require the user to have 2-3 existing discomforts with the field. If they do not, recommend running `landscape` first.
- Treat the output as candidates for judgment, not a textbook.
- Include confidence labels for each dispute or unstated problem.
- Completion test: the reader can predict how the community would split on a new submission.

## Working Rules

- Prefer the `autoscholar handout init` command over ad hoc Semantic Scholar calls.
- Treat `queries.jsonl`, `artifacts/semantic_results.jsonl`, and `artifacts/semantic_failures.jsonl` as source artifacts.
- Treat `reports/handout.md` as an evidence-backed draft packet. The agent should still perform judgment and synthesis before presenting the final handout.
- If retrieval is weak, expand or rewrite queries and rerun before making strong claims.
- For tension maps, avoid popularity-only ranking. Low-citation recent work, failure analyses, and benchmark critiques may be more informative than famous surveys.
