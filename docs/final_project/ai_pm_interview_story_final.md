# AI PM 面试讲解故事

## Q1：为什么做这个项目？

企业营销团队通常需要把用户数据、用户洞察、企业经验和活动策略拼接起来，流程依赖人工且难以复用。我设计 Customer Intelligence Agent，把这条链路拆成 Data、Insight、Knowledge、Strategy 四个可诊断模块，目标是提升决策辅助效率和策略可解释性。

## Q2：为什么不只是使用普通 RAG？

普通 RAG 只能解决“找文档”，但营销决策还需要理解用户行为、判断生命周期、规划知识用途并生成策略。因此系统采用 Data Agent、Insight Agent、Knowledge Agent 和 Strategy Agent 协作，并用 artifacts 记录每一步证据。

## Q3：为什么采用 Multi-Agent？

- Data Agent：处理消费事实和商品偏好。
- Lifecycle Classification：基于用户级信号识别生命周期。
- Insight Agent：把统计结果转成可解释洞察。
- Knowledge Agent：按业务意图检索企业知识。
- Strategy Agent：将知识规划落到产品、内容、促销、渠道和指标字段。

模块边界让失败可以定位，而不是只看到一个不可解释的最终文本。

## Q4：最大的挑战是什么？

最大的挑战不是单纯提高模型生成能力，而是证明输出可信。为此我设计了 Benchmark、Golden Label、D/I/K/S 指标、Artifact Persistence 和 Failure Analysis。比如 Knowledge Retrieval 成功不等于 Strategy 采用成功，必须验证 source→concept→field→expression 的闭环。

## Q5：如何迭代？

先看失败位置，再做最小修改：数据类别映射错误导致 Data 下降，就修 canonical mapping；生命周期被商品分群平均，就升级到 user-level classifier；RAG 召回不稳定，就增加 intent routing 和 metadata rerank；策略知识无法验证，就加入 business concept alignment。每轮都冻结 Benchmark 和 Evaluator，保留真实结果。

## Q6：如果继续优化，会做什么？

优先提升 Enterprise Knowledge Coverage 和 Strategy Requirement Coverage；补充人工评审闭环，加入线上 shadow evaluation，并扩大真实企业知识和业务问题覆盖。不会用降低阈值或删除失败案例的方式刷分。

## Q7：如何解释最终结果？

v7 覆盖 3 套数据集、12000 用户、45 个问题：DataScore 93.43、InsightScore 100、KnowledgeScore 65.17、StrategyScore 75.37、OverallScore 83.10，Grounding 平均 89.63%，E2E Pass Rate 15.56%。这是 deterministic offline baseline，不是线上商业收益实验。
