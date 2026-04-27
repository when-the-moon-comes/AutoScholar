---
name: triggered-push
description: |
  Use when the user is at the "zero to fuzzy idea" stage and wants to
  scan a research domain not as a survey but as a search for materials
  that produce a personal reaction (boring / want-to-argue / unsure)
  against their existing research DNA. Surfaces 5-10 curated cards in
  one of four paradigms — Controversy Map, Failure Archive,
  Method×Scenario Matrix, Cross-Domain Pairs — and rolls the user's
  reactions into a persistent DNA profile that sharpens later runs.
  Trigger phrases include: 模糊 idea, 找研究方向, 没灵感, 领域扫描,
  研究品味, 跨领域同构, 争论地图, 失败档案, 方法场景矩阵, 触发式推送,
  controversy map, failure archive, cross domain pair, research dna scan,
  fuzzy idea generation.
---

# Triggered-Push

This skill is the **"zero-to-fuzzy-idea"** companion to AutoScholar.
It does not produce a literature shortlist or a feasibility report.
It produces *triggers* — small, deliberately diverse cards designed
to provoke the user's reaction, because reactions (not summaries)
are what generate ideas at this stage.

## Role split, non-negotiable

- **AI** surfaces materials. Not the most relevant ones, not the
  most cited ones. The ones with the highest expected reaction rate
  given the user's DNA profile.
- **The user** reacts. Bored, wants-to-argue, unsure. The reaction is
  captured in the workspace. AI does not produce ideas for the user.

If the user asks AI to "just give me an idea", redirect: this skill
generates *cards*, not ideas. For idea generation from a seed paper, use
`idea-creation`.

## When NOT to use this skill

- User already has a concrete idea → `idea-creation`.
- User wants a structured study guide for a new field → `handout`.
- User wants to evaluate a specific direction → `idea-evaluation`.
- User wants help picking a journal → `journal-fit-advisor`.

## Paradigms — pick exactly one per run

| Paradigm | What it surfaces | When to pick |
| --- | --- | --- |
| `controversy` | 5-8 live disputes researchers fight about | User has a sense of the field but no foothold. |
| `failure-archive` | 5-10 once-promising, now-cold directions | User suspects "the consensus is wrong" but not where. |
| `matrix` | method × scenario grid with empty cells annotated | User is comfortable with β-type ideas (composition). |
| `cross-domain` | 5-8 pairs of structurally isomorphic papers | User is comfortable with α-type ideas (transfer). |

Combining paradigms in one run drowns the user. Run them sequentially
and let `relay` carry a positive reaction forward.

## Hard rules across all paradigms

1. **Diversity, not ranking.** Every card must occupy a distinct axis
   relative to the other cards. AI assigns each card a
   `ai_diversity_axis` field at synthesis time. If two cards share
   an axis, drop one and resample.
2. **Reactions must be captured.** Use `autoscholar trigger react` after
   the user reads the report. For positive reactions
   (`want_to_argue` / `curious` / `partial` / `changed`), the `--take`
   field is mandatory and validates non-empty server-side.
3. **Boring reactions are kept.** They define the boundary of the user's
   DNA as much as positive ones. Never silently drop them.
4. **DNA input is seed papers + rolling profile, not a domain string.**
   If the user only gave a domain, request 3-5 seed papers before
   running `push`.

## Workflow

1. `autoscholar trigger init <dir> --domain "..."` bootstraps the
   workspace.
2. User fills `inputs/seed_papers.md` (3-5 papers, one-line reason each).
3. `autoscholar trigger push --workspace <dir> --paradigm <name>` runs
   the paradigm-specific crawl + AI synthesis + report rendering.
4. User reads `reports/push_<paradigm>_<run_id>.md`.
5. User captures reactions with `autoscholar trigger react` (one per
   card the user formed an opinion about — including bored ones).
6. Optional: `autoscholar trigger relay --source-card <id>
   --target-paradigm <name>` carries a positive reaction into the next
   paradigm as concentrated DNA input.

## References

Read these before generating a card report:

- `references/dna_profile.md` — rolling window mechanics and trait
  derivation. **Always read first.**
- `references/paradigm_controversy.md` — for `--paradigm controversy`.
- `references/paradigm_failure_archive.md` — for `--paradigm failure-archive`.
- `references/paradigm_matrix.md` — for `--paradigm matrix`.
- `references/paradigm_cross_domain.md` — for `--paradigm cross-domain`.
- `references/file_contracts.md` — schemas for every artifact file.
