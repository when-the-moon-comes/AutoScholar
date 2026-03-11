import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = REPO_ROOT / "paper"
CLAIM_UNITS = PAPER_DIR / "citation_claim_units.md"
DEDUPED_RESULTS = PAPER_DIR / "semantic_scholar_raw_results_deduped.jsonl"
OUTPUT_PATH = PAPER_DIR / "claim_recommended_citations.md"
RULES_CONFIG = REPO_ROOT / "config" / "claim_recommendation_rules.yaml"


DEFAULT_STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "into", "this", "these", "those",
    "their", "there", "where", "which", "while", "within", "across", "between",
    "rather", "than", "such", "through", "using", "based", "study", "research",
    "urban", "regional", "region", "regions", "spatial", "planning", "analysis",
    "approach", "case", "system", "systems", "city", "cities", "area", "areas",
    "greater", "bay", "mega", "cross", "boundary", "governance", "functional",
    "integration", "governance", "space", "spaces", "scale", "scales",
}


@dataclass(frozen=True)
class ClaimInfo:
    claim_id: str
    section: str
    source_lines: str
    claim_text: str
    claim_type: str
    priority: str


@dataclass(frozen=True)
class RecommendationRules:
    stopwords: Set[str]
    excluded_queries: Dict[str, str]
    excluded_papers: Dict[str, str]
    claim_notes: Dict[str, str]


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

    return RecommendationRules(
        stopwords=stopwords,
        excluded_queries={str(key): str(val) for key, val in excluded_queries.items()},
        excluded_papers={str(key): str(val) for key, val in excluded_papers.items()},
        claim_notes={str(key): str(val) for key, val in claim_notes.items()},
    )


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


def score_paper(
    claim: ClaimInfo,
    supporting_queries: List[dict],
    paper: dict,
    rules: RecommendationRules,
) -> tuple:
    claim_tokens = tokenize(claim.claim_text, rules.stopwords)
    query_tokens = set()
    for record in supporting_queries:
        query_tokens |= tokenize(record.get("query_text", ""), rules.stopwords)
        query_tokens |= tokenize(record.get("short_label", ""), rules.stopwords)
        query_tokens |= tokenize(record.get("core_keywords", ""), rules.stopwords)

    paper_text = " ".join(
        part for part in [paper.get("title", ""), paper.get("abstract", ""), paper.get("venue", "")]
        if part
    )
    paper_tokens = tokenize(paper_text, rules.stopwords)

    claim_overlap = len(claim_tokens & paper_tokens)
    query_overlap = len(query_tokens & paper_tokens)
    support_count = len({record["query_key"] for record in supporting_queries})
    influential = paper.get("influentialCitationCount") or 0
    citations = paper.get("citationCount") or 0
    year = paper.get("year") or 0

    return (
        support_count,
        influential,
        citations,
        claim_overlap,
        query_overlap,
        year,
    )


def claim_status(
    claim_id: str,
    selected_queries: List[dict],
    selected_papers: List[dict],
    rules: RecommendationRules,
) -> str:
    if not selected_papers:
        return "weak"
    if claim_id in rules.claim_notes:
        return "review"
    if any(record["paper_count"] < 3 for record in selected_queries):
        return "review"
    return "ready"


def build_recommendations(
    claims: Dict[str, ClaimInfo],
    records: List[dict],
    rules: RecommendationRules,
) -> Dict[str, dict]:
    by_claim: Dict[str, List[dict]] = {}
    for record in records:
        by_claim.setdefault(record["claim_id"], []).append(record)

    recommendations: Dict[str, dict] = {}
    for claim_id, claim in claims.items():
        claim_records = by_claim.get(claim_id, [])
        usable_records = [
            record for record in claim_records
            if record["query_key"] not in rules.excluded_queries and record.get("paper_count", 0) > 0
        ]

        paper_groups: Dict[str, dict] = {}
        for record in usable_records:
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
                    },
                )
                group["records"].append(record)

        ranked = []
        for group in paper_groups.values():
            score = score_paper(claim, group["records"], group["paper"], rules)
            ranked.append((score, group))

        ranked.sort(reverse=True, key=lambda item: item[0])
        selected = [group for _, group in ranked[:3]]

        recommendations[claim_id] = {
            "claim": claim,
            "usable_records": usable_records,
            "excluded_queries": [
                (record["query_key"], rules.excluded_queries[record["query_key"]])
                for record in claim_records
                if record["query_key"] in rules.excluded_queries
            ],
            "selected_papers": selected,
            "status": claim_status(claim_id, usable_records, selected, rules),
            "note": rules.claim_notes.get(claim_id),
        }

    return recommendations


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
        handle.write("- Recommendation rule: prefer non-excluded queries, then rank papers by topical overlap, cross-query support, and citation signal.\n\n")

        for claim_id in sorted(recommendations.keys()):
            item = recommendations[claim_id]
            claim = item["claim"]
            handle.write(f"## {claim_id}\n")
            handle.write(f"- Section: {claim.section}\n")
            handle.write(f"- Source lines: {claim.source_lines}\n")
            handle.write(f"- Claim type: {claim.claim_type}\n")
            handle.write(f"- Priority: {claim.priority}\n")
            handle.write(f"- Status: {item['status']}\n")
            handle.write(f"- Claim: {claim.claim_text}\n")

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
                support = ", ".join(sorted({record["query_key"] for record in group["records"]}))
                title = paper.get("title") or "Untitled"
                year = paper.get("year") or "n/a"
                cites = paper.get("citationCount") or 0
                doi = paper.get("doi") or "n/a"
                venue = paper.get("venue") or "n/a"
                handle.write(
                    f"  {index}. {title} ({year}; cites={cites}; doi={doi}; venue={venue}; support={support})\n"
                )
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
