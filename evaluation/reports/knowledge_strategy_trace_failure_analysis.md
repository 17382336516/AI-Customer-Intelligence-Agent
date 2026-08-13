# Knowledge-to-Strategy Traceability v1 Failure Analysis

分析范围：dataset_01 q01–q03。未修改 Benchmark、Golden Label、Evaluator 或评分阈值。

## 结果

| Question | KnowledgeScore | StrategyScore | OverallScore | Knowledge Grounding Score |
|---|---:|---:|---:|---:|
| q01 | 100.00 | 100.00 | 98.65 | 53.33% |
| q02 | 65.00 | 97.00 | 90.60 | 53.33% |
| q03 | 100.00 | 85.00 | 93.40 | 56.67% |

Knowledge Grounding Score 是新增诊断指标，不替代现有 S2，也没有参与原有总分计算。

## 诊断

- Knowledge Evidence 已生成，能够记录 source、type、business goal、target segment、concepts 和 evidence text。
- Knowledge Plan 已生成，并能映射 source 到 strategy field。
- Strategy Trace 已生成，但部分 trace 的 concept 文本没有在对应策略字段中被规则化识别，因此 grounding score 低于 80%。
- q02 的根因仍包含 operation_rule 未进入 Top3；这不是 trace 服务引入的问题。

结论：链路结构已经闭环，但当前 grounding 诊断暴露出“知识概念表达”和“策略字段文本”的别名覆盖不足。保持真实结果，不自动把 retrieval 或 plan 视为采用。
