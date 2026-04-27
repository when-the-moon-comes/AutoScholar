from __future__ import annotations

from collections import defaultdict

from autoscholar.citation.common import load_rules, paper_key, paper_reference_aliases, paper_strength, rules_stopwords, tokenize, utc_now
from autoscholar.citation.config import CitationRulesConfig, RecommendationConfig
from autoscholar.integrations import SemanticScholarClient
from autoscholar.io import read_json_list, read_jsonl, write_jsonl
from autoscholar.models import (
    ClaimRecord,
    CorrectionCandidateRecord,
    PaperRecord,
    QueryRecord,
    QueryReviewRecord,
    RecommendationCorrectionRecord,
    SearchResultRecord,
    SeedPaperRecord,
)
from autoscholar.workspace import Workspace


def _query_candidate_groups(
    claim: ClaimRecord,
    claim_records: list[SearchResultRecord],
    claim_reviews: list[QueryReviewRecord],
    rules: CitationRulesConfig,
) -> dict[str, dict]:
    review_by_id = {item.query_id: item for item in claim_reviews}
    stopwords = rules_stopwords(rules)
    claim_tokens = tokenize(claim.claim_text, stopwords)
    groups: dict[str, dict] = {}
    for record in claim_records:
        review = review_by_id.get(record.query_id)
        if review is None or review.status == "exclude":
            continue
        query_tokens = tokenize(record.query_text, stopwords) | tokenize(record.short_label, stopwords)
        for paper in record.papers:
            aliases = paper_reference_aliases(paper)
            if any(alias in rules.excluded_papers for alias in aliases):
                continue
            paper_tokens = tokenize(paper.title, stopwords) | tokenize(paper.abstract or "", stopwords)
            key = paper_key(paper)
            entry = groups.setdefault(
                key,
                {
                    "paper": paper,
                    "supporting_query_ids": set(),
                    "claim_overlap": 0,
                    "query_overlap": 0,
                },
            )
            if paper_strength(paper) > paper_strength(entry["paper"]):
                entry["paper"] = paper
            entry["supporting_query_ids"].add(record.query_id)
            entry["claim_overlap"] = max(entry["claim_overlap"], len(claim_tokens & paper_tokens))
            entry["query_overlap"] = max(entry["query_overlap"], len(query_tokens & paper_tokens))
    return groups


def _rank_seed_candidates(groups: dict[str, dict]) -> list[tuple[str, dict]]:
    ranked = list(groups.items())
    ranked.sort(
        key=lambda item: (
            len(item[1]["supporting_query_ids"]),
            item[1]["claim_overlap"] + item[1]["query_overlap"],
            item[1]["paper"].influential_citation_count or 0,
            item[1]["paper"].citation_count or 0,
            item[1]["paper"].year or 0,
        ),
        reverse=True,
    )
    return ranked


def _candidate_lookup(ranked: list[tuple[str, dict]]) -> dict[str, tuple[str, dict]]:
    lookup: dict[str, tuple[str, dict]] = {}
    for paper_key_value, entry in ranked:
        for alias in paper_reference_aliases(entry["paper"]):
            lookup.setdefault(alias, (paper_key_value, entry))
    return lookup


def _select_seeds(
    claim_id: str,
    ranked_candidates: list[tuple[str, dict]],
    config: RecommendationConfig,
) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]], dict[str, list[str] | str]]:
    control = config.seed.claim_overrides.get(claim_id)
    lookup = _candidate_lookup(ranked_candidates)
    selected: list[tuple[str, dict]] = []
    negatives: list[tuple[str, dict]] = []
    blocked_keys: set[str] = set()
    warnings: list[str] = []

    if control:
        for blocked_ref in control.blocked:
            match = lookup.get(blocked_ref)
            if match:
                blocked_keys.add(match[0])

        for positive_ref in control.positive:
            match = lookup.get(positive_ref)
            if match and match[0] not in blocked_keys:
                selected.append(match)

        for negative_ref in control.negative:
            match = lookup.get(negative_ref)
            if match and match[0] not in blocked_keys:
                negatives.append(match)

    if config.seed.selection_mode != "manual":
        for paper_key_value, entry in ranked_candidates:
            if paper_key_value in blocked_keys:
                continue
            if any(paper_key_value == existing_key for existing_key, _ in selected):
                continue
            if entry["claim_overlap"] + entry["query_overlap"] < config.seed.min_total_overlap:
                continue
            selected.append((paper_key_value, entry))
            if len(selected) >= config.seed.max_seeds_per_claim:
                break

    if control and config.seed.selection_mode == "manual" and not selected:
        warnings.append("manual seed mode produced no usable positive seeds")

    return selected[: config.seed.max_seeds_per_claim], negatives, {
        "selection_mode": config.seed.selection_mode,
        "warnings": warnings,
    }


def _compute_trigger_reasons(
    candidate_groups: dict[str, dict],
    claim_reviews: list[QueryReviewRecord],
    claim_note: str | None,
    config: RecommendationConfig,
) -> list[str]:
    reasons: list[str] = []
    ranked = _rank_seed_candidates(candidate_groups)
    if len(ranked) < config.trigger.min_selected_papers:
        reasons.append("insufficient_candidates")
    if not any(len(entry["supporting_query_ids"]) >= config.trigger.min_cross_query_support for _, entry in ranked):
        reasons.append("weak_cross_query_support")
    if ranked and len(ranked) <= config.trigger.max_low_signal_candidates:
        if all((entry["paper"].citation_count or 0) <= config.trigger.low_citation_threshold for _, entry in ranked):
            reasons.append("low_signal_candidates")
    if config.trigger.include_review_status and any(review.status == "review" for review in claim_reviews):
        reasons.append("review_queries_present")
    if config.trigger.include_claim_notes and claim_note:
        reasons.append("claim_note_present")
    return reasons


def _normalize_recommended_paper(raw_paper: dict) -> PaperRecord:
    authors = [author.get("name") for author in raw_paper.get("authors", []) if author.get("name")]
    external_ids = raw_paper.get("externalIds") or {}
    open_access_pdf = raw_paper.get("openAccessPdf") or {}
    return PaperRecord(
        paper_id=raw_paper.get("paperId"),
        title=raw_paper.get("title") or "Untitled",
        year=raw_paper.get("year"),
        authors=authors,
        venue=raw_paper.get("venue"),
        url=raw_paper.get("url"),
        abstract=raw_paper.get("abstract"),
        citation_count=raw_paper.get("citationCount"),
        influential_citation_count=raw_paper.get("influentialCitationCount"),
        doi=external_ids.get("DOI"),
        external_ids={str(key): str(value) for key, value in external_ids.items()},
        is_open_access=raw_paper.get("isOpenAccess"),
        open_access_pdf_url=open_access_pdf.get("url"),
    )


def _serialize_seed(rank: int, paper_key_value: str, entry: dict) -> SeedPaperRecord:
    return SeedPaperRecord(
        rank=rank,
        paper_key=paper_key_value,
        paper=entry["paper"],
        query_support_count=len(entry["supporting_query_ids"]),
        supporting_query_ids=sorted(entry["supporting_query_ids"]),
        claim_overlap=entry["claim_overlap"],
        query_overlap=entry["query_overlap"],
    )


def run_correction(
    workspace: Workspace,
    rules: CitationRulesConfig,
    config: RecommendationConfig,
) -> list[RecommendationCorrectionRecord]:
    claims = {item.claim_id: item for item in read_jsonl(workspace.require_path("artifacts", "claims"), ClaimRecord)}
    records = read_jsonl(workspace.require_path("artifacts", "search_results_deduped"), SearchResultRecord)
    query_reviews = read_json_list(workspace.require_path("artifacts", "query_reviews"), "query_reviews", QueryReviewRecord)

    by_claim_records: dict[str, list[SearchResultRecord]] = defaultdict(list)
    by_claim_reviews: dict[str, list[QueryReviewRecord]] = defaultdict(list)
    for record in records:
        by_claim_records[record.claim_id].append(record)
    for review in query_reviews:
        by_claim_reviews[review.claim_id].append(review)

    correction_records: list[RecommendationCorrectionRecord] = []
    with SemanticScholarClient() as client:
        for claim_id in sorted(claims):
            claim = claims[claim_id]
            claim_records = by_claim_records.get(claim_id, [])
            claim_reviews_local = sorted(by_claim_reviews.get(claim_id, []), key=lambda item: item.query_id)
            claim_note = rules.claim_notes.get(claim_id)
            query_groups = _query_candidate_groups(claim, claim_records, claim_reviews_local, rules)
            trigger_reasons = _compute_trigger_reasons(query_groups, claim_reviews_local, claim_note, config)
            if not trigger_reasons:
                continue

            ranked_candidates = _rank_seed_candidates(query_groups)
            seeds, negatives, seed_control = _select_seeds(claim_id, ranked_candidates, config)
            recommendation_candidates: dict[str, dict] = {}
            recommendation_failures: list[dict] = []

            positive_ids = [entry["paper"].paper_id for _, entry in seeds if entry["paper"].paper_id]
            negative_ids = [entry["paper"].paper_id for _, entry in negatives if entry["paper"].paper_id]
            if positive_ids:
                try:
                    if config.recommendations.method == "positive_seed_list":
                        raw_recommendations = client.get_recommendations_from_lists(
                            positive_paper_ids=positive_ids,
                            negative_paper_ids=negative_ids or None,
                            limit=config.recommendations.per_seed_limit * max(1, len(positive_ids)),
                            fields=config.recommendations.fields,
                        )
                    else:
                        raw_recommendations = []
                        for seed_paper_id in positive_ids:
                            raw_recommendations.extend(
                                client.get_recommendations(
                                    paper_id=seed_paper_id,
                                    limit=config.recommendations.per_seed_limit,
                                    fields=config.recommendations.fields,
                                )
                            )
                    for raw_paper in raw_recommendations:
                        paper = _normalize_recommended_paper(raw_paper)
                        aliases = paper_reference_aliases(paper)
                        if any(alias in rules.excluded_papers for alias in aliases):
                            continue
                        key = paper_key(paper)
                        if any(key == seed_key for seed_key, _ in seeds):
                            continue
                        entry = recommendation_candidates.setdefault(
                            key,
                            {
                                "paper": paper,
                                "recommended_by_seed_ids": set(positive_ids),
                                "supporting_query_ids": set(),
                                "claim_overlap": 0,
                                "query_overlap": 0,
                            },
                        )
                        if paper_strength(paper) > paper_strength(entry["paper"]):
                            entry["paper"] = paper
                except Exception as exc:
                    recommendation_failures.append(
                        {
                            "error_type": exc.__class__.__name__,
                            "error": str(exc),
                        }
                    )

            candidates: list[CorrectionCandidateRecord] = []
            merged: dict[str, dict] = {}
            for key, entry in query_groups.items():
                merged[key] = {
                    "paper": entry["paper"],
                    "supporting_query_ids": set(entry["supporting_query_ids"]),
                    "recommended_by_seed_ids": set(),
                    "claim_overlap": entry["claim_overlap"],
                    "query_overlap": entry["query_overlap"],
                }
            for key, entry in recommendation_candidates.items():
                existing = merged.setdefault(
                    key,
                    {
                        "paper": entry["paper"],
                        "supporting_query_ids": set(),
                        "recommended_by_seed_ids": set(),
                        "claim_overlap": entry["claim_overlap"],
                        "query_overlap": entry["query_overlap"],
                    },
                )
                if paper_strength(entry["paper"]) > paper_strength(existing["paper"]):
                    existing["paper"] = entry["paper"]
                existing["recommended_by_seed_ids"].update(entry["recommended_by_seed_ids"])

            ranked_merged = list(merged.items())
            ranked_merged.sort(
                key=lambda item: (
                    len(item[1]["supporting_query_ids"]) > 0 and len(item[1]["recommended_by_seed_ids"]) > 0,
                    len(item[1]["supporting_query_ids"]),
                    len(item[1]["recommended_by_seed_ids"]),
                    item[1]["claim_overlap"] + item[1]["query_overlap"],
                    item[1]["paper"].influential_citation_count or 0,
                    item[1]["paper"].citation_count or 0,
                    item[1]["paper"].year or 0,
                ),
                reverse=True,
            )

            for rank, (paper_key_value, entry) in enumerate(
                ranked_merged[: config.recommendations.top_candidates_per_claim],
                start=1,
            ):
                origin = "query+recommendation"
                if entry["supporting_query_ids"] and not entry["recommended_by_seed_ids"]:
                    origin = "query"
                if entry["recommended_by_seed_ids"] and not entry["supporting_query_ids"]:
                    origin = "recommendation"
                candidates.append(
                    CorrectionCandidateRecord(
                        rank=rank,
                        paper_key=paper_key_value,
                        paper=entry["paper"],
                        origin=origin,
                        query_support_count=len(entry["supporting_query_ids"]),
                        supporting_query_ids=sorted(entry["supporting_query_ids"]),
                        recommendation_support_count=len(entry["recommended_by_seed_ids"]),
                        recommended_by_seed_ids=sorted(entry["recommended_by_seed_ids"]),
                        claim_overlap=entry["claim_overlap"],
                        query_overlap=entry["query_overlap"],
                    )
                )

            if not seeds:
                status = "rewrite_needed"
            elif recommendation_failures and not recommendation_candidates:
                status = "blocked"
            else:
                high_fit = [
                    item for item in candidates
                    if item.claim_overlap + item.query_overlap >= config.recommendations.ready_min_total_overlap
                ]
                status = (
                    "corrected_ready"
                    if len(high_fit) >= config.recommendations.ready_candidate_count
                    else "corrected_review"
                )

            correction_records.append(
                RecommendationCorrectionRecord(
                    claim=claim,
                    current_status="review" if any(item.status == "review" for item in claim_reviews_local) else "ready",
                    status=status,
                    trigger_reasons=trigger_reasons,
                    recommendation_method=config.recommendations.method,
                    seed_selection_mode=seed_control["selection_mode"],
                    claim_note=claim_note,
                    query_reviews=claim_reviews_local,
                    seeds=[_serialize_seed(rank, paper_key_value, entry) for rank, (paper_key_value, entry) in enumerate(seeds, start=1)],
                    negative_seeds=[_serialize_seed(rank, paper_key_value, entry) for rank, (paper_key_value, entry) in enumerate(negatives, start=1)],
                    recommendation_failures=recommendation_failures,
                    candidates=candidates,
                    generated_at=utc_now(),
                )
            )

    write_jsonl(workspace.require_path("artifacts", "recommendation_corrections"), correction_records)
    return correction_records
