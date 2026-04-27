from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DEFAULT_FIELDS = (
    "paperId,title,year,authors,url,abstract,citationCount,"
    "influentialCitationCount,venue,externalIds,isOpenAccess,openAccessPdf"
)


class SearchFilters(BaseModel):
    sort: str | None = None
    publication_types: list[str] = Field(default_factory=list)
    open_access_pdf: bool | None = None
    min_citation_count: int | None = None
    publication_date_or_year: str | None = None
    year: str | None = None
    venue: str | None = None
    fields_of_study: list[str] = Field(default_factory=list)


class SearchExecutionProfile(BaseModel):
    workers: int = 1
    max_retries: int = 5
    retry_delay: float = 1.0
    pause_seconds: float = 0.0


class SearchConfig(BaseModel):
    endpoint: Literal["relevance", "bulk"] = "relevance"
    limit: int = 10
    timeout: float = 30.0
    fields: str = DEFAULT_FIELDS
    filters: SearchFilters = Field(default_factory=SearchFilters)
    mode: Literal["single_thread", "multi_thread"] = "single_thread"
    single_thread: SearchExecutionProfile = Field(
        default_factory=lambda: SearchExecutionProfile(workers=1, pause_seconds=1.0)
    )
    multi_thread: SearchExecutionProfile = Field(
        default_factory=lambda: SearchExecutionProfile(workers=8, pause_seconds=0.0)
    )

    def profile(self) -> SearchExecutionProfile:
        return self.single_thread if self.mode == "single_thread" else self.multi_thread

    def search_options(self) -> dict[str, object]:
        options: dict[str, object] = {
            "endpoint": self.endpoint,
            "limit": self.limit,
            "fields": self.fields,
        }
        filters = self.filters.model_dump(exclude_none=True)
        if filters:
            options["filters"] = filters
        return options


class QueryStatusWeights(BaseModel):
    keep: float = 1.0
    review: float = 0.6
    rewrite: float = 0.25
    exclude: float = 0.0

    def for_status(self, status: str) -> float:
        return getattr(self, status, 0.0)


class ScoreWeights(BaseModel):
    title_claim_overlap: float = 4.0
    abstract_claim_overlap: float = 1.75
    title_query_overlap: float = 2.5
    abstract_query_overlap: float = 1.0
    support_count: float = 0.75
    weighted_support: float = 2.5
    best_rank_reciprocal: float = 3.0
    mean_rank_reciprocal: float = 1.5
    influential_citations: float = 0.8
    citations: float = 0.3


class CitationRulesConfig(BaseModel):
    stopwords: list[str] = Field(default_factory=list)
    excluded_queries: dict[str, str] = Field(default_factory=dict)
    excluded_papers: dict[str, str] = Field(default_factory=dict)
    claim_notes: dict[str, str] = Field(default_factory=dict)
    selected_papers_limit: int = 3
    query_status_weights: QueryStatusWeights = Field(default_factory=QueryStatusWeights)
    score_weights: ScoreWeights = Field(default_factory=ScoreWeights)


class TriggerSettings(BaseModel):
    min_selected_papers: int = 2
    min_cross_query_support: int = 2
    low_citation_threshold: int = 10
    max_low_signal_candidates: int = 2
    include_review_status: bool = True
    include_claim_notes: bool = True


class ClaimSeedControl(BaseModel):
    positive: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


class SeedSettings(BaseModel):
    selection_mode: Literal["auto", "hybrid", "manual"] = "auto"
    max_seeds_per_claim: int = 2
    min_total_overlap: int = 2
    claim_overrides: dict[str, ClaimSeedControl] = Field(default_factory=dict)


class RecommendationSettings(BaseModel):
    method: Literal["single_seed", "positive_seed_list"] = "positive_seed_list"
    per_seed_limit: int = 5
    top_candidates_per_claim: int = 5
    ready_candidate_count: int = 2
    ready_min_total_overlap: int = 3
    pause_seconds: float = 0.2
    fields: str = DEFAULT_FIELDS


class RecommendationConfig(BaseModel):
    trigger: TriggerSettings = Field(default_factory=TriggerSettings)
    seed: SeedSettings = Field(default_factory=SeedSettings)
    recommendations: RecommendationSettings = Field(default_factory=RecommendationSettings)


class IdeaEvaluationConfig(BaseModel):
    top_evidence_per_claim: int = 2
    ready_threshold: float = 0.7
    revision_threshold: float = 0.45
    report_top_papers_per_claim: int = 3
    report_reference_limit: int = 12
    report_claim_summary_limit: int = 3
