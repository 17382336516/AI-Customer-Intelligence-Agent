# AI Product Manager Interview Story

## Situation

企业营销分析通常需要在用户数据、人工洞察、企业经验和策略制定之间多次切换，过程耗时且难以验证。

## Task

设计一个能够从消费行为出发，生成生命周期洞察、调用企业知识并输出营销策略的 Customer Intelligence Agent，同时建立可量化的 Evaluation Framework。

## Action

我将系统拆成 Data、Insight、Knowledge、Strategy 四层，并为每层设计 artifact 和可计算指标。迭代中先修复类别 canonical mapping 和单品类 tie bug，再将生命周期判断下沉到用户级；随后加入 RAG intent routing、query expansion、metadata rerank，以及 Strategy Requirement Planner 和 Knowledge Trace。

## Result

在 3 套 Benchmark、12,000 用户、45 个营销任务上，最终 DataScore 为 93.43，InsightScore 为 100，KnowledgeScore 为 65.17，StrategyScore 为 75.37，OverallScore 为 83.10。

## Reflection

结果证明数据和洞察链路已具备稳定 baseline，但 RAG 和业务策略覆盖仍是瓶颈。后续可以接入更真实的企业知识、Human Feedback Loop 和 Online Evaluation，但不能把当前离线结果包装成真实商业收益。
