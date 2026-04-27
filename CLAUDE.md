# AutoScholar v2 — CLAUDE.md

结构化学术研究工具包。Python CLI (`autoscholar`) + AI agent skills 驱动六条工作流。

## 关键约定

- **工作区输出全部在 `workspaces/`**，已被 `.claudeignore` 排除，不要主动读取旧工作区文件，除非用户明确要求。
- **Skills 定义在 `.agents/skills/<name>/SKILL.md`**，每条工作流的行为规范在此，先读再动手。
- **代码在 `src/autoscholar/`**，CLI 入口是 `src/autoscholar/cli.py`，以 `autoscholar <subcommand>` 形式调用。

## Python 环境

`autoscholar` 包**未安装**到任何 conda 环境（网络离线，`pip install` 无法拉取依赖）。调用方式：

```bash
PYTHONPATH=/home/yingjun/.conda/envs/wind/lib/python3.9/site-packages:/home/yingjun/data/auto_scholar2.0版/src \
~/.conda/envs/yingjun/bin/python3 -c "..."
```

- `~/.conda/envs/yingjun`：有 pydantic / yaml / jinja2 / requests，**没有** httpx / typer。
- `~/.conda/envs/wind/lib/python3.9/site-packages`：有 httpx（0.28.1）及其依赖（httpcore / anyio / h11）。
- 两者合并即可满足 autoscholar 全部运行时依赖（CLI 的 typer 除外）。
- **不要尝试 `pip install`**，网络离线，会超时报错。

## 检索渠道

### OpenAlex（优先）

- 匿名访问无限速，稳定可用。
- 模块：`src/autoscholar/openalex_crawl.py`，客户端：`src/autoscholar/integrations/openalex.py`。
- **查询要领**：机器学习类话题必须用领域专属短语（`catastrophic forgetting neural networks`），不能用泛化词（`incremental learning`）——后者会被 OpenAlex 匹配到教育学、政策学等无关论文。需要时加 `filters="publication_year:>2015"` 限定深度学习时代。

### Semantic Scholar（备用）

- 匿名访问频繁触发 429；有 `S2_API_KEY` 环境变量时可正常使用。
- 模块：`src/autoscholar/semantic_crawl.py`，客户端：`src/autoscholar/integrations/semantic_scholar.py`。
- 断点续跑已内置：每条 query 执行后即时落盘，重跑同一命令自动跳过已完成项。
- `until_complete=True`（`init_handout` 默认值）会循环直到所有 query 成功；`round_delay=300` 给限速恢复时间。
- 遇到 429 时不要删 artifacts，降速重跑即可（`--max-queries 1 --round-delay 300`）。

## Handout Skill 使用方式

标准调用（`autoscholar` 命令不可用时）：

```python
PYTHONPATH=... python3 - << 'EOF'
from pathlib import Path
from autoscholar.handout import build_handout_queries, render_handout_report
from autoscholar.openalex_crawl import OpenAlexQuery, OpenAlexCrawlConfig, crawl_openalex_queries
from autoscholar.io import write_text

domain = "..."
level  = "terminology"   # or "landscape" / "tension"
root   = Path("workspaces/handout/<slug>-<level>")
results_path  = root / "artifacts" / "openalex_results.jsonl"
failures_path = root / "artifacts" / "openalex_failures.jsonl"
report_path   = root / "reports"   / "handout_openalex.md"
root.mkdir(parents=True, exist_ok=True)
(root / "artifacts").mkdir(exist_ok=True)
(root / "reports").mkdir(exist_ok=True)

queries = [OpenAlexQuery("id_01", "query text one"), ...]
config  = OpenAlexCrawlConfig(output=results_path, failures=failures_path, limit=12, pause_seconds=1.5)
summary = crawl_openalex_queries(queries, config)

handout_queries = build_handout_queries(domain, level)
report = render_handout_report(domain=domain, level=level, queries=handout_queries,
                               results_path=results_path, failures_path=failures_path,
                               crawl_summary=summary)
write_text(report_path, report)
EOF
```

然后读 `reports/handout_openalex.md` 中的证据池，综合输出 `reports/final_handout.md`。

## 工作流速查

| 工作流 | Skill | 关键命令 |
|---|---|---|
| 引用文献 | `citation-workflow` | `citation search / prescreen / correct / shortlist / bib` |
| 想法评估 | `idea-evaluation` | `citation search … → idea assess → report render` |
| 想法孵化 | `idea-creation-v2` | 人机对话驱动，CLI 只做 init 和 report |
| 领域速览 | `handout` | `handout init "<domain>" --level <level>` |
| 期刊匹配 | `journal-fit-advisor` | `jfa init → jfa run` |
| 触发推送 | `triggered-push` | `trigger init → trigger push --paradigm <p>` |

## 测试

```bash
~/.conda/envs/yingjun/bin/python3 -m pytest tests/ -x -q
```

Live smoke tests（需要 `S2_API_KEY`）：`pytest -m live`，无 key 时自动跳过。
