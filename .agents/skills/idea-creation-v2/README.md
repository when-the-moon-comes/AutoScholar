# idea-creation-v2

对话式 idea 孵化 skill。旧版 `idea-creation` 的升级版本。

## 设计哲学

旧版 `idea-creation` 把 idea 当成"种子论文 → Track A/B 排列组合 → 卡片"的流水线。新版把 idea 当成"模糊冲动 → 五阶段对话 → 命名"的状态机。

**共脑原则**：研究者和 Claude 在每一轮都做对方做不了的事。
- 研究者做：判断、选择、承诺、品味、承担代价
- Claude 做：覆盖、反驳、形式化变换、强制提出平行选项

违反这个分工的对话轮是无效轮。

## 文件结构

```
idea-creation-v2/
├── SKILL.md                              # 核心 skill 描述，触发规则
├── README.md                             # 本文件
├── references/
│   ├── input-templates.md                # 四种起点形态的输入模板
│   ├── stage-playbook.md                 # 五阶段详细操作手册
│   └── autoscholar-integration.md        # 与 AutoScholar 的集成/非集成边界
├── schemas/
│   ├── stage1_diagnosis.schema.json
│   ├── stage2_alternatives.schema.json
│   ├── stage3_pruning.schema.json
│   ├── stage4_failure_narratives.schema.json
│   └── stage5_identity.schema.json
└── workspace_template/
    ├── workspace.yaml.j2                 # workspace manifest 模板
    ├── idea_seed.md                      # 研究者填的输入种子
    └── conversation.yaml                 # 检索预算 + 阶段阈值
```

## 安装到 AutoScholar

### 1. 复制 skill 到仓库
```bash
cp -r idea-creation-v2/ <autoscholar-repo>/.agents/skills/
```

### 2. 在 workspace 模板注册表中注册
编辑 `src/autoscholar/workspace/templates.py`（或等效位置），新增：
```python
"idea-creation-v2": {
    "template_path": ".agents/skills/idea-creation-v2/workspace_template",
    "required_inputs": ["idea_seed.md"],
    "required_configs": ["conversation.yaml"],
}
```

### 3. 在 report-authoring skill 中新增渲染 kind
新增 `idea-conversation` kind 的 Jinja 模板，从五阶段 artifacts 合成最终 markdown 报告。

### 4. 更新顶层 routing
在 `.agents/skills/autoscholar/SKILL.md` 的 capability routing 里区分：
- `idea-creation`（旧）：有种子论文 + 想要候选列表 → 用它
- `idea-creation-v2`（新）：有模糊冲动 + 想要孵化 → 用它
- `idea-evaluation`：有成型 idea + 想要评估 → 用它

## 使用流程

```bash
# 1. 初始化 workspace
autoscholar workspace init D:\workspaces\my-idea \
  --template idea-creation-v2 \
  --reports-lang zh

# 2. 研究者填 inputs/idea_seed.md（选一种形态）
# 3. 与 Claude 对话，Claude 会：
#    - 识别形态
#    - 执行五阶段状态机
#    - 在检索时机调用 autoscholar semantic / citation 命令
#    - 写入 artifacts/stageN_*.json

# 4. 最终渲染
autoscholar report render --workspace D:\workspaces\my-idea --kind idea-conversation
```

## 五阶段速览

| Stage | 任务 | 主导方 | 检索强度 | 典型轮数 |
|-------|------|--------|---------|---------|
| 1. 输入压测 | 诊断输入弱点 | 研究者 | 轻（<5） | 1-2 |
| 2. 对抗展开 | 造 3-5 个平行 framing | Claude | 中（15-25） | 2-4 |
| 3. 方法裁剪 | 约束驱动消元 | 共同 | **重**（full pipeline） | 2-4 |
| 4. 证伪设计 | 写失败叙事 | Claude | 中（每叙事 3-5） | 1-2 |
| 5. 命名收敛 | 做取舍、选名字 | 研究者 | 无 | 1 |

四种形态在不同阶段的承重不同，详见 `SKILL.md`。

## 与旧 idea-creation 共存

旧版不删除。使用场景：
- 旧版：从一篇具体 seed paper 出发、想要一批候选卡片供进一步筛选
- 新版：从一个模糊的研究冲动出发、想要把它推到可决策状态

二者互补，不替代。

## 失败模式警告

Claude 必须主动识别并打断以下失败：
1. 角色倒错（Claude 判断 / 研究者穷举）
2. 模板填充化（对话变成填字段）
3. 检索泛滥（每轮都跑 citation search）
4. 过早收敛（Stage 2 没做就跳 Stage 3）
5. 命名推迟（Stage 5 被省略）

识别到以上任一，立刻指出并拉回正确路径。
