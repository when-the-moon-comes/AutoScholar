from __future__ import annotations

from collections import defaultdict
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from autoscholar.citation.config import IdeaEvaluationConfig
from autoscholar.io import read_json, read_json_list, read_jsonl, read_yaml, write_text
from autoscholar.models import ClaimRecord, QueryReviewRecord, SelectedCitationRecord
from autoscholar.reporting.authoring import build_deep_dive_context, build_feasibility_context
from autoscholar.workspace import Workspace


def _template_environment() -> Environment:
    template_dir = files("autoscholar").joinpath("templates")
    return Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False, trim_blocks=True, lstrip_blocks=True)


def _language_labels(language: str) -> dict[str, str]:
    if language == "zh":
        return {
            "ready": "ready",
            "review": "review",
            "weak": "weak",
            "keep": "keep",
            "rewrite": "rewrite",
            "exclude": "exclude",
        }
    return {
        "ready": "ready",
        "review": "review",
        "weak": "weak",
        "keep": "keep",
        "rewrite": "rewrite",
        "exclude": "exclude",
    }


def _read_optional_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return read_json(path)


def render_report(workspace: Workspace, kind: str) -> Path:
    env = _template_environment()
    language = workspace.manifest.report_language
    labels = _language_labels(language)

    if kind == "prescreen":
        claims = {item.claim_id: item for item in read_jsonl(workspace.require_path("artifacts", "claims"), ClaimRecord)}
        query_reviews = read_json_list(workspace.require_path("artifacts", "query_reviews"), "query_reviews", QueryReviewRecord)
        reviews_by_claim: dict[str, list[QueryReviewRecord]] = defaultdict(list)
        for review in query_reviews:
            reviews_by_claim[review.claim_id].append(review)
        output_path = workspace.require_path("reports", "prescreen")
        template = env.get_template("report_prescreen.md.j2")
        content = template.render(
            language=language,
            labels=labels,
            claims=claims,
            reviews_by_claim=reviews_by_claim,
            summary={
                "query_count": len(query_reviews),
                "ready_claims": sum(
                    1 for claim_id, items in reviews_by_claim.items()
                    if any(item.status == "keep" for item in items)
                ),
                "rewrite_claims": sum(
                    1 for claim_id, items in reviews_by_claim.items()
                    if items and all(item.status in {"rewrite", "exclude"} for item in items)
                ),
            },
        )
    elif kind == "shortlist":
        records = read_jsonl(workspace.require_path("artifacts", "selected_citations"), SelectedCitationRecord)
        output_path = workspace.require_path("reports", "shortlist")
        template = env.get_template("report_shortlist.md.j2")
        content = template.render(
            language=language,
            labels=labels,
            records=records,
            summary={
                "claim_count": len(records),
                "ready_count": sum(1 for item in records if item.status == "ready"),
                "review_count": sum(1 for item in records if item.status == "review"),
                "weak_count": sum(1 for item in records if item.status == "weak"),
            },
        )
    elif kind == "feasibility":
        config = IdeaEvaluationConfig.model_validate(read_yaml(workspace.require_path("configs", "idea_evaluation")))
        context = build_feasibility_context(workspace, config)
        output_path = workspace.require_path("reports", "feasibility")
        template = env.get_template("report_feasibility.md.j2")
        content = template.render(language=language, labels=labels, **context)
    elif kind == "deep-dive":
        config = IdeaEvaluationConfig.model_validate(read_yaml(workspace.require_path("configs", "idea_evaluation")))
        context = build_deep_dive_context(workspace, config)
        output_path = workspace.require_path("reports", "deep_dive")
        template = env.get_template("report_deep_dive.md.j2")
        content = template.render(language=language, labels=labels, **context)
    elif kind == "idea-conversation":
        output_path = workspace.require_path("reports", "conversation_record")
        template = env.get_template("report_idea_conversation.md.j2")
        content = template.render(
            language=language,
            labels=labels,
            stages={
                "stage1": _read_optional_json(workspace.path("artifacts", "stage1")),
                "stage2": _read_optional_json(workspace.path("artifacts", "stage2")),
                "stage3": _read_optional_json(workspace.path("artifacts", "stage3")),
                "stage4": _read_optional_json(workspace.path("artifacts", "stage4")),
                "stage5": _read_optional_json(workspace.path("artifacts", "stage5")),
            },
        )
    else:
        raise ValueError(f"Unsupported report kind: {kind}")

    write_text(output_path, content.strip() + "\n")
    return output_path
