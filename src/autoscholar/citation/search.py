from __future__ import annotations

import concurrent.futures as cf
import time
from collections.abc import Iterable

import httpx

from autoscholar.citation.config import SearchConfig
from autoscholar.citation.common import paper_key, utc_now
from autoscholar.integrations import SemanticScholarClient
from autoscholar.io import read_jsonl, write_jsonl
from autoscholar.models import PaperRecord, QueryRecord, SearchFailureRecord, SearchResultRecord
from autoscholar.workspace import Workspace


def _normalize_paper(raw_paper: dict, rank: int) -> PaperRecord:
    authors = [author.get("name") for author in raw_paper.get("authors", []) if author.get("name")]
    external_ids = raw_paper.get("externalIds") or {}
    open_access_pdf = raw_paper.get("openAccessPdf") or {}
    return PaperRecord(
        rank=rank,
        paper_id=raw_paper.get("paperId"),
        title=raw_paper.get("title") or "Untitled",
        year=raw_paper.get("year"),
        authors=authors,
        venue=raw_paper.get("venue"),
        url=raw_paper.get("url"),
        abstract=raw_paper.get("abstract"),
        citation_count=raw_paper.get("citationCount"),
        influential_citation_count=raw_paper.get("influentialCitationCount"),
        doi=external_ids.get("DOI"),
        external_ids={str(key): str(value) for key, value in external_ids.items()},
        is_open_access=raw_paper.get("isOpenAccess"),
        open_access_pdf_url=open_access_pdf.get("url"),
    )


def _collect_unique_papers(raw_papers: Iterable[dict], limit: int) -> list[PaperRecord]:
    seen: set[str] = set()
    papers: list[PaperRecord] = []
    for raw_paper in raw_papers:
        candidate = _normalize_paper(raw_paper, rank=len(papers) + 1)
        key = paper_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        papers.append(candidate)
        if len(papers) >= limit:
            break
    return papers


def _run_relevance_search(client: SemanticScholarClient, query: QueryRecord, config: SearchConfig) -> SearchResultRecord:
    payload = client.search_papers(
        query=query.query_text,
        limit=config.limit,
        fields=config.fields,
        timeout=config.timeout,
    )
    papers = _collect_unique_papers(payload.get("data", []), config.limit)
    return SearchResultRecord(
        query_id=query.query_id,
        claim_id=query.claim_id,
        query_text=query.query_text,
        short_label=query.short_label,
        endpoint=config.endpoint,
        search_options=config.search_options(),
        attempts=1,
        status_code=200,
        page_count=1,
        total_hits=payload.get("total"),
        paper_count=len(papers),
        papers=papers,
        retrieved_at=utc_now(),
    )


def _run_bulk_search(client: SemanticScholarClient, query: QueryRecord, config: SearchConfig) -> SearchResultRecord:
    papers: list[PaperRecord] = []
    seen: set[str] = set()
    token: str | None = None
    page_count = 0
    total_hits: int | None = None
    while True:
        payload = client.search_papers_bulk_page(
            query=query.query_text,
            fields=config.fields,
            token=token,
            timeout=config.timeout,
            sort=config.filters.sort,
            publication_types=config.filters.publication_types,
            open_access_pdf=config.filters.open_access_pdf,
            min_citation_count=config.filters.min_citation_count,
            publication_date_or_year=config.filters.publication_date_or_year,
            year=config.filters.year,
            venue=config.filters.venue,
            fields_of_study=config.filters.fields_of_study,
        )
        page_count += 1
        if total_hits is None:
            total_hits = payload.get("total")
        for raw_paper in payload.get("data", []):
            candidate = _normalize_paper(raw_paper, rank=len(papers) + 1)
            key = paper_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            papers.append(candidate)
            if len(papers) >= config.limit:
                return SearchResultRecord(
                    query_id=query.query_id,
                    claim_id=query.claim_id,
                    query_text=query.query_text,
                    short_label=query.short_label,
                    endpoint=config.endpoint,
                    search_options=config.search_options(),
                    attempts=1,
                    status_code=200,
                    page_count=page_count,
                    total_hits=total_hits,
                    paper_count=len(papers),
                    papers=papers,
                    retrieved_at=utc_now(),
                )
        token = payload.get("token")
        if not token:
            return SearchResultRecord(
                query_id=query.query_id,
                claim_id=query.claim_id,
                query_text=query.query_text,
                short_label=query.short_label,
                endpoint=config.endpoint,
                search_options=config.search_options(),
                attempts=1,
                status_code=200,
                page_count=page_count,
                total_hits=total_hits,
                paper_count=len(papers),
                papers=papers,
                retrieved_at=utc_now(),
            )


def _execute_query(query: QueryRecord, config: SearchConfig) -> tuple[bool, SearchResultRecord | SearchFailureRecord]:
    profile = config.profile()
    attempt = 0
    with SemanticScholarClient(timeout=config.timeout) as client:
        while attempt < profile.max_retries:
            attempt += 1
            try:
                result = (
                    _run_bulk_search(client, query, config)
                    if config.endpoint == "bulk"
                    else _run_relevance_search(client, query, config)
                )
                return True, result.model_copy(update={"attempts": attempt})
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                retryable = status == 429 or (status is not None and 500 <= status < 600)
                if retryable and attempt < profile.max_retries:
                    time.sleep(profile.retry_delay)
                    continue
                return False, SearchFailureRecord(
                    query_id=query.query_id,
                    claim_id=query.claim_id,
                    query_text=query.query_text,
                    endpoint=config.endpoint,
                    search_options=config.search_options(),
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                    failed_at=utc_now(),
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < profile.max_retries:
                    time.sleep(profile.retry_delay)
                    continue
                return False, SearchFailureRecord(
                    query_id=query.query_id,
                    claim_id=query.claim_id,
                    query_text=query.query_text,
                    endpoint=config.endpoint,
                    search_options=config.search_options(),
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                    failed_at=utc_now(),
                )

    raise RuntimeError(f"Unexpected search control flow for query: {query.query_id}")


def _result_matches_query(query: QueryRecord, record: SearchResultRecord) -> bool:
    return (
        record.query_id == query.query_id
        and record.claim_id == query.claim_id
        and record.query_text == query.query_text
        and record.short_label == query.short_label
    )


def _failure_matches_query(query: QueryRecord, record: SearchFailureRecord) -> bool:
    return (
        record.query_id == query.query_id
        and record.claim_id == query.claim_id
        and record.query_text == query.query_text
    )


def _load_existing_results(
    queries: list[QueryRecord],
    raw_output,
    failures_output,
) -> tuple[dict[str, SearchResultRecord], dict[str, SearchFailureRecord]]:
    by_query = {query.query_id: query for query in queries}

    existing_results: dict[str, SearchResultRecord] = {}
    if raw_output.exists() and raw_output.read_text(encoding="utf-8").strip():
        for record in read_jsonl(raw_output, SearchResultRecord):
            query = by_query.get(record.query_id)
            if query is None or not _result_matches_query(query, record):
                continue
            existing_results[record.query_id] = record

    existing_failures: dict[str, SearchFailureRecord] = {}
    if failures_output.exists() and failures_output.read_text(encoding="utf-8").strip():
        for record in read_jsonl(failures_output, SearchFailureRecord):
            query = by_query.get(record.query_id)
            if query is None or record.query_id in existing_results or not _failure_matches_query(query, record):
                continue
            existing_failures[record.query_id] = record

    return existing_results, existing_failures


def _ordered_results(
    queries: list[QueryRecord],
    results: dict[str, SearchResultRecord],
) -> list[SearchResultRecord]:
    ordered: list[SearchResultRecord] = []
    for query in queries:
        record = results.get(query.query_id)
        if record is not None:
            ordered.append(record)
    return ordered


def _ordered_failures(
    queries: list[QueryRecord],
    failures: dict[str, SearchFailureRecord],
    completed_query_ids: set[str],
) -> list[SearchFailureRecord]:
    ordered: list[SearchFailureRecord] = []
    for query in queries:
        if query.query_id in completed_query_ids:
            continue
        record = failures.get(query.query_id)
        if record is not None:
            ordered.append(record)
    return ordered


def _flush_search_state(
    queries: list[QueryRecord],
    raw_output,
    failures_output,
    results: dict[str, SearchResultRecord],
    failures: dict[str, SearchFailureRecord],
) -> None:
    write_jsonl(raw_output, _ordered_results(queries, results))
    write_jsonl(failures_output, _ordered_failures(queries, failures, set(results)))


def run_search(workspace: Workspace, config: SearchConfig) -> tuple[int, int]:
    queries = read_jsonl(workspace.require_path("artifacts", "queries"), QueryRecord)
    raw_output = workspace.require_path("artifacts", "search_results_raw")
    failures_output = workspace.require_path("artifacts", "search_failures")
    existing_results, existing_failures = _load_existing_results(queries, raw_output, failures_output)
    pending_queries = [query for query in queries if query.query_id not in existing_results]
    profile = config.profile()

    _flush_search_state(queries, raw_output, failures_output, existing_results, existing_failures)

    if not pending_queries:
        return len(existing_results), len(existing_failures)

    if config.mode == "single_thread":
        for index, query in enumerate(pending_queries, start=1):
            success, payload = _execute_query(query, config)
            if success:
                existing_results[query.query_id] = payload
                existing_failures.pop(query.query_id, None)
            else:
                existing_failures[query.query_id] = payload
            _flush_search_state(queries, raw_output, failures_output, existing_results, existing_failures)
            if index < len(pending_queries) and profile.pause_seconds > 0:
                time.sleep(profile.pause_seconds)
        return len(existing_results), len(existing_failures)

    with cf.ThreadPoolExecutor(max_workers=profile.workers) as executor:
        futures = [executor.submit(_execute_query, query, config) for query in pending_queries]
        for future in cf.as_completed(futures):
            success, payload = future.result()
            if success:
                existing_results[payload.query_id] = payload
                existing_failures.pop(payload.query_id, None)
            else:
                existing_failures[payload.query_id] = payload
            _flush_search_state(queries, raw_output, failures_output, existing_results, existing_failures)
    return len(existing_results), len(existing_failures)
