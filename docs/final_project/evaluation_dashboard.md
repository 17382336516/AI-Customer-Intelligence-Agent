# Evaluation Dashboard 展示说明

## 页面一：Overall Score

展示 OverallScore 83.10、E2E Pass Rate 15.56%，并标注实验模式为 deterministic_fallback、45 个问题和 3 套数据集。

## 页面二：Agent Scorecard

|Agent|核心指标|结果|
|-|-:|-:|
|Data|DataScore|93.43|
|Insight|InsightScore|100.00|
|Knowledge|KnowledgeScore|65.17|
|Strategy|StrategyScore|75.37|

补充展示 D1 91.11%、D2 98.83%、K1 61.67%、K2 73.33%、S1 72.15%、S2 68.33%、S3 Risk Violation 0%。

## 页面三：Optimization Timeline

Baseline Overall 65.53 → Data Mapping → Lifecycle v2 → RAG v3 → Strategy Planning v4 → Grounding Alignment v2。每个节点展示问题、修改边界和指标变化。

## 页面四：Failure Analysis

展示 S1、K1、S2、K2 的失败数量，并支持按 dataset、question、agent、metric 筛选。失败案例必须保留原始原因和 artifact 路径。

## 页面五：Knowledge→Strategy Traceability

展示：

`document_source → business_concept → strategy_field → strategy_expression → verification_result`

Grounding 平均值为 89.63%，同时展示最低值、失败概念和匹配类型，避免只展示单一总分。
