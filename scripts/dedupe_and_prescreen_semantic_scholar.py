import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = REPO_ROOT / "paper"
RAW_RESULTS = PAPER_DIR / "semantic_scholar_raw_results.jsonl"
CLAIM_UNITS = PAPER_DIR / "citation_claim_units.md"
DEDUPED_RESULTS = PAPER_DIR / "semantic_scholar_raw_results_deduped.jsonl"
PRESCREEN_REPORT = PAPER_DIR / "semantic_scholar_prescreen.md"


MANUAL_QUERY_OVERRIDES = {
    "C02:query_2": ("exclude", "off-topic retrieval; results are not usable for citation screening"),
}


@dataclass(frozen=True)
class ClaimInfo:
    claim_id: str
    section: str
    source_lines: str
    claim_text: str
    claim_type: str
    priority: str


def load_claim_units(path: Path) -> Dict[str, ClaimInfo]:
    claims: Dict[str, ClaimInfo] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("| C"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) != 6:
            continue
        claim = ClaimInfo(
            claim_id=parts[0],
            section=parts[1],
            source_lines=parts[2],
            claim_text=parts[3],
            claim_type=parts[4],
            priority=parts[5],
        )
        claims[claim.claim_id] = claim
    return claims


def load_raw_results(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def paper_key(paper: dict) -> str:
    if paper.get("paperId"):
        return f"paperId:{paper['paperId']}"
    if paper.get("doi"):
        return f"doi:{paper['doi'].lower()}"
    title = (paper.get("title") or "").strip().lower()
    year = paper.get("year") or ""
    return f"title:{title}|year:{year}"


def record_sort_key(record: dict) -> Tuple[int, int, str]:
    total_hits = record.get("total_hits")
    if total_hits is None:
        total_hits = -1
    return (
        int(record.get("paper_count", 0)),
        int(total_hits),
        str(record.get("retrieved_at", "")),
    )


def dedupe_record_papers(record: dict) -> dict:
    deduped = []
    seen = set()
    for paper in record.get("papers", []):
        key = paper_key(paper)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(paper)

    updated = dict(record)
    updated["papers"] = deduped
    updated["paper_count"] = len(deduped)
    return updated


def dedupe_query_records(records: List[dict]) -> Tuple[List[dict], int]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for record in records:
        grouped[record["query_key"]].append(record)

    deduped_records = []
    duplicate_count = 0
    for query_key, group in grouped.items():
        duplicate_count += max(0, len(group) - 1)
        best = max(group, key=record_sort_key)
        deduped_records.append(dedupe_record_papers(best))

    deduped_records.sort(key=lambda item: item["query_key"])
    return deduped_records, duplicate_count


def evaluate_query(record: dict) -> Tuple[str, str]:
    override = MANUAL_QUERY_OVERRIDES.get(record["query_key"])
    if override:
        return override

    paper_count = int(record.get("paper_count", 0))
    max_citations = max((paper.get("citationCount") or 0) for paper in record.get("papers", [])) if paper_count else 0

    if paper_count == 0:
        return "rewrite", "empty result set"
    if paper_count == 1 and max_citations == 0:
        return "rewrite", "single low-signal result"
    if max_citations == 0:
        return "review", "all returned papers currently have zero citations"
    if paper_count < 3:
        return "review", "small result set; keep but verify manually"
    return "keep", "usable for preliminary screening"


def build_claim_candidates(records: List[dict]) -> Dict[str, dict]:
    claims: Dict[str, dict] = {}

    for record in records:
        claim_id = record["claim_id"]
        claim_entry = claims.setdefault(
            claim_id,
            {
                "query_statuses": [],
                "papers": {},
            },
        )

        status, reason = evaluate_query(record)
        claim_entry["query_statuses"].append(
            {
                "query_key": record["query_key"],
                "status": status,
                "reason": reason,
                "paper_count": record["paper_count"],
                "total_hits": record.get("total_hits"),
            }
        )

        if status == "exclude" or record["paper_count"] == 0:
            continue

        for paper in record["papers"]:
            key = paper_key(paper)
            existing = claim_entry["papers"].get(key)
            if existing is None:
                claim_entry["papers"][key] = {
                    "paper": paper,
                    "supporting_query_keys": [record["query_key"]],
                }
                continue

            if record["query_key"] not in existing["supporting_query_keys"]:
                existing["supporting_query_keys"].append(record["query_key"])

            old_score = (
                existing["paper"].get("influentialCitationCount") or 0,
                existing["paper"].get("citationCount") or 0,
                existing["paper"].get("year") or 0,
            )
            new_score = (
                paper.get("influentialCitationCount") or 0,
                paper.get("citationCount") or 0,
                paper.get("year") or 0,
            )
            if new_score > old_score:
                existing["paper"] = paper

    return claims


def sort_claim_papers(papers: Dict[str, dict]) -> List[dict]:
    items = list(papers.values())
    items.sort(
        key=lambda item: (
            len(item["supporting_query_keys"]),
            item["paper"].get("influentialCitationCount") or 0,
            item["paper"].get("citationCount") or 0,
            item["paper"].get("year") or 0,
        ),
        reverse=True,
    )
    return items


def claim_screen_status(claim_entry: dict) -> str:
    papers = claim_entry["papers"]
    if not papers:
        return "rewrite"

    kept = [item for item in claim_entry["query_statuses"] if item["status"] == "keep"]
    if kept:
        return "ready"
    return "review"


def write_deduped_results(path: Path, records: List[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_prescreen_report(
    path: Path,
    claim_infos: Dict[str, ClaimInfo],
    deduped_records: List[dict],
    duplicate_count: int,
) -> None:
    claim_candidates = build_claim_candidates(deduped_records)
    query_review_rows = []
    for record in deduped_records:
        status, reason = evaluate_query(record)
        max_citations = max((paper.get("citationCount") or 0) for paper in record.get("papers", [])) if record["paper_count"] else 0
        query_review_rows.append(
            (
                record["claim_id"],
                record["query_key"],
                status,
                record["paper_count"],
                max_citations,
                reason,
            )
        )

    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Semantic Scholar Prescreen\n\n")
        handle.write("## Summary\n\n")
        handle.write(f"- Expected unique queries: {len(deduped_records)}\n")
        handle.write(f"- Duplicate success records removed: {duplicate_count}\n")
        handle.write(f"- Claims with at least one candidate: {len([k for k,v in claim_candidates.items() if v['papers']])}\n")
        handle.write(f"- Claims requiring query rewrite: {len([k for k,v in claim_candidates.items() if claim_screen_status(v) == 'rewrite'])}\n\n")

        handle.write("## Query Review\n\n")
        handle.write("| claim_id | query_key | status | paper_count | max_citations | note |\n")
        handle.write("| --- | --- | --- | --- | --- | --- |\n")
        for claim_id, query_key, status, paper_count, max_citations, reason in sorted(query_review_rows):
            handle.write(
                f"| {claim_id} | {query_key} | {status} | {paper_count} | {max_citations} | {reason} |\n"
            )

        handle.write("\n## Claim Shortlist\n")
        claim_ids = sorted(claim_infos.keys())
        for claim_id in claim_ids:
            claim_info = claim_infos[claim_id]
            claim_entry = claim_candidates.get(claim_id, {"query_statuses": [], "papers": {}})
            status = claim_screen_status(claim_entry)
            papers = sort_claim_papers(claim_entry["papers"])

            handle.write(f"\n### {claim_id}\n")
            handle.write(f"- Section: {claim_info.section}\n")
            handle.write(f"- Source lines: {claim_info.source_lines}\n")
            handle.write(f"- Claim type: {claim_info.claim_type}\n")
            handle.write(f"- Priority: {claim_info.priority}\n")
            handle.write(f"- Status: {status}\n")
            handle.write(f"- Claim: {claim_info.claim_text}\n")

            query_summaries = []
            for item in sorted(claim_entry["query_statuses"], key=lambda row: row["query_key"]):
                query_summaries.append(
                    f"{item['query_key']} [{item['status']}, papers={item['paper_count']}]"
                )
            handle.write(
                f"- Query summary: {', '.join(query_summaries) if query_summaries else 'no retrieved queries'}\n"
            )

            if not papers:
                handle.write("- Recommended papers: none yet; rewrite or supplement query set.\n")
                continue

            handle.write("- Recommended papers:\n")
            for index, item in enumerate(papers[:5], start=1):
                paper = item["paper"]
                support = ", ".join(sorted(item["supporting_query_keys"]))
                year = paper.get("year") or "n/a"
                cites = paper.get("citationCount") or 0
                doi = paper.get("doi") or "n/a"
                title = paper.get("title") or "Untitled"
                handle.write(
                    f"  {index}. {title} ({year}; cites={cites}; doi={doi}; support={support})\n"
                )


def main() -> int:
    claim_infos = load_claim_units(CLAIM_UNITS)
    raw_records = load_raw_results(RAW_RESULTS)
    deduped_records, duplicate_count = dedupe_query_records(raw_records)
    write_deduped_results(DEDUPED_RESULTS, deduped_records)
    write_prescreen_report(PRESCREEN_REPORT, claim_infos, deduped_records, duplicate_count)
    print(f"Deduped records: {len(deduped_records)}")
    print(f"Removed duplicate success records: {duplicate_count}")
    print(f"Wrote: {DEDUPED_RESULTS}")
    print(f"Wrote: {PRESCREEN_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
