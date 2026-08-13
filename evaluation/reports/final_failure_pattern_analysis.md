# Final Failure Pattern Analysis v4

分析范围：3 个数据集、45 个问题。失败案例按问题去重后分析；同一问题可能同时触发 Knowledge、Strategy 和 Overall 失败。

## 1. Failure Distribution

| Agent | Failure Count | Percentage |
|---|---:|---:|
| Data | 0 | 0.00% |
| Insight | 0 | 0.00% |
| Knowledge | 31 | 68.89% |
| Strategy | 38 | 84.44% |

补充：原始失败指标记录共 149 条，其中 S1=38、K1=31、S2=27、K2=24、Overall threshold=29。百分比按 45 个问题计算，Agent 之间可重叠。

## 2. Knowledge Failure Analysis

### K1/K2现象

Knowledge 失败集中在部分 Golden source 未进入 Top3，主要缺失文档类型如下：

| Knowledge type | Missing expected-source count |
|---|---:|
| marketing_case | 13 |
| brand | 6 |
| product | 5 |
| user_growth | 0 |
| operation_rule | 0 |

缺失最集中的文档：

- `marketing_case/case_005.md`：6
- `brand/brand_profile.md`：6
- `marketing_case/case_006.md`：3
- `marketing_case/case_003.md`：3
- `marketing_case/case_002.md`：3

业务问题分布显示：

- 活动运营：marketing_case 缺失 9 次
- 用户召回：marketing_case 缺失 6 次
- 商品推荐：brand 缺失 6 次、product 缺失 5 次
- 复购提升：marketing_case 缺失 1 次

判断：Knowledge 失败不是全局 RAG 不可用，而是集中在具体案例文档、品牌文档和产品文档的 Top3 排名边界，属于特定知识类型/业务意图的检索边界问题。

## 3. Strategy Failure Analysis

### S1 Golden Coverage

S1 失败 38 个问题。当前失败主要不是结构字段完全缺失，而是 Golden 要求的目标人群、产品机制、内容、渠道、指标和必含关键词未全部覆盖，尤其在知识召回不足时更明显。

### S2 Knowledge Adoption

S2 失败 27 个问题，主要链路为：

1. Golden knowledge source 未召回，导致策略没有可用知识；
2. 知识已召回，但没有稳定进入对应 strategy field；
3. 少量情况是采用概念存在，但字段或证据文本与 Golden 规则不一致。

当前 artifact 已具备 `knowledge_applications`，因此不是“完全没有归因结构”的系统性问题，而是知识覆盖和字段级采用的一致性仍有限。

## 4. Business Question Pattern

| 业务类型 | 问题数 | E2E通过 | 通过率 |
|---|---:|---:|---:|
| 用户增长 | 9 | 5 | 55.56% |
| 复购提升 | 9 | 1 | 11.11% |
| 用户召回 | 9 | 0 | 0.00% |
| 活动运营 | 9 | 0 | 0.00% |
| 商品推荐 | 9 | 0 | 0.00% |

用户增长问题表现最好，说明生命周期识别和基础策略链路已经较稳定。活动运营、用户召回、商品推荐更依赖具体企业案例、品牌和产品知识，因此通过率明显较低。

## 5. 最终判断

### 是否达到作品集展示标准？

**达到。**

系统已经具备可展示的完整 Evaluation 闭环：

- 45 个企业营销问题
- DataScore 93.43
- InsightScore 100
- StrategyScore 71.09
- OverallScore 78.98
- 保留真实失败案例和 E2E 通过率 13.33%

### 剩余问题归类

- A. 核心能力缺陷：不是 Data 或 Insight 核心链路；Knowledge 在部分业务意图下的召回稳定性仍不足。
- B. 边界 case：具体 marketing_case、brand、product 文档的 Top3 排名，以及需要多个 Golden 关键词同时覆盖的策略题。
- C. 需要继续优化：如果继续迭代，应聚焦 RAG 的案例/品牌/产品意图覆盖和 Strategy 字段采用；不需要大规模重构。

结论：当前结果适合作为可信 baseline 和作品集展示，不建议为了提升单项分数而修改 Evaluator、阈值、Golden Label 或删除失败案例。
