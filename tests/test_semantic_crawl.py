from __future__ import annotations

from pathlib import Path

import httpx
from typer.testing import CliRunner

from autoscholar.cli import app
from autoscholar.semantic_crawl import (
    SemanticCrawlConfig,
    crawl_semantic_queries,
    load_jsonl_records,
    normalize_queries,
)


class _FakeSemanticClient:
    failures: set[str] = set()
    failure_counts: dict[str, int] = {}
    calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def search_papers(self, query: str, limit: int, fields: str, timeout: float | None = None) -> dict:
        del limit, fields, timeout
        self.calls.append(query)
        if self.failure_counts.get(query, 0) > 0:
            self.failure_counts[query] -= 1
            request = httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/search")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)
        if query in self.failures:
            request = httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/search")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)
        return {
            "total": 1,
            "data": [{"paperId": f"{query}-paper", "title": f"Paper for {query}"}],
        }


def _client_factory() -> _FakeSemanticClient:
    return _FakeSemanticClient()


def test_semantic_crawl_resumes_successes_and_retries_failures(tmp_path: Path) -> None:
    queries = normalize_queries(["query one", "query two"])
    config = SemanticCrawlConfig(
        output=tmp_path / "results.jsonl",
        failures=tmp_path / "failures.jsonl",
        max_retries=1,
        pause_seconds=0,
    )

    _FakeSemanticClient.calls = []
    _FakeSemanticClient.failure_counts = {}
    _FakeSemanticClient.failures = {"query two"}
    first = crawl_semantic_queries(queries, config, client_factory=_client_factory)

    assert first["processed"] == 2
    assert first["stored_success"] == 1
    assert first["stored_failure"] == 1
    assert first["completed"] == 1
    assert first["remaining"] == 1
    assert first["complete"] is False
    assert _FakeSemanticClient.calls == ["query one", "query two"]

    _FakeSemanticClient.calls = []
    _FakeSemanticClient.failure_counts = {}
    _FakeSemanticClient.failures = set()
    second = crawl_semantic_queries(queries, config, client_factory=_client_factory)

    assert second["processed"] == 1
    assert second["skipped"] == 1
    assert second["stored_success"] == 2
    assert second["stored_failure"] == 0
    assert second["completed"] == 2
    assert second["remaining"] == 0
    assert second["complete"] is True
    assert _FakeSemanticClient.calls == ["query two"]

    results = load_jsonl_records(config.output)
    failures = load_jsonl_records(config.failures)
    assert len(results) == 2
    assert not failures


def test_semantic_crawl_until_complete_runs_checkpoint_rounds(tmp_path: Path) -> None:
    queries = normalize_queries(["query one", "query two", "query three"])
    config = SemanticCrawlConfig(
        output=tmp_path / "results.jsonl",
        failures=tmp_path / "failures.jsonl",
        max_retries=1,
        pause_seconds=0,
        max_queries=1,
        until_complete=True,
        round_delay=0,
    )

    _FakeSemanticClient.calls = []
    _FakeSemanticClient.failures = set()
    _FakeSemanticClient.failure_counts = {}
    summary = crawl_semantic_queries(queries, config, client_factory=_client_factory)

    assert summary["processed"] == 3
    assert summary["rounds"] == 3
    assert summary["completed"] == 3
    assert summary["remaining"] == 0
    assert summary["complete"] is True
    assert _FakeSemanticClient.calls == ["query one", "query two", "query three"]


def test_semantic_crawl_until_complete_respects_max_rounds(tmp_path: Path) -> None:
    queries = normalize_queries(["query one"])
    config = SemanticCrawlConfig(
        output=tmp_path / "results.jsonl",
        failures=tmp_path / "failures.jsonl",
        max_retries=1,
        pause_seconds=0,
        until_complete=True,
        round_delay=0,
        max_rounds=2,
    )

    _FakeSemanticClient.calls = []
    _FakeSemanticClient.failures = {"query one"}
    _FakeSemanticClient.failure_counts = {}
    summary = crawl_semantic_queries(queries, config, client_factory=_client_factory)

    assert summary["processed"] == 2
    assert summary["rounds"] == 2
    assert summary["remaining"] == 1
    assert summary["complete"] is False
    assert summary["max_rounds_reached"] is True


def test_semantic_crawl_cli_validates_query_source(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "semantic",
            "crawl",
            "--output",
            str(tmp_path / "results.jsonl"),
            "--failures",
            str(tmp_path / "failures.jsonl"),
        ],
    )
    assert result.exit_code != 0
    assert "Provide at least one --query or --queries-file" in result.output
