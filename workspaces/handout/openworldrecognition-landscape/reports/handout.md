# open world recognition computer vision 讲义：第 2 层：地貌图（Landscape Map）

生成时间：2026-04-25T15:51:10.779412+00:00

## 层级目标

- 认知层级：地貌深度
- 产物目标：3-5 个方法家族、评价环境、非线性时间线，以及代表人物/实验室。
- 长度边界：建议 5000-10000 字；参考文献精选 30-50 篇。

## 不要做

- 不要罗列所有论文。
- 不要追求 comprehensive。
- 不要把时间线写成单线因果链。

## 检索策略

本文件由 `autoscholar handout init` 生成。检索使用 AutoScholar 的 checkpointed Semantic Scholar crawl：成功结果写入 `handouts/openworldrecognition-landscape/artifacts/semantic_results.jsonl`，失败项写入 `handouts/openworldrecognition-landscape/artifacts/semantic_failures.jsonl`。再次运行同一命令会跳过同一检索签名下已成功的 query，并重试失败或未完成 query。

- `landscape_01_survey-map`: open world recognition computer vision survey methods taxonomy benchmark  
  目的：寻找能搭建方法家族的综述入口。
- `landscape_02_state-of-the-art`: open world recognition computer vision state of the art benchmark metrics  
  目的：寻找评价环境与 SOTA 设定。
- `landscape_03_recent-advances`: open world recognition computer vision recent advances 2020 2021 2022 2023 2024  
  目的：捕捉近 5-8 年的变化节点。
- `landscape_04_representative-work`: open world recognition computer vision representative methods comparison  
  目的：寻找代表工作和方法比较。
- `landscape_05_labs-authors`: open world recognition computer vision leading researchers labs  
  目的：寻找代表人物、实验室和研究谱系线索。

检索摘要：

```json
{
  "total": 5,
  "processed": 5,
  "skipped": 0,
  "success": 0,
  "failure": 5,
  "completed": 0,
  "remaining": 5,
  "complete": false,
  "rounds": 1,
  "until_complete": false,
  "max_rounds_reached": false,
  "stored_success": 0,
  "stored_failure": 5
}
```

## 证据池

- 暂无成功检索结果；重新运行同一命令会跳过已成功项并重试失败项。

## 失败或待重试检索

- `landscape_01_survey-map`: HTTPStatusError - Client error '429 ' for url 'https://api.semanticscholar.org/graph/v1/paper/search?query=open+world+recognition+computer+vision+survey+methods+taxonomy+benchmark&limit=10&fields=paperId%2Ctitle%2Cyear%2Cauthors%2Curl%2Cabstract%2CcitationCount%2CinfluentialCitationCount%2Cvenue%2CpublicationTypes%2CexternalIds'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `landscape_02_state-of-the-art`: HTTPStatusError - Client error '429 ' for url 'https://api.semanticscholar.org/graph/v1/paper/search?query=open+world+recognition+computer+vision+state+of+the+art+benchmark+metrics&limit=10&fields=paperId%2Ctitle%2Cyear%2Cauthors%2Curl%2Cabstract%2CcitationCount%2CinfluentialCitationCount%2Cvenue%2CpublicationTypes%2CexternalIds'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `landscape_03_recent-advances`: HTTPStatusError - Client error '429 ' for url 'https://api.semanticscholar.org/graph/v1/paper/search?query=open+world+recognition+computer+vision+recent+advances+2020+2021+2022+2023+2024&limit=10&fields=paperId%2Ctitle%2Cyear%2Cauthors%2Curl%2Cabstract%2CcitationCount%2CinfluentialCitationCount%2Cvenue%2CpublicationTypes%2CexternalIds'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `landscape_04_representative-work`: HTTPStatusError - Client error '429 ' for url 'https://api.semanticscholar.org/graph/v1/paper/search?query=open+world+recognition+computer+vision+representative+methods+comparison&limit=10&fields=paperId%2Ctitle%2Cyear%2Cauthors%2Curl%2Cabstract%2CcitationCount%2CinfluentialCitationCount%2Cvenue%2CpublicationTypes%2CexternalIds'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- `landscape_05_labs-authors`: HTTPStatusError - Client error '429 ' for url 'https://api.semanticscholar.org/graph/v1/paper/search?query=open+world+recognition+computer+vision+leading+researchers+labs&limit=10&fields=paperId%2Ctitle%2Cyear%2Cauthors%2Curl%2Cabstract%2CcitationCount%2CinfluentialCitationCount%2Cvenue%2CpublicationTypes%2CexternalIds'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429

## 讲义正文骨架

### 1. 方法家族

从证据池中归纳 3-5 个 `open world recognition computer vision` 主流方法家族。每个家族保留：核心假设、代表工作、近年演进、它解决和回避的问题。

### 2. 评价环境

列出主要 benchmark、metric、默认实验设定。写清楚每个评价设置偏向哪类方法，以及哪些能力没有被测到。

### 3. 非线性时间线

按 5-8 年窗口写“焦点迁移”：哪些年份大家集中做什么，哪篇或哪类论文改变了问题表述，基础模型或数据集变化如何让旧问题重新变热。

### 4. 代表人物和实验室

每个方法家族列 2-3 个代表人物/实验室。重点不是名录，而是解释他们的工作为什么定义了该家族的走向。


## 互动问题

- 从 3-5 个方法家族中选一个，写下它最核心的假设。
- 指出一个 benchmark 或 metric 可能偏向哪一类方法。
- 在时间线里标出一个焦点迁移节点，并解释它为什么发生。

## 完成度测试

- 能在该领域的学术 talk 里跟上约 70%。
- 读到一篇新论文时，能定位它属于哪个方法家族。
- 能判断新论文是在延续、修补还是反叛某条谱系。

## 写作要求

- 最终讲义必须显式写明这是第几层，不要把三层混成一份泛综述。
- 每个关键判断都要能回到证据池中的论文或检索 query。
- 保留互动问题和完成度测试，让读者能判断自己是否真正抵达本层。
- 如果证据池不足，先扩展 query 或重跑 crawl，不要用泛泛常识补齐关键结论。
