import argparse
import importlib.util
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = REPO_ROOT / "paper"
CLAIM_UNITS = PAPER_DIR / "citation_claim_units.md"
DEDUPED_RESULTS = PAPER_DIR / "semantic_scholar_raw_results_deduped.jsonl"
OUTPUT_PATH = PAPER_DIR / "claim_recommended_citations.md"
RULES_CONFIG = REPO_ROOT / "config" / "claim_recommendation_rules.yaml"
PRESCREEN_SCRIPT = REPO_ROOT / "scripts" / "dedupe_and_prescreen_semantic_scholar.py"


DEFAULT_STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "into", "this", "these", "those",
    "their", "there", "where", "which", "while", "within", "across", "between",
    "rather", "than", "such", "through", "using", "based", "study", "research",
    "urban", "regional", "region", "regions", "spatial", "planning", "analysis",
    "approach", "case", "system", "systems", "city", "cities", "area", "areas",
    "greater", "bay", "mega", "cross", "boundary", "governance", "functional",
    "integration", "space", "spaces", "scale", "scales",
}
DEFAULT_SELECTED_PAPERS_LIMIT = 3
DEFAULT_QUERY_STATUS_WEIGHTS = {
    "keep": 1.0,
    "review": 0.6,
    "rewrite": 0.25,
    "exclude": 0.0,
}
DEFAULT_SCORE_WEIGHTS = {
    "title_claim_overlap": 4.0,
    "abstract_claim_overlap": 1.75,
    "title_query_overlap": 2.5,
    "abstract_query_overlap": 1.0,
    "support_count": 0.75,
    "weighted_support": 2.5,
    "best_rank_reciprocal": 3.0,
    "mean_rank_reciprocal": 1.5,
    "influential_citations": 0.8,
    "citations": 0.3,
}

_PRESCREEN_MODULE: Any | None = None


@dataclass(frozen=True)
class ClaimInfo:
    claim_id: str
    section: str
    source_lines: str
    claim_text: str
    claim_type: str
    priority: str


@dataclass(frozen=True)
class QueryStatusWeights:
    keep: float
    review: float
    rewrite: float
    exclude: float

    def weight_for(self, status: str) -> float:
        return {
            "keep": self.keep,
            "review": self.review,
            "rewrite": self.rewrite,
            "exclude": self.exclude,
        }.get(status, 0.0)


@dataclass(frozen=True)
class ScoreWeights:
    title_claim_overlap: float
    abstract_claim_overlap: float
    title_query_overlap: float
    abstract_query_overlap: float
    support_count: float
    weighted_support: float
    best_rank_reciprocal: float
    mean_rank_reciprocal: float
    influential_citations: float
    citations: float


@dataclass(frozen=True)
class RecommendationRules:
    stopwords: Set[str]
    excluded_queries: Dict[str, str]
    excluded_papers: Dict[str, str]
    claim_notes: Dict[str, str]
    selected_papers_limit: int
    query_status_weights: QueryStatusWeights
    score_weights: ScoreWeights


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate claim-level citation recommendations from deduplicated search results."
    )
    parser.add_argument(
        "rules_config",
        nargs="?",
        default=str(RULES_CONFIG),
        help="Optional YAML rules config path. Defaults to config/claim_recommendation_rules.yaml.",
    )
    return parser.parse_args()


def merge_weight_overrides(
    raw: object,
    defaults: Dict[str, float],
    field_name: str,
) -> Dict[str, float]:
    merged = dict(defaults)
    if raw is None:
        return merged
    if not isinstance(raw, dict):
        raise ValueError(f"Rules config field '{field_name}' must be a mapping.")

    for key, value in raw.items():
        if key not in merged:
            continue
        merged[key] = float(value)
    return merged


def load_rules(path: Path) -> RecommendationRules:
    config_path = path if path.is_absolute() else (REPO_ROOT / path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Rules config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Rules config root must be a YAML mapping.")

    stopwords = set(DEFAULT_STOPWORDS)
    extra_stopwords = raw.get("stopwords", [])
    if extra_stopwords:
        if not isinstance(extra_stopwords, list):
            raise ValueError("Rules config field 'stopwords' must be a list.")
        stopwords |= {str(item).strip().lower() for item in extra_stopwords if str(item).strip()}

    excluded_queries = raw.get("excluded_queries", {})
    excluded_papers = raw.get("excluded_papers", {})
    claim_notes = raw.get("claim_notes", {})

    for field_name, value in (
        ("excluded_queries", excluded_queries),
        ("excluded_papers", excluded_papers),
        ("claim_notes", claim_notes),
    ):
        if not isinstance(value, dict):
            raise ValueError(f"Rules config field '{field_name}' must be a mapping.")

    selected_papers_limit = int(raw.get("selected_papers_limit", DEFAULT_SELECTED_PAPERS_LIMIT))
    if selected_papers_limit < 1:
        raise ValueError("Rules config field 'selected_papers_limit' must be >= 1.")

    query_status_weights = merge_weight_overrides(
        raw.get("query_status_weights"),
        DEFAULT_QUERY_STATUS_WEIGHTS,
        "query_status_weights",
    )
    score_weights = merge_weight_overrides(
        raw.get("score_weights"),
        DEFAULT_SCORE_WEIGHTS,
        "score_weights",
    )

    return RecommendationRules(
        stopwords=stopwords,
        excluded_queries={str(key): str(val) for key, val in excluded_queries.items()},
        excluded_papers={str(key): str(val) for key, val in excluded_papers.items()},
        claim_notes={str(key): str(val) for key, val in claim_notes.items()},
        selected_papers_limit=selected_papers_limit,
        query_status_weights=QueryStatusWeights(**query_status_weights),
        score_weights=ScoreWeights(**score_weights),
    )


def load_prescreen_module() -> Any:
    global _PRESCREEN_MODULE
    if _PRESCREEN_MODULE is not None:
        return _PRESCREEN_MODULE

    spec = importlib.util.spec_from_file_location(
        "claim_recommendation_prescreen",
        PRESCREEN_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load prescreen module: {PRESCREEN_SCRIPT}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _PRESCREEN_MODULE = module
    return module


def tokenize(text: str, stopwords: Set[str]) -> Set[str]:
    tokens = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", (text or "").lower()):
        normalized = token.strip("-")
        if len(normalized) < 4:
            continue
        if normalized in stopwords:
            continue
        tokens.add(normalized)
    return tokens


def load_claim_units(path: Path) -> Dict[str, ClaimInfo]:
    claims: Dict[str, ClaimInfo] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("| C"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) != 6:
            continue
        claims[parts[0]] = ClaimInfo(
            claim_id=parts[0],
            section=parts[1],
            source_lines=parts[2],
            claim_text=parts[3],
            claim_type=parts[4],
            priority=parts[5],
        )
    return claims


def load_records(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def paper_key(paper: dict) -> str:
    if paper.get("paperId"):
        return f"paperId:{paper['paperId']}"
    if paper.get("doi"):
        return f"doi:{paper['doi'].lower()}"
    title = (paper.get("title") or "").strip().lower()
    year = paper.get("year") or ""
    return f"title:{title}|year:{year}"


def paper_strength(paper: dict) -> tuple[int, int, int]:
    return (
        paper.get("influentialCitationCount") or 0,
        paper.get("citationCount") or 0,
        paper.get("year") or 0,
    )


def paper_exclusion_reason(paper: dict, rules: RecommendationRules) -> str | None:
    candidates = []
    if paper.get("paperId"):
        candidates.append(f"paperid:{str(paper['paperId']).lower()}")
    if paper.get("doi"):
        candidates.append(f"doi:{str(paper['doi']).lower()}")

    title = (paper.get("title") or "").strip().lower()
    year = paper.get("year") or ""
    if title:
        candidates.append(f"title:{title}|year:{year}")

    for candidate in candidates:
        reason = rules.excluded_papers.get(candidate)
        if reason:
            return reason
    return None


def evaluate_query_record(record: dict, rules: RecommendationRules, prescreen_module: Any) -> dict:
    if record["query_key"] in rules.excluded_queries:
        return {
            "query_key": record["query_key"],
            "status": "exclude",
            "reason": rules.excluded_queries[record["query_key"]],
            "paper_count": int(record.get("paper_count", 0)),
            "total_hits": record.get("total_hits"),
        }

    status, reason = prescreen_module.evaluate_query(record)
    return {
        "query_key": record["query_key"],
        "status": status,
        "reason": reason,
        "paper_count": int(record.get("paper_count", 0)),
        "total_hits": record.get("total_hits"),
    }


def build_query_context_tokens(records: List[dict], stopwords: Set[str]) -> Set[str]:
    query_tokens = set()
    for record in records:
        query_tokens |= tokenize(record.get("query_text", ""), stopwords)
        query_tokens |= tokenize(record.get("short_label", ""), stopwords)
        query_tokens |= tokenize(record.get("core_keywords", ""), stopwords)
    return query_tokens


def paper_rank_for_record(paper: dict) -> int:
    rank = paper.get("rank")
    if rank is None:
        return 999
    try:
        return max(1, int(rank))
    except (TypeError, ValueError):
        return 999


def score_paper(
    claim: ClaimInfo,
    claim_tokens: Set[str],
    claim_query_tokens: Set[str],
    group: dict,
    rules: RecommendationRules,
) -> dict:
    paper = group["paper"]
    title_tokens = tokenize(paper.get("title", ""), rules.stopwords)
    abstract_tokens = tokenize(paper.get("abstract", ""), rules.stopwords)
    query_hits = list(group["query_hits"].values())

    title_claim_overlap = len(claim_tokens & title_tokens)
    abstract_claim_overlap = len(claim_tokens & abstract_tokens)
    title_query_overlap = len(claim_query_tokens & title_tokens)
    abstract_query_overlap = len(claim_query_tokens & abstract_tokens)
    support_count = len(query_hits)
    weighted_support = sum(hit["status_weight"] for hit in query_hits)
    reciprocal_ranks = [
        hit["status_weight"] / max(hit["paper_rank"], 1)
        for hit in query_hits
    ]
    best_rank_reciprocal = max(reciprocal_ranks, default=0.0)
    mean_rank_reciprocal = (
        sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0
    )
    influential_log = math.log1p(paper.get("influentialCitationCount") or 0)
    citations_log = math.log1p(paper.get("citationCount") or 0)

    weights = rules.score_weights
    topical_fit = (
        weights.title_claim_overlap * title_claim_overlap
        + weights.abstract_claim_overlap * abstract_claim_overlap
        + weights.title_query_overlap * title_query_overlap
        + weights.abstract_query_overlap * abstract_query_overlap
    )
    support_signal = (
        weights.support_count * support_count
        + weights.weighted_support * weighted_support
    )
    retrieval_signal = (
        weights.best_rank_reciprocal * best_rank_reciprocal
        + weights.mean_rank_reciprocal * mean_rank_reciprocal
    )
    authority_signal = (
        weights.influential_citations * influential_log
        + weights.citations * citations_log
    )
    final_score = topical_fit + support_signal + retrieval_signal + authority_signal

    return {
        "title_claim_overlap": title_claim_overlap,
        "abstract_claim_overlap": abstract_claim_overlap,
        "title_query_overlap": title_query_overlap,
        "abstract_query_overlap": abstract_query_overlap,
        "support_count": support_count,
        "weighted_support": weighted_support,
        "best_rank_reciprocal": best_rank_reciprocal,
        "mean_rank_reciprocal": mean_rank_reciprocal,
        "topical_fit": topical_fit,
        "support_signal": support_signal,
        "retrieval_signal": retrieval_signal,
        "authority_signal": authority_signal,
        "final_score": final_score,
    }


def candidate_sort_key(group: dict) -> tuple:
    score = group["score_breakdown"]
    paper = group["paper"]
    return (
        score["final_score"],
        score["topical_fit"],
        score["support_signal"],
        score["retrieval_signal"],
        score["authority_signal"],
        score["weighted_support"],
        score["support_count"],
        paper.get("influentialCitationCount") or 0,
        paper.get("citationCount") or 0,
        paper.get("year") or 0,
    )


def claim_status(
    claim_id: str,
    query_reviews: List[dict],
    selected_papers: List[dict],
    rules: RecommendationRules,
) -> str:
    if not selected_papers:
        return "weak"
    if claim_id in rules.claim_notes:
        return "review"
    if not any(item["status"] == "keep" for item in query_reviews):
        return "review"

    top_candidate = selected_papers[0]["score_breakdown"]
    if top_candidate["support_count"] < 2:
        return "review"
    return "ready"


def build_recommendations(
    claims: Dict[str, ClaimInfo],
    records: List[dict],
    rules: RecommendationRules,
) -> Dict[str, dict]:
    prescreen_module = load_prescreen_module()

    by_claim: Dict[str, List[dict]] = {}
    for record in records:
        by_claim.setdefault(record["claim_id"], []).append(record)

    recommendations: Dict[str, dict] = {}
    for claim_id, claim in claims.items():
        claim_records = sorted(by_claim.get(claim_id, []), key=lambda item: item["query_key"])
        query_reviews = [
            evaluate_query_record(record, rules, prescreen_module)
            for record in claim_records
        ]
        query_review_by_key = {
            item["query_key"]: item
            for item in query_reviews
        }
        usable_records = [
            record
            for record in claim_records
            if query_review_by_key[record["query_key"]]["status"] != "exclude"
            and int(record.get("paper_count", 0)) > 0
        ]

        claim_tokens = tokenize(claim.claim_text, rules.stopwords)
        claim_query_tokens = build_query_context_tokens(usable_records, rules.stopwords)

        paper_groups: Dict[str, dict] = {}
        for record in usable_records:
            query_review = query_review_by_key[record["query_key"]]
            status_weight = rules.query_status_weights.weight_for(query_review["status"])

            for paper in record.get("papers", []):
                exclusion_reason = paper_exclusion_reason(paper, rules)
                if exclusion_reason:
                    continue

                key = paper_key(paper)
                group = paper_groups.setdefault(
                    key,
                    {
                        "paper": paper,
                        "records": [],
                        "query_hits": {},
                    },
                )
                group["records"].append(record)
                if paper_strength(paper) > paper_strength(group["paper"]):
                    group["paper"] = paper

                query_hit = {
                    "query_key": record["query_key"],
                    "status": query_review["status"],
                    "reason": query_review["reason"],
                    "status_weight": status_weight,
                    "paper_rank": paper_rank_for_record(paper),
                }
                existing_hit = group["query_hits"].get(record["query_key"])
                if existing_hit is None or query_hit["paper_rank"] < existing_hit["paper_rank"]:
                    group["query_hits"][record["query_key"]] = query_hit

        ranked = []
        for key, group in paper_groups.items():
            group["query_hits"] = {
                hit["query_key"]: hit
                for hit in sorted(
                    group["query_hits"].values(),
                    key=lambda item: (-item["status_weight"], item["paper_rank"], item["query_key"]),
                )
            }
            group["score_breakdown"] = score_paper(
                claim=claim,
                claim_tokens=claim_tokens,
                claim_query_tokens=claim_query_tokens,
                group=group,
                rules=rules,
            )
            group["paper_key"] = key
            ranked.append((candidate_sort_key(group), group))

        ranked.sort(reverse=True, key=lambda item: item[0])
        selected = [group for _, group in ranked[:rules.selected_papers_limit]]

        recommendations[claim_id] = {
            "claim": claim,
            "usable_records": usable_records,
            "query_reviews": query_reviews,
            "excluded_queries": [
                (item["query_key"], item["reason"])
                for item in query_reviews
                if item["status"] == "exclude"
            ],
            "selected_papers": selected,
            "candidate_count": len(ranked),
            "status": claim_status(claim_id, query_reviews, selected, rules),
            "note": rules.claim_notes.get(claim_id),
        }

    return recommendations


def format_score_line(score: dict) -> str:
    return (
        f"score={score['final_score']:.2f}; "
        f"topical={score['topical_fit']:.2f}; "
        f"support={score['support_signal']:.2f}; "
        f"retrieval={score['retrieval_signal']:.2f}; "
        f"authority={score['authority_signal']:.2f}"
    )


def format_overlap_line(score: dict) -> str:
    return (
        "overlap: "
        f"title_claim={score['title_claim_overlap']}, "
        f"abstract_claim={score['abstract_claim_overlap']}, "
        f"title_query={score['title_query_overlap']}, "
        f"abstract_query={score['abstract_query_overlap']}"
    )


def format_query_hit_line(query_hits: Dict[str, dict]) -> str:
    if not query_hits:
        return "query_hits: none"
    summary = ", ".join(
        f"{item['query_key']}[{item['status']}; rank={item['paper_rank']}]"
        for item in query_hits.values()
    )
    return f"query_hits: {summary}"


def write_report(path: Path, recommendations: Dict[str, dict]) -> None:
    ready_count = sum(1 for item in recommendations.values() if item["status"] == "ready")
    review_count = sum(1 for item in recommendations.values() if item["status"] == "review")
    weak_count = sum(1 for item in recommendations.values() if item["status"] == "weak")

    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Claim Recommended Citations\n\n")
        handle.write("## Summary\n\n")
        handle.write(f"- Claims with recommendation lists: {len(recommendations)}\n")
        handle.write(f"- `ready` claims: {ready_count}\n")
        handle.write(f"- `review` claims: {review_count}\n")
        handle.write(f"- `weak` claims: {weak_count}\n")
        handle.write(
            "- Recommendation rule: rank by claim/query topical fit first, then weighted multi-query support, retrieval rank, and citation signal.\n\n"
        )

        for claim_id in sorted(recommendations.keys()):
            item = recommendations[claim_id]
            claim = item["claim"]
            handle.write(f"## {claim_id}\n")
            handle.write(f"- Section: {claim.section}\n")
            handle.write(f"- Source lines: {claim.source_lines}\n")
            handle.write(f"- Claim type: {claim.claim_type}\n")
            handle.write(f"- Priority: {claim.priority}\n")
            handle.write(f"- Status: {item['status']}\n")
            handle.write(f"- Candidate pool: {item['candidate_count']}\n")
            handle.write(f"- Claim: {claim.claim_text}\n")

            if item["query_reviews"]:
                review_summary = ", ".join(
                    f"{entry['query_key']}[{entry['status']}; papers={entry['paper_count']}]"
                    for entry in item["query_reviews"]
                )
                handle.write(f"- Query review: {review_summary}\n")

            if item["excluded_queries"]:
                excluded = ", ".join(
                    f"{query_key} ({reason})" for query_key, reason in item["excluded_queries"]
                )
                handle.write(f"- Excluded queries: {excluded}\n")

            if item["note"]:
                handle.write(f"- Note: {item['note']}\n")

            if not item["selected_papers"]:
                handle.write("- Recommended citations: none yet\n\n")
                continue

            handle.write("- Recommended citations:\n")
            for index, group in enumerate(item["selected_papers"], start=1):
                paper = group["paper"]
                score = group["score_breakdown"]
                title = paper.get("title") or "Untitled"
                year = paper.get("year") or "n/a"
                cites = paper.get("citationCount") or 0
                doi = paper.get("doi") or "n/a"
                venue = paper.get("venue") or "n/a"

                handle.write(
                    f"  {index}. {title} ({year}; cites={cites}; doi={doi}; venue={venue})\n"
                )
                handle.write(f"     {format_score_line(score)}\n")
                handle.write(f"     {format_overlap_line(score)}\n")
                handle.write(f"     {format_query_hit_line(group['query_hits'])}\n")
            handle.write("\n")


def main() -> int:
    args = parse_args()
    rules = load_rules(Path(args.rules_config))
    claims = load_claim_units(CLAIM_UNITS)
    records = load_records(DEDUPED_RESULTS)
    recommendations = build_recommendations(claims, records, rules)
    write_report(OUTPUT_PATH, recommendations)
    print(f"Wrote: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
