from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from autoscholar.citation.common import normalize_text, slugify, tokenize, utc_now
from autoscholar.exceptions import ValidationError
from autoscholar.integrations import SemanticScholarClient
from autoscholar.io import read_json, read_text, write_json, write_text
from autoscholar.journal_fit.input_parser import (
    extract_materials_from_pdf,
    load_materials_from_workspace,
    load_or_build_figures_manifest,
    parse_materials_markdown,
    render_materials_markdown,
    validate_materials,
)
from autoscholar.journal_fit.models import (
    AdversarialReviewRecord,
    AngleType,
    AssetInventoryRecord,
    AssetRecord,
    ContributionTypeWeightRecord,
    CurrentContributionRecord,
    EvidenceRefRecord,
    ExistingNarrativeRecord,
    FitMatrixEntryRecord,
    FitMatrixRecord,
    FitScoresRecord,
    FiguresManifestRecord,
    JournalFitMode,
    JournalProfileRecord,
    NarrativeCandidateRecord,
    NarrativeClaimRecord,
    OverclaimedItemRecord,
    PatchListRecord,
    PatchRecord,
    ReferencePaperRecord,
    ReviewQuestionRecord,
    ReviewTargetRecord,
    RunMetaRecord,
    RunSourceRecord,
    SourceFetchRecord,
    TargetJournalRecord,
    TopCombinationRecord,
    WritingStyleRecord,
)
from autoscholar.journal_fit.workspace import JournalFitWorkspace


DEFAULT_SCORE_WEIGHTS = {
    "taste_fit": 0.3,
    "evidence_support": 0.35,
    "differentiation": 0.2,
    "risk": 0.15,
}

ANGLE_PRIORITY: list[AngleType] = [
    "method-novelty",
    "application-driven",
    "empirical-discovery",
    "efficiency-focused",
    "unification",
    "theoretical-insight",
    "systems-contribution",
]


@dataclass
class JournalFitRunSummary:
    primary_narrative: str
    primary_journal: str
    primary_risk: str
    backup_narrative: str | None
    backup_journal: str | None
    action_items: list[str]
    warnings: list[str]
    report_path: Path


def _plain_tokens(text: str) -> set[str]:
    return tokenize(normalize_text(text), set())


def _safe_average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _clamp_score(value: float) -> int:
    return max(1, min(5, int(round(value))))


def _strength_score(value: str) -> int:
    return {"strong": 5, "medium": 3, "weak": 2}.get(value, 1)


def _infer_asset_category(text: str, default: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("efficien", "latency", "runtime", "parameter", "memory", "faster")):
        return "efficiency"
    if any(token in lowered for token in ("interpret", "explain", "attention", "visual", "saliency", "case")):
        return "interpretability"
    if any(token in lowered for token in ("theory", "theorem", "bound", "proof", "guarantee")):
        return "theory"
    if any(token in lowered for token in ("general", "robust", "cross-domain", "across", "transfer", "multi-dataset")):
        return "generality"
    if any(token in lowered for token in ("application", "clinical", "real-world", "practice", "deployed")):
        return "application"
    if any(token in lowered for token in ("framework", "pipeline", "architecture", "system", "module", "workflow")):
        return "methodology"
    return default


def _infer_angle(text: str, category: str | None = None) -> AngleType:
    lowered = text.lower()
    if category == "efficiency" or any(token in lowered for token in ("efficien", "latency", "runtime", "fast")):
        return "efficiency-focused"
    if category == "theory" or any(token in lowered for token in ("theory", "theorem", "proof")):
        return "theoretical-insight"
    if category == "application" or any(token in lowered for token in ("clinical", "application", "practice", "patient")):
        return "application-driven"
    if category == "generality" or any(token in lowered for token in ("unified", "general", "across", "cross-domain")):
        return "unification"
    if any(token in lowered for token in ("benchmark", "empirical", "study", "analysis")):
        return "empirical-discovery"
    if any(token in lowered for token in ("system", "platform", "pipeline", "workflow")):
        return "systems-contribution"
    return "method-novelty"


def _datasets_strength_count(texts: list[str]) -> int:
    total = 0
    for text in texts:
        if not text:
            continue
        total += len([item for item in re.split(r"[;,/]\s*|\band\b", text) if item.strip()])
    return total


def _contains_numeric_signal(text: str) -> bool:
    return bool(re.search(r"\d", text))


def _extract_sentences(text: str, limit: int = 2) -> list[str]:
    sentences = [
        item.strip(" -")
        for item in re.split(r"(?<=[.!?。！？])\s+|\n+", normalize_text(text))
        if item.strip(" -")
    ]
    return sentences[:limit] if sentences else ([normalize_text(text)] if text.strip() else [])


def _summarize_text(text: str, max_segments: int = 2, max_words: int = 28) -> str:
    segments = _extract_sentences(text, limit=max_segments)
    if not segments:
        return normalize_text(text).strip()
    summary = " ".join(segments)
    words = summary.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]).rstrip(",;:.") + "..."
    return summary


def _display_text(text: str, max_words: int = 14) -> str:
    summary = _summarize_text(text, max_segments=1, max_words=max_words)
    return summary[0].lower() + summary[1:] if len(summary) > 1 else summary.lower()


def _strongest_strength(assets: list[AssetRecord]) -> str:
    if any(asset.strength == "strong" for asset in assets):
        return "strong"
    if any(asset.strength == "medium" for asset in assets):
        return "medium"
    return "weak"


def _task_label(materials: Any, default: str = "the target task", max_words: int = 12) -> str:
    raw_task = normalize_text(materials.identity.task or "").strip()
    if not raw_task:
        return default
    words = raw_task.split()
    if words and words[0].lower() in {
        "develop",
        "apply",
        "propose",
        "present",
        "introduce",
        "design",
        "build",
        "construct",
        "study",
        "evaluate",
    } and len(words) > max_words:
        return default
    return _summarize_text(raw_task, max_segments=1, max_words=max_words).rstrip(".")


def _domain_label(materials: Any, default: str = "the field", max_words: int = 8) -> str:
    return _summarize_text(materials.identity.domain or default, max_segments=1, max_words=max_words).rstrip(".")


def _build_contribution_lines(
    candidate: NarrativeCandidateRecord,
    assets: list[AssetRecord],
) -> list[str]:
    asset_map = {asset.id: asset for asset in assets}
    lines: list[str] = []
    seen: set[str] = set()

    def add_line(text: str, support_ids: list[str]) -> None:
        normalized = normalize_text(text)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        support = ", ".join(support_ids) if support_ids else "n/a"
        lines.append(f"- {text}  (`assets: {support}`)")

    for claim in candidate.main_claims[:4]:
        add_line(_summarize_text(claim.claim, max_segments=2, max_words=18), claim.supporting_assets)

    fallback_asset_ids = [*candidate.assets_to_foreground, *candidate.assets_to_background]
    for asset_id in fallback_asset_ids:
        asset = asset_map.get(asset_id)
        if asset is None:
            continue
        add_line(_summarize_text(asset.content, max_segments=2, max_words=18), [asset_id])
        if len(lines) >= 4:
            break

    if len(lines) < 3:
        add_line(
            _summarize_text(candidate.one_line_thesis, max_segments=1, max_words=18),
            candidate.assets_to_foreground[:2],
        )

    return lines[:4] or ["- Rebuild the contribution bullets from the strongest asset before drafting."]


def _group_related_work(journal: JournalProfileRecord, candidate: NarrativeCandidateRecord) -> list[str]:
    if not journal.reference_papers:
        return ["- No reference-paper cluster was available. Refresh Phase 2 before drafting Related Work."]

    label_map = {
        "method-novelty": "method novelty",
        "application-driven": "application driven",
        "theoretical-insight": "theoretical insight",
        "efficiency-focused": "efficiency focused",
        "unification": "unification",
        "empirical-discovery": "empirical discovery",
        "systems-contribution": "systems contribution",
    }
    grouped: dict[str, list[str]] = {}
    for paper in journal.reference_papers[:6]:
        bucket = _infer_angle(f"{paper.title} {paper.abstract or ''}")
        label = label_map.get(bucket, bucket.replace("-", " "))
        grouped.setdefault(label, []).append(f"{paper.title} ({paper.year or 'n/a'})")

    target_gap = candidate.main_angle.replace("-", " ")
    lines: list[str] = []
    for label, items in grouped.items():
        lines.append(
            f"- {label}: {'; '.join(items[:3])}. Gap: pivot from this cluster to why the paper needs a {target_gap} framing."
        )
    return lines


def _review_resolution(concern: str) -> tuple[str, str, int, str]:
    lowered = concern.lower()
    patch_type = _patch_type_for_concern(concern)

    if any(token in concern for token in ("真实应用场景", "实用价值", "落地")) or any(
        token in lowered for token in ("real-world", "practical value", "deployment", "use case")
    ):
        return (
            "no",
            "none",
            0,
            "This concern needs new external validation or a clearer application case; current artifacts can only soften the claim.",
        )

    if "理论" in concern or any(token in lowered for token in ("theory", "theoretical", "mechanism")):
        return (
            "partial",
            "appendix-note",
            3,
            "Add a compact mechanism explanation or appendix note, but avoid claiming full theoretical closure.",
        )

    if patch_type == "new-analysis":
        return (
            "partial",
            patch_type,
            5,
            "Add one focused analysis slice from existing outputs to answer the concern directly.",
        )
    if patch_type == "new-figure":
        return (
            "partial",
            patch_type,
            4,
            "Add or revise a figure so the defended claim is visible at first glance.",
        )
    if patch_type == "new-ablation-snippet":
        return (
            "partial",
            patch_type,
            6,
            "Expose a narrow ablation snippet from existing logs instead of rerunning the full study.",
        )
    if patch_type == "appendix-note":
        return (
            "yes",
            patch_type,
            3,
            "Move supporting explanation into an appendix note tied directly to the current evidence.",
        )
    return (
        "yes",
        "rewording",
        2,
        "Tighten the claim language so it matches the strongest existing experiment.",
    )


def _build_report_warnings(
    matrix: FitMatrixRecord,
    profiles: dict[str, JournalProfileRecord],
    narratives: dict[str, NarrativeCandidateRecord],
) -> list[str]:
    warnings: list[str] = []
    if any(profile.confidence == "low" for profile in profiles.values()):
        warnings.append("At least one journal profile is low confidence; treat the ranking as directional until Phase 2 is refreshed.")
    generated_narratives = [narrative for key, narrative in narratives.items() if key != "N0"]
    if len(generated_narratives) < 3:
        warnings.append("Narrative space remained narrow after de-duplication; ranking gaps may be fragile.")
    entry_map = {(entry.narrative_id, entry.journal_slug): entry for entry in matrix.matrix}
    top_entry = None
    if matrix.top_combinations:
        top = matrix.top_combinations[0]
        top_entry = entry_map.get((top.narrative_id, top.journal_slug))
    if top_entry is not None and top_entry.scores.taste_fit < 3:
        warnings.append("Even the top option has weak taste fit. Reconsider the target journal list before a deep rewrite.")
    return warnings


def _merge_materials(preferred: Any, overrides: Any) -> Any:
    merged = preferred.model_copy(deep=True)
    if overrides.identity.domain:
        merged.identity.domain = overrides.identity.domain
    if overrides.identity.task:
        merged.identity.task = overrides.identity.task
    if overrides.identity.working_title:
        merged.identity.working_title = overrides.identity.working_title
    if overrides.algorithm.input_spec.strip():
        merged.algorithm.input_spec = overrides.algorithm.input_spec
    if overrides.algorithm.method_pipeline.strip():
        merged.algorithm.method_pipeline = overrides.algorithm.method_pipeline
    if overrides.algorithm.output_spec.strip():
        merged.algorithm.output_spec = overrides.algorithm.output_spec
    if overrides.algorithm.novelty_claims:
        merged.algorithm.novelty_claims = overrides.algorithm.novelty_claims
    if overrides.experiments:
        merged.experiments = overrides.experiments
    if overrides.target_journals:
        merged.target_journals = overrides.target_journals
    for field in ("current_abstract", "current_intro_p1", "figure_1_caption", "prior_rejection_feedback"):
        value = getattr(overrides.existing_drafts, field)
        if value:
            setattr(merged.existing_drafts, field, value)
    merged.extraction_notes = list(dict.fromkeys([*preferred.extraction_notes, *overrides.extraction_notes]))
    return merged


def _build_assets(materials: Any, figures_manifest: FiguresManifestRecord) -> list[AssetRecord]:
    assets: list[AssetRecord] = []
    asset_index = 1

    def add_asset(category: str, content: str, refs: list[EvidenceRefRecord], strength: str, rationale: str, caveats: str | None = None) -> None:
        nonlocal asset_index
        normalized = normalize_text(content)
        if not normalized:
            return
        if any(normalize_text(item.content) == normalized for item in assets):
            return
        assets.append(
            AssetRecord(
                id=f"A{asset_index:02d}",
                category=category,  # type: ignore[arg-type]
                content=content,
                evidence_refs=refs,
                strength=strength,  # type: ignore[arg-type]
                strength_rationale=rationale,
                caveats=caveats,
            )
        )
        asset_index += 1

    for novelty in materials.algorithm.novelty_claims:
        category = _infer_asset_category(novelty, "methodology")
        add_asset(
            category,
            _summarize_text(novelty, max_segments=1, max_words=26),
            [EvidenceRefRecord(type="method", ref="Algorithm.novelty")],
            "weak",
            "Author-declared novelty without direct quantitative support yet.",
            "Need to anchor this framing to experiment-backed evidence when writing.",
        )

    algorithm_summary = _summarize_text(materials.algorithm.method_pipeline, max_segments=2, max_words=32)
    if algorithm_summary:
        category = _infer_asset_category(algorithm_summary, "methodology")
        add_asset(
            category,
            algorithm_summary,
            [EvidenceRefRecord(type="method", ref="Algorithm.method_pipeline")],
            "medium",
            "Method properties are explicitly described in the fixed pipeline.",
            "Strength depends on how directly experiments validate this property.",
        )

    for experiment in materials.experiments:
        dataset_count = max(1, len(experiment.datasets))
        has_numbers = _contains_numeric_signal(experiment.key_results)
        strength = "strong" if has_numbers and dataset_count >= 2 else "medium"
        rationale = (
            "Supported by direct quantitative evidence across multiple datasets/settings."
            if strength == "strong"
            else "Supported by direct results, but evidence breadth is limited."
        )
        caveat = None if strength == "strong" else "This result should be framed as setting-specific unless more breadth is shown."
        performance_content = _summarize_text(experiment.key_results, max_segments=3, max_words=36)
        add_asset(
            _infer_asset_category(performance_content, "performance"),
            f"{experiment.name}: {performance_content}",
            [EvidenceRefRecord(type="experiment", ref=experiment.experiment_id)],
            strength,
            rationale,
            caveat,
        )
        if experiment.side_findings:
            add_asset(
                _infer_asset_category(experiment.side_findings, "interpretability"),
                f"{experiment.name} side finding: {_summarize_text(experiment.side_findings, max_segments=2, max_words=28)}",
                [EvidenceRefRecord(type="experiment", ref=experiment.experiment_id)],
                "medium" if has_numbers else "weak",
                "Derived from secondary observations attached to the experiment.",
                "Treat as supporting context rather than the paper's only central claim.",
            )
        if len(experiment.datasets) >= 2:
            add_asset(
                "generality",
                f"{experiment.name} validates behavior across {len(experiment.datasets)} datasets/settings.",
                [EvidenceRefRecord(type="experiment", ref=experiment.experiment_id)],
                "strong",
                "The experiment explicitly spans multiple datasets or settings.",
            )

    for figure in figures_manifest.figures:
        figure_text = " ".join(filter(None, [figure.what_it_shows, figure.visual_claim, figure.numeric_claim or "", figure.caption_original]))
        category = _infer_asset_category(figure_text, "interpretability")
        strength = "medium" if figure.numeric_claim or figure.linked_experiments else "weak"
        add_asset(
            category,
            figure.visual_claim or figure.what_it_shows or figure.caption_original,
            [
                EvidenceRefRecord(
                    type="figure",
                    ref=figure.id,
                    claim_type="numeric" if figure.numeric_claim else "visual",
                )
            ],
            strength,
            "Derived from an explicit figure-level claim that can support paper framing.",
            None if strength == "medium" else "Visual evidence alone should not carry the main thesis.",
        )

    if len(assets) < 4:
        raise ValidationError("Extracted fewer than 4 candidate assets. The materials are too thin for journal-fit analysis.")

    return assets[:15]


def _map_assets_to_text(assets: list[AssetRecord], text: str, limit: int = 3) -> list[str]:
    target_tokens = _plain_tokens(text)
    scored: list[tuple[float, str]] = []
    for asset in assets:
        overlap = len(target_tokens & _plain_tokens(asset.content))
        if overlap == 0:
            continue
        scored.append((overlap + _strength_score(asset.strength) / 10.0, asset.id))
    scored.sort(reverse=True)
    return [asset_id for _, asset_id in scored[:limit]]


def _build_existing_narrative(materials: Any, assets: list[AssetRecord]) -> ExistingNarrativeRecord | None:
    abstract = materials.existing_drafts.current_abstract or ""
    intro = materials.existing_drafts.current_intro_p1 or ""
    thesis = _extract_sentences(abstract or intro, limit=1)
    if not thesis:
        return None
    bullets = _extract_sentences(abstract or intro, limit=3)
    contributions: list[CurrentContributionRecord] = []
    used_assets: set[str] = set()
    overclaimed: list[OverclaimedItemRecord] = []
    for bullet in bullets:
        mapped_assets = _map_assets_to_text(assets, bullet)
        used_assets.update(mapped_assets)
        strength = "weak"
        if mapped_assets:
            mapped_strengths = [_strength_score(next(item for item in assets if item.id == asset_id).strength) for asset_id in mapped_assets]
            strength = "strong" if max(mapped_strengths) >= 5 else "medium"
        else:
            overclaimed.append(OverclaimedItemRecord(claim=bullet, issue="No matching evidence-backed asset was found."))
        contributions.append(
            CurrentContributionRecord(
                bullet=bullet,
                mapped_assets=mapped_assets,
                evidence_strength=strength,  # type: ignore[arg-type]
            )
        )

    unused_strong_assets = [asset.id for asset in assets if asset.strength == "strong" and asset.id not in used_assets]
    structural_issues: list[str] = []
    if unused_strong_assets:
        structural_issues.append(f"Strong assets are currently underused: {', '.join(unused_strong_assets[:4])}.")
    if overclaimed:
        structural_issues.append("Some current claims overreach the evidence currently exposed in the draft.")
    if not structural_issues:
        structural_issues.append("The current framing is coherent, but alternative emphasis may still improve journal fit.")

    return ExistingNarrativeRecord(
        extracted_from="raw/draft.pdf",
        one_line_thesis=thesis[0],
        main_angle=_infer_angle(thesis[0]),
        current_contributions=contributions,
        unused_strong_assets=unused_strong_assets,
        overclaimed_items=overclaimed,
        structural_issues=structural_issues,
    )


def _top_assets_for_angle(assets: list[AssetRecord], angle: AngleType) -> list[AssetRecord]:
    category_map = {
        "method-novelty": {"methodology", "performance"},
        "application-driven": {"application", "performance"},
        "theoretical-insight": {"theory", "methodology"},
        "efficiency-focused": {"efficiency", "performance"},
        "unification": {"generality", "methodology"},
        "empirical-discovery": {"performance", "generality", "interpretability"},
        "systems-contribution": {"methodology", "application"},
    }
    wanted = category_map[angle]
    ranked = sorted(
        [asset for asset in assets if asset.category in wanted],
        key=lambda item: (_strength_score(item.strength), -int(item.id[1:])),
        reverse=True,
    )
    return ranked[:3]


def _candidate_reader(materials: Any, angle: AngleType) -> str:
    task = _task_label(materials)
    domain = _domain_label(materials, default="the target domain")
    if angle == "application-driven":
        return f"Researchers in {domain} who care about practical value on {task}"
    if angle == "efficiency-focused":
        return f"Readers who need deployable performance for {task}"
    if angle == "theoretical-insight":
        return f"Method-oriented readers looking for principled understanding in {domain}"
    return f"Editors and reviewers evaluating methodological contribution on {task}"


def _candidate_thesis(materials: Any, angle: AngleType, selected_assets: list[AssetRecord]) -> str:
    title = materials.identity.working_title
    task = _task_label(materials)
    lead = _display_text(selected_assets[0].content, max_words=16) if selected_assets else title
    if angle == "application-driven":
        return f"{title} should be framed as a task-grounded advance that makes {task} more actionable in practice."
    if angle == "efficiency-focused":
        return f"{title} is best positioned as a more efficient route to strong {task} performance without changing the core task setup."
    if angle == "unification":
        return f"{title} should be presented as a unifying framing that stabilizes performance across settings for {task}."
    if angle == "theoretical-insight":
        return f"{title} should emphasize the principled mechanism behind its gains rather than only the end metrics."
    if angle == "empirical-discovery":
        return f"{title} works as an evidence-first paper where the experimental pattern itself is the contribution."
    if angle == "systems-contribution":
        return f"{title} is strongest when positioned as a workflow-level contribution that reorganizes how {task} is solved."
    return f"{title} should foreground {lead} as the key methodological advance behind the paper's contribution."


def _build_candidate_record(
    candidate_id: str,
    materials: Any,
    angle: AngleType,
    all_assets: list[AssetRecord],
    selected_assets: list[AssetRecord],
) -> NarrativeCandidateRecord:
    strongest = max(selected_assets, key=lambda item: _strength_score(item.strength))
    primary_support = selected_assets[: min(3, len(selected_assets))]
    main_claims = [
        NarrativeClaimRecord(
            claim=_summarize_text(primary_support[0].content, max_segments=2, max_words=24),
            supporting_assets=[asset.id for asset in primary_support[:2]],
            evidence_strength=_strongest_strength(primary_support[:2]),  # type: ignore[arg-type]
        )
    ]
    if len(primary_support) > 1:
        main_claims.append(
            NarrativeClaimRecord(
                claim=_summarize_text(primary_support[1].content, max_segments=2, max_words=24),
                supporting_assets=[asset.id for asset in primary_support[1:3]],
                evidence_strength=_strongest_strength(primary_support[1:3]),  # type: ignore[arg-type]
            )
        )
    return NarrativeCandidateRecord(
        id=candidate_id,
        one_line_thesis=_candidate_thesis(materials, angle, selected_assets),
        main_angle=angle,
        target_reader=_candidate_reader(materials, angle),
        main_claims=main_claims,
        assets_to_foreground=[asset.id for asset in primary_support],
        assets_to_background=[asset.id for asset in all_assets if asset.id not in {item.id for item in primary_support}][:2],
        implicit_assumptions=[
            "The target journal values evidence-backed framing more than maximal novelty language.",
            "The abstract and figure order can be changed without touching the core algorithm.",
        ],
        biggest_risk=strongest.caveats or "Reviewers may ask whether the framing overstates breadth relative to current evidence.",
        required_framing_moves=[
            "Open the introduction with the problem pressure that the strongest experiment actually supports.",
            "Align the first figure and first main result with the narrative's main claim.",
        ],
    )


def _dedupe_candidates(candidates: list[NarrativeCandidateRecord], existing: ExistingNarrativeRecord | None) -> list[NarrativeCandidateRecord]:
    deduped: list[NarrativeCandidateRecord] = []
    seen: list[set[str]] = []
    existing_tokens = _plain_tokens(existing.one_line_thesis) if existing else set()
    for candidate in candidates:
        tokens = _plain_tokens(candidate.one_line_thesis)
        if existing and (candidate.main_angle == existing.main_angle or len(tokens & existing_tokens) >= max(5, int(len(existing_tokens) * 0.5))):
            continue
        if any(len(tokens & other) >= max(5, int(max(len(tokens), len(other)) * 0.5)) for other in seen):
            continue
        deduped.append(candidate)
        seen.append(tokens)
    return deduped[:6]


def _build_candidates(materials: Any, assets: list[AssetRecord], existing: ExistingNarrativeRecord | None) -> list[NarrativeCandidateRecord]:
    candidates: list[NarrativeCandidateRecord] = []
    for index, angle in enumerate(ANGLE_PRIORITY, start=1):
        selected_assets = _top_assets_for_angle(assets, angle)
        if not selected_assets:
            continue
        candidates.append(_build_candidate_record(f"N{index}", materials, angle, assets, selected_assets))
    deduped = _dedupe_candidates(candidates, existing)
    renumbered: list[NarrativeCandidateRecord] = []
    for index, candidate in enumerate(deduped[:6], start=1):
        renumbered.append(candidate.model_copy(update={"id": f"N{index}"}))
    return renumbered


def _normalize_reference_papers(payloads: list[dict[str, Any]], query_terms: set[str]) -> list[ReferencePaperRecord]:
    seen: set[tuple[str, int | None]] = set()
    records: list[ReferencePaperRecord] = []
    sorted_payloads = sorted(
        payloads,
        key=lambda item: ((item.get("citationCount") or 0), (item.get("year") or 0)),
        reverse=True,
    )
    for item in sorted_payloads:
        key = (normalize_text(item.get("title") or ""), item.get("year"))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        abstract = normalize_text(item.get("abstract") or "")
        relevance = "medium"
        if len(_plain_tokens(f"{item.get('title', '')} {abstract}") & query_terms) >= 4:
            relevance = "high"
        records.append(
            ReferencePaperRecord(
                title=item.get("title") or "Untitled",
                year=item.get("year"),
                venue=item.get("venue"),
                citation_count=item.get("citationCount"),
                doi=((item.get("externalIds") or {}).get("DOI") if isinstance(item.get("externalIds"), dict) else None),
                url=item.get("url"),
                abstract=abstract or None,
                relevance_to_user=relevance,  # type: ignore[arg-type]
                source="semantic_scholar",
            )
        )
    return records[:12]


def _contribution_weights(reference_papers: list[ReferencePaperRecord], query_terms: set[str]) -> list[ContributionTypeWeightRecord]:
    counts = {angle: 1.0 for angle in ANGLE_PRIORITY}
    for paper in reference_papers:
        combined = f"{paper.title} {paper.abstract or ''}"
        angle = _infer_angle(combined)
        counts[angle] += 1.0
        if len(_plain_tokens(combined) & query_terms) >= 4:
            counts[angle] += 0.5
    total = sum(counts.values()) or 1.0
    return [
        ContributionTypeWeightRecord(type=angle, weight=round(count / total, 4))
        for angle, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]


def _style_from_reference_papers(reference_papers: list[ReferencePaperRecord]) -> WritingStyleRecord:
    if not reference_papers:
        return WritingStyleRecord()
    abstract_lengths = [len((paper.abstract or "").split()) for paper in reference_papers if paper.abstract]
    avg_length = _safe_average([float(length) for length in abstract_lengths]) if abstract_lengths else 140.0
    jargon_ratio = _safe_average(
        [
            len([token for token in _plain_tokens((paper.abstract or "") + " " + paper.title) if len(token) > 8]) / max(1, len(_plain_tokens((paper.abstract or "") + " " + paper.title)))
            for paper in reference_papers
            if (paper.abstract or paper.title)
        ]
    )
    length = "compact" if avg_length < 130 else "expansive" if avg_length > 190 else "standard"
    jargon_density = "high" if jargon_ratio > 0.35 else "low" if jargon_ratio < 0.18 else "medium"
    return WritingStyleRecord(length=length, tone="formal", jargon_density=jargon_density)


def _top_keywords_from_papers(reference_papers: list[ReferencePaperRecord], excluded: set[str], limit: int = 5) -> list[str]:
    counts: dict[str, int] = {}
    for paper in reference_papers:
        for token in _plain_tokens(f"{paper.title} {paper.abstract or ''}"):
            if token in excluded or len(token) < 5:
                continue
            counts[token] = counts.get(token, 0) + 1
    return [token for token, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def _search_duckduckgo(query: str, timeout: float = 10.0) -> list[dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote(query)}"
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"user-agent": "AutoScholar/2.0"})
        response.raise_for_status()
    except Exception:
        return []
    html = response.text
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.S,
    )
    results: list[dict[str, str]] = []
    for match in pattern.finditer(html):
        title = re.sub(r"<.*?>", "", match.group("title"))
        snippet = re.sub(r"<.*?>", "", match.group("snippet"))
        results.append(
            {
                "url": normalize_text(match.group("url")),
                "title": normalize_text(title),
                "snippet": normalize_text(snippet),
            }
        )
        if len(results) >= 3:
            break
    return results


def _build_journal_profile(materials: Any, journal: TargetJournalRecord, use_cache: bool, workspace: JournalFitWorkspace) -> JournalProfileRecord:
    slug = slugify(journal.journal_name) or "journal"
    path = workspace.journal_profile_path(slug)
    now = datetime.now(timezone.utc)
    if use_cache and path.exists():
        cached = JournalProfileRecord.model_validate(read_json(path))
        cached_at = datetime.fromisoformat(cached.cached_at)
        if now - cached_at < timedelta(days=cached.cache_ttl_days):
            return cached

    query_seed = " ".join(
        filter(
            None,
            [
                materials.identity.task or "",
                materials.identity.domain or "",
                materials.identity.working_title,
            ],
        )
    )
    query_terms = _plain_tokens(query_seed)
    semantic_source = SourceFetchRecord(fetched=False, reason="No Semantic Scholar results.")
    payloads: list[dict[str, Any]] = []
    try:
        with SemanticScholarClient(timeout=20.0) as client:
            payloads = list(
                client.search_papers_bulk(
                    query=query_seed or journal.journal_name,
                    fields="title,abstract,year,authors,url,venue,citationCount,externalIds",
                    max_results=20,
                    venue=journal.journal_name,
                    timeout=20.0,
                )
            )
            if not payloads:
                fallback = client.search_papers(
                    query=f"{journal.journal_name} {query_seed}".strip(),
                    limit=10,
                    fields="title,abstract,year,authors,url,venue,citationCount,externalIds",
                    timeout=20.0,
                )
                payloads = fallback.get("data", [])
            if payloads:
                semantic_source = SourceFetchRecord(fetched=True, paper_count=len(payloads))
    except Exception as exc:
        semantic_source = SourceFetchRecord(fetched=False, reason=str(exc))

    current_year = now.year
    recent_payloads = [item for item in payloads if item.get("year") in {current_year, current_year - 1, current_year - 2}]
    reference_papers = _normalize_reference_papers(recent_payloads or payloads, query_terms)
    venue_normalized = next((paper.venue for paper in reference_papers if paper.venue), journal.journal_name)

    scope_results = _search_duckduckgo(f'"{journal.journal_name}" aims and scope')
    guidelines_results = _search_duckduckgo(f'"{journal.journal_name}" author guidelines')
    editorial_results = _search_duckduckgo(f'"{journal.journal_name}" editorial')

    web_scope = (
        SourceFetchRecord(fetched=True, url=scope_results[0]["url"])
        if scope_results
        else SourceFetchRecord(fetched=False, reason="scope search returned no results")
    )
    web_guidelines = (
        SourceFetchRecord(fetched=True, url=guidelines_results[0]["url"])
        if guidelines_results
        else SourceFetchRecord(fetched=False, reason="guidelines search returned no results")
    )
    web_editorials = (
        SourceFetchRecord(fetched=True, url=editorial_results[0]["url"])
        if editorial_results
        else SourceFetchRecord(fetched=False, reason="editorial search returned no results")
    )

    aims_scope_summary = ""
    if scope_results:
        aims_scope_summary = scope_results[0]["snippet"]
    elif reference_papers:
        top_titles = "; ".join(paper.title for paper in reference_papers[:3])
        aims_scope_summary = f"Recent accepted papers cluster around the following themes: {top_titles}."
    preferred_types = _contribution_weights(reference_papers, query_terms)
    preferred_patterns = ["problem-first", "evidence-first"]
    if any(weight.type == "application-driven" and weight.weight >= 0.18 for weight in preferred_types[:3]):
        preferred_patterns.append("application-first")
    typical_structure = ["Introduction", "Related Work", "Method", "Experiments", "Discussion", "Conclusion"]
    rising_subtopics = _top_keywords_from_papers(reference_papers, query_terms)
    reviewer_red_flags = [
        "缺少与主张直接对齐的核心实验定位",
        "贡献叙事大于当前证据实际支撑强度",
        "主图与摘要主 claim 没有形成第一时间共振",
    ]
    if any(weight.type == "application-driven" for weight in preferred_types[:2]):
        reviewer_red_flags.insert(0, "缺少真实应用场景或实用价值的清晰落点")
    if any(weight.type == "theoretical-insight" for weight in preferred_types[:2]):
        reviewer_red_flags.insert(0, "理论动机与实验现象之间缺少闭环")

    confidence = "high"
    if not reference_papers or len(reference_papers) < 5:
        confidence = "medium"
    if not semantic_source.fetched and not web_scope.fetched:
        confidence = "low"

    profile = JournalProfileRecord(
        journal_name=journal.journal_name,
        venue_normalized=venue_normalized,
        slug=slug,
        cached_at=utc_now(),
        cache_ttl_days=14,
        sources={
            "semantic_scholar": semantic_source.model_dump(mode="json"),
            "web_scope": web_scope.model_dump(mode="json"),
            "web_guidelines": web_guidelines.model_dump(mode="json"),
            "web_editorials": web_editorials.model_dump(mode="json"),
        },
        aims_scope_summary=aims_scope_summary,
        preferred_contribution_types=preferred_types,
        preferred_narrative_patterns=list(dict.fromkeys(preferred_patterns)),
        writing_style=_style_from_reference_papers(reference_papers),
        typical_structure=typical_structure,
        rising_subtopics=rising_subtopics,
        reviewer_red_flags=list(dict.fromkeys(reviewer_red_flags))[:5],
        reference_papers=reference_papers,
        confidence=confidence,  # type: ignore[arg-type]
    )
    write_json(path, profile.model_dump(mode="json"))
    return profile


def _load_narratives(workspace: JournalFitWorkspace) -> list[NarrativeCandidateRecord]:
    paths = sorted(workspace.narratives_dir.glob("candidate_*.json"))
    return [NarrativeCandidateRecord.model_validate(read_json(path)) for path in paths]


def _build_baseline_candidate(existing: ExistingNarrativeRecord) -> NarrativeCandidateRecord:
    return NarrativeCandidateRecord(
        id="N0",
        one_line_thesis=existing.one_line_thesis,
        main_angle=existing.main_angle,
        target_reader="Current draft readers",
        main_claims=[
            NarrativeClaimRecord(
                claim=item.bullet,
                supporting_assets=item.mapped_assets,
                evidence_strength=item.evidence_strength,
            )
            for item in existing.current_contributions
        ],
        assets_to_foreground=[asset_id for item in existing.current_contributions for asset_id in item.mapped_assets][:3],
        assets_to_background=existing.unused_strong_assets[:2],
        implicit_assumptions=["The current framing can already satisfy the journal with limited surgery."],
        biggest_risk=existing.structural_issues[0] if existing.structural_issues else "Current framing may leave strong assets unused.",
        required_framing_moves=["Keep the current thesis but tighten evidence alignment."],
    )


def _angle_weight(profile: JournalProfileRecord, angle: AngleType) -> float:
    for item in profile.preferred_contribution_types:
        if item.type == angle:
            return item.weight
    return 0.05


def _differentiation_score(candidate: NarrativeCandidateRecord, profile: JournalProfileRecord) -> int:
    candidate_tokens = _plain_tokens(candidate.one_line_thesis)
    overlaps: list[float] = []
    for paper in profile.reference_papers:
        paper_tokens = _plain_tokens(f"{paper.title} {paper.abstract or ''}")
        if not paper_tokens:
            continue
        overlaps.append(len(candidate_tokens & paper_tokens) / max(1, len(candidate_tokens | paper_tokens)))
    if not overlaps:
        return 3
    average_overlap = _safe_average(overlaps)
    return 5 if average_overlap < 0.12 else 4 if average_overlap < 0.18 else 3 if average_overlap < 0.24 else 2


def _score_candidate(candidate: NarrativeCandidateRecord, profile: JournalProfileRecord) -> FitMatrixEntryRecord:
    taste_fit = _clamp_score(1.5 + _angle_weight(profile, candidate.main_angle) * 10.0)
    evidence_support = _clamp_score(_safe_average([float(_strength_score(item.evidence_strength)) for item in candidate.main_claims]) or 2.0)
    differentiation = _differentiation_score(candidate, profile)
    risk = _clamp_score((taste_fit + evidence_support) / 2.0 - (1 if "risk" in candidate.biggest_risk.lower() else 0))
    weighted_total = round(
        taste_fit * DEFAULT_SCORE_WEIGHTS["taste_fit"]
        + evidence_support * DEFAULT_SCORE_WEIGHTS["evidence_support"]
        + differentiation * DEFAULT_SCORE_WEIGHTS["differentiation"]
        + risk * DEFAULT_SCORE_WEIGHTS["risk"],
        2,
    )
    expectation = "high" if weighted_total >= 4.3 else "medium-high" if weighted_total >= 3.7 else "medium" if weighted_total >= 3.0 else "low"
    rationale = (
        f"Angle {candidate.main_angle} matches the journal's preference with evidence score {evidence_support}/5 "
        f"and differentiation {differentiation}/5."
    )
    return FitMatrixEntryRecord(
        narrative_id=candidate.id,
        journal_slug=profile.slug,
        scores=FitScoresRecord(
            taste_fit=taste_fit,
            evidence_support=evidence_support,
            differentiation=differentiation,
            risk=risk,
        ),
        weighted_total=weighted_total,
        one_line_rationale=rationale,
        acceptance_expectation=expectation,  # type: ignore[arg-type]
    )


def _select_top_combinations(entries: list[FitMatrixEntryRecord]) -> list[TopCombinationRecord]:
    ordered = sorted(entries, key=lambda item: (item.weighted_total, item.scores.evidence_support, item.scores.taste_fit), reverse=True)
    return [
        TopCombinationRecord(narrative_id=item.narrative_id, journal_slug=item.journal_slug, rank=index)
        for index, item in enumerate(ordered[:2], start=1)
    ]


def _load_profiles(workspace: JournalFitWorkspace) -> list[JournalProfileRecord]:
    return [JournalProfileRecord.model_validate(read_json(path)) for path in sorted(workspace.journals_dir.glob("*.json")) if not path.name.startswith("_")]


def _load_assets(workspace: JournalFitWorkspace) -> AssetInventoryRecord:
    return AssetInventoryRecord.model_validate(read_json(workspace.assets_path))


def _load_existing_narrative(workspace: JournalFitWorkspace) -> ExistingNarrativeRecord | None:
    if not workspace.existing_narrative_path.exists():
        return None
    return ExistingNarrativeRecord.model_validate(read_json(workspace.existing_narrative_path))


def _load_run_meta(workspace: JournalFitWorkspace) -> RunMetaRecord:
    return RunMetaRecord.model_validate(read_json(workspace.run_meta_path))


def _title_candidates(materials: Any, candidate: NarrativeCandidateRecord) -> list[str]:
    angle_label = candidate.main_angle.replace("-", " ")
    base = materials.identity.working_title
    return [
        f"{base}: A {angle_label.title()} Framing",
        f"{base}: An Evidence-Led {angle_label.title()} Story",
        f"{base}: Repositioning the Paper Through {angle_label.title()} Emphasis",
    ]


def _extract_main_experiment(materials: Any, candidate: NarrativeCandidateRecord, assets: list[AssetRecord]) -> str:
    supporting_ids = {asset_id for claim in candidate.main_claims for asset_id in claim.supporting_assets}
    for asset in assets:
        if asset.id not in supporting_ids:
            continue
        for ref in asset.evidence_refs:
            if ref.type == "experiment":
                return ref.ref
    return materials.experiments[0].experiment_id if materials.experiments else "Exp-1"


def _build_abstract(materials: Any, candidate: NarrativeCandidateRecord, journal: JournalProfileRecord) -> str:
    task = _task_label(materials, max_words=10)
    domain = _domain_label(materials, max_words=6)
    title = materials.identity.working_title
    main_claim = _summarize_text(
        candidate.main_claims[0].claim if candidate.main_claims else candidate.one_line_thesis,
        max_segments=2,
        max_words=26,
    ).rstrip(".")
    support = _summarize_text(
        candidate.main_claims[1].claim if len(candidate.main_claims) > 1 else candidate.one_line_thesis,
        max_segments=2,
        max_words=24,
    ).rstrip(".")
    framing = candidate.main_angle.replace("-", " ")
    sentences = [
        f"{task.capitalize()} remains difficult in {domain} when the paper narrative does not immediately expose which evidence should matter most to reviewers.",
        f"We present {title} and frame it explicitly as a {framing} contribution for {journal.journal_name}, rather than as a generic method paper.",
        f"Our central thesis is that {main_claim.lower()}.",
        f"This position is reinforced by a second evidence line: {support.lower()}.",
        "The abstract should therefore foreground the experiment, figure, and contribution order that make this evidence path legible from the first paragraph.",
        "This version preserves the fixed algorithm and experiment set, but narrows unsupported novelty language so the opening claim, the lead result, and the paper structure all point in the same direction.",
    ]
    abstract = " ".join(sentences)
    while len(abstract.split()) < 140:
        abstract += (
            " In practice, that means leading with the most defensible evidence bundle, naming the decision pressure early, and making every contribution bullet traceable to an explicit asset-level support point."
        )
    return abstract


def _figure_action(figure: Any, candidate: NarrativeCandidateRecord) -> tuple[str, str]:
    figure_tokens = _plain_tokens(" ".join(filter(None, [figure.what_it_shows, figure.visual_claim, figure.numeric_claim or "", figure.caption_original])))
    candidate_tokens = _plain_tokens(candidate.one_line_thesis)
    overlap = len(figure_tokens & candidate_tokens)
    if overlap >= 4:
        return "keep", figure.caption_original or figure.what_it_shows
    if overlap >= 2:
        return "recaption", f"{figure.caption_original or figure.what_it_shows}. Recast to foreground {candidate.main_angle.replace('-', ' ')}."
    return "redraw", f"Redraw to make the first visible message support: {candidate.one_line_thesis}"


def _build_skeleton_markdown(
    materials: Any,
    candidate: NarrativeCandidateRecord,
    journal: JournalProfileRecord,
    assets: list[AssetRecord],
    figures_manifest: FiguresManifestRecord,
    existing: ExistingNarrativeRecord | None,
) -> str:
    titles = _title_candidates(materials, candidate)
    main_experiment = _extract_main_experiment(materials, candidate, assets)
    contribution_lines = _build_contribution_lines(candidate, assets)
    related_lines = _group_related_work(journal, candidate)

    figure_lines = []
    for index, figure in enumerate(figures_manifest.figures, start=1):
        action, new_caption = _figure_action(figure, candidate)
        position = f"Fig {index}" if index <= 3 else "Appendix"
        figure_lines.append(f"- {figure.id}: {position}, {action}, caption: {new_caption}")

    diff_lines: list[str] = []
    if existing:
        diff_lines = [
            f"- Existing thesis: {existing.one_line_thesis}",
            f"- New thesis: {candidate.one_line_thesis}",
            "- 最小改动版: 只改 Abstract 首段、Contribution bullets、Fig 1 caption。",
            "- 完整改造版: 重排 Intro 开篇问题、主实验顺序与图表位置。",
        ]

    return "\n".join(
        [
            f"# Skeleton for {candidate.id} x {journal.journal_name}",
            "",
            "## Title Candidates",
            *[f"- [{candidate.main_angle}] {title}" for title in titles],
            "",
            "## Abstract",
            _build_abstract(materials, candidate, journal),
            "",
            "## Introduction Skeleton",
            f"1. <intent>Define the decision pressure in {_task_label(materials)} and the failure of generic framing.</intent> [supports: thesis]",
            f"2. <intent>Introduce {materials.identity.working_title} as a constrained, evidence-backed response.</intent> [supports: {candidate.assets_to_foreground[0] if candidate.assets_to_foreground else 'A01'}]",
            f"3. <intent>Preview the strongest empirical support and why it fits {journal.journal_name}.</intent> [supports: {main_experiment}]",
            "4. <intent>State the contribution bullets in evidence-first order rather than pipeline order.</intent> [supports: contributions]",
            "",
            "## Contribution Bullets",
            *contribution_lines,
            "",
            "## Related Work Strategy",
            *related_lines,
            "",
            "## Experiment Arrangement",
            f"- Main experiment: {main_experiment}",
            "- Body text: keep experiments that directly defend the thesis in the main paper.",
            "- Appendix: move supporting but non-critical ablations or secondary analyses.",
            "- Rationale: the order should follow reviewer proof burden, not chronological experiment order.",
            "",
            "## Figure Strategy",
            *(figure_lines or ["- No standalone figures were provided."]),
            "",
            "## Discussion / Future Work",
            f"- Close by discussing how the framing can extend once additional low-cost evidence is added around {candidate.biggest_risk.lower().rstrip('.')}.",
            "",
            "## Diff View" if diff_lines else "",
            *diff_lines,
            "",
        ]
    ).strip() + "\n"


def _patch_type_for_concern(concern: str) -> str:
    lowered = concern.lower()
    if any(token in lowered for token in ("figure", "visual", "caption")):
        return "new-figure"
    if any(token in lowered for token in ("analysis", "error", "robust", "distribution")):
        return "new-analysis"
    if any(token in lowered for token in ("ablation", "component")):
        return "new-ablation-snippet"
    if any(token in lowered for token in ("appendix", "proof")):
        return "appendix-note"
    return "rewording"


class JournalFitRunner:
    def __init__(self, workspace: JournalFitWorkspace):
        self.workspace = workspace.ensure_layout()

    def phase0(self, input_path: Path | None = None, draft_pdf: Path | None = None) -> RunMetaRecord:
        if input_path is not None:
            self.workspace.copy_input(input_path)
        if draft_pdf is not None:
            self.workspace.copy_draft_pdf(draft_pdf)

        mode: JournalFitMode = "draft_reframing" if self.workspace.draft_pdf_path.exists() else "from_scratch"
        if mode == "draft_reframing":
            override_materials = None
            if self.workspace.input_path.exists():
                override_materials = parse_materials_markdown(
                    read_text(self.workspace.input_path),
                    self.workspace.paper_id,
                    "from_scratch",
                )
            materials, notes = extract_materials_from_pdf(
                self.workspace.draft_pdf_path,
                self.workspace.paper_id,
                target_journals=override_materials.target_journals if override_materials else None,
            )
            if override_materials is not None:
                materials = _merge_materials(materials, override_materials)
            write_text(self.workspace.input_path, render_materials_markdown(materials, auto_extracted=True))
        else:
            if not self.workspace.input_path.exists():
                raise ValidationError(f"Input file not found: {self.workspace.input_path}")
            materials = load_materials_from_workspace(self.workspace, "from_scratch")
            notes = []

        issues = validate_materials(materials)
        if issues:
            raise ValidationError("Phase 0 validation failed: " + "; ".join(issues))

        figures_manifest = load_or_build_figures_manifest(self.workspace)
        write_json(self.workspace.figures_manifest_path, figures_manifest.model_dump(mode="json"))

        extraction_confidence = "high"
        if notes:
            extraction_confidence = "medium" if len(notes) <= 2 else "low"
        run_meta = RunMetaRecord(
            paper_id=self.workspace.paper_id,
            mode=mode,
            created_at=utc_now(),
            source=RunSourceRecord(
                has_pdf=self.workspace.draft_pdf_path.exists(),
                pdf_path="raw/draft.pdf" if self.workspace.draft_pdf_path.exists() else None,
                figures_count=len(figures_manifest.figures),
                extraction_confidence=extraction_confidence,  # type: ignore[arg-type]
                low_confidence_fields=notes,
            ),
            target_journals=[item.journal_name for item in materials.target_journals],
            target_journals_normalized=[item.journal_name for item in materials.target_journals],
        )
        write_json(self.workspace.run_meta_path, run_meta.model_dump(mode="json"))
        return run_meta

    def phase1(self) -> AssetInventoryRecord:
        run_meta = _load_run_meta(self.workspace)
        materials = load_materials_from_workspace(self.workspace, run_meta.mode)
        figures_manifest = load_or_build_figures_manifest(self.workspace)
        assets = _build_assets(materials, figures_manifest)
        inventory = AssetInventoryRecord(
            paper_id=self.workspace.paper_id,
            generated_at=utc_now(),
            assets=assets,
        )
        write_json(self.workspace.assets_path, inventory.model_dump(mode="json"))
        if run_meta.mode == "draft_reframing":
            existing = _build_existing_narrative(materials, assets)
            if existing is not None:
                write_json(self.workspace.existing_narrative_path, existing.model_dump(mode="json"))
        return inventory

    def phase2(self, journal_name: str | None = None, use_cache: bool = True) -> list[JournalProfileRecord]:
        run_meta = _load_run_meta(self.workspace)
        materials = load_materials_from_workspace(self.workspace, run_meta.mode)
        profiles: list[JournalProfileRecord] = []
        selected = [item for item in materials.target_journals if journal_name is None or item.journal_name == journal_name]
        for journal in selected:
            profiles.append(_build_journal_profile(materials, journal, use_cache=use_cache, workspace=self.workspace))
        return profiles

    def phase3(self) -> list[NarrativeCandidateRecord]:
        inventory = _load_assets(self.workspace)
        run_meta = _load_run_meta(self.workspace)
        materials = load_materials_from_workspace(self.workspace, run_meta.mode)
        existing = _load_existing_narrative(self.workspace)
        narratives = _build_candidates(materials, inventory.assets, existing)
        for stale in self.workspace.narratives_dir.glob("candidate_*.json"):
            stale.unlink()
        for index, narrative in enumerate(narratives, start=1):
            write_json(self.workspace.narrative_path(index), narrative.model_dump(mode="json"))
        return narratives

    def phase4(self) -> FitMatrixRecord:
        narratives = _load_narratives(self.workspace)
        profiles = _load_profiles(self.workspace)
        existing = _load_existing_narrative(self.workspace)
        if existing is not None:
            narratives = [_build_baseline_candidate(existing), *narratives]
        if not narratives:
            raise ValidationError("Phase 4 requires narrative candidates. Run phase3 first.")
        if not profiles:
            raise ValidationError("Phase 4 requires journal profiles. Run phase2 first.")

        entries = [_score_candidate(candidate, profile) for candidate in narratives for profile in profiles]
        matrix = FitMatrixRecord(matrix=entries, top_combinations=_select_top_combinations(entries))
        write_json(self.workspace.fit_matrix_path, matrix.model_dump(mode="json"))
        return matrix

    def phase5(self) -> list[Path]:
        run_meta = _load_run_meta(self.workspace)
        materials = load_materials_from_workspace(self.workspace, run_meta.mode)
        assets = _load_assets(self.workspace).assets
        figures_manifest = load_or_build_figures_manifest(self.workspace)
        existing = _load_existing_narrative(self.workspace)
        matrix = FitMatrixRecord.model_validate(read_json(self.workspace.fit_matrix_path))
        narrative_map = {item.id: item for item in _load_narratives(self.workspace)}
        if existing is not None:
            narrative_map["N0"] = _build_baseline_candidate(existing)
        profile_map = {item.slug: item for item in _load_profiles(self.workspace)}

        written: list[Path] = []
        for stale in self.workspace.skeletons_dir.glob("skeleton_*.md"):
            stale.unlink()
        for combination in matrix.top_combinations[:2]:
            candidate = narrative_map[combination.narrative_id]
            profile = profile_map[combination.journal_slug]
            content = _build_skeleton_markdown(materials, candidate, profile, assets, figures_manifest, existing)
            path = self.workspace.skeleton_path(candidate.id, profile.slug)
            write_text(path, content)
            written.append(path)
        return written

    def phase6(self) -> tuple[AdversarialReviewRecord, PatchListRecord]:
        matrix = FitMatrixRecord.model_validate(read_json(self.workspace.fit_matrix_path))
        narrative_map = {item.id: item for item in _load_narratives(self.workspace)}
        existing = _load_existing_narrative(self.workspace)
        if existing is not None:
            narrative_map["N0"] = _build_baseline_candidate(existing)
        profile_map = {item.slug: item for item in _load_profiles(self.workspace)}
        reviews: list[ReviewTargetRecord] = []
        patches: list[PatchRecord] = []
        entry_map = {(item.narrative_id, item.journal_slug): item for item in matrix.matrix}
        for combination in matrix.top_combinations[:2]:
            candidate = narrative_map[combination.narrative_id]
            profile = profile_map[combination.journal_slug]
            entry = entry_map[(combination.narrative_id, combination.journal_slug)]
            concerns = list(profile.reviewer_red_flags[:3])
            concerns.append(candidate.biggest_risk)
            concerns = list(dict.fromkeys([item for item in concerns if item]))[:5]
            questions: list[ReviewQuestionRecord] = []
            for index, concern in enumerate(concerns, start=1):
                severity = "high" if index == 1 or entry.scores.evidence_support <= 3 else "medium"
                if "unused" in concern.lower():
                    severity = "medium"
                addressable, patch_type, cost, description = _review_resolution(concern)
                question = ReviewQuestionRecord(
                    qid=f"Q{index}",
                    concern=concern,
                    severity=severity,  # type: ignore[arg-type]
                    addressable_by_existing_data=addressable,  # type: ignore[arg-type]
                    patch_type=patch_type,  # type: ignore[arg-type]
                    patch_cost_hours=cost,
                    patch_description=description,
                )
                questions.append(question)
                if question.addressable_by_existing_data != "no" and question.patch_type != "none":
                    patches.append(
                        PatchRecord(
                            target_narrative=candidate.id,
                            target_journal=profile.slug,
                            qid=question.qid,
                            severity=question.severity,
                            patch_type=question.patch_type,
                            patch_cost_hours=question.patch_cost_hours,
                            patch_description=question.patch_description,
                        )
                    )
            reviews.append(ReviewTargetRecord(target_narrative=candidate.id, target_journal=profile.slug, questions=questions))
        review_bundle = AdversarialReviewRecord(reviews=reviews)
        deduped_patches: dict[tuple[str, str, str, str], PatchRecord] = {}
        for patch in patches:
            key = (patch.target_narrative, patch.target_journal, patch.patch_type, patch.patch_description)
            deduped_patches.setdefault(key, patch)
        patch_bundle = PatchListRecord(
            patches=sorted(deduped_patches.values(), key=lambda item: (item.patch_cost_hours, item.target_journal, item.qid))
        )
        write_json(self.workspace.adversarial_review_path, review_bundle.model_dump(mode="json"))
        write_json(self.workspace.patches_path, patch_bundle.model_dump(mode="json"))
        return review_bundle, patch_bundle

    def phase7(self) -> JournalFitRunSummary:
        matrix = FitMatrixRecord.model_validate(read_json(self.workspace.fit_matrix_path))
        profiles = {item.slug: item for item in _load_profiles(self.workspace)}
        narratives = {item.id: item for item in _load_narratives(self.workspace)}
        existing = _load_existing_narrative(self.workspace)
        if existing is not None:
            narratives["N0"] = _build_baseline_candidate(existing)
        assets = _load_assets(self.workspace)
        review_bundle = AdversarialReviewRecord.model_validate(read_json(self.workspace.adversarial_review_path))
        patch_bundle = PatchListRecord.model_validate(read_json(self.workspace.patches_path))

        top = matrix.top_combinations[0]
        primary_narrative = narratives[top.narrative_id]
        primary_journal = profiles[top.journal_slug]
        backup_narrative = narratives[matrix.top_combinations[1].narrative_id] if len(matrix.top_combinations) > 1 else None
        backup_journal = profiles[matrix.top_combinations[1].journal_slug] if len(matrix.top_combinations) > 1 else None
        warnings = _build_report_warnings(matrix, profiles, narratives)

        action_items = [
            f"重写摘要首段和 contribution bullets，使其对齐 `{primary_narrative.id}` 的 thesis。",
            f"按 `skeletons/skeleton_{primary_narrative.id}_{primary_journal.slug}.md` 调整引言和实验顺序。",
            "优先完成成本最低的 1-2 个补丁项，再决定是否进入完整改稿。",
        ]
        if patch_bundle.patches:
            action_items.append(f"优先处理 `{patch_bundle.patches[0].patch_type}`，预计 {patch_bundle.patches[0].patch_cost_hours} 小时。")

        asset_lines = [
            f"- {asset.id} [{asset.category}/{asset.strength}]: {asset.content}"
            for asset in assets.assets
        ]
        journal_lines = [
            f"- {profile.journal_name} (`confidence: {profile.confidence}`): {profile.aims_scope_summary}"
            for profile in profiles.values()
        ]
        narrative_lines = [
            f"- {narrative.id} [{narrative.main_angle}]: {narrative.one_line_thesis}"
            for narrative in narratives.values()
        ]
        matrix_lines = [
            f"- {entry.narrative_id} x {entry.journal_slug}: total={entry.weighted_total}, taste={entry.scores.taste_fit}, evidence={entry.scores.evidence_support}, differentiation={entry.scores.differentiation}, risk={entry.scores.risk}"
            for entry in sorted(matrix.matrix, key=lambda item: item.weighted_total, reverse=True)
        ]
        review_lines = [
            f"- {review.target_narrative} x {review.target_journal}: " + "; ".join(question.concern for question in review.questions[:3])
            for review in review_bundle.reviews
        ]
        patch_lines = [
            f"- {patch.target_narrative} x {patch.target_journal}: {patch.patch_type} ({patch.patch_cost_hours}h) - {patch.patch_description}"
            for patch in patch_bundle.patches[:5]
        ]
        decision_lines = [
            f"- 主推方案: {primary_narrative.id} x {primary_journal.journal_name}。理由: 证据支撑与期刊口味的综合分最高。",
            f"- 关键风险: {primary_narrative.biggest_risk}",
        ]
        if backup_narrative and backup_journal:
            decision_lines.append(
                f"- 备胎方案: {backup_narrative.id} x {backup_journal.journal_name}。若主推方案的前两项补丁无法在两周内完成，则切换。"
            )
        decision_lines.extend(f"- 两周动作: {item}" for item in action_items)

        report = "\n".join(
            [
                "# Journal Fit Advisor Report",
                "",
                "## 1. Asset Inventory",
                *asset_lines,
                "",
                "## 2. Journal Taste Profiles",
                *journal_lines,
                "",
                "## Warnings" if warnings else "",
                *[f"- {warning}" for warning in warnings],
                "" if warnings else "",
                "## 3. Narrative Candidates",
                *narrative_lines,
                "",
                "## 4. Fit Matrix",
                *matrix_lines,
                "",
                "## 5. Skeleton Outputs",
                *[
                    f"- {path.name}"
                    for path in sorted(self.workspace.skeletons_dir.glob("skeleton_*.md"))
                ],
                "",
                "## 6. Adversarial Review and Patch List",
                *review_lines,
                *patch_lines,
                "",
                "## 7. Final Recommendation",
                *decision_lines,
                "",
            ]
        )
        write_text(self.workspace.report_path, report)
        return JournalFitRunSummary(
            primary_narrative=primary_narrative.id,
            primary_journal=primary_journal.journal_name,
            primary_risk=primary_narrative.biggest_risk,
            backup_narrative=backup_narrative.id if backup_narrative else None,
            backup_journal=backup_journal.journal_name if backup_journal else None,
            action_items=action_items,
            warnings=warnings,
            report_path=self.workspace.report_path,
        )

    def run(self, input_path: Path | None = None, draft_pdf: Path | None = None, use_cache: bool = True) -> JournalFitRunSummary:
        self.phase0(input_path=input_path, draft_pdf=draft_pdf)
        self.phase1()
        self.phase2(use_cache=use_cache)
        self.phase3()
        self.phase4()
        self.phase5()
        self.phase6()
        return self.phase7()
