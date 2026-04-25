# 开放世界识别讲义：第 2 层 Landscape Map

生成日期：2026-04-25  
领域范围：计算机视觉中的开放世界识别，重点是图像分类、开放集识别、开放世界目标检测、开放词表检测及其评测环境。  
证据状态：已按 `handout` skill 执行 `autoscholar handout init "open world recognition computer vision" --level landscape --output-dir handouts\openworldrecognition-landscape`。Semantic Scholar Graph API 在本轮返回 429，失败记录见 `artifacts/semantic_failures.jsonl`。正式讲义基于 `queries.jsonl` 的检索意图，补充使用论文页面、CVF/OpenReview/arXiv/NeurIPS 等主来源，来源清单见 `artifacts/web_evidence.jsonl`。

## 0. 这一层要解决什么

这一层不是术语表，也不是争议判断，而是地貌图。读完后你应该能听懂一个开放世界识别方向的报告约 70%，并能把一篇新论文放进大致谱系：它是在做未知拒识、未知发现、增量学习、开放世界检测，还是把开放词表能力当作开放世界能力来用。

这里的“开放世界”比“开放集”更宽。开放集识别只要求模型在测试时把不属于训练类别的样本拒掉或标成 unknown。开放世界识别还要求系统在运行过程中发现未知类别，等待人工或其他 oracle 给出标签，并把这些新类别并入模型，同时尽量不忘掉旧类 [R02]。开放词表检测又是另一条线：它让模型用文本提示识别训练检测集之外的类别，但如果候选词表里没有目标，模型仍可能被迫在词表内选择，因此它不是天然的 open-set 模型 [R28]。

## 1. 方法家族地图

### 家族 A：开放集边界与风险控制

核心问题：已知类的分类器怎样避免把未知样本硬塞进已知类？

这一族从形式化问题开始。Scheirer 等把 open set recognition 写成要同时控制 empirical risk 和 open space risk 的问题，强调在远离训练样本的空间里给出高置信已知类预测是风险 [R01]。Bendale 和 Boult 的 OpenMax 把这种思想带到深度网络里，用倒数第二层激活向量和 EVT 建模类别尾部分布，再把 SoftMax 改成带 unknown 概率的 OpenMax [R03]。它的贡献不只是一个模块，而是让深度网络的 unknown rejection 有了可讨论的风险边界。

这个家族后来分成两类：一类继续设计已知类边界，如 EVT、距离阈值、最大 logit、能量分数；另一类质疑“复杂 OSR 模块是否真的必要”。Hendrycks 与 Gimpel 的 MSP baseline、ODIN、Mahalanobis detector、energy-based OOD detector 都说明，普通分类器的输出和特征空间本身已经包含大量异常检测信号 [R04][R05][R06][R11]。Vaze 等进一步提出强闭集分类器加简单分数就能在多个 OSR benchmark 上逼近甚至超过复杂方法，并提出 Semantic Shift Benchmark，提醒领域别把低层分布偏移误当作语义未知 [R13]。

这一族的强项是简单、可插拔、适合分类模型；弱项是通常只解决“拒掉未知”，不解决“未知是什么、怎样纳入模型”。如果论文只在 CIFAR/SVHN/TinyImageNet split 上报 AUROC，而没有新类学习或真实开放场景，它多半属于这一族，而不是完整开放世界系统。

### 家族 B：重构、生成与原型空间

核心问题：只看已知类时，怎样学出“已知类流形之外”的可判别空间？

CROSR 和 C2AE 代表了重构路线：模型既要分类，也要重构输入或按类别条件重构输入。未知样本在错误类别条件下往往重构异常，由此形成拒识信号 [R08][R09]。Reciprocal Point Learning 则显式学习每个已知类对应的“类外空间”表示，让样本离已知原型近、离 reciprocal point 的关系可判别，从而压缩已知类并为未知留出空间 [R10]。OpenGAN 把问题进一步改成用生成或开放数据来训练 open-vs-closed 判别器 [R12]。

这类方法的共同假设是：未知不是完全无结构的，它至少会在重构误差、原型距离、生成判别器或类外代理空间中露出痕迹。它们比单纯阈值更有建模意图，但也更容易被 benchmark 设置牵着走。如果未知类和已知类语义很近，重构误差未必大；如果用外部 open data，评测必须说明这些 open data 是否泄露了测试未知类的语义。

在读这类论文时，重点看三件事：它的 unknown signal 来自哪里；该 signal 是否依赖外部负样本；它是否牺牲了已知类分类精度。OSR 领域的大量方法差别不在“有没有 unknown 分数”，而在 unknown 分数是否比强闭集 baseline 更稳。

### 家族 C：从拒识到增量学习的开放世界识别

核心问题：模型发现未知后，怎样把它变成新的已知类？

Bendale 和 Boult 的 open world recognition 定义里有一个闭环：先识别已知类，遇到未知时标为 unknown，再由 oracle 标注部分新类，然后增量更新分类器 [R02]。Nearest Non-Outlier 是早期代表，它把开放集最近类均值分类与增量加类结合起来。这个方向与 continual learning/class-incremental learning 强相关，LwF、iCaRL、DER 等方法解决的是“学新类不忘旧类”的稳定性-可塑性问题 [R31][R32][R33]。

但要注意，class-incremental learning 不等于开放世界识别。很多增量学习论文默认每一阶段的新类标签已经干净给出，测试时也不要求检测未知；开放世界识别多了一个前置难题：哪些样本值得送去标注，哪些 unknown 应聚成同一新类，哪些只是噪声或背景。也就是说，开放世界系统至少有四个模块：unknown detection、unknown clustering 或 discovery、oracle/active labeling、incremental update。

这一族在应用上最接近真实系统，但论文数量反而不如 OSR/OOD 多。原因是评测难：闭集准确率、unknown recall、标注成本、忘记率、更新时间都要同时看。一个论文如果只报 final accuracy，不报告拒识质量和新增类成本，就很难证明它真的处理了开放世界。

### 家族 D：开放世界目标检测

核心问题：检测器怎样把“未知物体”从背景里捞出来？

目标检测比分类难，因为标准检测训练会把所有未标注区域当背景。开放世界目标检测 (OWOD) 要求模型检测已知类别，同时发现未知物体，之后在新任务阶段逐步学习这些类别 [R15]。ORE 首先把这个设置系统化，使用 contrastive clustering 和 energy-based unknown identification，并提出一套包含未知召回与增量任务的评测协议 [R15]。

OW-DETR 把 DETR/Transformer 的 object query 用起来，通过 attention-driven pseudo-labeling、novelty classification 和 objectness scoring 来识别未知前景 [R16]。PROB 则把关键矛盾说得更直接：未知物体缺少标注，不能简单用背景负样本训练，因此需要估计“objectness”而不是只训练一个 closed-set 分类头 [R17]。这条线的中心不再是“未知类的分类概率低不低”，而是“未知物体是否被当成前景 proposal 生成出来”。

OWOD 的典型指标包括 known-class mAP、unknown recall、Wilderness Impact、Absolute Open-Set Error，以及后续任务中的增量 mAP。它比图像级 OSR 更接近自动驾驶、机器人、监控等场景，但也更依赖数据集标注规则。一个未标注对象究竟是 unknown，还是数据集本来不关心的背景，这是 OWOD 评测最容易产生噪声的地方。

### 家族 E：开放词表与视觉语言模型

核心问题：能否用语言把类别空间打开？

CLIP 让自然语言成为引用视觉概念的接口，open-vocabulary detection 随后快速发展 [R20]。OVR-CNN 用 caption 构造视觉语义空间 [R19]；ViLD 把视觉语言模型知识蒸馏到检测器里 [R21]；RegionCLIP 把图像级 CLIP 推到 region-text matching [R22]；GLIP 统一 detection 和 phrase grounding [R23]；OWL-ViT 用 ViT 和图文预训练做文本条件检测 [R24]；Detic 用 image-level labels 把检测器词表扩到大规模类别 [R25]；Grounding DINO 和 YOLO-World 分别代表更强的开放词表定位和实时开放词表检测路线 [R26][R27]。

这条线改变了开放世界识别的生态。以前 unknown 类需要被拒掉；现在很多系统可以直接问“图里有没有 traffic cone / forklift / fire extinguisher”。但开放词表不是开放世界的终点。VLM 仍有有限 query set、prompt 敏感性、开放词表外未知、相似文本标签混淆、低 precision/recall tradeoff 等问题 [R28]。所以更准确的说法是：VLM 让“可命名未知”变容易了，但“不可预期未知”和“新类闭环学习”仍未解决。

判断一篇开放词表论文是否属于开放世界，要看它是否允许 unknown 作为合法输出，是否评估未列入词表的对象，是否有增量学习或 human-in-the-loop 机制。如果只是 base/novel split 上的 AP_novel，它主要是 open-vocabulary 或 zero-shot detection，不是完整 open-world recognition。

## 2. 评测环境与指标

开放世界识别的评测不是一个统一 benchmark，而是几套相互重叠的协议。

图像级 OSR 常用 MNIST、SVHN、CIFAR-10/100、TinyImageNet、ImageNet 子集等，把一部分类作为 known，另一部分作为 unknown。早期论文常报已知类 accuracy、unknown AUROC、AUPR、F1、open set classification rate，或用 openness 表示未知空间大小。OSCR 类曲线试图同时看 known classification 和 unknown rejection，避免模型通过牺牲已知类准确率换取高拒识率 [R07]。

OOD detection 更关注 ID/OOD 区分，常用 AUROC、AUPR、FPR95。OpenOOD 把 OOD、anomaly detection、OSR、uncertainty 相关方法放进统一代码和 benchmark，反映了社区正在从单个数据集比较转向更标准化的评测 [R14]。但 OOD 和 OSR 的目标不完全一样：OOD 可以是风格、传感器、背景、噪声变化；OSR 更关心语义类别未知。Vaze 等提出 SSB，正是为了把语义未知从一般分布偏移中分出来 [R13]。

OWOD 评测以 VOC/COCO 的任务序列为主。第一阶段只给部分类别标注，模型要检测 known 和 unknown；后续阶段把部分 unknown 变成 newly known，测试是否能继续检测旧类、新类和剩余未知。关键指标包括已知类 mAP、unknown recall、A-OSE、WI，以及每一阶段的 incremental mAP [R15][R16][R17]。其中 unknown recall 很重要，因为把未知都当背景的检测器也可能保持不错的 known mAP。

开放词表检测常用 COCO、LVIS、Objects365、ODinW、RefCOCO 等，指标是 AP_base、AP_novel、AP_all，或 zero-shot transfer AP。这个评测偏向“已知名字但无框标注”的泛化能力。它适合衡量语言监督带来的类别扩展，不足以衡量 unknown rejection。Grounding DINO 这类模型会在“open-set object detection”语境下使用 open-set 一词，但在开放世界识别讲义里要把它放在 VLM/open-vocabulary 家族，不要和 OWOD 的 unknown discovery 混为一谈 [R26][R28]。

## 3. 非线性时间线：焦点怎样移动

2013 到 2016 是概念奠基期。Open set recognition 形式化了 open space risk [R01]，open world recognition 把拒识和增量加类连成闭环 [R02]，OpenMax 把深度网络拉进这套问题 [R03]。这些工作奠定了领域语言，但当时的深度视觉生态还没有今天的大规模预训练和检测 transformer。

2017 到 2020 的焦点转向“未知分数是否可靠”。MSP、ODIN、Mahalanobis、energy score 等 OOD 方法显示，闭集分类器本身就是强 baseline [R04][R05][R06][R11]。同时 CROSR、C2AE、RPL 等 OSR 方法尝试从重构、类条件、原型空间建模未知 [R08][R09][R10]。这几年形成了一个重要张力：专门的 OSR 模块是否真的超过强分类器加合理分数？

2021 到 2022 是评测反思和检测扩展期。ORE 把开放世界问题推向 object detection，要求模型处理 unknown foreground 和 incremental learning [R15]。Vaze 等提出 SSB，OpenOOD 提供统一 OOD benchmark，说明社区开始重视评测定义本身 [R13][R14]。同一时期，ViLD、RegionCLIP、GLIP、OWL-ViT、Detic 让语言监督进入检测，开放词表能力快速成为另一条主干 [R21][R22][R23][R24][R25]。

2023 到 2024 的焦点进一步分叉。OWOD 里，PROB 强调 objectness 概率，说明未知物体检测的难点不只是分类头阈值，而是前景建模 [R17]。开放词表里，Grounding DINO 和 YOLO-World 把文本条件检测推进到更强性能和更实时的系统 [R26][R27]。与此同时，VLM OSR 研究明确指出：能识别大量文本类别不等于能处理 open-set 条件 [R28]。

2025 到 2026 的合理读法是汇合期。开放世界识别不会只是一种算法，而会变成一套系统问题：基础模型提供可命名类别的迁移能力，OSR/OOD 提供拒识和不确定性机制，OWOD 提供未知前景发现，continual learning 提供新增类更新。未来论文的价值很可能不在单个 AUROC，而在是否能把这些模块放进稳定、可评测、低标注成本的闭环。

## 4. 代表人物与实验室

UCCS/VAST Lab 的 Terrance Boult、Walter Scheirer、Abhijit Bendale 是开放集和开放世界识别的概念源头之一，贡献包括 open space risk、open world recognition 和 OpenMax [R01][R02][R03]。

Johns Hopkins 的 Vishal Patel 相关工作代表了深度 OSR 的重构和类条件方向，如 C2AE [R09]。Peking University、Peng Cheng Laboratory、Hikvision 等团队在 reciprocal point、ARPL 类方法上推动了原型和类外空间建模 [R10]。

Oxford VGG 的 Zisserman/Vedaldi/Vaze 线条代表了评测反思：强闭集分类器和 Semantic Shift Benchmark 迫使 OSR 论文重新证明自己超过简单强 baseline [R13]。

Yixuan Li、Ziwei Liu、Jingkang Yang 等团队把 OOD detection、OpenOOD benchmark 和广义 OOD survey 推成更标准化的评测生态 [R14][R30]。这条线虽然不完全等同于 OSR，但对开放世界系统的安全部署很关键。

IIT Hyderabad、MBZUAI、ANU、Linkoping、UCF 等团队围绕 ORE/OW-DETR 推动了 OWOD 设置 [R15][R16]。Stanford 的 Serena Yeung 团队通过 PROB 强调 probabilistic objectness，代表了 OWOD 中“未知前景建模”的方向 [R17]。

Microsoft、Google、Meta、OpenAI 及相关高校团队构成开放词表/VLM 检测主线：CLIP、ViLD、RegionCLIP、GLIP、OWL-ViT、Detic、Grounding DINO、YOLO-World 都在改变“类别空间如何打开”的技术路线 [R20]-[R27]。

## 5. 读新论文时的定位表

如果论文的核心是 AUROC、FPR95、energy/logit/distance score，它多半属于 OSR/OOD 打分族。问它是否在语义未知上评估，是否超过强闭集 baseline。

如果论文有 autoencoder、GAN、prototype、reciprocal point、negative/open data，它属于重构/生成/原型族。问它的 unknown signal 是否依赖外部未知样本，是否在近语义 unknown 上仍有效。

如果论文有 unknown discovery、oracle、incremental update、catastrophic forgetting，它属于开放世界闭环族。问它是否同时报告拒识、聚类、标注成本和遗忘。

如果论文在 COCO/VOC 上报告 unknown recall、A-OSE、WI、incremental mAP，它属于 OWOD。问它如何区分未知物体和背景，是否真的生成高质量 unknown proposals。

如果论文使用 CLIP、text prompt、caption、phrase grounding、LVIS novel AP，它属于开放词表/VLM 族。问它是否允许 unknown 输出，是否评估不在 query set 中的对象。

## 6. 互动练习

1. 选一篇论文，先不要看方法名，只看评测表。它报的是 AUROC/FPR95、OSCR、unknown recall/WI，还是 AP_novel？据此判断它属于哪个家族。
2. 把“开放集识别”“OOD detection”“开放词表检测”“开放世界识别”四个词各写一句边界定义。要求每句包含它的输入假设和输出要求。
3. 给一个自动驾驶场景：训练集中有 car、truck、person，测试时出现 scooter、traffic cone、fallen tree。分别说明 OSR、OWOD、open-vocabulary detector 会如何处理。
4. 读 Grounding DINO 或 YOLO-World 的摘要，指出它为什么增强了开放世界能力，又为什么不自动解决 unknown rejection。
5. 设计一个更严格的评测：要求模型发现 unknown、请求标注、增量学习。列出至少四个指标，并说明每个指标防止哪种投机行为。

## 7. 完成度测试

读者达到 landscape 层时，应能做到：

1. 听到 open set recognition 时，能马上想到 open space risk、unknown rejection、AUROC/OSCR、强闭集 baseline。
2. 听到 open world recognition 时，能补上 discovery、oracle labeling、incremental learning、forgetting，而不只停在“拒掉 unknown”。
3. 听到 open world object detection 时，能说出未知前景和背景混淆是核心难点，并知道 unknown recall、A-OSE、WI 的角色。
4. 听到 open-vocabulary detection 时，能区分 AP_novel 和 unknown detection，不把 VLM 的大词表误认为完整开放世界。
5. 看到一篇新论文的实验表，能在 3 分钟内判断它延续、修补还是反驳哪条谱系。

## 8. 精选参考文献

完整来源见 `artifacts/web_evidence.jsonl`。建议优先读：

[R01] Scheirer et al., Toward Open Set Recognition, TPAMI 2013.  
[R02] Bendale and Boult, Towards Open World Recognition, CVPR 2015.  
[R03] Bendale and Boult, Towards Open Set Deep Networks, CVPR 2016.  
[R13] Vaze et al., Open-Set Recognition: a Good Closed-Set Classifier is All You Need?, ICLR 2022.  
[R14] Yang et al., OpenOOD, NeurIPS Datasets and Benchmarks 2022.  
[R15] Joseph et al., Towards Open World Object Detection, CVPR 2021.  
[R16] Gupta et al., OW-DETR, CVPR 2022.  
[R17] Zohar et al., PROB, CVPR 2023.  
[R20] Radford et al., CLIP, ICML 2021.  
[R23] Li et al., GLIP, CVPR 2022.  
[R24] Minderer et al., OWL-ViT, ECCV 2022.  
[R26] Liu et al., Grounding DINO, ECCV 2024.  
[R28] Miller et al., Open-Set Recognition in the Age of Vision-Language Models, ECCV 2024.
