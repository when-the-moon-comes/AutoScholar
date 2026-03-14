import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "paper" / "innovation_candidates.json"
DEFAULT_STATE = REPO_ROOT / "paper" / "novelty_verification_state.json"
DEFAULT_OUTPUT = REPO_ROOT / "paper" / "novelty_verification.json"
DEFAULT_FIELDS = "paperId,title,year,authors,venue,abstract,citationCount,externalIds"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resumable Semantic Scholar novelty verification with checkpointing."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--recent-year", type=int, default=2022)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--sleep-ok", type=float, default=5.0)
    parser.add_argument("--sleep-429", type=float, default=10.0)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--candidate-id", action="append", dest="candidate_ids", default=[])
    parser.add_argument("--refresh-failed", action="store_true")
    parser.add_argument("--refresh-ok", action="store_true")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_candidates(path: Path) -> list[dict]:
    payload = load_json(path, {})
    candidates = payload.get("candidates") if isinstance(payload, dict) else payload
    if not isinstance(candidates, list):
        raise ValueError("innovation_candidates payload must contain a 'candidates' list")
    validated = []
    for candidate in candidates:
        candidate_id = str(candidate.get("id", "")).strip()
        queries = candidate.get("novelty_search_queries") or []
        if not candidate_id:
            raise ValueError("Each candidate requires a non-empty 'id'")
        if not isinstance(queries, list) or not any(str(item).strip() for item in queries):
            raise ValueError(f"Candidate '{candidate_id}' requires non-empty queries")
        validated.append(candidate)
    return validated


def normalize_paper(paper: dict) -> dict:
    external_ids = paper.get("externalIds") or {}
    return {
        "paperId": paper.get("paperId"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": int(paper.get("citationCount") or 0),
        "venue": paper.get("venue"),
        "abstract": paper.get("abstract"),
        "doi": external_ids.get("DOI"),
    }


def paper_key(paper: dict) -> str:
    if paper.get("paperId"):
        return f"paperId:{paper['paperId']}"
    if paper.get("doi"):
        return f"doi:{str(paper['doi']).lower()}"
    title = str(paper.get("title") or "").strip().lower()
    year = paper.get("year") or ""
    return f"title:{title}|year:{year}"


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


def fetch_query(query: str, limit: int, timeout: float, max_retries: int, sleep_ok: float, sleep_429: float) -> dict:
    params = urllib.parse.urlencode(
        {
            "query": query,
            "limit": limit,
            "fields": DEFAULT_FIELDS,
        }
    )
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"

    last_error_type = None
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            papers = [normalize_paper(paper) for paper in payload.get("data", [])]
            if sleep_ok > 0:
                time.sleep(sleep_ok)
            return {
                "query": query,
                "status": "ok",
                "paper_count": len(papers),
                "papers": papers,
                "fetched_at": utc_now(),
            }
        except urllib.error.HTTPError as exc:
            last_error_type = exc.__class__.__name__
            last_error = f"HTTP {exc.code}: {exc.reason}"
            if exc.code == 429 and attempt < max_retries:
                time.sleep(sleep_429 * attempt)
                continue
            break
        except Exception as exc:
            last_error_type = exc.__class__.__name__
            last_error = str(exc)
            break

    return {
        "query": query,
        "status": "failed",
        "error_type": last_error_type,
        "error": last_error,
        "fetched_at": utc_now(),
    }


def recompute_output(state: dict, candidates_by_id: dict[str, dict], top_k: int, recent_year: int) -> dict:
    verifications = []
    for candidate_id, candidate in candidates_by_id.items():
        candidate_state = state.setdefault("candidates", {}).setdefault(candidate_id, {"queries": {}})
        unique_papers = {}
        query_summaries = []

        for raw_query in candidate.get("novelty_search_queries") or []:
            query = str(raw_query).strip()
            if not query:
                continue
            query_state = candidate_state.get("queries", {}).get(query, {"query": query, "status": "missing"})
            summary = {"query": query, "status": query_state.get("status", "missing")}
            if summary["status"] == "ok":
                papers = query_state.get("papers", [])
                summary["paper_count"] = len(papers)
                for paper in papers:
                    key = paper_key(paper)
                    existing = unique_papers.get(key)
                    if existing is None or top_paper_sort_key(paper) > top_paper_sort_key(existing):
                        unique_papers[key] = paper
            elif summary["status"] == "failed":
                summary["error_type"] = query_state.get("error_type")
                summary["error"] = query_state.get("error")
            query_summaries.append(summary)

        ranked_papers = sorted(unique_papers.values(), key=top_paper_sort_key, reverse=True)
        total_papers_found = len(ranked_papers)
        recent_papers_count = sum(
            1 for paper in ranked_papers if int(paper.get("year") or 0) >= recent_year
        )
        failed_queries = sum(1 for item in query_summaries if item["status"] == "failed")
        rating = sparsity_rating(total_papers_found)

        verifications.append(
            {
                "candidate_id": candidate_id,
                "candidate_title": candidate.get("candidate_title"),
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
        )

    return {
        "generated_at": utc_now(),
        "verifications": verifications,
    }


def main() -> int:
    args = parse_args()
    input_path = resolve_path(args.input)
    state_path = resolve_path(args.state)
    output_path = resolve_path(args.output)

    all_candidates = load_candidates(input_path)
    candidates = all_candidates
    if args.candidate_ids:
        selected = {candidate_id.strip() for candidate_id in args.candidate_ids if candidate_id.strip()}
        candidates = [candidate for candidate in candidates if str(candidate.get("id")) in selected]

    candidates_by_id = {str(candidate["id"]): candidate for candidate in all_candidates}
    state = load_json(state_path, {"updated_at": utc_now(), "candidates": {}})

    for candidate in candidates:
        candidate_id = str(candidate["id"])
        candidate_state = state.setdefault("candidates", {}).setdefault(candidate_id, {"queries": {}})
        for raw_query in candidate.get("novelty_search_queries") or []:
            query = str(raw_query).strip()
            if not query:
                continue
            existing = candidate_state.setdefault("queries", {}).get(query)
            should_fetch = existing is None
            if existing is not None and existing.get("status") == "failed" and args.refresh_failed:
                should_fetch = True
            if existing is not None and existing.get("status") == "ok" and args.refresh_ok:
                should_fetch = True
            if not should_fetch:
                continue

            result = fetch_query(
                query=query,
                limit=args.limit,
                timeout=args.timeout,
                max_retries=args.max_retries,
                sleep_ok=args.sleep_ok,
                sleep_429=args.sleep_429,
            )
            candidate_state["queries"][query] = result
            state["updated_at"] = utc_now()
            save_json(state_path, state)

            output_payload = recompute_output(state, candidates_by_id, args.top_k, args.recent_year)
            save_json(output_path, output_payload)
            print(candidate_id, result["status"], query)

    output_payload = recompute_output(state, candidates_by_id, args.top_k, args.recent_year)
    save_json(output_path, output_payload)
    print(f"State: {state_path}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
