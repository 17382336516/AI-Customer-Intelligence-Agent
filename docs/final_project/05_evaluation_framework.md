# Evaluation Framework v1

LLM Agent 不能只评价最终文本，因此系统保存每个 Agent 的 evaluation artifact，并分别评价数据、洞察、知识和策略层。

| 层级 | 指标 | 说明 |
|---|---|---|
| Data | D1 Preference Accuracy | 预测商品偏好与 category ground truth 的一致性 |
| Data | D2 Distribution Similarity | 预测分布与真实分布的相似度 |
| Insight | I1 Lifecycle Recognition | 生命周期标签识别率 |
| Insight | I2 Insight Grounding | 洞察证据与真实统计的一致性 |
| Knowledge | K1 Recall@3 | Golden knowledge source 的 Top3 命中 |
| Knowledge | K2 MRR | 第一个相关知识源的倒数排名 |
| Strategy | S1 Golden Coverage | 目标、字段和业务关键词覆盖 |
| Strategy | S2 Knowledge Adoption | 企业知识进入策略字段的比例 |
| Strategy | S3 Risk Violation | 风险约束违规率 |

采用规则化 Evaluation 的原因是可复现、可解释、便于模块化诊断。通过失败案例可以区分数据映射、生命周期识别、知识召回和策略生成问题。
