from __future__ import annotations

from autoscholar.citation.common import build_query_reviews, dedupe_search_results
from autoscholar.citation.config import CitationRulesConfig
from autoscholar.io import read_jsonl, write_json, write_jsonl
from autoscholar.models import ClaimRecord, QueryRecord, QueryReviewRecord, SearchResultRecord
from autoscholar.workspace import Workspace


def run_prescreen(workspace: Workspace, rules: CitationRulesConfig) -> list[QueryReviewRecord]:
    claims = {item.claim_id: item for item in read_jsonl(workspace.require_path("artifacts", "claims"), ClaimRecord)}
    queries = {item.query_id: item for item in read_jsonl(workspace.require_path("artifacts", "queries"), QueryRecord)}
    raw_results = read_jsonl(workspace.require_path("artifacts", "search_results_raw"), SearchResultRecord)
    deduped = dedupe_search_results(raw_results)
    reviews = build_query_reviews(claims=claims, queries=queries, records=deduped, rules=rules)
    write_jsonl(workspace.require_path("artifacts", "search_results_deduped"), deduped)
    write_json(
        workspace.require_path("artifacts", "query_reviews"),
        {"query_reviews": [item.model_dump(mode="json") for item in reviews]},
    )
    return reviews
