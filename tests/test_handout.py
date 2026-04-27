from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from autoscholar.cli import app
from autoscholar.handout import build_handout_queries

runner = CliRunner()


def test_build_handout_queries_are_level_specific() -> None:
    terminology = build_handout_queries("open set recognition", "terminology")
    landscape = build_handout_queries("open set recognition", "landscape")
    tension = build_handout_queries("open set recognition", "tension")

    assert len(terminology) == 4
    assert len(landscape) == 5
    assert len(tension) == 6
    assert all(query.query_id.startswith("terminology_") for query in terminology)
    assert any("benchmark" in query.query_text for query in landscape)
    assert any("limitations" in query.query_text for query in tension)


def test_handout_cli_runs_checkpointed_crawl_and_writes_report(monkeypatch, tmp_path: Path) -> None:
    import autoscholar.handout as handout_module

    calls = {}

    def fake_crawl(queries, config):
        calls["queries"] = queries
        calls["config"] = config
        config.output.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for query in queries:
            records.append(
                {
                    "status": "ok",
                    "query_id": query.query_id,
                    "query_text": query.query_text,
                    "endpoint": config.endpoint,
                    "search_signature": config.search_signature(),
                    "attempts": 1,
                    "total_hits": 1,
                    "paper_count": 1,
                    "papers": [
                        {
                            "paperId": f"{query.query_id}-paper",
                            "title": f"Paper for {query.query_text}",
                            "year": 2024,
                            "authors": [{"name": "Demo Author"}],
                            "url": "https://example.test/paper",
                            "abstract": "A survey of benchmark metrics and method families.",
                            "citationCount": 12,
                            "venue": "DemoConf",
                        }
                    ],
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                }
            )
        with config.output.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {
            "total": len(queries),
            "processed": len(queries),
            "skipped": 0,
            "success": len(queries),
            "failure": 0,
            "completed": len(queries),
            "remaining": 0,
            "complete": True,
            "rounds": 1,
            "until_complete": config.until_complete,
            "max_rounds_reached": False,
            "stored_success": len(queries),
            "stored_failure": 0,
        }

    monkeypatch.setattr(handout_module, "crawl_semantic_queries", fake_crawl)

    output_dir = tmp_path / "open-set-landscape"
    result = runner.invoke(
        app,
        [
            "handout",
            "init",
            "open set recognition",
            "--level",
            "landscape",
            "--output-dir",
            str(output_dir),
            "--pause-seconds",
            "0",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "All queries complete." in result.stdout
    assert len(calls["queries"]) == 5
    assert calls["config"].until_complete is True
    assert calls["config"].retry_delay == 120.0
    assert calls["config"].pause_seconds == 10.0
    assert calls["config"].output == output_dir / "artifacts" / "semantic_results.jsonl"
    assert calls["config"].failures == output_dir / "artifacts" / "semantic_failures.jsonl"

    report = output_dir / "reports" / "handout.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "第 2 层：地貌图" in text
    assert "互动问题" in text
    assert "完成度测试" in text
    assert "checkpointed Semantic Scholar crawl" in text
