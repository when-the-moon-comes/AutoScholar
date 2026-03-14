import argparse
import concurrent.futures as cf
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

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
    "influentialCitationCount,venue,externalIds,isOpenAccess,openAccessPdf"
)
DEFAULT_MODE = "single_thread"
DEFAULT_ENDPOINT = "relevance"


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
    endpoint: str
    single_thread: ModeProfile
    multi_thread: ModeProfile
    claim_ids: List[str]
    dry_run: bool
    fields: str
    sort: Optional[str]
    publication_types: List[str]
    open_access_pdf: Optional[bool]
    min_citation_count: Optional[int]
    publication_date_or_year: Optional[str]
    year: Optional[str]
    venue: Optional[str]
    fields_of_study: List[str]

    def selected_profile(self) -> ModeProfile:
        if self.mode == "single_thread":
            return self.single_thread
        if self.mode == "multi_thread":
            return self.multi_thread
        raise ValueError(f"Unsupported mode: {self.mode}")

    def search_options(self) -> Dict[str, object]:
        options: Dict[str, object] = {
            "endpoint": self.endpoint,
            "limit": self.limit,
            "fields": self.fields,
        }
        if self.sort:
            options["sort"] = self.sort
        if self.publication_types:
            options["publication_types"] = self.publication_types
        if self.open_access_pdf is not None:
            options["open_access_pdf"] = self.open_access_pdf
        if self.min_citation_count is not None:
            options["min_citation_count"] = self.min_citation_count
        if self.publication_date_or_year:
            options["publication_date_or_year"] = self.publication_date_or_year
        if self.year:
            options["year"] = self.year
        if self.venue:
            options["venue"] = self.venue
        if self.fields_of_study:
            options["fields_of_study"] = self.fields_of_study
        return options

    def search_signature(self) -> str:
        return json.dumps(self.search_options(), sort_keys=True, ensure_ascii=True)


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


def parse_optional_bool(value: object, field_name: str) -> Optional[bool]:
    if value in (None, ""):
        return None
    return parse_bool(value, field_name)


def parse_mode(value: object) -> str:
    if value is None:
        return DEFAULT_MODE

    mode = str(value).strip().lower()
    if mode not in {"single_thread", "multi_thread"}:
        raise ValueError(
            f"Invalid mode: {value!r}. Expected 'single_thread' or 'multi_thread'."
        )
    return mode


def parse_endpoint(value: object) -> str:
    if value in (None, ""):
        return DEFAULT_ENDPOINT

    endpoint = str(value).strip().lower()
    mapping = {
        "relevance": "relevance",
        "search": "relevance",
        "paper_search": "relevance",
        "bulk": "bulk",
        "bulk_search": "bulk",
        "paper_search_bulk": "bulk",
    }
    if endpoint not in mapping:
        raise ValueError(
            f"Invalid endpoint: {value!r}. Expected 'relevance' or 'bulk'."
        )
    return mapping[endpoint]


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


def parse_string_list(value: object, field_name: str) -> List[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
        return [item for item in items if item]
    if isinstance(value, list):
        items = [str(item).strip() for item in value]
        return [item for item in items if item]
    raise ValueError(f"Invalid list value for '{field_name}': {value!r}")


def parse_optional_str(value: object) -> Optional[str]:
    if value in (None, ""):
        return None
    normalized = str(value).strip()
    return normalized or None


def parse_optional_int(value: object, field_name: str) -> Optional[int]:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"Field '{field_name}' must be >= 0.")
    return parsed


def parse_mapping(value: object, field_name: str) -> Dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Field '{field_name}' must be a YAML mapping.")
    return value


def read_config_value(
    raw: Dict[str, object],
    *paths: Tuple[str, ...] | str,
    default: object = None,
) -> object:
    for path in paths:
        keys = (path,) if isinstance(path, str) else path
        current: object = raw
        found = True
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                found = False
                break
            current = current[key]
        if found:
            return current
    return default


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


def validate_config(config: SearchConfig) -> None:
    if config.limit < 1:
        raise ValueError("Config field 'limit' must be >= 1.")
    if config.timeout <= 0:
        raise ValueError("Config field 'timeout' must be > 0.")

    if config.endpoint == "relevance":
        bulk_only_options_used = any(
            [
                config.sort,
                config.publication_types,
                config.open_access_pdf is not None,
                config.min_citation_count is not None,
                config.publication_date_or_year,
                config.year,
                config.venue,
                config.fields_of_study,
            ]
        )
        if bulk_only_options_used:
            raise ValueError(
                "Bulk-only search filters require endpoint='bulk'."
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
    paths_section = parse_mapping(raw.get("paths"), "paths")
    run_section = parse_mapping(raw.get("run"), "run")
    search_section = parse_mapping(raw.get("search"), "search")
    filters_section = parse_mapping(search_section.get("filters"), "search.filters")
    execution_section = parse_mapping(raw.get("execution"), "execution")

    config = SearchConfig(
        input=resolve_path(
            read_config_value(paths_section, "input", default=raw.get("input")),
            base_dir,
            DEFAULT_INPUT_NAME,
        ),
        output=resolve_path(
            read_config_value(paths_section, "output", default=raw.get("output")),
            base_dir,
            DEFAULT_OUTPUT_NAME,
        ),
        failures=resolve_path(
            read_config_value(paths_section, "failures", default=raw.get("failures")),
            base_dir,
            DEFAULT_FAILURES_NAME,
        ),
        limit=int(
            read_config_value(search_section, "limit", default=raw.get("limit", 10))
        ),
        timeout=float(
            read_config_value(search_section, "timeout", default=raw.get("timeout", 30.0))
        ),
        mode=parse_mode(
            read_config_value(execution_section, "mode", default=raw.get("mode", DEFAULT_MODE))
        ),
        endpoint=parse_endpoint(
            read_config_value(search_section, "endpoint", default=raw.get("endpoint", DEFAULT_ENDPOINT))
        ),
        single_thread=parse_profile(
            "single_thread",
            read_config_value(
                execution_section,
                "single_thread",
                default=raw.get("single_thread"),
            ),
            default_workers=1,
            default_pause=1.0,
        ),
        multi_thread=parse_profile(
            "multi_thread",
            read_config_value(
                execution_section,
                "multi_thread",
                default=raw.get("multi_thread"),
            ),
            default_workers=8,
            default_pause=0.0,
        ),
        claim_ids=parse_claim_ids(
            read_config_value(run_section, "claim_ids", default=raw.get("claim_ids", []))
        ),
        dry_run=parse_bool(
            read_config_value(run_section, "dry_run", default=raw.get("dry_run", False)),
            "dry_run",
        ),
        fields=str(
            read_config_value(search_section, "fields", default=raw.get("fields", DEFAULT_FIELDS))
        ),
        sort=parse_optional_str(
            read_config_value(filters_section, "sort", default=raw.get("sort"))
        ),
        publication_types=parse_string_list(
            read_config_value(
                filters_section,
                "publication_types",
                default=raw.get("publication_types"),
            ),
            "publication_types",
        ),
        open_access_pdf=parse_optional_bool(
            read_config_value(
                filters_section,
                "open_access_pdf",
                default=raw.get("open_access_pdf"),
            ),
            "open_access_pdf",
        ),
        min_citation_count=parse_optional_int(
            read_config_value(
                filters_section,
                "min_citation_count",
                default=raw.get("min_citation_count"),
            ),
            "min_citation_count",
        ),
        publication_date_or_year=parse_optional_str(
            read_config_value(
                filters_section,
                "publication_date_or_year",
                default=raw.get("publication_date_or_year"),
            )
        ),
        year=parse_optional_str(
            read_config_value(filters_section, "year", default=raw.get("year"))
        ),
        venue=parse_optional_str(
            read_config_value(filters_section, "venue", default=raw.get("venue"))
        ),
        fields_of_study=parse_string_list(
            read_config_value(
                filters_section,
                "fields_of_study",
                default=raw.get("fields_of_study"),
            ),
            "fields_of_study",
        ),
    )
    validate_config(config)
    return config


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


def load_completed_query_keys(path: Path, config: SearchConfig) -> Set[str]:
    completed: Set[str] = set()
    if not path.exists():
        return completed

    expected_signature = config.search_signature()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            query_key = record.get("query_key")
            if not query_key:
                continue

            record_signature = record.get("search_signature")
            if record_signature:
                if record_signature == expected_signature:
                    completed.add(query_key)
                continue

            legacy_endpoint = record.get("endpoint", "relevance")
            if config.endpoint == "relevance" and legacy_endpoint == "relevance":
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
        "isOpenAccess": paper.get("isOpenAccess"),
        "openAccessPdf": paper.get("openAccessPdf"),
    }


def build_bulk_search_kwargs(config: SearchConfig) -> Dict[str, object]:
    kwargs: Dict[str, object] = {}
    if config.sort:
        kwargs["sort"] = config.sort
    if config.publication_types:
        kwargs["publication_types"] = config.publication_types
    if config.open_access_pdf is not None:
        kwargs["open_access_pdf"] = config.open_access_pdf
    if config.min_citation_count is not None:
        kwargs["min_citation_count"] = config.min_citation_count
    if config.publication_date_or_year:
        kwargs["publication_date_or_year"] = config.publication_date_or_year
    if config.year:
        kwargs["year"] = config.year
    if config.venue:
        kwargs["venue"] = config.venue
    if config.fields_of_study:
        kwargs["fields_of_study"] = config.fields_of_study
    return kwargs


def collect_unique_papers(raw_papers: Iterable[dict], limit: int) -> List[dict]:
    seen_keys: Set[str] = set()
    papers: List[dict] = []

    for raw_paper in raw_papers:
        paper_key = build_paper_key(raw_paper)
        if paper_key in seen_keys:
            continue
        seen_keys.add(paper_key)
        papers.append(normalize_paper(raw_paper, rank=len(papers) + 1))
        if len(papers) >= limit:
            break

    return papers


def run_relevance_search(
    client: SemanticScholarClient,
    query_text: str,
    limit: int,
    timeout: float,
    fields: str,
) -> dict:
    payload = client.search_papers(
        query=query_text,
        limit=limit,
        fields=fields,
        timeout=timeout,
    )
    papers = collect_unique_papers(payload.get("data", []), limit=limit)
    return {
        "status_code": 200,
        "total_hits": payload.get("total"),
        "papers": papers,
        "page_count": 1,
    }


def run_bulk_search(
    client: SemanticScholarClient,
    query_text: str,
    limit: int,
    timeout: float,
    fields: str,
    config: SearchConfig,
) -> dict:
    papers: List[dict] = []
    seen_keys: Set[str] = set()
    total_hits = None
    token: Optional[str] = None
    page_count = 0

    while True:
        payload = client.search_papers_bulk_page(
            query=query_text,
            fields=fields,
            token=token,
            timeout=timeout,
            **build_bulk_search_kwargs(config),
        )
        page_count += 1
        if total_hits is None:
            total_hits = payload.get("total")

        for raw_paper in payload.get("data", []):
            paper_key = build_paper_key(raw_paper)
            if paper_key in seen_keys:
                continue
            seen_keys.add(paper_key)
            papers.append(normalize_paper(raw_paper, rank=len(papers) + 1))
            if len(papers) >= limit:
                return {
                    "status_code": 200,
                    "total_hits": total_hits,
                    "papers": papers,
                    "page_count": page_count,
                }

        token = payload.get("token")
        if not token:
            return {
                "status_code": 200,
                "total_hits": total_hits,
                "papers": papers,
                "page_count": page_count,
            }


def run_query(
    client: SemanticScholarClient,
    query: QuerySpec,
    config: SearchConfig,
    max_retries: int,
    retry_delay: float,
) -> dict:
    attempt = 0
    last_status_code: Optional[int] = None

    while attempt < max_retries:
        attempt += 1
        try:
            if config.endpoint == "bulk":
                result = run_bulk_search(
                    client=client,
                    query_text=query.query_text,
                    limit=config.limit,
                    timeout=config.timeout,
                    fields=config.fields,
                    config=config,
                )
            else:
                result = run_relevance_search(
                    client=client,
                    query_text=query.query_text,
                    limit=config.limit,
                    timeout=config.timeout,
                    fields=config.fields,
                )

            last_status_code = int(result["status_code"])
            return {
                "status": "ok",
                "query_key": query.query_key,
                "claim_id": query.claim_id,
                "short_label": query.short_label,
                "query_slot": query.query_slot,
                "query_text": query.query_text,
                "core_keywords": query.core_keywords,
                "notes": query.notes,
                "endpoint": config.endpoint,
                "search_options": config.search_options(),
                "search_signature": config.search_signature(),
                "attempts": attempt,
                "status_code": last_status_code,
                "limit": config.limit,
                "page_count": result["page_count"],
                "total_hits": result["total_hits"],
                "paper_count": len(result["papers"]),
                "papers": result["papers"],
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
            config=config,
            max_retries=profile.max_retries,
            retry_delay=profile.retry_delay,
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
            "endpoint": config.endpoint,
            "search_options": config.search_options(),
            "search_signature": config.search_signature(),
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
                f"(endpoint={payload['endpoint']}, pages={payload['page_count']}, "
                f"attempts={payload['attempts']}, status={payload['status_code']})"
            )
        else:
            append_jsonl(config.failures, payload)
            failure_count += 1
            print(f"  failed: {payload['error_type']} - {payload['error']}")

        if index < len(pending) and profile.pause_seconds > 0:
            time.sleep(profile.pause_seconds)

    print(
        f"Finished. mode=single_thread endpoint={config.endpoint} pending={len(pending)} "
        f"success={success_count} failure={failure_count} output={config.output} "
        f"failures={config.failures}"
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
                    f"(endpoint={payload['endpoint']}, pages={payload['page_count']}, "
                    f"attempts={payload['attempts']}, status={payload['status_code']})"
                )
            else:
                append_jsonl(config.failures, payload)
                failure_count += 1
                print(f"  failed: {payload['error_type']} - {payload['error']}")

    print(
        f"Finished. mode=multi_thread endpoint={config.endpoint} pending={len(pending)} "
        f"success={success_count} failure={failure_count} output={config.output} "
        f"failures={config.failures}"
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

    completed = load_completed_query_keys(config.output, config)
    pending = [query for query in queries if query.query_key not in completed]

    if config.dry_run:
        print(
            f"Loaded {len(queries)} queries, {len(pending)} pending. "
            f"endpoint={config.endpoint} options={json.dumps(config.search_options(), ensure_ascii=False)}"
        )
        for query in pending:
            print(f"{query.query_key} -> {query.query_text}")
        return 0

    profile = config.selected_profile()
    if config.mode == "single_thread":
        return run_single_thread(pending, config, profile)
    return run_multi_thread(pending, config, profile)


if __name__ == "__main__":
    raise SystemExit(main())
