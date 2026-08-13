# Category Distribution Analysis

分析范围：`dataset_01_general`，4,000 用户，使用 q01 Data artifact；类别按现有 alias 规则归一化。

| Category | Ground truth users | Ground truth share | Data Agent prediction users | Prediction share | Difference |
|---|---:|---:|---:|---:|---:|
| electronics | 1,712 | 42.80% | 1,632 | 40.80% | -2.00pp |
| travel | 837 | 20.93% | 826 | 20.65% | -0.28pp |
| beauty | 314 | 7.85% | 0 | 0.00% | -7.85pp |
| apparel | 297 | 7.43% | 664 | 16.60% | +9.17pp |
| sports | 282 | 7.05% | 250 | 6.25% | -0.80pp |
| home | 232 | 5.80% | 161 | 4.03% | -1.77pp |
| mother_baby | 208 | 5.20% | 0 | 0.00% | -5.20pp |
| food | 118 | 2.95% | 0 | 0.00% | -2.95pp |
| other | 0 | 0.00% | 229 | 5.73% | +5.73pp |
| kids | 0 | 0.00% | 173 | 4.33% | +4.33pp |
| gift | 0 | 0.00% | 65 | 1.63% | +1.63pp |

结论：预测分布明显向 `apparel`、`other`、`kids` 偏移，且 `beauty`、`food`、`mother_baby` 被系统性吞并。这不是单纯的类别比例波动，首先应排查 canonical mapping 和评分输入列对齐。
