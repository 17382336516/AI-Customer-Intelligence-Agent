from __future__ import annotations

import json
import logging
import random
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .agents.orchestrator import OrchestratorAgent
from .config import settings
from .database import Repository, SessionLocal, SessionRecord, init_db
from .schemas import (
    AnalysisCreate,
    AnalysisResponse,
    AuditEventResponse,
    ConversationResponse,
    ContinueAnalysisCreate,
    DatasetAssetResponse,
    DatasetResponse,
    MessageResponse,
    QualityReport,
    SessionDetailResponse,
    SessionResponse,
    SessionSummary,
)
from .services.context_manager import ContextManager
from .services.data_tools import build_quality_report, build_upload_preview, read_dataset_preview
from .workflow import CustomerIntelligenceWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    init_db()
    yield


app = FastAPI(
    title="AI Customer Intelligence Agent",
    description="ML customer segmentation + multi-agent orchestration + RAG knowledge-enhanced decision platform",
    version="1.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def _dataset_response(record, preview: dict | None = None, record_count: int = 0) -> DatasetResponse:
    return DatasetResponse(
        id=record.id,
        name=record.name,
        file_type=record.file_type,
        row_count=record.row_count,
        quality=QualityReport.model_validate(json.loads(record.quality_json)),
        created_at=record.created_at,
        preview=preview,
        record_count=record_count,
    )


def _analysis_response(record, dataset_name: str = "") -> AnalysisResponse:
    return AnalysisResponse(
        id=record.id,
        dataset_id=record.dataset_id,
        dataset_name=dataset_name,
        question=record.question,
        status=record.status,
        route=record.route,
        result=json.loads(record.result_json),
        error_message=record.error_message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _run_analysis(analysis_id: str, payload: dict[str, str]) -> None:
    with SessionLocal() as session:
        repository = Repository(session)
        dataset = repository.get_dataset(payload["dataset_id"])
        if dataset is None:
            repository.fail_analysis(analysis_id, "数据集不存在或已删除。")
            return
        # 关联或创建 Analysis Session（分析项目）
        session_id = payload.get("session_id") or ""
        existing = repository.get_session(session_id) if session_id else None
        if existing is None:
            analysis_session = repository.create_session(
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                name=payload.get("session_name") or f"{dataset.name} 分析项目",
            )
        else:
            analysis_session = existing
            repository.update_session(analysis_session.id, status="active")
        conversation = repository.add_conversation(
            session_id=analysis_session.id,
            analysis_id=analysis_id,
            question=payload["question"],
        )
        logger.info(
            "[业务记录] 创建 business_record=%s session=%s question=%s",
            conversation.id,
            analysis_session.id,
            payload["question"],
        )
        # 数据资产复用：若同一数据集已有沉淀的洞察资产，则直接读取缓存，
        # 跳过数据清洗 / 分群 / Insight Agent，仅基于既有洞察生成策略。
        cached = repository.get_cache(dataset.id)
        cached_analysis: dict[str, Any] | None = None
        if cached is not None:
            try:
                cached_analysis = json.loads(cached.result_json)
            except (json.JSONDecodeError, TypeError):
                cached_analysis = None
        # 构建会话上下文（来自真实历史数据）
        ctx = ContextManager(repository).build_session_context(analysis_session, payload["question"])
        try:
            workflow = CustomerIntelligenceWorkflow(repository)
            result = workflow.invoke(
                {
                    "analysis_id": analysis_id,
                    "dataset_id": dataset.id,
                    "dataset_path": dataset.file_path,
                    "question": payload["question"],
                    "strategy_goal": payload["strategy_goal"],
                    "brand_tone": payload["brand_tone"],
                    "analysis_window": payload["analysis_window"],
                    "session_id": analysis_session.id,
                    "conversation_id": conversation.id,
                    "session_context": ctx,
                    "cached_analysis": cached_analysis,
                    "model_mode": "deterministic",
                }
            )
            repository.finish_analysis(analysis_id, result)
            # 沉淀数据集分析资产（仅当本次包含完整洞察时写入/更新缓存）
            if result.get("segments") and result.get("insights"):
                repository.upsert_cache(
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    quality=result.get("quality", {}),
                    result=result,
                )
            strategy_cards = result.get("strategy_cards", []) or []
            logger.info(
                "[业务记录] business_record=%s strategy_agent_response cards=%s route=%s intent=%s",
                conversation.id,
                len(strategy_cards),
                result.get("route"),
                result.get("intent"),
            )
            # 完整结果回填业务记录：洞察 / 策略 / 执行轨迹，支持历史记录独立展示。
            repository.update_conversation_results(
                conversation.id,
                answer_summary=result.get("executive_summary", ""),
                insight_result=result.get("insights", []),
                strategy_result=strategy_cards,
                agent_trace=result.get("agent_trace", []),
            )
            logger.info(
                "[业务记录] 保存结果 business_record=%s insight=%s strategy=%s trace=%s",
                conversation.id,
                len(result.get("insights", []) or []),
                len(strategy_cards),
                len(result.get("agent_trace", []) or []),
            )
            # 更新 Session 摘要
            _summarize_session(repository, analysis_session, result)
            if result["strategy_cards"] and result["evaluation"]["completeness"] >= 0.9:
                repository.remember(
                    dataset_id=dataset.id,
                    kind="validated_strategy_case",
                    content={
                        "question": payload["question"],
                        "segments": [
                            card["segment_name"] for card in result["strategy_cards"]
                        ],
                        "strategy_cards": result["strategy_cards"],
                    },
                    version="1.1",
                    source="analysis_pipeline",
                )
        except Exception as exc:
            logger.exception("Analysis %s failed", analysis_id)
            repository.fail_analysis(analysis_id, str(exc))


def _summarize_session(repository: Repository, analysis_session, result: dict[str, Any]) -> None:
    """将一次完整分析的关键产出汇总进 Session 摘要（真实数据）。"""
    segments = result.get("segments", []) or []
    insights = result.get("insights", []) or []
    strategies = result.get("strategy_cards", []) or []
    summary_lines = [
        f"数据集：{analysis_session.dataset_name}",
        f"识别人群 {len(segments)} 个，生成洞察 {len(insights)} 条，策略 {len(strategies)} 套。",
    ]
    if segments:
        top = "、".join(item.get("name", "") for item in segments[:4])
        summary_lines.append(f"主要人群：{top}。")
    if result.get("executive_summary"):
        summary_lines.append(result["executive_summary"])
    repository.update_session(
        analysis_session.id,
        summary="\n".join(summary_lines),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.2.0"}


@app.get("/api/v1/meta/agents")
def agent_manifest() -> dict:
    return {
        "architecture": "3+1",
        "agents": [
            {
                "name": "Orchestrator Agent",
                "role": "理解业务问题，动态决定调用哪些 Agent，输出编排计划与委派",
            },
            {
                "name": "Data Agent",
                "role": "字段映射、清洗、特征工程与 KMeans 自动选 K 聚类分群",
            },
            {
                "name": "Insight Agent",
                "role": "证据解释、需求洞察、替代解释与限制",
            },
            {
                "name": "Knowledge Agent",
                "role": "本地知识库 RAG 检索：结合业务问题与人群画像检索营销案例、产品知识与券规则，为策略提供知识依据",
            },
            {
                "name": "Strategy Agent",
                "role": "产品机制、页面方向、slogan 与验证指标",
            },
        ],
        "llm_mode": "enabled" if settings.llm_enabled else "deterministic_fallback",
    }


@app.post(
    "/api/v1/datasets/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> DatasetResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=415, detail="仅支持 CSV、XLSX 和 XLS 文件。")

    maximum = settings.max_upload_mb * 1024 * 1024
    content = await file.read(maximum + 1)
    if len(content) > maximum:
        raise HTTPException(
            status_code=413,
            detail=f"文件不能超过 {settings.max_upload_mb} MB。",
        )

    safe_path = settings.upload_dir / f"{uuid.uuid4()}{suffix}"
    safe_path.write_bytes(content)
    try:
        raw, total_rows = read_dataset_preview(safe_path)
        quality, preview = build_upload_preview(raw, total_rows)
    except Exception as exc:
        safe_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"文件解析失败：{exc}") from exc

    # 数据集唯一识别：同一文件名视为同一数据集，不重复创建，
    # 直接复用既有资产的洞察资产与业务记录（实现「一数据集对应一张左侧卡片」）。
    import hashlib

    dataset_name = Path(file.filename or "dataset").name
    fingerprint = hashlib.sha256(
        f"{dataset_name}:{len(content)}:".encode() + content[: 1 << 20]
    ).hexdigest()
    repository = Repository(session)
    existing = repository.get_dataset_by_name(dataset_name)
    if existing is not None:
        # 复用既有数据集：更新文件与体检结果，保留已沉淀的洞察资产与业务记录。
        existing.file_path = str(safe_path.resolve())
        existing.file_type = suffix.removeprefix(".")
        existing.row_count = total_rows
        existing.quality_json = json.dumps(quality, ensure_ascii=False)
        existing.fingerprint = fingerprint
        session.add(existing)
        session.commit()
        record = existing
    else:
        record = repository.add_dataset(
            name=dataset_name,
            file_path=str(safe_path.resolve()),
            file_type=suffix.removeprefix("."),
            row_count=total_rows,
            quality=quality,
            fingerprint=fingerprint,
        )
    return _dataset_response(record, preview)


@app.post(
    "/api/v1/demo/dataset",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_demo_dataset(session: SessionDep) -> DatasetResponse:
    randomizer = random.Random(42)
    now = datetime.now(UTC).replace(tzinfo=None)
    personas = {
        "travel": [("机票", "旅行"), ("酒店", "旅行"), ("景点门票", "旅行")],
        "tea": [("多肉葡萄", "奶茶"), ("珍珠奶茶", "奶茶"), ("果茶", "茶饮")],
        "coffee": [("美式咖啡", "咖啡"), ("拿铁", "咖啡"), ("冷萃", "咖啡")],
        "home": [("香薰", "家居"), ("影音会员", "会员"), ("居家零食", "居家")],
    }
    rows: list[dict] = []
    order = 0
    for persona_index, (persona, products) in enumerate(personas.items()):
        for user_index in range(18):
            user_id = f"U{persona_index + 1}{user_index + 1:03d}"
            purchases = randomizer.randint(5, 10)
            for _ in range(purchases):
                order += 1
                product, category = randomizer.choice(products)
                if randomizer.random() < 0.18:
                    product, category = randomizer.choice(
                        [item for values in personas.values() for item in values]
                    )
                base_amount = {
                    "travel": 680,
                    "tea": 28,
                    "coffee": 32,
                    "home": 110,
                }[persona]
                rows.append(
                    {
                        "order_id": f"D{order:05d}",
                        "user_id": user_id,
                        "amount": round(max(8, randomizer.gauss(base_amount, base_amount * 0.3)), 2),
                        "category": category,
                        "product": product,
                        "event_time": (
                            now
                            - timedelta(
                                days=randomizer.randint(0, 120),
                                hours=randomizer.randint(0, 23),
                            )
                        ).isoformat(),
                        "status": "paid",
                    }
                )
    frame = pd.DataFrame(rows)
    path = settings.upload_dir / f"demo-{uuid.uuid4()}.csv"
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    quality = build_quality_report(frame)
    _, preview = build_upload_preview(frame, len(frame))
    repository = Repository(session)
    # 同名 demo 数据集复用，不重复创建（保持「一数据集只一张卡片」）
    existing = repository.get_dataset_by_name("demo_customer_transactions.csv")
    if existing is not None:
        existing.file_path = str(path.resolve())
        existing.file_type = "csv"
        existing.row_count = len(frame)
        existing.quality_json = json.dumps(quality, ensure_ascii=False)
        session.add(existing)
        session.commit()
        record = existing
    else:
        record = repository.add_dataset(
            name="demo_customer_transactions.csv",
            file_path=str(path.resolve()),
            file_type="csv",
            row_count=len(frame),
            quality=quality,
        )
    return _dataset_response(record, preview)


@app.get("/api/v1/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str, session: SessionDep) -> DatasetResponse:
    record = Repository(session).get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="数据集不存在。")
    return _dataset_response(record)


@app.get("/api/v1/datasets/{dataset_id}/asset", response_model=DatasetAssetResponse)
def get_dataset_asset(dataset_id: str, session: SessionDep) -> DatasetAssetResponse:
    """读取数据集级分析资产（沉淀的洞察 / 分群 / 消费趋势），供基础分析结果与业务问题复用。"""
    repository = Repository(session)
    record = repository.get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="数据集不存在。")
    cached = repository.get_cache(dataset_id)
    if cached is None:
        return DatasetAssetResponse(
            dataset_id=dataset_id,
            dataset_name=record.name,
            quality=json.loads(record.quality_json),
            has_asset=False,
        )
    try:
        result = json.loads(cached.result_json)
    except (json.JSONDecodeError, TypeError):
        result = {}
    try:
        quality = json.loads(cached.quality_json) or json.loads(record.quality_json)
    except (json.JSONDecodeError, TypeError):
        quality = {}
    return DatasetAssetResponse(
        dataset_id=dataset_id,
        dataset_name=cached.dataset_name or record.name,
        quality=quality,
        segments=result.get("segments", []),
        insights=result.get("insights", []),
        overall_consumption_insight=result.get("overall_consumption_insight", {}),
        income_profile=result.get("income_profile", {}),
        cluster_quality=result.get("cluster_quality", {}),
        segment_method=result.get("segment_method", "category_preference"),
        has_asset=True,
    )


@app.delete("/api/v1/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: str, session: SessionDep) -> None:
    repository = Repository(session)
    record = repository.delete_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="数据集不存在。")
    path = Path(record.file_path).resolve()
    upload_root = settings.upload_dir.resolve()
    if upload_root in path.parents:
        path.unlink(missing_ok=True)


@app.post(
    "/api/v1/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_analysis(
    payload: AnalysisCreate,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> AnalysisResponse:
    repository = Repository(session)
    dataset = repository.get_dataset(payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="数据集不存在。")
    route = OrchestratorAgent.choose_route(payload.question, payload.strategy_goal)
    record = repository.create_analysis(
        dataset_id=payload.dataset_id,
        question=payload.question,
        strategy_goal=payload.strategy_goal,
        brand_tone=payload.brand_tone,
        route=route,
    )
    # 一数据集一分析项目：业务问题统一归属该数据集下的分析项目，不重复创建。
    session = repository.get_session_by_dataset(payload.dataset_id)
    background_tasks.add_task(
        _run_analysis,
        record.id,
        {
            **payload.model_dump(),
            "session_id": session.id if session else "",
            "session_name": session.name if session else "",
        },
    )
    return _analysis_response(record, dataset.name)


@app.get("/api/v1/analyses", response_model=list[AnalysisResponse])
def list_analyses(session: SessionDep, limit: int = 20) -> list[AnalysisResponse]:
    repository = Repository(session)
    responses: list[AnalysisResponse] = []
    for item in repository.list_analyses(limit):
        dataset = repository.get_dataset(item.dataset_id)
        responses.append(_analysis_response(item, dataset.name if dataset else "已删除数据集"))
    return responses


@app.get("/api/v1/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str, session: SessionDep) -> AnalysisResponse:
    repository = Repository(session)
    record = repository.get_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="分析任务不存在。")
    dataset = repository.get_dataset(record.dataset_id)
    return _analysis_response(record, dataset.name if dataset else "已删除数据集")


@app.delete("/api/v1/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(analysis_id: str, session: SessionDep) -> None:
    record = Repository(session).delete_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="分析任务不存在。")


@app.get(
    "/api/v1/analyses/{analysis_id}/events",
    response_model=list[AuditEventResponse],
)
def get_analysis_events(
    analysis_id: str,
    session: SessionDep,
) -> list[AuditEventResponse]:
    repository = Repository(session)
    if repository.get_analysis(analysis_id) is None:
        raise HTTPException(status_code=404, detail="分析任务不存在。")
    return [
        AuditEventResponse(
            agent=event.agent,
            event_type=event.event_type,
            payload=json.loads(event.payload_json),
            created_at=event.created_at,
        )
        for event in repository.list_events(analysis_id)
    ]


# ======================================================================
# Analysis Workspace：分析项目 / 会话历史 / 继续分析
# ======================================================================
def _session_response(record, repository: Repository) -> SessionResponse:
    conversations = repository.list_conversations(record.id)
    # 统计该 session 数据集下历史分析的关键产出数量
    from .database import AnalysisRecord
    from sqlalchemy import select

    analyses = list(
        repository.session.scalars(
            select(AnalysisRecord)
            .where(AnalysisRecord.dataset_id == record.dataset_id)
            .order_by(AnalysisRecord.created_at)
        )
    )
    segment_count = insight_count = strategy_count = 0
    last_question = ""
    for analysis in analyses:
        try:
            result = json.loads(analysis.result_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(result, dict):
            continue
        segment_count = max(segment_count, len(result.get("segments", []) or []))
        insight_count = max(insight_count, len(result.get("insights", []) or []))
        strategy_count = max(strategy_count, len(result.get("strategy_cards", []) or []))
        last_question = analysis.question
    return SessionResponse(
        id=record.id,
        dataset_id=record.dataset_id,
        dataset_name=record.dataset_name,
        name=record.name,
        status=record.status,
        summary=record.summary,
        created_at=record.created_at,
        updated_at=record.updated_at,
        stats=SessionSummary(
            segment_count=segment_count,
            insight_count=insight_count,
            strategy_count=strategy_count,
            conversation_count=len(conversations),
        ),
        question=last_question,
    )


@app.get("/api/v1/sessions", response_model=list[SessionResponse])
def list_sessions(session: SessionDep, limit: int = 50) -> list[SessionResponse]:
    repository = Repository(session)
    return [_session_response(item, repository) for item in repository.list_sessions(limit)]


def _conversation_response(item) -> ConversationResponse:
    """把一条业务记录（conversation）转成前端可直接展示的响应（含完整洞察/策略/轨迹）。"""
    return ConversationResponse(
        id=item.id,
        session_id=item.session_id,
        analysis_id=item.analysis_id,
        question=item.question,
        answer_summary=item.answer_summary,
        insight_result=json.loads(item.insight_json),
        strategy_result=json.loads(item.strategy_json),
        agent_trace=json.loads(item.trace_json),
        created_at=item.created_at,
    )


def _is_empty_conversation(item) -> bool:
    """判断是否为无结果的空壳记录（崩溃/失败遗留：洞察/策略/轨迹全空且无摘要）。
    这类记录对用户无意义，详情接口会过滤掉，避免展示「暂无完整结果」。"""
    return (
        not (item.answer_summary or "").strip()
        and (item.insight_json or "[]").strip() in ("[]", "{}", "")
        and (item.strategy_json or "[]").strip() in ("[]", "{}", "")
        and (item.trace_json or "[]").strip() in ("[]", "{}", "")
    )


@app.get("/api/v1/datasets", response_model=list[DatasetResponse])
def list_datasets(session: SessionDep, limit: int = 100) -> list[DatasetResponse]:
    """左侧导航：按数据集维度列出全部数据集，附带该数据集下的业务记录数。

    同一文件名的历史重复数据集在此聚合为单张卡片（业务记录数累加），
    实现「一数据集 → 多业务问题」的导航结构。
    """
    repository = Repository(session)
    return [
        _dataset_response(
            record,
            record_count=repository.count_conversations_by_name(record.name),
        )
        for record in repository.list_datasets(limit)
    ]


@app.get("/api/v1/datasets/{dataset_id}/detail", response_model=SessionDetailResponse)
def get_dataset_detail(dataset_id: str, session: SessionDep) -> SessionDetailResponse:
    """数据集详情：聚合该数据集下所有分析项目的业务记录，返回统一的可展开结构。

    前端复用 SessionDetailResponse 形状：session 字段为合成的数据集级聚合会话，
    conversations 为该数据集（含同名历史重复数据集）下全部业务记录，
    每条独立保存洞察/策略/轨迹。
    """
    repository = Repository(session)
    record = repository.get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="数据集不存在。")
    # 同名数据集（含历史重复）下的全部分析项目，统一聚合业务记录
    same_name_datasets = repository.find_datasets_by_name(record.name)
    dataset_ids = [ds.id for ds in same_name_datasets] or [dataset_id]
    sessions_ = [
        sess
        for ds_id in dataset_ids
        for sess in repository.list_sessions_by_dataset(ds_id)
    ]
    conversations: list[ConversationResponse] = []
    messages: list[MessageResponse] = []
    for sess in sessions_:
        conversations.extend(
            _conversation_response(item)
            for item in repository.list_conversations(sess.id)
            if not _is_empty_conversation(item)
        )
        messages.extend(
            MessageResponse(
                id=item.id,
                session_id=item.session_id,
                conversation_id=item.conversation_id,
                agent=item.agent,
                event_type=item.event_type,
                payload=json.loads(item.payload_json),
                created_at=item.created_at,
            )
            for item in repository.list_messages(sess.id)
        )
    # 业务记录去重：相同业务问题只保留最新一条，避免重复展示。
    question_map: dict[str, ConversationResponse] = {}
    for conv in conversations:
        key = (conv.question or "").strip()
        if not key:
            continue
        existing = question_map.get(key)
        if existing is None or conv.created_at > existing.created_at:
            question_map[key] = conv
    conversations = sorted(question_map.values(), key=lambda c: c.created_at)
    # 合成数据集级聚合会话（保持 SessionDetailResponse 形状兼容前端）
    # 直接用聚合后的业务记录统计，避免依赖真实 SessionRecord 字段。
    last_question = conversations[-1].question if conversations else ""
    agg_session = SessionResponse(
        id=dataset_id,
        dataset_id=dataset_id,
        dataset_name=record.name,
        name=f"{record.name} 分析项目",
        status="active",
        summary="",
        created_at=record.created_at,
        updated_at=record.created_at,
        stats=SessionSummary(
            segment_count=0,
            insight_count=0,
            strategy_count=0,
            conversation_count=len(conversations),
        ),
        question=last_question,
    )
    return SessionDetailResponse(
        session=agg_session,
        conversations=conversations,
        messages=messages,
    )


@app.get("/api/v1/datasets/{dataset_id}/find-question")
def find_existing_question(
    dataset_id: str, question: str, session: SessionDep
) -> dict:
    """提交业务问题前查重：若该数据集下已存在相同业务问题，返回对应业务记录（可直接跳转复用）。"""
    repository = Repository(session)
    record = repository.get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="数据集不存在。")
    existing = repository.find_conversation_by_question(dataset_id, question)
    if existing is None:
        return {"found": False, "conversation": None}
    return {"found": True, "conversation": _conversation_response(existing)}


@app.get("/api/v1/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(session_id: str, session: SessionDep) -> SessionDetailResponse:
    repository = Repository(session)
    record = repository.get_session(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="分析项目不存在。")
    conversations = [
        _conversation_response(item)
        for item in repository.list_conversations(session_id)
        if not _is_empty_conversation(item)
    ]
    messages = [
        MessageResponse(
            id=item.id,
            session_id=item.session_id,
            conversation_id=item.conversation_id,
            agent=item.agent,
            event_type=item.event_type,
            payload=json.loads(item.payload_json),
            created_at=item.created_at,
        )
        for item in repository.list_messages(session_id)
    ]
    return SessionDetailResponse(
        session=_session_response(record, repository),
        conversations=conversations,
        messages=messages,
    )


@app.delete("/api/v1/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, session: SessionDep) -> None:
    record = Repository(session).delete_session(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="分析项目不存在。")


@app.post(
    "/api/v1/sessions/{session_id}/continue",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def continue_analysis(
    session_id: str,
    payload: ContinueAnalysisCreate,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> AnalysisResponse:
    repository = Repository(session)
    target_session = repository.get_session(session_id)
    if target_session is None:
        raise HTTPException(status_code=404, detail="分析项目不存在。")
    dataset = repository.get_dataset(target_session.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="数据集不存在或已删除。")
    route = OrchestratorAgent.choose_route(payload.question, payload.strategy_goal)
    record = repository.create_analysis(
        dataset_id=target_session.dataset_id,
        question=payload.question,
        strategy_goal=payload.strategy_goal,
        brand_tone=payload.brand_tone,
        route=route,
    )
    background_tasks.add_task(
        _run_analysis,
        record.id,
        {
            "dataset_id": target_session.dataset_id,
            "question": payload.question,
            "strategy_goal": payload.strategy_goal,
            "brand_tone": payload.brand_tone,
            "analysis_window": payload.analysis_window,
            "session_id": session_id,
            "session_name": target_session.name,
        },
    )
    return _analysis_response(record, dataset.name)
