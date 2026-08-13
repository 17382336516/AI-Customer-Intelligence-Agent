# Data Agent Category Scoring Experiment v1

## 实验约束

- 仅离线重算，不修改生产 Data Agent。
- 不修改 Benchmark、Golden Label、Evaluator。
- 4,000 用户，类别标签使用现有 evaluator alias 归一化。
- D2 使用与现有 evaluator 相同的 total variation similarity。

## 三种策略

### Strategy A：金额优先

`0.5 × amount_ratio - 0.3 × frequency_ratio - 0.2 × recent_ratio`

### Strategy B：兴趣偏好

`0.2 × amount_ratio + 0.4 × frequency_ratio + 0.3 × purchase_count_ratio + 0.1 × recent_ratio`

### Strategy C：用户类型动态权重

- 高价值用户：金额权重 0.6，频次 0.2，近期 0.1，订单数 0.1
- 普通用户：金额 0.25，频次 0.5，近期 0.15，订单数 0.1

## 结果

| Strategy | D1 | D2 | DataScore |
|---|---:|---:|---:|
| A 金额优先 | 93.83% | 97.58% | 94.95 |
| B 兴趣偏好 | 80.50% | 85.22% | 81.92 |
| C 动态权重 | 86.60% | 90.05% | 87.63 |

离线重算显示 Strategy A 最好，但它与当前 q01 artifact 的实际 D1 71.53% 不一致。该差异本身是重要发现：当前生产 artifact 的类别特征、canonical mapping 或评分执行路径与离线定义没有一致落地。不能直接据此修改权重或宣称生产效果已提升。

## 当前错误 Top30

以下为当前 artifact 的错误组合；占比按 1,139 个错误用户计算。

| 真实 → 预测 | 数量 | 错误占比 |
|---|---:|---:|
| beauty → other | 161 | 14.14% |
| mother_baby → kids | 143 | 12.55% |
| electronics → apparel | 99 | 8.69% |
| beauty → apparel | 70 | 6.15% |
| travel → apparel | 67 | 5.88% |
| home → apparel | 59 | 5.18% |
| electronics → travel | 49 | 4.30% |
| mother_baby → apparel | 45 | 3.95% |
| food → other | 40 | 3.51% |
| travel → electronics | 40 | 3.51% |
| sports → apparel | 36 | 3.16% |
| food → apparel | 36 | 3.16% |
| food → gift | 32 | 2.81% |
| beauty → gift | 26 | 2.28% |
| beauty → travel | 19 | 1.67% |
| sports → travel | 17 | 1.49% |
| beauty → sports | 16 | 1.40% |
| home → travel | 13 | 1.14% |
| apparel → sports | 12 | 1.05% |
| beauty → home | 10 | 0.88% |
| sports → other | 9 | 0.79% |
| home → other | 9 | 0.79% |
| apparel → home | 9 | 0.79% |
| apparel → electronics | 8 | 0.70% |
| home → sports | 7 | 0.61% |
| apparel → travel | 7 | 0.61% |
| sports → electronics | 7 | 0.61% |
| home → kids | 7 | 0.61% |
| beauty → electronics | 6 | 0.53% |
| beauty → kids | 6 | 0.53% |

## 回答

### 1. 当前 D1 下降的主要原因

主要不是金额权重本身，而是生产 artifact 与评分定义不一致：

1. `beauty`、`food`、`mother_baby` 被映射为 `other`、`gift`、`kids` 等非 Golden canonical 类别。
2. 大量单品类用户被预测为 `apparel`，说明评分使用的类别列或归一化路径存在错位。
3. Strategy A 的离线结果为 93.83%，反而证明“金额优先”在当前数据上并非天然失败；失败发生在落地链路的一致性。

### 2. 哪种评分策略最好

离线结果中 Strategy A 最好：DataScore 94.95，优于 C 的 87.63 和 B 的 81.92。但在修复映射/输入一致性前，不应直接将 A 推入生产。

### 3. 是否需要修改 Data Agent

需要，但下一步应先做最小修复：

- 统一 `mother_baby/kids`、`beauty`、`food` 等 canonical key；
- 增加单一品类不变量校验；
- 逐用户记录评分输入与最终类别，确认离线和 artifact 使用同一批比例。

暂不建议先改评分权重，也不建议修改 Benchmark 或 Golden Label。

### 4. 预计 Full Evaluation 提升幅度

不能把离线 94.95 直接当作正式提升承诺。若修复后能使生产路径接近离线 Strategy A，D1 理论上可能从 71.53% 回到约 90% 以上，DataScore 可能提升约 15–22 分；实际幅度必须通过 q01–q03 回归验证后再决定是否运行 Full Evaluation。
