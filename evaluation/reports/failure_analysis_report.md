# Overall Summary

- ?????45
- E2E???0/45
- E2E Pass Rate?0.0%
- ??OverallScore?65.53
- ?????????14
- ?????full_benchmark_agent_execution_deterministic_fallback

# Agent Score

## Data Agent
- consumption_preference_accuracy: 76.44
- distribution_similarity: 76.58
- data_score: 76.49

## Insight Agent
- segment_recognition_rate: 54.44
- insight_grounding_rate: 100.0
- insight_score: 81.78

## Knowledge Agent
- recall_at_3: 57.78
- mrr: 54.96
- knowledge_score: 56.93

## Strategy Agent
- golden_rule_coverage: 46.67
- knowledge_adoption_rate: 38.33
- risk_violation_rate: 0.0
- strategy_score: 52.58

# Failure Pattern Analysis

???????????????????????

1. D1 Consumption Preference Accuracy
   count: 45
   percentage: 100.0%

2. D2 Distribution Similarity
   count: 45
   percentage: 100.0%

3. S1 Strategy Golden Coverage
   count: 45
   percentage: 100.0%

4. OverallScore
   count: 42
   percentage: 93.33%

5. S2 Knowledge Adoption
   count: 36
   percentage: 80.0%

6. I1 Lifecycle Segment Recognition
   count: 33
   percentage: 73.33%

7. K2 MRR
   count: 33
   percentage: 73.33%

8. K1 Recall@3
   count: 30
   percentage: 66.67%

# Representative Failed Cases

| question_id | business_question | failed_metric | reason | suggested_improvement |
|---|---|---|---|---|
| dataset_01_general_q03 | 如何在综合消费基准中识别并运营年轻、非一线城市的潜力用户？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_03_retention_interest_q03 | 如何在留存与品类兴趣基准中识别并运营年轻、非一线城市的潜力用户？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_02_growth_campaign_q03 | 如何在年轻增长与促销基准中识别并运营年轻、非一线城市的潜力用户？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_01_general_q11 | 如何为综合消费基准设计兼顾年轻用户与家庭用户的春节活动？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_02_growth_campaign_q11 | 如何为年轻增长与促销基准设计兼顾年轻用户与家庭用户的春节活动？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_03_retention_interest_q11 | 如何为留存与品类兴趣基准设计兼顾年轻用户与家庭用户的春节活动？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_03_retention_interest_q12 | 留存与品类兴趣基准适合怎样的年轻化周年节点活动？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_01_general_q12 | 综合消费基准适合怎样的年轻化周年节点活动？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_02_growth_campaign_q12 | 年轻增长与促销基准适合怎样的年轻化周年节点活动？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
| dataset_03_retention_interest_q13 | 留存与品类兴趣基准中哪些用户适合电子产品新品推荐？ | D1 Consumption Preference Accuracy | Data Agent category prediction mismatch | Inspect the corresponding persisted artifact; do not relax the evaluator threshold. |
