# AutoScholar 项目 Skills 工作流说明

这份文档整理了仓库内 6 个本地 skill 的大致工作流程，覆盖它们各自的职责、输入输出、执行顺序，以及彼此之间怎么衔接。

整理依据主要来自：

- `.agents/skills/*/SKILL.md`
- 各 skill 下的 `references/*.md`
- `src/autoscholar/cli.py`
- `src/autoscholar/workspace.py`
- `src/autoscholar/journal_fit/*`

## 1. 先看整体：这些 skill 在项目里分别负责什么

AutoScholar 不是“一个 prompt 干到底”的仓库，它更像一个按阶段拆开的工作流系统：

1. `autoscholar` 负责总入口和路由。
2. `citation-workflow` 负责 claim-first 的检索、预筛、纠偏、短名单和 BibTeX。
3. `idea-evaluation` 在已有证据的基础上评估一个研究方向值不值得做。
4. `report-authoring` 把前面沉淀下来的结构化证据渲染成最终面向人的报告，并做校验。
5. `semantic-scholar-api` 提供底层 Semantic Scholar 查询和调试能力。
6. `journal-fit-advisor` 不再讨论“这个 idea 值不值得做”，而是面向“实验已经做完，论文该怎么讲、投什么刊”。

可以把整体链路理解成下面这样：

```text
autoscholar
  ├─ citation-workflow
  │    └─ 产出 selected_citations / references.bib / prescreen / shortlist
  ├─ idea-evaluation
  │    └─ 复用 citation-workflow 的证据，产出 idea_assessment / evidence_map
  │         └─ report-authoring
  │              └─ 产出 feasibility / deep_dive / validation
  ├─ semantic-scholar-api
  │    └─ 给 citation-workflow 和排障提供底层数据能力
  └─ journal-fit-advisor
       └─ 面向固定算法和固定实验的论文定位、叙事和期刊适配
```

## 2. AutoScholar 的统一工作区模型

除 `journal-fit-advisor` 外，其余几个主流程 skill 都依赖 AutoScholar 的显式 workspace。

标准 workspace 结构：

```text
workspace/
  ├─ workspace.yaml
  ├─ inputs/
  ├─ configs/
  ├─ artifacts/
  └─ reports/
```

几个关键约束：

- `workspace.yaml` 是逻辑路径的单一来源。
- `artifacts/*.jsonl`、`artifacts/*.json` 是上游真值。
- `reports/*.md` 是渲染产物，不应反向当作结构化输入。
- workspace 可以放在仓库外部，不要求数据直接塞在 repo 里。

常用初始化命令：

```powershell
autoscholar workspace init D:\workspaces\demo --template citation-paper --reports-lang zh
autoscholar workspace doctor --workspace D:\workspaces\demo
```

`workspace init` 当前支持两个模板：

- `citation-paper`
- `idea-evaluation`

## 3. `autoscholar`：总入口和能力路由 skill

### 3.1 它的定位

`autoscholar` 是仓库的总入口 skill。它本身不代表一条很长的业务流水线，而是负责：

- 帮用户选对下游 skill
- 初始化和检查 workspace
- 统一要求尽量走 `autoscholar` CLI，而不是临时脚本
- 强调结构化 artifact 才是可信上游

### 3.2 什么时候应该用它

适合下面几类场景：

- 你刚开始接触这个仓库，不知道该走哪条流程
- 你需要先创建一个合规 workspace
- 你想把“查文献 / 评估 idea / 渲染报告 / Semantic Scholar 调试”串起来
- 你只是知道目标，不知道该叫哪个下游 skill

### 3.3 它的大致工作流程

1. 判断任务属于哪条能力线。
2. 如果还没有 workspace，先执行 `workspace init`。
3. 用 `workspace doctor` 检查 manifest、配置和已有 artifact 是否可用。
4. 把任务路由到具体子 skill：
   - 文献证据收集 -> `citation-workflow`
   - idea 可行性判断 -> `idea-evaluation`
   - 最终报告产出 -> `report-authoring`
   - 底层 Semantic Scholar 查询/排障 -> `semantic-scholar-api`
5. 在整个过程中持续坚持“JSONL/JSON/YAML 为真值，Markdown 为输出”的 operating model。

### 3.4 典型输入与输出

输入：

- 用户目标
- workspace 路径
- workspace 模板类型

输出：

- 一个可用 workspace
- 一条被正确分发的后续流程
- 对当前数据状态的校验结果

### 3.5 常用命令

```powershell
autoscholar workspace init <dir> --template citation-paper --reports-lang zh
autoscholar workspace init <dir> --template idea-evaluation --reports-lang zh
autoscholar workspace doctor --workspace <dir>
autoscholar semantic paper CorpusID:123
autoscholar util pdf-to-text D:\papers\sample.pdf
```

## 4. `citation-workflow`：claim-first 引文工作流

### 4.1 它的定位

这是 AutoScholar 最核心的证据收集链路。它不是先“广撒网找文献”，而是先把要支持的 claim 结构化，再围绕 claim 组织 query、检索、筛选和推荐纠偏。

### 4.2 它解决什么问题

- 某个论断需要论文支持
- 想把零散检索变成可重复执行的结构化检索流程
- 需要从检索结果里得到 shortlist 和 BibTeX
- 想把“检索质量差”的情况显式识别出来并补救

### 4.3 前置条件

通常需要一个 `citation-paper` 或 `idea-evaluation` workspace，并至少准备好：

- `artifacts/claims.jsonl`
- `artifacts/queries.jsonl`
- `configs/search.yaml`
- `configs/recommendation.yaml`
- `configs/citation_rules.yaml`

### 4.4 它的标准工作流程

#### 第 1 步：准备 claim 和 query

先把目标拆成结构化 claim，再给每个 claim 配搜索 query。这里强调的是 JSONL，而不是在 Markdown 里随手写几段描述。

#### 第 2 步：执行检索

运行：

```powershell
autoscholar citation search --workspace <dir>
```

这一步会调用检索层，把原始结果写入：

- `artifacts/search_results.raw.jsonl`
- `artifacts/search_results.deduped.jsonl`
- `artifacts/search_failures.jsonl`

#### 第 3 步：做 prescreen

运行：

```powershell
autoscholar citation prescreen --workspace <dir>
```

这一层的目的不是直接选最终论文，而是判断当前 query 集是否“可用”。输出主要是：

- `artifacts/query_reviews.json`

这里的结果会告诉你：

- 哪些 query 值得保留
- 哪些 query 应该重写
- 哪些 query 应该排除

#### 第 4 步：在检索弱或混杂时做 correction

运行：

```powershell
autoscholar citation correct --workspace <dir>
```

这是一个“纠偏”步骤，不是默认总要做的大动作。它的使用条件是：当前检索结果弱、杂、交叉支持不足，值得额外引入推荐机制。

输出：

- `artifacts/recommendation_corrections.jsonl`

要点是：

- correction 只会补充候选证据
- correction 不会直接覆盖 shortlist

#### 第 5 步：生成 shortlist

运行：

```powershell
autoscholar citation shortlist --workspace <dir>
```

这一层才是 claim 级别的推荐结果。输出：

- `artifacts/selected_citations.jsonl`

这个文件很关键，后续多个流程都会直接依赖它。

#### 第 6 步：生成 BibTeX

运行：

```powershell
autoscholar citation bib --workspace <dir>
```

输出：

- `artifacts/references.bib`

BibTeX 的上游真值不是 raw search result，而是 `selected_citations.jsonl`。

#### 第 7 步：按需渲染报告

在结构化 artifact 已经齐备后，才渲染人类可读报告：

```powershell
autoscholar report render --workspace <dir> --kind prescreen
autoscholar report render --workspace <dir> --kind shortlist
```

### 4.5 这个 skill 的核心产物

- `search_results.raw.jsonl`
- `search_results.deduped.jsonl`
- `query_reviews.json`
- `recommendation_corrections.jsonl`
- `selected_citations.jsonl`
- `references.bib`
- `reports/prescreen.md`
- `reports/shortlist.md`

### 4.6 它和其他 skill 的关系

- 它通常是 `idea-evaluation` 的上游证据来源。
- 它也能单独使用，只做 citation 支持，不继续做 idea 评估。
- 底层检索异常时，常要借助 `semantic-scholar-api` 做排障。

## 5. `idea-evaluation`：研究方向/想法评估

### 5.1 它的定位

`idea-evaluation` 的任务不是找一篇论文引用，而是对一个研究 idea 做结构化判断：是否值得推进，证据强弱如何，主要风险在哪，下一步应该怎么收窄。

### 5.2 什么时候应该用它

适合下面这些问题：

- 这个研究方向值不值得做
- 这个题目是否已经被做穿了
- 现有证据能否支持“继续推进 / 需要修订 / 不建议继续”
- 我需要一份 feasibility / deep-dive 报告草稿

### 5.3 前置条件

一般需要先创建 `idea-evaluation` 类型的 workspace：

```powershell
autoscholar workspace init <dir> --template idea-evaluation --reports-lang zh
```

然后至少准备：

- `inputs/idea_source.md`
- `artifacts/claims.jsonl`
- `artifacts/queries.jsonl`
- `configs/idea_evaluation.yaml`

并且通常需要先跑完 citation 流程，尤其拿到：

- `artifacts/selected_citations.jsonl`

### 5.4 它的标准工作流程

#### 第 1 步：初始化 idea-evaluation workspace

这个模板会自动准备：

- `inputs/idea_source.md`
- 一套 citation 相关 configs
- 一套 idea evaluation config
- 对应的 artifacts/report 路径

#### 第 2 步：填写 idea 源描述

在 `inputs/idea_source.md` 里写清：

- idea 是什么
- 来源是什么
- 想做的贡献是什么
- 与现有工作的差异假设是什么

#### 第 3 步：构建 claim/query 并复用 citation-workflow

这一步本质上仍然要回到 claim-first 检索：

```powershell
autoscholar citation search --workspace <dir>
autoscholar citation prescreen --workspace <dir>
autoscholar citation correct --workspace <dir>
autoscholar citation shortlist --workspace <dir>
```

也就是说，`idea-evaluation` 不是脱离 citation 独立运行的，它是建立在 citation 证据层之上的。

#### 第 4 步：执行 idea assess

运行：

```powershell
autoscholar idea assess --workspace <dir>
```

这一命令会做两件事：

1. 生成 `artifacts/idea_assessment.json`
2. 生成 `artifacts/evidence_map.json`

`idea_assessment.json` 是机器可读的主评估记录，文档里明确强调它才是上游真值。

#### 第 5 步：渲染两类报告

运行：

```powershell
autoscholar report render --workspace <dir> --kind feasibility
autoscholar report render --workspace <dir> --kind deep-dive
```

输出：

- `reports/feasibility.md`
- `reports/deep_dive.md`

#### 第 6 步：校验报告

运行：

```powershell
autoscholar report validate --workspace <dir> --kind feasibility
autoscholar report validate --workspace <dir> --kind deep-dive
```

输出：

- `artifacts/report_validation.json`

### 5.5 这个 skill 的核心产物

- `artifacts/idea_assessment.json`
- `artifacts/evidence_map.json`
- `reports/feasibility.md`
- `reports/deep_dive.md`
- `artifacts/report_validation.json`

其中 assessment 记录包含的关键字段包括：

- `idea_id`
- `title`
- `summary`
- `scores`
- `risks`
- `recommendation`
- `evidence`
- `next_actions`

### 5.6 它和其他 skill 的关系

- 它强依赖 `citation-workflow` 提供证据。
- 当用户更关心最终报告质量而不是中间流程时，通常会衔接到 `report-authoring`。
- 若 citation 检索层出了问题，底层排障通常仍需 `semantic-scholar-api`。

## 6. `report-authoring`：最终报告产出与校验

### 6.1 它的定位

这个 skill 的重点不在“把流程跑通”，而在“把已经有的结构化证据，整理成能交付给人看的最终报告，并确认报告可审计、可追溯”。

它更像是后处理与交付层。

### 6.2 什么时候应该用它

适合下面这些情况：

- citation 和 idea assessment 已经基本完成
- 用户要的是一份更像最终交付物的 feasibility / deep-dive 报告
- 用户关心叙事质量、章节完整性、证据追踪性

### 6.3 前置条件

这个 skill 明确要求 evidence pipeline 已经在位，至少要有：

- `inputs/idea_source.md`
- `artifacts/selected_citations.jsonl`
- `artifacts/idea_assessment.json`
- `artifacts/evidence_map.json`

如果这几个文件还不完整，先别急着润色 prose，先回去补 citation 或 reassess。

### 6.4 它的标准工作流程

#### 第 1 步：确认 citation 证据完整

至少确认 `selected_citations.jsonl` 已存在，因为它代表被真正选中的 claim-level 证据。

#### 第 2 步：刷新 assessment 和 evidence map

运行：

```powershell
autoscholar idea assess --workspace <dir>
```

即使你之前跑过一次，这里仍建议重新生成，确保报告引用的 assessment/evidence 是最新的。

#### 第 3 步：渲染目标报告

运行：

```powershell
autoscholar report render --workspace <dir> --kind feasibility
autoscholar report render --workspace <dir> --kind deep-dive
```

#### 第 4 步：执行校验

运行：

```powershell
autoscholar report validate --workspace <dir> --kind feasibility
autoscholar report validate --workspace <dir> --kind deep-dive
```

### 6.5 它对报告的要求

`report-authoring` 的 reference 文件对两类报告给了比较明确的验收面。

#### feasibility 报告至少要回答

- 当前推荐结论是什么
- 为什么这个方向仍值得推进
- 主要 gap 和 risk 在哪
- framing 应该怎样收窄
- 每个关键结论由哪些 claim-level evidence 和 top papers 支撑

#### deep-dive 报告至少要回答

- 一页式结论是什么
- 每个大 claim 的证据强度如何
- 论文应该把 framing 边界画到哪里
- 方法和实验优先级怎么排
- 什么能 claim，什么不该 claim
- 顶层证据论文的 digest 是什么

#### validate 阶段会检查什么

- 是否提到了足够的 claim ID，保证可追踪
- 是否提到了足够的关键论文标题，保证可审计
- 是否缺少必须的 section heading

其中“缺少必须标题”是 hard failure。

### 6.6 它和其他 skill 的关系

- 它不是独立起步的 skill，而是 `idea-evaluation` 的交付层延伸。
- 如果报告看起来空泛，不应只补 prose，而应回到 claim 和 evidence 本身收紧。

## 7. `semantic-scholar-api`：底层 Semantic Scholar 能力

### 7.1 它的定位

这个 skill 不走完整 AutoScholar 工作流，它直接暴露 Semantic Scholar Graph API 能力，用于：

- 单篇 paper 查询
- author 查询
- citations / references 查看
- recommendations 调试
- 原始 metadata 拉取
- open-access PDF 下载

它更像底层工具箱和排障接口。

### 7.2 什么时候应该用它

- 你怀疑 citation workflow 的检索结果不合理，想看原始返回
- 你想先手动验证某个 paper ID / author ID
- 你要排查推荐逻辑
- 你要直接抓取某篇 paper 的 metadata 或 open-access PDF

### 7.3 它的大致工作流程

#### 模式 A：先人工直查，再决定是否进入 workspace 流程

1. 用 `semantic paper/search/author` 看原始结果。
2. 确认 paper、author、venue、年份等元数据是否符合预期。
3. 再决定要不要把它们变成 query 或引入 citation 流程。

#### 模式 B：citation 流程异常时做排障

1. 发现 `citation search` 结果异常少、异常杂或与预期偏离。
2. 用 `autoscholar semantic search <query>` 直接看底层返回。
3. 用 `recommend/citations/references` 进一步看相邻图谱。
4. 必要时再修改 `configs/search.yaml`、`configs/recommendation.yaml` 或 claim/query 设计。

### 7.4 支持的能力面

根据 skill 和源码，当前支持：

- paper lookup
- batch paper lookup
- relevance search
- bulk search
- recommendations
- citations
- references
- author search
- author papers
- open-access PDF download

核心实现位置：

- `src/autoscholar/integrations/semantic_scholar.py`

### 7.5 常用命令

```powershell
autoscholar semantic paper <paper_id>
autoscholar semantic search <query>
autoscholar semantic recommend <paper_id>
autoscholar semantic citations <paper_id>
autoscholar semantic references <paper_id>
autoscholar semantic author-search <query>
autoscholar semantic author <author_id>
autoscholar semantic author-papers <author_id>
autoscholar semantic download-pdf <paper_id>
autoscholar semantic smoke
```

### 7.6 使用注意点

- 有 `S2_API_KEY` 时会读取该环境变量。
- 没有 key 也能跑，但速率限制会更低。
- 尽量显式指定 `fields`，避免返回体过大。
- `semantic smoke` 在没配 `S2_API_KEY` 时会跳过，不会硬失败。

### 7.7 它和其他 skill 的关系

- 它通常不直接产生最终报告。
- 它是 `citation-workflow` 的底层支撑和排障工具。
- 在 journal fit 场景下，它也可用于补 journal profile 或检索期刊相关信号。

## 8. `journal-fit-advisor`：期刊适配与论文叙事定位

### 8.1 它的定位

这是仓库里和其他几个 skill 明显不同的一条线。

前面几个 skill 的核心问题是：

- 这条 idea 值不值得做
- 哪些论文能支持 claim

而 `journal-fit-advisor` 的核心问题是：

- 算法和核心实验已经定了，现在这篇论文该怎么讲
- 哪个叙事更适合哪个期刊
- 为了提高命中率，最低成本应该补哪些 patch

### 8.2 它的硬约束

这个 skill 的约束非常明确：

- 算法输入 / 方法 / 输出视为固定
- 核心实验视为固定
- 默认不建议做重量级新实验
- 允许的是低成本 patch，比如：
  - 小规模补充分析
  - figure 重画或重 caption
  - wording 调整
  - appendix 注释
  - 很轻量的 ablation 片段

### 8.3 它适合什么阶段

适合在下面这个时间点用：

- 方法已经确定
- 主实验已经做完
- 当前真正的问题是论文 framing、narrative、journal fit、submission positioning

### 8.4 它的工作目录模型

它不使用前面那套 `workspace.yaml` 模型，而是在：

- `.autoscholar/<paper_id>/`

下面生成一整套中间产物。

典型产物包括：

- `run_meta.json`
- `assets.json`
- `journals/*.json`
- `narratives/candidate_*.json`
- `fit_matrix.json`
- `skeletons/*.md`
- `adversarial_review.json`
- `patches.json`
- `report.md`

### 8.5 它的标准工作流程

源码里这个流程已经拆成 phase0 到 phase7。

#### Phase 0：规范化输入

目标：

- 把输入整理成 `.autoscholar/<paper_id>/input.md`
- 必要时接收草稿 PDF，进入 draft reframing 模式

命令：

```powershell
autoscholar jfa init --working-title "My Paper"
autoscholar jfa phase0 --paper-id <paper_id> --input input.md
autoscholar jfa phase0 --paper-id <paper_id> --draft-pdf path\to\draft.pdf --input input.md
```

这一阶段会判断当前属于两种模式之一：

- `from_scratch`
- `draft_reframing`

如果给了 PDF，它会先从 PDF 抽材料，再与 `input.md` 的显式信息合并，最后写回规范化输入。

#### Phase 1：抽取 asset inventory

命令：

```powershell
autoscholar jfa phase1 --paper-id <paper_id>
```

这一层会从固定材料里提炼资产清单，比如：

- 结果资产
- 方法资产
- 图表资产
- 已有叙事资产

输出：

- `.autoscholar/<paper_id>/assets.json`

如果是 draft reframing 模式，还可能额外写已有叙事的基线表示，供后续拿来和新叙事比较。

#### Phase 2：构建期刊口味画像

命令：

```powershell
autoscholar jfa phase2 --paper-id <paper_id>
autoscholar jfa phase2 --paper-id <paper_id> --journal "<journal_name>" --no-cache
```

这一阶段会围绕目标期刊构建 profile。文档里写的是：

- 基于 Semantic Scholar
- 可选叠加 web 信号

输出：

- `.autoscholar/<paper_id>/journals/*.json`

#### Phase 3：生成 narrative candidates

命令：

```powershell
autoscholar jfa phase3 --paper-id <paper_id>
```

这一层会生成 4 到 6 个明显不同的叙事候选，而不是只给一个模糊建议。

输出：

- `.autoscholar/<paper_id>/narratives/candidate_*.json`

#### Phase 4：做 narrative-journal 配对打分

命令：

```powershell
autoscholar jfa phase4 --paper-id <paper_id>
```

这一步会把 narrative 候选和 journal profile 两两配对，形成 fit matrix，然后选出 top combinations。

输出：

- `.autoscholar/<paper_id>/fit_matrix.json`

#### Phase 5：为 top 组合生成 skeleton

命令：

```powershell
autoscholar jfa phase5 --paper-id <paper_id>
```

系统会针对 top 组合生成骨架稿，帮助快速落地到摘要、引言、实验排序、图表组织。

输出：

- `.autoscholar/<paper_id>/skeletons/*.md`

#### Phase 6：做 adversarial review 和 patch list

命令：

```powershell
autoscholar jfa phase6 --paper-id <paper_id>
```

这一步会用 reviewer 式视角去挑刺，然后只保留可由现有材料或低成本补丁解决的问题。

输出：

- `.autoscholar/<paper_id>/adversarial_review.json`
- `.autoscholar/<paper_id>/patches.json`

这里的 patch 会带：

- 对应 narrative
- 对应 journal
- 严重性
- patch 类型
- 预计耗时
- patch 描述

#### Phase 7：汇总最终建议

命令：

```powershell
autoscholar jfa phase7 --paper-id <paper_id>
```

或直接一键跑完整流程：

```powershell
autoscholar jfa run --paper-id <paper_id> --input input.md
autoscholar jfa run --paper-id <paper_id> --draft-pdf path\to\draft.pdf --input input.md
```

最终会输出：

- primary narrative x journal
- backup narrative x journal
- primary risk
- action items
- 汇总报告 `.autoscholar/<paper_id>/report.md`

### 8.6 它的输入模板大致要求什么

`input_template.md` 要求的核心信息包括：

- 论文身份信息：标题、领域、任务
- 固定算法：输入 / 方法流程 / 输出
- novelty claims
- 固定实验：数据集、baseline、指标、结果、side findings
- 目标期刊
- 现有摘要、引言、图注、拒稿反馈（可选）

### 8.7 它和其他 skill 的关系

- 它和 `idea-evaluation` 是两条不同阶段的能力线。
- `idea-evaluation` 更偏“做不做这个方向”。
- `journal-fit-advisor` 更偏“方向和实验都定了，怎么讲、投哪”。
- 它会借用 Semantic Scholar 一类信号，但不依赖标准 workspace。

## 9. 这 6 个 skill 最常见的衔接方式

### 9.1 路线 A：文献支持

适用场景：你只想把 claim 支撑和参考文献整理出来。

流程：

1. `autoscholar`
2. `citation-workflow`
3. 按需 `report render --kind prescreen|shortlist`

最终重点产物：

- `selected_citations.jsonl`
- `references.bib`
- `prescreen.md`
- `shortlist.md`

### 9.2 路线 B：idea 可行性分析

适用场景：你要判断某个研究方向是否值得继续推进。

流程：

1. `autoscholar`
2. `idea-evaluation`
3. 其中嵌套调用 `citation-workflow`
4. 再进入 `report-authoring`

最终重点产物：

- `idea_assessment.json`
- `evidence_map.json`
- `feasibility.md`
- `deep_dive.md`
- `report_validation.json`

### 9.3 路线 C：底层排障 / 数据侦察

适用场景：完整工作流还没准备好，或者检索结果不对，需要先做底层核查。

流程：

1. `autoscholar`
2. `semantic-scholar-api`
3. 再回到 `citation-workflow` 或 `journal-fit-advisor`

### 9.4 路线 D：论文包装与期刊定位

适用场景：方法和实验已经做完，接下来是写作策略和投稿定位。

流程：

1. `journal-fit-advisor`
2. phase0 -> phase1 -> phase2 -> phase3 -> phase4 -> phase5 -> phase6 -> phase7

或直接：

```powershell
autoscholar jfa run --paper-id <paper_id> --input input.md
```

## 10. 一句话总结每个 skill

- `autoscholar`：总入口，负责选路、建 workspace、查健康度。
- `citation-workflow`：围绕 claim 组织检索、预筛、纠偏、shortlist 和 BibTeX。
- `idea-evaluation`：基于 citation 证据评估研究方向的可行性和风险。
- `report-authoring`：把 assessment 和 evidence 渲染成最终报告并做可追踪校验。
- `semantic-scholar-api`：底层检索、推荐、引用图谱和排障接口。
- `journal-fit-advisor`：面向已完成方法和实验的论文 framing、期刊适配和低成本 patch 规划。

## 11. 推荐阅读顺序

如果你是第一次接手这个项目，建议按这个顺序读：

1. `.agents/skills/autoscholar/SKILL.md`
2. `.agents/skills/citation-workflow/SKILL.md`
3. `.agents/skills/citation-workflow/references/workflow.md`
4. `.agents/skills/idea-evaluation/SKILL.md`
5. `.agents/skills/idea-evaluation/references/workflow.md`
6. `.agents/skills/report-authoring/SKILL.md`
7. `.agents/skills/report-authoring/references/workflow.md`
8. `.agents/skills/semantic-scholar-api/SKILL.md`
9. `.agents/skills/journal-fit-advisor/SKILL.md`
10. `src/autoscholar/cli.py`

这样读的好处是：先建立顶层路由，再进入主线工作流，最后看底层命令面和 JFA 这条独立能力线。
