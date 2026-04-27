from __future__ import annotations

from autoscholar.citation.common import utc_now
from autoscholar.citation.config import IdeaEvaluationConfig
from autoscholar.io import read_json, read_json_model, read_jsonl, read_text, write_json
from autoscholar.models import (
    EvidenceClaimRecord,
    EvidenceMapRecord,
    EvidencePaperRecord,
    IdeaAssessmentRecord,
    ReportValidationBundleRecord,
    ReportValidationIssueRecord,
    ReportValidationRecord,
    SelectedCitationRecord,
    SelectedPaperRecord,
)
from autoscholar.workspace import Workspace


def _primary_source_text(workspace: Workspace) -> str:
    for input_name in ("idea_source", "manuscript"):
        path = workspace.path("inputs", input_name)
        if path is not None and path.exists():
            return read_text(path)
    return ""


def _short_claim_label(record: SelectedCitationRecord) -> str:
    return record.claim.short_label or record.claim.claim_text[:80]


def _claim_sort_score(record: EvidenceClaimRecord) -> tuple[int, int, int]:
    strength_rank = {"strong": 2, "mixed": 1, "weak": 0}[record.evidence_strength]
    status_rank = {"ready": 2, "review": 1, "weak": 0}[record.status]
    citation_rank = max((paper.citation_count or 0 for paper in record.top_papers), default=0)
    return strength_rank, status_rank, citation_rank


def _recommendation_phrase(language: str, recommendation: str) -> str:
    if language == "zh":
        mapping = {
            "recommended": "已经具备继续推进和写成论文主线的条件",
            "needs-revision": "值得继续推进，但需要先收窄定义并补齐关键证据",
            "not-ready": "目前还不足以直接写成稳定的论文主线",
        }
        return mapping[recommendation]
    mapping = {
        "recommended": "already looks viable as a paper direction",
        "needs-revision": "is promising but still needs narrowing and stronger evidence",
        "not-ready": "is not yet ready to anchor a paper direction",
    }
    return mapping[recommendation]


def _evidence_strength(record: SelectedCitationRecord) -> str:
    top_citations = max((paper.paper.citation_count or 0 for paper in record.selected_papers), default=0)
    if record.status == "ready" and (len(record.selected_papers) >= 2 or top_citations >= 40):
        return "strong"
    if record.status == "weak" or not record.selected_papers:
        return "weak"
    return "mixed"


def _support_tier(item: SelectedPaperRecord) -> str:
    claim_overlap = item.score_breakdown.title_claim_overlap + item.score_breakdown.abstract_claim_overlap
    query_overlap = item.score_breakdown.title_query_overlap + item.score_breakdown.abstract_query_overlap
    if claim_overlap >= 2 or query_overlap >= 4:
        return "direct"
    if claim_overlap >= 1 or query_overlap >= 2:
        return "adjacent"
    return "context"


def _paper_support_reason(language: str, claim_label: str, item: SelectedPaperRecord, support_tier: str) -> str:
    title = item.paper.title
    citation_count = item.paper.citation_count or 0
    if language == "zh":
        if support_tier == "direct":
            return (
                f"《{title}》与“{claim_label}”的表述最接近，且已有 {citation_count} 次引用，"
                "可以作为直接支撑或最靠近的对照文献。"
            )
        if support_tier == "adjacent":
            return (
                f"《{title}》更像邻域支撑文献，适合用来说明相关问题真实存在、"
                f"评价设置可行，当前引用数约为 {citation_count}。"
            )
        return (
            f"《{title}》提供的是背景性上下文，能帮助界定相关工作或风险，但不宜当作完全同题支撑，"
            f"当前引用数约为 {citation_count}。"
        )

    if support_tier == "direct":
        return (
            f'"{title}" is the closest direct support for "{claim_label}" and already has '
            f"{citation_count} citations."
        )
    if support_tier == "adjacent":
        return (
            f'"{title}" is better treated as adjacent evidence for "{claim_label}", '
            f"especially for motivation and evaluation framing; citations={citation_count}."
        )
    return (
        f'"{title}" is mainly contextual evidence for "{claim_label}" and should not be framed '
        f"as exact same-task prior art; citations={citation_count}."
    )


def _claim_notes(language: str, record: SelectedCitationRecord) -> list[str]:
    notes: list[str] = []
    if record.note:
        notes.append(record.note)

    review_statuses = sorted({review.status for review in record.query_reviews})
    if review_statuses:
        if language == "zh":
            notes.append(f"相关 query 状态包含: {', '.join(review_statuses)}。")
        else:
            notes.append(f"Observed query statuses: {', '.join(review_statuses)}.")
    return notes


def _claim_narrative(language: str, record: SelectedCitationRecord, evidence_strength: str) -> str:
    label = _short_claim_label(record)
    top_titles = [paper.paper.title for paper in record.selected_papers[:2]]
    if language == "zh":
        if evidence_strength == "strong":
            return (
                f"当前证据对“{label}”提供了较强支撑，最值得优先使用的文献是"
                f"{'、'.join(f'《{title}》' for title in top_titles)}。"
            )
        if evidence_strength == "mixed":
            return (
                f"当前证据能部分支撑“{label}”，但更像邻域拼接而不是成熟主线，"
                f"应重点核查 {'、'.join(f'《{title}》' for title in top_titles)} 的适配边界。"
            )
        return (
            f"“{label}”目前支撑偏弱，现有检索结果更适合作为动机或风险提示，"
            "不宜直接写成已被充分支持的主张。"
        )

    if evidence_strength == "strong":
        return (
            f'Current evidence strongly supports "{label}", with '
            f"{'; '.join(top_titles)} as the leading anchors."
        )
    if evidence_strength == "mixed":
        return (
            f'Current evidence only partially supports "{label}" and should be framed as an '
            "adjacent-evidence synthesis rather than a mature direct line."
        )
    return f'Evidence for "{label}" is currently weak and should not be presented as fully established.'


def _dedupe_reference_papers(claims: list[EvidenceClaimRecord], limit: int) -> list[EvidencePaperRecord]:
    seen: dict[str, EvidencePaperRecord] = {}
    for claim in claims:
        for paper in claim.top_papers:
            key = paper.doi or paper.paper_id or paper.title
            existing = seen.get(key)
            if existing is None or (paper.citation_count or 0) > (existing.citation_count or 0):
                seen[key] = paper
    return sorted(
        seen.values(),
        key=lambda item: ((item.citation_count or 0), item.title),
        reverse=True,
    )[:limit]


def build_evidence_map(workspace: Workspace, config: IdeaEvaluationConfig) -> EvidenceMapRecord:
    language = workspace.manifest.report_language
    assessment = read_json_model(workspace.require_path("artifacts", "idea_assessment"), IdeaAssessmentRecord)
    records = read_jsonl(workspace.require_path("artifacts", "selected_citations"), SelectedCitationRecord)
    source_text = _primary_source_text(workspace)

    claims: list[EvidenceClaimRecord] = []
    for record in records:
        claim_label = _short_claim_label(record)
        top_papers = [
            EvidencePaperRecord(
                paper_id=item.paper.paper_id,
                title=item.paper.title,
                year=item.paper.year,
                venue=item.paper.venue,
                citation_count=item.paper.citation_count,
                doi=item.paper.doi,
                url=item.paper.url,
                support_tier=_support_tier(item),  # type: ignore[arg-type]
                support_reason=_paper_support_reason(language, claim_label, item, _support_tier(item)),
            )
            for item in record.selected_papers[: config.report_top_papers_per_claim]
        ]
        evidence_strength = _evidence_strength(record)
        claims.append(
            EvidenceClaimRecord(
                claim_id=record.claim.claim_id,
                short_label=record.claim.short_label,
                claim_text=record.claim.claim_text,
                claim_type=record.claim.claim_type,
                priority=record.claim.priority,
                status=record.status,
                evidence_strength=evidence_strength,  # type: ignore[arg-type]
                narrative=_claim_narrative(language, record, evidence_strength),
                notes=_claim_notes(language, record),
                top_papers=top_papers,
            )
        )

    ordered_claims = sorted(claims, key=_claim_sort_score, reverse=True)
    strongest = [claim.claim_id for claim in ordered_claims[: config.report_claim_summary_limit]]
    weakest = [
        claim.claim_id
        for claim in sorted(claims, key=_claim_sort_score)[: config.report_claim_summary_limit]
        if claim.evidence_strength != "strong"
    ]
    reference_papers = _dedupe_reference_papers(claims, config.report_reference_limit)

    strongest_labels = [claim.short_label or claim.claim_id for claim in ordered_claims[:2]]
    weakest_labels = [claim.short_label or claim.claim_id for claim in ordered_claims[-2:] if claim.evidence_strength != "strong"]
    if language == "zh":
        executive_summary = (
            f"{assessment.summary} 基于当前证据，{assessment.title}{_recommendation_phrase(language, assessment.recommendation)}。"
        )
        if strongest_labels:
            executive_summary += f" 当前支撑相对最强的部分集中在 {', '.join(strongest_labels)}。"
        if weakest_labels:
            executive_summary += f" 目前最需要补证据或收窄表述的部分是 {', '.join(weakest_labels)}。"
    else:
        executive_summary = (
            f"{assessment.summary} Based on the current evidence bundle, {assessment.title} "
            f"{_recommendation_phrase(language, assessment.recommendation)}."
        )

    evidence_map = EvidenceMapRecord(
        idea_id=assessment.idea_id,
        title=assessment.title,
        language=language,  # type: ignore[arg-type]
        recommendation=assessment.recommendation,
        executive_summary=executive_summary,
        strongest_claim_ids=strongest,
        weakest_claim_ids=weakest,
        claims=claims,
        reference_papers=reference_papers,
        generated_at=utc_now(),
    )
    write_json(workspace.require_path("artifacts", "evidence_map"), evidence_map.model_dump(mode="json"))
    if source_text:
        del source_text
    return evidence_map


def _claim_lookup(evidence_map: EvidenceMapRecord) -> dict[str, EvidenceClaimRecord]:
    return {claim.claim_id: claim for claim in evidence_map.claims}


def _labels_for_claim_ids(evidence_map: EvidenceMapRecord, claim_ids: list[str]) -> list[str]:
    lookup = _claim_lookup(evidence_map)
    labels: list[str] = []
    for claim_id in claim_ids:
        claim = lookup.get(claim_id)
        if claim is not None:
            labels.append(claim.short_label or claim.claim_id)
    return labels


def build_feasibility_context(workspace: Workspace, config: IdeaEvaluationConfig) -> dict[str, object]:
    assessment = read_json_model(workspace.require_path("artifacts", "idea_assessment"), IdeaAssessmentRecord)
    evidence_map = build_evidence_map(workspace, config)
    language = workspace.manifest.report_language
    strongest_labels = _labels_for_claim_ids(evidence_map, evidence_map.strongest_claim_ids)
    weakest_labels = _labels_for_claim_ids(evidence_map, evidence_map.weakest_claim_ids)

    if language == "zh":
        support_story = []
        if strongest_labels:
            support_story.append(
                f"当前最有把握继续推进的是 {', '.join(strongest_labels)}，这些部分已经有可直接引用或可稳定借用的邻域文献支撑。"
            )
        if weakest_labels:
            support_story.append(
                f"当前最薄弱的是 {', '.join(weakest_labels)}。这意味着论文叙事应先收窄，不要把所有相邻问题都写成已经被同一批文献充分支撑。"
            )
        if not support_story:
            support_story.append("当前证据包规模较小，但没有发现结构性冲突，后续关键在于继续补强主张边界。")

        gaps = list(assessment.risks)
        if not gaps:
            gaps.append("当前没有检测到明显的结构性短板，但仍需人工复核 top papers 的适配边界。")

        framing_suggestions = [
            "优先把 strongest claims 写成论文主线，把 weak claims 降级为动机、风险或后续工作。",
            "把邻域文献写成 support surface，而不是写成已经存在成熟同题主线。",
            "在摘要、引言和贡献点里避免超过当前证据边界的宽泛表述。",
        ]
        if weakest_labels:
            framing_suggestions.append(f"对 {', '.join(weakest_labels)} 先补检索或重写 query，再决定是否保留为正式 claim。")

        return {
            "assessment": assessment,
            "evidence_map": evidence_map,
            "recommendation_summary": evidence_map.executive_summary,
            "support_story": support_story,
            "gaps": gaps,
            "framing_suggestions": framing_suggestions,
            "action_plan": assessment.next_actions,
        }

    support_story = []
    if strongest_labels:
        support_story.append(
            f"The strongest current support is concentrated around {', '.join(strongest_labels)}."
        )
    if weakest_labels:
        support_story.append(
            f"The weakest part remains {', '.join(weakest_labels)}, so the paper scope should narrow before publication framing."
        )
    if not support_story:
        support_story.append("The evidence bundle is still small, but no structural contradiction is visible yet.")

    return {
        "assessment": assessment,
        "evidence_map": evidence_map,
        "recommendation_summary": evidence_map.executive_summary,
        "support_story": support_story,
        "gaps": assessment.risks,
        "framing_suggestions": [
            "Anchor the paper around the strongest claims first.",
            "Treat adjacent papers as support surface, not exact same-task prior art.",
            "Avoid broader claims than the current evidence bundle can defend.",
        ],
        "action_plan": assessment.next_actions,
    }


def build_deep_dive_context(workspace: Workspace, config: IdeaEvaluationConfig) -> dict[str, object]:
    assessment = read_json_model(workspace.require_path("artifacts", "idea_assessment"), IdeaAssessmentRecord)
    evidence_map = build_evidence_map(workspace, config)
    language = workspace.manifest.report_language
    strongest_labels = _labels_for_claim_ids(evidence_map, evidence_map.strongest_claim_ids)
    weakest_labels = _labels_for_claim_ids(evidence_map, evidence_map.weakest_claim_ids)

    if language == "zh":
        one_page_conclusion = [
            evidence_map.executive_summary,
            "当前更适合把这个方向写成“问题定义清晰、证据边界明确、相邻文献可支撑”的工作，而不是假设已经存在成熟且密集的同题主线。"
            if weakest_labels
            else "当前证据已经足以支撑较稳定的论文叙事，下一步重点是把方法与实验协议收紧到 strongest claims 上。",
        ]
        framing_definition = [
            "先把 strongest claims 写成主问题定义或主贡献，再围绕它们组织 related work。",
            "明确指出哪些证据是 direct support，哪些只是 adjacent support，避免叙事越界。",
            "如果某些 claim 只有 mixed/weak support，应把它们降级为动机、风险或未来工作。",
        ]
        if weakest_labels:
            framing_definition.append(f"当前尤其需要对 {', '.join(weakest_labels)} 进行降级、重写或补证据。")

        method_guidance = [
            "方法部分必须显式 operationalize 最核心的 problem claim，而不是只在动机里提出它。",
            "优先做最小可解释改动，让每个模块都能回指到一条 claim 或一组证据。",
            "把 top papers 当作设计信号、baseline 或对照，而不是宣称它们已经解决了完全同一问题。",
        ]
        if strongest_labels:
            method_guidance.append(f"当前方法叙事建议围绕 {', '.join(strongest_labels)} 展开。")

        experiment_plan = [
            "至少设计一个实验直接验证 strongest claim，而不是只报告常规主指标。",
            "对 mixed/weak claims 单独安排 stress test、ablation 或 falsification-style 实验。",
            "比较对象优先选择 evidence map 中最靠前的 direct/adjacent papers。",
        ]
        if weakest_labels:
            experiment_plan.append(f"若 {', '.join(weakest_labels)} 仍要保留在论文里，就必须给出专门验证协议。")

        can_claim = [
            "当前方向具有继续推进价值，而且能被写成证据边界清楚的研究问题。",
            "相邻文献已经足以支撑问题动机、风险建模或评价协议设计。",
            "在收窄表述的前提下，可以把 strongest claims 作为论文主线。"
        ]
        avoid_claims = [
            "不要宣称已经存在成熟且密集的同题主线，除非 direct support 明显增多。",
            "不要把所有邻域证据都写成完全同任务 prior art。",
            "不要做“统一解决所有相邻问题”的宽泛主张。",
        ]

        risk_responses = []
        actions = assessment.next_actions or ["继续补证据并收窄问题定义。"]
        for index, risk in enumerate(assessment.risks or ["当前未发现额外结构性风险。"]):
            response = actions[min(index, len(actions) - 1)]
            risk_responses.append({"risk": risk, "response": response})

        return {
            "assessment": assessment,
            "evidence_map": evidence_map,
            "one_page_conclusion": one_page_conclusion,
            "framing_definition": framing_definition,
            "method_guidance": method_guidance,
            "experiment_plan": experiment_plan,
            "can_claim": can_claim,
            "avoid_claims": avoid_claims,
            "risk_responses": risk_responses,
        }

        return {
            "assessment": assessment,
            "evidence_map": evidence_map,
            "one_page_conclusion": [evidence_map.executive_summary],
        "framing_definition": [
            "Anchor the paper around the strongest claims first.",
            "Separate direct support from adjacent support explicitly.",
            "Downgrade weak claims into motivation, risk, or future work.",
        ],
        "method_guidance": [
            "Operationalize the strongest problem claim explicitly in the method section.",
            "Keep model changes narrow and defensible.",
            "Use top papers as design signals or baselines rather than exact same-task proof.",
        ],
        "experiment_plan": [
            "Add at least one experiment that directly validates the strongest claim.",
            "Use stress tests or ablations for weak claims.",
            "Compare against the most relevant direct or adjacent papers in the evidence map.",
        ],
        "can_claim": [
            "The direction is still viable with a narrower framing.",
            "Adjacent literature provides defendable motivation and evaluation grounding.",
        ],
        "avoid_claims": [
            "Avoid claiming a mature direct literature line when support is still mixed.",
            "Avoid presenting all adjacent work as exact same-task prior art.",
        ],
            "risk_responses": [
                {
                    "risk": risk,
                    "response": (assessment.next_actions or ["Keep narrowing the scope and strengthening evidence."])[
                        min(index, len((assessment.next_actions or ["Keep narrowing the scope and strengthening evidence."])) - 1)
                    ],
                }
                for index, risk in enumerate(assessment.risks)
            ],
        }


def _required_headings(kind: str, language: str) -> list[str]:
    if kind == "feasibility":
        if language == "zh":
            return [
                "## 1. 评估结论",
                "## 2. 为什么值得继续做",
                "## 3. 当前不足与风险",
                "## 4. 建议的收敛方向",
                "## 5. 关键证据摘要",
                "## 6. 下一步建议",
            ]
        return [
            "## 1. Recommendation",
            "## 2. Why It Is Still Worth Pursuing",
            "## 3. Gaps And Risks",
            "## 4. Recommended Narrowing",
            "## 5. Key Evidence Digest",
            "## 6. Next Actions",
        ]

    if language == "zh":
        return [
            "## 1. 一页结论",
            "## 2. 证据全景",
            "## 3. 推荐的问题定义与边界",
            "## 4. 方法层建议",
            "## 5. 实验与验证建议",
            "## 6. 论文中可以主张什么 / 不应主张什么",
            "## 7. 主要风险与应对",
            "## 8. 参考证据清单",
        ]
    return [
        "## 1. One-Page Conclusion",
        "## 2. Evidence Landscape",
        "## 3. Recommended Framing And Boundaries",
        "## 4. Method Guidance",
        "## 5. Experimental Guidance",
        "## 6. What The Paper Can Claim / Should Avoid",
        "## 7. Main Risks And Responses",
        "## 8. Evidence Reference List",
    ]


def _update_validation_bundle(
    workspace: Workspace,
    record: ReportValidationRecord,
) -> None:
    path = workspace.require_path("artifacts", "report_validation")
    payload = read_json(path) if path.exists() else {}
    bundle = ReportValidationBundleRecord.model_validate(payload or {})
    if record.kind == "feasibility":
        bundle.feasibility = record
    else:
        bundle.deep_dive = record
    write_json(path, bundle.model_dump(mode="json"))


def validate_report(workspace: Workspace, kind: str, config: IdeaEvaluationConfig) -> ReportValidationRecord:
    if kind not in {"feasibility", "deep-dive"}:
        raise ValueError(f"Unsupported validation kind: {kind}")

    report_name = "deep_dive" if kind == "deep-dive" else kind
    report_path = workspace.require_path("reports", report_name)
    language = workspace.manifest.report_language
    text = read_text(report_path)
    evidence_map = build_evidence_map(workspace, config)
    issues: list[ReportValidationIssueRecord] = []

    for heading in _required_headings(kind, language):
        if heading not in text:
            issues.append(
                ReportValidationIssueRecord(
                    level="error",
                    code="missing_heading",
                    message=f"Missing required heading: {heading}",
                )
            )

    expected_claim_count = min(2, len(evidence_map.claims)) if kind == "deep-dive" else min(1, len(evidence_map.claims))
    matched_claims = sum(1 for claim in evidence_map.claims if claim.claim_id in text)
    if matched_claims < expected_claim_count:
        issues.append(
            ReportValidationIssueRecord(
                level="error",
                code="missing_claim_trace",
                message="Report does not trace enough claim IDs from the evidence map.",
            )
        )

    expected_paper_count = min(3 if kind == "deep-dive" else 1, len(evidence_map.reference_papers))
    matched_papers = sum(1 for paper in evidence_map.reference_papers if paper.title in text)
    if matched_papers < expected_paper_count:
        issues.append(
            ReportValidationIssueRecord(
                level="error",
                code="missing_evidence_titles",
                message="Report does not mention enough top evidence paper titles.",
            )
        )

    min_length = 1800 if kind == "deep-dive" and language == "zh" else 1200 if kind == "deep-dive" else 700
    if len(text.strip()) < min_length:
        issues.append(
            ReportValidationIssueRecord(
                level="warning",
                code="short_report",
                message=f"Report length looks short for {kind}: {len(text.strip())} characters.",
            )
        )

    passed = not any(issue.level == "error" for issue in issues)
    record = ReportValidationRecord(
        kind=kind,  # type: ignore[arg-type]
        report_path=str(report_path),
        passed=passed,
        issues=issues,
        checked_at=utc_now(),
    )
    _update_validation_bundle(workspace, record)
    return record
