from __future__ import annotations

import json
from pathlib import Path

import fitz
from typer.testing import CliRunner

from autoscholar.cli import app

runner = CliRunner()


def test_workspace_init_and_doctor(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "citation-demo"
    result = runner.invoke(
        app,
        [
            "workspace",
            "init",
            str(workspace_dir),
            "--template",
            "citation-paper",
            "--reports-lang",
            "zh",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (workspace_dir / "workspace.yaml").exists()

    doctor = runner.invoke(app, ["workspace", "doctor", "--workspace", str(workspace_dir)])
    assert doctor.exit_code == 0, doctor.stdout


def test_idea_creation_v2_workspace_init_render_and_doctor(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "idea-v2-demo"
    result = runner.invoke(
        app,
        [
            "workspace",
            "init",
            str(workspace_dir),
            "--template",
            "idea-creation-v2",
            "--reports-lang",
            "zh",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (workspace_dir / "inputs" / "idea_seed.md").exists()
    assert (workspace_dir / "configs" / "conversation.yaml").exists()
    assert (workspace_dir / "artifacts" / "retrieval").is_dir()

    doctor = runner.invoke(app, ["workspace", "doctor", "--workspace", str(workspace_dir)])
    assert doctor.exit_code == 0, doctor.stdout

    render = runner.invoke(
        app, ["report", "render", "--workspace", str(workspace_dir), "--kind", "idea-conversation"]
    )
    assert render.exit_code == 0, render.stdout
    record = workspace_dir / "reports" / "idea_conversation_record.md"
    assert record.exists()
    assert "Stage 1 Diagnosis" in record.read_text(encoding="utf-8")


def test_schema_export(tmp_path: Path) -> None:
    output_dir = tmp_path / "schemas"
    result = runner.invoke(app, ["schema", "export", "--output-dir", str(output_dir)])
    assert result.exit_code == 0, result.stdout
    assert (output_dir / "workspace_manifest.schema.json").exists()
    assert (output_dir / "assets.schema.json").exists()


class _FakeSemanticClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get_paper(self, paper_id: str, fields: str, timeout: float | None = None) -> dict:
        del fields, timeout
        return {"paperId": paper_id, "title": "Demo Paper"}

    def search_papers(self, query: str, limit: int, fields: str, timeout: float | None = None) -> dict:
        del limit, fields, timeout
        return {"total": 1, "data": [{"paperId": "demo-1", "title": f"Search for {query}"}]}

    def get_recommendations(self, paper_id: str, limit: int, fields: str, timeout: float | None = None) -> list[dict]:
        del limit, fields, timeout
        return [{"paperId": f"{paper_id}-rec", "title": "Recommended Demo"}]

    def get_paper_citations(self, paper_id: str, fields: str, timeout: float | None = None) -> list[dict]:
        del paper_id, fields, timeout
        return [{"paperId": "cite-1", "title": "Citation Demo"}]

    def get_paper_references(self, paper_id: str, fields: str, timeout: float | None = None) -> list[dict]:
        del paper_id, fields, timeout
        return [{"paperId": "ref-1", "title": "Reference Demo"}]

    def search_author(self, query: str, fields: str, timeout: float | None = None) -> dict:
        del fields, timeout
        return {"data": [{"authorId": "author-1", "name": query}]}

    def get_author(self, author_id: str, fields: str, timeout: float | None = None) -> dict:
        del fields, timeout
        return {"authorId": author_id, "name": "Author Demo"}

    def get_author_papers(self, author_id: str, limit: int, fields: str, timeout: float | None = None) -> list[dict]:
        del limit, fields, timeout
        return [{"paperId": f"{author_id}-paper-1", "title": "Author Paper Demo"}]

    def download_open_access_pdf(self, paper_id: str, directory: Path, timeout: float | None = None) -> Path:
        del timeout
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / f"{paper_id}.pdf"
        output.write_bytes(b"%PDF-1.4\n")
        return output


class _FakeOpenAlexClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get_paper(self, paper_id: str, fields: str, timeout: float | None = None) -> dict:
        del fields, timeout
        return {"paperId": paper_id, "title": "OpenAlex Demo Paper"}

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
        return {"total": 1, "data": [{"paperId": "W1", "title": f"OpenAlex search for {query}"}]}

    def search_papers_bulk(self, *args, **kwargs):
        del args, kwargs
        yield {"paperId": "W1", "title": "OpenAlex bulk demo"}

    def get_recommendations(self, paper_id: str, limit: int, fields: str, timeout: float | None = None) -> list[dict]:
        del limit, fields, timeout
        return [{"paperId": f"{paper_id}-related", "title": "Related Demo"}]

    def get_paper_citations(
        self,
        paper_id: str,
        limit: int,
        fields: str,
        timeout: float | None = None,
    ) -> list[dict]:
        del paper_id, limit, fields, timeout
        return [{"paperId": "cite-1", "title": "OpenAlex Citation Demo"}]

    def get_paper_references(
        self,
        paper_id: str,
        limit: int,
        fields: str,
        timeout: float | None = None,
    ) -> list[dict]:
        del paper_id, limit, fields, timeout
        return [{"paperId": "ref-1", "title": "OpenAlex Reference Demo"}]

    def search_author(self, query: str, limit: int, fields: str, timeout: float | None = None) -> dict:
        del limit, fields, timeout
        return {"data": [{"authorId": "A1", "name": query}]}

    def get_author(self, author_id: str, fields: str, timeout: float | None = None) -> dict:
        del fields, timeout
        return {"authorId": author_id, "name": "OpenAlex Author Demo"}

    def get_author_papers(self, author_id: str, limit: int, fields: str, timeout: float | None = None) -> list[dict]:
        del limit, fields, timeout
        return [{"paperId": f"{author_id}-paper-1", "title": "OpenAlex Author Paper Demo"}]

    def download_open_access_pdf(self, paper_id: str, directory: Path, timeout: float | None = None) -> Path:
        del timeout
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / f"{paper_id}.pdf"
        output.write_bytes(b"%PDF-1.4\n")
        return output


def test_semantic_cli_commands(monkeypatch, tmp_path: Path) -> None:
    import autoscholar.cli as cli_module

    monkeypatch.setattr(cli_module, "SemanticScholarClient", _FakeSemanticClient)

    result = runner.invoke(app, ["semantic", "paper", "CorpusID:123"])
    assert result.exit_code == 0, result.stdout
    assert "Demo Paper" in result.stdout

    result = runner.invoke(app, ["semantic", "search", "medical image segmentation"])
    assert result.exit_code == 0, result.stdout
    assert "Search for medical image segmentation" in result.stdout

    result = runner.invoke(app, ["semantic", "citations", "CorpusID:123"])
    assert result.exit_code == 0, result.stdout
    assert "Citation Demo" in result.stdout

    result = runner.invoke(app, ["semantic", "references", "CorpusID:123"])
    assert result.exit_code == 0, result.stdout
    assert "Reference Demo" in result.stdout

    result = runner.invoke(app, ["semantic", "download-pdf", "CorpusID:123", "--directory", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "CorpusID:123.pdf").exists()


def test_openalex_cli_commands(monkeypatch, tmp_path: Path) -> None:
    import autoscholar.cli as cli_module

    monkeypatch.setattr(cli_module, "OpenAlexClient", _FakeOpenAlexClient)

    result = runner.invoke(app, ["openalex", "paper", "W123"])
    assert result.exit_code == 0, result.stdout
    assert "OpenAlex Demo Paper" in result.stdout

    result = runner.invoke(app, ["openalex", "search", "medical image segmentation"])
    assert result.exit_code == 0, result.stdout
    assert "OpenAlex search for medical image segmentation" in result.stdout

    result = runner.invoke(app, ["openalex", "recommend", "W123"])
    assert result.exit_code == 0, result.stdout
    assert "Related Demo" in result.stdout

    result = runner.invoke(app, ["openalex", "citations", "W123"])
    assert result.exit_code == 0, result.stdout
    assert "OpenAlex Citation Demo" in result.stdout

    result = runner.invoke(app, ["openalex", "references", "W123"])
    assert result.exit_code == 0, result.stdout
    assert "OpenAlex Reference Demo" in result.stdout

    result = runner.invoke(app, ["openalex", "author-search", "Demo Author"])
    assert result.exit_code == 0, result.stdout
    assert "Demo Author" in result.stdout

    result = runner.invoke(app, ["openalex", "author", "A123"])
    assert result.exit_code == 0, result.stdout
    assert "OpenAlex Author Demo" in result.stdout

    result = runner.invoke(app, ["openalex", "author-papers", "A123"])
    assert result.exit_code == 0, result.stdout
    assert "OpenAlex Author Paper Demo" in result.stdout

    result = runner.invoke(app, ["openalex", "download-pdf", "W123", "--directory", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "W123.pdf").exists()


def test_semantic_smoke_skips_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("S2_API_KEY", raising=False)
    result = runner.invoke(app, ["semantic", "smoke"])
    assert result.exit_code == 0, result.stdout
    assert "live smoke test skipped" in result.stdout


def test_openalex_smoke_skips_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    result = runner.invoke(app, ["openalex", "smoke"])
    assert result.exit_code == 0, result.stdout
    assert "live smoke test skipped" in result.stdout


def test_util_pdf_to_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "demo.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Hello AutoScholar")
    document.save(pdf_path)
    document.close()

    result = runner.invoke(app, ["util", "pdf-to-text", str(pdf_path)])
    assert result.exit_code == 0, result.stdout
    output_path = pdf_path.with_suffix(".txt")
    assert output_path.exists()
    assert "Hello AutoScholar" in output_path.read_text(encoding="utf-8")
