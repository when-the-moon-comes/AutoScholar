# AutoScholar 集成：边界与耦合点

本文档规定 idea-creation-v2 skill 如何与 AutoScholar 主体能力集成，**同样重要的是规定不集成什么**。

## 集成哲学

- AutoScholar 提供**基础设施**（workspace / semantic API / citation pipeline / report rendering）
- idea-creation-v2 提供**过程**（五阶段对话状态机 + 非对称分工）
- 二者在**具体检索时机**耦合，不互相吞并

换句话说：skill 不重新造 Semantic Scholar 客户端；AutoScholar 的 CLI 不被改造去做对话。

---

## 明确**不**集成的能力

以下能力看似相关，但接入后会破坏对话流程，**禁止自动调用**：

### ❌ `autoscholar idea assess`
- 原因：这是 rubric-based 评估器，对已有 idea 打分
- 问题：如果在对话中自动调用，每轮都会被 rubric 拖回填表模式，违背"emergent"原则
- 替代：如果研究者明确要求对选定 idea 做最终评估，在 Stage 5 之后、作为可选后置步骤调用

### ❌ 旧版 `idea-creation` Track A/B 双轨流程
- 原因：固定 schema，产出 idea cards
- 问题：它假设所有 idea 都从种子论文出发，和新版的四形态识别冲突
- 替代：α 型（有种子论文）研究者可以**在 Stage 2** 选择性调用 Track A/B 作为生成 alternatives 的策略之一

### ❌ `journal-fit-advisor`
- 原因：完全正交的功能（投稿期刊匹配）
- 替代：Stage 5 完成后可推荐研究者独立运行 `jfa`，但不自动触发

### ❌ 自动生成 `idea_cards.md`
- 原因：卡片化输出鼓励把 idea 当独立单元执行，和"对话轨迹 + 命名收敛"不兼容
- 替代：最终产物是 `idea_conversation_record.md`

---

## 具体集成点

### 集成点 1：Workspace 模板

在 AutoScholar workspace 系统中新增模板 `idea-creation-v2`：

```bash
autoscholar workspace init <path> --template idea-creation-v2 --reports-lang zh
```

初始化时创建：

```
<workspace>/
├── workspace.yaml
├── inputs/
│   ├── idea_seed.md              # 研究者填写 α/β/C/D 模板
│   └── constraints.yaml          # 研究者的真实约束（Stage 3 用）
├── configs/
│   └── conversation.yaml         # 检索预算、阶段阈值
├── artifacts/
│   ├── stage1_diagnosis.json
│   ├── stage2_alternatives.json
│   ├── stage3_pruning.json
│   ├── stage4_failure_narratives.json
│   ├── stage5_identity.json
│   └── retrieval/                # 子目录，存放各阶段检索产物
│       ├── stage1_uniqueness_check.jsonl
│       ├── stage2_density_per_alt.jsonl
│       ├── stage3_shortlist.jsonl
│       └── stage4_failure_evidence.jsonl
└── reports/
    └── idea_conversation_record.md
```

`conversation.yaml` 默认内容：

```yaml
retrieval_budgets:
  stage1: 5
  stage2_per_alt: 5
  stage3_per_survivor: 50   # shortlist 使用
  stage4_per_narrative: 5
  stage5: 0

stage_gates:
  stage1_max_rounds: 3
  stage2_min_alternatives: 3
  stage2_max_alternatives: 5
  stage3_max_survivors: 3

form_types_allowed: [alpha, beta, gamma, delta]
```

---

### 集成点 2：Stage 1 — framing 唯一性检查

**调用动作**：
```bash
# Claude 基于用户填的模板提取 1-3 个紧凑查询
autoscholar semantic smoke               # 可选：确认 API 可达
autoscholar semantic paper <query>       # 检查有没有论文直接命名这个 framing
```

**写入 artifact**：
- 结果存到 `artifacts/retrieval/stage1_uniqueness_check.jsonl`
- 命中的已有命名写到 `stage1_diagnosis.json` 的 `framing_uniqueness_check` 字段

**预算**：< 5 次调用

**何时**：Stage 1 第 1 轮，在 Claude 做诊断同时进行

---

### 集成点 3：Stage 2 — 每个 alternative 的密度查询

**调用动作**：
```bash
# 对每个 alternative，构造 2-3 个轻量查询
# 不走 prescreen / shortlist，只看 raw search 结果
autoscholar semantic paper <query-per-alt>
```

**写入 artifact**：
- 每个 alternative 的 representative papers 写到 `stage2_alternatives.json`
- Raw 结果存到 `artifacts/retrieval/stage2_density_per_alt.jsonl`

**预算**：每个 alt 3-5 次调用，总 15-25 次

**何时**：Claude 生成 alternatives 之后，在请研究者排序之前

---

### 集成点 4：Stage 3 — 完整 citation pipeline

**这是整个流程里唯一使用完整 citation pipeline 的地方**。

**调用动作**：
```bash
# 对每个 stage3 survivor，构造 claims 并运行完整 pipeline
autoscholar citation search --workspace <path>
autoscholar citation prescreen --workspace <path>
autoscholar citation correct --workspace <path>
autoscholar citation shortlist --workspace <path>
autoscholar report render --workspace <path> --kind shortlist
```

**写入 artifact**：
- Shortlist 结果存到 `artifacts/retrieval/stage3_shortlist.jsonl`
- 文献密度判断写到 `stage3_pruning.json` 的 `survivors[].literature_density` 字段

**预算**：每个 survivor ≤ 50 篇（由 shortlist 配置决定）

**何时**：Claude 完成消元并锁定 2-3 个 survivor 之后

**注意**：
- pipeline 的 claims 由 Claude 根据 survivor 的 framing + method 自动构造，写入 `inputs/claims.md`
- 研究者可以介入修改 claims（AutoScholar 原生支持）

---

### 集成点 5：Stage 4 — references / citations 追溯

**调用动作**：
```bash
# 对 Stage 3 survivor 的代表性论文做引文追溯
autoscholar semantic references CorpusID:xxx
autoscholar semantic citations CorpusID:xxx
```

**写入 artifact**：
- 追溯发现的相关证据存到 `artifacts/retrieval/stage4_failure_evidence.jsonl`
- 关键证据写到 `stage4_failure_narratives.json` 的 `supporting_evidence_from_retrieval`

**预算**：每个失败叙事 3-5 次调用

**何时**：Claude 写完失败叙事之后，研究者给出预防设计之前

---

### 集成点 6：最终报告渲染

**调用动作**：
```bash
autoscholar report render --workspace <path> --kind idea-conversation
autoscholar report validate --workspace <path> --kind idea-conversation
```

需在 AutoScholar 的 `report-authoring` skill 里新增 `idea-conversation` kind 的 template。模板结构：

```
# {final_identity.title}

**One-sentence pitch**: {final_identity.one_sentence_pitch}
**Community**: {final_identity.community}
**Contribution type**: {final_identity.primary_contribution_type}

## 起点（Stage 1 诊断后）
...从 stage1_diagnosis.json 渲染...

## 为什么不走其他 framing（Stage 2 排序）
...

## 方法选择与消元过程（Stage 3）
...

## 已知风险与预防设计（Stage 4）
...

## 命名取舍（Stage 5）
选择 "{selected_name}" 意味着放弃了：{sacrifice_statement}

## 检索附录
- Stage 1 唯一性检查：...
- Stage 2 密度查询：...
- Stage 3 shortlist：...
- Stage 4 失败证据：...
```

---

## 引入到现有 AutoScholar 仓库的改动清单

以下是要在现有仓库里改的（最小改动集）：

### 1. 新增 skill 目录
```
.agents/skills/idea-creation-v2/
├── SKILL.md
├── references/
│   ├── input-templates.md
│   ├── stage-playbook.md
│   └── autoscholar-integration.md
├── schemas/
│   ├── stage1_diagnosis.schema.json
│   ├── stage2_alternatives.schema.json
│   ├── stage3_pruning.schema.json
│   ├── stage4_failure_narratives.schema.json
│   └── stage5_identity.schema.json
└── workspace_template/
    ├── workspace.yaml.j2
    └── configs/conversation.yaml
```

### 2. 在 `src/autoscholar/workspace/` 注册新模板
在 workspace template registry 里添加 `idea-creation-v2`，指向本 skill 的 `workspace_template/`。

### 3. 在 `.agents/skills/report-authoring/` 新增渲染 kind
为 `idea-conversation` kind 新增 Jinja 模板和 renderer 逻辑。

### 4. 更新顶层 `.agents/skills/autoscholar/SKILL.md`
在 capability routing 里加入 idea-creation-v2 的触发描述，与现有 idea-creation / idea-evaluation 清晰区分：
- `idea-creation`（旧）：从种子论文出发、Track A/B、产出 cards
- `idea-creation-v2`（新）：模糊 idea 的对话孵化、五阶段、产出 record
- `idea-evaluation`：对已成型 idea 做 rubric 评估

### 5. `README.md` 新增 quickstart section
```bash
autoscholar workspace init D:\workspaces\my-idea --template idea-creation-v2 --reports-lang zh
# Claude 读取 inputs/idea_seed.md，进入五阶段对话
# 每阶段产出 artifacts/stageN_*.json
autoscholar report render --workspace D:\workspaces\my-idea --kind idea-conversation
```

---

## 失败集成的识别

如果发现以下现象，说明集成出了问题：

1. **检索泛滥**：每轮对话都在跑 pipeline，对话被淹没
2. **CLI 主导**：Claude 每次都先说"让我先跑 autoscholar ..."再对话
3. **Artifact 驱动**：研究者在填字段而不是在思考
4. **模板吞并**：对话的 emergent 空间被 schema 压扁

发现这些症状，立刻拉回到"skill 是主线，AutoScholar 是工具"的关系。
