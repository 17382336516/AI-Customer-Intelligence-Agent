# Data Agent Scoring Pipeline Audit v1

审计范围：`dataset_01_general` 完整 4,000 用户特征构建路径。仅做静态审计和只读复核，未修改代码、Benchmark、Golden Label、Evaluator 或评分权重。

## 1. 发现的问题

### 1.1 category 集合

审计结果：

- score 计算使用 categories：`apparel, beauty, electronics, food, home, mother_baby, sports, travel`
- prediction 使用 categories：同上
- score/prediction category diff：空集

因此不存在“score 使用一套类别、prediction 使用另一套类别”的集合错位。

### 1.2 amount_ratio

审计结果：

- 用户数：4,000
- amount_ratio 总和异常：0
- 所有有金额用户的 amount_ratio 之和均为 1（浮点误差范围内）

金额比例计算本身没有发现归一化错误。

### 1.3 单品类不变量

审计结果：

- 只有一个 canonical category 且 amount_ratio = 1 的用户：924
- 违反“预测必须等于该唯一类别”的用户：369

这是已确认的生产 bug。

## 2. 具体代码位置

### 2.1 类别集合构建

`backend/app/services/data_tools.py:697-726`

- `pivot_weighted`、`count_shares`、`recent_shares` 均按 `normalized_category` 聚合。
- category 列统一从 `weighted_matrix.columns` 生成。

### 2.2 ratio 计算

`backend/app/services/data_tools.py:854-860`

- `amount_ratio` 使用 `{category}_purchase_amount / total_amount`。
- `frequency_ratio` 使用 `{category}_share`。
- `recent_ratio` 使用 `{category}_recent_share`。

三类 ratio 的分母分别在各自矩阵中按用户归一化；amount_ratio 实测总和正常。

### 2.3 已确认的 tie bug

`backend/app/services/data_tools.py:861-866`

当前公式：

```text
score = 0.5 * amount_ratio - 0.3 * frequency_ratio - 0.2 * recent_ratio
```

对唯一品类用户：

```text
amount_ratio = 1
frequency_ratio = 1
recent_ratio = 1
score = 0.5 - 0.3 - 0.2 = 0
```

而所有不存在的类别也会被当作 0：

```text
amount_ratio = 0
frequency_ratio = 0
recent_ratio = 0
score = 0
```

随后 `sorted(scores.items(), key=lambda item: item[1], reverse=True)` 在并列时保留类别列原始顺序。当前类别顺序中 `apparel` 排在前面，因此唯一 beauty/electronics/travel 等用户会被错误选为 apparel。

这直接解释了大量“单一品类金额 100% 仍预测 apparel”的现象。

## 3. index alignment 审计

未发现导致 apparel 系统性偏移的 index 错位：

- `pivot_table`、`groupby` 结果均按 `user_id` 索引。
- `reindex(features.index)` 明确对齐用户特征索引。
- `purchase_long`、`recent_shares` 也在写入特征列前执行了 `reindex(features.index)`。
- `user_category_score_details` 使用 `features.loc[idx]`，并按同一行读取类别列。
- prediction 由同一份 `details` 顺序生成，没有独立排序或 `iloc` 重排。

因此当前主因不是 merge/sort/iloc/index 错位，而是评分结果的零分并列处理。

## 4. 是否确认 bug

**确认。**

Bug 类型：评分公式允许真实类别和不存在类别同时得到 0 分，缺少“只在有效消费类别中选择”或唯一品类短路逻辑。

类别映射链路本身已统一；ratio 归一化和索引对齐也未发现异常。

## 5. 最小修复方案

不改变评分公式和权重，仅修改候选类别选择：

1. 仅保留 `amount > 0` 或至少一个行为比例大于 0 的有效类别作为候选；或
2. 对 `len(nonzero_categories) == 1` 直接返回该唯一 canonical category；或
3. 二者同时实现，并增加 924 个单品类用户的不变量测试。

建议采用第 2 + 第 3 项：逻辑最小、可解释、不会改变多品类用户的既有评分排序。

修复后应重新执行 q01–q03；在未修复前不应继续调权重或修改 Benchmark 标签。
