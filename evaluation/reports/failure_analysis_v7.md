# Failure Analysis v7

## 总览

- 题目数：45
- E2E通过：7/45（15.56%）
- Grounding记录：135，平均 89.63%，最低 0%，最高 100%
- Grounding未完全通过记录：43

## Grounding失败模式

|模式|数量/判断|
|-|-|
|knowledge retrieved but not applied|57 条字段级概念未找到可验证的策略表达|
|concept matched but strategy field missing|属于字段约束不匹配，未计入 matched_concepts|
|strategy generated without knowledge support|仅当 source 不在真实 evidence/retrieval 时失败|
|alias missing|仍存在未覆盖表达，主要表现为字段内语义匹配失败|

本轮 grounding 匹配类型：business_concept_match 225 条，exact_or_alias 345 条。召回不等于采用，所有 matched 仍要求 source→concept→strategy_field→strategy_expression 闭环。

## Evaluator 失败计数

同一题可能有多个失败指标，原始 failed cases 统计为：

|指标|失败记录数|
|-|-:|
|S1 Strategy Golden Rule Coverage|35|
|K1 Recall@3|30|
|S2 Knowledge Adoption Rate|27|
|K2 MRR|21|
|OverallScore|19|

## Knowledge失败模式

完整评估平均 Recall@3 为 61.67%，MRR 为 73.33%。失败主要表现为正确 primary source 未稳定进入 Top3，属于 Knowledge Retrieval 覆盖与排序问题，不是 grounding verifier 造成。

## Strategy失败模式

S1 Golden Coverage 为 72.15%，S2 Knowledge Adoption 为 68.33%。剩余问题集中在业务关键词覆盖、策略字段完整性和部分知识概念未落入目标字段。本轮未修改 Strategy 生成逻辑。

## 新瓶颈判断

DataScore 93.43、InsightScore 100，Data 与 Insight 已稳定。当前主要瓶颈仍是 Knowledge Retrieval 与 Strategy Requirement Coverage。Grounding Alignment v2 在完整 45 题上保持 89.63% 平均值，但仍存在 43 条字段级边界case。
