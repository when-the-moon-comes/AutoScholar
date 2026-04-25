#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from SemanticScholarApi import SemanticScholarClient


DEFAULT_INPUT = REPO_ROOT / "paper" / "innovation_candidates.json"
DEFAULT_OUTPUT = REPO_ROOT / "paper" / "novelty_verification.json"
DEFAULT_FIELDS = (
    "paperId,title,year,authors,venue,url,abstract,citationCount,externalIds"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify dual-track idea-candidate novelty with Semantic Scholar using "
            "the local AutoScholar API client."
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


def normalize_track(value: object, default_track: str) -> str:
    normalized = str(value or default_track).strip().lower()
    mapping = {
        "a": "A",
        "track_a": "A",
        "track-a": "A",
        "b": "B",
        "track_b": "B",
        "track-b": "B",
    }
    return mapping.get(normalized, default_track)


def dedupe_queries(raw_queries: object) -> List[str]:
    if not isinstance(raw_queries, list):
        return []
    queries: List[str] = []
    seen = set()
    for raw_query in raw_queries:
        query = str(raw_query).strip()
        if not query or query in seen:
            continue
        seen.add(query)
        queries.append(query)
    return queries


def normalize_candidate(candidate: dict, default_track: str) -> dict:
    if not isinstance(candidate, dict):
        raise ValueError("Each candidate must be a JSON object.")

    candidate_id = str(candidate.get("id", "")).strip()
    if not candidate_id:
        raise ValueError("Each candidate requires a non-empty 'id'.")

    normalized = dict(candidate)
    normalized["id"] = candidate_id
    normalized["track"] = normalize_track(candidate.get("track"), default_track)
    normalized["novelty_search_queries"] = dedupe_queries(
        candidate.get("novelty_search_queries")
    )
    if not normalized["novelty_search_queries"]:
        raise ValueError(
            f"Candidate '{candidate_id}' requires a non-empty 'novelty_search_queries' list."
        )

    if normalized["track"] == "B":
        normalized["principle_level_search_queries"] = dedupe_queries(
            candidate.get("principle_level_search_queries")
        )
    return normalized


def load_candidates(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Candidate file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates: List[dict] = []

    if isinstance(payload, list):
        return [normalize_candidate(candidate, "A") for candidate in payload]

    if not isinstance(payload, dict):
        raise ValueError("innovation_candidates payload must be a JSON object or list.")

    if isinstance(payload.get("candidates"), list):
        return [normalize_candidate(candidate, "A") for candidate in payload["candidates"]]

    track_a_candidates = payload.get("track_a_candidates", [])
    track_b_candidates = payload.get("track_b_candidates", [])
    if not isinstance(track_a_candidates, list) or not isinstance(track_b_candidates, list):
        raise ValueError(
            "innovation_candidates payload must use lists for 'track_a_candidates' and 'track_b_candidates'."
        )

    candidates.extend(
        normalize_candidate(candidate, "A") for candidate in track_a_candidates
    )
    candidates.extend(
        normalize_candidate(candidate, "B") for candidate in track_b_candidates
    )
    return candidates


def filter_candidates(candidates: Iterable[dict], candidate_ids: List[str]) -> List[dict]:
    if not candidate_ids:
        return list(candidates)
    selected = {candidate_id.strip() for candidate_id in candidate_ids if candidate_id.strip()}
    return [candidate for candidate in candidates if candidate["id"] in selected]


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
        "url": paper.get("url"),
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


def verdict_for_track_a(rating: str) -> str:
    if rating == "HIGH":
        return "PROCEED - very sparse, high novelty potential"
    if rating == "MEDIUM":
        return "INVESTIGATE - meaningful gap may still exist"
    return "DEPRIORITIZE - crowded space unless a sharper gap is clear"


def verdict_for_track_b(task_rating: str, principle_rating: str) -> str:
    if principle_rating == "HIGH":
        if task_rating == "LOW":
            return "PROCEED - task area is active, but this principle transfer remains sparse"
        if task_rating == "MEDIUM":
            return "PROCEED - some task overlap exists, but the principle transfer still looks sparse"
        return "PROCEED - both task-level and principle-level searches are sparse"

    if principle_rating == "MEDIUM":
        if task_rating == "LOW":
            return "INVESTIGATE - the task is crowded, but the principle transfer may still leave a gap"
        return "INVESTIGATE - principle transfer shows moderate prior work"

    return "DEPRIORITIZE - principle transfer already looks crowded"


def seed_paper_ids(papers: List[dict], limit: int = 3) -> List[str]:
    seed_ids: List[str] = []
    for paper in papers:
        paper_id = paper.get("paperId")
        if not paper_id or paper_id in seed_ids:
            continue
        seed_ids.append(paper_id)
        if len(seed_ids) >= limit:
            break
    return seed_ids


def search_queries(
    client: SemanticScholarClient,
    queries: List[str],
    limit: int,
    timeout: float,
) -> dict:
    unique_papers: Dict[str, dict] = {}
    query_summaries: List[dict] = []

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
    return {
        "queries_run": query_summaries,
        "papers": ranked_papers,
        "failed_queries": sum(1 for item in query_summaries if item["status"] == "failed"),
    }


def summarize_search_result(
    search_result: dict,
    recent_year: int,
    top_k: int,
    *,
    query_source: Optional[str] = None,
) -> dict:
    papers = search_result["papers"]
    total_papers_found = len(papers)
    recent_papers_count = sum(
        1 for paper in papers if int(paper.get("year") or 0) >= recent_year
    )
    rating = sparsity_rating(total_papers_found)

    summary = {
        "queries_run": search_result["queries_run"],
        "total_papers_found": total_papers_found,
        "recent_papers_2022_plus": recent_papers_count,
        "sparsity_rating": rating,
        "top_existing_papers": [
            {
                "paperId": paper.get("paperId"),
                "title": paper.get("title"),
                "year": paper.get("year"),
                "citationCount": paper.get("citationCount"),
                "venue": paper.get("venue"),
                "url": paper.get("url"),
            }
            for paper in papers[:top_k]
        ],
        "seed_paper_ids": seed_paper_ids(papers),
    }
    if query_source is not None:
        summary["query_source"] = query_source
    return summary


def note_for_track_a(summary: dict, failed_queries: int) -> str:
    total = summary["total_papers_found"]
    recent_count = summary["recent_papers_2022_plus"]
    if failed_queries and total == 0:
        return "All Semantic Scholar queries failed or returned no usable results."
    if total == 0:
        return "No directly matching papers surfaced in the current keyword probe."
    if total < 5:
        return "Sparse result set across query variants; inspect top papers manually for fit."
    if total <= 20 and recent_count > 0:
        return "Moderate density with recent activity; manual inspection is still needed."
    if total <= 20:
        return "Moderate density, but recent overlap appears limited."
    return "Many related papers surfaced; sharpen the framing or narrow the deployment gap."


def note_for_track_b(
    task_summary: dict,
    principle_summary: dict,
    task_failed_queries: int,
    principle_failed_queries: int,
) -> str:
    notes: List[str] = []
    if principle_summary.get("query_source") == "fallback_to_task_queries":
        notes.append(
            "Track B principle-level queries were missing, so task-level queries were reused as a fallback."
        )
    if task_failed_queries or principle_failed_queries:
        notes.append("Some Semantic Scholar queries failed; review query coverage manually.")

    task_rating = task_summary["sparsity_rating"]
    principle_rating = principle_summary["sparsity_rating"]

    if task_rating == "LOW" and principle_rating == "HIGH":
        notes.append(
            "The target task is active, but very little evidence suggests that this specific principle has already transferred."
        )
    elif task_rating == "MEDIUM" and principle_rating == "HIGH":
        notes.append(
            "Existing task overlap exists, but the principle-level transfer still appears sparse."
        )
    elif principle_rating == "LOW":
        notes.append(
            "The principle itself already appears widely explored in the target domain."
        )
    elif principle_rating == "MEDIUM":
        notes.append(
            "The principle transfer shows some precedent and needs manual gap analysis."
        )
    else:
        notes.append("Both task-level and principle-level searches remain sparse.")

    return " ".join(notes)


def run_candidate_verification(
    client: SemanticScholarClient,
    candidate: dict,
    limit: int,
    top_k: int,
    recent_year: int,
    timeout: float,
) -> dict:
    task_queries = candidate["novelty_search_queries"]
    task_search_result = search_queries(
        client=client,
        queries=task_queries,
        limit=limit,
        timeout=timeout,
    )
    task_summary = summarize_search_result(
        search_result=task_search_result,
        recent_year=recent_year,
        top_k=top_k,
    )

    verification = {
        "candidate_id": candidate["id"],
        "track": candidate["track"],
        "candidate_title": candidate.get("candidate_title")
        or candidate.get("innovation_direction")
        or candidate["id"],
        "convergence_with": candidate.get("convergence_with"),
        "autoscholar_queries": task_queries,
        "seed_paper_ids": task_summary["seed_paper_ids"],
        "queries_run": task_summary["queries_run"],
        "total_papers_found": task_summary["total_papers_found"],
        "recent_papers_2022_plus": task_summary["recent_papers_2022_plus"],
        "sparsity_rating": task_summary["sparsity_rating"],
        "top_existing_papers": task_summary["top_existing_papers"],
    }

    if candidate["track"] == "A":
        verification["verdict"] = verdict_for_track_a(task_summary["sparsity_rating"])
        verification["note"] = note_for_track_a(
            task_summary,
            task_search_result["failed_queries"],
        )
        return verification

    principle_queries = candidate.get("principle_level_search_queries") or []
    query_source = "explicit"
    if not principle_queries:
        principle_queries = task_queries
        query_source = "fallback_to_task_queries"

    principle_search_result = search_queries(
        client=client,
        queries=principle_queries,
        limit=limit,
        timeout=timeout,
    )
    principle_summary = summarize_search_result(
        search_result=principle_search_result,
        recent_year=recent_year,
        top_k=top_k,
        query_source=query_source,
    )

    verification["principle_level_search"] = principle_summary
    verification["verdict"] = verdict_for_track_b(
        task_summary["sparsity_rating"],
        principle_summary["sparsity_rating"],
    )
    verification["note"] = note_for_track_b(
        task_summary,
        principle_summary,
        task_search_result["failed_queries"],
        principle_search_result["failed_queries"],
    )
    return verification


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
            principle_count = len(candidate.get("principle_level_search_queries") or [])
            print(
                f"{candidate['id']}: track={candidate['track']} "
                f"task_queries={len(candidate['novelty_search_queries'])} "
                f"principle_queries={principle_count}"
            )
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
