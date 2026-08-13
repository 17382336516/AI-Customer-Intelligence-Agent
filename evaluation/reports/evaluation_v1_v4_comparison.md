# Evaluation v1 vs v4

| Metric | V1 | V4 | Improvement |
|---|---:|---:|---:|
| DataScore | 76.49 | 93.43 | +16.94 |
| InsightScore | 81.78 | 100.00 | +18.22 |
| KnowledgeScore | 56.93 | 52.03 | -4.90 |
| StrategyScore | 52.58 | 71.09 | +18.51 |
| OverallScore | 65.53 | 78.98 | +13.45 |
| E2E Pass Rate | 0.00% | 13.33% (6/45) | +13.33pp |

V4 使用 `deterministic_fallback` 模式，不应包装为真实 qwen LLM 实验。KnowledgeScore 下降，保留为真实结果。
