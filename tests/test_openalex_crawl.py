from __future__ import annotations

from pathlib import Path

import httpx

from autoscholar.openalex_crawl import (
    OpenAlexCrawlConfig,
    crawl_openalex_queries,
    load_jsonl_records,
    normalize_queries,
)


class _FakeOpenAlexClient:
    failures: set[str] = set()
    failure_counts: dict[str, int] = {}
    calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def search_papers(
        self,
        query: str,
        limit: int,
        fields: str,
        timeout: float | None = None,
        filters: str | None = None,
        sort: str | None = None,
    ) -> dict:
        del limit, fields, timeout, filters, sort
        self.calls.append(query)
        if self.failure_counts.get(query, 0) > 0:
            self.failure_counts[query] -= 1
            request = httpx.Request("GET", "https://api.openalex.org/works")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)
        if query in self.failures:
            request = httpx.Request("GET", "https://api.openalex.org/works")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)
        return {
            "total": 1,
            "data": [{"paperId": f"{query}-paper", "title": f"OpenAlex paper for {query}"}],
        }


def _client_factory() -> _FakeOpenAlexClient:
    return _FakeOpenAlexClient()


def test_openalex_crawl_resumes_successes_and_retries_failures(tmp_path: Path) -> None:
    queries = normalize_queries(["query one", "query two"])
    config = OpenAlexCrawlConfig(
        output=tmp_path / "results.jsonl",
        failures=tmp_path / "failures.jsonl",
        max_retries=1,
        pause_seconds=0,
    )

    _FakeOpenAlexClient.calls = []
    _FakeOpenAlexClient.failure_counts = {}
    _FakeOpenAlexClient.failures = {"query two"}
    first = crawl_openalex_queries(queries, config, client_factory=_client_factory)

    assert first["processed"] == 2
    assert first["stored_success"] == 1
    assert first["stored_failure"] == 1
    assert first["completed"] == 1
    assert first["remaining"] == 1
    assert first["complete"] is False
    assert _FakeOpenAlexClient.calls == ["query one", "query two"]

    _FakeOpenAlexClient.calls = []
    _FakeOpenAlexClient.failure_counts = {}
    _FakeOpenAlexClient.failures = set()
    second = crawl_openalex_queries(queries, config, client_factory=_client_factory)

    assert second["processed"] == 1
    assert second["skipped"] == 1
    assert second["stored_success"] == 2
    assert second["stored_failure"] == 0
    assert second["completed"] == 2
    assert second["remaining"] == 0
    assert second["complete"] is True
    assert _FakeOpenAlexClient.calls == ["query two"]

    results = load_jsonl_records(config.output)
    failures = load_jsonl_records(config.failures)
    assert len(results) == 2
    assert not failures


def test_openalex_crawl_cli_validates_query_source(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from autoscholar.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "openalex",
            "crawl",
            "--output",
            str(tmp_path / "results.jsonl"),
            "--failures",
            str(tmp_path / "failures.jsonl"),
        ],
    )
    assert result.exit_code != 0
    assert "Provide at least one --query or --queries-file" in result.output
