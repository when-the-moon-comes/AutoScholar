from __future__ import annotations

import re
from pathlib import Path

from autoscholar.exceptions import ValidationError
from autoscholar.io import read_json, read_text
from autoscholar.journal_fit.models import (
    AlgorithmRecord,
    ExistingDraftsRecord,
    ExperimentRecord,
    FigureRecord,
    FiguresManifestRecord,
    JournalFitMode,
    PaperIdentityRecord,
    PaperMaterialsRecord,
    TargetJournalRecord,
)
from autoscholar.journal_fit.workspace import JournalFitWorkspace
from autoscholar.utils.pdf import extract_pdf_text


IDENTITY_HEADING = "## 1. Paper Identity"
ALGORITHM_HEADING = "## 2. Algorithm (fixed, not to be changed by this module)"
EXPERIMENTS_HEADING = "## 3. Experiments (fixed facts)"
JOURNALS_HEADING = "## 4. Target Journals"
DRAFTS_HEADING = "## 5. Existing Drafts (optional)"
NOVELTY_HEADING = "### Key Novelty Claim(s) (作者自认)"
AUTO_EXTRACTED_PREFIX = "> 由 PDF 自动抽取，请审阅。\n\n"


def _section(text: str, heading: str, end_headings: list[str]) -> str:
    if end_headings:
        tail = rf"(?=^(?:{'|'.join(re.escape(item) for item in end_headings)})\s*$|\Z)"
    else:
        tail = r"(?=\Z)"
    pattern = rf"(?ms)^{re.escape(heading)}\s*$\n(.*?){tail}"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _dedent_block(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return []
    indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.strip()]
    min_indent = min(indents) if indents else 0
    return [line[min_indent:] if len(line) >= min_indent else line for line in lines]


def _extract_bullet_value(text: str, key: str) -> str:
    lines = text.splitlines()
    start_index: int | None = None
    inline_value = ""
    for index, line in enumerate(lines):
        match = re.match(rf"^-\s*{re.escape(key)}:\s*(.*)$", line)
        if match:
            start_index = index
            inline_value = match.group(1).rstrip()
            break
    if start_index is None:
        return ""

    continuation: list[str] = []
    for line in lines[start_index + 1 :]:
        if re.match(r"^-\s*[A-Za-z0-9_]+:\s*", line):
            break
        continuation.append(line)

    normalized_inline = inline_value.strip()
    continuation = _dedent_block(continuation)
    if normalized_inline in {"|", ">"}:
        return "\n".join(continuation).strip()
    if continuation:
        prefix = [normalized_inline] if normalized_inline else []
        return "\n".join(prefix + continuation).strip()
    return normalized_inline


def _parse_list_field(value: str) -> list[str]:
    if not value:
        return []
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    bullet_items = [re.sub(r"^-\s*", "", line).strip() for line in lines if line.startswith("-")]
    if bullet_items:
        return bullet_items
    flattened = value.replace("\n", "; ")
    parts = re.split(r"[;,/]\s*|\s*\|\s*", flattened)
    return [item.strip() for item in parts if item.strip()]


def _first_sentence(text: str) -> str:
    for part in re.split(r"(?<=[.!?。！？])\s+|\n+", text.strip()):
        cleaned = part.strip()
        if cleaned:
            return cleaned
    return text.strip()


def _render_scalar_bullet(key: str, value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return f"- {key}:"
    if "\n" in cleaned:
        indented = "\n".join(f"    {line}" if line else "" for line in cleaned.splitlines())
        return f"- {key}: |\n{indented}"
    return f"- {key}: {cleaned}"


def _render_list_bullet(key: str, values: list[str]) -> str:
    items = [item.strip() for item in values if item.strip()]
    if not items:
        return f"- {key}:"
    lines = [f"- {key}:"]
    lines.extend(f"  - {item}" for item in items)
    return "\n".join(lines)


def _parse_target_journals(journals_section: str) -> list[TargetJournalRecord]:
    journals: list[TargetJournalRecord] = []
    lines = [line.strip() for line in journals_section.splitlines() if line.strip()]
    index = 0
    while index < len(lines):
        line = lines[index]
        same_line = re.match(r"-\s*journal_\d+:\s*(.*?)\s+priority:\s*(high|medium|low)\s*$", line, re.IGNORECASE)
        if same_line:
            journals.append(
                TargetJournalRecord(
                    journal_name=same_line.group(1).strip(),
                    priority=same_line.group(2).lower(),  # type: ignore[arg-type]
                )
            )
            index += 1
            continue

        journal_only = re.match(r"-\s*journal_\d+:\s*(.*?)\s*$", line, re.IGNORECASE)
        if journal_only:
            priority = "medium"
            if index + 1 < len(lines):
                priority_match = re.match(r"-\s*priority:\s*(high|medium|low)\s*$", lines[index + 1], re.IGNORECASE)
                if priority_match:
                    priority = priority_match.group(1).lower()
                    index += 1
            journals.append(
                TargetJournalRecord(
                    journal_name=journal_only.group(1).strip(),
                    priority=priority,  # type: ignore[arg-type]
                )
            )
        index += 1
    return journals


def parse_materials_markdown(text: str, paper_id: str, mode: JournalFitMode) -> PaperMaterialsRecord:
    identity_section = _section(text, IDENTITY_HEADING, [ALGORITHM_HEADING])
    algorithm_section = _section(text, ALGORITHM_HEADING, [EXPERIMENTS_HEADING])
    experiments_section = _section(text, EXPERIMENTS_HEADING, [JOURNALS_HEADING])
    journals_section = _section(text, JOURNALS_HEADING, [DRAFTS_HEADING])
    drafts_section = _section(text, DRAFTS_HEADING, [])

    input_spec = _section(algorithm_section, "### Input", ["### Method / Pipeline"])
    method_pipeline = _section(algorithm_section, "### Method / Pipeline", ["### Output"])
    output_spec = _section(algorithm_section, "### Output", [NOVELTY_HEADING])
    novelty_section = _section(algorithm_section, NOVELTY_HEADING, [])
    novelty_claims = [
        value
        for value in (
            _extract_bullet_value(novelty_section, "novelty_1"),
            _extract_bullet_value(novelty_section, "novelty_2"),
        )
        if value
    ]

    experiment_matches = list(
        re.finditer(r"(?ms)^###\s+(Exp-\d+):\s*(.+?)\s*$\n(.*?)(?=^###\s+Exp-\d+:|\Z)", experiments_section)
    )
    experiments: list[ExperimentRecord] = []
    for match in experiment_matches:
        experiment_id = match.group(1).strip()
        name = match.group(2).strip()
        body = match.group(3)
        experiments.append(
            ExperimentRecord(
                experiment_id=experiment_id,
                name=name,
                purpose=_extract_bullet_value(body, "purpose") or None,
                datasets=_parse_list_field(_extract_bullet_value(body, "datasets")),
                baselines=_parse_list_field(_extract_bullet_value(body, "baselines")),
                metrics=_parse_list_field(_extract_bullet_value(body, "metrics")),
                key_results=_extract_bullet_value(body, "key_results"),
                side_findings=_extract_bullet_value(body, "side_findings") or None,
            )
        )

    materials = PaperMaterialsRecord(
        paper_id=paper_id,
        mode=mode,
        identity=PaperIdentityRecord(
            working_title=_extract_bullet_value(identity_section, "working_title"),
            domain=_extract_bullet_value(identity_section, "domain") or None,
            task=_extract_bullet_value(identity_section, "task") or None,
        ),
        algorithm=AlgorithmRecord(
            input_spec=input_spec,
            method_pipeline=method_pipeline,
            output_spec=output_spec,
            novelty_claims=novelty_claims,
        ),
        experiments=experiments,
        target_journals=_parse_target_journals(journals_section),
        existing_drafts=ExistingDraftsRecord(
            current_abstract=_extract_bullet_value(drafts_section, "current_abstract") or None,
            current_intro_p1=_extract_bullet_value(drafts_section, "current_intro_p1") or None,
            figure_1_caption=_extract_bullet_value(drafts_section, "figure_1_caption") or None,
            prior_rejection_feedback=_extract_bullet_value(drafts_section, "prior_rejection_feedback") or None,
        ),
    )
    return materials


def render_materials_markdown(materials: PaperMaterialsRecord, auto_extracted: bool = False) -> str:
    prefix = AUTO_EXTRACTED_PREFIX if auto_extracted else ""
    novelty_lines = materials.algorithm.novelty_claims or ["", ""]
    while len(novelty_lines) < 2:
        novelty_lines.append("")
    experiment_blocks: list[str] = []
    for experiment in materials.experiments:
        experiment_blocks.append(
            "\n".join(
                [
                    f"### {experiment.experiment_id}: {experiment.name}",
                    _render_scalar_bullet("purpose", experiment.purpose),
                    _render_list_bullet("datasets", experiment.datasets),
                    _render_list_bullet("baselines", experiment.baselines),
                    _render_list_bullet("metrics", experiment.metrics),
                    _render_scalar_bullet("key_results", experiment.key_results),
                    _render_scalar_bullet("side_findings", experiment.side_findings),
                ]
            )
        )

    journal_lines = [
        f"- journal_{index}: {item.journal_name}   priority: {item.priority}"
        for index, item in enumerate(materials.target_journals, start=1)
    ]

    return (
        prefix
        + "# Paper Materials Submission\n\n"
        + f"{IDENTITY_HEADING}\n"
        + _render_scalar_bullet("working_title", materials.identity.working_title)
        + "\n"
        + _render_scalar_bullet("domain", materials.identity.domain)
        + "\n"
        + _render_scalar_bullet("task", materials.identity.task)
        + "\n\n"
        + f"{ALGORITHM_HEADING}\n\n"
        + "### Input\n"
        + f"{materials.algorithm.input_spec.strip()}\n\n"
        + "### Method / Pipeline\n"
        + f"{materials.algorithm.method_pipeline.strip()}\n\n"
        + "### Output\n"
        + f"{materials.algorithm.output_spec.strip()}\n\n"
        + f"{NOVELTY_HEADING}\n"
        + f"- novelty_1: {novelty_lines[0]}\n"
        + f"- novelty_2: {novelty_lines[1]}\n\n"
        + f"{EXPERIMENTS_HEADING}\n\n"
        + (
            "\n\n".join(experiment_blocks)
            if experiment_blocks
            else "### Exp-1: Main experiment\n- purpose:\n- datasets:\n- baselines:\n- metrics:\n- key_results:\n- side_findings:\n"
        )
        + "\n\n"
        + f"{JOURNALS_HEADING}\n"
        + ("\n".join(journal_lines) if journal_lines else "- journal_1: Target Journal   priority: high")
        + "\n\n"
        + f"{DRAFTS_HEADING}\n"
        + _render_scalar_bullet("current_abstract", materials.existing_drafts.current_abstract)
        + "\n"
        + _render_scalar_bullet("current_intro_p1", materials.existing_drafts.current_intro_p1)
        + "\n"
        + _render_scalar_bullet("figure_1_caption", materials.existing_drafts.figure_1_caption)
        + "\n"
        + _render_scalar_bullet("prior_rejection_feedback", materials.existing_drafts.prior_rejection_feedback)
        + "\n"
    )


def validate_materials(materials: PaperMaterialsRecord) -> list[str]:
    issues: list[str] = []
    if not materials.algorithm.input_spec.strip():
        issues.append("Algorithm input specification is required.")
    if not materials.algorithm.method_pipeline.strip():
        issues.append("Algorithm method/pipeline is required.")
    if not materials.algorithm.output_spec.strip():
        issues.append("Algorithm output specification is required.")
    if not materials.experiments:
        issues.append("At least one experiment block is required.")
    for experiment in materials.experiments:
        if not experiment.key_results.strip():
            issues.append(f"{experiment.experiment_id} is missing key_results.")
    if not materials.target_journals:
        issues.append("At least one target journal is required.")
    return issues


def extract_materials_from_pdf(
    draft_pdf: Path,
    paper_id: str,
    target_journals: list[TargetJournalRecord] | None = None,
) -> tuple[PaperMaterialsRecord, list[str]]:
    text = extract_pdf_text(draft_pdf)
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("===")]
    title = lines[0] if lines else draft_pdf.stem

    def section_for(*names: str) -> str:
        heading_pattern = "|".join(re.escape(name) for name in names)
        match = re.search(
            rf"(?mis)^(?:{heading_pattern})\s*$\n(.*?)(?=^(?:abstract|introduction|method|methods|approach|experiment|experiments|results|discussion|conclusion|references)\s*$|\Z)",
            text,
        )
        return match.group(1).strip() if match else ""

    abstract = section_for("abstract")
    introduction = section_for("introduction")
    method = section_for("method", "methods", "approach")
    results = section_for("experiment", "experiments", "results")
    conclusion = section_for("conclusion", "discussion")

    experiments: list[ExperimentRecord] = []
    if results:
        blocks = [block.strip() for block in re.split(r"\n\s*\n", results) if block.strip()]
        for index, block in enumerate(blocks[:3], start=1):
            experiments.append(
                ExperimentRecord(
                    experiment_id=f"Exp-{index}",
                    name=_first_sentence(block)[:80],
                    purpose=_first_sentence(block)[:160] or None,
                    key_results=block[:400],
                )
            )
    elif conclusion:
        experiments.append(
            ExperimentRecord(
                experiment_id="Exp-1",
                name="PDF extracted evaluation",
                purpose="Recovered from the draft conclusion.",
                key_results=conclusion[:400],
            )
        )

    notes: list[str] = []
    if not method:
        notes.append("Method section extraction confidence is low.")
    if not experiments:
        notes.append("Experiment section extraction confidence is low.")
        experiments.append(
            ExperimentRecord(
                experiment_id="Exp-1",
                name="PDF extracted experiment",
                purpose="Recovered from draft-level text.",
                key_results=(results or conclusion or introduction or abstract or title)[:400],
            )
        )

    materials = PaperMaterialsRecord(
        paper_id=paper_id,
        mode="draft_reframing",
        identity=PaperIdentityRecord(working_title=title, domain=None, task=None),
        algorithm=AlgorithmRecord(
            input_spec=_first_sentence(introduction or abstract) or "Recovered from the draft introduction.",
            method_pipeline=method or "Recovered from the draft; please revise manually.",
            output_spec=_first_sentence(conclusion or abstract) or "Recovered from the draft conclusion.",
            novelty_claims=[_first_sentence(abstract)] if abstract else [],
        ),
        experiments=experiments,
        target_journals=target_journals or [],
        existing_drafts=ExistingDraftsRecord(
            current_abstract=abstract or None,
            current_intro_p1=_first_sentence(introduction) or None,
        ),
        extraction_notes=notes,
    )
    return materials, notes


def _infer_figure_type(filename: str) -> str:
    lowered = filename.lower()
    if "pipeline" in lowered or "workflow" in lowered or "framework" in lowered:
        return "pipeline"
    if "ablation" in lowered or "heatmap" in lowered:
        return "ablation"
    if "trend" in lowered or "curve" in lowered:
        return "trend"
    if "distribution" in lowered or "hist" in lowered:
        return "distribution"
    if "case" in lowered:
        return "case_study"
    return "main_result"


def _infer_figure_claims(path: Path) -> tuple[str, str, str | None]:
    stem = path.stem.replace("_", " ").replace("-", " ").strip()
    lowered = stem.lower()
    if any(token in lowered for token in ("workflow", "pipeline", "framework", "fig 1", "fig 01")):
        return (
            stem or "Main workflow figure",
            "This figure summarizes the analysis workflow and scale transitions in the paper.",
            None,
        )
    if "typology" in lowered:
        return (
            stem or "Typology figure",
            "This figure visualizes the governance-space typology and the spatial contrast between diagnosed regions.",
            None,
        )
    if lowered.startswith("page "):
        return (
            stem or "Supplementary manuscript page",
            "This image is a manuscript page snapshot and should not be treated as standalone evidence without recaptioning.",
            None,
        )
    return (
        stem or "Main result figure",
        "This figure likely carries a main experimental or diagnostic result and should be aligned with the paper thesis.",
        None,
    )


def load_or_build_figures_manifest(workspace: JournalFitWorkspace) -> FiguresManifestRecord:
    if workspace.figures_manifest_path.exists():
        manifest = FiguresManifestRecord.model_validate(read_json(workspace.figures_manifest_path))
        upgraded: list[FigureRecord] = []
        for figure in manifest.figures:
            path = workspace.root / figure.path
            caption, visual_claim, numeric_claim = _infer_figure_claims(path if path.exists() else Path(figure.path))
            placeholder_claim = figure.visual_claim.strip().endswith("is important to the paper story.")
            upgraded.append(
                figure.model_copy(
                    update={
                        "type": figure.type or _infer_figure_type(path.name if path.exists() else figure.path),
                        "caption_original": figure.caption_original or caption,
                        "what_it_shows": figure.what_it_shows or caption,
                        "visual_claim": visual_claim if placeholder_claim or not figure.visual_claim.strip() else figure.visual_claim,
                        "numeric_claim": figure.numeric_claim or numeric_claim,
                    }
                )
            )
        return FiguresManifestRecord(figures=upgraded)

    figure_files = sorted(
        [path for path in workspace.figures_dir.iterdir() if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf"}]
    )
    figures: list[FigureRecord] = []
    for index, path in enumerate(figure_files, start=1):
        caption, visual_claim, numeric_claim = _infer_figure_claims(path)
        figures.append(
            FigureRecord(
                id=f"F{index:02d}",
                path=str(path.relative_to(workspace.root)).replace("\\", "/"),
                type=_infer_figure_type(path.name),  # type: ignore[arg-type]
                linked_experiments=["Exp-1"],
                caption_original=caption,
                what_it_shows=caption,
                visual_claim=visual_claim,
                numeric_claim=numeric_claim,
                confidence="low",
            )
        )
    return FiguresManifestRecord(figures=figures)


def load_materials_from_workspace(workspace: JournalFitWorkspace, mode: JournalFitMode) -> PaperMaterialsRecord:
    if not workspace.input_path.exists():
        raise ValidationError(f"Input file not found: {workspace.input_path}")
    return parse_materials_markdown(read_text(workspace.input_path), workspace.paper_id, mode)
