"""Triggered-push CLI: autoscholar trigger ...

Wire into the main CLI with:
    from autoscholar.triggered_push.cli import trigger_app
    app.add_typer(trigger_app, name="trigger")
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import typer

from autoscholar.citation.common import DEFAULT_STOPWORDS, tokenize, utc_now
from autoscholar.integrations import SemanticScholarClient
from autoscholar.io import read_yaml, write_yaml
from autoscholar.semantic_crawl import (
    SemanticCrawlConfig,
    SemanticQuery,
    crawl_semantic_queries,
)

from autoscholar.triggered_push import render as render_module

trigger_app = typer.Typer(help="Triggered-push: surface DNA-resonant materials.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POSITIVE_REACTIONS = {
    "want_to_argue",  # controversy
    "changed",        # failure-archive
    "curious",        # matrix
    "partial",        # cross-domain
    "deep",           # cross-domain
}

BORING_REACTIONS = {
    "bored",           # controversy
    "still_holds",     # failure-archive
    "irrelevant",      # matrix
    "not_isomorphic",  # cross-domain
}

AMBIGUOUS_REACTIONS = {
    "spectate",  # controversy
    "unsure",    # failure-archive
    "shallow",   # cross-domain
}

VALID_REACTIONS_PER_PARADIGM: dict[str, set[str]] = {
    "controversy":     {"bored", "spectate", "want_to_argue"},
    "failure-archive": {"still_holds", "changed", "unsure"},
    "matrix":          {"obvious_void", "curious", "irrelevant"},
    "cross-domain":    {"not_isomorphic", "shallow", "partial", "deep"},
}

PARADIGM_CHOICES = list(VALID_REACTIONS_PER_PARADIGM.keys())

_CHALLENGE_PHRASES = frozenset({
    "challenge", "contradict", "fails to", "revisit", "reconsider",
    "comment on", "reply to", "rebuttal", "overclaim", "does not",
    "no evidence", "contrary", "inconsistent", "refute",
})

# ---------------------------------------------------------------------------
# IO helpers (thin wrappers; heavier ops use project-wide helpers above)
# ---------------------------------------------------------------------------


def _short_hash(text: str, n: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _load_manifest(workspace: Path) -> dict:
    manifest_path = workspace / "triggered-push.yaml"
    if not manifest_path.exists():
        raise typer.BadParameter(f"Not a triggered-push workspace: {workspace}")
    return read_yaml(manifest_path)


def _artifact_path(workspace: Path, manifest: dict, key: str) -> Path:
    return (workspace / manifest["artifacts"][key]).resolve()

# ---------------------------------------------------------------------------
# Seed paper parsing
# ---------------------------------------------------------------------------


_PAPER_BLOCK_RE = re.compile(r"##\s+Paper\s+\d+\s*\n(?P<body>.+?)(?=\n##\s+Paper|\Z)", re.S)
_FIELD_RE = re.compile(r"^-\s*(?P<key>title|paper_id|year|user_note)\s*:\s*(?P<value>.+?)\s*$", re.M)


def _parse_seed_papers(text: str) -> list[dict[str, str]]:
    papers: list[dict[str, str]] = []
    for match in _PAPER_BLOCK_RE.finditer(text):
        body = match.group("body")
        fields = {m.group("key"): m.group("value") for m in _FIELD_RE.finditer(body)}
        if "title" in fields and "user_note" in fields:
            papers.append(fields)
    return papers

# ---------------------------------------------------------------------------
# DNA profile (rolling window, pure-statistics)
# ---------------------------------------------------------------------------


def _select_window(
    reactions: list[dict],
    *,
    max_count: int,
    max_age_days: int,
    now: datetime,
) -> list[dict]:
    by_recency = sorted(reactions, key=lambda r: r["captured_at"], reverse=True)
    count_ids = {r["reaction_id"] for r in by_recency[:max_count]}
    cutoff = now - timedelta(days=max_age_days)
    age_ids = {
        r["reaction_id"] for r in by_recency
        if datetime.fromisoformat(r["captured_at"]) >= cutoff
    }
    keep = count_ids & age_ids
    return [r for r in by_recency[:max_count] if r["reaction_id"] in keep]


def _derive_traits(window: list[dict]) -> dict[str, Any]:
    engaging_pool = [r for r in window if r["reaction"] in POSITIVE_REACTIONS]
    boring_pool   = [r for r in window if r["reaction"] in BORING_REACTIONS]
    ambiguous_pool = [r for r in window if r["reaction"] in AMBIGUOUS_REACTIONS]

    def _kw_freq(pool: list[dict], weight: float = 1.0) -> Counter:
        counter: Counter = Counter()
        for r in pool:
            text = (r.get("card_summary") or "") + " " + (r.get("user_take") or "")
            for token in tokenize(text, DEFAULT_STOPWORDS):
                counter[token] += weight
        return counter

    engaging_kw = _kw_freq(engaging_pool, 1.0) + _kw_freq(ambiguous_pool, 0.5)
    boring_kw = _kw_freq(boring_pool, 1.0)

    engaging_axes: Counter = Counter(
        r.get("card_diversity_axis") for r in engaging_pool if r.get("card_diversity_axis")
    )
    boring_axes: Counter = Counter(
        r.get("card_diversity_axis") for r in boring_pool if r.get("card_diversity_axis")
    )

    paradigm_totals: Counter = Counter(r["paradigm"] for r in window)
    paradigm_positives: Counter = Counter(
        r["paradigm"] for r in window if r["reaction"] in POSITIVE_REACTIONS
    )
    preferred_paradigm = None
    if sum(paradigm_totals.values()) >= 5:
        ratios = {
            p: paradigm_positives[p] / paradigm_totals[p]
            for p in paradigm_totals if paradigm_totals[p] > 0
        }
        if ratios:
            preferred_paradigm = max(ratios, key=lambda k: ratios[k])

    return {
        "engaging_keywords": engaging_kw.most_common(10),
        "boring_keywords": boring_kw.most_common(10),
        "engaging_axes": engaging_axes.most_common(),
        "boring_axes": boring_axes.most_common(),
        "preferred_paradigm": preferred_paradigm,
        "computed_at": utc_now(),
    }


def _refresh_profile(workspace: Path, manifest: dict) -> dict:
    profile_path = _artifact_path(workspace, manifest, "dna_profile")
    reactions_path = _artifact_path(workspace, manifest, "reactions")
    profile = _read_json(profile_path) or {
        "schema_version": "1",
        "rolling": manifest.get("defaults", {}).get("rolling_window", {
            "max_count": 30, "max_age_days": 90,
        }),
        "rolling_policy": "intersection",
        "seed_papers": [],
        "recent_reactions": [],
        "derived_traits": {},
    }
    rolling = profile.get("rolling", {"max_count": 30, "max_age_days": 90})
    all_reactions = _read_jsonl(reactions_path)
    window = _select_window(
        all_reactions,
        max_count=int(rolling.get("max_count", 30)),
        max_age_days=int(rolling.get("max_age_days", 90)),
        now=datetime.now(timezone.utc),
    )
    profile["recent_reactions"] = window
    profile["derived_traits"] = _derive_traits(window)
    profile["updated_at"] = utc_now()
    _write_json(profile_path, profile)
    return profile

# ---------------------------------------------------------------------------
# Shared retrieval helpers
# ---------------------------------------------------------------------------


def _collect_papers_from_crawl(results_path: Path) -> dict[str, dict]:
    """Deduplicated papers keyed by paperId from a crawl results file."""
    records = _read_jsonl(results_path)
    papers: dict[str, dict] = {}
    for record in records:
        for paper in record.get("papers") or []:
            pid = paper.get("paperId")
            if pid and pid not in papers:
                papers[pid] = paper
    return papers


def _crawl_defaults(manifest: dict) -> dict:
    return manifest.get("defaults", {}).get("crawl", {
        "pause_seconds": 1.0,
        "max_retries": 3,
    })


def _synthesis_bundle_path(workspace: Path, tag: str, run_id: str) -> Path:
    return workspace / "artifacts" / f"synthesis_input_{tag}_{run_id}.json"


def _print_synthesis_needed(bundle_path: Path, cards_path: Path, instruction: str) -> None:
    sep = "=" * 60
    typer.echo(f"\n{sep}")
    typer.echo("RETRIEVAL COMPLETE — AI SYNTHESIS NEEDED")
    typer.echo(sep)
    typer.echo(f"Synthesis bundle : {bundle_path}")
    typer.echo(f"Write cards to   : {cards_path}")
    typer.echo(f"\n{instruction}")
    typer.echo("\nAfter writing cards, rerun the push command to render the report.")

# ---------------------------------------------------------------------------
# Density labeling (pure-statistics, shared with matrix)
# ---------------------------------------------------------------------------


def label_density(paper_count: int, max_citations: int) -> str:
    if paper_count == 0:
        return "empty"
    if paper_count >= 8 and max_citations >= 50:
        return "dense"
    if paper_count <= 3 or max_citations < 10:
        return "sparse"
    return "dense"

# ---------------------------------------------------------------------------
# Commands: init
# ---------------------------------------------------------------------------


_SEED_PAPERS_TEMPLATE = """\
# Seed Papers

Paste 3-5 papers that represent your research DNA. For each, write
ONE LINE about what you reacted to in the paper.

## Paper 1
- title: <title>
- paper_id: <optional, semantic scholar paper id>
- year: <optional>
- user_note: <one line, what you reacted to>

## Paper 2
- title:
- user_note:
"""


@trigger_app.command("init")
def trigger_init(
    target_dir: Path = typer.Argument(..., help="Workspace directory to create."),
    domain: str = typer.Option(..., "--domain", help="Research domain string."),
    home_field: str | None = typer.Option(None, "--home-field", help="Semantic Scholar fieldOfStudy."),
) -> None:
    if target_dir.exists() and any(target_dir.iterdir()):
        raise typer.BadParameter(f"Directory not empty: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "inputs").mkdir(exist_ok=True)
    (target_dir / "artifacts").mkdir(exist_ok=True)
    (target_dir / "reports").mkdir(exist_ok=True)

    manifest: dict = {
        "schema_version": "1",
        "domain": domain,
        "created_at": utc_now(),
        "defaults": {
            "rolling_window": {"max_count": 30, "max_age_days": 90},
            "matrix": {"max_queries_per_run": 32},
            "crawl": {"pause_seconds": 1.0, "max_retries": 3, "until_complete": True},
        },
        "artifacts": {
            "dna_profile":       "artifacts/dna_profile.json",
            "reactions":         "artifacts/reactions.jsonl",
            "semantic_results":  "artifacts/semantic_results.jsonl",
            "semantic_failures": "artifacts/semantic_failures.jsonl",
            "controversy_cards": "artifacts/controversy_cards.jsonl",
            "failure_archive":   "artifacts/failure_archive.jsonl",
            "matrix":            "artifacts/matrix.json",
            "cross_domain_pairs":"artifacts/cross_domain_pairs.jsonl",
        },
        "reports_dir": "reports",
    }
    write_yaml(target_dir / "triggered-push.yaml", manifest)
    write_yaml(
        target_dir / "inputs" / "scope.yaml",
        {
            "schema_version": "1",
            "domain": domain,
            "home_field": home_field,
            "foreign_fields_allowed": [
                "Biology", "Physics", "Psychology", "Economics", "Linguistics",
            ],
            "home_vocabulary": [],
            "non_standard_scenarios_hint": [],
        },
    )
    (target_dir / "inputs" / "seed_papers.md").write_text(_SEED_PAPERS_TEMPLATE, encoding="utf-8")
    typer.echo(f"Initialized triggered-push workspace: {target_dir}")
    typer.echo("Next: edit inputs/seed_papers.md, then run `autoscholar trigger push`.")

# ---------------------------------------------------------------------------
# Commands: push (dispatcher)
# ---------------------------------------------------------------------------


@trigger_app.command("push")
def trigger_push(
    workspace_dir: Path = typer.Option(..., "--workspace"),
    paradigm: str = typer.Option(..., "--paradigm", help="|".join(PARADIGM_CHOICES)),
    run_id: str | None = typer.Option(None, "--run-id", help="Stable id for resumable runs."),
) -> None:
    if paradigm not in PARADIGM_CHOICES:
        raise typer.BadParameter(f"--paradigm must be one of {PARADIGM_CHOICES}")
    workspace = workspace_dir.resolve()
    manifest = _load_manifest(workspace)
    profile = _refresh_profile(workspace, manifest)

    seed_text = (workspace / "inputs" / "seed_papers.md").read_text(encoding="utf-8")
    seed_papers = _parse_seed_papers(seed_text)
    if len(seed_papers) < 3:
        raise typer.BadParameter("Need 3+ seed papers in inputs/seed_papers.md before push.")

    profile["seed_papers"] = [
        {
            "paper_id": sp.get("paper_id"),
            "title": sp["title"],
            "user_note": sp["user_note"],
            "added_at": profile.get("updated_at") or utc_now(),
        }
        for sp in seed_papers
    ]
    _write_json(_artifact_path(workspace, manifest, "dna_profile"), profile)

    resolved_run_id = run_id or _short_hash(f"{paradigm}-{utc_now()}")
    dispatch = {
        "controversy":     _run_controversy,
        "failure-archive": _run_failure_archive,
        "matrix":          _run_matrix,
        "cross-domain":    _run_cross_domain,
    }
    dispatch[paradigm](workspace, manifest, profile, resolved_run_id)

# ---------------------------------------------------------------------------
# Paradigm runners
# ---------------------------------------------------------------------------


def _run_controversy(workspace: Path, manifest: dict, profile: dict, run_id: str) -> None:
    domain = manifest["domain"]
    crawl_cfg = _crawl_defaults(manifest)
    results_path  = _artifact_path(workspace, manifest, "semantic_results")
    failures_path = _artifact_path(workspace, manifest, "semantic_failures")
    cards_path    = _artifact_path(workspace, manifest, "controversy_cards")
    bundle_path   = _synthesis_bundle_path(workspace, "controversy", run_id)

    # Step 1 — candidate sweep (checkpointed)
    queries = [
        SemanticQuery("controversy_debate",      f"{domain} debate"),
        SemanticQuery("controversy_critique",    f"{domain} critique limitations"),
        SemanticQuery("controversy_contradicts", f"{domain} contradicts findings"),
        SemanticQuery("controversy_rebuttal",    f"{domain} rebuttal comment reply"),
        SemanticQuery("controversy_overclaim",   f"{domain} overclaim reconsidered"),
    ]
    crawl_semantic_queries(
        queries,
        SemanticCrawlConfig(
            output=results_path,
            failures=failures_path,
            endpoint="relevance",
            limit=15,
            fields="paperId,title,year,abstract,citationCount,authors",
            until_complete=True,
            pause_seconds=crawl_cfg.get("pause_seconds", 1.0),
            max_retries=crawl_cfg.get("max_retries", 3),
        ),
    )

    # Steps 2+3 — citations + challenge filter (skip if bundle already built)
    if not bundle_path.exists():
        NOW_YEAR = datetime.now(timezone.utc).year
        candidates = _collect_papers_from_crawl(results_path)
        pairs: list[dict] = []
        with SemanticScholarClient() as client:
            for paper in list(candidates.values())[:20]:
                if (paper.get("citationCount") or 0) < 20:
                    continue
                try:
                    citations = client.get_paper_citations(
                        paper_id=paper["paperId"],
                        fields="paperId,title,year,abstract,authors",
                    )
                except Exception:
                    continue
                recent = [c for c in citations if (c.get("year") or 0) >= NOW_YEAR - 3]
                challengers = [
                    c for c in recent
                    if any(
                        phrase in f"{c.get('title') or ''} {c.get('abstract') or ''}".lower()
                        for phrase in _CHALLENGE_PHRASES
                    )
                ]
                if challengers:
                    pairs.append({"seminal": paper, "challengers": challengers[:5]})

        _write_json(bundle_path, {
            "schema_version": "1",
            "paradigm": "controversy",
            "run_id": run_id,
            "domain": domain,
            "created_at": utc_now(),
            "candidate_pairs": pairs[:30],
            "seed_papers": profile.get("seed_papers", []),
            "engaging_axes": profile.get("derived_traits", {}).get("engaging_axes", []),
            "boring_axes": profile.get("derived_traits", {}).get("boring_axes", []),
        })
        typer.echo(f"Synthesis bundle: {bundle_path} ({len(pairs)} candidate pairs)")

    # Step 4 — render if cards exist, else prompt for synthesis
    if not _read_jsonl(cards_path):
        _print_synthesis_needed(
            bundle_path, cards_path,
            "Produce 5-8 controversy cards following references/paradigm_controversy.md.\n"
            "Each card needs a distinct ai_diversity_axis.\n"
            "Both sides must have papers from the last 3 years.",
        )
        return

    out = render_module.render_controversy(workspace, manifest, run_id, profile)
    typer.echo(f"Report: {out}")


def _run_failure_archive(workspace: Path, manifest: dict, profile: dict, run_id: str) -> None:
    domain = manifest["domain"]
    crawl_cfg = _crawl_defaults(manifest)
    results_path  = _artifact_path(workspace, manifest, "semantic_results")
    failures_path = _artifact_path(workspace, manifest, "semantic_failures")
    archive_path  = _artifact_path(workspace, manifest, "failure_archive")
    bundle_path   = _synthesis_bundle_path(workspace, "failure-archive", run_id)
    NOW_YEAR = datetime.now(timezone.utc).year

    # Step 1 — historical stars via bulk crawl (checkpointed)
    crawl_semantic_queries(
        [SemanticQuery("history_stars", domain)],
        SemanticCrawlConfig(
            output=results_path,
            failures=failures_path,
            endpoint="bulk",
            limit=50,
            fields="paperId,title,year,abstract,citationCount,venue,authors",
            sort="citationCount:desc",
            year=f"{NOW_YEAR - 15}-{NOW_YEAR - 5}",
            until_complete=True,
            pause_seconds=crawl_cfg.get("pause_seconds", 1.0),
            max_retries=crawl_cfg.get("max_retries", 3),
        ),
    )

    if not bundle_path.exists():
        stars = list(_collect_papers_from_crawl(results_path).values())

        # Steps 2+3 — citation timeline + abandonment scoring
        abandoned_candidates: list[dict] = []
        with SemanticScholarClient() as client:
            for star in stars[:30]:
                pid = star.get("paperId")
                if not pid:
                    continue
                try:
                    citations = client.get_paper_citations(paper_id=pid, fields="paperId,year")
                except Exception:
                    continue
                year_buckets: Counter = Counter(
                    c.get("year") for c in citations if c.get("year")
                )
                if not year_buckets:
                    continue
                peak_year, peak_count = max(year_buckets.items(), key=lambda x: x[1])
                recent_count = sum(year_buckets[y] for y in range(NOW_YEAR - 1, NOW_YEAR + 1))
                decay_ratio = recent_count / peak_count if peak_count > 0 else 0.0
                if decay_ratio < 0.20 and peak_count >= 30:
                    abandoned_candidates.append({
                        "paper": star,
                        "peak_year": peak_year,
                        "peak_count": peak_count,
                        "decay_ratio": round(decay_ratio, 3),
                        "year_buckets": dict(year_buckets),
                    })

            # Steps 4+5 — critique sweep + absorption check
            enriched: list[dict] = []
            for candidate in abandoned_candidates[:15]:
                title = candidate["paper"].get("title") or ""
                try:
                    critique = client.search_papers(
                        query=f"{title} reconsidered limitations negative results",
                        limit=8,
                        fields="paperId,title,year,abstract,citationCount",
                    ).get("data", [])
                    absorbed = client.search_papers(
                        query=f"{title} extension generalization unified",
                        limit=10,
                        fields="paperId,title,year,abstract,citationCount",
                    ).get("data", [])
                except Exception:
                    critique, absorbed = [], []
                candidate["critique_papers"] = critique
                candidate["absorption_check_papers"] = absorbed
                enriched.append(candidate)

        _write_json(bundle_path, {
            "schema_version": "1",
            "paradigm": "failure-archive",
            "run_id": run_id,
            "domain": domain,
            "created_at": utc_now(),
            "abandoned_candidates": enriched,
            "seed_papers": profile.get("seed_papers", []),
            "engaging_axes": profile.get("derived_traits", {}).get("engaging_axes", []),
            "boring_axes": profile.get("derived_traits", {}).get("boring_axes", []),
        })
        typer.echo(f"Synthesis bundle: {bundle_path} ({len(enriched)} abandoned candidates)")

    if not _read_jsonl(archive_path):
        _print_synthesis_needed(
            bundle_path, archive_path,
            "Produce 5-10 failure archive entries following references/paradigm_failure_archive.md.\n"
            "Drop candidates whose absorption_check_papers contain a successor.\n"
            "Each abandonment reason must be tagged era_dependent or permanent.",
        )
        return

    out = render_module.render_failure_archive(workspace, manifest, run_id, profile)
    typer.echo(f"Report: {out}")


def _run_matrix(workspace: Path, manifest: dict, profile: dict, run_id: str) -> None:
    domain = manifest["domain"]
    crawl_cfg = _crawl_defaults(manifest)
    results_path  = _artifact_path(workspace, manifest, "semantic_results")
    failures_path = _artifact_path(workspace, manifest, "semantic_failures")
    matrix_path   = _artifact_path(workspace, manifest, "matrix")
    max_queries   = manifest.get("defaults", {}).get("matrix", {}).get("max_queries_per_run", 32)

    scope_yaml_path = workspace / "inputs" / "scope.yaml"
    scope = read_yaml(scope_yaml_path) if scope_yaml_path.exists() else {}
    scenario_hints = scope.get("non_standard_scenarios_hint") or []

    matrix_data = _read_json(matrix_path)
    methods   = matrix_data.get("dimensions", {}).get("methods", [])
    scenarios = matrix_data.get("dimensions", {}).get("scenarios", [])

    # Phase A — warmup + dimension proposal bundle
    warmup_bundle = _synthesis_bundle_path(workspace, "matrix-warmup", run_id)
    if not warmup_bundle.exists():
        try:
            with SemanticScholarClient() as client:
                warmup_papers = client.search_papers(
                    query=f"{domain} survey methods",
                    limit=10,
                    fields="title,abstract,year",
                ).get("data", [])
        except Exception:
            warmup_papers = []
        _write_json(warmup_bundle, {
            "schema_version": "1",
            "paradigm": "matrix-warmup",
            "run_id": run_id,
            "domain": domain,
            "created_at": utc_now(),
            "warmup_papers": warmup_papers,
            "seed_papers": profile.get("seed_papers", []),
            "engaging_keywords": profile.get("derived_traits", {}).get("engaging_keywords", []),
            "scenario_hints": scenario_hints,
        })
        typer.echo(f"Warmup bundle: {warmup_bundle}")

    if not methods or not scenarios:
        sep = "=" * 60
        typer.echo(
            f"\n{sep}\nDIMENSION PROPOSAL NEEDED\n{sep}\n"
            f"Read {warmup_bundle} and write dimensions into {matrix_path}.\n"
            'Format: {"dimensions": {"methods": [...], "scenarios": [...]}, "cells": []}\n'
            "Rules: 5-8 methods by mechanism; 5-8 scenarios with ≥3 non-standard.\n"
            "Then rerun to fill cells."
        )
        return

    # Phase B — cell-filling crawl (checkpointed by query_id = cell_id)
    cell_queries = [
        SemanticQuery(f"{m['id']}x{s['id']}", f"{m['label']} {s['label']} {domain}")
        for m in methods for s in scenarios
    ]
    crawl_semantic_queries(
        cell_queries,
        SemanticCrawlConfig(
            output=results_path,
            failures=failures_path,
            endpoint="relevance",
            limit=10,
            fields="paperId,title,year,abstract,citationCount",
            until_complete=True,
            max_queries=max_queries,
            pause_seconds=crawl_cfg.get("pause_seconds", 1.0),
            max_retries=crawl_cfg.get("max_retries", 3),
        ),
    )

    # Phase C — density labeling (pure statistics)
    cell_results: dict[str, list[dict]] = {
        record.get("query_id", ""): record.get("papers") or []
        for record in _read_jsonl(results_path)
    }
    failed_qids = {r.get("query_id") for r in _read_jsonl(failures_path)}

    cells = []
    for m in methods:
        for s in scenarios:
            cell_id = f"{m['id']}x{s['id']}"
            papers = cell_results.get(cell_id, [])
            paper_count = len(papers)
            max_citations = max((p.get("citationCount") or 0 for p in papers), default=0)
            density = (
                "unknown" if cell_id in failed_qids and not papers
                else label_density(paper_count, max_citations)
            )
            top_papers = sorted(papers, key=lambda p: p.get("citationCount") or 0, reverse=True)[:3]
            cells.append({
                "cell_id": cell_id,
                "method_id": m["id"],
                "scenario_id": s["id"],
                "query_used": f"{m['label']} {s['label']} {domain}",
                "paper_count": paper_count,
                "max_citations": max_citations,
                "density": density,
                "top_papers": [
                    {
                        "paper_id": p.get("paperId"),
                        "title": p.get("title"),
                        "year": p.get("year"),
                        "citation_count": p.get("citationCount") or 0,
                    }
                    for p in top_papers
                ],
                "ai_diversity_axis": None,
                "ai_void_note": None,
            })

    matrix_data.update({
        "schema_version": "1",
        "domain": domain,
        "generated_at": utc_now(),
        "cells": cells,
    })
    _write_json(matrix_path, matrix_data)

    # Phase D — void-note pass
    sparse_empty = [c for c in cells if c["density"] in {"sparse", "empty"}]
    has_void_notes = all(c.get("ai_void_note") for c in sparse_empty) if sparse_empty else True

    if not has_void_notes:
        void_bundle = _synthesis_bundle_path(workspace, "matrix-void", run_id)
        _write_json(void_bundle, {
            "schema_version": "1",
            "paradigm": "matrix-void",
            "run_id": run_id,
            "domain": domain,
            "created_at": utc_now(),
            "sparse_empty_cells": sparse_empty,
            "dimensions": matrix_data.get("dimensions", {}),
        })
        sep = "=" * 60
        typer.echo(
            f"\n{sep}\nVOID-NOTE PASS NEEDED\n{sep}\n"
            f"Read {void_bundle}.\n"
            f"For each sparse/empty cell, update ai_void_note and ai_diversity_axis in {matrix_path}.\n"
            "Then rerun to render the report."
        )
        return

    out = render_module.render_matrix(workspace, manifest, run_id, profile)
    typer.echo(f"Report: {out}")


def _run_cross_domain(workspace: Path, manifest: dict, profile: dict, run_id: str) -> None:
    domain = manifest["domain"]
    crawl_cfg = _crawl_defaults(manifest)
    results_path  = _artifact_path(workspace, manifest, "semantic_results")
    failures_path = _artifact_path(workspace, manifest, "semantic_failures")
    pairs_path    = _artifact_path(workspace, manifest, "cross_domain_pairs")

    scope_yaml_path = workspace / "inputs" / "scope.yaml"
    scope = read_yaml(scope_yaml_path) if scope_yaml_path.exists() else {}
    home_field      = scope.get("home_field") or domain
    foreign_fields: list[str] = scope.get("foreign_fields_allowed") or [
        "Biology", "Physics", "Sociology", "Psychology", "Economics", "Linguistics",
    ]
    home_vocabulary: set[str] = set(scope.get("home_vocabulary") or [])

    # Phase A — skeleton extraction bundle
    skeleton_bundle = _synthesis_bundle_path(workspace, "cross-domain-skeletons", run_id)
    queries_bundle  = _synthesis_bundle_path(workspace, "cross-domain-queries", run_id)

    if not skeleton_bundle.exists():
        _write_json(skeleton_bundle, {
            "schema_version": "1",
            "paradigm": "cross-domain-skeletons",
            "run_id": run_id,
            "domain": domain,
            "created_at": utc_now(),
            "seed_papers": profile.get("seed_papers", []),
            "instructions": (
                "Extract 1-2 problem-structure skeletons from the seed papers. "
                "For each skeleton: describe (a) input shape, (b) objective, (c) core difficulty. "
                "Do NOT mention the home domain by name. "
                "For each skeleton, generate 2-3 functional-vocabulary queries "
                "(no domain-specific terms) that would retrieve structurally similar problems "
                "in other fields. "
                f"Write results to {queries_bundle} as: "
                '{"skeletons": [...], "functional_queries": [{"skeleton_id": 0, "queries": '
                '[{"query_text": "..."}]}]}'
            ),
        })
        typer.echo(f"Skeleton bundle: {skeleton_bundle}")

    if not queries_bundle.exists():
        sep = "=" * 60
        typer.echo(
            f"\n{sep}\nSKELETON EXTRACTION NEEDED\n{sep}\n"
            f"Read {skeleton_bundle}.\n"
            f"Extract skeletons and write functional queries to {queries_bundle}.\n"
            "Then rerun to search foreign-domain candidates."
        )
        return

    # Phase B — crawl with functional queries (checkpointed)
    queries_data = _read_json(queries_bundle)
    functional_queries = queries_data.get("functional_queries") or []
    sq_list = [
        SemanticQuery(f"sk{i}_q{j}", q["query_text"])
        for i, sk in enumerate(functional_queries)
        for j, q in enumerate(sk.get("queries") or [])
        if q.get("query_text")
    ]
    if sq_list:
        crawl_semantic_queries(
            sq_list,
            SemanticCrawlConfig(
                output=results_path,
                failures=failures_path,
                endpoint="bulk",
                limit=20,
                fields="paperId,title,year,abstract,citationCount,fieldsOfStudy,authors,venue",
                until_complete=True,
                pause_seconds=crawl_cfg.get("pause_seconds", 1.0),
                max_retries=crawl_cfg.get("max_retries", 3),
            ),
        )

    # Phase C — surface-vocabulary filter
    home_vocab_tokens = tokenize(" ".join(home_vocabulary), DEFAULT_STOPWORDS) if home_vocabulary else set()
    filtered_foreign: list[dict] = []
    for paper in _collect_papers_from_crawl(results_path).values():
        paper_fields = set(paper.get("fieldsOfStudy") or [])
        # skip papers that are solely from the home field
        if home_field and paper_fields == {home_field}:
            continue
        if home_vocab_tokens:
            abstract_tokens = tokenize(
                f"{paper.get('title') or ''} {paper.get('abstract') or ''}",
                DEFAULT_STOPWORDS,
            )
            if abstract_tokens and len(abstract_tokens & home_vocab_tokens) / len(abstract_tokens) > 0.25:
                continue
        filtered_foreign.append(paper)

    # Phase D — pairing bundle
    pairing_bundle = _synthesis_bundle_path(workspace, "cross-domain-pairing", run_id)
    _write_json(pairing_bundle, {
        "schema_version": "1",
        "paradigm": "cross-domain-pairing",
        "run_id": run_id,
        "domain": domain,
        "created_at": utc_now(),
        "skeletons": queries_data.get("skeletons") or [],
        "foreign_candidates": filtered_foreign[:60],
        "seed_papers": profile.get("seed_papers", []),
        "engaging_keywords": profile.get("derived_traits", {}).get("engaging_keywords", []),
    })
    typer.echo(f"Pairing bundle: {pairing_bundle} ({len(filtered_foreign)} foreign candidates)")

    if not _read_jsonl(pairs_path):
        _print_synthesis_needed(
            pairing_bundle, pairs_path,
            "Produce 5-8 cross-domain pairs following references/paradigm_cross_domain.md.\n"
            "home_paper.field != foreign_paper.field.\n"
            "Reject pairs with heavy surface-vocabulary overlap.\n"
            "likely_break_point is mandatory for every pair.",
        )
        return

    out = render_module.render_cross_domain(workspace, manifest, run_id, profile)
    typer.echo(f"Report: {out}")

# ---------------------------------------------------------------------------
# Commands: react
# ---------------------------------------------------------------------------


@trigger_app.command("react")
def trigger_react(
    workspace_dir: Path = typer.Option(..., "--workspace"),
    card_id: str = typer.Option(...),
    reaction: str = typer.Option(...),
    take: str | None = typer.Option(None, "--take"),
) -> None:
    workspace = workspace_dir.resolve()
    manifest = _load_manifest(workspace)
    paradigm, card_summary, card_axis = _lookup_card(workspace, manifest, card_id)
    if paradigm is None:
        raise typer.BadParameter(f"Card not found in any paradigm artifact: {card_id}")

    valid = VALID_REACTIONS_PER_PARADIGM[paradigm]
    if reaction not in valid:
        raise typer.BadParameter(f"--reaction for {paradigm} must be one of {sorted(valid)}")
    if reaction in POSITIVE_REACTIONS and not (take and take.strip()):
        raise typer.BadParameter(
            f"Reaction '{reaction}' is positive; --take is mandatory and must be non-empty."
        )

    captured_at = utc_now()
    record = {
        "reaction_id": "r_" + _short_hash(f"{card_id}-{captured_at}"),
        "captured_at": captured_at,
        "paradigm": paradigm,
        "card_id": card_id,
        "card_summary": card_summary,
        "card_diversity_axis": card_axis,
        "reaction": reaction,
        "user_take": (take or "").strip() or None,
        "source_run_id": _run_id_from_card(card_id),
    }
    _append_jsonl(_artifact_path(workspace, manifest, "reactions"), record)
    _refresh_profile(workspace, manifest)
    typer.echo(f"Reaction recorded: {record['reaction_id']}")


def _lookup_card(workspace: Path, manifest: dict, card_id: str) -> tuple[str | None, str, str]:
    for paradigm, key in [
        ("controversy",     "controversy_cards"),
        ("failure-archive", "failure_archive"),
        ("cross-domain",    "cross_domain_pairs"),
    ]:
        for record in _read_jsonl((workspace / manifest["artifacts"][key]).resolve()):
            if record.get("card_id") == card_id:
                summary = record.get(
                    "proposition" if paradigm == "controversy"
                    else "direction_name" if paradigm == "failure-archive"
                    else "skeleton",
                    "",
                )
                return paradigm, summary[:200], record.get("ai_diversity_axis", "")

    matrix_data = _read_json((workspace / manifest["artifacts"]["matrix"]).resolve())
    for cell in matrix_data.get("cells", []):
        if cell.get("cell_id") == card_id:
            note = cell.get("ai_void_note") or f"density={cell.get('density')}"
            return "matrix", note[:200], cell.get("ai_diversity_axis", "")

    return None, "", ""


def _run_id_from_card(card_id: str) -> str:
    parts = card_id.rsplit("_", 1)
    return parts[0] if len(parts) > 1 else card_id

# ---------------------------------------------------------------------------
# Commands: profile
# ---------------------------------------------------------------------------


@trigger_app.command("profile")
def trigger_profile(workspace_dir: Path = typer.Option(..., "--workspace")) -> None:
    workspace = workspace_dir.resolve()
    manifest = _load_manifest(workspace)
    profile = _refresh_profile(workspace, manifest)
    traits = profile.get("derived_traits", {})
    typer.echo(f"Updated: {profile.get('updated_at')}")
    typer.echo(f"Window size: {len(profile.get('recent_reactions', []))}")
    typer.echo(f"Preferred paradigm: {traits.get('preferred_paradigm')}")
    typer.echo(f"Engaging axes: {traits.get('engaging_axes')}")
    typer.echo(f"Boring axes: {traits.get('boring_axes')}")
    typer.echo(f"Engaging keywords (top 5): {traits.get('engaging_keywords', [])[:5]}")
    typer.echo(f"Boring keywords (top 5): {traits.get('boring_keywords', [])[:5]}")
    for r in profile.get("recent_reactions", [])[-5:]:
        typer.echo(f"  {r['reaction_id']} [{r['paradigm']}/{r['reaction']}] {r['card_summary'][:80]}")

# ---------------------------------------------------------------------------
# Commands: relay
# ---------------------------------------------------------------------------


@trigger_app.command("relay")
def trigger_relay(
    workspace_dir: Path = typer.Option(..., "--workspace"),
    source_card: str = typer.Option(..., "--source-card"),
    target_paradigm: str = typer.Option(..., "--target-paradigm"),
) -> None:
    if target_paradigm not in PARADIGM_CHOICES:
        raise typer.BadParameter(f"--target-paradigm must be one of {PARADIGM_CHOICES}")
    workspace = workspace_dir.resolve()
    manifest = _load_manifest(workspace)
    paradigm, summary, axis = _lookup_card(workspace, manifest, source_card)
    if paradigm is None:
        raise typer.BadParameter(f"Source card not found: {source_card}")

    reactions = _read_jsonl(_artifact_path(workspace, manifest, "reactions"))
    take = next(
        (r.get("user_take") for r in reversed(reactions)
         if r["card_id"] == source_card and r["reaction"] in POSITIVE_REACTIONS),
        None,
    )
    if not take:
        raise typer.BadParameter(
            f"Source card {source_card} has no positive reaction with a take. "
            "relay only carries forward reactions the user already engaged with."
        )

    relay_path = workspace / "artifacts" / f"relay_to_{target_paradigm}.json"
    _write_json(relay_path, {
        "schema_version": "1",
        "created_at": utc_now(),
        "source_card_id": source_card,
        "source_paradigm": paradigm,
        "target_paradigm": target_paradigm,
        "card_summary": summary,
        "user_take": take,
        "card_diversity_axis": axis,
    })
    typer.echo(
        f"Relay payload written: {relay_path}. "
        f"Run `autoscholar trigger push --paradigm {target_paradigm}` next."
    )
