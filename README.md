# AutoScholar v2

结构化学术研究工具包，由 Python CLI 驱动，配合 Claude 等 AI agent 使用。

---

## 目录结构

```
.
├── .agents/skills/          # Claude 读取的技能定义（SKILL.md + 参考文档）
├── config/                  # 全局配置（搜索规则等）
├── docs/
│   ├── design/              # 各功能设计思路文档
│   └── PROJECT_SKILLS_WORKFLOW.md
├── scripts/                 # 独立脚本工具
│   ├── SemanticScholarApi/  # 兼容旧版导入的 shim 层
│   └── *.py                 # 批量搜索、推荐纠错等脚本
├── src/autoscholar/         # 安装包核心代码
├── tests/
└── workspaces/              # 运行数据（输入 / 中间产物 / 报告）
    ├── handout/             # handout 工作区
    ├── idea-creation/       # idea-creation-v2 工作区
    └── triggered-push/      # triggered-push 工作区
```

> **所有运行数据都放在 `workspaces/` 下**，和代码完全分离。  
> 你不需要手动创建子目录，每个命令的 `init` 步骤会替你建好。

---

## 安装

```bash
python -m pip install -e .[test]
```

---

## 六大工作流

### 1. 引用文献工作流 (Citation)

**用途**：给一篇论文搜索相关文献，生成精选引用列表和 `.bib` 文件。

**输入放在哪**：`<workspace>/inputs/` 下，文件由 `workspace init` 生成后手动填写。

```
<workspace>/
├── workspace.yaml              ← 自动生成，不需要改
├── inputs/
│   ├── idea_source.md          ← 填写：论文摘要 / 研究问题 / 已知文献
│   └── citation_claim_units.md ← 填写：每条引用对应的声明（claim）
└── configs/
    ├── search.yaml             ← 可调：搜索词、限制年份
    └── citation_rules.yaml     ← 可调：引用筛选规则
```

**完整流程**：

```bash
# 1. 建工作区
autoscholar workspace init workspaces/my-paper --template citation-paper --reports-lang zh

# 2. 填写 workspaces/my-paper/inputs/ 下的文件（见上面说明）

# 3. 跑流程
autoscholar citation search     --workspace workspaces/my-paper
autoscholar citation prescreen  --workspace workspaces/my-paper
autoscholar citation correct    --workspace workspaces/my-paper
autoscholar citation shortlist  --workspace workspaces/my-paper
autoscholar citation bib        --workspace workspaces/my-paper

# 4. 生成报告
autoscholar report render --workspace workspaces/my-paper --kind prescreen
autoscholar report render --workspace workspaces/my-paper --kind shortlist
```

**输出**：`workspaces/my-paper/reports/` 下的 Markdown 报告，以及 `artifacts/references.bib`。

---

### 2. 想法评估工作流 (Idea Evaluation)

**用途**：评估一个研究 idea 的可行性、新颖性，生成可行性报告和深度分析。

**输入放在哪**：

```
<workspace>/
├── inputs/
│   └── idea_source.md     ← 填写：研究 idea 描述（背景、问题、初步方案）
└── configs/
    └── idea_evaluation.yaml  ← 可调：评估维度权重
```

**完整流程**：

```bash
autoscholar workspace init workspaces/my-idea-eval --template idea-evaluation --reports-lang zh

# 填写 workspaces/my-idea-eval/inputs/idea_source.md

autoscholar citation search    --workspace workspaces/my-idea-eval
autoscholar citation prescreen --workspace workspaces/my-idea-eval
autoscholar citation correct   --workspace workspaces/my-idea-eval
autoscholar citation shortlist --workspace workspaces/my-idea-eval
autoscholar idea assess        --workspace workspaces/my-idea-eval
autoscholar report render   --workspace workspaces/my-idea-eval --kind feasibility
autoscholar report render   --workspace workspaces/my-idea-eval --kind deep-dive
autoscholar report validate --workspace workspaces/my-idea-eval --kind feasibility
```

---

### 3. 想法孵化 v2 (Idea Creation v2)

**用途**：五阶段 AI 对话式 idea 孵化（压力测试 → 对抗扩展 → 方法剪枝 → 可证伪设计 → 命名收敛）。

**输入放在哪**：

```
<workspace>/
└── inputs/
    └── idea_seed.md    ← 填写你的 idea 种子（模板见下）
```

`idea_seed.md` 有四种形态（α/β/γ/δ），建工作区后会生成带提示的空白模板：

- **α 型**（概念切分）：怀疑 X 和 Y 被合并对待，其实应分开
- **β 型**（场景倒逼）：某个具体场景+硬约束，标准做法不够用
- **γ 型**（空白观察）：发现某个领域空白，想搞清楚为何空
- **δ 型**（约束驱动）：有目标+不可妥协的约束，在约束里找方案

**完整流程**：

```bash
# 1. 建工作区
autoscholar workspace init workspaces/my-new-idea --template idea-creation-v2 --reports-lang zh

# 2. 填写 workspaces/my-new-idea/inputs/idea_seed.md（选一种形态，按模板填写）

# 3. 让 Claude 读取技能并开始对话
#    提示 Claude：阅读 .agents/skills/idea-creation-v2/SKILL.md 并开始阶段一
autoscholar workspace doctor --workspace workspaces/my-new-idea

# 4. 生成对话记录报告
autoscholar report render --workspace workspaces/my-new-idea --kind idea-conversation
```

> 这个工作流主要是 **人机对话驱动**，Claude 扮演压力测试方，你负责判断和选择。
> `autoscholar` 命令只负责初始化和生成报告，核心五个阶段在 Claude 对话里完成。

---

### 4. 领域速览 (Handout)

**用途**：给一个研究领域快速生成三层深度的综述手稿（术语层 / 全景层 / 张力层）。

**输入**：直接在命令行传领域名称，无需准备文件。

**输出放在哪**：`workspaces/handout/<domain-slug>-<level>/`

```bash
# 术语层（最快，适合入门摸底）
autoscholar handout init "open set recognition" --level terminology

# 全景层（中等深度，领域版图）
autoscholar handout init "open set recognition" --level landscape

# 张力层（最深，核心争议和研究方向）
autoscholar handout init "open set recognition" --level tension --max-queries 1 --round-delay 300
```

**常用选项**：
- `--level` : `terminology` / `landscape` / `tension`
- `--output-dir` : 自定义输出目录（默认 `workspaces/handout/<domain>-<level>`）
- `--max-queries N` : 限制单次爬取的查询数量
- `--single-pass` : 只跑一轮就停（断点续跑时用）
- `--round-delay N` : 每轮之间等待 N 秒（避免 API 限速）

> 每次爬取后写 checkpoint，中断后重新执行同一命令会自动跳过已完成的查询。

---

### 5. 期刊匹配顾问 (Journal Fit Advisor)

**用途**：分析一篇论文稿件，推荐合适的目标期刊，分阶段评估匹配度。

**输入放在哪**：需要一个稿件输入 Markdown 文件，路径在命令行指定。

```bash
# 1. 初始化（创建 paper-id 对应的工作目录）
autoscholar jfa init --working-title "My Paper Title"

# 2. 运行完整分析（--input 传稿件路径）
autoscholar jfa run --paper-id <paper_id> --input path/to/paper_input.md

# 3. 单阶段运行（可选）
autoscholar jfa phase2 --paper-id <paper_id>   # 重跑某一阶段
autoscholar jfa phase3 --paper-id <paper_id> --no-cache
```

稿件输入文件（`paper_input.md`）内容：论文标题、摘要、关键词、研究问题。

---

### 6. 触发式推送 (Triggered Push)

**用途**：基于你的阅读偏好 DNA，主动推送文献中的争议/失败方向/方法空白/跨域结构。

**输入放在哪**：

```
<workspace>/
├── triggered-push.yaml         ← 自动生成，不需要改
└── inputs/
    ├── seed_papers.md          ← 填写：3-10 篇你熟悉的代表性论文（标题+年份）
    └── scope.yaml              ← 可调：home_field、允许的外域列表、领域词汇
```

**完整流程**：

```bash
# 1. 建工作区
autoscholar trigger init workspaces/triggered-push/my-domain \
    --domain "open set recognition" \
    --home-field "Computer Science"

# 2. 填写 inputs/seed_papers.md（写几篇你读过的论文，标题+年份即可）
# 3. 可选：编辑 inputs/scope.yaml 补充领域词汇

# 4. 选择一个范式运行
autoscholar trigger push --workspace workspaces/triggered-push/my-domain --paradigm controversy
autoscholar trigger push --workspace workspaces/triggered-push/my-domain --paradigm failure-archive
autoscholar trigger push --workspace workspaces/triggered-push/my-domain --paradigm matrix
autoscholar trigger push --workspace workspaces/triggered-push/my-domain --paradigm cross-domain
```

**四种范式**：
| 范式 | 推送内容 | 有效反应 |
|------|----------|----------|
| `controversy` | 领域内活跃争议（正反两派） | `bored` / `spectate` / `want_to_argue` |
| `failure-archive` | 曾经主流、后来被放弃的方向 | `still_holds` / `unsure` / `changed` |
| `matrix` | 方法×场景密度图，找稀疏空格 | `irrelevant` / `obvious_void` / `curious` |
| `cross-domain` | 跨领域结构同构的论文对 | `not_isomorphic` / `shallow` / `partial` / `deep` |

**报告在哪**：`<workspace>/reports/push_<paradigm>_<run_id>.md`

> **AI 合成步骤**：`push` 命令完成文献爬取后会打印一条提示，需要你把 `synthesis_input_*.json` 交给 Claude 做判断，Claude 写完卡片后再重跑 `push` 即可渲染报告。

**记录反应**（读完报告后）：

```bash
autoscholar trigger react \
    --workspace workspaces/triggered-push/my-domain \
    --card-id <card_id> \
    --reaction want_to_argue \
    --take "这个争议在 OOD 检测场景下会倒过来"

# 查看当前 DNA 画像
autoscholar trigger profile --workspace workspaces/triggered-push/my-domain

# 把一张卡片的反应带入另一个范式
autoscholar trigger relay \
    --workspace workspaces/triggered-push/my-domain \
    --source-card <card_id> \
    --target-paradigm cross-domain
```

---

## 技能 (Skills)

`.agents/skills/` 下的每个目录是一个 Claude 技能，包含 `SKILL.md`（行为规范）和参考文档：

| 技能目录 | 用途 |
|----------|------|
| `autoscholar` | 工具总览，能力路由 |
| `citation-workflow` | 引用文献工作流完整说明 |
| `handout` | 三层 handout 生成规范 |
| `idea-creation` | 早期 idea 评估技能 |
| `idea-creation-v2` | 五阶段 idea 孵化（含输入模板、阶段 playbook） |
| `idea-evaluation` | 想法可行性评估 |
| `journal-fit-advisor` | 期刊推荐分析流程 |
| `report-authoring` | 报告生成规范 |
| `semantic-scholar-api` | Semantic Scholar API 使用说明 |
| `triggered-push` | 四范式触发推送流程 |

使用方式：在 Claude 对话开头说"请阅读 `.agents/skills/<skill-name>/SKILL.md`"，Claude 会按技能规范工作。

---

## CLI 速查

```
autoscholar workspace   init / doctor
autoscholar citation    search / prescreen / correct / shortlist / bib
autoscholar idea        assess
autoscholar report      render / validate
autoscholar handout     init
autoscholar jfa         init / run / phase0..phase7
autoscholar trigger     init / push / react / profile / relay
autoscholar semantic    paper / search / crawl / citations / references / download-pdf / smoke
autoscholar util        pdf-to-text
autoscholar schema      export
```

任意命令加 `--help` 查看详细参数：

```bash
autoscholar trigger push --help
autoscholar handout init --help
```

---

## 独立脚本 (scripts/)

不依赖工作区，直接处理文件的批量工具：

| 脚本 | 用途 |
|------|------|
| `batch_semantic_scholar_search.py` | 批量 Semantic Scholar 搜索，输出 JSONL |
| `dedupe_and_prescreen_semantic_scholar.py` | 去重 + 初筛 |
| `generate_claim_recommendation_list.py` | 生成声明推荐列表 |
| `generate_references_bib.py` | 生成 `.bib` 文件 |
| `recommendation_auto_correct.py` | 推荐结果自动纠错 |
| `resumable_novelty_verification.py` | 断点续跑式新颖性验证 |
| `pdf_to_text.py` | PDF 转文本 |

脚本配置文件放在 `config/` 目录下（或运行时 `--config` 指定）。
