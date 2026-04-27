import argparse
import importlib.util
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from SemanticScholarApi import SemanticScholarClient


DEFAULT_CONFIG = Path("config/recommendation_auto_correct.yaml")
DEFAULT_FIELDS = (
    "paperId,title,year,authors,url,abstract,citationCount,"
    "influentialCitationCount,venue,externalIds,isOpenAccess,openAccessPdf"
)


@dataclass(frozen=True)
class TriggerSettings:
    min_selected_papers: int
    min_cross_query_support: int
    low_citation_threshold: int
    max_low_signal_candidates: int
    include_review_status: bool
    include_claim_notes: bool


@dataclass(frozen=True)
class ClaimSeedControl:
    positive: List[str]
    negative: List[str]
    blocked: List[str]


@dataclass(frozen=True)
class SeedSettings:
    selection_mode: str
    max_seeds_per_claim: int
    min_total_overlap: int
    claim_overrides: Dict[str, ClaimSeedControl]


@dataclass(frozen=True)
class RecommendationSettings:
    method: str
    per_seed_limit: int
    top_candidates_per_claim: int
    ready_candidate_count: int
    ready_min_total_overlap: int
    pause_seconds: float
    fields: str


@dataclass(frozen=True)
class CorrectionConfig:
    claim_units: Path
    deduped_results: Path
    recommendation_rules: Path
    output_jsonl: Path
    output_report: Path
    claim_ids: List[str]
    dry_run: bool
    trigger: TriggerSettings
    seed: SeedSettings
    recommendations: RecommendationSettings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a standalone Semantic Scholar recommendation-based correction pass "
            "for claims with weak or mixed retrieval."
        )
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Optional YAML config path. Defaults to config/recommendation_auto_correct.yaml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate trigger and seed selection without calling the Recommendations API.",
    )
    parser.add_argument(
        "--claim-id",
        action="append",
        dest="claim_ids",
        default=[],
        help="Optional claim ID to process. Can be passed multiple times.",
    )
    return parser.parse_args()


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


def parse_claim_ids(value: object) -> List[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        claim_ids: List[str] = []
        for item in value:
            claim_id = str(item).strip()
            if claim_id:
                claim_ids.append(claim_id)
        return claim_ids
    raise ValueError(f"Invalid claim_ids value: {value!r}")


def resolve_path(value: Optional[object], base_dir: Path, fallback: Path) -> Path:
    if value in (None, ""):
        raw_path = fallback
    else:
        raw_path = Path(str(value))

    if raw_path.is_absolute():
        return raw_path
    return (base_dir / raw_path).resolve()


def default_rules_path() -> Path:
    paper_rules = REPO_ROOT / "paper" / "claim_recommendation_rules.yaml"
    if paper_rules.exists():
        return paper_rules
    return REPO_ROOT / "config" / "claim_recommendation_rules.yaml"


def parse_seed_reference(value: object, field_name: str) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError(f"Config field '{field_name}' contains an empty seed reference.")
        if normalized.startswith(("paperid:", "doi:", "title:")):
            return normalized
        raise ValueError(
            f"Config field '{field_name}' must use 'paperId:', 'doi:', or 'title:...|year:...'."
        )

    if isinstance(value, dict):
        if "paper_key" in value:
            return parse_seed_reference(value["paper_key"], field_name)

        paper_id = value.get("paperId", value.get("paper_id"))
        if paper_id not in (None, ""):
            return f"paperid:{str(paper_id).strip().lower()}"

        doi = value.get("doi")
        if doi not in (None, ""):
            return f"doi:{str(doi).strip().lower()}"

        title = value.get("title")
        if title not in (None, ""):
            normalized_title = str(title).strip().lower()
            year = value.get("year", "")
            return f"title:{normalized_title}|year:{year}"

    raise ValueError(
        f"Config field '{field_name}' must be a string seed reference or a mapping with "
        "'paperId', 'doi', 'paper_key', or 'title'+'year'."
    )


def parse_seed_reference_list(value: object, field_name: str) -> List[str]:
    if value in (None, "", []):
        return []
    if not isinstance(value, list):
        raise ValueError(f"Config field '{field_name}' must be a list.")

    refs: List[str] = []
    seen = set()
    for item in value:
        ref = parse_seed_reference(item, field_name)
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs


def parse_claim_seed_controls(raw: object) -> Dict[str, ClaimSeedControl]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Config field 'seed.claim_overrides' must be a YAML mapping.")

    overrides: Dict[str, ClaimSeedControl] = {}
    for claim_id, value in raw.items():
        normalized_claim_id = str(claim_id).strip()
        if not normalized_claim_id:
            continue
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise ValueError(
                f"Config field 'seed.claim_overrides.{normalized_claim_id}' must be a mapping."
            )
        overrides[normalized_claim_id] = ClaimSeedControl(
            positive=parse_seed_reference_list(
                value.get("positive"),
                f"seed.claim_overrides.{normalized_claim_id}.positive",
            ),
            negative=parse_seed_reference_list(
                value.get("negative"),
                f"seed.claim_overrides.{normalized_claim_id}.negative",
            ),
            blocked=parse_seed_reference_list(
                value.get("blocked"),
                f"seed.claim_overrides.{normalized_claim_id}.blocked",
            ),
        )
    return overrides


def parse_trigger_settings(raw: object) -> TriggerSettings:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Config field 'trigger' must be a YAML mapping.")

    return TriggerSettings(
        min_selected_papers=int(raw.get("min_selected_papers", 2)),
        min_cross_query_support=int(raw.get("min_cross_query_support", 2)),
        low_citation_threshold=int(raw.get("low_citation_threshold", 10)),
        max_low_signal_candidates=int(raw.get("max_low_signal_candidates", 2)),
        include_review_status=parse_bool(
            raw.get("include_review_status", True),
            "trigger.include_review_status",
        ),
        include_claim_notes=parse_bool(
            raw.get("include_claim_notes", True),
            "trigger.include_claim_notes",
        ),
    )


def parse_seed_settings(raw: object) -> SeedSettings:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Config field 'seed' must be a YAML mapping.")

    selection_mode = str(raw.get("selection_mode", "auto")).strip().lower()
    if selection_mode not in {"auto", "hybrid", "manual"}:
        raise ValueError(
            "Config field 'seed.selection_mode' must be 'auto', 'hybrid', or 'manual'."
        )

    return SeedSettings(
        selection_mode=selection_mode,
        max_seeds_per_claim=int(raw.get("max_seeds_per_claim", 2)),
        min_total_overlap=int(raw.get("min_total_overlap", 2)),
        claim_overrides=parse_claim_seed_controls(raw.get("claim_overrides")),
    )


def parse_recommendation_settings(raw: object) -> RecommendationSettings:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Config field 'recommendations' must be a YAML mapping.")

    method = str(raw.get("method", "positive_seed_list")).strip().lower()
    if method not in {"single_seed", "positive_seed_list"}:
        raise ValueError(
            "Config field 'recommendations.method' must be 'single_seed' or 'positive_seed_list'."
        )

    return RecommendationSettings(
        method=method,
        per_seed_limit=int(raw.get("per_seed_limit", 5)),
        top_candidates_per_claim=int(raw.get("top_candidates_per_claim", 5)),
        ready_candidate_count=int(raw.get("ready_candidate_count", 2)),
        ready_min_total_overlap=int(raw.get("ready_min_total_overlap", 3)),
        pause_seconds=float(raw.get("pause_seconds", 0.2)),
        fields=str(raw.get("fields", DEFAULT_FIELDS)),
    )


def load_config(path: Path) -> CorrectionConfig:
    config_path = path if path.is_absolute() else (REPO_ROOT / path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a YAML mapping.")

    base_dir = config_path.parent
    return CorrectionConfig(
        claim_units=resolve_path(raw.get("claim_units"), base_dir, Path("paper/citation_claim_units.md")),
        deduped_results=resolve_path(
            raw.get("deduped_results"),
            base_dir,
            Path("paper/semantic_scholar_raw_results_deduped.jsonl"),
        ),
        recommendation_rules=resolve_path(
            raw.get("recommendation_rules"),
            base_dir,
            default_rules_path(),
        ),
        output_jsonl=resolve_path(
            raw.get("output_jsonl"),
            base_dir,
            Path("paper/semantic_scholar_recommendation_corrections.jsonl"),
        ),
        output_report=resolve_path(
            raw.get("output_report"),
            base_dir,
            Path("paper/semantic_scholar_recommendation_correction_report.md"),
        ),
        claim_ids=parse_claim_ids(raw.get("claim_ids", [])),
        dry_run=parse_bool(raw.get("dry_run", False), "dry_run"),
        trigger=parse_trigger_settings(raw.get("trigger")),
        seed=parse_seed_settings(raw.get("seed")),
        recommendations=parse_recommendation_settings(raw.get("recommendations")),
    )


def load_script_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def paper_strength(paper: dict) -> Tuple[int, int, int]:
    return (
        paper.get("influentialCitationCount") or 0,
        paper.get("citationCount") or 0,
        paper.get("year") or 0,
    )


def normalize_recommended_paper(paper: dict) -> dict:
    authors = [author.get("name") for author in paper.get("authors", []) if author.get("name")]
    external_ids = paper.get("externalIds") or {}
    return {
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


def effective_query_review(record: dict, rules: Any, prescreen_module: Any) -> dict:
    if record["query_key"] in rules.excluded_queries:
        return {
            "query_key": record["query_key"],
            "status": "exclude",
            "reason": rules.excluded_queries[record["query_key"]],
            "paper_count": int(record.get("paper_count", 0)),
        }

    status, reason = prescreen_module.evaluate_query(record)
    return {
        "query_key": record["query_key"],
        "status": status,
        "reason": reason,
        "paper_count": int(record.get("paper_count", 0)),
    }


def build_claim_context_tokens(
    claim: Any,
    claim_records: List[dict],
    rules: Any,
    recommendation_module: Any,
) -> Tuple[set[str], set[str]]:
    claim_tokens = recommendation_module.tokenize(claim.claim_text, rules.stopwords)
    query_tokens = set()
    for record in claim_records:
        query_tokens |= recommendation_module.tokenize(record.get("query_text", ""), rules.stopwords)
        query_tokens |= recommendation_module.tokenize(record.get("short_label", ""), rules.stopwords)
        query_tokens |= recommendation_module.tokenize(record.get("core_keywords", ""), rules.stopwords)
    return claim_tokens, query_tokens


def paper_overlap_features(
    paper: dict,
    claim_tokens: set[str],
    query_tokens: set[str],
    rules: Any,
    recommendation_module: Any,
) -> Tuple[int, int]:
    paper_text = " ".join(
        part for part in [paper.get("title", ""), paper.get("abstract", ""), paper.get("venue", "")]
        if part
    )
    paper_tokens = recommendation_module.tokenize(paper_text, rules.stopwords)
    return len(claim_tokens & paper_tokens), len(query_tokens & paper_tokens)


def build_query_candidate_groups(
    claim: Any,
    claim_records: List[dict],
    rules: Any,
    recommendation_module: Any,
) -> Dict[str, dict]:
    claim_tokens, query_tokens = build_claim_context_tokens(
        claim=claim,
        claim_records=claim_records,
        rules=rules,
        recommendation_module=recommendation_module,
    )

    grouped: Dict[str, dict] = {}
    usable_records = [
        record
        for record in claim_records
        if record["query_key"] not in rules.excluded_queries and int(record.get("paper_count", 0)) > 0
    ]

    for record in usable_records:
        for paper in record.get("papers", []):
            exclusion_reason = recommendation_module.paper_exclusion_reason(paper, rules)
            if exclusion_reason:
                continue

            paper_key = recommendation_module.paper_key(paper)
            entry = grouped.setdefault(
                paper_key,
                {
                    "paper": paper,
                    "supporting_records": [],
                    "recommended_by_seed_ids": set(),
                    "recommended_by_seed_titles": set(),
                    "claim_overlap": 0,
                    "query_overlap": 0,
                },
            )
            entry["supporting_records"].append(record)
            if paper_strength(paper) > paper_strength(entry["paper"]):
                entry["paper"] = paper

    for entry in grouped.values():
        claim_overlap, query_overlap = paper_overlap_features(
            paper=entry["paper"],
            claim_tokens=claim_tokens,
            query_tokens=query_tokens,
            rules=rules,
            recommendation_module=recommendation_module,
        )
        entry["claim_overlap"] = claim_overlap
        entry["query_overlap"] = query_overlap

    return grouped


def candidate_sort_key(entry: dict) -> Tuple[int, int, int, int, int, int, int, int]:
    query_support_count = len({record["query_key"] for record in entry["supporting_records"]})
    recommendation_support_count = len(entry["recommended_by_seed_ids"])
    both_sources = int(query_support_count > 0 and recommendation_support_count > 0)
    return (
        both_sources,
        query_support_count,
        recommendation_support_count,
        entry["claim_overlap"],
        entry["query_overlap"],
        entry["paper"].get("influentialCitationCount") or 0,
        entry["paper"].get("citationCount") or 0,
        entry["paper"].get("year") or 0,
    )


def rank_candidates(groups: Dict[str, dict]) -> List[Tuple[str, dict]]:
    ranked = list(groups.items())
    ranked.sort(key=lambda item: candidate_sort_key(item[1]), reverse=True)
    return ranked


def candidate_reference_aliases(paper: dict, recommendation_module: Any) -> List[str]:
    aliases = [parse_seed_reference(recommendation_module.paper_key(paper), "candidate.paper_key")]

    paper_id = paper.get("paperId")
    if paper_id:
        aliases.append(f"paperid:{str(paper_id).strip().lower()}")

    doi = paper.get("doi")
    if doi:
        aliases.append(f"doi:{str(doi).strip().lower()}")

    title = (paper.get("title") or "").strip().lower()
    year = paper.get("year") or ""
    if title:
        aliases.append(f"title:{title}|year:{year}")

    deduped: List[str] = []
    seen = set()
    for alias in aliases:
        if alias in seen:
            continue
        seen.add(alias)
        deduped.append(alias)
    return deduped


def build_seed_candidate_lookup(
    ranked_query_candidates: List[Tuple[str, dict]],
    recommendation_module: Any,
) -> Dict[str, Tuple[str, dict]]:
    lookup: Dict[str, Tuple[str, dict]] = {}
    for paper_key, entry in ranked_query_candidates:
        for alias in candidate_reference_aliases(entry["paper"], recommendation_module):
            lookup.setdefault(alias, (paper_key, entry))
    return lookup


def match_seed_control_refs(
    refs: List[str],
    lookup: Dict[str, Tuple[str, dict]],
    *,
    require_paper_id: bool,
) -> Tuple[List[Tuple[str, str, dict]], List[str], List[str]]:
    matched_refs: List[Tuple[str, str, dict]] = []
    unresolved_refs: List[str] = []
    unseedable_refs: List[str] = []

    for ref in refs:
        match = lookup.get(ref)
        if match is None:
            unresolved_refs.append(ref)
            continue

        paper_key, entry = match
        if require_paper_id and not entry["paper"].get("paperId"):
            unseedable_refs.append(ref)
            continue

        matched_refs.append((ref, paper_key, entry))

    return matched_refs, unresolved_refs, unseedable_refs


def select_auto_seed_candidates(
    ranked_query_candidates: List[Tuple[str, dict]],
    config: CorrectionConfig,
    excluded_paper_keys: set[str],
    remaining_slots: int,
) -> List[Tuple[str, dict]]:
    seeds: List[Tuple[str, dict]] = []
    if remaining_slots <= 0:
        return seeds

    for paper_key, entry in ranked_query_candidates:
        if paper_key in excluded_paper_keys:
            continue
        total_overlap = entry["claim_overlap"] + entry["query_overlap"]
        if total_overlap < config.seed.min_total_overlap:
            continue
        if not entry["paper"].get("paperId"):
            continue
        seeds.append((paper_key, entry))
        if len(seeds) >= remaining_slots:
            break
    return seeds


def select_seed_candidates(
    claim_id: str,
    ranked_query_candidates: List[Tuple[str, dict]],
    config: CorrectionConfig,
    recommendation_module: Any,
) -> Tuple[List[Tuple[str, dict]], List[Tuple[str, dict]], dict]:
    control = config.seed.claim_overrides.get(
        claim_id,
        ClaimSeedControl(positive=[], negative=[], blocked=[]),
    )
    candidate_lookup = build_seed_candidate_lookup(ranked_query_candidates, recommendation_module)

    blocked_matches, unresolved_blocked_refs, _ = match_seed_control_refs(
        control.blocked,
        candidate_lookup,
        require_paper_id=False,
    )
    matched_blocked_refs = [ref for ref, _, _ in blocked_matches]
    blocked_keys = {paper_key for _, paper_key, _ in blocked_matches}

    manual_positive_matches, unresolved_positive_refs, unseedable_positive_refs = (
        match_seed_control_refs(
            control.positive,
            candidate_lookup,
            require_paper_id=True,
        )
    )
    manual_negative_matches, unresolved_negative_refs, unseedable_negative_refs = (
        match_seed_control_refs(
            control.negative,
            candidate_lookup,
            require_paper_id=True,
        )
    )

    warnings: List[str] = []

    if control.positive and config.seed.selection_mode == "auto":
        warnings.append("manual positive seed refs were configured but ignored because selection_mode=auto")

    if unseedable_positive_refs:
        warnings.append(
            "some configured positive seed refs matched candidate papers without paperId and were ignored"
        )
    if unseedable_negative_refs:
        warnings.append(
            "some configured negative seed refs matched candidate papers without paperId and were ignored"
        )

    filtered_manual_positive: List[Tuple[str, dict]] = []
    filtered_positive_refs: List[str] = []
    positive_keys = set()
    for ref, paper_key, entry in manual_positive_matches:
        if paper_key in blocked_keys:
            warnings.append("blocked seed refs take precedence over positive seed refs")
            continue
        if paper_key in positive_keys:
            continue
        positive_keys.add(paper_key)
        filtered_positive_refs.append(ref)
        filtered_manual_positive.append((paper_key, entry))

    filtered_manual_negative: List[Tuple[str, dict]] = []
    filtered_negative_refs: List[str] = []
    negative_keys = set()
    for ref, paper_key, entry in manual_negative_matches:
        if paper_key in blocked_keys:
            warnings.append("blocked seed refs take precedence over negative seed refs")
            continue
        if paper_key in positive_keys:
            warnings.append("positive seed refs take precedence over negative seed refs")
            continue
        if paper_key in negative_keys:
            continue
        negative_keys.add(paper_key)
        filtered_negative_refs.append(ref)
        filtered_manual_negative.append((paper_key, entry))

    selected_positive: List[Tuple[str, dict]] = []
    if config.seed.selection_mode == "manual":
        if len(filtered_manual_positive) > config.seed.max_seeds_per_claim:
            warnings.append("manual positive seeds were truncated to max_seeds_per_claim")
        selected_positive = filtered_manual_positive[: config.seed.max_seeds_per_claim]
    elif config.seed.selection_mode == "hybrid":
        if len(filtered_manual_positive) > config.seed.max_seeds_per_claim:
            warnings.append("manual positive seeds were truncated to max_seeds_per_claim before hybrid auto-fill")
        selected_positive.extend(filtered_manual_positive[: config.seed.max_seeds_per_claim])
        auto_excluded_keys = blocked_keys | negative_keys | {paper_key for paper_key, _ in selected_positive}
        auto_candidates = select_auto_seed_candidates(
            ranked_query_candidates=ranked_query_candidates,
            config=config,
            excluded_paper_keys=auto_excluded_keys,
            remaining_slots=max(config.seed.max_seeds_per_claim - len(selected_positive), 0),
        )
        selected_positive.extend(auto_candidates)
    else:
        auto_excluded_keys = blocked_keys | negative_keys
        selected_positive = select_auto_seed_candidates(
            ranked_query_candidates=ranked_query_candidates,
            config=config,
            excluded_paper_keys=auto_excluded_keys,
            remaining_slots=config.seed.max_seeds_per_claim,
        )

    selected_positive_keys = {paper_key for paper_key, _ in selected_positive}
    effective_negative = [
        (paper_key, entry)
        for paper_key, entry in filtered_manual_negative
        if paper_key not in selected_positive_keys
    ]
    if len(effective_negative) < len(filtered_manual_negative):
        warnings.append("selected positive seeds are never also used as negative seeds")

    control_report = {
        "selection_mode": config.seed.selection_mode,
        "configured_positive_refs": list(control.positive),
        "configured_negative_refs": list(control.negative),
        "configured_blocked_refs": list(control.blocked),
        "matched_positive_refs": filtered_positive_refs,
        "matched_negative_refs": filtered_negative_refs,
        "matched_blocked_refs": matched_blocked_refs,
        "unresolved_positive_refs": unresolved_positive_refs,
        "unresolved_negative_refs": unresolved_negative_refs,
        "unresolved_blocked_refs": unresolved_blocked_refs,
        "unseedable_positive_refs": unseedable_positive_refs,
        "unseedable_negative_refs": unseedable_negative_refs,
        "warnings": sorted(set(warnings)),
    }
    return selected_positive, effective_negative, control_report


def compute_trigger_reasons(
    recommendation_item: dict,
    query_reviews: List[dict],
    config: CorrectionConfig,
) -> List[str]:
    reasons: List[str] = []

    selected_papers = recommendation_item["selected_papers"]
    usable_records = recommendation_item["usable_records"]
    statuses = [item["status"] for item in query_reviews]

    if recommendation_item["status"] == "weak":
        reasons.append("claim_status_weak")
    elif config.trigger.include_review_status and recommendation_item["status"] == "review":
        reasons.append("claim_status_review")

    if config.trigger.include_claim_notes and recommendation_item.get("note"):
        reasons.append("claim_note_present")

    if not usable_records:
        reasons.append("no_usable_queries")

    if statuses and all(status in {"rewrite", "exclude"} for status in statuses):
        reasons.append("all_queries_unusable")

    if len(selected_papers) < config.trigger.min_selected_papers:
        reasons.append("too_few_selected_papers")

    max_query_support = max(
        (
            len({record["query_key"] for record in group["records"]})
            for group in selected_papers
        ),
        default=0,
    )
    if usable_records and max_query_support < config.trigger.min_cross_query_support:
        reasons.append("low_cross_query_support")

    max_citations = max(
        (group["paper"].get("citationCount") or 0 for group in selected_papers),
        default=0,
    )
    if (
        0 < len(selected_papers) <= config.trigger.max_low_signal_candidates
        and max_citations <= config.trigger.low_citation_threshold
    ):
        reasons.append("low_signal_candidates")

    deduped: List[str] = []
    seen = set()
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            deduped.append(reason)
    return deduped


def fetch_recommendation_groups(
    claim: Any,
    claim_records: List[dict],
    seed_candidates: List[Tuple[str, dict]],
    negative_seed_candidates: List[Tuple[str, dict]],
    config: CorrectionConfig,
    rules: Any,
    recommendation_module: Any,
) -> Tuple[Dict[str, dict], List[dict]]:
    claim_tokens, query_tokens = build_claim_context_tokens(
        claim=claim,
        claim_records=claim_records,
        rules=rules,
        recommendation_module=recommendation_module,
    )

    grouped: Dict[str, dict] = {}
    failures: List[dict] = []
    client = SemanticScholarClient()

    try:
        if config.recommendations.method == "positive_seed_list":
            positive_seed_ids = [
                seed_entry["paper"]["paperId"]
                for _, seed_entry in seed_candidates
                if seed_entry["paper"].get("paperId")
            ]
            negative_seed_ids = [
                seed_entry["paper"]["paperId"]
                for _, seed_entry in negative_seed_candidates
                if seed_entry["paper"].get("paperId")
            ]
            positive_seed_titles = [
                seed_entry["paper"].get("title") or seed_entry["paper"]["paperId"]
                for _, seed_entry in seed_candidates
                if seed_entry["paper"].get("paperId")
            ]
            request_limit = max(1, config.recommendations.per_seed_limit * max(len(seed_candidates), 1))
            source_id = "positive_seed_list:" + "+".join(sorted(positive_seed_ids))
            source_title = "positive_seed_list[" + "; ".join(positive_seed_titles) + "]"

            try:
                recommended_papers = client.get_recommendations_from_lists(
                    positive_paper_ids=positive_seed_ids,
                    negative_paper_ids=negative_seed_ids or None,
                    limit=request_limit,
                    fields=config.recommendations.fields,
                )
            except Exception as exc:
                failures.append(
                    {
                        "seed_paper_id": source_id,
                        "seed_title": source_title,
                        "error_type": exc.__class__.__name__,
                        "error": str(exc),
                    }
                )
            else:
                seed_keys = {seed_key for seed_key, _ in seed_candidates}
                for raw_paper in recommended_papers:
                    paper = normalize_recommended_paper(raw_paper)
                    exclusion_reason = recommendation_module.paper_exclusion_reason(paper, rules)
                    if exclusion_reason:
                        continue

                    paper_key = recommendation_module.paper_key(paper)
                    if paper_key in seed_keys:
                        continue

                    entry = grouped.setdefault(
                        paper_key,
                        {
                            "paper": paper,
                            "supporting_records": [],
                            "recommended_by_seed_ids": set(),
                            "recommended_by_seed_titles": set(),
                            "claim_overlap": 0,
                            "query_overlap": 0,
                        },
                    )
                    if paper_strength(paper) > paper_strength(entry["paper"]):
                        entry["paper"] = paper
                    entry["recommended_by_seed_ids"].add(source_id)
                    entry["recommended_by_seed_titles"].add(source_title)
        else:
            for index, (seed_key, seed_entry) in enumerate(seed_candidates, start=1):
                seed_paper = seed_entry["paper"]
                try:
                    recommended_papers = client.get_recommendations(
                        seed_paper["paperId"],
                        limit=config.recommendations.per_seed_limit,
                        fields=config.recommendations.fields,
                    )
                except Exception as exc:
                    failures.append(
                        {
                            "seed_paper_id": seed_paper.get("paperId"),
                            "seed_title": seed_paper.get("title"),
                            "error_type": exc.__class__.__name__,
                            "error": str(exc),
                        }
                    )
                    continue

                for raw_paper in recommended_papers:
                    paper = normalize_recommended_paper(raw_paper)
                    exclusion_reason = recommendation_module.paper_exclusion_reason(paper, rules)
                    if exclusion_reason:
                        continue

                    paper_key = recommendation_module.paper_key(paper)
                    if paper_key == seed_key:
                        continue

                    entry = grouped.setdefault(
                        paper_key,
                        {
                            "paper": paper,
                            "supporting_records": [],
                            "recommended_by_seed_ids": set(),
                            "recommended_by_seed_titles": set(),
                            "claim_overlap": 0,
                            "query_overlap": 0,
                        },
                    )
                    if paper_strength(paper) > paper_strength(entry["paper"]):
                        entry["paper"] = paper
                    entry["recommended_by_seed_ids"].add(seed_paper["paperId"])
                    entry["recommended_by_seed_titles"].add(seed_paper.get("title") or seed_paper["paperId"])

                if index < len(seed_candidates) and config.recommendations.pause_seconds > 0:
                    time.sleep(config.recommendations.pause_seconds)
    finally:
        client.close()

    for entry in grouped.values():
        claim_overlap, query_overlap = paper_overlap_features(
            paper=entry["paper"],
            claim_tokens=claim_tokens,
            query_tokens=query_tokens,
            rules=rules,
            recommendation_module=recommendation_module,
        )
        entry["claim_overlap"] = claim_overlap
        entry["query_overlap"] = query_overlap

    return grouped, failures


def merge_candidate_groups(
    query_groups: Dict[str, dict],
    recommendation_groups: Dict[str, dict],
) -> Dict[str, dict]:
    merged: Dict[str, dict] = {}

    for paper_key, entry in query_groups.items():
        merged[paper_key] = {
            "paper": entry["paper"],
            "supporting_records": list(entry["supporting_records"]),
            "recommended_by_seed_ids": set(entry["recommended_by_seed_ids"]),
            "recommended_by_seed_titles": set(entry["recommended_by_seed_titles"]),
            "claim_overlap": entry["claim_overlap"],
            "query_overlap": entry["query_overlap"],
        }

    for paper_key, entry in recommendation_groups.items():
        existing = merged.get(paper_key)
        if existing is None:
            merged[paper_key] = {
                "paper": entry["paper"],
                "supporting_records": list(entry["supporting_records"]),
                "recommended_by_seed_ids": set(entry["recommended_by_seed_ids"]),
                "recommended_by_seed_titles": set(entry["recommended_by_seed_titles"]),
                "claim_overlap": entry["claim_overlap"],
                "query_overlap": entry["query_overlap"],
            }
            continue

        if paper_strength(entry["paper"]) > paper_strength(existing["paper"]):
            existing["paper"] = entry["paper"]
        existing["recommended_by_seed_ids"].update(entry["recommended_by_seed_ids"])
        existing["recommended_by_seed_titles"].update(entry["recommended_by_seed_titles"])
        existing["claim_overlap"] = max(existing["claim_overlap"], entry["claim_overlap"])
        existing["query_overlap"] = max(existing["query_overlap"], entry["query_overlap"])

    return merged


def candidate_origin(entry: dict) -> str:
    query_support_count = len({record["query_key"] for record in entry["supporting_records"]})
    recommendation_support_count = len(entry["recommended_by_seed_ids"])
    if query_support_count > 0 and recommendation_support_count > 0:
        return "query+recommendation"
    if query_support_count > 0:
        return "query"
    return "recommendation"


def determine_correction_status(
    seed_candidates: List[Tuple[str, dict]],
    merged_candidates: List[Tuple[str, dict]],
    recommendation_groups: Dict[str, dict],
    failures: List[dict],
    config: CorrectionConfig,
) -> str:
    if not seed_candidates:
        return "rewrite_needed"
    if config.dry_run:
        return "pending_api"
    if not recommendation_groups and failures:
        return "blocked"

    high_fit = [
        item
        for item in merged_candidates[: config.recommendations.top_candidates_per_claim]
        if item[1]["claim_overlap"] + item[1]["query_overlap"]
        >= config.recommendations.ready_min_total_overlap
    ]
    if len(high_fit) >= config.recommendations.ready_candidate_count:
        return "corrected_ready"
    if recommendation_groups:
        return "corrected_review"
    return "blocked"


def serialize_candidate(paper_key: str, entry: dict, rank: int) -> dict:
    paper = entry["paper"]
    supporting_query_keys = sorted({record["query_key"] for record in entry["supporting_records"]})
    return {
        "rank": rank,
        "paper_key": paper_key,
        "paperId": paper.get("paperId"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "authors": paper.get("authors") or [],
        "venue": paper.get("venue"),
        "url": paper.get("url"),
        "doi": paper.get("doi"),
        "citationCount": paper.get("citationCount"),
        "influentialCitationCount": paper.get("influentialCitationCount"),
        "isOpenAccess": paper.get("isOpenAccess"),
        "openAccessPdf": paper.get("openAccessPdf"),
        "origin": candidate_origin(entry),
        "query_support_count": len(supporting_query_keys),
        "supporting_query_keys": supporting_query_keys,
        "recommendation_support_count": len(entry["recommended_by_seed_ids"]),
        "recommended_by_seed_ids": sorted(entry["recommended_by_seed_ids"]),
        "recommended_by_seed_titles": sorted(entry["recommended_by_seed_titles"]),
        "claim_overlap": entry["claim_overlap"],
        "query_overlap": entry["query_overlap"],
    }


def serialize_seed(paper_key: str, entry: dict, rank: int) -> dict:
    paper = entry["paper"]
    supporting_query_keys = sorted({record["query_key"] for record in entry["supporting_records"]})
    return {
        "rank": rank,
        "paper_key": paper_key,
        "paperId": paper.get("paperId"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount"),
        "influentialCitationCount": paper.get("influentialCitationCount"),
        "query_support_count": len(supporting_query_keys),
        "supporting_query_keys": supporting_query_keys,
        "claim_overlap": entry["claim_overlap"],
        "query_overlap": entry["query_overlap"],
    }


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_report(path: Path, records: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    status_counts: Dict[str, int] = defaultdict(int)
    for record in records:
        status_counts[record["status"]] += 1

    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Recommendation Auto-Correction Report\n\n")
        handle.write("## Summary\n\n")
        handle.write(f"- Triggered claims: {len(records)}\n")
        for status in sorted(status_counts):
            handle.write(f"- `{status}`: {status_counts[status]}\n")
        handle.write("\n")

        for record in records:
            handle.write(f"## {record['claim_id']}\n")
            handle.write(f"- Status: {record['status']}\n")
            handle.write(f"- Current recommendation status: {record['current_status']}\n")
            handle.write(f"- Recommendation method: {record['recommendation_method']}\n")
            handle.write(f"- Seed selection mode: {record['seed_selection_mode']}\n")
            handle.write(f"- Claim: {record['claim_text']}\n")
            handle.write(f"- Trigger reasons: {', '.join(record['trigger_reasons'])}\n")
            if record.get("claim_note"):
                handle.write(f"- Existing note: {record['claim_note']}\n")

            query_summaries = [
                f"{item['query_key']} [{item['status']}, papers={item['paper_count']}]"
                for item in record["query_reviews"]
            ]
            handle.write(
                f"- Query review: {', '.join(query_summaries) if query_summaries else 'none'}\n"
            )

            seed_control = record.get("seed_control") or {}
            seed_warnings = seed_control.get("warnings") or []
            if seed_warnings:
                handle.write(f"- Seed control warnings: {'; '.join(seed_warnings)}\n")

            unresolved_refs = []
            for field_name in (
                "unresolved_positive_refs",
                "unresolved_negative_refs",
                "unresolved_blocked_refs",
                "unseedable_positive_refs",
                "unseedable_negative_refs",
            ):
                unresolved_refs.extend(seed_control.get(field_name) or [])
            if unresolved_refs:
                handle.write(f"- Unresolved or unusable seed refs: {', '.join(unresolved_refs)}\n")

            if not record["seeds"]:
                handle.write("- Seed papers: none; query rewrite is recommended.\n\n")
                continue

            handle.write("- Seed papers:\n")
            for seed in record["seeds"]:
                handle.write(
                    "  "
                    f"{seed['rank']}. {seed['title']} "
                    f"({seed['year'] or 'n/a'}; cites={seed['citationCount'] or 0}; "
                    f"support={', '.join(seed['supporting_query_keys'])}; "
                    f"overlap={seed['claim_overlap'] + seed['query_overlap']})\n"
                )

            if record.get("negative_seeds"):
                handle.write("- Negative seed papers:\n")
                for seed in record["negative_seeds"]:
                    handle.write(
                        "  "
                        f"{seed['rank']}. {seed['title']} "
                        f"({seed['year'] or 'n/a'}; cites={seed['citationCount'] or 0}; "
                        f"support={', '.join(seed['supporting_query_keys'])}; "
                        f"overlap={seed['claim_overlap'] + seed['query_overlap']})\n"
                    )

            if record["recommendation_failures"]:
                handle.write("- Recommendation failures:\n")
                for failure in record["recommendation_failures"]:
                    handle.write(
                        "  "
                        f"- {failure['seed_title'] or failure['seed_paper_id']}: "
                        f"{failure['error_type']} - {failure['error']}\n"
                    )

            handle.write("- Top corrected candidates:\n")
            for candidate in record["candidates"]:
                handle.write(
                    "  "
                    f"{candidate['rank']}. {candidate['title']} "
                    f"({candidate['year'] or 'n/a'}; origin={candidate['origin']}; "
                    f"q_support={candidate['query_support_count']}; "
                    f"rec_support={candidate['recommendation_support_count']}; "
                    f"cites={candidate['citationCount'] or 0}; "
                    f"overlap={candidate['claim_overlap'] + candidate['query_overlap']})\n"
                )
            handle.write("\n")


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Failed to load config: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        config = CorrectionConfig(
            claim_units=config.claim_units,
            deduped_results=config.deduped_results,
            recommendation_rules=config.recommendation_rules,
            output_jsonl=config.output_jsonl,
            output_report=config.output_report,
            claim_ids=config.claim_ids,
            dry_run=True,
            trigger=config.trigger,
            seed=config.seed,
            recommendations=config.recommendations,
        )

    if args.claim_ids:
        config = CorrectionConfig(
            claim_units=config.claim_units,
            deduped_results=config.deduped_results,
            recommendation_rules=config.recommendation_rules,
            output_jsonl=config.output_jsonl,
            output_report=config.output_report,
            claim_ids=args.claim_ids,
            dry_run=config.dry_run,
            trigger=config.trigger,
            seed=config.seed,
            recommendations=config.recommendations,
        )

    recommendation_module = load_script_module(
        REPO_ROOT / "scripts" / "generate_claim_recommendation_list.py",
        "autocorrect_generate_claim_recommendation_list",
    )
    prescreen_module = load_script_module(
        REPO_ROOT / "scripts" / "dedupe_and_prescreen_semantic_scholar.py",
        "autocorrect_dedupe_and_prescreen_semantic_scholar",
    )

    try:
        claims = recommendation_module.load_claim_units(config.claim_units)
        records = recommendation_module.load_records(config.deduped_results)
        rules = recommendation_module.load_rules(config.recommendation_rules)
    except Exception as exc:
        print(f"Failed to load inputs: {exc}", file=sys.stderr)
        return 1

    if config.claim_ids:
        claim_filter = {claim_id.strip() for claim_id in config.claim_ids}
        claims = {claim_id: claim for claim_id, claim in claims.items() if claim_id in claim_filter}

    if not claims:
        print("No matching claims found after applying filters.", file=sys.stderr)
        return 1

    by_claim: Dict[str, List[dict]] = defaultdict(list)
    for record in records:
        if record["claim_id"] in claims:
            by_claim[record["claim_id"]].append(record)

    current_recommendations = recommendation_module.build_recommendations(claims, records, rules)

    triggered_records: List[dict] = []
    for index, claim_id in enumerate(sorted(claims.keys()), start=1):
        claim = claims[claim_id]
        claim_records = by_claim.get(claim_id, [])
        recommendation_item = current_recommendations[claim_id]
        query_reviews = [
            effective_query_review(record, rules, prescreen_module)
            for record in sorted(claim_records, key=lambda item: item["query_key"])
        ]
        trigger_reasons = compute_trigger_reasons(recommendation_item, query_reviews, config)
        if not trigger_reasons:
            continue

        print(f"[{index}/{len(claims)}] {claim_id}: {', '.join(trigger_reasons)}")

        query_groups = build_query_candidate_groups(
            claim=claim,
            claim_records=claim_records,
            rules=rules,
            recommendation_module=recommendation_module,
        )
        ranked_query_candidates = rank_candidates(query_groups)
        seed_candidates, negative_seed_candidates, seed_control = select_seed_candidates(
            claim_id=claim_id,
            ranked_query_candidates=ranked_query_candidates,
            config=config,
            recommendation_module=recommendation_module,
        )

        if negative_seed_candidates and config.recommendations.method != "positive_seed_list":
            seed_control["warnings"].append(
                "negative seeds require recommendations.method=positive_seed_list and were ignored"
            )
            negative_seed_candidates = []

        recommendation_groups: Dict[str, dict] = {}
        recommendation_failures: List[dict] = []
        if not config.dry_run and seed_candidates:
            recommendation_groups, recommendation_failures = fetch_recommendation_groups(
                claim=claim,
                claim_records=claim_records,
                seed_candidates=seed_candidates,
                negative_seed_candidates=negative_seed_candidates,
                config=config,
                rules=rules,
                recommendation_module=recommendation_module,
            )

        merged_groups = merge_candidate_groups(query_groups, recommendation_groups)
        ranked_merged_candidates = rank_candidates(merged_groups)
        top_candidates = [
            serialize_candidate(paper_key, entry, rank)
            for rank, (paper_key, entry) in enumerate(
                ranked_merged_candidates[: config.recommendations.top_candidates_per_claim],
                start=1,
            )
        ]
        serialized_seeds = [
            serialize_seed(paper_key, entry, rank)
            for rank, (paper_key, entry) in enumerate(seed_candidates, start=1)
        ]
        serialized_negative_seeds = [
            serialize_seed(paper_key, entry, rank)
            for rank, (paper_key, entry) in enumerate(negative_seed_candidates, start=1)
        ]
        status = determine_correction_status(
            seed_candidates=seed_candidates,
            merged_candidates=ranked_merged_candidates,
            recommendation_groups=recommendation_groups,
            failures=recommendation_failures,
            config=config,
        )

        payload = {
            "claim_id": claim_id,
            "claim_text": claim.claim_text,
            "section": claim.section,
            "source_lines": claim.source_lines,
            "claim_type": claim.claim_type,
            "priority": claim.priority,
            "current_status": recommendation_item["status"],
            "claim_note": recommendation_item.get("note"),
            "status": status,
            "trigger_reasons": trigger_reasons,
            "seed_selection_mode": seed_control["selection_mode"],
            "seed_control": seed_control,
            "recommendation_method": config.recommendations.method,
            "query_reviews": query_reviews,
            "seed_count": len(serialized_seeds),
            "seeds": serialized_seeds,
            "negative_seed_count": len(serialized_negative_seeds),
            "negative_seeds": serialized_negative_seeds,
            "recommendation_failures": recommendation_failures,
            "recommendation_candidate_count": len(recommendation_groups),
            "merged_candidate_count": len(merged_groups),
            "candidates": top_candidates,
            "generated_at": utc_now(),
        }
        triggered_records.append(payload)

    if not triggered_records:
        print("No claims triggered the auto-correction rules.")
        return 0

    if config.dry_run:
        print(f"Dry run complete. Triggered claims: {len(triggered_records)}")
        for record in triggered_records:
            print(
                f"{record['claim_id']}: status={record['status']} "
                f"seeds={record['seed_count']} negatives={record['negative_seed_count']} "
                f"triggers={','.join(record['trigger_reasons'])}"
            )
        return 0

    if config.output_jsonl.exists():
        config.output_jsonl.unlink()
    for record in triggered_records:
        append_jsonl(config.output_jsonl, record)
    write_report(config.output_report, triggered_records)

    print(f"Wrote: {config.output_jsonl}")
    print(f"Wrote: {config.output_report}")
    print(f"Triggered claims: {len(triggered_records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
