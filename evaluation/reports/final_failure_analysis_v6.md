# Final Failure Analysis v6

- 总问题数：45
- E2E 通过：7
- E2E 失败：38
- 平均 OverallScore：83.10
- 失败指标记录：132 条

| 失败指标 | 数量 |
|---|---:|
| S1 Golden Coverage | 35 |
| K1 Recall@3 | 30 |
| S2 Knowledge Adoption | 27 |
| K2 MRR | 21 |
| OverallScore | 19 |

Data 和 Insight 没有形成主要失败来源。RAG v3 使 K1 从 48.33% 提升到 61.67%，K2 从 60.67% 提升到 73.33%，但具体 product/brand/marketing_case 文档仍存在 Top3 边界失败。

Strategy 的 S2 从 62.78% 提升到 68.33%，说明知识规划和字段归因有改善；S1 仍为 72.15%，剩余失败主要是业务关键词和问题级策略约束覆盖不足。

当前主要瓶颈是 RAG 与 Business Requirement Coverage 的组合，而不是 Data/Insight 核心能力。未修改阈值、Golden Label 或失败案例。
