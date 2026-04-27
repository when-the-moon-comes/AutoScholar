from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from autoscholar.citation.common import utc_now
from autoscholar.integrations import OpenAlexClient
from autoscholar.integrations.openalex import DEFAULT_WORK_SELECT
from autoscholar.semantic_crawl import (
    is_retryable_httpx_error,
    load_jsonl_records,
    retry_sleep_seconds,
    write_jsonl_records,
)


@dataclass(frozen=True)
class OpenAlexQuery:
    query_id: str
    query_text: str


@dataclass(frozen=True)
class OpenAlexCrawlConfig:
    output: Path
    failures: Path
    endpoint: str = "works"
    limit: int = 10
    fields: str = DEFAULT_WORK_SELECT
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 30.0
    pause_seconds: float = 1.0
    retry_failed: bool = True
    max_queries: int | None = None
    until_complete: bool = False
    round_delay: float = 300.0
    max_rounds: int | None = None
    filters: str | None = None
    sort: str | None = None

    def normalized_endpoint(self) -> str:
        mapping = {
            "works": "works",
            "search": "works",
            "relevance": "works",
            "bulk": "bulk",
            "cursor": "bulk",
        }
        return mapping.get(self.endpoint, self.endpoint)

    def search_signature(self) -> str:
        payload = {
            "endpoint": self.normalized_endpoint(),
            "limit": self.limit,
            "fields": self.fields,
            "filters": self.filters,
            "sort": self.sort,
        }
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def query_id_for_text(query_text: str) -> str:
    digest = hashlib.sha1(query_text.strip().encode("utf-8")).hexdigest()[:12]
    return f"q_{digest}"


def normalize_queries(queries: Iterable[str | dict[str, Any]]) -> list[OpenAlexQuery]:
    normalized: list[OpenAlexQuery] = []
    seen: set[str] = set()
    for index, raw_query in enumerate(queries, start=1):
        if isinstance(raw_query, str):
            query_text = raw_query.strip()
            query_id = query_id_for_text(query_text)
        elif isinstance(raw_query, dict):
            query_text = str(
                raw_query.get("query")
                or raw_query.get("query_text")
                or raw_query.get("text")
                or ""
            ).strip()
            query_id = str(
                raw_query.get("query_id")
                or raw_query.get("id")
                or query_id_for_text(query_text)
            ).strip()
        else:
            raise ValueError(f"Unsupported query item at index {index}: {raw_query!r}")

        if not query_text:
            continue
        if query_id in seen:
            raise ValueError(f"Duplicate query_id: {query_id}")
        seen.add(query_id)
        normalized.append(OpenAlexQuery(query_id=query_id, query_text=query_text))
    return normalized


def load_queries_file(path: Path) -> list[OpenAlexQuery]:
    if not path.exists():
        raise FileNotFoundError(f"Queries file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("queries", [])
        if not isinstance(payload, list):
            raise ValueError("JSON query file must be a list or contain a 'queries' list.")
        return normalize_queries(payload)

    if path.suffix.lower() == ".jsonl":
        items = [json.loads(line) for line in text.splitlines() if line.strip()]
        return normalize_queries(items)

    return normalize_queries(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def fetch_query(
    client: OpenAlexClient,
    query: OpenAlexQuery,
    config: OpenAlexCrawlConfig,
) -> dict[str, Any]:
    endpoint = config.normalized_endpoint()
    if endpoint == "bulk":
        papers = list(
            client.search_papers_bulk(
                query=query.query_text,
                fields=config.fields,
                max_results=config.limit,
                timeout=config.timeout,
                filters=config.filters,
                sort=config.sort,
            )
        )
        return {
            "endpoint": "bulk",
            "total_hits": None,
            "paper_count": len(papers),
            "papers": papers,
        }

    payload = client.search_papers(
        query=query.query_text,
        limit=config.limit,
        fields=config.fields,
        timeout=config.timeout,
        filters=config.filters,
        sort=config.sort,
    )
    papers = payload.get("data", [])
    return {
        "endpoint": "works",
        "total_hits": payload.get("total"),
        "paper_count": len(papers),
        "papers": papers,
    }


def run_query_with_retries(
    query: OpenAlexQuery,
    config: OpenAlexCrawlConfig,
    client_factory: Callable[[], OpenAlexClient],
) -> tuple[bool, dict[str, Any]]:
    attempt = 0
    last_error: httpx.HTTPError | None = None
    while attempt < config.max_retries:
        attempt += 1
        with client_factory() as client:
            try:
                result = fetch_query(client, query, config)
                return True, {
                    "status": "ok",
                    "query_id": query.query_id,
                    "query_text": query.query_text,
                    "endpoint": result["endpoint"],
                    "search_signature": config.search_signature(),
                    "attempts": attempt,
                    "total_hits": result["total_hits"],
                    "paper_count": result["paper_count"],
                    "papers": result["papers"],
                    "retrieved_at": utc_now(),
                }
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < config.max_retries and is_retryable_httpx_error(exc):
                    time.sleep(retry_sleep_seconds(exc, config.retry_delay, attempt))
                    continue
                break

    status_code = None
    if isinstance(last_error, httpx.HTTPStatusError) and last_error.response is not None:
        status_code = last_error.response.status_code
    return False, {
        "status": "failed",
        "query_id": query.query_id,
        "query_text": query.query_text,
        "endpoint": config.normalized_endpoint(),
        "search_signature": config.search_signature(),
        "attempts": attempt,
        "status_code": status_code,
        "retryable": is_retryable_httpx_error(last_error) if last_error else False,
        "error_type": last_error.__class__.__name__ if last_error else "UnknownError",
        "error": str(last_error) if last_error else "Unknown error",
        "failed_at": utc_now(),
    }


def crawl_openalex_queries(
    queries: list[OpenAlexQuery],
    config: OpenAlexCrawlConfig,
    client_factory: Callable[[], OpenAlexClient] | None = None,
) -> dict[str, int | bool]:
    if config.normalized_endpoint() not in {"works", "bulk"}:
        raise ValueError("endpoint must be 'works', 'search', 'relevance', or 'bulk'.")
    if config.limit < 1:
        raise ValueError("limit must be >= 1.")
    if config.max_retries < 1:
        raise ValueError("max_retries must be >= 1.")
    if config.max_queries is not None and config.max_queries < 1:
        raise ValueError("max_queries must be >= 1.")
    if config.max_rounds is not None and config.max_rounds < 1:
        raise ValueError("max_rounds must be >= 1.")

    client_factory = client_factory or (lambda: OpenAlexClient(timeout=config.timeout))
    signature = config.search_signature()
    results = load_jsonl_records(config.output)
    failures = load_jsonl_records(config.failures)

    def completed_query_ids() -> set[str]:
        return {
            query_id
            for query_id, record in results.items()
            if record.get("status") == "ok" and record.get("search_signature") == signature
        }

    def pending_queries() -> list[OpenAlexQuery]:
        completed_ids = completed_query_ids()
        pending = []
        for query in queries:
            if query.query_id in completed_ids:
                continue
            if not config.retry_failed and query.query_id in failures:
                continue
            pending.append(query)
        if config.max_queries is not None:
            pending = pending[: config.max_queries]
        return pending

    success_count = 0
    failure_count = 0
    skipped_count = len([query for query in queries if query.query_id in completed_query_ids()])
    processed_count = 0
    round_count = 0
    max_rounds_reached = False

    ordered_ids = [query.query_id for query in queries]
    while True:
        pending = pending_queries()
        if not pending:
            break
        if config.max_rounds is not None and round_count >= config.max_rounds:
            max_rounds_reached = True
            break

        round_count += 1
        for index, query in enumerate(pending, start=1):
            ok, record = run_query_with_retries(query, config, client_factory)
            processed_count += 1
            if ok:
                results[query.query_id] = record
                failures.pop(query.query_id, None)
                success_count += 1
            else:
                failures[query.query_id] = record
                failure_count += 1

            write_jsonl_records(config.output, [results[item] for item in ordered_ids if item in results])
            write_jsonl_records(config.failures, [failures[item] for item in ordered_ids if item in failures])

            print(
                f"[round {round_count} {index}/{len(pending)}] {record['status']} "
                f"{query.query_id}: {query.query_text}"
            )
            if config.pause_seconds > 0 and index < len(pending):
                time.sleep(config.pause_seconds)

        if len(completed_query_ids()) == len(queries):
            break
        if not config.until_complete:
            break
        if config.max_rounds is not None and round_count >= config.max_rounds:
            max_rounds_reached = True
            break
        if config.round_delay > 0:
            remaining = len(queries) - len(completed_query_ids())
            print(f"Waiting {config.round_delay:.0f}s before next checkpoint round. remaining={remaining}")
            time.sleep(config.round_delay)

    final_completed_ids = completed_query_ids()
    completed_count = len([query for query in queries if query.query_id in final_completed_ids])
    remaining_count = len(queries) - completed_count

    return {
        "total": len(queries),
        "processed": processed_count,
        "skipped": skipped_count,
        "success": success_count,
        "failure": failure_count,
        "completed": completed_count,
        "remaining": remaining_count,
        "complete": remaining_count == 0,
        "rounds": round_count,
        "until_complete": config.until_complete,
        "max_rounds_reached": max_rounds_reached,
        "stored_success": len(results),
        "stored_failure": len(failures),
    }
