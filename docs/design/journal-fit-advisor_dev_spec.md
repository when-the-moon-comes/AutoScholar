# `journal-fit-advisor` 模块 · 开发文档

> 版本：v0.1（初稿）
> 定位：AutoScholar 项目下的独立 Skill 模块
> 使用方式：既可作为 Claude Skill 单独触发，也可被 AutoScholar 的 codex 调用链消费其中间产物

---

## 0. 一句话定义

> **给定一组已固定的算法内容与已完成的实验事实，以及 1–3 本目标期刊，本模块在"叙事可调空间"中搜索出最匹配期刊口味、最被现有素材支撑、最能放大贡献的若干候选叙事方案，并把每个候选具体化到可落笔的论文骨架。**

---

## 1. 模块定位

### 1.1 核心目标

本模块需要能回答并产出三件事：

1. **叙事可行性**：候选叙事能否被已有实验顶住，不依赖新实验
2. **期刊适配度**：候选叙事是否匹配目标期刊近两年真实录用的那类论文
3. **落地可写性**：产出段落意图级骨架 + 可直接改写的 Abstract / Title 草稿，用户拿到即可开写

### 1.2 与 `paper-idea-advisor` 的边界（重要）

本模块必须与 `paper-idea-advisor` 严格区分，避免行为漂移。核心差别如下：

| 维度 | `paper-idea-advisor` | `journal-fit-advisor`（本模块） |
|---|---|---|
| 技术内容状态 | 模糊 idea，可变 | 算法 + 核心实验**已固定** |
| 主要自由度 | 改方向、加实验、调 claim | **仅叙事与包装** |
| 关键输入 | 一个 idea | 固定素材包 + 目标期刊 |
| 核心产出 | 研究路线图 | 叙事候选 + 论文骨架草稿 |

**边界约束（必须写入 SKILL.md 的角色约束段）**：

- 算法 I/A/O 与核心实验视为**不可变参数**
- 本模块**默认不建议**新增重型实验；只允许建议"低成本补丁"（新增 ablation 片段、补一段分析、补一张图、改措辞）
- 若用户在对话中提出要改算法或补重型实验，应**显式建议 fallback 到 `paper-idea-advisor`**

### 1.3 不做什么

为避免膨胀，本模块**明确不负责**以下事项（可作为未来扩展，见 §12）：

- 不生成完整 Method 章节正文
- 不生成完整 Related Work 正文
- 不生成 Cover Letter / Response Letter
- 不做 rebuttal 演练
- 不做投稿流程操作

### 1.4 两种使用模式（重要）

根据用户输入形态不同，模块运行在两种模式之一，**行为有差异**，必须在 Phase 0 结束前判定并记录到 `run_meta.json`。

#### Mode A · From-scratch-framing（从零设计叙事）

- **触发条件**：用户仅提供素材（算法 + 实验事实表），未提供论文初稿
- **核心任务**：在叙事空间中**生成**候选
- **Phase 1 行为**：仅抽取卖点
- **Phase 5 行为**：产出 Title/Abstract 的"从零草稿"

#### Mode B · Draft-reframing（现有叙事改造）

- **触发条件**：用户提供了论文初稿 PDF（无论完整度）
- **核心任务**：在叙事空间中**生成候选 + 对比现有叙事**
- **Phase 0 行为**：从 PDF 抽取填充素材模板，免去手填
- **Phase 1 行为**：额外做"**现有叙事诊断**"子步骤（§5.1.3）
- **Phase 4 行为**：评分时把"现有叙事"作为一个基线候选（N0）一起评
- **Phase 5 行为**：产出 Title/Abstract 时同时给出 **diff 视图**（改哪几处、为什么改）

> 诊断结果可能是："现有叙事已经是最优解之一，建议仅微调"——这是允许且有价值的结论，不要为了推出新方案而强行否定用户原稿。

---

## 2. 术语约定

| 术语 | 定义 |
|---|---|
| **素材包 (Asset Pack)** | 用户提供的固定算法 + 固定实验集合 |
| **卖点 (Selling Point)** | 从素材包中抽取出的一条可被讲成"贡献"的素材 |
| **卖点表 (Asset Inventory)** | 所有卖点的结构化表格，Phase 1 产出 |
| **期刊口味卡 (Journal Taste Profile)** | 某目标期刊的偏好画像，Phase 2 产出 |
| **叙事候选 (Narrative Candidate)** | 一个差异化的论文讲法，Phase 3 产出 |
| **匹配矩阵 (Fit Matrix)** | 叙事 × 期刊 的打分矩阵，Phase 4 产出 |
| **论文骨架 (Paper Skeleton)** | 段落意图级的章节规划 + Title/Abstract 草稿，Phase 5 产出 |
| **补丁清单 (Patch List)** | 对抗审稿后得出的低成本改进项，Phase 6 产出 |

---

## 3. 输入契约

### 3.1 必选输入

用户提交的输入可以是以下**两种形态之一**（模式判定见 §1.4）：

#### 形态 A · 素材模板（触发 From-scratch-framing 模式）

必须包含：

1. **算法素材包**：
   - 输入（Input specification）
   - 算法流程（Method / Pipeline，文字或伪代码）
   - 输出（Output specification）
2. **实验事实表**（强制结构化，见 §3.3 模板）
3. **目标期刊列表**：1–3 本，带优先级
4. **（可选）图表文件**：若有实验图，放入 `raw/figures/` 目录，每张图附带 caption（见 §3.5）

#### 形态 B · 论文初稿 PDF（触发 Draft-reframing 模式）

必须包含：

1. **论文初稿 PDF**：放入 `raw/draft.pdf`
2. **目标期刊列表**：1–3 本，带优先级
3. **（可选）独立图表文件**：若有正文外的补充图、或更高分辨率源图，放入 `raw/figures/`
4. **（可选）改投背景**：上一次投稿的拒稿意见、当前对叙事不满意的点

Phase 0 会从 PDF 抽取算法信息、实验事实表、图表 caption，**自动填充**到与形态 A 等价的结构化表示，后续所有 Phase 共用同一套中间产物。

#### 共同规则

- 若同时提供 PDF 和素材模板：以 PDF 为准，模板用于覆盖/修正 PDF 抽取中的歧义
- 若用户只给了 PDF 但未指定目标期刊：Phase 0 强制追问
- 若 PDF 是扫描版无文字层：走 OCR 降级（见 §10）

### 3.2 输入结构化策略（设计决策）

**默认策略：内部一律以结构化模板表示**，对用户则有两条便利路径：

- **素材模板路径**：用户直接填 `input_template.md`（Mode A）
- **PDF 路径**：用户给 PDF，Phase 0 自动抽取填充模板（Mode B）

两条路径在 Phase 1 开始前必须汇聚到同一份 `input.md` + `raw/figures/*`。

理由：
- 后续所有 Phase 高度依赖结构化输入，自然语言 PDF 直接消费 → 幻觉叙事
- 单一用户给 PDF 更方便；未来开放给他人使用，两条路径并存
- PDF 抽取失败 / 有歧义时，要求用户补填模板对应字段

### 3.3 输入模板（`input_template.md`）

```markdown
# Paper Materials Submission

## 1. Paper Identity
- working_title:
- domain:        (e.g., NLP / CV / Bioinformatics / ...)
- task:          (e.g., node classification on graphs)

## 2. Algorithm (fixed, not to be changed by this module)

### Input
<详细描述输入>

### Method / Pipeline
<详细描述或贴伪代码>

### Output
<详细描述输出>

### Key Novelty Claim(s) (作者自认)
- novelty_1:
- novelty_2:

## 3. Experiments (fixed facts)

### Exp-1: <name>
- purpose:
- datasets:
- baselines:
- metrics:
- key_results:       (写清具体数值)
- side_findings:     (附带发现的现象)

### Exp-2: <name>
...

## 4. Target Journals
- journal_1: <name>   priority: high
- journal_2: <name>   priority: medium
- journal_3: <name>   priority: low

## 5. Existing Drafts (optional)
- current_abstract:
- current_intro_p1:
- figure_1_caption:
- prior_rejection_feedback:
```

### 3.4 输入校验规则

进入 Phase 1 之前，必须通过以下校验（校验失败 → 提示用户补齐）：

- [ ] 算法三件套（Input / Method / Output）非空
- [ ] 实验数 ≥ 1
- [ ] 每个实验 `key_results` 字段有具体数值或现象描述
- [ ] 目标期刊 ≥ 1 本
- [ ] 若为 Mode B：PDF 成功解析出 ≥ 1 个实验章节 + ≥ 1 个方法章节；否则降级到提示用户补填模板

### 3.5 图表输入约定

图表是独立的证据载体，不能只作为实验表格的附属。

#### 目录与命名

```
raw/figures/
├── fig_01_main_pipeline.png         # 方法流程图
├── fig_02_main_results.pdf          # 主实验结果图
├── fig_03_ablation_heatmap.png      # 消融热图
└── figures_manifest.json            # 图表清单
```

#### `figures_manifest.json` 结构

```json
{
  "figures": [
    {
      "id": "F01",
      "path": "raw/figures/fig_01_main_pipeline.png",
      "type": "pipeline | main_result | ablation | case_study | trend | distribution | qualitative",
      "linked_experiments": ["Exp-1"],
      "caption_original": "用户撰写的原图释（若 Mode B 则从 PDF 抽取）",
      "what_it_shows": "这张图真正传达的一句话信息",
      "visual_claim": "这张图在视觉上最强烈传达的结论",
      "numeric_claim": "这张图可量化的关键数值（若有）"
    }
  ]
}
```

- `visual_claim` vs `numeric_claim` 的区分很关键：叙事设计时常需要"放大 visual_claim"或"调出被 visual_claim 掩盖的 numeric_claim"
- Mode B 下由 Phase 0 自动抽取（含图片本体 + 抽取 caption）；Mode A 下由用户手填或最简填写

---

## 4. 输出契约

### 4.1 最终输出（呈现给用户）

**一份汇总报告** `report.md`，包含：

1. 卖点表（Phase 1）
2. 期刊口味卡（每本期刊一张，Phase 2）
3. 叙事候选卡（4–6 张，Phase 3）
4. 匹配矩阵 + Top 组合（Phase 4）
5. Top 1–2 方案的论文骨架（Phase 5）
6. 对抗审稿模拟 + 补丁清单（Phase 6）
7. 最终决策建议与投稿路径（Phase 7）

### 4.2 中间产物（落盘，供其他 skill 消费）

这是**本模块作为 AutoScholar 子模块的关键接口**。所有中间产物必须落盘为结构化文件，目录结构见 §8。

| 产物 | 路径 | 格式 | 产生时机 |
|---|---|---|---|
| 原始输入（规范化后） | `input.md` | Markdown | Phase 0 |
| 原始 PDF（若 Mode B） | `raw/draft.pdf` | PDF | 用户提供 |
| 图表文件 | `raw/figures/*` | PNG/PDF | 用户提供 或 Phase 0 从 PDF 抽取 |
| 图表清单 | `raw/figures_manifest.json` | JSON | Phase 0 |
| 运行元信息（模式标签等） | `run_meta.json` | JSON | Phase 0 |
| 卖点表 | `assets.json` | JSON | Phase 1 |
| 现有叙事诊断（仅 Mode B） | `existing_narrative.json` | JSON | Phase 1 |
| 期刊口味卡 | `journals/<slug>.json` | JSON | Phase 2 |
| 叙事候选 | `narratives/candidate_<N>.json` | JSON | Phase 3 |
| 匹配矩阵 | `fit_matrix.json` | JSON | Phase 4 |
| 论文骨架 | `skeletons/skeleton_<narrative>_<journal>.md` | Markdown | Phase 5 |
| 审稿模拟 | `adversarial_review.json` | JSON | Phase 6 |
| 补丁清单 | `patches.json` | JSON | Phase 6 |
| 最终报告 | `report.md` | Markdown | Phase 7 |

---

## 5. Phase 流程详解

整体链路为 Phase 0 → 7，其中 Phase 1 与 Phase 2 无依赖，可并行。

```
        ┌── Phase 1 (Asset Inventory) ──┐
Phase 0 ┤                                ├── Phase 3 ── Phase 4 ── Phase 5 ── Phase 6 ── Phase 7
        └── Phase 2 (Journal Profiling)─┘
```

---

### Phase 0 · 输入规范化 / 信息补全

**目的**：识别输入形态 → 抽取/校验 → 产出规范化 `input.md` + 图表清单 + 模式标签。

**处理逻辑**：

1. 识别输入形态：检查用户工作区是否存在 `raw/draft.pdf`，有则判定为 Mode B，否则为 Mode A
2. **Mode A 分支**：
   - 读取 `input_template.md`
   - 校验 §3.4 规则
   - 若 `raw/figures/` 有图但无 `figures_manifest.json`，提示用户补齐或最简填写
3. **Mode B 分支**：
   - 调用 PDF 解析（建议复用 `/mnt/skills/public/pdf-reading` skill）
   - 抽取章节：Abstract / Introduction / Method / Experiments / Conclusion
   - 抽取图表：导出图像到 `raw/figures/fig_*.png`，抽取 caption
   - 抽取实验事实：把 Experiments 章节的每个小节映射到 `input_template.md` 的实验块
   - 生成 `figures_manifest.json`（`caption_original` 字段从 PDF caption 填入，`what_it_shows` / `visual_claim` / `numeric_claim` 字段由 LLM 基于图像 + caption 自动填充，打 `confidence: low/medium/high` 标签）
   - 把抽取结果写入 `input.md`，并在文件头部标注"**由 PDF 自动抽取，请审阅**"
   - **列出抽取低置信字段**，要求用户一次性确认/修正（≤ 5 个问题）
4. 若用户在对话中请求改动算法或大型实验 → 提示 fallback 到 `paper-idea-advisor`，终止本模块
5. 写入 `run_meta.json`：

```json
{
  "paper_id": "...",
  "mode": "from_scratch | draft_reframing",
  "created_at": "ISO-8601",
  "source": {
    "has_pdf": true,
    "pdf_path": "raw/draft.pdf",
    "figures_count": 6,
    "extraction_confidence": "high | medium | low"
  },
  "target_journals": ["..."]
}
```

**产出**：`input.md` + `raw/figures_manifest.json` + `run_meta.json`

---

### Phase 1 · 素材盘点（Asset Inventory）

**目的**：不做任何搜索，只对**固定内容**做多角度抽取，得到"可讲的素材库"。这是后续叙事的"证据根"。

**处理逻辑**：
- 沿 7 个类别扫描算法 + 实验表 + **图表清单**，抽取每一条潜在卖点
- 对每条卖点评估证据强度（强 / 中 / 弱）并引用来源
- **证据来源允许三类**：`experiment`（实验表数据）、`figure`（图表的 visual/numeric claim）、`method`（算法本身的性质）
- 图表的 `visual_claim` 常能支撑实验表无法直接表达的卖点（如"方法在尾部分布更稳"），**必须显式考察**
- 强度判定规则见 §5.1.1

**输出结构（`assets.json`）**：

```json
{
  "paper_id": "string",
  "generated_at": "ISO-8601",
  "assets": [
    {
      "id": "A01",
      "category": "methodology | performance | generality | theory | efficiency | application | interpretability",
      "content": "一句话描述这个卖点",
      "evidence_refs": [
        {"type": "experiment", "ref": "Exp-1"},
        {"type": "experiment", "ref": "Exp-2.ablation.row3"},
        {"type": "figure", "ref": "F02", "claim_type": "visual"},
        {"type": "method", "ref": "Algorithm.step4"}
      ],
      "strength": "strong | medium | weak",
      "strength_rationale": "为什么是这个强度",
      "caveats": "使用时需要注意的点（例如只在单一数据集验证）"
    }
  ]
}
```

#### 5.1.1 证据强度判定规则（必须写入 Skill）

- **Strong**：有直接的定量实验结果支撑，且在 ≥ 2 个数据集 / ≥ 2 个设定下成立
- **Medium**：有直接定量支撑，但仅在单一设定成立；或有间接支撑
- **Weak**：仅靠定性观察 / 作者主观 claim / 单条 case study

#### 5.1.2 产出要求

- 卖点条目数量：**8–15 条**（过少说明抽取不充分，过多说明粒度失控）
- 每个类别至少尝试抽取 1 条（抽不出就明确写"无"并说明）
- 任意一条 `strength = weak` 的卖点必须配 `caveats`
- 至少有 1 条卖点的 `evidence_refs` 包含 `type: figure`（若用户提供了图表）

#### 5.1.3 现有叙事诊断（仅 Mode B 触发）

**目的**：在生成新叙事之前，先把用户初稿里**已经存在**的叙事抽出来结构化，作为后续 Phase 4 评分中的"N0 基线候选"。

**处理逻辑**：
1. 从 PDF 的 Abstract + Introduction 末段抽取当前 main claim
2. 识别当前论文的 **主 angle**（方法 / 应用 / 理论 / ...）
3. 把当前 contribution bullets 逐条反向映射到 `assets.json`，标注哪些卖点被用了、哪些被浪费了
4. 识别叙事与证据之间的 misalignment：即"声称了但证据不够"或"证据很强但没声称"
5. 列出该叙事的结构性缺陷（若有），例如：主 claim 在该期刊口味下偏弱、核心图表放在了次要位置

**输出结构（`existing_narrative.json`）**：

```json
{
  "extracted_from": "raw/draft.pdf",
  "one_line_thesis": "从 abstract 提炼",
  "main_angle": "method-novelty",
  "current_contributions": [
    {
      "bullet": "...",
      "mapped_assets": ["A03"],
      "evidence_strength": "strong | medium | weak"
    }
  ],
  "unused_strong_assets": ["A07", "A09"],
  "overclaimed_items": [
    {"claim": "...", "issue": "依赖的 asset 强度不足"}
  ],
  "structural_issues": [
    "主实验 (Exp-1) 和图 2 的 visual_claim 不匹配",
    "..."
  ]
}
```

该文件在 Phase 3 参与约束叙事多样性（新候选必须在 thesis 上**显著**不同于 N0），在 Phase 4 以 N0 身份加入评分矩阵，在 Phase 5 若最终推荐 N0，则 skeleton 退化为"微调建议清单"。

---

### Phase 2 · 目标期刊口味画像（Journal Taste Profiling）

**目的**：基于真实证据，构建每本目标期刊的口味画像。

**整体策略**：拆成两个子阶段，对应两类信息源。**不要只用网页检索**，也不要只用 Semantic Scholar。

```
Phase 2a (Semantic Scholar API)  ──┐
                                   ├──→ journals/<slug>.json
Phase 2b (Web Fetch)            ──┘
```

#### Phase 2a · 代表论文样本（走 Semantic Scholar API）

**信息目标**：该刊近期录用论文的 title / abstract / venue / year / 引用数 / 作者机构。

**为什么走 Semantic Scholar 而非网页搜索**：
- 结构化返回，免解析，省 token
- `venue` 字段可精确过滤，不受期刊名变体困扰
- 支持按 `year` 过滤，天然满足"近 18 个月"需求
- 可按引用数排序，快速挑高影响力代表作
- AutoScholar 项目已集成，复用而非新增依赖

**调用策略**：
1. 用 Semantic Scholar 的 paper search 端点（`/graph/v1/paper/search`），`venue` 过滤 + `year >= now-18mo`
2. 对与本文方向相关的子查询，用算法主关键词 + 任务名做 query
3. 按 `citationCount` 降序取 Top-K（K = 8–12）
4. 对每篇补拉 abstract（若初次返回不含）

**字段抓取清单**：`title, abstract, year, venue, authors, citationCount, externalIds.DOI, url`

**期刊名模糊匹配**：用户输入的期刊名可能与 Semantic Scholar 的 `venue` 字段不完全一致（如 "Nature Methods" vs "Nat Methods"）。建议：
- 先做一次 `venue` 字段模糊查询，返回匹配候选
- 让用户在 Phase 0 末尾确认规范化后的期刊名（写入 `run_meta.json.target_journals_normalized`）
- 缓存期刊名映射表 `journals/_venue_alias.json`

#### Phase 2b · 期刊自述与生态（走 Web Fetch）

**信息目标**：Semantic Scholar 不提供的半结构化内容。

**抓取对象**：
1. 期刊官网的 **Aims & Scope / About the journal**
2. 期刊官网的 **Author Guidelines / Submission Guidelines**（含篇幅限制、结构偏好）
3. 近 2 年的 **Editorial / Editor's Choice / Perspectives**（反映编辑审美）
4. （可选）公开审稿指南或 review templates

**搜索策略**：
- `<journal_name> aims and scope`
- `<journal_name> author guidelines`
- `<journal_name> editorial <year>`

**注意**：Phase 2b 的抓取结果更零散，允许部分失败并降级。

**输出结构（`journals/<slug>.json`）**：

```json
{
  "journal_name": "string",
  "venue_normalized": "string (Semantic Scholar 规范化后的 venue 值)",
  "slug": "string",
  "cached_at": "ISO-8601",
  "cache_ttl_days": 14,
  "sources": {
    "semantic_scholar": {"fetched": true, "paper_count": 10},
    "web_scope": {"fetched": true, "url": "..."},
    "web_guidelines": {"fetched": true, "url": "..."},
    "web_editorials": {"fetched": false, "reason": "not found"}
  },
  "aims_scope_summary": "...",
  "preferred_contribution_types": [
    {"type": "method-novelty", "weight": 0.3},
    {"type": "application-driven", "weight": 0.4},
    {"type": "benchmark", "weight": 0.1},
    {"type": "theory", "weight": 0.05},
    {"type": "system", "weight": 0.05},
    {"type": "dataset", "weight": 0.1}
  ],
  "preferred_narrative_patterns": ["problem-first", "application-first"],
  "writing_style": {
    "length": "compact | standard | expansive",
    "tone": "formal | accessible",
    "jargon_density": "high | medium | low"
  },
  "typical_structure": [
    "Introduction",
    "Related Work",
    "Method",
    "Experiments",
    "Discussion",
    "Conclusion"
  ],
  "rising_subtopics": ["..."],
  "reviewer_red_flags": [
    "缺少真实场景验证",
    "过度依赖合成数据"
  ],
  "reference_papers": [
    {
      "title": "...",
      "year": 2025,
      "venue": "...",
      "citation_count": 42,
      "doi": "...",
      "url": "...",
      "abstract": "...",
      "relevance_to_user": "high | medium | low",
      "source": "semantic_scholar"
    }
  ],
  "confidence": "high | medium | low"
}
```

#### 5.2.1 缓存策略（设计决策）

**默认策略**：落盘缓存 + 14 天 TTL，**双源独立失效**。

- 每次运行先查 `journals/<slug>.json` 的 `cached_at` + `sources.*.fetched`
- Semantic Scholar 部分与 Web 部分可以独立过期/独立重抓（比如只 Web 部分过期时只重跑 Phase 2b）
- 若 `now - cached_at < cache_ttl_days` 且两源都为 `fetched: true` → 直接复用
- 提供 `--no-cache` / `--refresh-semantic` / `--refresh-web` 三档刷新粒度

理由：
- Semantic Scholar 拉取相对稳定快速，Web 抓取慢且易失败，双源分开管理故障边界更清晰
- 同一研究者常反复投同一批期刊，缓存命中率高

#### 5.2.2 产出质量检查

- `reference_papers` 长度必须 ≥ 5，且 `source: semantic_scholar` 占比 ≥ 60%
- `preferred_contribution_types` 权重之和 = 1.0（归一化）
- `reviewer_red_flags` 必须 ≥ 3 条（低于 3 条说明调研不充分，重跑）
- 若 Phase 2b 的 `aims_scope_summary` 为空但 Phase 2a 成功 → `confidence: medium`
- 若两源都失败 → `confidence: low`，在 `report.md` 中显式警告

---

### Phase 3 · 叙事空间生成（Narrative Space Generation）

**目的**：在受约束的搜索空间中，生成 **4–6 个差异化的叙事候选**。

#### 5.3.1 约束条件

1. 每个候选必须声明**主 angle**，取值范围：
   - `method-novelty` / `application-driven` / `theoretical-insight` / `efficiency-focused` / `unification` / `empirical-discovery` / `systems-contribution`
2. 每个候选**必须**引用 `assets.json` 中的 2–3 条作为主支撑（且至少 1 条必须是 `strong`）
3. 候选之间必须在"论文一句话定位（one-line thesis）"层面真正不同，**不允许仅措辞差异**
4. 不得引用不存在的实验或数据
5. **Mode B 额外约束**：存在 `existing_narrative.json` 时，新生成的候选必须与 N0 在 thesis 或 main angle 至少一项显著不同；N0 本身不重复生成，而是在 Phase 4 直接作为基线加入匹配矩阵

#### 5.3.2 生成策略

**二阶段生成 + 自我去重**：

1. 第一阶段：要求模型生成 **8 个**候选
2. 第二阶段：模型自我审查，基于"thesis 差异度"去重、合并，收敛到 **4–6 个**
3. 若最终少于 4 个，报告"叙事空间偏窄"并进入 Phase 4（不强行凑数）

#### 5.3.3 输出结构（`narratives/candidate_<N>.json`）

```json
{
  "id": "N1",
  "one_line_thesis": "...",
  "main_angle": "method-novelty",
  "target_reader": "computational biologists who care about interpretability",
  "main_claims": [
    {
      "claim": "...",
      "supporting_assets": ["A03", "A05"],
      "evidence_strength": "strong"
    }
  ],
  "assets_to_foreground": ["A03", "A05", "A07"],
  "assets_to_background": ["A02"],
  "implicit_assumptions": ["..."],
  "biggest_risk": "审稿人可能质疑方法在 X 场景下未验证",
  "required_framing_moves": [
    "在 Intro 中先立 X 问题的痛点",
    "把 Exp-2 作为主实验而非 Exp-1"
  ]
}
```

---

### Phase 4 · 叙事 × 期刊 匹配评分

**目的**：评估每个 (叙事, 期刊) 组合，选出 Top 组合进入 Phase 5。

**Mode B 特殊行为**：把 `existing_narrative.json` 以 `narrative_id: "N0"` 加入评分矩阵，使用户能直观看到"现有叙事 vs 新候选"的相对位次。若 N0 最终进入 Top，说明现有叙事已近最优。

#### 5.4.1 评分维度（每项 1–5 分）

| 维度 | 含义 | 判据来源 |
|---|---|---|
| **taste_fit** | 叙事 angle 与期刊偏好的契合 | `journal.preferred_contribution_types` |
| **evidence_support** | 叙事主 claim 的证据强度 | `narrative.main_claims[].evidence_strength` |
| **differentiation** | 相对该刊近期论文的新鲜度 | `journal.reference_papers` |
| **risk** | 被该刊拒后转投成本（低分为高风险） | 综合判断 |

#### 5.4.2 输出结构（`fit_matrix.json`）

```json
{
  "matrix": [
    {
      "narrative_id": "N1",
      "journal_slug": "journal_a",
      "scores": {
        "taste_fit": 4,
        "evidence_support": 5,
        "differentiation": 3,
        "risk": 4
      },
      "weighted_total": 4.1,
      "one_line_rationale": "...",
      "acceptance_expectation": "medium-high"
    }
  ],
  "top_combinations": [
    {"narrative_id": "N1", "journal_slug": "journal_a", "rank": 1},
    {"narrative_id": "N3", "journal_slug": "journal_b", "rank": 2}
  ]
}
```

**权重默认**：`taste_fit: 0.3, evidence_support: 0.35, differentiation: 0.2, risk: 0.15`（可在 Skill 配置中改）。

---

### Phase 5 · Top 方案具体化（Instantiation）

**目的**：对 Top 1–2 组合产出可直接开写的论文骨架。

#### 5.5.1 产出要求（每个 Top 组合一份 `skeletons/skeleton_<N>_<journal>.md`）

1. **Title**：3–5 个候选，每个标注其 angle
2. **Abstract**：完整草稿 150–250 词，严格对齐该叙事的 thesis（完整段落）
3. **Introduction 骨架**：段落级意图（第一段要干什么、第二段要干什么……），每段标注服务于哪个 claim
4. **Contribution bullets**：3–4 条，每条必须映射回 `assets.json` 中的具体 asset id
5. **Related Work 切分策略**：
   - 分几类
   - 每类代表性工作（**必须**来自 `journals/<slug>.json.reference_papers`，不得编造）
   - 用户的工作落在哪个"空位"
6. **实验章节编排**：
   - 主实验（哪一个实验升到主角位）
   - 配菜（哪些放正文）
   - 附录（哪些降到附录）
   - **注意**：这可能与用户原来的编排不同，必须给出理由
7. **Figure 使用策略**（基于 `figures_manifest.json`）：
   - 每张图的位置建议（Fig 1 / Fig 2 / ... / 附录 / 删除）
   - 每张图是否需要**重做**（redraw）、**改 caption**（recaption）、**保持不变**（keep）
   - 若 `visual_claim` 与新叙事主 claim 不匹配 → 建议 recaption 或 redraw，给出新 caption 草稿
   - Fig 1 的建议必须特别写明：在新叙事下，Fig 1 应该第一眼传达什么
8. **Discussion / Future Work 立意**：与主 thesis 呼应的开放性问题
9. **Mode B 专属：Diff 视图**：
   - 相对于 `existing_narrative.json` 的差异（哪几句改、为什么改）
   - 标注"最小改动版"（仅 Abstract + Fig 1 caption）vs"完整改造版"（含章节重排）两档

#### 5.5.2 草稿粒度规范（设计决策）

- **Abstract**：产出完整段落（高价值、可审）
- **Introduction**：仅产出段落意图，**不产出完整段落**（避免幻觉具体数字 / 文献）
- **Related Work**：产出类别切分 + 代表作列表，**不产出正文**
- **Method / Experiments / Conclusion**：仅产出编排与意图

理由：控制幻觉风险 + 保留用户的"写作感"。

---

### Phase 6 · 对抗审稿模拟（Adversarial Review）

**目的**：以目标期刊审稿人视角硬核挑刺，显式量化叙事风险。

#### 5.6.1 处理逻辑

对每个 Top 组合：
1. 加载该期刊的 `reviewer_red_flags`
2. 以审稿人视角提出 3–5 条质疑
3. 每条质疑评估"现有实验能否回应"
4. 若不能 → 给出**最低成本补救**（限制在：补一个 ablation 片段 / 补一段分析 / 补一张图 / 改措辞 / 补一个附录证明）
5. **不得建议重做实验 / 换数据集 / 换方法**

#### 5.6.2 输出结构（`adversarial_review.json`）

```json
{
  "reviews": [
    {
      "target_narrative": "N1",
      "target_journal": "journal_a",
      "questions": [
        {
          "qid": "Q1",
          "concern": "方法是否在 out-of-domain 设定下 robust？",
          "severity": "high | medium | low",
          "addressable_by_existing_data": "yes | partial | no",
          "patch_type": "new-ablation-snippet | new-analysis | new-figure | rewording | appendix-note | none",
          "patch_cost_hours": 4,
          "patch_description": "从 Exp-3 的残差中切一张箱线图，加到 §4.4"
        }
      ]
    }
  ]
}
```

#### 5.6.3 汇总为补丁清单（`patches.json`）

将所有 review 中的 patch 按 `patch_cost_hours` 升序排列，标注对应叙事与期刊。用户据此决定做与不做。

---

### Phase 7 · 决策建议与投稿路径

**目的**：收束全链路，给出**可执行**的下一步。

#### 5.7.1 产出内容

- **主推方案**：(叙事 X, 期刊 Y) + 一句理由 + 关键风险
- **备胎方案**：(叙事 Z, 期刊 W) + 从主推转投的成本评估
- **2 周行动清单**：3–5 件具体事项（写哪个部分 / 做哪个补丁 / 读哪篇文献）
- **决策分岔点**：明确列出"什么情况下应该放弃主推改投备胎"

#### 5.7.2 输出位置

直接写入 `report.md` 末尾。同时在控制台/会话层面以简短结构回显。

---

## 6. 数据结构汇总

所有 JSON schema 统一存放于 `schemas/` 目录下（便于其他 skill 引用和校验）：

```
schemas/
├── assets.schema.json
├── journal_profile.schema.json
├── narrative_candidate.schema.json
├── fit_matrix.schema.json
├── adversarial_review.schema.json
└── patches.schema.json
```

建议每个 schema 写成 JSON Schema Draft-07 以便后续工具化校验。

---

## 7. 目录结构约定

### 7.1 Skill 源码布局

```
skills/journal-fit-advisor/
├── SKILL.md                        # 运行时 prompt，参考 paper-idea-advisor 结构
├── input_template.md               # 用户输入模板
├── README.md                       # 给开发者看的说明
├── schemas/                        # JSON Schema
│   └── *.schema.json
├── prompts/                        # 各 Phase 的子提示（可选，便于拆分）
│   ├── phase1_asset_extraction.md
│   ├── phase2_journal_profiling.md
│   ├── phase3_narrative_generation.md
│   ├── phase4_fit_scoring.md
│   ├── phase5_instantiation.md
│   └── phase6_adversarial_review.md
├── examples/                       # 样例 run（示范输入 + 期望输出）
│   └── example_01/
│       ├── input.md
│       ├── assets.json
│       └── ...
└── tests/                          # 最小可运行测试用例
    └── test_cases.yaml
```

### 7.2 运行时工作区布局（每篇论文一个）

```
.autoscholar/
└── <paper_id>/
    ├── run_meta.json
    ├── input.md
    ├── raw/
    │   ├── draft.pdf                       # Mode B 必有；Mode A 可无
    │   ├── figures/
    │   │   ├── fig_01_main_pipeline.png
    │   │   └── fig_02_main_results.pdf
    │   └── figures_manifest.json
    ├── assets.json
    ├── existing_narrative.json             # 仅 Mode B 存在
    ├── journals/
    │   ├── _venue_alias.json               # 期刊名规范化缓存
    │   ├── journal_a.json
    │   └── journal_b.json
    ├── narratives/
    │   ├── candidate_1.json
    │   ├── candidate_2.json
    │   └── ...
    ├── fit_matrix.json
    ├── skeletons/
    │   ├── skeleton_N1_journal_a.md
    │   └── skeleton_N3_journal_b.md
    ├── adversarial_review.json
    ├── patches.json
    └── report.md
```

`paper_id` 建议由 `slugify(working_title) + short_hash` 生成，确保同一篇论文的多次迭代都落到同一目录。

---

## 8. 关键设计决策与默认值

| 决策项 | 默认值 | 理由 | 修改位置 |
|---|---|---|---|
| 输入结构化 | 强制模板；Mode B 自动从 PDF 抽取 | 后续质量依赖结构化 | Phase 0 |
| 论文检索来源 | Semantic Scholar API（2a）+ Web（2b）双源 | 前者结构化稳定、后者补 Scope/Editorial | Phase 2 |
| 期刊画像缓存 | 14 天 TTL，双源独立失效 | 省 token、故障边界清晰 | Phase 2 |
| 叙事候选数量 | 生成 8 → 收敛 4–6 | 平衡多样性与输出长度 | Phase 3 |
| Mode B 基线 | 现有叙事以 N0 身份参评 | 允许"不改"成为合法结论 | Phase 4 |
| 草稿粒度 | Abstract 全文 / 其他仅意图 | 控幻觉 + 保留写作感 | Phase 5 |
| Figure 策略 | 按新叙事给 keep/recaption/redraw 建议 | 用户已有图应被复用而非忽视 | Phase 5 |
| 评分权重 | 0.3 / 0.35 / 0.2 / 0.15 | 证据支撑略高于口味匹配 | Phase 4 |
| 模块名 | `journal-fit-advisor` | 与 `paper-idea-advisor` 明确区分 | 全局 |
| 工作区位置 | `.autoscholar/<paper_id>/` | 便于与其他 skill 共享 | 全局 |
| 中间产物落盘 | 强制 | 使其他 skill 可消费 | 全局 |

---

## 9. 与 AutoScholar / codex 的集成接口

### 9.1 复用 AutoScholar 既有基础设施

本模块**尽量不重复造轮子**，明确复用：

| 能力 | 来源 | 使用位置 |
|---|---|---|
| Semantic Scholar 客户端 | AutoScholar 已有封装 | Phase 2a |
| PDF 解析 | Claude Skill `pdf-reading` 或项目已有 PDF 处理 | Phase 0 (Mode B) |
| Web 抓取 | 任何可用网页抓取能力（如 web_fetch） | Phase 2b |

如果项目内 Semantic Scholar 封装尚不覆盖 `venue + year` 过滤或批量 abstract 拉取，本模块开发时**顺便补齐**而非另起炉灶，保证整个 AutoScholar 的检索能力统一。

### 9.2 作为独立 Skill 被触发

触发关键词（写入 SKILL.md description）：
- "论文叙事"、"paper framing"、"期刊叙事"、"journal fit"
- "论文讲法"、"投稿策略（且算法已定）"、"narrative for my paper"
- "已经做完实验，怎么写论文"、"选哪个期刊更合适"

### 9.3 作为 AutoScholar pipeline 的一环

提供一个最小 CLI 入口（建议 Python），供 codex 从脚本侧调用：

```bash
# 一次性跑完所有 Phase
autoscholar jfa run --paper-id <id> --input input.md

# 分阶段跑
autoscholar jfa phase1 --paper-id <id>
autoscholar jfa phase2 --paper-id <id> --journal "Nature Methods"
autoscholar jfa phase3 --paper-id <id>
...

# 强制刷新期刊缓存
autoscholar jfa phase2 --paper-id <id> --no-cache
```

每个 Phase 命令严格遵守"读输入文件 → 写输出文件"的纯函数式接口，便于单测。

### 9.3 与未来 `draft-writer` skill 的衔接

本模块产出的 `skeletons/*.md` + `assets.json` 被设计为未来"草稿生成 skill"的标准输入。因此 skeleton 的段落意图字段需保持可机器解析（建议用固定 tag，如 `<intent>...</intent>`）。

---

## 10. 异常处理

| 情景 | 处理策略 |
|---|---|
| 用户输入未填模板 | Phase 0 返回带填写示例的模板，终止 |
| 用户要求改算法 | 提示 fallback `paper-idea-advisor`，终止 |
| 卖点抽取少于 4 条 | 报告"素材包过薄"，建议用户补充实验细节后重跑 |
| 期刊搜索结果过少（< 5 篇相关） | 警告"口味画像置信度低"，在 report 中显式标注 |
| 叙事候选去重后少于 3 个 | 报告"叙事空间偏窄"，Phase 4 仍继续但给出警告 |
| 所有 Top 组合的 taste_fit < 3 | 建议用户重新考虑目标期刊选择 |
| 网络失败 / 搜索工具不可用 | Phase 2 降级：仅使用官网 scope + 用户已有知识，显式标注"低置信画像" |

---

## 11. 验收标准（给开发者的 checklist）

模块开发完成后，必须通过以下验收项：

**功能性**：
- [ ] 用 `examples/example_01` 跑通完整流程，产出所有中间文件与最终 `report.md`
- [ ] 分阶段调用（Phase 1 → 2 → ... → 7）结果与一次性跑完一致
- [ ] 关闭网络时 Phase 2 能降级运行并显式标注低置信

**质量性**：
- [ ] 卖点表条目数在 8–15 之间
- [ ] 每本目标期刊的 `reference_papers` ≥ 5 条
- [ ] 叙事候选数在 4–6 之间，且两两 thesis 有明显差异
- [ ] 每个叙事的主 claim **必然**能映射回至少一个 `strong` asset
- [ ] Phase 6 所有 patch 的 `patch_type` ∈ 允许集合（不得出现"重做实验"类建议）

**接口性**：
- [ ] 所有 JSON 产物能通过对应 schema 校验
- [ ] `paper_id` 目录结构完整、命名一致
- [ ] 控制台回显简洁（Top 方案 + 风险 + 2 周清单），不把完整 report 刷屏

**边界性**：
- [ ] 输入描述算法可变时，模块能识别并 fallback
- [ ] 输入未填模板时，模块能拒绝进入 Phase 1

---

## 12. 扩展路线图（不在 v0.1 范围，但留接口）

| 扩展项 | 说明 | 预计依赖 |
|---|---|---|
| **拆分可行性分析** | 素材过厚时，建议拆成两篇 | 新增 Phase 4.5 |
| **Cover Letter 生成** | 基于 Top 叙事自动生成投稿信 | 消费 `skeletons/*.md` |
| **Rebuttal 演练** | 收到真实 review 后做一致性分析 | 复用 Phase 6 的对抗框架 |
| **多版本对比** | 同一 (narrative, journal) 多次迭代的 diff | `paper_id` 支持版本号 |
| **Figure 1 建议** | 基于 Top 叙事建议核心 figure 的形式 | 消费 `narratives/*.json` |

上述扩展不要求现在实现，但当前版本的**数据结构与目录结构设计必须允许这些扩展无痛接入**（即：不要写死只支持单叙事、不要把产物耦合在单一 report 文件里）。

---

## 13. 开发优先级建议

如果分 sprint 实现，建议顺序：

1. **Sprint 1（骨架）**：Phase 0 + 输入模板 + 工作区目录 + CLI 入口
2. **Sprint 2（核心）**：Phase 1 + Phase 3 + Phase 4（先跑通不依赖网络的核心链路）
3. **Sprint 3（外部信息）**：Phase 2 + 缓存机制
4. **Sprint 4（落地）**：Phase 5 + Phase 6 + Phase 7 + `report.md` 汇总
5. **Sprint 5（打磨）**：JSON Schema 校验、异常处理、examples、tests

每个 Sprint 结束都应能端到端跑通（可能降级运行），避免最后一次性集成。

---

## 14. 附录 · SKILL.md 骨架参考

```markdown
---
name: journal-fit-advisor
description: 论文叙事与期刊匹配顾问。当用户已完成算法设计与核心实验（不再变动），希望基于目标期刊偏好优化论文叙事与讲法时，触发此 Skill。产出：叙事候选、匹配评分、论文骨架、对抗审稿补丁清单。触发关键词：论文叙事、期刊叙事、journal fit、paper framing、实验做完了怎么写论文、选哪个期刊合适、同一篇投不同期刊怎么讲。不适用场景：算法未定 / 想改实验 / 仅想评估 idea 潜力（这些走 paper-idea-advisor）。
---

# Journal Fit Advisor — 论文叙事与期刊匹配顾问

## 角色定位
你是一位兼具**顶刊主编视角**与**资深审稿人嗅觉**的学术叙事顾问……

## 核心约束
- 算法 I/A/O 与核心实验为**不可变参数**
- 本模块**不建议**新增重型实验
- 若用户要求改算法/加重型实验 → 建议 fallback 到 `paper-idea-advisor` 并终止

## 工作流程
[Phase 0 → 7，内容同本开发文档 §5]

## 输出规范
- 中文叙事 + 英文专业术语
- 所有中间产物落盘到 `.autoscholar/<paper_id>/`
- 最终汇总到 `report.md`
- 严禁引用不存在的实验或文献
```

---

**文档结束**

如需进一步细化某个 Phase 的实现细节（如 Phase 2 的搜索策略、Phase 3 的去重算法、Phase 4 的权重调优），可在本文档基础上追加子章节。
