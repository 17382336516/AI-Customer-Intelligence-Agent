# Failure Case Library

## Case 1：Data 类别映射错误

- Problem：beauty、mother_baby 等类别被错误归入 other、kids 或 apparel。
- Detection：D1 下降而 D2 相对稳定；confusion matrix 出现集中错配。
- Root Cause：raw category、canonical category 与 evaluation category 不一致。
- Solution：建立 canonical mapping、alias normalization，并修复单品类 score tie。
- Metric Change：DataScore 从 76.49 提升至 93.43。

## Case 2：Lifecycle 识别粒度不足

- Problem：同一商品分群内混合 high value、young growth 和 churn 场景。
- Detection：I1 失败，segment-level 平均统计无法匹配 Golden Label。
- Root Cause：生命周期判断基于分群平均值，而非用户级信号。
- Solution：引入 user-level lifecycle classification 和 evidence。
- Metric Change：InsightScore 从 81.78 提升至 100。

## Case 3：RAG Recall 失败

- Problem：业务问题中的“年轻用户增长”等表达没有稳定召回 primary knowledge source。
- Detection：K1 Recall@3 和 K2 MRR 下降，retrieval artifact 记录 source、rank、score 和 metadata。
- Root Cause：query 与企业知识概念存在语义距离，知识类型混合导致排序靠后。
- Solution：Intent Routing、Query Expansion、Metadata Rerank 和知识类型路由。
- Metric Change：KnowledgeScore 从 56.93 提升至 65.17。

## Case 4：Strategy Coverage 失败

- Problem：策略文本较通用，缺少 target segment、业务关键词或完整字段。
- Detection：S1 Golden Coverage 失败，strategy_card 与 Golden Rule 对比暴露缺失字段。
- Root Cause：生成前没有显式 Strategy Requirement Planning。
- Solution：增加 strategy requirement、knowledge plan 和 field-level attribution。
- Metric Change：StrategyScore 从 52.58 提升至 75.37。

## Case 5：Knowledge Grounding 失败

- Problem：知识“自动小额储蓄降低使用门槛”与策略“培养长期使用习惯”语义一致，但严格关键词匹配失败。
- Detection：Grounding 初始约 54.44%，matched_concepts 为空或 failed_concepts 增多。
- Root Cause：Document Concept 与 Strategy Text 之间缺少 Business Concept 中间层。
- Solution：增加 knowledge aliases、business concept mapping 和三层 verifier。
- Metric Change：完整 v7 Grounding 平均 89.63%。
