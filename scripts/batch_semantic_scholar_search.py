import argparse
import concurrent.futures as cf
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from SemanticScholarApi import SemanticScholarClient


DEFAULT_CONFIG = Path("paper/semantic_scholar_search.yaml")
DEFAULT_INPUT_NAME = Path("search_keyword_prep.md")
DEFAULT_OUTPUT_NAME = Path("semantic_scholar_raw_results.jsonl")
DEFAULT_FAILURES_NAME = Path("semantic_scholar_failures.jsonl")
DEFAULT_FIELDS = (
    "paperId,title,year,authors,url,abstract,citationCount,"
    "influentialCitationCount,venue,externalIds"
)
DEFAULT_MODE = "single_thread"


@dataclass(frozen=True)
class QuerySpec:
    claim_id: str
    short_label: str
    core_keywords: str
    query_slot: str
    query_text: str
    notes: str

    @property
    def query_key(self) -> str:
        return f"{self.claim_id}:{self.query_slot}"


@dataclass(frozen=True)
class ModeProfile:
    workers: int
    max_retries: int
    retry_delay: float
    pause_seconds: float


@dataclass(frozen=True)
class SearchConfig:
    input: Path
    output: Path
    failures: Path
    limit: int
    timeout: float
    mode: str
    single_thread: ModeProfile
    multi_thread: ModeProfile
    claim_ids: List[str]
    dry_run: bool
    fields: str

    def selected_profile(self) -> ModeProfile:
        if self.mode == "single_thread":
            return self.single_thread
        if self.mode == "multi_thread":
            return self.multi_thread
        raise ValueError(f"Unsupported mode: {self.mode}")


def parse_args() -> Path:
    parser = argparse.ArgumentParser(
        description="Run batch Semantic Scholar searches from a YAML config file."
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Optional YAML config path. Defaults to paper/semantic_scholar_search.yaml.",
    )
    return parser.parse_args().config


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_bool(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "on"}:
            return True
        if normalized in {"false", "no", "0", "off"}:
            return False
    raise ValueError(f"Invalid boolean value for '{field_name}': {value!r}")


def parse_mode(value: object) -> str:
    if value is None:
        return DEFAULT_MODE

    mode = str(value).strip().lower()
    if mode not in {"single_thread", "multi_thread"}:
        raise ValueError(
            f"Invalid mode: {value!r}. Expected 'single_thread' or 'multi_thread'."
        )
    return mode


def resolve_path(value: Optional[object], base_dir: Path, fallback: Path) -> Path:
    if value in (None, ""):
        raw_path = fallback
    else:
        raw_path = Path(str(value))

    if raw_path.is_absolute():
        return raw_path
    return (base_dir / raw_path).resolve()


def parse_claim_ids(value: object) -> List[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        claim_ids = []
        for item in value:
            claim_id = str(item).strip()
            if claim_id:
                claim_ids.append(claim_id)
        return claim_ids
    raise ValueError(f"Invalid claim_ids value: {value!r}")


def parse_profile(name: str, raw: object, default_workers: int, default_pause: float) -> ModeProfile:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"Profile '{name}' must be a YAML mapping.")

    workers = int(raw.get("workers", default_workers))
    max_retries = int(raw.get("max_retries", 30))
    retry_delay = float(raw.get("retry_delay", 1.0))
    pause_seconds = float(raw.get("pause_seconds", default_pause))

    if workers < 1:
        raise ValueError(f"Profile '{name}' requires workers >= 1.")
    if max_retries < 1:
        raise ValueError(f"Profile '{name}' requires max_retries >= 1.")
    if retry_delay < 0:
        raise ValueError(f"Profile '{name}' requires retry_delay >= 0.")
    if pause_seconds < 0:
        raise ValueError(f"Profile '{name}' requires pause_seconds >= 0.")

    return ModeProfile(
        workers=workers,
        max_retries=max_retries,
        retry_delay=retry_delay,
        pause_seconds=pause_seconds,
    )


def load_config(path: Path) -> SearchConfig:
    config_path = path if path.is_absolute() else (REPO_ROOT / path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a YAML mapping.")

    base_dir = config_path.parent
    return SearchConfig(
        input=resolve_path(raw.get("input"), base_dir, DEFAULT_INPUT_NAME),
        output=resolve_path(raw.get("output"), base_dir, DEFAULT_OUTPUT_NAME),
        failures=resolve_path(raw.get("failures"), base_dir, DEFAULT_FAILURES_NAME),
        limit=int(raw.get("limit", 10)),
        timeout=float(raw.get("timeout", 30.0)),
        mode=parse_mode(raw.get("mode", DEFAULT_MODE)),
        single_thread=parse_profile(
            "single_thread",
            raw.get("single_thread"),
            default_workers=1,
            default_pause=1.0,
        ),
        multi_thread=parse_profile(
            "multi_thread",
            raw.get("multi_thread"),
            default_workers=8,
            default_pause=0.0,
        ),
        claim_ids=parse_claim_ids(raw.get("claim_ids", [])),
        dry_run=parse_bool(raw.get("dry_run", False), "dry_run"),
        fields=str(raw.get("fields", DEFAULT_FIELDS)),
    )


def compute_retry_sleep(retry_delay: float) -> float:
    return retry_delay


def strip_code_ticks(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1].strip()
    return value


def parse_query_file(path: Path) -> List[QuerySpec]:
    if not path.exists():
        raise FileNotFoundError(f"Query preparation file not found: {path}")

    queries: List[QuerySpec] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("| C"):
            continue

        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) != 7:
            raise ValueError(f"Unexpected table row format: {raw_line}")

        claim_id, short_label, core_keywords, query_1, query_2, query_3, notes = parts
        query_map = {
            "query_1": strip_code_ticks(query_1),
            "query_2": strip_code_ticks(query_2),
            "query_3": strip_code_ticks(query_3),
        }
        for query_slot, query_text in query_map.items():
            if not query_text or query_text == "N/A":
                continue
            queries.append(
                QuerySpec(
                    claim_id=claim_id,
                    short_label=short_label,
                    core_keywords=core_keywords,
                    query_slot=query_slot,
                    query_text=query_text,
                    notes=notes,
                )
            )

    return queries


def filter_queries(queries: Iterable[QuerySpec], claim_ids: List[str]) -> List[QuerySpec]:
    if not claim_ids:
        return list(queries)
    claim_filter = {claim_id.strip() for claim_id in claim_ids}
    return [query for query in queries if query.claim_id in claim_filter]


def load_completed_query_keys(path: Path) -> Set[str]:
    completed: Set[str] = set()
    if not path.exists():
        return completed

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            query_key = record.get("query_key")
            if query_key:
                completed.add(query_key)
    return completed


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def build_paper_key(paper: dict) -> str:
    paper_id = paper.get("paperId")
    if paper_id:
        return f"paperId:{paper_id}"

    external_ids = paper.get("externalIds") or {}
    doi = external_ids.get("DOI")
    if doi:
        return f"doi:{doi.lower()}"

    title = (paper.get("title") or "").strip().lower()
    year = paper.get("year") or ""
    return f"title:{title}|year:{year}"


def normalize_paper(paper: dict, rank: int) -> dict:
    authors = [author.get("name") for author in paper.get("authors", []) if author.get("name")]
    external_ids = paper.get("externalIds") or {}
    return {
        "rank": rank,
        "paperId": paper.get("paperId"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "authors": authors,
        "venue": paper.get("venue"),
        "url": paper.get("url"),
        "abstract": paper.get("abstract"),
        "citationCount": paper.get("citationCount"),
        "influentialCitationCount": paper.get("influentialCitationCount"),
        "externalIds": external_ids,
        "doi": external_ids.get("DOI"),
    }


def search_once(
    client: SemanticScholarClient,
    query_text: str,
    limit: int,
    timeout: float,
    fields: str,
) -> requests.Response:
    return client.session.get(
        f"{client.BASE_URL}/paper/search",
        params={
            "query": query_text,
            "limit": limit,
            "fields": fields,
        },
        timeout=timeout,
    )


def run_query(
    client: SemanticScholarClient,
    query: QuerySpec,
    limit: int,
    timeout: float,
    max_retries: int,
    retry_delay: float,
    fields: str,
) -> dict:
    attempt = 0
    last_status_code: Optional[int] = None

    while attempt < max_retries:
        attempt += 1
        try:
            response = search_once(
                client=client,
                query_text=query.query_text,
                limit=limit,
                timeout=timeout,
                fields=fields,
            )
            last_status_code = response.status_code

            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt >= max_retries:
                    response.raise_for_status()
                time.sleep(compute_retry_sleep(retry_delay))
                continue

            response.raise_for_status()
            payload = response.json()
            seen_keys: Set[str] = set()
            papers = []
            for raw_paper in payload.get("data", []):
                paper_key = build_paper_key(raw_paper)
                if paper_key in seen_keys:
                    continue
                seen_keys.add(paper_key)
                papers.append(normalize_paper(raw_paper, rank=len(papers) + 1))

            return {
                "status": "ok",
                "query_key": query.query_key,
                "claim_id": query.claim_id,
                "short_label": query.short_label,
                "query_slot": query.query_slot,
                "query_text": query.query_text,
                "core_keywords": query.core_keywords,
                "notes": query.notes,
                "attempts": attempt,
                "status_code": last_status_code,
                "limit": limit,
                "total_hits": payload.get("total"),
                "paper_count": len(papers),
                "papers": papers,
                "retrieved_at": utc_now(),
            }
        except requests.exceptions.HTTPError as exc:
            response = exc.response
            if response is not None:
                last_status_code = response.status_code
            retryable = last_status_code == 429 or (
                last_status_code is not None and 500 <= last_status_code < 600
            )
            if retryable and attempt < max_retries:
                time.sleep(compute_retry_sleep(retry_delay))
                continue
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < max_retries:
                time.sleep(compute_retry_sleep(retry_delay))
                continue
            raise

    raise RuntimeError(f"Query failed unexpectedly after {max_retries} attempts: {query.query_key}")


def execute_query(query: QuerySpec, config: SearchConfig, profile: ModeProfile) -> Tuple[bool, dict]:
    client = SemanticScholarClient()
    try:
        record = run_query(
            client=client,
            query=query,
            limit=config.limit,
            timeout=config.timeout,
            max_retries=profile.max_retries,
            retry_delay=profile.retry_delay,
            fields=config.fields,
        )
        return True, record
    except Exception as exc:
        failure_record = {
            "status": "failed",
            "query_key": query.query_key,
            "claim_id": query.claim_id,
            "short_label": query.short_label,
            "query_slot": query.query_slot,
            "query_text": query.query_text,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "failed_at": utc_now(),
        }
        return False, failure_record
    finally:
        client.close()


def run_single_thread(pending: List[QuerySpec], config: SearchConfig, profile: ModeProfile) -> int:
    success_count = 0
    failure_count = 0

    for index, query in enumerate(pending, start=1):
        print(f"[{index}/{len(pending)}] {query.query_key}: {query.query_text}")
        success, payload = execute_query(query, config, profile)
        if success:
            append_jsonl(config.output, payload)
            success_count += 1
            print(
                f"  ok: {payload['paper_count']} papers saved "
                f"(attempts={payload['attempts']}, status={payload['status_code']})"
            )
        else:
            append_jsonl(config.failures, payload)
            failure_count += 1
            print(f"  failed: {payload['error_type']} - {payload['error']}")

        if index < len(pending) and profile.pause_seconds > 0:
            time.sleep(profile.pause_seconds)

    print(
        f"Finished. mode=single_thread pending={len(pending)} success={success_count} "
        f"failure={failure_count} output={config.output} failures={config.failures}"
    )
    return 0 if failure_count == 0 else 2


def run_multi_thread(pending: List[QuerySpec], config: SearchConfig, profile: ModeProfile) -> int:
    success_count = 0
    failure_count = 0
    total = len(pending)

    with cf.ThreadPoolExecutor(max_workers=profile.workers) as executor:
        future_to_query = {}
        for index, query in enumerate(pending, start=1):
            future = executor.submit(execute_query, query, config, profile)
            future_to_query[future] = query
            if index < total and profile.pause_seconds > 0:
                time.sleep(profile.pause_seconds)

        completed_count = 0
        for future in cf.as_completed(future_to_query):
            completed_count += 1
            query = future_to_query[future]
            success, payload = future.result()
            print(f"[{completed_count}/{total}] {query.query_key}: {query.query_text}")
            if success:
                append_jsonl(config.output, payload)
                success_count += 1
                print(
                    f"  ok: {payload['paper_count']} papers saved "
                    f"(attempts={payload['attempts']}, status={payload['status_code']})"
                )
            else:
                append_jsonl(config.failures, payload)
                failure_count += 1
                print(f"  failed: {payload['error_type']} - {payload['error']}")

    print(
        f"Finished. mode=multi_thread pending={len(pending)} success={success_count} "
        f"failure={failure_count} output={config.output} failures={config.failures}"
    )
    return 0 if failure_count == 0 else 2


def main() -> int:
    config_path = parse_args()

    try:
        config = load_config(config_path)
        queries = filter_queries(parse_query_file(config.input), config.claim_ids)
    except Exception as exc:
        print(f"Failed to load configuration or queries: {exc}", file=sys.stderr)
        return 1

    if not queries:
        print("No queries found after applying filters.", file=sys.stderr)
        return 1

    completed = load_completed_query_keys(config.output)
    pending = [query for query in queries if query.query_key not in completed]

    if config.dry_run:
        print(f"Loaded {len(queries)} queries, {len(pending)} pending.")
        for query in pending:
            print(f"{query.query_key} -> {query.query_text}")
        return 0

    profile = config.selected_profile()
    if config.mode == "single_thread":
        return run_single_thread(pending, config, profile)
    return run_multi_thread(pending, config, profile)


if __name__ == "__main__":
    raise SystemExit(main())
