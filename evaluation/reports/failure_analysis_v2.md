# Failure Analysis v2

## Data Agent
- consumption_preference_accuracy: 76.44
- distribution_similarity: 76.58
## Insight Agent
- segment_recognition_rate: 54.44
- insight_grounding_rate: 100.0
## Knowledge Agent
- recall_at_3: 48.33
- mrr: 60.67
## Strategy Agent
- golden_rule_coverage: 67.56
- knowledge_adoption_rate: 62.78
- risk_violation_rate: 0.0

## Remaining Failure TOP10

1. D1 Consumption Preference Accuracy: 45 cases (100.00%)
2. D2 Distribution Similarity: 45 cases (100.00%)
3. S1 Golden Coverage: 36 cases (80.00%)
4. I1 Lifecycle Recognition: 33 cases (73.33%)
5. OverallScore: 33 cases (73.33%)
6. K1 Recall@3: 31 cases (68.89%)
7. S2 Knowledge Adoption: 27 cases (60.00%)
8. K2 MRR: 24 cases (53.33%)

## Bottleneck Judgment

## Data Agent Failure Reason

D1/D2 与 v1 持平，45题均未达到阈值，主要是类别别名覆盖和分布校准问题。

## Lifecycle Recognition Failure Reason

I1 有33题失败，主要缺少 `young_growth_user` 与 `scenario_enhanced_churn_user` 的用户级年龄、近期活跃下降证据。

## RAG Recall Failure Reason

全量 v2 的 K1 为48.33%，低于 v1 的57.78%。q01-q03 定向测试达到100%，但全量路由在复购、活动和产品问题上仍存在误路由。主要未命中来源包括 operation_rule、bi_bi_zan、brand_profile、case_005 和 xiao_zhu_zan_qian_guan。

## Strategy Failure Reason

S1 从46.67%提升到67.56%，S2 从38.33%提升到62.78%。剩余失败主要来自生命周期 target_segment 未覆盖 Golden 标签，以及知识源未进入Top3后无法形成字段级采用。

RAG Recall ??????????????? Data ?????Lifecycle Recognition ? Strategy ???????Strategy Knowledge Adoption ???????????
