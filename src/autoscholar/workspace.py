from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml

from autoscholar.exceptions import ValidationError, WorkspaceError
from autoscholar.io import read_yaml, touch_jsonl, write_text, write_yaml
from autoscholar.models import WorkspaceManifest


WORKSPACE_SCHEMA_VERSION = "2.0"
WorkspaceTemplate = Literal["citation-paper", "idea-evaluation", "idea-creation-v2"]


def _default_manifest(template: WorkspaceTemplate, reports_lang: Literal["zh", "en"]) -> WorkspaceManifest:
    if template not in {"citation-paper", "idea-evaluation", "idea-creation-v2"}:
        raise WorkspaceError(f"Unsupported workspace template: {template}")

    if template == "idea-creation-v2":
        return WorkspaceManifest.model_validate(
            {
                "schema_version": WORKSPACE_SCHEMA_VERSION,
                "workspace_type": template,
                "report_language": reports_lang,
                "inputs": {
                    "manuscript": None,
                    "idea_source": None,
                    "idea_seed": "inputs/idea_seed.md",
                    "constraints": "inputs/constraints.yaml",
                },
                "configs": {"conversation": "configs/conversation.yaml"},
                "artifacts": {
                    "stage1": "artifacts/stage1_diagnosis.json",
                    "stage2": "artifacts/stage2_alternatives.json",
                    "stage3": "artifacts/stage3_pruning.json",
                    "stage4": "artifacts/stage4_failure_narratives.json",
                    "stage5": "artifacts/stage5_identity.json",
                    "retrieval_dir": "artifacts/retrieval",
                    "report_validation": "artifacts/report_validation.json",
                },
                "reports": {"conversation_record": "reports/idea_conversation_record.md"},
            }
        )

    if template == "citation-paper":
        inputs = {"manuscript": "inputs/manuscript.md", "idea_source": None}
    else:
        inputs = {"manuscript": None, "idea_source": "inputs/idea_source.md"}

    return WorkspaceManifest.model_validate(
        {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspace_type": template,
            "report_language": reports_lang,
            "inputs": inputs,
            "configs": {
                "search": "configs/search.yaml",
                "recommendation": "configs/recommendation.yaml",
                "citation_rules": "configs/citation_rules.yaml",
                "idea_evaluation": "configs/idea_evaluation.yaml",
            },
            "artifacts": {
                "claims": "artifacts/claims.jsonl",
                "queries": "artifacts/queries.jsonl",
                "search_results_raw": "artifacts/search_results.raw.jsonl",
                "search_results_deduped": "artifacts/search_results.deduped.jsonl",
                "query_reviews": "artifacts/query_reviews.json",
                "search_failures": "artifacts/search_failures.jsonl",
                "recommendation_corrections": "artifacts/recommendation_corrections.jsonl",
                "selected_citations": "artifacts/selected_citations.jsonl",
                "idea_assessment": "artifacts/idea_assessment.json",
                "evidence_map": "artifacts/evidence_map.json",
                "report_validation": "artifacts/report_validation.json",
                "references_bib": "artifacts/references.bib",
            },
            "reports": {
                "prescreen": "reports/prescreen.md",
                "shortlist": "reports/shortlist.md",
                "feasibility": "reports/feasibility.md",
                "deep_dive": "reports/deep_dive.md",
            },
        }
    )


def _default_search_config() -> dict:
    return {
        "endpoint": "relevance",
        "limit": 10,
        "timeout": 30.0,
        "fields": (
            "paperId,title,year,authors,url,abstract,citationCount,"
            "influentialCitationCount,venue,externalIds,isOpenAccess,openAccessPdf"
        ),
        "filters": {
            "sort": None,
            "publication_types": [],
            "open_access_pdf": None,
            "min_citation_count": None,
            "publication_date_or_year": None,
            "year": None,
            "venue": None,
            "fields_of_study": [],
        },
        "mode": "single_thread",
        "single_thread": {
            "workers": 1,
            "max_retries": 5,
            "retry_delay": 1.0,
            "pause_seconds": 1.0,
        },
        "multi_thread": {
            "workers": 8,
            "max_retries": 5,
            "retry_delay": 1.0,
            "pause_seconds": 0.0,
        },
    }


def _default_recommendation_config() -> dict:
    return {
        "trigger": {
            "min_selected_papers": 2,
            "min_cross_query_support": 2,
            "low_citation_threshold": 10,
            "max_low_signal_candidates": 2,
            "include_review_status": True,
            "include_claim_notes": True,
        },
        "seed": {
            "selection_mode": "auto",
            "max_seeds_per_claim": 2,
            "min_total_overlap": 2,
            "claim_overrides": {},
        },
        "recommendations": {
            "method": "positive_seed_list",
            "per_seed_limit": 5,
            "top_candidates_per_claim": 5,
            "ready_candidate_count": 2,
            "ready_min_total_overlap": 3,
            "pause_seconds": 0.2,
            "fields": (
                "paperId,title,year,authors,url,abstract,citationCount,"
                "influentialCitationCount,venue,externalIds,isOpenAccess,openAccessPdf"
            ),
        },
    }


def _default_citation_rules() -> dict:
    return {
        "stopwords": [],
        "excluded_queries": {},
        "excluded_papers": {},
        "claim_notes": {},
        "selected_papers_limit": 3,
        "query_status_weights": {
            "keep": 1.0,
            "review": 0.6,
            "rewrite": 0.25,
            "exclude": 0.0,
        },
        "score_weights": {
            "title_claim_overlap": 4.0,
            "abstract_claim_overlap": 1.75,
            "title_query_overlap": 2.5,
            "abstract_query_overlap": 1.0,
            "support_count": 0.75,
            "weighted_support": 2.5,
            "best_rank_reciprocal": 3.0,
            "mean_rank_reciprocal": 1.5,
            "influential_citations": 0.8,
            "citations": 0.3,
        },
    }


def _default_idea_evaluation_config() -> dict:
    return {
        "top_evidence_per_claim": 2,
        "ready_threshold": 0.7,
        "revision_threshold": 0.45,
        "report_top_papers_per_claim": 3,
        "report_reference_limit": 12,
        "report_claim_summary_limit": 3,
    }


def _default_conversation_config() -> dict:
    return {
        "retrieval_budgets": {
            "stage1": 5,
            "stage2_per_alt": 5,
            "stage3_per_survivor": 50,
            "stage4_per_narrative": 5,
            "stage5": 0,
        },
        "stage_gates": {
            "stage1_max_rounds": 3,
            "stage2_min_alternatives": 3,
            "stage2_max_alternatives": 5,
            "stage3_max_survivors": 3,
            "stage4_require_all_three_types": True,
            "stage5_allow_user_write_in": True,
        },
        "form_types_allowed": ["alpha", "beta", "gamma", "delta"],
        "report": {
            "kind": "idea-conversation",
            "language": "zh",
            "include_retrieval_appendix": True,
        },
    }


def _default_constraints_config() -> dict:
    return {
        "hard_constraints": [],
        "soft_constraints": [],
        "notes": "",
    }


def _default_idea_seed_text() -> str:
    return (
        "# Idea Seed\n\n"
        "Read `.agents/skills/idea-creation-v2/references/input-templates.md`, "
        "choose one form type, and fill only the relevant section.\n\n"
        "## Form Type\n\n"
        "- [ ] alpha - conceptual split\n"
        "- [ ] beta - scenario inversion\n"
        "- [ ] gamma - gap observation\n"
        "- [ ] delta - constraint driven\n\n"
        "## Trigger\n\n\n"
        "## Negative Space\n\n\n"
        "## Minimum Testable Unit\n\n\n"
        "## Notes\n\n\n"
    )


class Workspace:
    def __init__(self, root: Path, manifest: WorkspaceManifest):
        self.root = root.resolve()
        self.manifest = manifest

    @classmethod
    def load(cls, root: Path) -> "Workspace":
        root = root.resolve()
        manifest_path = root / "workspace.yaml"
        if not manifest_path.exists():
            raise WorkspaceError(f"workspace.yaml not found: {manifest_path}")
        manifest = WorkspaceManifest.model_validate(read_yaml(manifest_path))
        return cls(root=root, manifest=manifest)

    @classmethod
    def init(
        cls,
        root: Path,
        template: WorkspaceTemplate,
        reports_lang: Literal["zh", "en"],
    ) -> "Workspace":
        root = root.resolve()
        if root.exists() and any(root.iterdir()):
            raise WorkspaceError(f"Workspace directory is not empty: {root}")
        root.mkdir(parents=True, exist_ok=True)
        manifest = _default_manifest(template=template, reports_lang=reports_lang)
        workspace = cls(root=root, manifest=manifest)
        workspace._bootstrap()
        return workspace

    def _bootstrap(self) -> None:
        for directory in ("inputs", "configs", "artifacts", "reports"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

        write_yaml(self.root / "workspace.yaml", self.manifest.model_dump(mode="json"))
        if self.path("configs", "search") is not None:
            write_yaml(self.require_path("configs", "search"), _default_search_config())
        if self.path("configs", "recommendation") is not None:
            write_yaml(self.require_path("configs", "recommendation"), _default_recommendation_config())
        if self.path("configs", "citation_rules") is not None:
            write_yaml(self.require_path("configs", "citation_rules"), _default_citation_rules())
        if self.path("configs", "idea_evaluation") is not None:
            write_yaml(self.require_path("configs", "idea_evaluation"), _default_idea_evaluation_config())
        if self.path("configs", "conversation") is not None:
            write_yaml(self.require_path("configs", "conversation"), _default_conversation_config())

        if self.manifest.inputs.manuscript:
            write_text(
                self.root / self.manifest.inputs.manuscript,
                "# Manuscript Notes\n\nDescribe the paper draft or paste the relevant section here.\n",
            )
        if self.manifest.inputs.idea_source:
            write_text(
                self.root / self.manifest.inputs.idea_source,
                "# Idea Source\n\nDescribe the idea, source papers, and the intended contribution.\n",
            )
        if self.manifest.inputs.idea_seed:
            write_text(self.root / self.manifest.inputs.idea_seed, _default_idea_seed_text())
        if self.manifest.inputs.constraints:
            write_yaml(self.root / self.manifest.inputs.constraints, _default_constraints_config())

        for artifact_name in (
            "claims",
            "queries",
            "search_results_raw",
            "search_results_deduped",
            "search_failures",
            "recommendation_corrections",
            "selected_citations",
        ):
            path = self.path("artifacts", artifact_name)
            if path is not None:
                touch_jsonl(path)

        for json_path in (
            self.path("artifacts", "query_reviews"),
            self.path("artifacts", "idea_assessment"),
            self.path("artifacts", "evidence_map"),
            self.path("artifacts", "report_validation"),
            self.path("artifacts", "stage1"),
            self.path("artifacts", "stage2"),
            self.path("artifacts", "stage3"),
            self.path("artifacts", "stage4"),
            self.path("artifacts", "stage5"),
        ):
            if json_path is not None and not json_path.exists():
                write_text(json_path, "{}\n")

        retrieval_dir = self.path("artifacts", "retrieval_dir")
        if retrieval_dir is not None:
            retrieval_dir.mkdir(parents=True, exist_ok=True)

    def path(self, section: Literal["inputs", "configs", "artifacts", "reports"], name: str) -> Path | None:
        group = getattr(self.manifest, section)
        value = getattr(group, name, None)
        if value in (None, ""):
            return None
        return (self.root / value).resolve()

    def require_path(self, section: Literal["inputs", "configs", "artifacts", "reports"], name: str) -> Path:
        path = self.path(section, name)
        if path is None:
            raise WorkspaceError(f"Manifest does not define {section}.{name}")
        return path

    def doctor(self) -> list[str]:
        issues: list[str] = []
        manifest_path = self.root / "workspace.yaml"
        if not manifest_path.exists():
            return [f"Missing manifest: {manifest_path}"]

        for section in ("configs", "artifacts", "reports"):
            group = getattr(self.manifest, section)
            for name, relative_path in group.model_dump().items():
                if relative_path in (None, ""):
                    continue
                path = self.root / relative_path
                if not path.parent.exists():
                    issues.append(f"Missing parent directory for {section}.{name}: {path.parent}")

        for section in ("configs", "artifacts"):
            group = getattr(self.manifest, section)
            for name, relative_path in group.model_dump().items():
                if relative_path in (None, ""):
                    continue
                path = self.root / relative_path
                if section == "configs" and not path.exists():
                    issues.append(f"Missing config file: {path}")
                if name in {"claims", "queries"} and not path.exists():
                    issues.append(f"Missing required artifact: {path}")
        return issues


def workspace_summary(workspace: Workspace) -> dict:
    return {
        "root": str(workspace.root),
        "workspace_type": workspace.manifest.workspace_type,
        "report_language": workspace.manifest.report_language,
        "manifest": str(workspace.root / "workspace.yaml"),
    }


def dump_manifest(workspace: Workspace) -> str:
    return yaml.safe_dump(workspace.manifest.model_dump(mode="json"), sort_keys=False, allow_unicode=True)


def validate_workspace_type(workspace: Workspace, expected: WorkspaceTemplate) -> None:
    if workspace.manifest.workspace_type != expected:
        raise ValidationError(
            f"Workspace type mismatch: expected {expected}, got {workspace.manifest.workspace_type}"
        )
