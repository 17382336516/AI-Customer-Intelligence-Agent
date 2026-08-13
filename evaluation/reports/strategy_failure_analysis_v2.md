# Strategy Failure Analysis v2

分析范围：3 个数据集、45 个 Business Questions。未修改 Agent、Benchmark、Golden Label 或 Evaluator。

## 1. Strategy失败分布

| 指标 | 失败数量 | 45题占比 |
|---|---:|---:|
| S1 Golden Coverage | 38 | 84.44% |
| S2 Knowledge Adoption | 27 | 60.00% |

### 按业务类型的 E2E 通过率

| 业务类型 | 问题数 | E2E通过 | 通过率 |
|---|---:|---:|---:|
| 用户增长 | 9 | 5 | 55.56% |
| 用户召回 | 9 | 0 | 0.00% |
| 复购提升 | 9 | 1 | 11.11% |
| 活动运营 | 9 | 0 | 0.00% |
| 商品推荐 | 9 | 0 | 0.00% |

## 2. S1失败原因分类

### 结构字段

在失败 artifact 中未发现以下字段系统性为空：

- target_segment
- product_strategy
- content_strategy
- promotion_strategy
- channel
- metrics

因此 A–F 不是主要原因。

### 业务关键词缺失

S1 失败主要来自 G：Golden 要求的业务关键词没有完整进入 `generated_strategy_text`。典型缺失包括：

- 用户增长：城市、信任、分层运营
- 复购：补贴控制、触发条件、分阶段
- 召回：长期未购、最近购买天数、召回优先级、个性化召回
- 活动：618、春节、分层权益、家庭场景、社交传播
- 商品推荐：品类偏好、关联推荐、笔笔攒、目标储蓄

额外观察：dataset_03 的部分问题 target_segment 偏向 `high_value_user`，与问题要求的年轻/品类兴趣目标不完全一致，但主要扣分仍来自关键词覆盖不足。

## 3. S2失败原因

基于 retrieval_results、knowledge_plan、knowledge_applications 的逐题对齐：

| 原因 | 数量 | 说明 |
|---|---:|---|
| 知识没有召回 | 24 | Golden source 不在 retrieval_results |
| 已召回但没有进入 knowledge_plan | 3 | 召回结果存在，但规划层未形成对应计划 |
| 进入 knowledge_plan 但没有进入 strategy 字段 | 18 | 有计划，但未形成有效 knowledge_application |
| 进入 strategy 但 Evaluator 未识别 | 0 | 当前没有证据支持这是主因 |

S2 的主问题是上游召回缺失和计划到策略字段的落地断层，而不是 artifact 完全没有结构。

## 4. Top 10 失败案例

| question_id | business_goal | expected_strategy | actual_strategy | missing_element |
|---|---|---|---|---|
| dataset_01_general_q03 | 用户增长 | 年轻用户、城市、信任、分层运营 | target_segment=young_growth_user；通用年轻用户内容 | 城市、信任、分层运营 |
| dataset_01_general_q04 | 复购提升 | 高价值用户、复购、权益、补贴控制 | target_segment=young_growth_user；通用组合促销 | 高价值、补贴控制 |
| dataset_01_general_q05 | 复购提升 | 会员、频次、客单价、触发条件 | 通用内容与渠道策略 | 会员、触发条件 |
| dataset_01_general_q06 | 复购提升 | 优惠券、价格敏感、复购、分阶段 | 通用优惠与复购表达 | 分阶段 |
| dataset_01_general_q07 | 用户召回 | 长期未购、召回、分层触达、频控 | 通用年轻用户触达 | 长期未购、频控 |
| dataset_01_general_q08 | 用户召回 | 历史价值、最近购买天数、召回优先级 | 通用召回策略 | 最近购买天数、优先级 |
| dataset_01_general_q10 | 活动运营 | 618、分层权益、高价值、价格敏感 | 通用活动与优惠策略 | 618、分层权益 |
| dataset_01_general_q11 | 活动运营 | 春节、年轻用户、家庭场景、攒钱 | 通用年轻用户内容 | 春节、家庭场景、攒钱 |
| dataset_01_general_q13 | 商品推荐 | 电子产品、品类偏好、年轻用户 | 通用数码推荐 | 品类偏好 |
| dataset_01_general_q15 | 商品推荐 | 低门槛、笔笔攒、目标储蓄、消费行为 | 有产品机制但未稳定覆盖目标储蓄表达 | 笔笔攒、目标储蓄 |

## 5. 最终建议

### A. Prompt问题：部分是

当前 Strategy 生成模板能生成完整结构，但对问题级业务关键词约束不足，导致输出偏通用营销语言。建议仅增加“逐条覆盖 business question constraints”的轻量检查，不做整体 Prompt 重写。

### B. Artifact结构问题：不是主要问题

`strategy_card`、`knowledge_plan`、`knowledge_applications` 和本轮新增 trace 均已存在。问题在内容是否真实进入字段，而非字段缺失。

### C. Knowledge Planning问题：是

3 个问题属于“已召回但未进入计划”，18 个问题属于“进入计划但未进入有效 strategy field”。应优先检查 source → knowledge type → target field 的映射和采用证据。

### D. Evaluator问题：不是主因

S1 的关键词匹配确实较严格，但 Golden 关键词与业务目标直接相关，不能简单放宽。当前失败主要是 Agent 未输出要求内容，而不是 Evaluator 错误。

结论：当前 Strategy 瓶颈是 **知识规划落地 + 问题级约束覆盖**，属于局部能力问题，不需要大规模重构。下一步只建议增加计划到字段的最小校验和关键词覆盖检查。
