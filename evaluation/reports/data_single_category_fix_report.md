# Data Agent Single Category Score Tie Fix

## Bug原因

单一 canonical category 用户的真实类别 score 为：

```text
0.5 × 1 - 0.3 × 1 - 0.2 × 1 = 0
```

不存在消费记录的类别也得到 0 分，最终按类别列顺序选择了 `apparel`。

## 修改内容

仅修改 `user_category_score_details` 的候选类别执行逻辑：

1. 只保留有金额、频次或近期消费记录的 canonical category。
2. 如果只有一个有效 category 且 amount_ratio = 1，直接返回该 category。
3. 多品类用户继续使用原有 score 公式和权重。

未修改 Benchmark、Golden Label、Evaluator、category mapping、score 公式或权重。

## 新增测试

覆盖：

- electronics 100% → electronics
- beauty 100% → beauty
- apparel 100% → apparel
- 多品类用户仍按原 score 逻辑选择

测试结果：4 个场景全部通过。

## q01–q03指标变化

| 指标 | 修复前 | 修复后 | 变化 |
|---|---:|---:|---:|
| D1 | 81.85% | 91.07% | +9.22pp |
| D2 | 91.05% | 98.25% | +7.20pp |
| DataScore | 84.61 | 93.23 | +8.62 |
| OverallScore | 92.07 | 95.67 | +3.60 |
| E2E Pass Rate | 0/3 | 2/3 | +2 cases |

结果文件：

`evaluation/reports/single_category_fix_q01_q03_results.json`

本次修复只针对已确认的 score tie bug，未继续优化其他 Data Agent 问题。
