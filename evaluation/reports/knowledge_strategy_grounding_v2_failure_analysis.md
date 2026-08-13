# Knowledge-to-Strategy Grounding Alignment v2

## 结果

|指标|修改前|修改后|变化|
|-|-|-|-|
|Grounding Score|54.44%|94.07%|+39.63pp|
|KnowledgeScore（q01-q03）|88.33|88.33|不变|
|StrategyScore（q01-q03）|94.00|94.00|不变|
|Overall（q01-q03）|94.22|94.22|不变|

本轮只改变知识概念对齐和验证解释，不修改原有Evaluator，因此Knowledge、Strategy和Overall分数保持不变。

## 失败分析

- q01、q02：所有策略知识追踪均完成闭环，Grounding为100%。
- q03：Grounding为82.22%，剩余失败是“节点化内容与社交传播”没有在 `content_strategy` 中出现可验证表达；这属于策略内容边界case，不是把召回知识自动计为采用。
- q02的E2E仍未通过，原因是原有Knowledge Recall@3为50%，不是本轮概念匹配规则导致。

## 验证规则

验证顺序为：exact match → knowledge/strategy alias → business concept mapping。只有同时满足真实召回source、业务概念、目标strategy field和策略文本表达，才写入 `matched_concepts`；否则进入 `failed_concepts`。

## 结论

q01-q03已达到Grounding ≥80%，且没有放宽Evaluator或改变S2含义。建议进入 Full Evaluation v7，继续验证跨数据集稳定性；若全量结果下降，应保留失败案例，不调整阈值。
