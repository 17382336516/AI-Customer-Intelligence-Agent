# Apparel Over-Prediction Error Analysis

分析范围：`dataset_01_general` q01 Data artifact，4,000 用户。未修改 Benchmark、Golden Label、Evaluator 或评分逻辑。

## 1. 预测为 apparel 的用户

| 指标 | 数值 |
|---|---:|
| apparel predicted total_count | 655 |
| ground_truth = apparel | 252 |
| wrong apparel predictions | 403 |
| precision of apparel prediction | 38.47% |

### Ground truth 分布

| Ground truth | 数量 | 占 apparel 预测 |
|---|---:|---:|
| apparel | 252 | 38.47% |
| electronics | 99 | 15.11% |
| travel | 67 | 10.23% |
| beauty | 60 | 9.16% |
| home | 59 | 9.01% |
| mother_baby | 45 | 6.87% |
| food | 37 | 5.65% |
| sports | 36 | 5.50% |

## 2. Top错误组合

占比按 655 个 apparel 预测计算。

| ground_truth | predicted | count | percentage |
|---|---|---:|---:|
| electronics | apparel | 99 | 15.11% |
| travel | apparel | 67 | 10.23% |
| beauty | apparel | 60 | 9.16% |
| home | apparel | 59 | 9.01% |
| mother_baby | apparel | 45 | 6.87% |
| food | apparel | 37 | 5.65% |
| sports | apparel | 36 | 5.50% |

## 3. 20个错误样本

类别分布按用户订单金额占比；`total_consumption` 使用输入记录中的用户累计消费字段，缺失时回退为样本订单金额合计。

| customer_id | ground_truth | prediction | purchase_count | total_consumption | recent_activity(days) | category_distribution |
|---|---|---|---:|---:|---:|---|
| C8118270397 | travel | apparel | 1 | 1315.45 | 3 | 旅游100% |
| C1280969396 | home | apparel | 2 | 1113.19 | 3 | 家居100% |
| C0212531459 | sports | apparel | 1 | 966.25 | 22 | 运动100% |
| C9380819425 | food | apparel | 1 | 174.37 | 30 | 食品100% |
| C3498053520 | travel | apparel | 1 | 1365.78 | 9 | 旅游100% |
| C3129847780 | travel | apparel | 1 | 672.13 | 25 | 旅游100% |
| C2767269945 | sports | apparel | 1 | 287.17 | 17 | 运动100% |
| C1520216261 | electronics | apparel | 1 | 3670.12 | 16 | 电子产品100% |
| C9351114309 | sports | apparel | 1 | 900.47 | 27 | 运动100% |
| C1141897911 | beauty | apparel | 1 | 195.59 | 6 | 美妆100% |
| C8640571213 | electronics | apparel | 1 | 3604.38 | 22 | 电子产品100% |
| C6996087199 | travel | apparel | 1 | 1230.14 | 30 | 旅游100% |
| C1028125671 | beauty | apparel | 1 | 895.15 | 5 | 美妆100% |
| C7457056139 | beauty | apparel | 1 | 270.51 | 9 | 美妆100% |
| C5645522125 | electronics | apparel | 1 | 10046.63 | 20 | 电子产品100% |
| C0260423804 | electronics | apparel | 1 | 10567.33 | 28 | 电子产品100% |
| C0256940901 | travel | apparel | 1 | 638.80 | 11 | 旅游100% |
| C1061443537 | electronics | apparel | 1 | 3588.65 | 4 | 电子产品100% |
| C2645496501 | food | apparel | 1 | 133.04 | 28 | 食品100% |
| C2929542879 | electronics | apparel | 1 | 7606.47 | 21 | 电子产品100% |

## 4. 原因判断

### A. Category alias 错误：不是主要原因

当前错误覆盖 electronics、travel、beauty、home、food、sports 等多个 canonical 类别。若是单一 alias 错误，通常会集中在一个类别对；本次是跨类别统一被压到 apparel，因此不符合 alias 局部错误特征。

### B. Canonical hierarchy 错误：不是主要原因

Mapping v1 后，`beauty`、`mother_baby`、`food` 已能正常出现在预测分布中，且错误样本中的原始行为类别清晰。层级映射问题已明显缓解，但仍建议保留 canonical 输出不变量检查。

### C. Scoring/评分输入问题：主要原因

- 655 个 apparel 预测中有 403 个错误，apparel precision 仅 38.47%。
- 多个用户只有单一品类消费（旅游100%、电子产品100%、美妆100%），仍被预测为 apparel。这说明不是用户兴趣边界，而是类别评分输入或评分执行路径异常。
- 当前金额优先公式含频次和近期活跃扣分项；当不同类别比例列未使用同一分母、缺失类别被填充不一致，或行为权重列与实际消费金额列混用时，可能系统性抬高 apparel 得分。

### D. Benchmark 标签定义差异：不是主要原因

单一品类且金额分布为 100% 的样本仍预测为 apparel，不能合理解释为 Golden Label 的多品类边界问题。因此目前不应修改 Benchmark 或 Golden Label。

## 5. 建议

### 是否需要继续修改 Data Agent？

需要，但只建议最小修改，不调整评分公式权重：

1. 在最终选择前记录每个类别的 `amount_ratio`、`frequency_ratio`、`recent_ratio` 和最终 score。
2. 增加不变量：用户只有一个有效消费类别且该类别金额占比 100% 时，预测必须等于该 canonical 类别。
3. 确认三类 ratio 使用同一用户、同一 canonical category 集合和同一分母；缺失类别统一为 0，不得混入默认 `apparel`。
4. 用这20个单一品类错误样本做回归测试，再重新跑 q01–q03。

结论：当前不应继续调金额/频次权重，也不应修改标签。优先修复评分输入对齐和单一品类不变量，之后再评估是否需要调整评分策略。
