"""Run terminology-level handout for incremental learning via OpenAlex."""
from __future__ import annotations

from pathlib import Path

from autoscholar.handout import HandoutQuery, render_handout_report
from autoscholar.io import write_text
from autoscholar.openalex_crawl import OpenAlexCrawlConfig, OpenAlexQuery, crawl_openalex_queries

ROOT = Path("/home/yingjun/data/auto_scholar2.0版/workspaces/handout/incremental-learning-terminology")
RESULTS = ROOT / "artifacts" / "openalex_results.jsonl"
FAILURES = ROOT / "artifacts" / "openalex_failures.jsonl"
REPORT = ROOT / "reports" / "handout_openalex.md"

ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / "artifacts").mkdir(exist_ok=True)
(ROOT / "reports").mkdir(exist_ok=True)

# Domain-specific ML phrases per CLAUDE.md — avoids educational/policy noise
OA_QUERIES = [
    OpenAlexQuery(
        "terminology_01_survey",
        "catastrophic forgetting continual learning survey concepts definitions",
    ),
    OpenAlexQuery(
        "terminology_02_taxonomy",
        "continual learning incremental learning taxonomy glossary",
    ),
    OpenAlexQuery(
        "terminology_03_boundary",
        "task incremental class incremental domain incremental comparison",
    ),
    OpenAlexQuery(
        "terminology_04_benchmark",
        "continual learning benchmark metric evaluation neural networks",
    ),
]

# Matching HandoutQuery objects drive the report renderer
HANDOUT_QUERIES = [
    HandoutQuery(
        "terminology_01_survey",
        "catastrophic forgetting continual learning survey concepts definitions",
        "terminology-survey",
        "寻找综述性论文中的术语定义。",
    ),
    HandoutQuery(
        "terminology_02_taxonomy",
        "continual learning incremental learning taxonomy glossary",
        "tutorial-taxonomy",
        "寻找教程、taxonomy、glossary 式材料。",
    ),
    HandoutQuery(
        "terminology_03_boundary",
        "task incremental class incremental domain incremental comparison",
        "concept-boundary",
        "寻找术语边界和相近概念区分。",
    ),
    HandoutQuery(
        "terminology_04_benchmark",
        "continual learning benchmark metric evaluation neural networks",
        "benchmark-terms",
        "补齐评价相关术语。",
    ),
]

config = OpenAlexCrawlConfig(
    output=RESULTS,
    failures=FAILURES,
    limit=12,
    pause_seconds=1.5,
    filters="publication_year:>2015",
)

summary = crawl_openalex_queries(OA_QUERIES, config)
print(f"\nCrawl summary: {summary}")

report = render_handout_report(
    domain="增量学习 (Incremental / Continual Learning)",
    level="terminology",
    queries=HANDOUT_QUERIES,
    results_path=RESULTS,
    failures_path=FAILURES,
    crawl_summary=summary,
)
write_text(REPORT, report)
print(f"\nReport written to: {REPORT}")
