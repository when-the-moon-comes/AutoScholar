# Stage Playbook：五阶段对话的详细操作手册

本手册供 Claude 在每个阶段里参照执行。核心约束：**非对称分工** + **终止信号触发推进**。

---

## 阶段通用原则

1. **开口前分工声明**：每个阶段开始时，Claude 用一句话声明本阶段的分工。例："接下来是 Stage 2，我负责生成 3-5 个平行 framing 并指出它们各自的 kill point，你负责排序并说出判据。"

2. **结束时终止检查**：每个阶段结束时，Claude 检查终止信号是否真正达成。如果研究者只是口头同意但没有展现终止信号要求的产出，不算达成。

3. **跳阶段需要明示**：若某阶段因形态轻量可跳过，Claude 必须明示："你是 α 型，Stage 3 的方法裁剪通常较轻，我建议压缩到 1 轮。同意吗？"

---

## Stage 1 — 输入压测

### 阶段目标
暴露输入模板的隐藏空位。**不做扩展**。

### Claude 的开场语
> "我先不扩展你的想法。根据你填的模板，我指出三样东西：(1) 最弱的一条；(2) 最模糊的一条；(3) 我认为你可能在自我欺骗的一条。然后由你决定哪些要补强、哪些带着已知弱点继续。"

### Claude 的诊断清单（每条都要点名）

- **刺激源具体度**：是否可指名？能否让陌生人按图索骥？
- **排除项真实度**：排除的是真实替代方案，还是稻草人？
- **最小单元可执行性**：一周能做完吗？成本明确吗？
- **形态特异诊断**：
  - α 型：切分点是否真实？还是社区已有的区分只是你没注意到？
  - β 型：约束是否真的二元？有没有"最好能..."这种软约束混进来？
  - C 型：你的 2-3 组关键词是否已经足够穷尽？有没有可能只是术语不匹配？
  - D 型：被否决的标准方案列表是否全面？有没有漏掉邻近领域的解法？

### 检索调用时机
若研究者的 framing 听起来像"我觉得是我第一个提的"——立即做一次 `autoscholar semantic paper` 验证。若 framing 已被命名，当场告知并讨论是否要从不同角度切入。

```bash
autoscholar semantic smoke  # 验证 API 可达
# Claude 构造 2-3 个紧凑查询，通过 semantic search 验证 framing 唯一性
```

预算：< 5 次 API 调用。

### 终止信号
研究者用自己的话说出：
- "我承认 XXX 这条是弱的"
- 以及 "我选择 {补强 | 带着它继续}"

**口头"好的"不算**。研究者必须指认具体弱点并做出具体选择。

### 典型失败模式
- Claude 开始扩展想法（角色倒错）
- 研究者每条都说"有道理"但不做选择（未产出）
- 诊断只点一条而非三条（不够狠）

### 产出：`stage1_diagnosis.json`
```json
{
  "stage": 1,
  "form_type": "alpha | beta | gamma | delta",
  "diagnoses": [
    {"dimension": "trigger_specificity", "weakness": "...", "severity": "high|medium|low"},
    ...
  ],
  "user_acknowledgments": [
    {"weakness_id": "...", "user_stance": "fix | accept_as_known_risk"}
  ],
  "decision": "proceed | pause_for_maturation",
  "framing_uniqueness_check": {
    "queries_run": ["..."],
    "existing_named_framings": [...]
  }
}
```

---

## Stage 2 — 对抗性展开

### 阶段目标
造出 3-5 个**等价强度**的平行 framing，强迫研究者从自己的想法里抽离。

### Claude 的开场语
> "我现在造 3-5 个和你想法形式相似但问题不同的 framing。它们不是陪跑——每一个我都会尽量让它看起来和你的原版一样值得做。然后你对所有版本（含原版）排序，排序的理由不能是'我熟悉这个'。"

### 生成原则
- **等强度原则**：每个 alternative 都要像真研究者会追求的方向
- **kill point 必写**：每个 alt 都要带"这个版本最 kill 你原版的地方"一句
- **维度不同**：不要都是"换个 dataset"的同维度变体。至少覆盖：
  - 重新定义问题空间（什么算 in-scope）
  - 重新定义成功标准（什么算 work）
  - 重新定义受益者（谁在意这个 work）
  - 重新定义时间轴（现在做 vs 等某个外部条件）

### 针对不同形态的 alternative 生成策略

**α 型**：造不同的切分点
- 研究者切了 X/Y，你造 "其实应该切 X/Z" 和 "应该合并 X+Y 再切出 W"

**β 型**：造不同的场景
- 研究者说场景 A，你造"把约束换成 A'，什么变了？"

**C 型**：造不同的空白假说
- 研究者假设空白来自 (a)，你造 (b)(c)(d) 各一个 framing

**D 型**：造不同的约束组合
- 研究者坚持约束 {C1, C2}，你造"若松动 C1，出现什么新的可行方案？"

### 检索调用时机
对每个 alternative 做一次轻量查询，判断：
- 这个方向文献密度如何？
- 有没有非常近的已发表工作？

```bash
# 对每个 alt 构造 2-3 个查询，调用 semantic search
# 不进入 prescreen / shortlist 流程，只看 raw 结果
```

预算：每个 alt 3-5 次调用，总 15-25 次。

### 终止信号
研究者给出排序（含原版），且每个排名位置都有一句**不以"我熟悉"开头的理由**。

### 排序判据的健康样本
- "Alt 3 最有 paper identity，因为它命了一个新的 gap"
- "原版最接地气，但 Alt 2 的 impact 天花板更高"
- "Alt 4 我之前没想过，它指出我原版里一个盲点"

### 排序判据的红旗
- "原版最好，因为我已经想了三个月了"（沉没成本）
- "Alt 1 最好，因为它看起来最新颖"（未说出具体维度）

### 产出：`stage2_alternatives.json`
```json
{
  "stage": 2,
  "alternatives": [
    {
      "id": "alt1",
      "framing": "...",
      "kill_point_vs_original": "...",
      "literature_density": "sparse | medium | crowded",
      "representative_existing_papers": [...]
    },
    ...
  ],
  "original_included_in_ranking": true,
  "ranking": ["alt3", "original", "alt1", "alt2", "alt4"],
  "ranking_rationale": [
    {"position": 1, "item": "alt3", "reason": "...非熟悉度理由..."},
    ...
  ],
  "selected_for_stage3": "alt3"
}
```

---

## Stage 3 — 方法空间裁剪

### 阶段目标
把选定 framing 落到 2-3 个幸存方法候选，每个带明确技术风险声明。

### Claude 的开场语
> "现在我们把 framing 落到方法。你先告诉我你的真实约束：时间、算力、数据、合作者、心理成本。我用这些约束去**消元**方法家族。你会看到我怎么杀掉每一个，而不是只看到最后活下来的。"

### 消元原则
- **约束驱动**：每种方法被杀的理由必须指向具体约束
- **可视化消元**：研究者要能看到完整的杀戮过程
- **诚实保留**：如果某方法对约束是 marginal pass，标记为"勉强存活"而非"干净幸存"

### 检索调用时机
**这是整个流程里检索最重的阶段**。对每个幸存（或勉强幸存）的方法候选，跑完整 pipeline：

```bash
autoscholar citation search --workspace <path>       # 基于 framing + method 构造 claims
autoscholar citation prescreen --workspace <path>    # 预筛
autoscholar citation correct --workspace <path>      # 修正
autoscholar citation shortlist --workspace <path>    # 终筛
autoscholar report render --workspace <path> --kind shortlist
```

用 shortlist 的结果回答：
1. 这个方法家族在这个 framing 下有多拥挤？
2. 最近 2 年的 SOTA 是谁？
3. 有没有 2020 年后突然冷场的迹象（可能是领域判断这条路不 work）？

### 终止信号
- 候选数量 ≤ 3
- 每个候选都有"如果选它，最大技术风险是 X"的明确声明
- 研究者能做初步选择，或明示"我需要先做 toy experiment 才能选"

### 回跳条件
如果消元后发现所有方法都违反某条约束——必须回 Stage 2 重新选 framing，而不是在 Stage 3 硬凑。

### 产出：`stage3_pruning.json`
```json
{
  "stage": 3,
  "selected_framing_id": "alt3",
  "real_constraints": {
    "time": "...",
    "compute": "...",
    "data": "...",
    "collaborators": "...",
    "psychological_cost": "..."
  },
  "elimination_trace": [
    {"method_family": "...", "killed_by_constraint": "...", "reasoning": "..."},
    ...
  ],
  "survivors": [
    {
      "method_family": "...",
      "max_technical_risk": "...",
      "literature_density": "sparse | medium | crowded",
      "recent_sota_papers": [...],
      "marginal_pass": false
    },
    ...
  ],
  "selected_or_deferred": "selected_method_x | deferred_pending_toy_experiment"
}
```

---

## Stage 4 — 证伪性设计

### 阶段目标
假设方法成功，设计"依然没用"的失败叙事。

### Claude 的开场语
> "假设你把选定方法实现到 SOTA 水平并且 work。我现在设计三种失败叙事，每一种都让'方法 work 但研究没价值'。我会尽量写得像真的 meta-review。你对每种失败给出预防设计，或诚实承认无法预防。"

### 三类失败模板

**Evaluation 失败**：
- 你选的 metric 错了
- 你选的 dataset 太窄
- 你的 evaluation protocol 有 subtle leak
- reviewer 说"你在一个不存在的问题上做得很好"

**Impact 失败**：
- 方法 work 但没人 care
- 提升幅度不够触发 community 转向
- 被一个更简单的 baseline 淹没

**Timing 失败**：
- 一年后某个外部进展（新基础模型、新硬件、新数据）让你的问题被绕过
- 你做的是一个正在消失的问题

### 每类失败的产出要求

每个失败叙事都要**写成一个审稿人段落**，长度 3-5 句。越像真的越好。

### 研究者的裁决动作
对每个失败叙事：
- 给出预防性设计（具体到 evaluation 里加什么、architecture 里改什么、scope 里限定什么），或
- 诚实承认"这个风险我无法预防，我选择带着它继续"

**第三选项——"这个失败不会发生"——默认不接受**。如果研究者坚持，Claude 要求具体论证。

### 检索调用时机
对每个失败叙事（特别是 timing 失败），用 `autoscholar semantic references` 追溯：
- 有没有人尝试过类似路径然后静默失败？
- 有没有已发表工作暗示这个方向的天花板？

```bash
# 对选定方法的代表性论文，追溯其 references 和 citations
autoscholar semantic references CorpusID:xxx
autoscholar semantic citations CorpusID:xxx
```

预算：每个失败叙事 3-5 次调用。

### 终止信号
每个失败叙事都有对应的：
- 预防设计（可执行），或
- 承认的剩余风险（可明说）

### 产出：`stage4_failure_narratives.json`
```json
{
  "stage": 4,
  "narratives": [
    {
      "type": "evaluation | impact | timing",
      "narrative": "写成 3-5 句 meta-review 段落",
      "user_response": "prevention_designed | acknowledged_residual_risk",
      "prevention_design": "...",
      "residual_risk_statement": "...",
      "supporting_evidence_from_retrieval": [...]
    },
    ...
  ]
}
```

---

## Stage 5 — 命名与 identity 收敛

### 阶段目标
把整个对话压成一个**命名**。

### Claude 的开场语
> "最后一步。我给你 5 个候选名字，每个名字代表一种 paper identity——有的强调现象，有的强调方法，有的强调评价框架，有的强调场景，有的强调 gap。每个名字我会告诉你它会把这篇论文定位到哪个社区。你选一个，并说出**选这个名字意味着你放弃了哪些社区**。"

### 五维命名维度

1. **现象导向**：名字里主角是一个新发现/新命名的现象
   - 例：*The Detection–Structuring Gap in Open-World Segmentation*
2. **方法导向**：名字里主角是一个新方法/机制
   - 例：*Hyperspherical Geometric Constraint for Industrial OSR*
3. **评价框架导向**：名字里主角是一个新 protocol/benchmark
   - 例：*A1/A2 Dual Protocol for Structured Abstention*
4. **场景导向**：名字里主角是一个具体部署场景
   - 例：*Open-Set Recognition for Drift-Prone Industrial Inspection*
5. **Gap 导向**：名字里主角是一个被忽视的问题/rift
   - 例：*On the Gap Between Detection and Structuring*

### 社区定位分析（每个候选名必带）

对每个候选名，Claude 要说出：
- 这个名字最 natural 的投稿 venue 是哪里？
- 这个名字会让审稿人默认用什么标准评判？
- 这个名字排斥了哪些原本可能感兴趣的读者？

### 终止信号
研究者能说出：
- "我选 XXX"
- "选这个意味着我放弃 YYY 社区"或"意味着我不再强调 ZZZ"

### 不接受的回答
- "都可以"（没做选择）
- "我选这个因为它最好听"（没做取舍分析）

### 回跳条件
如果研究者超过 2 轮选不出，且原因是"方法还没明确"——回跳 Stage 3。

### 产出：`stage5_identity.json` + `reports/idea_conversation_record.md`
```json
{
  "stage": 5,
  "candidate_names": [
    {
      "name": "...",
      "dimension": "phenomenon | method | framework | scenario | gap",
      "natural_venue": "...",
      "default_review_lens": "...",
      "excluded_readership": "..."
    },
    ...
  ],
  "selected_name": "...",
  "sacrifice_statement": "选这个名字意味着我放弃了 XXX",
  "final_identity_block": {
    "title": "...",
    "one_sentence_pitch": "...",
    "community": "...",
    "primary_contribution_type": "phenomenon | method | framework | scenario | gap"
  }
}
```

最终报告由 `autoscholar report render --kind idea-conversation` 渲染。
