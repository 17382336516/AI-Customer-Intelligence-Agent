# Final Failure Analysis v4

## Summary

- 总问题数：45
- E2E 通过：6
- E2E 失败：39
- 平均 OverallScore：78.98
- 失败指标记录：149 条（同一问题可能有多个失败指标）

## 失败集中位置

| Agent/指标 | 失败记录数 |
|---|---:|
| Strategy S1 Golden Coverage | 38 |
| Knowledge K1 Recall@3 | 31 |
| Strategy S2 Knowledge Adoption | 27 |
| Knowledge K2 MRR | 24 |
| OverallScore threshold | 29 |

Data 和 Insight 没有进入主要失败列表，说明两轮优化已解决类别 tie、生命周期识别和 grounding 问题。

## 判断

当前存在两类真实剩余问题：

1. Knowledge Retrieval 在部分业务意图下未稳定命中 Golden source，属于 RAG 能力边界。
2. Strategy 在知识未召回或业务问题要求较细时，Golden Coverage/Knowledge Adoption 不足，属于下游策略生成能力边界。

未发现需要修改 Evaluator 或阈值的证据。失败案例已保留在三个 dataset failed 文件中。

## 已通过的问题

- Data canonical mapping 和单品类 score tie：DataScore 提升至 93.43。
- User-level lifecycle classification：InsightScore 达到 100。
- Insight grounding：I2 达到 100。
- Strategy knowledge attribution：S2 相比 v1 明显提升。
- Risk violation：S3 为 0，未发现风险约束违规。

## 边界案例

剩余失败主要集中在知识源要求更具体、多个知识类型同时匹配、以及策略必须覆盖多个关键词的题目，不构成 Data/Insight 链路的系统性故障。当前不建议为单个 q03 类问题进行大规模优化。
