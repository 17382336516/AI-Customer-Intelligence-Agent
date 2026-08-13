# Agent Design

## Data Agent

负责消费行为清洗、商品偏好识别和用户分群。通过 Canonical Category Mapping、Category Alias Normalization 和 Single Category Tie Fix 统一类别口径。D1 为 91.11%，D2 为 98.83%。

## Insight Agent

负责把统计结果转化为用户画像、生命周期标签和行为证据。核心升级是 User-level Lifecycle Classification。I1 和 I2 均为 100%。

## Knowledge Agent

负责企业知识检索和排序。采用 Business Intent Routing、Query Expansion、Metadata Rerank 和 Knowledge Type Routing。K1 Recall@3 为 61.67%，K2 MRR 为 73.33%。

## Strategy Agent

负责生成 Marketing Goal、Product Strategy、Content Strategy、Promotion Strategy、Channel 和 Metrics。通过 Strategy Requirement Planner、Knowledge Plan、Knowledge Trace 和 Field-level Attribution 提高可解释性。S1 为 72.15%，S2 为 68.33%，S3 风险违规率为 0%。
