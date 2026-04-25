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
from autoscholar.integrations import SemanticScholarClient


@dataclass(frozen=True)
class SemanticQuery:
    query_id: str
    query_text: str


@dataclass(frozen=True)
class SemanticCrawlConfig:
    output: Path
    failures: Path
    endpoint: str = "relevance"
    limit: int = 10
    fields: str = "paperId,title,year,authors,url,abstract,citationCount,venue"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 30.0
    pause_seconds: float = 1.0
    retry_failed: bool = True
    max_queries: int | None = None
    year: str | None = None
    sort: str | None = None
    venue: str | None = None

    def search_signature(self) -> str:
        payload = {
            "endpoint": self.endpoint,
            "limit": self.limit,
            "fields": self.fields,
            "year": self.year,
            "sort": self.sort,
            "venue": self.venue,
        }
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def query_id_for_text(query_text: str) -> str:
    digest = hashlib.sha1(query_text.strip().encode("utf-8")).hexdigest()[:12]
    return f"q_{digest}"


def normalize_queries(queries: Iterable[str | dict[str, Any]]) -> list[SemanticQuery]:
    normalized: list[SemanticQuery] = []
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
        normalized.append(SemanticQuery(query_id=query_id, query_text=query_text))
    return normalized


def load_queries_file(path: Path) -> list[SemanticQuery]:
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


def load_jsonl_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            query_id = record.get("query_id")
            if query_id:
                records[str(query_id)] = record
    return records


def write_jsonl_records(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def is_retryable_httpx_error(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        return status == 429 or (status is not None and 500 <= status < 600)
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def retry_sleep_seconds(exc: httpx.HTTPError, retry_delay: float, attempt: int) -> float:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        retry_after = exc.response.headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
    return max(0.0, retry_delay * attempt)


def fetch_query(
    client: SemanticScholarClient,
    query: SemanticQuery,
    config: SemanticCrawlConfig,
) -> dict[str, Any]:
    if config.endpoint == "bulk":
        papers = list(
            client.search_papers_bulk(
                query=query.query_text,
                fields=config.fields,
                max_results=config.limit,
                timeout=config.timeout,
                year=config.year,
                sort=config.sort,
                venue=config.venue,
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
    )
    papers = payload.get("data", [])
    return {
        "endpoint": "relevance",
        "total_hits": payload.get("total"),
        "paper_count": len(papers),
        "papers": papers,
    }


def run_query_with_retries(
    query: SemanticQuery,
    config: SemanticCrawlConfig,
    client_factory: Callable[[], SemanticScholarClient],
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
        "endpoint": config.endpoint,
        "search_signature": config.search_signature(),
        "attempts": attempt,
        "status_code": status_code,
        "retryable": is_retryable_httpx_error(last_error) if last_error else False,
        "error_type": last_error.__class__.__name__ if last_error else "UnknownError",
        "error": str(last_error) if last_error else "Unknown error",
        "failed_at": utc_now(),
    }


def crawl_semantic_queries(
    queries: list[SemanticQuery],
    config: SemanticCrawlConfig,
    client_factory: Callable[[], SemanticScholarClient] | None = None,
) -> dict[str, int]:
    if config.endpoint not in {"relevance", "bulk"}:
        raise ValueError("endpoint must be 'relevance' or 'bulk'.")
    if config.limit < 1:
        raise ValueError("limit must be >= 1.")
    if config.max_retries < 1:
        raise ValueError("max_retries must be >= 1.")

    client_factory = client_factory or (lambda: SemanticScholarClient(timeout=config.timeout))
    signature = config.search_signature()
    results = load_jsonl_records(config.output)
    failures = load_jsonl_records(config.failures)

    completed_ids = {
        query_id
        for query_id, record in results.items()
        if record.get("status") == "ok" and record.get("search_signature") == signature
    }
    pending = []
    for query in queries:
        if query.query_id in completed_ids:
            continue
        if not config.retry_failed and query.query_id in failures:
            continue
        pending.append(query)

    if config.max_queries is not None:
        pending = pending[: config.max_queries]

    success_count = 0
    failure_count = 0
    skipped_count = len(queries) - len(pending)
    processed_count = 0

    ordered_ids = [query.query_id for query in queries]
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
            f"[{index}/{len(pending)}] {record['status']} "
            f"{query.query_id}: {query.query_text}"
        )
        if ok and config.pause_seconds > 0 and index < len(pending):
            time.sleep(config.pause_seconds)

    return {
        "total": len(queries),
        "processed": processed_count,
        "skipped": skipped_count,
        "success": success_count,
        "failure": failure_count,
        "stored_success": len(results),
        "stored_failure": len(failures),
    }
