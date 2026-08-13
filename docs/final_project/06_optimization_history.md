# Optimization History

## Baseline

问题包括类别映射错误、生命周期识别缺失、RAG 召回不稳定、策略缺少知识约束。OverallScore：65.53。

## Data Optimization

引入 Canonical Category Mapping 和 Single Category Tie Fix，修复单品类 score tie。DataScore：76.49 → 93.43。

## Lifecycle Optimization

从 segment-level inference 升级为 user-level lifecycle classification，增加 lifecycle tags 和 evidence。InsightScore：81.78 → 100。

## RAG Optimization

引入 Business Intent Routing、Query Expansion、Metadata Rerank 和 Knowledge Type Routing。KnowledgeScore：56.93 → 65.17，Recall@3 达到 61.67%。

## Strategy Optimization

引入 Strategy Requirement Planner、Knowledge Plan、Knowledge Trace 和 Field Attribution。StrategyScore：52.58 → 75.37，Knowledge Adoption 达到 68.33%。

## Final v6

OverallScore：83.10，E2E Pass Rate：15.56%。失败案例保留为后续迭代依据。
