# AutoScholar

AutoScholar 是一个面向学术写作与研究构思的工具仓库，当前主要覆盖两条工作流：

1. **论文引文补全工作流**：从草稿中的 claim 出发，批量检索 Semantic Scholar，筛选候选文献，生成推荐列表与 `BibTeX`。
2. **研究创意与新颖性验证工作流**：从种子论文出发，挖掘隐含假设，生成创新方向，并用 Semantic Scholar 做可恢复的新颖性检索验证。

这个仓库更像一套可复用的 **研究辅助工具链**，而不是某一篇论文本身的内容仓库。

## 主要能力

### 1. Claim-first 引文补全

围绕“一个 claim 对应一组可检索证据”的思路，支持以下步骤：

- 从手稿中整理需要文献支持的 claim
- 为每个 claim 准备 2~3 条学术检索 query
- 批量调用 Semantic Scholar 搜索
- 对多 query 结果做去重与初筛
- 对弱检索 claim 追加 recommendation 扩展
- 生成 claim 级推荐文献清单
- 生成最终 `references.bib`

### 2. 创新方向生成与新颖性验证

围绕“先拆论文隐含假设，再打破假设找创新”的思路，支持以下步骤：

- 解析种子论文的问题设定与方法
- 挖掘显式/隐式 assumptions
- 生成 innovation candidates
- 为每个 candidate 构造 novelty search queries
- 以可断点恢复方式运行 Semantic Scholar 新颖性验证

## 仓库结构

```text
AutoScholar/
├── SemanticScholarApi/          # 本地 Semantic Scholar API 客户端
├── scripts/                     # 主工作流脚本
├── config/                      # 可复用 YAML 配置
├── .agents/skills/              # agent/skill 说明与辅助资料
├── PAPER_WORKFLOW.md            # 引文工作流详细说明
├── SKILL.md                     # 创意生成工作流说明
└── README.md
```

## 关键目录说明

- `SemanticScholarApi/api.py`：封装 Semantic Scholar Graph API / Recommendations API 的本地客户端。
- `scripts/`：主要执行入口，涵盖搜索、去重、推荐修正、BibTeX 生成、PDF 转文本、新颖性验证等。
- `config/`：推荐规则与 recommendation correction 配置。
- `PAPER_WORKFLOW.md`：论文引文补全的完整流程说明。
- `SKILL.md`：从种子论文生成创新点与做 novelty verification 的流程说明。
- `.agents/skills/semantic_scholar_api/SKILL.md`：本地 Semantic Scholar skill 的用法说明。
- `.agents/skills/idea-creation/`：创意生成 skill 的补充资源与参考模板。

## 环境要求

推荐使用 Python 3.10+。

常用依赖包括：

- `requests`
- `PyYAML`
- `PyMuPDF`

示例安装：

```powershell
pip install requests pyyaml pymupdf
```

## API Key

仓库默认读取环境变量 `S2_API_KEY` 作为 Semantic Scholar API Key。

- 不设置也可以运行，但更容易遇到限流。
- Recommendation 与批量搜索场景更建议配置 API Key。

PowerShell 示例：

```powershell
$env:S2_API_KEY = "your_api_key"
```

## 工作区约定

大多数脚本默认围绕仓库根目录下的 `paper/` 工作区运行。

这个目录通常存放某一篇论文或某一次研究构思的中间产物，例如：

```text
paper/
├── paper.tex
├── citation_claim_units.md
├── search_keyword_prep.md
├── semantic_scholar_search.yaml
├── semantic_scholar_raw_results.jsonl
├── semantic_scholar_raw_results_deduped.jsonl
├── semantic_scholar_prescreen.md
├── claim_recommended_citations.md
├── references.bib
├── seed_paper.md
├── assumptions.json
├── innovation_candidates.json
└── novelty_verification.json
```

注意：

- `.gitignore` 默认忽略整个 `paper/` 目录。
- 仓库更适合提交工具代码与流程文档，不适合提交每篇论文的工作中间文件。
- `.gitignore` 也忽略 `*.txt`，因此 `pdf_to_text.py` 生成的文本通常不会进入版本控制。

## 核心脚本总览

### 引文补全相关

- `scripts/batch_semantic_scholar_search.py`
  - 从 `paper/semantic_scholar_search.yaml` 读取配置
  - 批量执行 claim query 搜索
  - 输出 `paper/semantic_scholar_raw_results.jsonl` 和失败记录

- `scripts/dedupe_and_prescreen_semantic_scholar.py`
  - 对原始检索结果去重
  - 生成 `paper/semantic_scholar_raw_results_deduped.jsonl`
  - 生成 `paper/semantic_scholar_prescreen.md`

- `scripts/recommendation_auto_correct.py`
  - 针对弱检索或混杂检索的 claim 做 recommendation 扩展
  - 可先 `--dry-run` 只评估触发条件与 seed 选择
  - 输出 correction `jsonl` 与 review report

- `scripts/generate_claim_recommendation_list.py`
  - 基于 deduped 结果与规则文件生成 claim 级推荐文献清单
  - 默认输出 `paper/claim_recommended_citations.md`

- `scripts/generate_references_bib.py`
  - 从推荐结果重建选中文献集合
  - 生成 `paper/references.bib`

### 创意生成 / 新颖性验证相关

- `scripts/resumable_novelty_verification.py`
  - 针对 `paper/innovation_candidates.json` 执行新颖性验证
  - 支持 checkpoint/state 文件，可恢复运行
  - 默认输出 `paper/novelty_verification.json`

### 辅助工具

- `scripts/pdf_to_text.py`
  - 将 PDF 提取为可读纯文本
  - 适合先把论文转成 `.txt`，再做 claim 提取或 seed paper 解析

## 快速开始

### 场景 A：为论文草稿补参考文献

#### 1. 准备 `paper/` 工作区

至少准备以下文件：

- `paper/citation_claim_units.md`
- `paper/search_keyword_prep.md`
- `paper/semantic_scholar_search.yaml`

其中：

- `citation_claim_units.md` 用于定义 claim 列表
- `search_keyword_prep.md` 用于定义 claim 对应的 query 表
- `semantic_scholar_search.yaml` 用于配置检索参数

#### 2. 运行批量搜索

```powershell
python scripts\batch_semantic_scholar_search.py
```

#### 3. 去重并生成初筛报告

```powershell
python scripts\dedupe_and_prescreen_semantic_scholar.py
```

#### 4. 对弱检索 claim 做 recommendation 扩展

先 dry run：

```powershell
python scripts\recommendation_auto_correct.py --dry-run
```

再正式运行：

```powershell
python scripts\recommendation_auto_correct.py
```

#### 5. 生成 claim 级推荐清单

```powershell
python scripts\generate_claim_recommendation_list.py
```

如果你想使用其他规则文件：

```powershell
python scripts\generate_claim_recommendation_list.py config\claim_recommendation_rules.yaml
```

#### 6. 生成 `BibTeX`

```powershell
python scripts\generate_references_bib.py
```

最终你会得到：

- `paper/semantic_scholar_prescreen.md`
- `paper/claim_recommended_citations.md`
- `paper/references.bib`

### 场景 B：从种子论文生成研究创意

#### 1. 准备种子论文输入

你可以直接准备：

- `paper/seed_paper.md`

如果你手上只有 PDF，可先转文本：

```powershell
python scripts\pdf_to_text.py paper\seed_paper.pdf
```

#### 2. 按 `SKILL.md` 的流程生成中间文件

`SKILL.md` 定义了这一整条流程的数据契约，典型输出包括：

- `paper/parsed_paper.json`
- `paper/assumptions.json`
- `paper/paradigm_gap_check.json`
- `paper/innovation_candidates.json`
- `paper/idea_cards.md`

#### 3. 运行可恢复的新颖性验证

```powershell
python scripts\resumable_novelty_verification.py
```

常见用途：

- 只验证部分 candidate：

```powershell
python scripts\resumable_novelty_verification.py --candidate-id C1 --candidate-id C3
```

- 重新跑失败项：

```powershell
python scripts\resumable_novelty_verification.py --refresh-failed
```

主要输出：

- `paper/novelty_verification_state.json`
- `paper/novelty_verification.json`

## 搜索配置说明

`scripts/batch_semantic_scholar_search.py` 默认读取：

- `paper/semantic_scholar_search.yaml`

推荐使用如下分组结构：

```yaml
paths:
  input: search_keyword_prep.md
  output: semantic_scholar_raw_results.jsonl
  failures: semantic_scholar_failures.jsonl

run:
  claim_ids: []
  dry_run: false

search:
  endpoint: relevance
  limit: 10
  timeout: 30
  fields: paperId,title,year,authors,url,abstract,citationCount,influentialCitationCount,venue,externalIds,isOpenAccess,openAccessPdf
  filters:
    sort:
    publication_types: []
    open_access_pdf:
    min_citation_count:
    publication_date_or_year:
    year:
    venue:
    fields_of_study: []

execution:
  mode: single_thread
  single_thread:
    workers: 1
    max_retries: 30
    retry_delay: 1.0
    pause_seconds: 1.0
  multi_thread:
    workers: 8
    max_retries: 30
    retry_delay: 1.0
    pause_seconds: 0.0
```

脚本仍兼容旧的扁平配置键，但新的 grouped YAML 结构更适合作为长期维护格式。

## 规则配置说明

### `config/claim_recommendation_rules.yaml`

用于控制推荐列表生成逻辑，主要包括：

- `excluded_queries`：排除明显不适合的 query
- `excluded_papers`：排除明显离题的 paper
- `claim_notes`：记录需要人工注意的 claim 备注
- `selected_papers_limit`：每个 claim 最多输出多少篇主推荐
- `query_status_weights` 与 `score_weights`：推荐排序权重

### `config/recommendation_auto_correct.yaml`

用于控制 recommendation correction 流程，主要包括：

- 输入输出路径
- 触发阈值
- seed 选择模式
- recommendation 调用方式
- 每个 claim 保留多少 correction candidates

## 本地 API 客户端

`SemanticScholarApi/api.py` 提供统一的本地客户端，支持常见能力，包括：

- 按 paper id 获取论文详情
- 按 query 搜索论文
- 批量获取论文信息
- 获取 citations / references
- 获取 recommendations
- 下载 Open Access PDF

适合你在脚本里直接复用，而不是每次手写 HTTP 请求。

## 文档入口

- `README.md`：项目总览
- `PAPER_WORKFLOW.md`：引文补全工作流详细说明
- `SKILL.md`：创意生成与新颖性验证详细说明
- `.agents/skills/semantic_scholar_api/SKILL.md`：Semantic Scholar API skill 说明

## 项目定位

这个仓库目前的定位很明确：

- **保存工具，不保存具体论文内容**
- **保存流程约定，不保存一次性中间产物**
- **保存可复用脚本，不把人工判断完全黑箱自动化**

尤其在 recommendation 扩展和 claim 引文选择阶段，仓库设计默认“人机协同”，而不是无审查自动插引文。

## 后续可扩展方向

- 增加统一的 `requirements.txt` 或 `pyproject.toml`
- 为 `paper/` 提供标准化 starter template
- 增加 citation insertion audit 工具
- 增加更完整的 BibTeX 元数据补全
- 让更多脚本显式支持自定义输入输出路径
