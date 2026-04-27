---
name: openalex-api
description: Use when the user needs low-level OpenAlex API operations inside AutoScholar, such as work lookup, search, related works, citations, references, author inspection, checkpointed crawling, or replacing Semantic Scholar lookup flows with OpenAlex.
---

# OpenAlex API

Use this skill when the task is lower-level than the full AutoScholar workflow and should use OpenAlex rather than Semantic Scholar.

## Use Cases

- inspect one OpenAlex work or author directly
- debug OpenAlex search behavior
- inspect related works, citations, and references
- fetch raw or normalized metadata before it enters a workspace workflow
- run checkpointed query crawls against OpenAlex
- provide an OpenAlex replacement for `semantic-scholar-api` lookups

## Implementation Surface

The client lives in `src/autoscholar/integrations/openalex.py`.

It supports:

- work lookup, exposed as `get_work` and Semantic-like `get_paper`
- work search and cursor-based bulk search
- related works as recommendation-like output
- citations and references
- author search, author lookup, and author works
- open-access PDF download when OpenAlex exposes a PDF URL

Compatibility imports live in `scripts/openalex/`.

## CLI Surface

Use the `autoscholar openalex` command group for direct inspection and debugging:

- `autoscholar openalex paper <work_id>`
- `autoscholar openalex search <query>`
- `autoscholar openalex recommend <work_id>`
- `autoscholar openalex citations <work_id>`
- `autoscholar openalex references <work_id>`
- `autoscholar openalex author-search <query>`
- `autoscholar openalex author <author_id>`
- `autoscholar openalex author-papers <author_id>`
- `autoscholar openalex download-pdf <work_id>`
- `autoscholar openalex crawl --query <query>` for checkpointed multi-run search
- `autoscholar openalex smoke`

## Resumable Crawling

Use `autoscholar openalex crawl` when a search may hit rate limits or needs to be split across runs.

Examples:

```powershell
autoscholar openalex crawl --query "retrieval augmented generation" --query "graph RAG" --limit 5 --max-retries 1
autoscholar openalex crawl --queries-file paper/openalex_queries.txt --output paper/openalex_crawl_results.jsonl --failures paper/openalex_crawl_failures.jsonl --limit 10 --max-queries 3
```

The command writes successes and failures after every query. Re-running the same command skips successful queries and retries failed or unfinished ones by default.

## Notes

- The client reads `OPENALEX_API_KEY` when present and sends it as the `api_key` query parameter.
- Do not hardcode API keys in scripts or skill files.
- Use `--fields` to pass an OpenAlex `select` list and keep responses small.
- OpenAlex has no Semantic Scholar recommendations endpoint; `recommend` returns the work's `related_works`.
- `autoscholar openalex smoke` skips cleanly when `OPENALEX_API_KEY` is unset.
