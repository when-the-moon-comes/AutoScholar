from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import json
from pydantic import BaseModel, Field


class PaperRecord(BaseModel):
    rank: int | None = None
    paper_id: str | None = None
    title: str
    year: int | None = None
    authors: list[str] = Field(default_factory=list)
    venue: str | None = None
    url: str | None = None
    abstract: str | None = None
    citation_count: int | None = None
    influential_citation_count: int | None = None
    doi: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    is_open_access: bool | None = None
    open_access_pdf_url: str | None = None


class ClaimRecord(BaseModel):
    claim_id: str
    section: str
    source_lines: str
    claim_text: str
    claim_type: str
    priority: str
    short_label: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryRecord(BaseModel):
    query_id: str
    claim_id: str
    query_text: str
    short_label: str
    core_keywords: list[str] = Field(default_factory=list)
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResultRecord(BaseModel):
    query_id: str
    claim_id: str
    query_text: str
    short_label: str
    endpoint: str
    search_options: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 1
    status_code: int
    page_count: int = 1
    total_hits: int | None = None
    paper_count: int = 0
    papers: list[PaperRecord] = Field(default_factory=list)
    retrieved_at: str


class SearchFailureRecord(BaseModel):
    query_id: str
    claim_id: str
    query_text: str
    endpoint: str
    search_options: dict[str, Any] = Field(default_factory=dict)
    error_type: str
    error: str
    failed_at: str


class QueryReviewRecord(BaseModel):
    query_id: str
    claim_id: str
    status: Literal["keep", "review", "rewrite", "exclude"]
    reason: str
    paper_count: int
    total_hits: int | None = None
    max_citations: int = 0


class ScoreBreakdown(BaseModel):
    title_claim_overlap: int = 0
    abstract_claim_overlap: int = 0
    title_query_overlap: int = 0
    abstract_query_overlap: int = 0
    support_count: int = 0
    weighted_support: float = 0.0
    best_rank_reciprocal: float = 0.0
    mean_rank_reciprocal: float = 0.0
    topical_fit: float = 0.0
    support_signal: float = 0.0
    retrieval_signal: float = 0.0
    authority_signal: float = 0.0
    final_score: float = 0.0


class QueryHitRecord(BaseModel):
    query_id: str
    status: str
    reason: str
    paper_rank: int
    status_weight: float


class SelectedPaperRecord(BaseModel):
    rank: int
    paper_key: str
    paper: PaperRecord
    score_breakdown: ScoreBreakdown
    query_hits: list[QueryHitRecord] = Field(default_factory=list)


class SelectedCitationRecord(BaseModel):
    claim: ClaimRecord
    status: Literal["ready", "review", "weak"]
    note: str | None = None
    candidate_count: int = 0
    selected_papers: list[SelectedPaperRecord] = Field(default_factory=list)
    excluded_queries: dict[str, str] = Field(default_factory=dict)
    query_reviews: list[QueryReviewRecord] = Field(default_factory=list)


class SeedPaperRecord(BaseModel):
    rank: int
    paper_key: str
    paper: PaperRecord
    query_support_count: int = 0
    supporting_query_ids: list[str] = Field(default_factory=list)
    claim_overlap: int = 0
    query_overlap: int = 0


class CorrectionCandidateRecord(BaseModel):
    rank: int
    paper_key: str
    paper: PaperRecord
    origin: str
    query_support_count: int = 0
    supporting_query_ids: list[str] = Field(default_factory=list)
    recommendation_support_count: int = 0
    recommended_by_seed_ids: list[str] = Field(default_factory=list)
    claim_overlap: int = 0
    query_overlap: int = 0


class RecommendationCorrectionRecord(BaseModel):
    claim: ClaimRecord
    current_status: str
    status: Literal["pending_api", "rewrite_needed", "blocked", "corrected_review", "corrected_ready"]
    trigger_reasons: list[str] = Field(default_factory=list)
    recommendation_method: str
    seed_selection_mode: str
    claim_note: str | None = None
    query_reviews: list[QueryReviewRecord] = Field(default_factory=list)
    seeds: list[SeedPaperRecord] = Field(default_factory=list)
    negative_seeds: list[SeedPaperRecord] = Field(default_factory=list)
    recommendation_failures: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[CorrectionCandidateRecord] = Field(default_factory=list)
    generated_at: str


class ScoreCard(BaseModel):
    literature_support: float
    evidence_quality: float
    implementation_feasibility: float
    novelty_risk: float
    overall: float


class EvidenceSummary(BaseModel):
    claim_id: str
    status: str
    selected_paper_count: int
    top_papers: list[str] = Field(default_factory=list)


class EvidencePaperRecord(BaseModel):
    paper_id: str | None = None
    title: str
    year: int | None = None
    venue: str | None = None
    citation_count: int | None = None
    doi: str | None = None
    url: str | None = None
    support_tier: Literal["direct", "adjacent", "context"]
    support_reason: str


class EvidenceClaimRecord(BaseModel):
    claim_id: str
    short_label: str | None = None
    claim_text: str
    claim_type: str
    priority: str
    status: Literal["ready", "review", "weak"]
    evidence_strength: Literal["strong", "mixed", "weak"]
    narrative: str
    notes: list[str] = Field(default_factory=list)
    top_papers: list[EvidencePaperRecord] = Field(default_factory=list)


class EvidenceMapRecord(BaseModel):
    idea_id: str
    title: str
    language: Literal["zh", "en"]
    recommendation: Literal["recommended", "needs-revision", "not-ready"]
    executive_summary: str
    strongest_claim_ids: list[str] = Field(default_factory=list)
    weakest_claim_ids: list[str] = Field(default_factory=list)
    claims: list[EvidenceClaimRecord] = Field(default_factory=list)
    reference_papers: list[EvidencePaperRecord] = Field(default_factory=list)
    generated_at: str


class ReportValidationIssueRecord(BaseModel):
    level: Literal["error", "warning"]
    code: str
    message: str


class ReportValidationRecord(BaseModel):
    kind: Literal["feasibility", "deep-dive"]
    report_path: str
    passed: bool
    issues: list[ReportValidationIssueRecord] = Field(default_factory=list)
    checked_at: str


class ReportValidationBundleRecord(BaseModel):
    feasibility: ReportValidationRecord | None = None
    deep_dive: ReportValidationRecord | None = None


class IdeaAssessmentRecord(BaseModel):
    idea_id: str
    title: str
    summary: str
    recommendation: Literal["recommended", "needs-revision", "not-ready"]
    scores: ScoreCard
    risks: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSummary] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    generated_at: str


class WorkspaceInputs(BaseModel):
    manuscript: str | None = None
    idea_source: str | None = None


class WorkspaceConfigs(BaseModel):
    search: str
    recommendation: str
    citation_rules: str
    idea_evaluation: str | None = None


class WorkspaceArtifacts(BaseModel):
    claims: str
    queries: str
    search_results_raw: str
    search_results_deduped: str
    query_reviews: str
    search_failures: str | None = None
    recommendation_corrections: str
    selected_citations: str
    idea_assessment: str
    evidence_map: str | None = None
    report_validation: str | None = None
    references_bib: str | None = None


class WorkspaceReports(BaseModel):
    prescreen: str
    shortlist: str
    feasibility: str
    deep_dive: str


class WorkspaceManifest(BaseModel):
    schema_version: str
    workspace_type: Literal["citation-paper", "idea-evaluation"]
    report_language: Literal["zh", "en"]
    inputs: WorkspaceInputs
    configs: WorkspaceConfigs
    artifacts: WorkspaceArtifacts
    reports: WorkspaceReports


def export_json_schemas(output_dir: Path) -> list[Path]:
    from autoscholar.journal_fit.models import export_journal_fit_schemas

    output_dir.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {
        "workspace_manifest": WorkspaceManifest,
        "claim_record": ClaimRecord,
        "query_record": QueryRecord,
        "search_result_record": SearchResultRecord,
        "query_review_record": QueryReviewRecord,
        "selected_citation_record": SelectedCitationRecord,
        "idea_assessment_record": IdeaAssessmentRecord,
        "evidence_map_record": EvidenceMapRecord,
        "report_validation_bundle_record": ReportValidationBundleRecord,
        "recommendation_correction_record": RecommendationCorrectionRecord,
    }
    written: list[Path] = []
    for name, model in models.items():
        path = output_dir / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    written.extend(export_journal_fit_schemas(output_dir))
    return written
