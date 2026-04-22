from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


JournalFitMode = Literal["from_scratch", "draft_reframing"]
PriorityLevel = Literal["high", "medium", "low"]
EvidenceStrength = Literal["strong", "medium", "weak"]
AssetCategory = Literal[
    "methodology",
    "performance",
    "generality",
    "theory",
    "efficiency",
    "application",
    "interpretability",
]
AngleType = Literal[
    "method-novelty",
    "application-driven",
    "theoretical-insight",
    "efficiency-focused",
    "unification",
    "empirical-discovery",
    "systems-contribution",
]
FigureType = Literal[
    "pipeline",
    "main_result",
    "ablation",
    "case_study",
    "trend",
    "distribution",
    "qualitative",
]
PatchType = Literal[
    "new-ablation-snippet",
    "new-analysis",
    "new-figure",
    "rewording",
    "appendix-note",
    "none",
]


class PaperIdentityRecord(BaseModel):
    working_title: str
    domain: str | None = None
    task: str | None = None


class AlgorithmRecord(BaseModel):
    input_spec: str
    method_pipeline: str
    output_spec: str
    novelty_claims: list[str] = Field(default_factory=list)


class ExperimentRecord(BaseModel):
    experiment_id: str
    name: str
    purpose: str | None = None
    datasets: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    key_results: str
    side_findings: str | None = None


class TargetJournalRecord(BaseModel):
    journal_name: str
    priority: PriorityLevel = "medium"


class ExistingDraftsRecord(BaseModel):
    current_abstract: str | None = None
    current_intro_p1: str | None = None
    figure_1_caption: str | None = None
    prior_rejection_feedback: str | None = None


class PaperMaterialsRecord(BaseModel):
    paper_id: str
    mode: JournalFitMode
    identity: PaperIdentityRecord
    algorithm: AlgorithmRecord
    experiments: list[ExperimentRecord] = Field(default_factory=list)
    target_journals: list[TargetJournalRecord] = Field(default_factory=list)
    existing_drafts: ExistingDraftsRecord = Field(default_factory=ExistingDraftsRecord)
    extraction_notes: list[str] = Field(default_factory=list)


class FigureRecord(BaseModel):
    id: str
    path: str
    type: FigureType = "main_result"
    linked_experiments: list[str] = Field(default_factory=list)
    caption_original: str = ""
    what_it_shows: str = ""
    visual_claim: str = ""
    numeric_claim: str | None = None
    confidence: PriorityLevel = "medium"


class FiguresManifestRecord(BaseModel):
    figures: list[FigureRecord] = Field(default_factory=list)


class RunSourceRecord(BaseModel):
    has_pdf: bool = False
    pdf_path: str | None = None
    figures_count: int = 0
    extraction_confidence: PriorityLevel = "high"
    low_confidence_fields: list[str] = Field(default_factory=list)


class RunMetaRecord(BaseModel):
    paper_id: str
    mode: JournalFitMode
    created_at: str
    source: RunSourceRecord
    target_journals: list[str] = Field(default_factory=list)
    target_journals_normalized: list[str] = Field(default_factory=list)


class EvidenceRefRecord(BaseModel):
    type: Literal["experiment", "figure", "method"]
    ref: str
    claim_type: Literal["visual", "numeric"] | None = None


class AssetRecord(BaseModel):
    id: str
    category: AssetCategory
    content: str
    evidence_refs: list[EvidenceRefRecord] = Field(default_factory=list)
    strength: EvidenceStrength
    strength_rationale: str
    caveats: str | None = None


class AssetInventoryRecord(BaseModel):
    paper_id: str
    generated_at: str
    assets: list[AssetRecord] = Field(default_factory=list)


class CurrentContributionRecord(BaseModel):
    bullet: str
    mapped_assets: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = "weak"


class OverclaimedItemRecord(BaseModel):
    claim: str
    issue: str


class ExistingNarrativeRecord(BaseModel):
    extracted_from: str
    one_line_thesis: str
    main_angle: AngleType
    current_contributions: list[CurrentContributionRecord] = Field(default_factory=list)
    unused_strong_assets: list[str] = Field(default_factory=list)
    overclaimed_items: list[OverclaimedItemRecord] = Field(default_factory=list)
    structural_issues: list[str] = Field(default_factory=list)


class SourceFetchRecord(BaseModel):
    fetched: bool = False
    url: str | None = None
    reason: str | None = None
    paper_count: int | None = None


class JournalSourcesRecord(BaseModel):
    semantic_scholar: SourceFetchRecord = Field(default_factory=SourceFetchRecord)
    web_scope: SourceFetchRecord = Field(default_factory=SourceFetchRecord)
    web_guidelines: SourceFetchRecord = Field(default_factory=SourceFetchRecord)
    web_editorials: SourceFetchRecord = Field(default_factory=SourceFetchRecord)


class ContributionTypeWeightRecord(BaseModel):
    type: AngleType
    weight: float


class WritingStyleRecord(BaseModel):
    length: Literal["compact", "standard", "expansive"] = "standard"
    tone: Literal["formal", "accessible"] = "formal"
    jargon_density: Literal["high", "medium", "low"] = "medium"


class ReferencePaperRecord(BaseModel):
    title: str
    year: int | None = None
    venue: str | None = None
    citation_count: int | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    relevance_to_user: PriorityLevel = "medium"
    source: Literal["semantic_scholar", "web"] = "semantic_scholar"


class JournalProfileRecord(BaseModel):
    journal_name: str
    venue_normalized: str
    slug: str
    cached_at: str
    cache_ttl_days: int = 14
    sources: JournalSourcesRecord = Field(default_factory=JournalSourcesRecord)
    aims_scope_summary: str = ""
    preferred_contribution_types: list[ContributionTypeWeightRecord] = Field(default_factory=list)
    preferred_narrative_patterns: list[str] = Field(default_factory=list)
    writing_style: WritingStyleRecord = Field(default_factory=WritingStyleRecord)
    typical_structure: list[str] = Field(default_factory=list)
    rising_subtopics: list[str] = Field(default_factory=list)
    reviewer_red_flags: list[str] = Field(default_factory=list)
    reference_papers: list[ReferencePaperRecord] = Field(default_factory=list)
    confidence: PriorityLevel = "medium"


class NarrativeClaimRecord(BaseModel):
    claim: str
    supporting_assets: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = "weak"


class NarrativeCandidateRecord(BaseModel):
    id: str
    one_line_thesis: str
    main_angle: AngleType
    target_reader: str
    main_claims: list[NarrativeClaimRecord] = Field(default_factory=list)
    assets_to_foreground: list[str] = Field(default_factory=list)
    assets_to_background: list[str] = Field(default_factory=list)
    implicit_assumptions: list[str] = Field(default_factory=list)
    biggest_risk: str
    required_framing_moves: list[str] = Field(default_factory=list)


class FitScoresRecord(BaseModel):
    taste_fit: int
    evidence_support: int
    differentiation: int
    risk: int


class FitMatrixEntryRecord(BaseModel):
    narrative_id: str
    journal_slug: str
    scores: FitScoresRecord
    weighted_total: float
    one_line_rationale: str
    acceptance_expectation: Literal["low", "medium", "medium-high", "high"]


class TopCombinationRecord(BaseModel):
    narrative_id: str
    journal_slug: str
    rank: int


class FitMatrixRecord(BaseModel):
    matrix: list[FitMatrixEntryRecord] = Field(default_factory=list)
    top_combinations: list[TopCombinationRecord] = Field(default_factory=list)


class ReviewQuestionRecord(BaseModel):
    qid: str
    concern: str
    severity: PriorityLevel
    addressable_by_existing_data: Literal["yes", "partial", "no"]
    patch_type: PatchType
    patch_cost_hours: int
    patch_description: str


class ReviewTargetRecord(BaseModel):
    target_narrative: str
    target_journal: str
    questions: list[ReviewQuestionRecord] = Field(default_factory=list)


class AdversarialReviewRecord(BaseModel):
    reviews: list[ReviewTargetRecord] = Field(default_factory=list)


class PatchRecord(BaseModel):
    target_narrative: str
    target_journal: str
    qid: str
    severity: PriorityLevel
    patch_type: PatchType
    patch_cost_hours: int
    patch_description: str


class PatchListRecord(BaseModel):
    patches: list[PatchRecord] = Field(default_factory=list)


def export_journal_fit_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {
        "input_materials": PaperMaterialsRecord,
        "run_meta": RunMetaRecord,
        "figures_manifest": FiguresManifestRecord,
        "assets": AssetInventoryRecord,
        "existing_narrative": ExistingNarrativeRecord,
        "journal_profile": JournalProfileRecord,
        "narrative_candidate": NarrativeCandidateRecord,
        "fit_matrix": FitMatrixRecord,
        "adversarial_review": AdversarialReviewRecord,
        "patches": PatchListRecord,
    }
    written: list[Path] = []
    for name, model in models.items():
        path = output_dir / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written
