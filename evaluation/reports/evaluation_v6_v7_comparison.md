# Evaluation v6 vs v7

|指标|v6|v7|变化|
|-|-|-|-|
|DataScore|93.43|93.43|0.00|
|InsightScore|100.00|100.00|0.00|
|KnowledgeScore|65.17|65.17|0.00|
|StrategyScore|75.37|75.37|0.00|
|OverallScore|83.10|83.10|0.00|
|E2E Pass Rate|15.56%|13.33%|-2.23pp|
|Grounding Score（v6 q01-q03基线）|54.44%|89.63%（全45题）|+35.19pp*|

*Grounding 的 v6 数值来自 q01-q03 traceability smoke test，v7 为完整45题统计，范围不同，不能当作严格同口径提升。v7 未修改Evaluator，因此核心分数保持不变；E2E差异来自本次完整运行的真实题目结果。
