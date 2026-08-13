# RAG v2 vs RAG v3

| Metric | RAG v2 q01–q03 | RAG v3 q01–q03 | Improvement |
|---|---:|---:|---:|
| K1 Recall@3 | 100.00% | 83.33% | -16.67pp |
| K2 MRR | 100.00% | 100.00% | 0pp |
| KnowledgeScore | 100.00 | 88.33 | -11.67 |

说明：q01–q03 的旧结果正好是高分 smoke case，v3 对 q03 的目标文档排序更符合业务意图，但 q02 将 operation_rule 排到 Top3 之外。结果保持真实，未强制加入 Golden source，也未修改 Evaluator。
