from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from autoscholar.citation.common import normalize_text, slugify, utc_now
from autoscholar.io import write_text, write_yaml
from autoscholar.semantic_crawl import (
    SemanticCrawlConfig,
    SemanticQuery,
    crawl_semantic_queries,
    write_jsonl_records,
)

HandoutLevel = Literal["terminology", "landscape", "tension"]

HANDOUT_FIELDS = (
    "paperId,title,year,authors,url,abstract,citationCount,"
    "influentialCitationCount,venue,publicationTypes,externalIds"
)

LEVEL_ORDER: tuple[HandoutLevel, ...] = ("terminology", "landscape", "tension")


@dataclass(frozen=True)
class HandoutLevelSpec:
    key: HandoutLevel
    title: str
    depth_label: str
    output_goal: str
    length_hint: str
    avoid: tuple[str, ...]
    completion_tests: tuple[str, ...]
    interaction_prompts: tuple[str, ...]
    query_specs: tuple[tuple[str, str, str], ...]
    default_limit: int


@dataclass(frozen=True)
class HandoutQuery:
    query_id: str
    query_text: str
    purpose: str
    rationale: str

    def as_semantic_query(self) -> SemanticQuery:
        return SemanticQuery(query_id=self.query_id, query_text=self.query_text)

    def as_record(self) -> dict[str, str]:
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "purpose": self.purpose,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class HandoutRunSummary:
    domain: str
    level: HandoutLevel
    root: Path
    report_path: Path
    queries_path: Path
    results_path: Path
    failures_path: Path
    crawl_summary: dict[str, int | bool]


LEVEL_SPECS: dict[HandoutLevel, HandoutLevelSpec] = {
    "terminology": HandoutLevelSpec(
        key="terminology",
        title="第 1 层：术语骨架（Terminology Scaffold）",
        depth_label="词汇深度",
        output_goal="20-40 个核心概念、精确定义，以及最容易混淆术语之间的边界。",
        length_hint="建议 2000-4000 字。",
        avoid=(
            "不要试图综述整个领域。",
            "不要展开代表工作谱系。",
            "不要写时间线。",
        ),
        completion_tests=(
            "能读懂该领域一篇任意论文的 abstract，而不需要临时搜索术语。",
            "能解释两个 close terms 的边界，并能说出它们不等价的原因。",
            "能把一个新术语归到已有术语簇，或指出它为什么需要单独成类。",
        ),
        interaction_prompts=(
            "从证据池中挑 5 个你最不确定的术语，写下你当前的朴素解释。",
            "选择两组看起来相近的术语，分别回答：它们共享什么、分歧点是什么、误用会造成什么判断错误？",
            "找一篇检索结果中的论文 abstract，标出仍然卡住你的术语。",
        ),
        query_specs=(
            ("terminology-survey", "{domain} survey terminology concepts definitions", "寻找综述性论文中的术语定义。"),
            ("tutorial-taxonomy", "{domain} tutorial taxonomy glossary", "寻找教程、taxonomy、glossary 式材料。"),
            ("concept-boundary", "{domain} concept distinction comparison", "寻找术语边界和相近概念区分。"),
            ("benchmark-terms", "{domain} benchmark metric terminology", "补齐评价相关术语。"),
        ),
        default_limit=8,
    ),
    "landscape": HandoutLevelSpec(
        key="landscape",
        title="第 2 层：地貌图（Landscape Map）",
        depth_label="地貌深度",
        output_goal="3-5 个方法家族、评价环境、非线性时间线，以及代表人物/实验室。",
        length_hint="建议 5000-10000 字；参考文献精选 30-50 篇。",
        avoid=(
            "不要罗列所有论文。",
            "不要追求 comprehensive。",
            "不要把时间线写成单线因果链。",
        ),
        completion_tests=(
            "能在该领域的学术 talk 里跟上约 70%。",
            "读到一篇新论文时，能定位它属于哪个方法家族。",
            "能判断新论文是在延续、修补还是反叛某条谱系。",
        ),
        interaction_prompts=(
            "从 3-5 个方法家族中选一个，写下它最核心的假设。",
            "指出一个 benchmark 或 metric 可能偏向哪一类方法。",
            "在时间线里标出一个焦点迁移节点，并解释它为什么发生。",
        ),
        query_specs=(
            ("survey-map", "{domain} survey methods taxonomy benchmark", "寻找能搭建方法家族的综述入口。"),
            ("state-of-the-art", "{domain} state of the art benchmark metrics", "寻找评价环境与 SOTA 设定。"),
            ("recent-advances", "{domain} recent advances 2020 2021 2022 2023 2024", "捕捉近 5-8 年的变化节点。"),
            ("representative-work", "{domain} representative methods comparison", "寻找代表工作和方法比较。"),
            ("labs-authors", "{domain} leading researchers labs", "寻找代表人物、实验室和研究谱系线索。"),
        ),
        default_limit=10,
    ),
    "tension": HandoutLevelSpec(
        key="tension",
        title="第 3 层：张力地图（Tension Map）",
        depth_label="张力深度",
        output_goal="open disputes、声称进展与实际进展的落差、冷场方向，以及 community 心照不宣的问题。",
        length_hint="建议 4000-8000 字；每条张力都要标注置信度。",
        avoid=(
            "不要只按 citation popularity 排名。",
            "不要把所有 challenge 都当成真实争论。",
            "不要省略每条判断的不确定性。",
        ),
        completion_tests=(
            "读到新论文时，能说出 community 可能如何分裂地评价它。",
            "能说出该领域未来 2 年最可能发生的 framework shift。",
            "能把一个 open dispute 拆成双方主张、证据、盲点和你自己的站位。",
        ),
        interaction_prompts=(
            "先写下 2-3 个你对这个领域不舒服的地方；如果写不出，回到 landscape 层。",
            "为每个候选 dispute 标注你是否相信它是真争论，并写一句理由。",
            "选一个“声称已解决”的进展，指出它最可能没兑现的承诺。",
        ),
        query_specs=(
            ("open-challenges", "{domain} open challenges limitations", "寻找显性 open problem 与 limitation。"),
            ("critique", "{domain} critique debate limitations benchmark", "寻找批评、争论和 benchmark 质疑。"),
            ("failure-cases", "{domain} failure cases robustness generalization", "寻找失效模式和泛化问题。"),
            ("negative-results", "{domain} negative results ablation analysis", "寻找低热度但有判断价值的反例。"),
            ("benchmark-overfit", "{domain} benchmark overfitting shortcut bias", "寻找评价环境失真或过拟合信号。"),
            ("underexplored", "{domain} underexplored abandoned direction", "寻找被放弃或冷场方向。"),
        ),
        default_limit=8,
    ),
}


def validate_level(level: str) -> HandoutLevel:
    if level not in LEVEL_SPECS:
        allowed = ", ".join(LEVEL_ORDER)
        raise ValueError(f"Unsupported handout level: {level}. Expected one of: {allowed}.")
    return level  # type: ignore[return-value]


def domain_slug(domain: str) -> str:
    normalized = slugify(domain)
    if normalized:
        return normalized[:64]
    digest = hashlib.sha1(domain.strip().encode("utf-8")).hexdigest()[:10]
    return f"domain-{digest}"


def default_handout_dir(domain: str, level: HandoutLevel) -> Path:
    return Path("handouts") / f"{domain_slug(domain)}-{level}"


def build_handout_queries(domain: str, level: HandoutLevel) -> list[HandoutQuery]:
    spec = LEVEL_SPECS[level]
    normalized_domain = " ".join(domain.split())
    if not normalized_domain:
        raise ValueError("domain must not be empty.")

    queries: list[HandoutQuery] = []
    for index, (purpose, template, rationale) in enumerate(spec.query_specs, start=1):
        query_text = template.format(domain=normalized_domain)
        queries.append(
            HandoutQuery(
                query_id=f"{level}_{index:02d}_{purpose}",
                query_text=query_text,
                purpose=purpose,
                rationale=rationale,
            )
        )
    return queries


def load_crawl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def paper_key(paper: dict[str, Any]) -> str:
    paper_id = paper.get("paperId") or paper.get("paper_id")
    if paper_id:
        return f"paper:{paper_id}"
    title = normalize_text(str(paper.get("title") or "")).lower()
    year = paper.get("year") or ""
    return f"title:{title}|year:{year}"


def author_names(authors: Any, limit: int = 3) -> str:
    if not authors:
        return ""
    if not isinstance(authors, list):
        authors = [authors]
    names: list[str] = []
    for author in authors:
        if isinstance(author, dict):
            name = author.get("name")
        else:
            name = str(author)
        if name:
            names.append(str(name))
        if len(names) >= limit:
            break
    suffix = " et al." if len(authors) > limit else ""
    return ", ".join(names) + suffix


def citation_count(paper: dict[str, Any]) -> int:
    value = paper.get("citationCount", paper.get("citation_count", 0))
    return int(value or 0)


def paper_year(paper: dict[str, Any]) -> int:
    value = paper.get("year")
    return int(value or 0)


def collect_papers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for record in records:
        query_id = str(record.get("query_id") or "")
        query_text = str(record.get("query_text") or "")
        for rank, paper in enumerate(record.get("papers") or [], start=1):
            if not isinstance(paper, dict):
                continue
            key = paper_key(paper)
            if key not in by_key:
                by_key[key] = {
                    "paper": paper,
                    "query_hits": [],
                }
            by_key[key]["query_hits"].append(
                {
                    "query_id": query_id,
                    "query_text": query_text,
                    "rank": rank,
                }
            )

    items = list(by_key.values())
    items.sort(
        key=lambda item: (
            len(item["query_hits"]),
            citation_count(item["paper"]),
            paper_year(item["paper"]),
        ),
        reverse=True,
    )
    return items


def extract_candidate_terms(papers: list[dict[str, Any]], limit: int = 30) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "based",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "learning",
        "method",
        "methods",
        "model",
        "models",
        "of",
        "on",
        "or",
        "paper",
        "study",
        "survey",
        "the",
        "to",
        "towards",
        "using",
        "via",
        "with",
    }
    counter: Counter[str] = Counter()
    for item in papers:
        paper = item["paper"]
        text = f"{paper.get('title') or ''}. {paper.get('abstract') or ''}"
        for match in re.findall(r"\b[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3}\b", text):
            words = [word.lower() for word in match.split()]
            if len(words) == 1 and (words[0] in stopwords or len(words[0]) < 4):
                continue
            if words[0] in stopwords or words[-1] in stopwords:
                continue
            phrase = " ".join(match.split())
            counter[phrase] += 1
    return [term for term, _ in counter.most_common(limit)]


def render_paper_line(item: dict[str, Any], rank: int) -> str:
    paper = item["paper"]
    title = normalize_text(str(paper.get("title") or "Untitled"))
    year = paper.get("year") or "n.d."
    venue = normalize_text(str(paper.get("venue") or ""))
    authors = author_names(paper.get("authors") or [])
    citations = citation_count(paper)
    url = paper.get("url") or ""
    hit_count = len(item["query_hits"])
    parts = [f"{rank}. {title}", f"{year}", f"citations={citations}", f"query_hits={hit_count}"]
    if venue:
        parts.append(venue)
    if authors:
        parts.append(authors)
    if url:
        parts.append(str(url))
    return "- " + " | ".join(parts)


def render_level_body(domain: str, level: HandoutLevel, papers: list[dict[str, Any]]) -> str:
    spec = LEVEL_SPECS[level]
    top_papers = papers[:50]
    candidate_terms = extract_candidate_terms(top_papers)

    if level == "terminology":
        term_lines = "\n".join(f"- {term}" for term in candidate_terms[:30]) or "- 暂无候选术语；先检查检索结果。"
        return f"""## 讲义正文骨架

### 1. 核心术语候选

下面术语候选来自标题和摘要的轻量抽取。写最终讲义时保留 20-40 个，并为每个术语补齐“定义 / 容易混淆对象 / 边界判断”。

{term_lines}

### 2. 术语区分矩阵

按 `{domain}` 的语义距离选择 8-12 组 close terms。每组写三列：共同点、差异点、误用后果。

### 3. 读 abstract 前的最小词典

最终讲义应让读者读完后能直接进入论文 abstract。避免代表工作谱系，只保留理解标题、摘要和实验设置所需的词汇。
"""

    if level == "landscape":
        return f"""## 讲义正文骨架

### 1. 方法家族

从证据池中归纳 3-5 个 `{domain}` 主流方法家族。每个家族保留：核心假设、代表工作、近年演进、它解决和回避的问题。

### 2. 评价环境

列出主要 benchmark、metric、默认实验设定。写清楚每个评价设置偏向哪类方法，以及哪些能力没有被测到。

### 3. 非线性时间线

按 5-8 年窗口写“焦点迁移”：哪些年份大家集中做什么，哪篇或哪类论文改变了问题表述，基础模型或数据集变化如何让旧问题重新变热。

### 4. 代表人物和实验室

每个方法家族列 2-3 个代表人物/实验室。重点不是名录，而是解释他们的工作为什么定义了该家族的走向。
"""

    return f"""## 讲义正文骨架

### 1. Open disputes

为 `{domain}` 选择 5-10 个真实争论。每条必须写：双方主张、双方代表论文、争论为什么还没有被解决、置信度。

### 2. 声称的进展 vs 实际进展

列 3-5 个“community 宣称 X 已解决，但 Y 仍未兑现”的候选。每条都要说明证据来自哪些论文，而不是只写直觉。

### 3. 冷场或被放弃方向

列 2-4 个曾经被看好但近年冷场的方向，解释放弃原因，以及这些原因在今天是否仍成立。

### 4. 心照不宣的问题

列 1-3 个不一定会写进正式 survey 的问题，例如 benchmark overfit、评价口径失真、实验设定绕开真实困难。每条都要标注低/中/高置信度。
"""


def render_handout_report(
    *,
    domain: str,
    level: HandoutLevel,
    queries: list[HandoutQuery],
    results_path: Path,
    failures_path: Path,
    crawl_summary: dict[str, int | bool],
) -> str:
    spec = LEVEL_SPECS[level]
    records = load_crawl_records(results_path)
    failures = load_crawl_records(failures_path)
    papers = collect_papers(records)
    query_lines = "\n".join(
        f"- `{query.query_id}`: {query.query_text}  \n  目的：{query.rationale}" for query in queries
    )
    evidence_lines = "\n".join(render_paper_line(item, rank) for rank, item in enumerate(papers[:50], start=1))
    if not evidence_lines:
        evidence_lines = "- 暂无成功检索结果；重新运行同一命令会跳过已成功项并重试失败项。"

    failure_lines = "\n".join(
        f"- `{record.get('query_id')}`: {record.get('error_type')} - {record.get('error')}" for record in failures
    )
    if not failure_lines:
        failure_lines = "- 无。"

    avoid_lines = "\n".join(f"- {item}" for item in spec.avoid)
    interaction_lines = "\n".join(f"- {item}" for item in spec.interaction_prompts)
    completion_lines = "\n".join(f"- {item}" for item in spec.completion_tests)
    crawl_summary_json = json.dumps(crawl_summary, ensure_ascii=False, indent=2)
    generated_at = utc_now()

    return f"""# {domain} 讲义：{spec.title}

生成时间：{generated_at}

## 层级目标

- 认知层级：{spec.depth_label}
- 产物目标：{spec.output_goal}
- 长度边界：{spec.length_hint}

## 不要做

{avoid_lines}

## 检索策略

本文件由 `autoscholar handout init` 生成。检索使用 AutoScholar 的 checkpointed Semantic Scholar crawl：成功结果写入 `{results_path.as_posix()}`，失败项写入 `{failures_path.as_posix()}`。再次运行同一命令会跳过同一检索签名下已成功的 query，并重试失败或未完成 query。

{query_lines}

检索摘要：

```json
{crawl_summary_json}
```

## 证据池

{evidence_lines}

## 失败或待重试检索

{failure_lines}

{render_level_body(domain, level, papers)}

## 互动问题

{interaction_lines}

## 完成度测试

{completion_lines}

## 写作要求

- 最终讲义必须显式写明这是第几层，不要把三层混成一份泛综述。
- 每个关键判断都要能回到证据池中的论文或检索 query。
- 保留互动问题和完成度测试，让读者能判断自己是否真正抵达本层。
- 如果证据池不足，先扩展 query 或重跑 crawl，不要用泛泛常识补齐关键结论。
"""


def init_handout(
    *,
    domain: str,
    level: HandoutLevel,
    output_dir: Path | None = None,
    run_crawl: bool = True,
    endpoint: str = "relevance",
    limit: int | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    retry_delay: float = 120.0,
    pause_seconds: float = 10.0,
    retry_failed: bool = True,
    max_queries: int | None = None,
    until_complete: bool = True,
    round_delay: float = 300.0,
    max_rounds: int | None = None,
    year: str | None = None,
    sort: str | None = None,
    venue: str | None = None,
) -> HandoutRunSummary:
    level = validate_level(level)
    spec = LEVEL_SPECS[level]
    root = output_dir or default_handout_dir(domain, level)
    queries = build_handout_queries(domain, level)
    queries_path = root / "queries.jsonl"
    results_path = root / "artifacts" / "semantic_results.jsonl"
    failures_path = root / "artifacts" / "semantic_failures.jsonl"
    report_path = root / "reports" / "handout.md"

    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    write_yaml(
        root / "handout.yaml",
        {
            "schema_version": "1",
            "domain": domain,
            "level": level,
            "level_title": spec.title,
            "created_at": utc_now(),
            "artifacts": {
                "queries": queries_path.relative_to(root).as_posix(),
                "semantic_results": results_path.relative_to(root).as_posix(),
                "semantic_failures": failures_path.relative_to(root).as_posix(),
            },
            "reports": {
                "handout": report_path.relative_to(root).as_posix(),
            },
        },
    )
    write_jsonl_records(queries_path, [query.as_record() for query in queries])

    crawl_summary: dict[str, int | bool]
    if run_crawl:
        config = SemanticCrawlConfig(
            output=results_path,
            failures=failures_path,
            endpoint=endpoint,
            limit=limit or spec.default_limit,
            fields=HANDOUT_FIELDS,
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
        crawl_summary = crawl_semantic_queries(
            [query.as_semantic_query() for query in queries],
            config,
        )
    else:
        existing_success = len(load_crawl_records(results_path))
        existing_failure = len(load_crawl_records(failures_path))
        crawl_summary = {
            "total": len(queries),
            "processed": 0,
            "skipped": 0,
            "success": 0,
            "failure": 0,
            "completed": existing_success,
            "remaining": max(0, len(queries) - existing_success),
            "complete": existing_success >= len(queries),
            "rounds": 0,
            "until_complete": until_complete,
            "max_rounds_reached": False,
            "stored_success": existing_success,
            "stored_failure": existing_failure,
        }

    write_text(
        report_path,
        render_handout_report(
            domain=domain,
            level=level,
            queries=queries,
            results_path=results_path,
            failures_path=failures_path,
            crawl_summary=crawl_summary,
        ),
    )
    return HandoutRunSummary(
        domain=domain,
        level=level,
        root=root,
        report_path=report_path,
        queries_path=queries_path,
        results_path=results_path,
        failures_path=failures_path,
        crawl_summary=crawl_summary,
    )
