# 开放世界识别讲义：第 1 层术语骨架

生成日期：2026-04-26  
层级：terminology。本讲义只建立词表和边界，不写方法史、代表实验室或时间线。  
证据状态：已运行 `autoscholar handout init "open world recognition computer vision" --level terminology --output-dir handouts\openworldrecognition-terminology`。原始查询 2/4 成功但命中较杂；补充精确查询 5/5 触发 Semantic Scholar 429。术语判断主要锚定 `artifacts/web_evidence.jsonl` 中的主来源，失败记录保留在 `artifacts/semantic_failures*.jsonl`。

## 1. 核心词表

1. 闭集识别 closed-set recognition：训练类和测试类被假定相同，模型必须在已知类中选一个答案。
2. 开放集识别 open-set recognition, OSR：测试时可能出现训练未见类别，模型需要分类已知样本并拒识未知样本 [T01]。
3. 开放世界识别 open-world recognition, OWR：OSR 加上“发现未知、获得标签、增量纳入新类”的运行闭环 [T02]。
4. 已知类 known class：当前训练阶段有标签并参与监督学习的类别。
5. 未知类 unknown class：当前训练阶段未见、但测试或部署中出现的语义类别。
6. 未知拒识 unknown rejection：模型输出 unknown 或风险信号，而不是强行归入某个已知类。
7. 开放空间风险 open space risk：模型在远离训练样本支持区域的空间仍给出高置信已知类预测的风险 [T01]。
8. Openness：描述训练类、测试类、目标类集合差异大小的设置指标；它不是模型性能。
9. OOD detection：判断样本是否来自 in-distribution。OOD 可由新语义类、域变化、噪声或损坏引起 [T04][T10]。
10. 语义偏移 semantic shift：未知来自新语义类别，而非低层风格、传感器或图像质量变化 [T09]。
11. 异常 anomaly / outlier：偏离常态的样本；可能是坏图，也可能不是新类别。
12. 新颖类 novel class：训练阶段未标注、但评测或后续阶段可能已命名的类别。
13. MSP：最大 softmax 概率，用最高类别概率作为置信度或 OOD 基线 [T04]。
14. Energy score：从分类器 logit 构造的分数，用于区分 ID/OOD 或已知/未知 [T08]。
15. 阈值 threshold：把连续风险分数变成 accept/reject 决策的界线。
16. 校准 calibration：模型分数与真实正确概率的一致性；校准好不等于能识别未知。
17. OpenMax / EVT：用极值理论建模类别激活尾部，并为 unknown 分配概率 [T03]。
18. 特征距离 feature distance：用原型距离、Mahalanobis 距离等判断样本是否靠近已知类 [T06]。
19. Oracle / human-in-the-loop：为未知样本提供真实标签或确认新类的外部机制。
20. 增量学习 incremental learning：在不完全重训的情况下学习新类或新任务；它不自动包含未知检测 [T17][T18]。
21. 灾难性遗忘 catastrophic forgetting：学习新类后旧类性能下降。
22. 开放世界目标检测 OWOD：检测已知物体，同时发现未知前景，并在后续阶段学习新类 [T11]。
23. Unknown foreground：图像中确实是物体、但不属于当前已知类别的区域；它不是普通背景。
24. 开放词表 open-vocabulary：测试时用文本标签扩展候选类别；大词表不等于能输出 unknown [T14]-[T16]。

## 2. 近义词边界矩阵

| 易混术语 | 共同点 | 关键边界 | 误用后果 |
|---|---|---|---|
| OSR vs OOD | 都处理训练假设外样本 | OSR 更关心语义新类；OOD 还包括噪声、域偏移、损坏图 | 把低层偏移当成新类识别 |
| OSR vs OWR | 都允许 unknown | OWR 还要求标注和增量学习闭环 | 把拒识器误称为开放世界系统 |
| OWR vs 增量学习 | 都会学新类 | 增量学习常默认新类标签已给出；OWR 要先发现未知 | 忽略 unknown discovery 成本 |
| unknown vs anomaly | 都偏离训练经验 | unknown 是类别集合外；anomaly 可能只是异常状态 | 把异常检测结果解释成新类能力 |
| unknown foreground vs background | 都可能没有当前类标签 | 前者是物体，后者是非目标或忽略区域 | 检测器把未知物体训练成背景 |
| open-vocabulary vs open-set | 都突破固定类别表 | open-vocabulary 依赖候选文本；open-set 要能拒绝候选外样本 | 误以为 VLM 天然会拒识 |
| novel class vs unknown class | 都可能训练时未见 | novel 往往在评测词表中已命名；unknown 可能没有候选名 | 把 AP_novel 当 unknown rejection |
| AUROC/FPR95 vs OSCR | 都评估拒识 | AUROC 看二分类分离；OSCR 同时看已知类分类正确性 | 用牺牲已知准确率换拒识指标 |

## 3. 读摘要前的最小判断句

读到 “open-set”，先问它是否真的有 unknown 输出，以及 unknown 是否是语义新类。

读到 “open-world”，先问它是否包含未知发现、标注来源和增量更新。

读到 “open-vocabulary”，先问它只是文本候选类别扩展，还是能处理候选外未知。

读到 “incremental”，先问新类标签从哪里来，旧类是否遗忘，未知是否需要先被发现。

读到 “unknown object”，先问它在训练中被当作背景、忽略区域，还是显式未知前景。

## 4. 互动练习

1. 从核心词表中挑 5 个术语，各写一句“它不能等同于什么”。
2. 摘要说 “we improve novel AP with text prompts”，判断它更像 open-vocabulary 还是 OWR。
3. 摘要只报 CIFAR known/unknown AUROC，说明它缺少哪些开放世界条件。
4. 为自动驾驶场景各举一个 unknown foreground 和 background 的例子。
5. 读任意摘要时标出它解决的是：拒识、发现、标注、增量学习、开放词表中的哪一环。

## 5. 完成度测试

达到术语骨架层后，你应能：

1. 不查资料解释 OSR、OWR、OOD、open-vocabulary detection 的差异。
2. 看到 AUROC、OSCR、unknown recall、A-OSE、AP_novel 时知道它们服务哪类问题。
3. 读摘要时发现作者是否混用了 open-world、open-set、open-vocabulary。
4. 判断一篇“开放世界”论文是否缺少 unknown discovery、oracle labeling 或 incremental update。
5. 把新术语归入四组之一：拒识分数、未知发现、增量学习、开放词表/VLM。

## 6. 证据索引

开放集与开放空间风险：[T01]。开放世界闭环：[T02]。OpenMax/EVT：[T03]。OOD、MSP、Mahalanobis、energy：[T04]-[T08]。语义偏移和 OpenOOD：[T09][T10]。OWOD 术语：[T11]-[T13]。VLM 与开放词表边界：[T14]-[T16]。增量学习与遗忘：[T17][T18]。
