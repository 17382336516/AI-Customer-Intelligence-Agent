# Final Failure Analysis v5

## Summary

- 总问题数：45
- E2E 通过：8
- E2E 失败：37
- 平均 OverallScore：79.99
- 失败指标记录：145 条

## 剩余失败分布

| 指标 | 失败记录 |
|---|---:|
| S1 Golden Coverage | 35 |
| K1 Recall@3 | 31 |
| S2 Knowledge Adoption | 27 |
| K2 MRR | 24 |
| OverallScore | 28 |

## 判断

- Data：不是剩余主要问题；DataScore 93.43。
- Insight：不是剩余问题；InsightScore 100。
- RAG：仍是重要瓶颈，K1 48.33%、K2 60.67%，失败集中在特定 product/brand/marketing_case 文档。
- Strategy：S1 从 v4 的 67.33% 提升至 72.15%，但业务关键词和具体目标约束仍有边界失败；S2 未明显变化，说明知识采用受召回和字段匹配共同限制。

V5 的改进是真实但有限：策略规划层改善了要求显式化和部分 Golden Coverage，没有解决企业知识召回本身。失败案例已保留，未修改阈值或评分规则。
