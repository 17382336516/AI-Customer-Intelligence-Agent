# RAG v3 q01–q03 Failure Analysis

仅 q02 的 K1 未完全命中：

- q01：K1 100%，K2 100%，KnowledgeScore 100
- q02：K1 50%，K2 100%，KnowledgeScore 65
- q03：K1 100%，K2 100%，KnowledgeScore 100

q02 的 primary/secondary 之一未进入 Top3，缺失的是 `operation_rule/marketing_rule.md`；其 primary 文档已在 rank 1，因此 MRR 仍为 100%。

q03 通过了品牌 + marketing_case 的 Top3 召回，说明针对“城市/信任”条件的意图路由已生效。

当前未发现 metadata 缺失导致的空结果；主要剩余问题是 q02 的 Top3 多样性与 operation_rule 排名边界。
