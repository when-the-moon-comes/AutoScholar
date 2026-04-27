from __future__ import annotations

from pathlib import Path

from autoscholar.citation.config import IdeaEvaluationConfig
from autoscholar.citation.common import utc_now
from autoscholar.io import read_jsonl, read_text, read_yaml, write_json
from autoscholar.models import ClaimRecord, EvidenceSummary, IdeaAssessmentRecord, ScoreCard, SelectedCitationRecord
from autoscholar.workspace import Workspace


def _extract_title(source_text: str, workspace: Workspace) -> str:
    for line in source_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return workspace.root.name


def _extract_summary(source_text: str) -> str:
    paragraphs = [part.strip() for part in source_text.split("\n\n") if part.strip()]
    for paragraph in paragraphs:
        if not paragraph.startswith("#"):
            return paragraph[:500]
    return "No idea summary provided yet."


def _build_scores(records: list[SelectedCitationRecord]) -> ScoreCard:
    if not records:
        return ScoreCard(
            literature_support=0.0,
            evidence_quality=0.0,
            implementation_feasibility=0.0,
            novelty_risk=0.5,
            overall=0.0,
        )

    claim_count = len(records)
    ready_count = sum(1 for record in records if record.status == "ready")
    paper_count = sum(len(record.selected_papers) for record in records)
    avg_papers = paper_count / claim_count if claim_count else 0.0
    avg_citations = 0.0
    citation_denominator = 0
    for record in records:
        for paper in record.selected_papers:
            avg_citations += float(paper.paper.citation_count or 0)
            citation_denominator += 1
    avg_citations = avg_citations / citation_denominator if citation_denominator else 0.0

    literature_support = min(1.0, ready_count / max(claim_count, 1))
    evidence_quality = min(1.0, avg_citations / 50.0)
    implementation_feasibility = min(1.0, avg_papers / 3.0)
    novelty_risk = max(0.0, 1.0 - literature_support * 0.8)
    overall = min(
        1.0,
        literature_support * 0.4 + evidence_quality * 0.25 + implementation_feasibility * 0.35,
    )
    return ScoreCard(
        literature_support=round(literature_support, 3),
        evidence_quality=round(evidence_quality, 3),
        implementation_feasibility=round(implementation_feasibility, 3),
        novelty_risk=round(novelty_risk, 3),
        overall=round(overall, 3),
    )


def _build_risks(records: list[SelectedCitationRecord]) -> list[str]:
    risks: list[str] = []
    weak = [record.claim.claim_id for record in records if record.status == "weak"]
    review = [record.claim.claim_id for record in records if record.status == "review"]
    if weak:
        risks.append(f"Weak literature coverage remains for claims: {', '.join(weak[:5])}.")
    if review:
        risks.append(f"Manual review is still required for claims: {', '.join(review[:5])}.")
    if not risks:
        risks.append("No major structural risk was detected from the current evidence bundle.")
    return risks


def _build_next_actions(records: list[SelectedCitationRecord]) -> list[str]:
    actions = [
        "Review claim statuses and rewrite weak queries before treating the idea as publication-ready.",
        "Validate the top supporting papers against the intended contribution and problem framing.",
    ]
    if any(record.status != "ready" for record in records):
        actions.append("Run another recommendation pass or rewrite the weakest claims after manual inspection.")
    else:
        actions.append("Use the current evidence bundle to draft the related-work and problem-definition sections.")
    return actions


def assess_idea(workspace: Workspace, config: IdeaEvaluationConfig) -> IdeaAssessmentRecord:
    source_path = workspace.require_path("inputs", "idea_source")
    source_text = read_text(source_path)
    selected_path = workspace.require_path("artifacts", "selected_citations")
    selected_records = read_jsonl(selected_path, SelectedCitationRecord) if selected_path.exists() else []

    scores = _build_scores(selected_records)
    recommendation = "recommended"
    if scores.overall < config.revision_threshold:
        recommendation = "not-ready"
    elif scores.overall < config.ready_threshold:
        recommendation = "needs-revision"

    evidence = [
        EvidenceSummary(
            claim_id=record.claim.claim_id,
            status=record.status,
            selected_paper_count=len(record.selected_papers),
            top_papers=[item.paper.title for item in record.selected_papers[: config.top_evidence_per_claim]],
        )
        for record in selected_records
    ]

    assessment = IdeaAssessmentRecord(
        idea_id=workspace.root.name,
        title=_extract_title(source_text, workspace),
        summary=_extract_summary(source_text),
        recommendation=recommendation,
        scores=scores,
        risks=_build_risks(selected_records),
        evidence=evidence,
        next_actions=_build_next_actions(selected_records),
        generated_at=utc_now(),
    )
    write_json(workspace.require_path("artifacts", "idea_assessment"), assessment.model_dump(mode="json"))
    return assessment
