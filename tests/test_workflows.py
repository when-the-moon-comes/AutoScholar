from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from autoscholar.cli import app

runner = CliRunner()


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


class FakeSemanticScholarClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def close(self) -> None:
        return None

    def search_papers(self, query: str, limit: int, fields: str, timeout: float | None = None) -> dict:
        del fields, timeout
        if "adjacent" in query:
            data = [
                {
                    "paperId": "paper-demo-2",
                    "title": "Medical OOD Localization Benchmark",
                    "year": 2022,
                    "authors": [{"name": "Author B"}],
                    "venue": "Journal B",
                    "url": "https://example.org/b",
                    "abstract": "Benchmark for OOD localization in medical imaging.",
                    "citationCount": 50,
                    "influentialCitationCount": 8,
                    "externalIds": {"DOI": "10.1000/demo2"},
                    "isOpenAccess": True,
                    "openAccessPdf": {"url": "https://example.org/b.pdf"},
                },
                {
                    "paperId": "paper-demo-3",
                    "title": "Uncertainty-aware Segmentation Baseline",
                    "year": 2024,
                    "authors": [{"name": "Author C"}],
                    "venue": "Journal C",
                    "url": "https://example.org/c",
                    "abstract": "Uncertainty-aware segmentation baseline.",
                    "citationCount": 8,
                    "influentialCitationCount": 1,
                    "externalIds": {"DOI": "10.1000/demo3"},
                    "isOpenAccess": True,
                    "openAccessPdf": {"url": "https://example.org/c.pdf"},
                },
            ]
        else:
            data = [
                {
                    "paperId": "paper-demo-1",
                    "title": "Failure Detection in Medical Image Segmentation",
                    "year": 2024,
                    "authors": [{"name": "Author A"}],
                    "venue": "Journal A",
                    "url": "https://example.org/a",
                    "abstract": "Failure detection for medical segmentation.",
                    "citationCount": 12,
                    "influentialCitationCount": 2,
                    "externalIds": {"DOI": "10.1000/demo1"},
                    "isOpenAccess": True,
                    "openAccessPdf": {"url": "https://example.org/a.pdf"},
                }
            ]
        return {"total": len(data), "data": data[:limit]}

    def get_recommendations_from_lists(
        self,
        positive_paper_ids: list[str],
        negative_paper_ids: list[str] | None = None,
        limit: int = 10,
        fields: str = "",
        timeout: float | None = None,
    ) -> list[dict]:
        del positive_paper_ids, negative_paper_ids, limit, fields, timeout
        return [
            {
                "paperId": "paper-demo-4",
                "title": "Unknown-region Abstention for Segmentation",
                "year": 2025,
                "authors": [{"name": "Author D"}],
                "venue": "Journal D",
                "url": "https://example.org/d",
                "abstract": "Abstention for unsupported segmentation regions.",
                "citationCount": 6,
                "influentialCitationCount": 1,
                "externalIds": {"DOI": "10.1000/demo4"},
                "isOpenAccess": True,
                "openAccessPdf": {"url": "https://example.org/d.pdf"},
            }
        ]

    def get_recommendations(self, *args, **kwargs) -> list[dict]:
        return self.get_recommendations_from_lists([], None)


def test_citation_pipeline_end_to_end(tmp_path: Path, monkeypatch) -> None:
    workspace_dir = tmp_path / "pipeline-demo"
    result = runner.invoke(
        app,
        [
            "workspace",
            "init",
            str(workspace_dir),
            "--template",
            "idea-evaluation",
            "--reports-lang",
            "zh",
        ],
    )
    assert result.exit_code == 0, result.stdout

    _write_jsonl(
        workspace_dir / "artifacts" / "claims.jsonl",
        [
            {
                "claim_id": "C01",
                "section": "intro",
                "source_lines": "1-2",
                "claim_text": "Medical segmentation should support abstention for unsupported regions.",
                "claim_type": "problem",
                "priority": "high",
                "short_label": "abstention",
                "notes": "",
                "metadata": {},
            },
            {
                "claim_id": "C02",
                "section": "related-work",
                "source_lines": "3-5",
                "claim_text": "Relevant evidence is distributed across OOD localization and uncertainty-aware segmentation.",
                "claim_type": "evidence",
                "priority": "high",
                "short_label": "adjacent evidence",
                "notes": "",
                "metadata": {},
            },
        ],
    )
    _write_jsonl(
        workspace_dir / "artifacts" / "queries.jsonl",
        [
            {
                "query_id": "C01-Q1",
                "claim_id": "C01",
                "query_text": "medical segmentation abstention unsupported regions",
                "short_label": "abstention",
                "core_keywords": ["medical segmentation", "abstention"],
                "notes": "",
                "metadata": {},
            },
            {
                "query_id": "C02-Q1",
                "claim_id": "C02",
                "query_text": "adjacent medical OOD localization uncertainty segmentation",
                "short_label": "adjacent",
                "core_keywords": ["OOD localization", "uncertainty-aware segmentation"],
                "notes": "",
                "metadata": {},
            },
        ],
    )

    import autoscholar.citation.search as search_module
    import autoscholar.citation.correct as correct_module

    monkeypatch.setattr(search_module, "SemanticScholarClient", FakeSemanticScholarClient)
    monkeypatch.setattr(correct_module, "SemanticScholarClient", FakeSemanticScholarClient)

    for command in (
        ["citation", "search", "--workspace", str(workspace_dir)],
        ["citation", "prescreen", "--workspace", str(workspace_dir)],
        ["citation", "correct", "--workspace", str(workspace_dir)],
        ["citation", "shortlist", "--workspace", str(workspace_dir)],
        ["citation", "bib", "--workspace", str(workspace_dir)],
    ):
        outcome = runner.invoke(app, command)
        assert outcome.exit_code == 0, outcome.stdout

    selected = (workspace_dir / "artifacts" / "selected_citations.jsonl").read_text(encoding="utf-8").strip()
    assert "Failure Detection in Medical Image Segmentation" in selected
    assert (workspace_dir / "artifacts" / "references.bib").exists()


def test_idea_assess_and_render(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "idea-demo"
    source_example = Path("examples/idea-evaluation-demo")

    for relative in (
        "workspace.yaml",
        "inputs/idea_source.md",
        "configs/search.yaml",
        "configs/recommendation.yaml",
        "configs/citation_rules.yaml",
        "configs/idea_evaluation.yaml",
        "artifacts/claims.jsonl",
        "artifacts/queries.jsonl",
        "artifacts/search_results.raw.jsonl",
        "artifacts/search_results.deduped.jsonl",
        "artifacts/query_reviews.json",
        "artifacts/search_failures.jsonl",
        "artifacts/recommendation_corrections.jsonl",
        "artifacts/selected_citations.jsonl",
        "artifacts/evidence_map.json",
        "artifacts/report_validation.json",
    ):
        destination = workspace_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_path = source_example / relative
        if source_path.exists():
            destination.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            destination.write_text("{}\n" if relative.endswith(".json") else "", encoding="utf-8")

    assess = runner.invoke(app, ["idea", "assess", "--workspace", str(workspace_dir)])
    assert assess.exit_code == 0, assess.stdout

    render_feasibility = runner.invoke(
        app, ["report", "render", "--workspace", str(workspace_dir), "--kind", "feasibility"]
    )
    render_deep_dive = runner.invoke(
        app, ["report", "render", "--workspace", str(workspace_dir), "--kind", "deep-dive"]
    )
    validate_feasibility = runner.invoke(
        app, ["report", "validate", "--workspace", str(workspace_dir), "--kind", "feasibility"]
    )
    validate_deep_dive = runner.invoke(
        app, ["report", "validate", "--workspace", str(workspace_dir), "--kind", "deep-dive"]
    )

    assert render_feasibility.exit_code == 0, render_feasibility.stdout
    assert render_deep_dive.exit_code == 0, render_deep_dive.stdout
    assert validate_feasibility.exit_code == 0, validate_feasibility.stdout
    assert validate_deep_dive.exit_code == 0, validate_deep_dive.stdout
    feasibility_text = (workspace_dir / "reports" / "feasibility.md").read_text(encoding="utf-8")
    deep_dive_text = (workspace_dir / "reports" / "deep_dive.md").read_text(encoding="utf-8")
    assert "OpenPQFormer Idea" in feasibility_text
    assert "## 1. 评估结论" in feasibility_text
    assert "## 1. 一页结论" in deep_dive_text
    assert "MOOD 2020" in deep_dive_text
    evidence_map_text = (workspace_dir / "artifacts" / "evidence_map.json").read_text(encoding="utf-8")
    assert "executive_summary" in evidence_map_text
