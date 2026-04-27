from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from autoscholar.analysis import assess_idea
from autoscholar.citation import build_shortlist, run_correction, run_prescreen, run_search, write_bibtex
from autoscholar.citation.config import CitationRulesConfig, IdeaEvaluationConfig, RecommendationConfig, SearchConfig
from autoscholar.handout import HandoutLevel, init_handout, validate_level
from autoscholar.triggered_push.cli import trigger_app
from autoscholar.io import read_json, read_json_list, read_json_model, read_jsonl, read_yaml
from autoscholar.journal_fit import JournalFitRunner, JournalFitWorkspace, derive_paper_id
from autoscholar.models import (
    ClaimRecord,
    EvidenceMapRecord,
    IdeaAssessmentRecord,
    QueryRecord,
    QueryReviewRecord,
    RecommendationCorrectionRecord,
    ReportValidationBundleRecord,
    SearchFailureRecord,
    SearchResultRecord,
    SelectedCitationRecord,
    WorkspaceManifest,
    export_json_schemas,
)
from autoscholar.openalex_crawl import (
    OpenAlexCrawlConfig,
    crawl_openalex_queries,
    load_queries_file as load_openalex_queries_file,
    normalize_queries as normalize_openalex_queries,
)
from autoscholar.reporting import build_evidence_map, render_report, validate_report
from autoscholar.semantic_crawl import (
    SemanticCrawlConfig,
    crawl_semantic_queries,
    load_queries_file as load_semantic_queries_file,
    normalize_queries as normalize_semantic_queries,
)
from autoscholar.utils import pdf_to_text
from autoscholar.workspace import Workspace, dump_manifest, workspace_summary
from autoscholar.integrations import OpenAlexClient, SemanticScholarClient
from autoscholar.integrations.openalex import DEFAULT_AUTHOR_SELECT, DEFAULT_WORK_SELECT

app = typer.Typer(help="AutoScholar v2 unified CLI.")
workspace_app = typer.Typer(help="Workspace management.")
citation_app = typer.Typer(help="Citation workflow commands.")
idea_app = typer.Typer(help="Idea analysis workflow commands.")
report_app = typer.Typer(help="Report rendering commands.")
schema_app = typer.Typer(help="JSON schema export commands.")
semantic_app = typer.Typer(help="Low-level Semantic Scholar API commands.")
openalex_app = typer.Typer(help="Low-level OpenAlex API commands.")
util_app = typer.Typer(help="Utility commands.")
jfa_app = typer.Typer(help="Journal-fit-advisor workflow commands.")
handout_app = typer.Typer(help="Layered research handout generation.")

app.add_typer(workspace_app, name="workspace")
app.add_typer(citation_app, name="citation")
app.add_typer(idea_app, name="idea")
app.add_typer(report_app, name="report")
app.add_typer(schema_app, name="schema")
app.add_typer(semantic_app, name="semantic")
app.add_typer(openalex_app, name="openalex")
app.add_typer(util_app, name="util")
app.add_typer(jfa_app, name="jfa")
app.add_typer(handout_app, name="handout")
app.add_typer(trigger_app, name="trigger")


def _load_workspace(path: Path) -> Workspace:
    return Workspace.load(path)


def _dump_json(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _load_search_config(workspace: Workspace) -> SearchConfig:
    return SearchConfig.model_validate(read_yaml(workspace.require_path("configs", "search")))


def _load_recommendation_config(workspace: Workspace) -> RecommendationConfig:
    return RecommendationConfig.model_validate(read_yaml(workspace.require_path("configs", "recommendation")))


def _load_rules(workspace: Workspace) -> CitationRulesConfig:
    return CitationRulesConfig.model_validate(read_yaml(workspace.require_path("configs", "citation_rules")))


def _load_idea_config(workspace: Workspace) -> IdeaEvaluationConfig:
    return IdeaEvaluationConfig.model_validate(read_yaml(workspace.require_path("configs", "idea_evaluation")))


@workspace_app.command("init")
def workspace_init(
    target_dir: Path,
    template: str = typer.Option(..., "--template", help="citation-paper, idea-evaluation, or idea-creation-v2"),
    reports_lang: str = typer.Option("zh", "--reports-lang", help="zh or en"),
) -> None:
    workspace = Workspace.init(
        root=target_dir,
        template=template,  # type: ignore[arg-type]
        reports_lang=reports_lang,  # type: ignore[arg-type]
    )
    typer.echo(f"Initialized workspace: {workspace.root}")
    typer.echo(dump_manifest(workspace).strip())


@workspace_app.command("doctor")
def workspace_doctor(workspace_dir: Path = typer.Option(..., "--workspace")) -> None:
    workspace = _load_workspace(workspace_dir)
    issues = workspace.doctor()
    for loader in (
        lambda: WorkspaceManifest.model_validate(read_yaml(workspace.root / "workspace.yaml")),
        lambda: SearchConfig.model_validate(read_yaml(workspace.require_path("configs", "search")))
        if workspace.path("configs", "search") is not None
        else None,
        lambda: RecommendationConfig.model_validate(read_yaml(workspace.require_path("configs", "recommendation")))
        if workspace.path("configs", "recommendation") is not None
        else None,
        lambda: CitationRulesConfig.model_validate(read_yaml(workspace.require_path("configs", "citation_rules")))
        if workspace.path("configs", "citation_rules") is not None
        else None,
        lambda: IdeaEvaluationConfig.model_validate(read_yaml(workspace.require_path("configs", "idea_evaluation")))
        if workspace.path("configs", "idea_evaluation") is not None
        else None,
    ):
        try:
            loader()
        except Exception as exc:
            issues.append(str(exc))

    jsonl_checks = (
        ("claims", ClaimRecord),
        ("queries", QueryRecord),
        ("search_results_raw", SearchResultRecord),
        ("search_results_deduped", SearchResultRecord),
        ("search_failures", SearchFailureRecord),
        ("recommendation_corrections", RecommendationCorrectionRecord),
        ("selected_citations", SelectedCitationRecord),
    )
    for artifact_name, model in jsonl_checks:
        path = workspace.path("artifacts", artifact_name)
        if path is None:
            continue
        try:
            if path.exists() and path.read_text(encoding="utf-8").strip():
                read_jsonl(path, model)
        except Exception as exc:
            issues.append(str(exc))

    try:
        query_reviews_path = workspace.path("artifacts", "query_reviews")
        if query_reviews_path is not None and query_reviews_path.exists():
            read_json_list(query_reviews_path, "query_reviews", QueryReviewRecord)
    except Exception as exc:
        issues.append(str(exc))

    idea_assessment_path = workspace.path("artifacts", "idea_assessment")
    try:
        if idea_assessment_path is not None and idea_assessment_path.exists():
            payload = read_json(idea_assessment_path)
            if payload:
                read_json_model(idea_assessment_path, IdeaAssessmentRecord)
    except Exception as exc:
        issues.append(str(exc))

    for artifact_name, model in (
        ("evidence_map", EvidenceMapRecord),
        ("report_validation", ReportValidationBundleRecord),
    ):
        path = workspace.path("artifacts", artifact_name)
        if path is None:
            continue
        try:
            if path.exists():
                payload = read_json(path)
                if payload:
                    read_json_model(path, model)
        except Exception as exc:
            issues.append(str(exc))

    summary = workspace_summary(workspace)
    typer.echo(f"Workspace: {summary['root']}")
    typer.echo(f"Type: {summary['workspace_type']}")
    typer.echo(f"Report language: {summary['report_language']}")
    if issues:
        typer.echo("Issues:")
        for issue in issues:
            typer.echo(f"- {issue}")
        raise typer.Exit(code=1)
    typer.echo("Workspace is valid.")


@citation_app.command("search")
def citation_search(workspace_dir: Path = typer.Option(..., "--workspace")) -> None:
    workspace = _load_workspace(workspace_dir)
    success_count, failure_count = run_search(workspace, _load_search_config(workspace))
    typer.echo(f"Search complete. success={success_count} failure={failure_count}")


@citation_app.command("prescreen")
def citation_prescreen(workspace_dir: Path = typer.Option(..., "--workspace")) -> None:
    workspace = _load_workspace(workspace_dir)
    reviews = run_prescreen(workspace, _load_rules(workspace))
    typer.echo(f"Prescreen complete. query_reviews={len(reviews)}")


@citation_app.command("correct")
def citation_correct(workspace_dir: Path = typer.Option(..., "--workspace")) -> None:
    workspace = _load_workspace(workspace_dir)
    records = run_correction(
        workspace=workspace,
        rules=_load_rules(workspace),
        config=_load_recommendation_config(workspace),
    )
    typer.echo(f"Correction complete. triggered_claims={len(records)}")


@citation_app.command("shortlist")
def citation_shortlist(workspace_dir: Path = typer.Option(..., "--workspace")) -> None:
    workspace = _load_workspace(workspace_dir)
    records = build_shortlist(workspace, _load_rules(workspace))
    typer.echo(f"Shortlist complete. claims={len(records)}")


@citation_app.command("bib")
def citation_bib(workspace_dir: Path = typer.Option(..., "--workspace")) -> None:
    workspace = _load_workspace(workspace_dir)
    entry_count, _ = write_bibtex(workspace)
    typer.echo(f"Wrote BibTeX entries: {entry_count}")


@idea_app.command("assess")
def idea_assess(workspace_dir: Path = typer.Option(..., "--workspace")) -> None:
    workspace = _load_workspace(workspace_dir)
    config = _load_idea_config(workspace)
    assessment = assess_idea(workspace, config)
    build_evidence_map(workspace, config)
    typer.echo(f"Idea assessment complete. recommendation={assessment.recommendation}")


@report_app.command("render")
def report_render(
    workspace_dir: Path = typer.Option(..., "--workspace"),
    kind: str = typer.Option(..., "--kind", help="prescreen, shortlist, feasibility, deep-dive, or idea-conversation"),
) -> None:
    normalized_kind = "deep-dive" if kind == "deep-dive" else kind
    path = render_report(_load_workspace(workspace_dir), normalized_kind)
    typer.echo(f"Wrote report: {path}")


@report_app.command("validate")
def report_validate(
    workspace_dir: Path = typer.Option(..., "--workspace"),
    kind: str = typer.Option(..., "--kind", help="feasibility or deep-dive"),
) -> None:
    normalized_kind = "deep-dive" if kind == "deep-dive" else kind
    if normalized_kind not in {"feasibility", "deep-dive"}:
        raise typer.BadParameter("kind must be feasibility or deep-dive")
    workspace = _load_workspace(workspace_dir)
    record = validate_report(workspace, normalized_kind, _load_idea_config(workspace))
    typer.echo(f"Report validation passed={record.passed}")
    for issue in record.issues:
        typer.echo(f"- {issue.level}: {issue.code}: {issue.message}")
    if not record.passed:
        raise typer.Exit(code=1)


@schema_app.command("export")
def schema_export(output_dir: Path = typer.Option(..., "--output-dir")) -> None:
    written = export_json_schemas(output_dir)
    for path in written:
        typer.echo(f"Wrote: {path}")


def _load_jfa_runner(base_dir: Path, paper_id: str) -> JournalFitRunner:
    return JournalFitRunner(JournalFitWorkspace(base_dir=base_dir, paper_id=paper_id))


@handout_app.command("init")
def handout_init(
    domain: str,
    level: str = typer.Option(
        ...,
        "--level",
        help="terminology, landscape, or tension",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Handout workspace directory. Defaults to workspaces/handout/<domain>-<level>.",
    ),
    crawl: bool = typer.Option(
        True,
        "--crawl/--no-crawl",
        help="Run checkpointed Semantic Scholar crawl before rendering.",
    ),
    endpoint: str = typer.Option("relevance", "--endpoint", help="relevance or bulk"),
    limit: int | None = typer.Option(None, "--limit", help="Search results per query."),
    timeout: float = typer.Option(30.0, "--timeout"),
    max_retries: int = typer.Option(3, "--max-retries"),
    retry_delay: float = typer.Option(120.0, "--retry-delay"),
    pause_seconds: float = typer.Option(10.0, "--pause-seconds"),
    retry_failed: bool = typer.Option(
        True,
        "--retry-failed/--skip-failed",
        help="Retry failed queries from the failure checkpoint.",
    ),
    max_queries: int | None = typer.Option(
        None,
        "--max-queries",
        help="Process at most this many pending queries per checkpoint round.",
    ),
    until_complete: bool = typer.Option(
        True,
        "--until-complete/--single-pass",
        help="Keep running checkpoint rounds until all queries complete.",
    ),
    round_delay: float = typer.Option(
        300.0,
        "--round-delay",
        help="Seconds to wait between checkpoint rounds when --until-complete is enabled.",
    ),
    max_rounds: int | None = typer.Option(
        None,
        "--max-rounds",
        help="Optional cap on checkpoint rounds for this command.",
    ),
    year: str | None = typer.Option(None, "--year", help="Bulk endpoint year filter."),
    sort: str | None = typer.Option(None, "--sort", help="Bulk endpoint sort option."),
    venue: str | None = typer.Option(None, "--venue", help="Bulk endpoint venue filter."),
) -> None:
    try:
        resolved_level: HandoutLevel = validate_level(level)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    summary = init_handout(
        domain=domain,
        level=resolved_level,
        output_dir=output_dir,
        run_crawl=crawl,
        endpoint=endpoint,
        limit=limit,
        timeout=timeout,
        max_retries=max_retries,
        retry_delay=retry_delay,
        pause_seconds=pause_seconds,
        retry_failed=retry_failed,
        max_queries=max_queries,
        until_complete=until_complete,
        round_delay=round_delay,
        max_rounds=max_rounds,
        year=year,
        sort=sort,
        venue=venue,
    )
    typer.echo(f"Handout workspace: {summary.root}")
    typer.echo(f"Queries: {summary.queries_path}")
    typer.echo(f"Semantic results: {summary.results_path}")
    typer.echo(f"Semantic failures: {summary.failures_path}")
    typer.echo(f"Report: {summary.report_path}")
    if summary.crawl_summary.get("complete"):
        typer.echo("All queries complete.")
    else:
        typer.echo(f"Remaining queries: {summary.crawl_summary.get('remaining')}")
    _dump_json(summary.crawl_summary)


@jfa_app.command("init")
def jfa_init(
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
    paper_id: str | None = typer.Option(None, "--paper-id"),
    working_title: str | None = typer.Option(None, "--working-title"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite the input template if it already exists."),
) -> None:
    resolved_paper_id = paper_id or (derive_paper_id(working_title or "") if working_title else None)
    if not resolved_paper_id:
        raise typer.BadParameter("Provide either --paper-id or --working-title.")
    workspace = JournalFitWorkspace(base_dir=base_dir, paper_id=resolved_paper_id).ensure_layout()
    template_path = workspace.bootstrap_template(overwrite=overwrite)
    typer.echo(f"Initialized JFA workspace: {workspace.root}")
    typer.echo(f"Input template: {template_path}")


@jfa_app.command("run")
def jfa_run(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
    input_path: Path | None = typer.Option(None, "--input"),
    draft_pdf: Path | None = typer.Option(None, "--draft-pdf"),
    no_cache: bool = typer.Option(False, "--no-cache"),
) -> None:
    summary = _load_jfa_runner(base_dir, paper_id).run(
        input_path=input_path,
        draft_pdf=draft_pdf,
        use_cache=not no_cache,
    )
    typer.echo(f"Primary: {summary.primary_narrative} x {summary.primary_journal}")
    typer.echo(f"Risk: {summary.primary_risk}")
    if summary.backup_narrative and summary.backup_journal:
        typer.echo(f"Backup: {summary.backup_narrative} x {summary.backup_journal}")
    for warning in summary.warnings:
        typer.echo(f"Warning: {warning}")
    for item in summary.action_items:
        typer.echo(f"- {item}")
    typer.echo(f"Report: {summary.report_path}")


@jfa_app.command("phase0")
def jfa_phase0(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
    input_path: Path | None = typer.Option(None, "--input"),
    draft_pdf: Path | None = typer.Option(None, "--draft-pdf"),
) -> None:
    run_meta = _load_jfa_runner(base_dir, paper_id).phase0(input_path=input_path, draft_pdf=draft_pdf)
    typer.echo(f"Phase 0 complete. mode={run_meta.mode} journals={len(run_meta.target_journals)}")


@jfa_app.command("phase1")
def jfa_phase1(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
) -> None:
    inventory = _load_jfa_runner(base_dir, paper_id).phase1()
    typer.echo(f"Phase 1 complete. assets={len(inventory.assets)}")


@jfa_app.command("phase2")
def jfa_phase2(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
    journal: str | None = typer.Option(None, "--journal"),
    no_cache: bool = typer.Option(False, "--no-cache"),
) -> None:
    profiles = _load_jfa_runner(base_dir, paper_id).phase2(journal_name=journal, use_cache=not no_cache)
    typer.echo(f"Phase 2 complete. journals={len(profiles)}")


@jfa_app.command("phase3")
def jfa_phase3(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
) -> None:
    narratives = _load_jfa_runner(base_dir, paper_id).phase3()
    typer.echo(f"Phase 3 complete. narratives={len(narratives)}")


@jfa_app.command("phase4")
def jfa_phase4(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
) -> None:
    matrix = _load_jfa_runner(base_dir, paper_id).phase4()
    typer.echo(f"Phase 4 complete. combinations={len(matrix.matrix)} top={len(matrix.top_combinations)}")


@jfa_app.command("phase5")
def jfa_phase5(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
) -> None:
    paths = _load_jfa_runner(base_dir, paper_id).phase5()
    typer.echo(f"Phase 5 complete. skeletons={len(paths)}")


@jfa_app.command("phase6")
def jfa_phase6(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
) -> None:
    reviews, patches = _load_jfa_runner(base_dir, paper_id).phase6()
    typer.echo(f"Phase 6 complete. reviews={len(reviews.reviews)} patches={len(patches.patches)}")


@jfa_app.command("phase7")
def jfa_phase7(
    paper_id: str = typer.Option(..., "--paper-id"),
    base_dir: Path = typer.Option(Path("."), "--base-dir"),
) -> None:
    summary = _load_jfa_runner(base_dir, paper_id).phase7()
    typer.echo(f"Primary: {summary.primary_narrative} x {summary.primary_journal}")
    typer.echo(f"Report: {summary.report_path}")


@util_app.command("pdf-to-text")
def util_pdf_to_text(
    input_pdf: Path,
    output_txt: Path | None = typer.Option(None, "--output"),
) -> None:
    output_path = pdf_to_text(input_pdf, output_txt)
    typer.echo(f"Wrote text: {output_path}")


@semantic_app.command("paper")
def semantic_paper(
    paper_id: str,
    fields: str = typer.Option("paperId,title,authors,year,abstract", "--fields"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        _dump_json(client.get_paper(paper_id, fields=fields, timeout=timeout))


@semantic_app.command("search")
def semantic_search(
    query: str,
    limit: int = typer.Option(5, "--limit"),
    fields: str = typer.Option("paperId,title,year,authors,url,abstract", "--fields"),
    endpoint: str = typer.Option("relevance", "--endpoint"),
    year: str | None = typer.Option(None, "--year"),
    sort: str | None = typer.Option(None, "--sort"),
    venue: str | None = typer.Option(None, "--venue"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        if endpoint == "bulk":
            payload = list(
                client.search_papers_bulk(
                    query=query,
                    fields=fields,
                    max_results=limit,
                    year=year,
                    sort=sort,
                    venue=venue,
                    timeout=timeout,
                )
            )
            _dump_json({"endpoint": endpoint, "query": query, "count": len(payload), "data": payload})
            return
        _dump_json(client.search_papers(query=query, limit=limit, fields=fields, timeout=timeout))


@semantic_app.command("crawl")
def semantic_crawl(
    queries: list[str] | None = typer.Option(
        None,
        "--query",
        "-q",
        help="Query text. May be passed multiple times.",
    ),
    queries_file: Path | None = typer.Option(
        None,
        "--queries-file",
        help="Text, JSON, or JSONL file containing queries.",
    ),
    output: Path = typer.Option(Path("paper/semantic_crawl_results.jsonl"), "--output"),
    failures: Path = typer.Option(Path("paper/semantic_crawl_failures.jsonl"), "--failures"),
    endpoint: str = typer.Option("relevance", "--endpoint", help="relevance or bulk"),
    limit: int = typer.Option(10, "--limit"),
    fields: str = typer.Option(
        "paperId,title,year,authors,url,abstract,citationCount,venue",
        "--fields",
    ),
    timeout: float = typer.Option(30.0, "--timeout"),
    max_retries: int = typer.Option(3, "--max-retries"),
    retry_delay: float = typer.Option(30.0, "--retry-delay"),
    pause_seconds: float = typer.Option(1.0, "--pause-seconds"),
    retry_failed: bool = typer.Option(
        True,
        "--retry-failed/--skip-failed",
        help="Retry failed queries from the failure checkpoint.",
    ),
    max_queries: int | None = typer.Option(
        None,
        "--max-queries",
        help="Process at most this many pending queries per checkpoint round.",
    ),
    until_complete: bool = typer.Option(
        False,
        "--until-complete/--single-pass",
        help="Keep running checkpoint rounds until all queries complete.",
    ),
    round_delay: float = typer.Option(
        300.0,
        "--round-delay",
        help="Seconds to wait between checkpoint rounds when --until-complete is enabled.",
    ),
    max_rounds: int | None = typer.Option(
        None,
        "--max-rounds",
        help="Optional cap on checkpoint rounds for this command.",
    ),
    year: str | None = typer.Option(None, "--year", help="Bulk endpoint year filter."),
    sort: str | None = typer.Option(None, "--sort", help="Bulk endpoint sort option."),
    venue: str | None = typer.Option(None, "--venue", help="Bulk endpoint venue filter."),
) -> None:
    query_items = []
    if queries:
        query_items.extend(normalize_semantic_queries(queries))
    if queries_file is not None:
        query_items.extend(load_semantic_queries_file(queries_file))
    if not query_items:
        raise typer.BadParameter("Provide at least one --query or --queries-file.")

    config = SemanticCrawlConfig(
        output=output,
        failures=failures,
        endpoint=endpoint,
        limit=limit,
        fields=fields,
        timeout=timeout,
        max_retries=max_retries,
        retry_delay=retry_delay,
        pause_seconds=pause_seconds,
        retry_failed=retry_failed,
        max_queries=max_queries,
        until_complete=until_complete,
        round_delay=round_delay,
        max_rounds=max_rounds,
        year=year,
        sort=sort,
        venue=venue,
    )
    summary = crawl_semantic_queries(query_items, config)
    _dump_json(summary)


@semantic_app.command("recommend")
def semantic_recommend(
    paper_id: str,
    limit: int = typer.Option(5, "--limit"),
    fields: str = typer.Option("paperId,title,year,authors,url", "--fields"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        _dump_json(client.get_recommendations(paper_id=paper_id, limit=limit, fields=fields, timeout=timeout))


@semantic_app.command("citations")
def semantic_citations(
    paper_id: str,
    fields: str = typer.Option("paperId,title,year,authors,url", "--fields"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        _dump_json(client.get_paper_citations(paper_id=paper_id, fields=fields, timeout=timeout))


@semantic_app.command("references")
def semantic_references(
    paper_id: str,
    fields: str = typer.Option("paperId,title,year,authors,url", "--fields"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        _dump_json(client.get_paper_references(paper_id=paper_id, fields=fields, timeout=timeout))


@semantic_app.command("author-search")
def semantic_author_search(
    query: str,
    fields: str = typer.Option("authorId,name,url", "--fields"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        _dump_json(client.search_author(query=query, fields=fields, timeout=timeout))


@semantic_app.command("author")
def semantic_author(
    author_id: str,
    fields: str = typer.Option("authorId,name,url,paperCount,citationCount", "--fields"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        _dump_json(client.get_author(author_id=author_id, fields=fields, timeout=timeout))


@semantic_app.command("author-papers")
def semantic_author_papers(
    author_id: str,
    limit: int = typer.Option(20, "--limit"),
    fields: str = typer.Option("paperId,title,year,authors,url", "--fields"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        _dump_json(client.get_author_papers(author_id=author_id, limit=limit, fields=fields, timeout=timeout))


@semantic_app.command("download-pdf")
def semantic_download_pdf(
    paper_id: str,
    directory: Path = typer.Option(Path("papers"), "--directory"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with SemanticScholarClient(timeout=timeout) as client:
        output_path = client.download_open_access_pdf(paper_id=paper_id, directory=directory, timeout=timeout)
    if output_path is None:
        typer.echo("No open access PDF was available.")
        raise typer.Exit(code=1)
    typer.echo(f"Downloaded PDF: {output_path}")


@semantic_app.command("smoke")
def semantic_smoke(
    query: str = typer.Option("medical image segmentation", "--query"),
    timeout: float = typer.Option(30.0, "--timeout"),
) -> None:
    if not os.environ.get("S2_API_KEY"):
        typer.echo("S2_API_KEY is not set; live smoke test skipped.")
        return

    with SemanticScholarClient(timeout=timeout) as client:
        search_payload = client.search_papers(
            query=query,
            limit=1,
            fields="paperId,title,year",
            timeout=timeout,
        )
        papers = search_payload.get("data", [])
        if not papers:
            typer.echo("Live smoke test failed: search returned no papers.")
            raise typer.Exit(code=1)
        paper_id = papers[0].get("paperId")
        if not paper_id:
            typer.echo("Live smoke test failed: top search result had no paperId.")
            raise typer.Exit(code=1)
        recommendations = client.get_recommendations(
            paper_id=paper_id,
            limit=1,
            fields="paperId,title,year",
            timeout=timeout,
        )

    _dump_json(
        {
            "query": query,
            "top_paper": papers[0],
            "recommendation_count": len(recommendations),
            "recommendations": recommendations,
        }
    )


@openalex_app.command("paper")
def openalex_paper(
    work_id: str,
    fields: str = typer.Option(DEFAULT_WORK_SELECT, "--fields", help="OpenAlex select fields."),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        _dump_json(client.get_paper(work_id, fields=fields, timeout=timeout))


@openalex_app.command("search")
def openalex_search(
    query: str,
    limit: int = typer.Option(5, "--limit"),
    fields: str = typer.Option(DEFAULT_WORK_SELECT, "--fields", help="OpenAlex select fields."),
    endpoint: str = typer.Option("works", "--endpoint", help="works/search/relevance or bulk."),
    filters: str | None = typer.Option(None, "--filter", help="OpenAlex filter expression."),
    sort: str | None = typer.Option(None, "--sort", help="OpenAlex sort expression."),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        if endpoint in {"bulk", "cursor"}:
            payload = list(
                client.search_papers_bulk(
                    query=query,
                    fields=fields,
                    max_results=limit,
                    filters=filters,
                    sort=sort,
                    timeout=timeout,
                )
            )
            _dump_json({"endpoint": "bulk", "query": query, "count": len(payload), "data": payload})
            return
        _dump_json(
            client.search_papers(
                query=query,
                limit=limit,
                fields=fields,
                filters=filters,
                sort=sort,
                timeout=timeout,
            )
        )


@openalex_app.command("crawl")
def openalex_crawl(
    queries: list[str] | None = typer.Option(
        None,
        "--query",
        "-q",
        help="Query text. May be passed multiple times.",
    ),
    queries_file: Path | None = typer.Option(
        None,
        "--queries-file",
        help="Text, JSON, or JSONL file containing queries.",
    ),
    output: Path = typer.Option(Path("paper/openalex_crawl_results.jsonl"), "--output"),
    failures: Path = typer.Option(Path("paper/openalex_crawl_failures.jsonl"), "--failures"),
    endpoint: str = typer.Option("works", "--endpoint", help="works/search/relevance or bulk."),
    limit: int = typer.Option(10, "--limit"),
    fields: str = typer.Option(DEFAULT_WORK_SELECT, "--fields", help="OpenAlex select fields."),
    filters: str | None = typer.Option(None, "--filter", help="OpenAlex filter expression."),
    sort: str | None = typer.Option(None, "--sort", help="OpenAlex sort expression."),
    timeout: float = typer.Option(30.0, "--timeout"),
    max_retries: int = typer.Option(3, "--max-retries"),
    retry_delay: float = typer.Option(30.0, "--retry-delay"),
    pause_seconds: float = typer.Option(1.0, "--pause-seconds"),
    retry_failed: bool = typer.Option(
        True,
        "--retry-failed/--skip-failed",
        help="Retry failed queries from the failure checkpoint.",
    ),
    max_queries: int | None = typer.Option(
        None,
        "--max-queries",
        help="Process at most this many pending queries per checkpoint round.",
    ),
    until_complete: bool = typer.Option(
        False,
        "--until-complete/--single-pass",
        help="Keep running checkpoint rounds until all queries complete.",
    ),
    round_delay: float = typer.Option(
        300.0,
        "--round-delay",
        help="Seconds to wait between checkpoint rounds when --until-complete is enabled.",
    ),
    max_rounds: int | None = typer.Option(
        None,
        "--max-rounds",
        help="Optional cap on checkpoint rounds for this command.",
    ),
) -> None:
    query_items = []
    if queries:
        query_items.extend(normalize_openalex_queries(queries))
    if queries_file is not None:
        query_items.extend(load_openalex_queries_file(queries_file))
    if not query_items:
        raise typer.BadParameter("Provide at least one --query or --queries-file.")

    config = OpenAlexCrawlConfig(
        output=output,
        failures=failures,
        endpoint=endpoint,
        limit=limit,
        fields=fields,
        timeout=timeout,
        max_retries=max_retries,
        retry_delay=retry_delay,
        pause_seconds=pause_seconds,
        retry_failed=retry_failed,
        max_queries=max_queries,
        until_complete=until_complete,
        round_delay=round_delay,
        max_rounds=max_rounds,
        filters=filters,
        sort=sort,
    )
    summary = crawl_openalex_queries(query_items, config)
    _dump_json(summary)


@openalex_app.command("recommend")
def openalex_recommend(
    work_id: str,
    limit: int = typer.Option(5, "--limit"),
    fields: str = typer.Option(DEFAULT_WORK_SELECT, "--fields", help="OpenAlex select fields."),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        _dump_json(client.get_recommendations(paper_id=work_id, limit=limit, fields=fields, timeout=timeout))


@openalex_app.command("citations")
def openalex_citations(
    work_id: str,
    limit: int = typer.Option(50, "--limit"),
    fields: str = typer.Option(DEFAULT_WORK_SELECT, "--fields", help="OpenAlex select fields."),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        _dump_json(client.get_paper_citations(paper_id=work_id, limit=limit, fields=fields, timeout=timeout))


@openalex_app.command("references")
def openalex_references(
    work_id: str,
    limit: int = typer.Option(50, "--limit"),
    fields: str = typer.Option(DEFAULT_WORK_SELECT, "--fields", help="OpenAlex select fields."),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        _dump_json(client.get_paper_references(paper_id=work_id, limit=limit, fields=fields, timeout=timeout))


@openalex_app.command("author-search")
def openalex_author_search(
    query: str,
    limit: int = typer.Option(10, "--limit"),
    fields: str = typer.Option(DEFAULT_AUTHOR_SELECT, "--fields", help="OpenAlex select fields."),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        _dump_json(client.search_author(query=query, limit=limit, fields=fields, timeout=timeout))


@openalex_app.command("author")
def openalex_author(
    author_id: str,
    fields: str = typer.Option(DEFAULT_AUTHOR_SELECT, "--fields", help="OpenAlex select fields."),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        _dump_json(client.get_author(author_id=author_id, fields=fields, timeout=timeout))


@openalex_app.command("author-papers")
def openalex_author_papers(
    author_id: str,
    limit: int = typer.Option(20, "--limit"),
    fields: str = typer.Option(DEFAULT_WORK_SELECT, "--fields", help="OpenAlex select fields."),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        _dump_json(client.get_author_papers(author_id=author_id, limit=limit, fields=fields, timeout=timeout))


@openalex_app.command("download-pdf")
def openalex_download_pdf(
    work_id: str,
    directory: Path = typer.Option(Path("papers"), "--directory"),
    timeout: float | None = typer.Option(None, "--timeout"),
) -> None:
    with OpenAlexClient(timeout=timeout) as client:
        output_path = client.download_open_access_pdf(paper_id=work_id, directory=directory, timeout=timeout)
    if output_path is None:
        typer.echo("No open access PDF was available.")
        raise typer.Exit(code=1)
    typer.echo(f"Downloaded PDF: {output_path}")


@openalex_app.command("smoke")
def openalex_smoke(
    query: str = typer.Option("medical image segmentation", "--query"),
    timeout: float = typer.Option(30.0, "--timeout"),
) -> None:
    if not os.environ.get("OPENALEX_API_KEY"):
        typer.echo("OPENALEX_API_KEY is not set; live smoke test skipped.")
        return

    with OpenAlexClient(timeout=timeout) as client:
        search_payload = client.search_papers(
            query=query,
            limit=1,
            fields="id,title,display_name,publication_year,related_works",
            timeout=timeout,
        )
        papers = search_payload.get("data", [])
        if not papers:
            typer.echo("Live smoke test failed: search returned no papers.")
            raise typer.Exit(code=1)
        paper_id = papers[0].get("paperId")
        if not paper_id:
            typer.echo("Live smoke test failed: top search result had no paperId.")
            raise typer.Exit(code=1)
        recommendations = client.get_recommendations(
            paper_id=paper_id,
            limit=1,
            fields="id,title,display_name,publication_year",
            timeout=timeout,
        )

    _dump_json(
        {
            "query": query,
            "top_paper": papers[0],
            "recommendation_count": len(recommendations),
            "recommendations": recommendations,
        }
    )


if __name__ == "__main__":
    app()
