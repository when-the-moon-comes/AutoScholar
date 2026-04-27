from __future__ import annotations

import math
from collections import defaultdict

from autoscholar.citation.common import (
    claim_status_for_selected,
    load_rules,
    paper_key,
    paper_reference_aliases,
    paper_strength,
    review_by_query_id,
    rules_stopwords,
    score_authority,
    tokenize,
)
from autoscholar.citation.config import CitationRulesConfig
from autoscholar.io import read_json_list, read_jsonl, write_jsonl
from autoscholar.models import (
    ClaimRecord,
    CorrectionCandidateRecord,
    QueryRecord,
    QueryHitRecord,
    QueryReviewRecord,
    RecommendationCorrectionRecord,
    ScoreBreakdown,
    SearchResultRecord,
    SelectedCitationRecord,
    SelectedPaperRecord,
)
from autoscholar.workspace import Workspace


def _paper_exclusion_reason(paper_aliases: list[str], rules: CitationRulesConfig) -> str | None:
    for alias in paper_aliases:
        reason = rules.excluded_papers.get(alias)
        if reason:
            return reason
    return None


def _score_claim_paper(
    claim: ClaimRecord,
    query_records: list[QueryRecord],
    query_reviews: list[QueryReviewRecord],
    candidate_paper,
    source_hits: list[dict],
    recommendation_support_count: int,
    rules: CitationRulesConfig,
) -> tuple[float, ScoreBreakdown, list[QueryHitRecord]]:
    stopwords = rules_stopwords(rules)
    claim_tokens = tokenize(claim.claim_text, stopwords)
    query_tokens = set()
    for query in query_records:
        query_tokens |= tokenize(query.query_text, stopwords)
        query_tokens |= tokenize(query.short_label, stopwords)
        query_tokens |= {item.lower() for item in query.core_keywords if len(item.strip()) >= 4}

    title_tokens = tokenize(candidate_paper.title, stopwords)
    abstract_tokens = tokenize(candidate_paper.abstract or "", stopwords)

    query_review_by_id = review_by_query_id(query_reviews)
    query_hits: list[QueryHitRecord] = []
    support_count = 0
    weighted_support = float(recommendation_support_count) * 0.8
    best_rank_reciprocal = 0.0
    mean_rank_reciprocal = 0.0

    for hit in source_hits:
        review = query_review_by_id[hit["query_id"]]
        status_weight = rules.query_status_weights.for_status(review.status)
        query_hit = QueryHitRecord(
            query_id=hit["query_id"],
            status=review.status,
            reason=review.reason,
            paper_rank=hit["paper_rank"],
            status_weight=status_weight,
        )
        query_hits.append(query_hit)
        support_count += 1
        weighted_support += status_weight
        rank_score = status_weight / max(hit["paper_rank"], 1)
        best_rank_reciprocal = max(best_rank_reciprocal, rank_score)
        mean_rank_reciprocal += rank_score

    if query_hits:
        mean_rank_reciprocal /= len(query_hits)

    title_claim_overlap = len(claim_tokens & title_tokens)
    abstract_claim_overlap = len(claim_tokens & abstract_tokens)
    title_query_overlap = len(query_tokens & title_tokens)
    abstract_query_overlap = len(query_tokens & abstract_tokens)
    influential_log, citations_log = score_authority(candidate_paper)
    weights = rules.score_weights

    topical_fit = (
        weights.title_claim_overlap * title_claim_overlap
        + weights.abstract_claim_overlap * abstract_claim_overlap
        + weights.title_query_overlap * title_query_overlap
        + weights.abstract_query_overlap * abstract_query_overlap
    )
    support_signal = weights.support_count * support_count + weights.weighted_support * weighted_support
    retrieval_signal = (
        weights.best_rank_reciprocal * best_rank_reciprocal
        + weights.mean_rank_reciprocal * mean_rank_reciprocal
    )
    authority_signal = (
        weights.influential_citations * influential_log + weights.citations * citations_log
    )
    final_score = topical_fit + support_signal + retrieval_signal + authority_signal

    breakdown = ScoreBreakdown(
        title_claim_overlap=title_claim_overlap,
        abstract_claim_overlap=abstract_claim_overlap,
        title_query_overlap=title_query_overlap,
        abstract_query_overlap=abstract_query_overlap,
        support_count=support_count,
        weighted_support=weighted_support,
        best_rank_reciprocal=best_rank_reciprocal,
        mean_rank_reciprocal=mean_rank_reciprocal,
        topical_fit=topical_fit,
        support_signal=support_signal,
        retrieval_signal=retrieval_signal,
        authority_signal=authority_signal,
        final_score=final_score,
    )
    return final_score, breakdown, sorted(query_hits, key=lambda item: item.paper_rank)


def _load_correction_candidates(workspace: Workspace) -> dict[str, RecommendationCorrectionRecord]:
    path = workspace.require_path("artifacts", "recommendation_corrections")
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    records = read_jsonl(path, RecommendationCorrectionRecord)
    return {record.claim.claim_id: record for record in records}


def build_shortlist(workspace: Workspace, rules: CitationRulesConfig) -> list[SelectedCitationRecord]:
    claims = {item.claim_id: item for item in read_jsonl(workspace.require_path("artifacts", "claims"), ClaimRecord)}
    queries = {item.query_id: item for item in read_jsonl(workspace.require_path("artifacts", "queries"), QueryRecord)}
    records = read_jsonl(workspace.require_path("artifacts", "search_results_deduped"), SearchResultRecord)
    query_reviews = read_json_list(workspace.require_path("artifacts", "query_reviews"), "query_reviews", QueryReviewRecord)
    corrections = _load_correction_candidates(workspace)

    by_claim_records: dict[str, list[SearchResultRecord]] = defaultdict(list)
    by_claim_reviews: dict[str, list[QueryReviewRecord]] = defaultdict(list)
    by_claim_queries: dict[str, list[QueryRecord]] = defaultdict(list)

    for query in queries.values():
        by_claim_queries[query.claim_id].append(query)
    for record in records:
        by_claim_records[record.claim_id].append(record)
    for review in query_reviews:
        by_claim_reviews[review.claim_id].append(review)

    shortlist: list[SelectedCitationRecord] = []
    for claim_id in sorted(claims):
        claim = claims[claim_id]
        claim_records = by_claim_records.get(claim_id, [])
        claim_reviews = sorted(by_claim_reviews.get(claim_id, []), key=lambda item: item.query_id)
        claim_queries = by_claim_queries.get(claim_id, [])

        candidate_map: dict[str, dict] = {}
        for record in claim_records:
            review = next((item for item in claim_reviews if item.query_id == record.query_id), None)
            if review is None or review.status == "exclude":
                continue
            for paper in record.papers:
                aliases = paper_reference_aliases(paper)
                if _paper_exclusion_reason(aliases, rules):
                    continue
                key = paper_key(paper)
                entry = candidate_map.setdefault(
                    key,
                    {"paper": paper, "source_hits": [], "recommendation_support_count": 0},
                )
                if paper_strength(paper) > paper_strength(entry["paper"]):
                    entry["paper"] = paper
                entry["source_hits"].append({"query_id": record.query_id, "paper_rank": paper.rank or 999})

        correction = corrections.get(claim_id)
        if correction:
            for candidate in correction.candidates:
                aliases = paper_reference_aliases(candidate.paper)
                if _paper_exclusion_reason(aliases, rules):
                    continue
                key = paper_key(candidate.paper)
                entry = candidate_map.setdefault(
                    key,
                    {"paper": candidate.paper, "source_hits": [], "recommendation_support_count": 0},
                )
                if paper_strength(candidate.paper) > paper_strength(entry["paper"]):
                    entry["paper"] = candidate.paper
                entry["recommendation_support_count"] = max(
                    entry["recommendation_support_count"],
                    candidate.recommendation_support_count,
                )

        ranked: list[tuple[float, SelectedPaperRecord]] = []
        for paper_candidate in candidate_map.values():
            paper = paper_candidate["paper"]
            score, breakdown, query_hits = _score_claim_paper(
                claim=claim,
                query_records=claim_queries,
                query_reviews=claim_reviews,
                candidate_paper=paper,
                source_hits=paper_candidate["source_hits"],
                recommendation_support_count=paper_candidate["recommendation_support_count"],
                rules=rules,
            )
            ranked.append(
                (
                    score,
                    SelectedPaperRecord(
                        rank=0,
                        paper_key=paper_key(paper),
                        paper=paper,
                        score_breakdown=breakdown,
                        query_hits=query_hits,
                    ),
                )
            )

        ranked.sort(
            key=lambda item: (
                item[0],
                item[1].score_breakdown.topical_fit,
                item[1].score_breakdown.support_signal,
                item[1].score_breakdown.retrieval_signal,
                item[1].paper.influential_citation_count or 0,
                item[1].paper.citation_count or 0,
                item[1].paper.year or 0,
            ),
            reverse=True,
        )
        selected = [
            paper.model_copy(update={"rank": index})
            for index, (_, paper) in enumerate(ranked[: rules.selected_papers_limit], start=1)
        ]
        note = rules.claim_notes.get(claim_id)
        shortlist.append(
            SelectedCitationRecord(
                claim=claim,
                status=claim_status_for_selected(claim_reviews, len(selected), note),
                note=note,
                candidate_count=len(ranked),
                selected_papers=selected,
                excluded_queries={query_id: reason for query_id, reason in rules.excluded_queries.items() if queries.get(query_id, None) and queries[query_id].claim_id == claim_id},
                query_reviews=claim_reviews,
            )
        )

    write_jsonl(workspace.require_path("artifacts", "selected_citations"), shortlist)
    return shortlist
