#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

import requests


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from SemanticScholarApi import SemanticScholarClient


DEFAULT_INPUT = REPO_ROOT / "paper" / "innovation_candidates.json"
DEFAULT_OUTPUT = REPO_ROOT / "paper" / "novelty_verification.json"
DEFAULT_FIELDS = (
    "paperId,title,year,authors,venue,abstract,citationCount,externalIds"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify idea-candidate novelty with Semantic Scholar using the local "
            "AutoScholar API client."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to innovation_candidates.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to novelty_verification.json.",
    )
    parser.add_argument(
        "--candidate-id",
        action="append",
        dest="candidate_ids",
        default=[],
        help="Candidate ID to process. May be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Maximum number of Semantic Scholar results per query.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="How many top existing papers to keep per candidate.",
    )
    parser.add_argument(
        "--recent-year",
        type=int,
        default=2022,
        help="Year threshold used for recent-paper counting.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print what would be searched without calling the API.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def load_candidates(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Candidate file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        candidates = payload.get("candidates")
    else:
        candidates = payload

    if not isinstance(candidates, list):
        raise ValueError("innovation_candidates payload must contain a 'candidates' list.")

    validated: List[dict] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Each candidate must be a JSON object.")
        candidate_id = str(candidate.get("id", "")).strip()
        if not candidate_id:
            raise ValueError("Each candidate requires a non-empty 'id'.")
        queries = candidate.get("novelty_search_queries")
        if not isinstance(queries, list) or not any(str(item).strip() for item in queries):
            raise ValueError(
                f"Candidate '{candidate_id}' requires a non-empty 'novelty_search_queries' list."
            )
        validated.append(candidate)
    return validated


def filter_candidates(candidates: Iterable[dict], candidate_ids: List[str]) -> List[dict]:
    if not candidate_ids:
        return list(candidates)
    selected = {candidate_id.strip() for candidate_id in candidate_ids if candidate_id.strip()}
    return [candidate for candidate in candidates if str(candidate.get("id")) in selected]


def paper_key(paper: dict) -> str:
    paper_id = paper.get("paperId")
    if paper_id:
        return f"paperId:{paper_id}"

    doi = paper.get("doi")
    if doi:
        return f"doi:{str(doi).lower()}"

    title = str(paper.get("title") or "").strip().lower()
    year = paper.get("year") or ""
    return f"title:{title}|year:{year}"


def normalize_paper(paper: dict) -> dict:
    external_ids = paper.get("externalIds") or {}
    return {
        "paperId": paper.get("paperId"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount") or 0,
        "venue": paper.get("venue"),
        "abstract": paper.get("abstract"),
        "doi": external_ids.get("DOI"),
    }


def top_paper_sort_key(paper: dict) -> tuple:
    return (
        int(paper.get("citationCount") or 0),
        int(paper.get("year") or 0),
        str(paper.get("title") or ""),
    )


def sparsity_rating(total_papers_found: int) -> str:
    if total_papers_found < 5:
        return "HIGH"
    if total_papers_found <= 20:
        return "MEDIUM"
    return "LOW"


def verdict_for_rating(rating: str) -> str:
    if rating == "HIGH":
        return "PROCEED - very sparse, high novelty potential"
    if rating == "MEDIUM":
        return "INVESTIGATE - meaningful gap may still exist"
    return "DEPRIORITIZE - crowded space unless a sharper gap is clear"


def note_for_candidate(total: int, recent_count: int, failed_queries: int) -> str:
    if failed_queries and total == 0:
        return "All Semantic Scholar queries failed or returned no usable results."
    if total == 0:
        return "No directly matching papers surfaced in the current keyword probe."
    if total < 5:
        return "Sparse result set across query variants; inspect top papers manually for fit."
    if total <= 20 and recent_count > 0:
        return "Moderate density with recent activity; check whether the existing papers actually solve the same problem."
    if total <= 20:
        return "Moderate density, but recent overlap appears limited."
    return "Many related papers surfaced; sharpen the framing or look for a narrower gap."


def run_candidate_verification(
    client: SemanticScholarClient,
    candidate: dict,
    limit: int,
    top_k: int,
    recent_year: int,
    timeout: float,
) -> dict:
    unique_papers: Dict[str, dict] = {}
    query_summaries: List[dict] = []

    raw_queries = candidate.get("novelty_search_queries") or []
    queries = []
    seen_queries = set()
    for raw_query in raw_queries:
        query = str(raw_query).strip()
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)
        queries.append(query)

    for query in queries:
        try:
            payload = client.search_papers(
                query=query,
                limit=limit,
                fields=DEFAULT_FIELDS,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            query_summaries.append(
                {
                    "query": query,
                    "status": "failed",
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
            continue

        papers = [normalize_paper(paper) for paper in payload.get("data", [])]
        query_summaries.append(
            {
                "query": query,
                "status": "ok",
                "paper_count": len(papers),
            }
        )

        for paper in papers:
            key = paper_key(paper)
            existing = unique_papers.get(key)
            if existing is None or top_paper_sort_key(paper) > top_paper_sort_key(existing):
                unique_papers[key] = paper

    ranked_papers = sorted(unique_papers.values(), key=top_paper_sort_key, reverse=True)
    total_papers_found = len(ranked_papers)
    recent_papers_count = sum(
        1 for paper in ranked_papers if int(paper.get("year") or 0) >= recent_year
    )
    failed_queries = sum(1 for item in query_summaries if item["status"] == "failed")
    rating = sparsity_rating(total_papers_found)

    return {
        "candidate_id": candidate["id"],
        "candidate_title": candidate.get("candidate_title")
        or candidate.get("innovation_direction")
        or candidate["id"],
        "queries_run": query_summaries,
        "total_papers_found": total_papers_found,
        "recent_papers_2022_plus": recent_papers_count,
        "sparsity_rating": rating,
        "top_existing_papers": [
            {
                "title": paper.get("title"),
                "year": paper.get("year"),
                "citationCount": paper.get("citationCount"),
                "venue": paper.get("venue"),
            }
            for paper in ranked_papers[:top_k]
        ],
        "verdict": verdict_for_rating(rating),
        "note": note_for_candidate(total_papers_found, recent_papers_count, failed_queries),
    }


def write_output(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)

    if args.limit < 1:
        raise ValueError("--limit must be >= 1.")
    if args.top_k < 1:
        raise ValueError("--top-k must be >= 1.")
    if args.timeout <= 0:
        raise ValueError("--timeout must be > 0.")

    candidates = filter_candidates(load_candidates(input_path), args.candidate_ids)
    if not candidates:
        raise ValueError("No matching candidates found after applying filters.")

    if args.dry_run:
        print(f"Candidates loaded: {len(candidates)}")
        for candidate in candidates:
            query_count = len(candidate.get("novelty_search_queries") or [])
            print(f"{candidate['id']}: queries={query_count}")
        return 0

    client = SemanticScholarClient()
    try:
        verifications = [
            run_candidate_verification(
                client=client,
                candidate=candidate,
                limit=args.limit,
                top_k=args.top_k,
                recent_year=args.recent_year,
                timeout=args.timeout,
            )
            for candidate in candidates
        ]
    finally:
        client.close()

    payload = {
        "generated_at": utc_now(),
        "source": {
            "input": str(input_path),
            "limit_per_query": args.limit,
            "recent_year_threshold": args.recent_year,
        },
        "verifications": verifications,
    }
    write_output(output_path, payload)

    print(f"Wrote: {output_path}")
    print(f"Candidates processed: {len(verifications)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
