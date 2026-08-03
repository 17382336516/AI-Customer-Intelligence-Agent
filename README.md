# 群策 · AI Customer Intelligence Agent

一个面向产品经理的 workflow-based 3+1 Multi-Agent 决策辅助系统。输入多用户消费数据和业务问题，输出人群分群、需求洞察、产品策略、页面方向、slogan 与验证指标。

项目按 PRD V1.1 实现，默认不依赖模型密钥也能完整运行；配置 OpenAI-compatible 模型后，会在不发送原始交易明细的前提下增强洞察和策略表达。

## 已实现

- Orchestrator Agent：意图识别、任务拆解、动态路由、异常回退
- Data Agent：CSV / Excel、质量报告、数据清洗、RFM、规则分群、KMeans 辅助
- Insight Agent：证据解释、需求洞察、替代解释、限制说明
- Strategy Agent：产品机制、权益、页面结构、视觉关键词、slogan、验证指标
- LangGraph 条件工作流：质量检查、仅分群、完整策略三条路径
- Memory：高质量聚合案例入库；删除数据集时联动清理
- Evaluation：完整度、证据覆盖、可执行性、区分度与告警
- Vue 3 工作台：上传、质量仪表、Agent 轨迹、人群图、策略卡和页面方向

架构细节见 [docs/architecture.md](docs/architecture.md)，PRD 对照见 [docs/acceptance-checklist.md](docs/acceptance-checklist.md)。

## 一键运行

需要 Docker Desktop：

```bash
docker compose up --build
```

打开 `http://localhost:8080`。首次体验可直接点击“载入完整示例”，然后开始分析。

Docker 方案使用 PostgreSQL / pgvector 镜像、FastAPI 后端和 Nginx 托管的 Vue 前端。

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m app
```

接口文档：`http://localhost:8000/docs`

### 前端

```bash
cd frontend
npm install
npm run dev
```

工作台：`http://localhost:5173`

## 模型增强（可选）

复制 `.env.example` 为 `.env`，配置任意兼容 Chat Completions 协议的服务：

```env
LLM_API_KEY=...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=...
```

未配置时，系统使用确定性洞察与策略模板。配置后，Insight Agent 与 Strategy Agent 会增强表达；发生超时或解析错误时自动降级，不中断主流程。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/datasets/upload` | 上传并校验数据 |
| `POST` | `/api/v1/demo/dataset` | 创建可演示数据集 |
| `GET` | `/api/v1/datasets/{id}` | 查看数据与质量报告 |
| `DELETE` | `/api/v1/datasets/{id}` | 删除数据及相关分析和 Memory |
| `POST` | `/api/v1/analyses` | 创建分析任务 |
| `GET` | `/api/v1/analyses/{id}` | 查询结构化结果 |
| `GET` | `/api/v1/analyses/{id}/events` | 查看 Agent 审计轨迹 |
| `GET` | `/api/v1/meta/agents` | 查看 3+1 Agent 清单 |

## 输入字段

系统会自动识别中英文别名。核心字段：

- `user_id`
- `amount`
- `event_time`
- `category` 或 `product` 至少一个

可选字段：`order_id`、`status`、城市、会员等级和渠道。系统不会使用可选属性推断敏感身份。

## 测试

```bash
cd backend
pytest
ruff check app tests

cd ../frontend
npm run build
```

