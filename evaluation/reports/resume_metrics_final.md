# Resume Metrics — Customer Intelligence Agent

构建企业级 Customer Intelligence Agent Evaluation Framework，基于：

- 3 套 Benchmark Dataset
- 12,000 用户
- 45 个营销任务

实现：

- 消费偏好识别准确率：91.11%
- Insight Grounding：100.00%
- Enterprise RAG Recall@3：61.67%
- Knowledge Adoption：68.33%
- Strategy Golden Coverage：72.15%
- Overall Evaluation Score：83.10%
- E2E Pass Rate：15.56%（7/45）

实验模式：`deterministic_fallback`，不应包装为真实线上 qwen LLM 实验。
