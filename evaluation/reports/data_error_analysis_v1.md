# Data Agent Error Analysis v1

## 1. D1错误统计

分析范围：`dataset_01_general`，q01 artifact（q01–q03 使用同一份用户级 Data artifact）。

| 指标 | 数值 |
|---|---:|
| total_users | 4,000 |
| correct_users | 2,861 |
| wrong_users | 1,139 |
| accuracy | 71.53% |

类别归一化沿用现有 `category_alias_mapping.json`，未修改评估规则。

## 2. Top 20 Confusion Matrix

| 真实类别 | 预测类别 | 数量 |
|---|---|---:|
| beauty | other | 161 |
| mother_baby | kids | 143 |
| electronics | apparel | 99 |
| beauty | apparel | 70 |
| travel | apparel | 67 |
| home | apparel | 59 |
| electronics | travel | 49 |
| mother_baby | apparel | 45 |
| food | other | 40 |
| travel | electronics | 40 |
| sports | apparel | 36 |
| food | apparel | 36 |
| food | gift | 32 |
| beauty | gift | 26 |
| beauty | travel | 19 |
| sports | travel | 17 |
| beauty | sports | 16 |
| home | travel | 13 |
| apparel | sports | 12 |
| beauty | home | 10 |

## 3. 20个错误样本

金额单位为数据集原始金额；类别分布为该用户订单金额占比；样本随机种子为 42。

| customer_id | ground truth | prediction | purchase_count | total_consumption | category_distribution |
|---|---|---|---:|---:|---|
| C2828499931 | electronics | apparel | 1 | 388.50 | 电子产品100% |
| C8619304344 | mother_baby | apparel | 6 | 2558.18 | 母婴36%, 服饰29%, 运动15% |
| C9007314491 | electronics | apparel | 2 | 3703.41 | 电子产品100% |
| C7219935573 | home | kids | 11 | 9345.46 | 家居30%, 母婴20%, 服饰20% |
| C2569628618 | mother_baby | kids | 1 | 604.72 | 母婴100% |
| C2195305400 | mother_baby | kids | 3 | 1110.30 | 母婴52%, 电子产品39% |
| C1711833759 | beauty | apparel | 2 | 412.61 | 美妆68%, 食品32% |
| C3891552839 | electronics | apparel | 1 | 3616.90 | 电子产品100% |
| C1548677093 | apparel | kids | 6 | 3557.14 | 服饰47%, 母婴37% |
| C9844864315 | electronics | apparel | 1 | 7700.95 | 电子产品100% |
| C7167583634 | beauty | other | 1 | 453.33 | 美妆100% |
| C3619319680 | electronics | apparel | 1 | 5408.73 | 电子产品100% |
| C0421088160 | electronics | apparel | 3 | 26842.92 | 电子产品100% |
| C6753129957 | sports | apparel | 2 | 848.30 | 运动100% |
| C2391320503 | beauty | gift | 5 | 1170.78 | 美妆37%, 运动22%, 家居20% |
| C5566398195 | beauty | other | 1 | 530.34 | 美妆100% |
| C2377184770 | mother_baby | apparel | 1 | 725.72 | 母婴100% |
| C8459244607 | mother_baby | kids | 1 | 221.95 | 母婴100% |
| C5644675676 | beauty | other | 1 | 264.65 | 美妆100% |
| C2029820898 | beauty | apparel | 6 | 3574.41 | 美妆34%, 服饰30%, 运动22% |

近期活跃字段在 artifact 中由 Data Agent 计算；本报告不重新推断标签。

## 4. 错误原因判断

### A. Prediction规则错误（主要）

- `electronics → apparel`、`beauty → apparel` 等错误出现在单一品类或明显主品类用户上，不能仅用“金额权重不足”解释。
- 新评分对频次占比和近期占比做扣分，在单一品类用户上会产生较强惩罚；同时应核查各类别特征列是否在评分阶段完整对齐。
- 这类错误优先指向预测特征/评分实现，而不是 Benchmark 标签。

### B. Category mapping问题（明确存在）

- `mother_baby → kids` 是层级名称不一致：业务标签使用 `mother_baby`，预测使用 `kids`。
- `beauty → other` 说明美妆别名或细分类别没有稳定归一化。
- 该类问题会同时拉低 D1，但不一定代表用户行为预测错误。

### C. Ground Truth与业务定义不一致（次要）

- 多品类用户如 `home` 用户同时有母婴、服饰、电子产品消费，单一主品类标签存在边界歧义。
- 但单品类用户被预测为无关类别，不能归因于标签边界。

### D. 数据增强导致标签偏差（当前证据不足）

- 本次 D1 只比较商品偏好标签；年龄、收入、生命周期增强字段不会直接改变 `category_ground_truth`。
- 暂无证据表明数据增强是主要原因。

## 5. 下一步建议

1. **先修复类别映射和特征列对齐**：补齐 `mother_baby/kids`、`beauty` 等 canonical 映射，并对单一品类用户增加不变量检查：金额占比 100% 时不得预测到无消费品类。
2. **再验证评分权重**：保持 Benchmark、Golden Label、Evaluator 不变，离线比较金额权重、频次扣分和近期活跃扣分的敏感性；不要直接调参追分。
3. **保留品类兴趣定义**：目前“主品类=金额/行为综合最高”仍可作为基线，但多品类用户应记录 top-2 分布和集中度，避免把边界用户强行解释为单一偏好。
4. **暂不修改 Benchmark 标签**：当前存在明确的映射/预测异常，尚不能据此判定 Golden Label 错误。只有在完成映射和实现审计后，仍持续出现系统性边界冲突，才评估标签定义。

结论：当前优先级为 **类别映射与评分输入对齐 > 评分权重校准 > 多品类兴趣定义增强**；不建议先修改 Benchmark 或 Golden Label。
