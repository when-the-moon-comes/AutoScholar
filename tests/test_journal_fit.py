from __future__ import annotations

import json
from pathlib import Path

import fitz
from typer.testing import CliRunner

from autoscholar.cli import app
from autoscholar.journal_fit.input_parser import parse_materials_markdown

runner = CliRunner()


SAMPLE_INPUT = """# Paper Materials Submission

## 1. Paper Identity
- working_title: BioShiftGate
- domain: Bioinformatics
- task: protein function prediction under distribution shift

## 2. Algorithm (fixed, not to be changed by this module)

### Input
Protein embeddings, pathway metadata, and a frozen encoder.

### Method / Pipeline
The method routes each protein to a structure-aware expert and adds a calibrated abstention head to flag unsupported regions.

### Output
Function predictions with confidence-aware abstention scores.

### Key Novelty Claim(s) (作者自认)
- novelty_1: Structure-aware expert routing improves reliability without retraining the frozen encoder.
- novelty_2: Confidence-aware abstention exposes unsupported proteins before they become false positives.

## 3. Experiments (fixed facts)

### Exp-1: Cross-dataset evaluation
- purpose: Validate predictive stability across multiple benchmarks.
- datasets: SwissProt, GOA, UniRef50
- baselines: frozen encoder, prompt tuning, entropy thresholding
- metrics: macro-F1, AUROC, AUPRC
- key_results: Improves macro-F1 by 3.1-4.4 points and AUROC by 2.7 points across three datasets.
- side_findings: The largest gains appear on long-tail protein families.

### Exp-2: Calibration analysis
- purpose: Show that abstention aligns with unsupported inputs.
- datasets: SwissProt, GOA
- baselines: max-probability thresholding
- metrics: ECE, abstention precision
- key_results: Reduces ECE by 18% and increases abstention precision from 0.61 to 0.76.
- side_findings: The disagreement view clearly separates shifted samples.

## 4. Target Journals
- journal_1: Bioinformatics   priority: high
- journal_2: Patterns   priority: medium

## 5. Existing Drafts (optional)
- current_abstract:
- current_intro_p1:
- figure_1_caption:
- prior_rejection_feedback:
"""


class FakeSemanticClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def search_papers_bulk(
        self,
        query: str,
        fields: str = "",
        max_results: int | None = None,
        venue: str | None = None,
        timeout: float | None = None,
        **kwargs,
    ):
        del query, fields, timeout, kwargs
        data = [
            {
                "title": "Reliable Protein Function Prediction Under Shift",
                "abstract": "A methodological paper about robustness and calibration in protein function prediction.",
                "year": 2025,
                "venue": venue or "Bioinformatics",
                "citationCount": 34,
                "externalIds": {"DOI": "10.1000/demo-a"},
                "url": "https://example.org/a",
            },
            {
                "title": "Calibration Strategies for Biological Sequence Models",
                "abstract": "An empirical study focused on calibration, uncertainty, and selective abstention.",
                "year": 2024,
                "venue": venue or "Bioinformatics",
                "citationCount": 22,
                "externalIds": {"DOI": "10.1000/demo-b"},
                "url": "https://example.org/b",
            },
            {
                "title": "A Unified Workflow for Sequence Reliability Analysis",
                "abstract": "A systems-oriented workflow paper covering sequence analysis pipelines and reliability.",
                "year": 2024,
                "venue": venue or "Bioinformatics",
                "citationCount": 18,
                "externalIds": {"DOI": "10.1000/demo-c"},
                "url": "https://example.org/c",
            },
            {
                "title": "Benchmarking Shift-Robust Protein Annotation",
                "abstract": "An empirical benchmark study on protein annotation robustness across datasets.",
                "year": 2025,
                "venue": venue or "Bioinformatics",
                "citationCount": 15,
                "externalIds": {"DOI": "10.1000/demo-d"},
                "url": "https://example.org/d",
            },
            {
                "title": "Selective Prediction for Protein Annotation",
                "abstract": "An application-driven selective prediction paper for biological annotation systems.",
                "year": 2023,
                "venue": venue or "Bioinformatics",
                "citationCount": 12,
                "externalIds": {"DOI": "10.1000/demo-e"},
                "url": "https://example.org/e",
            },
        ]
        limit = max_results or len(data)
        return iter(data[:limit])

    def search_papers(self, query: str, limit: int, fields: str = "", timeout: float | None = None) -> dict:
        del query, fields, timeout
        return {"data": list(self.search_papers_bulk("", max_results=limit))}


def _stub_web_search(query: str, timeout: float = 10.0) -> list[dict[str, str]]:
    del timeout
    return [
        {
            "url": f"https://example.org/{query.replace(' ', '-')}",
            "title": query,
            "snippet": f"Snippet for {query} describing scope, editorial preferences, and submission expectations.",
        }
    ]


def test_parse_materials_markdown_supports_multiline_fields() -> None:
    materials = parse_materials_markdown(
        """# Paper Materials Submission

## 1. Paper Identity
- working_title: Spatial Mosaic
- domain: Urban Analytics
- task: cross-boundary governance diagnosis

## 2. Algorithm (fixed, not to be changed by this module)

### Input
Cross-scale land use, production, and ecological indicators.

### Method / Pipeline
Boundary-free diagnosis pipeline.

### Output
Governance-space typology.

### Key Novelty Claim(s) (作者自认)
- novelty_1: A boundary-free diagnosis workflow supports multi-scale governance analysis.
- novelty_2: |
    The typology reveals differentiated governance configurations
    rather than a single integrated regional narrative.

## 3. Experiments (fixed facts)

### Exp-1: Multi-scale diagnosis
- purpose: |
    Compare the diagnosed region structure
    across multiple scales.
- datasets:
  - GBA block groups
  - Cross-boundary PLE indicators
- baselines:
  - Administrative-boundary zoning
  - Single-scale diagnosis
- metrics:
  - cluster stability
  - spatial coherence
- key_results: |
    The boundary-free workflow recovers three stable configurations
    and preserves cross-scale contrast.
- side_findings:
  - Transitional regions occupy the widest area.
  - Mosaic structures are concentrated near cross-boundary corridors.

## 4. Target Journals
- journal_1: Computers, Environment and Urban Systems
- priority: high

## 5. Existing Drafts (optional)
- current_abstract: |
    Sentence one.
    Sentence two.
- current_intro_p1:
- figure_1_caption:
- prior_rejection_feedback:
""",
        paper_id="demo-paper",
        mode="from_scratch",
    )

    assert materials.algorithm.novelty_claims[1].startswith("The typology reveals")
    assert materials.experiments[0].datasets == ["GBA block groups", "Cross-boundary PLE indicators"]
    assert materials.experiments[0].baselines == ["Administrative-boundary zoning", "Single-scale diagnosis"]
    assert "Transitional regions occupy the widest area." in (materials.experiments[0].side_findings or "")
    assert "Mosaic structures are concentrated near cross-boundary corridors." in (materials.experiments[0].side_findings or "")
    assert materials.target_journals[0].priority == "high"
    assert materials.existing_drafts.current_abstract == "Sentence one.\nSentence two."


def test_jfa_run_end_to_end(tmp_path: Path, monkeypatch) -> None:
    import autoscholar.journal_fit.phases as phases_module

    monkeypatch.setattr(phases_module, "SemanticScholarClient", FakeSemanticClient)
    monkeypatch.setattr(phases_module, "_search_duckduckgo", _stub_web_search)

    paper_id = "demo-jfa"
    input_path = tmp_path / "materials.md"
    input_path.write_text(SAMPLE_INPUT, encoding="utf-8")

    init = runner.invoke(app, ["jfa", "init", "--paper-id", paper_id, "--base-dir", str(tmp_path)])
    assert init.exit_code == 0, init.stdout

    workspace_root = tmp_path / ".autoscholar" / paper_id
    figures_dir = workspace_root / "raw" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    (figures_dir / "fig_01_main_pipeline.png").write_bytes(b"fake-image")

    result = runner.invoke(
        app,
        [
            "jfa",
            "run",
            "--paper-id",
            paper_id,
            "--base-dir",
            str(tmp_path),
            "--input",
            str(input_path),
            "--no-cache",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Primary:" in result.stdout

    assets_path = workspace_root / "assets.json"
    fit_matrix_path = workspace_root / "fit_matrix.json"
    report_path = workspace_root / "report.md"
    assert assets_path.exists()
    assert fit_matrix_path.exists()
    assert report_path.exists()
    assert any(workspace_root.joinpath("skeletons").glob("skeleton_*.md"))

    assets_payload = json.loads(assets_path.read_text(encoding="utf-8"))
    fit_payload = json.loads(fit_matrix_path.read_text(encoding="utf-8"))
    report_text = report_path.read_text(encoding="utf-8")
    narrative_payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(workspace_root.joinpath("narratives").glob("candidate_*.json"))
    ]
    skeleton_path = sorted(workspace_root.joinpath("skeletons").glob("skeleton_*.md"))[0]
    skeleton_text = skeleton_path.read_text(encoding="utf-8")
    contribution_block = skeleton_text.split("## Contribution Bullets\n", 1)[1].split("\n## Related Work Strategy", 1)[0]
    contribution_lines = [line for line in contribution_block.splitlines() if line.startswith("- ")]
    assert len(assets_payload["assets"]) >= 4
    assert fit_payload["top_combinations"]
    assert len(narrative_payloads) == len({item["id"] for item in narrative_payloads})
    assert len(contribution_lines) >= 3
    assert "Journal Fit Advisor Report" in report_text
    assert "Final Recommendation" in report_text
    assert "Risk:" in result.stdout


def test_jfa_phase0_pdf_mode(tmp_path: Path) -> None:
    paper_id = "draft-jfa"
    input_path = tmp_path / "override.md"
    input_path.write_text(
        """# Paper Materials Submission

## 1. Paper Identity
- working_title: Draft Override
- domain: Computer Vision
- task: medical image segmentation

## 2. Algorithm (fixed, not to be changed by this module)

### Input
images

### Method / Pipeline
placeholder

### Output
masks

### Key Novelty Claim(s) (作者自认)
- novelty_1:
- novelty_2:

## 3. Experiments (fixed facts)

### Exp-1: Placeholder
- purpose:
- datasets:
- baselines:
- metrics:
- key_results: placeholder
- side_findings:

## 4. Target Journals
- journal_1: Medical Image Analysis   priority: high

## 5. Existing Drafts (optional)
- current_abstract:
- current_intro_p1:
- figure_1_caption:
- prior_rejection_feedback:
""",
        encoding="utf-8",
    )

    pdf_path = tmp_path / "draft.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "BioDraft",
                "Abstract",
                "We study segmentation reliability under distribution shift.",
                "Introduction",
                "This problem matters in deployment settings.",
                "Methods",
                "Our approach adds a gating module and abstention head.",
                "Experiments",
                "Across three datasets we improve AUROC and calibration.",
                "Conclusion",
                "The method is robust and selective.",
            ]
        ),
    )
    document.save(pdf_path)
    document.close()

    result = runner.invoke(
        app,
        [
            "jfa",
            "phase0",
            "--paper-id",
            paper_id,
            "--base-dir",
            str(tmp_path),
            "--draft-pdf",
            str(pdf_path),
            "--input",
            str(input_path),
        ],
    )
    assert result.exit_code == 0, result.stdout

    workspace_root = tmp_path / ".autoscholar" / paper_id
    run_meta = json.loads((workspace_root / "run_meta.json").read_text(encoding="utf-8"))
    normalized_input = (workspace_root / "input.md").read_text(encoding="utf-8")
    assert run_meta["mode"] == "draft_reframing"
    assert "由 PDF 自动抽取" in normalized_input
    assert "Medical Image Analysis" in normalized_input
