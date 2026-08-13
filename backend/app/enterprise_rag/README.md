# Enterprise Knowledge RAG

为 **AI Customer Intelligence Agent（群策）** 提供企业业务上下文增强层，使 Strategy Agent
在生成营销策略时，不再只依赖用户消费数据与用户洞察，而能结合企业业务背景、产品体系、
用户增长目标、营销案例与竞品信息，生成符合真实企业场景的营销策略。

## Purpose

- 让营销策略生成同时考虑：用户洞察、企业业务目标、产品能力、品牌定位、历史营销经验。
- 禁止生成与企业定位冲突的策略（如夸大收益、编造未公开内部指标）。

## Knowledge Structure

| 分类 (category) | 目录 | 内容 |
|----------------|------|------|
| brand | `brand/brand_profile.md` | 企业 / 品牌定位、用户定位、品牌调性、竞争环境 |
| product | `product/yu_e_bao.md` `bi_bi_zan.md` `xiao_zhu_zan_qian_guan.md` | 余额宝、笔笔攒、小猪攒钱罐产品知识 |
| case | `marketing_case/case_001~006.md` | 余额宝营销案例（小挣青年 / 十周年 / 年年有余 / 时光机 / 葫芦兄弟 / 余人节） |
| growth | `user_growth/young_user_growth.md` | 年轻用户增长背景、挑战、机会 |
| competition | `competition/competitor_analysis.md` | 微信零钱通竞品分析 |
| operation_rule | `operation_rule/marketing_rule.md` | 年轻用户运营原则、金融产品营销限制 |

## Metadata

每篇文档顶部 YAML frontmatter 携带：

```yaml
type: enterprise
company: Ant Group
product: Yu'eBao
category: brand|product|case|growth|competition
source: 公开资料链接
```

`KnowledgeBase` 解析该 frontmatter，在检索结果中透传 `metadata`，
`KnowledgeAgent` 据此区分「用户消费知识」与「企业知识」，
仅把 `type=enterprise` 的命中组装为 `enterprise_context` 供 Strategy Agent 使用。

## Usage

1. `KnowledgeAgent` 检索知识库（含 `settings.knowledge_dir` 用户知识 + `settings.enterprise_knowledge_dir` 企业知识）。
2. 检索结果写入 `state["knowledge_support"]` 与 `state["enterprise_context"]`。
3. `StrategyAgent` 在 prompt 中接收 `enterprise_context`，并受企业约束 checklist 约束。

## Data Source

所有内容来自公开资料整理（百度百科、数英网、新京报、澎湃新闻等），任何案例均可追溯到
`## Source` 中标注的链接。未补充任何未公开的用户增长比例、GMV 提升、转化率或内部运营指标；
仅保留公开的活动目标、产品机制、营销方式与可复用策略方向。

> 注意：本知识库用于模拟企业 AI 决策场景，不构成任何真实业务承诺。
