# File Contracts

Authoritative schemas for every file in a `triggered-push` workspace.
Read this before writing any artifact.

## Workspace layout

```
<workspace>/
  triggered-push.yaml
  inputs/
    seed_papers.md
    scope.yaml
  artifacts/
    dna_profile.json
    reactions.jsonl
    semantic_results.jsonl
    semantic_failures.jsonl
    controversy_cards.jsonl     # only if controversy was run
    failure_archive.jsonl       # only if failure-archive was run
    matrix.json                 # only if matrix was run
    cross_domain_pairs.jsonl    # only if cross-domain was run
  reports/
    push_<paradigm>_<run_id>.md
```

## triggered-push.yaml

```yaml
schema_version: "1"
domain: "string; the user's stated domain"
created_at: "ISO-8601"
defaults:
  rolling_window:
    max_count: 30
    max_age_days: 90
  matrix:
    max_queries_per_run: 32
  crawl:
    pause_seconds: 1.0
    max_retries: 3
    until_complete: true
artifacts:
  dna_profile: artifacts/dna_profile.json
  reactions: artifacts/reactions.jsonl
  semantic_results: artifacts/semantic_results.jsonl
  semantic_failures: artifacts/semantic_failures.jsonl
  controversy_cards: artifacts/controversy_cards.jsonl
  failure_archive: artifacts/failure_archive.jsonl
  matrix: artifacts/matrix.json
  cross_domain_pairs: artifacts/cross_domain_pairs.jsonl
reports_dir: reports
```

## inputs/seed_papers.md

Free-form Markdown with one section per paper. The init command
writes this template; the user fills it before running `push`.

```markdown
# Seed Papers

Paste 3-5 papers that represent your research DNA. For each, write
ONE LINE about what you like or dislike about it. Don't write a
summary; write a reaction.

## Paper 1
- title: <title>
- paper_id: <semantic scholar paper id, optional but speeds up retrieval>
- year: <year>
- user_note: <one line, what you reacted to in this paper>

## Paper 2
...
```

The skill's parser expects each paper block to have `title:` and
`user_note:`; `paper_id:` and `year:` are optional. If `paper_id` is
missing, the skill resolves the paper via Semantic Scholar relevance
search before running.

## inputs/scope.yaml

```yaml
schema_version: "1"
domain: "string"
home_field: "string; one of Semantic Scholar fieldsOfStudy values"
foreign_fields_allowed: ["Biology", "Physics", "Psychology", "Economics", "Linguistics"]
home_vocabulary: ["domain-specific term to filter against in cross-domain"]
non_standard_scenarios_hint: ["optional user-suggested scenarios for matrix"]
```

`foreign_fields_allowed` and `non_standard_scenarios_hint` are
optional. If absent, sensible defaults apply.

## artifacts/dna_profile.json

See `references/dna_profile.md`.

## artifacts/reactions.jsonl

Append-only log. One reaction per line, schema identical to a single
entry in `dna_profile.recent_reactions`. Never trimmed.

## artifacts/semantic_results.jsonl and semantic_failures.jsonl

Direct outputs of `crawl_semantic_queries`. Schema is whatever your
existing `semantic_crawl` module writes. Treat as opaque, do not
reformat.

## Paradigm-specific files

- `controversy_cards.jsonl` — see `references/paradigm_controversy.md`.
- `failure_archive.jsonl` — see `references/paradigm_failure_archive.md`.
- `matrix.json` — see `references/paradigm_matrix.md`.
- `cross_domain_pairs.jsonl` — see `references/paradigm_cross_domain.md`.

## reports/push_<paradigm>_<run_id>.md

Generated from the corresponding artifact. The report is a
**rendered view**, not a source of truth. If a report and an artifact
disagree, the artifact wins. Re-run rendering, do not edit the
report by hand.

Run IDs are an 8-char hash of `(paradigm, generated_at)` so the same
paradigm can be re-run without overwriting prior reports.
