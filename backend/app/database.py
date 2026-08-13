from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine, delete, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DatasetRecord(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    file_path: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(16))
    row_count: Mapped[int] = mapped_column(default=0)
    quality_json: Mapped[str] = mapped_column(Text, default="{}")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisRecord(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(36), index=True)
    question: Mapped[str] = mapped_column(Text)
    strategy_goal: Mapped[str] = mapped_column(String(255), default="")
    brand_tone: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    route: Mapped[str] = mapped_column(String(32), default="full_strategy")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(String(36), index=True)
    agent: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryRecord(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    kind: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    source: Mapped[str] = mapped_column(String(255), default="system")
    content_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DatasetAnalysisCache(Base):
    """数据集分析资产缓存（Dataset Analysis Cache）。

    一个数据集只执行一次完整用户洞察分析（数据清洗 + 分群 + Insight Agent），
    结果沉淀为该数据集的「客户洞察资产」。之后同一数据集的不同业务问题直接读取缓存，
    跳过数据清洗 / 分群 / Insight Agent，仅基于已有洞察生成策略（Strategy / Knowledge）。
    """

    __tablename__ = "dataset_analysis_cache"

    dataset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_name: Mapped[str] = mapped_column(String(255), default="")
    quality_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SessionRecord(Base):
    """分析项目（Analysis Session）：一次完整业务分析的生命周期容器。

    每次用户上传数据并完成一次完整分析，即创建一个 Session。
    后续所有业务问题、洞察、策略都归属同一个 Session（通过 session_id + dataset_id 关联）。
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_name: Mapped[str] = mapped_column(String(255), default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConversationRecord(Base):
    """会话内的业务问答记录（Conversation History）。

    一次完整分析（analysis）若归属某 session，则在该 session 下创建一条 conversation。
    每条记录自带完整结果（insight_result / strategy_result / agent_trace），
    展开历史记录时直接读取，无需重新跑分析。
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    analysis_id: Mapped[str] = mapped_column(String(36), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer_summary: Mapped[str] = mapped_column(Text, default="")
    # 完整结果（持久化，支持历史记录独立展示）
    insight_json: Mapped[str] = mapped_column(Text, default="[]")
    strategy_json: Mapped[str] = mapped_column(Text, default="[]")
    trace_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageRecord(Base):
    """会话内的单条 Agent 协作记录（Agent Trace History）。

    保存每次分析过程中 Orchestrator / Insight / Strategy / Knowledge Agent 的执行轨迹，
    服务于「Agent Trace 保存」与上下文裁剪。
    """

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    agent: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    # 轻量迁移：为已存在的表补齐新字段（存量库兼容）。
    _migrate_conversations_columns()
    _migrate_datasets_columns()


def _migrate_datasets_columns() -> None:
    from sqlalchemy import inspect

    expected = {"fingerprint": "VARCHAR(64)", "display_name": "VARCHAR(255)"}
    with engine.begin() as conn:
        existing = {col["name"] for col in inspect(engine).get_columns("datasets")}
        for column, ctype in expected.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE datasets ADD COLUMN {column} {ctype} DEFAULT ''"))


def _migrate_conversations_columns() -> None:
    from sqlalchemy import inspect

    expected = {
        "insight_json": "TEXT",
        "strategy_json": "TEXT",
        "trace_json": "TEXT",
    }
    with engine.begin() as conn:
        existing = {col["name"] for col in inspect(engine).get_columns("conversations")}
        for column, ctype in expected.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE conversations ADD COLUMN {column} {ctype} DEFAULT '[]'"))


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def add_dataset(
        self,
        *,
        name: str,
        file_path: str,
        file_type: str,
        row_count: int,
        quality: dict[str, Any],
        fingerprint: str = "",
        display_name: str = "",
    ) -> DatasetRecord:
        record = DatasetRecord(
            id=str(uuid.uuid4()),
            name=name,
            display_name=display_name,
            file_path=file_path,
            file_type=file_type,
            row_count=row_count,
            quality_json=json.dumps(quality, ensure_ascii=False),
            fingerprint=fingerprint,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def get_dataset(self, dataset_id: str) -> DatasetRecord | None:
        return self.session.get(DatasetRecord, dataset_id)

    def get_dataset_by_name(self, name: str) -> DatasetRecord | None:
        """按文件名查找已有数据集（实现数据集唯一识别：同一文件重复上传时复用，不新建）。"""
        from sqlalchemy import select

        statement = (
            select(DatasetRecord)
            .where(DatasetRecord.name == name)
            .order_by(DatasetRecord.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def dataset_fingerprint(self, dataset_id: str) -> str:
        record = self.session.get(DatasetRecord, dataset_id)
        return record.fingerprint if record else ""

    def list_datasets(self, limit: int = 100) -> list[DatasetRecord]:
        """全部数据集列表（左侧导航按数据集维度展示）。

        同一文件名的重复数据集（历史脏数据）在此聚合为单条：返回每个 name 最新的代表记录，
        业务记录数由上层累加。实现「一个数据集只出现一张左侧卡片」。
        """
        from sqlalchemy import select

        statement = select(DatasetRecord).order_by(DatasetRecord.created_at.desc()).limit(limit)
        rows = list(self.session.scalars(statement))
        seen: dict[str, DatasetRecord] = {}
        ordered: list[DatasetRecord] = []
        for row in rows:
            if row.name not in seen:
                seen[row.name] = row
                ordered.append(row)
        return ordered

    def count_conversations_by_dataset(self, dataset_id: str) -> int:
        """统计某数据集下全部业务分析记录数（跨其所有分析项目聚合）。"""
        from sqlalchemy import func, select

        statement = (
            select(func.count(ConversationRecord.id))
            .join(SessionRecord, ConversationRecord.session_id == SessionRecord.id)
            .where(SessionRecord.dataset_id == dataset_id)
        )
        return int(self.session.scalars(statement).first() or 0)

    def count_conversations_by_name(self, name: str) -> int:
        """统计某文件名下全部数据集（含历史重复）的业务记录总数。

        与详情接口一致：排除无结果的空壳记录（洞察/策略/轨迹全空且无摘要），
        避免左侧计数与展开内容不一致。
        """
        from sqlalchemy import func, select

        statement = (
            select(func.count(ConversationRecord.id))
            .join(SessionRecord, ConversationRecord.session_id == SessionRecord.id)
            .join(DatasetRecord, SessionRecord.dataset_id == DatasetRecord.id)
            .where(DatasetRecord.name == name)
            .where(
                ConversationRecord.insight_json.notin_(["[]", "{}", ""])
                | ConversationRecord.strategy_json.notin_(["[]", "{}", ""])
                | ConversationRecord.trace_json.notin_(["[]", "{}", ""])
                | (ConversationRecord.answer_summary != "")
            )
        )
        return int(self.session.scalars(statement).first() or 0)

    def find_datasets_by_name(self, name: str) -> list[DatasetRecord]:
        """返回某文件名下的全部数据集（含历史重复），用于聚合业务记录。"""
        from sqlalchemy import select

        statement = (
            select(DatasetRecord)
            .where(DatasetRecord.name == name)
            .order_by(DatasetRecord.created_at)
        )
        return list(self.session.scalars(statement))

    def list_sessions_by_dataset(self, dataset_id: str) -> list[SessionRecord]:
        """返回某数据集下的全部分析项目（用于聚合业务记录）。"""
        from sqlalchemy import select

        statement = (
            select(SessionRecord)
            .where(SessionRecord.dataset_id == dataset_id)
            .order_by(SessionRecord.created_at)
        )
        return list(self.session.scalars(statement))

    def create_analysis(
        self,
        *,
        dataset_id: str,
        question: str,
        strategy_goal: str,
        brand_tone: str,
        route: str,
    ) -> AnalysisRecord:
        record = AnalysisRecord(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            question=question,
            strategy_goal=strategy_goal,
            brand_tone=brand_tone,
            route=route,
            status="running",
        )
        self.session.add(record)
        self.session.commit()
        return record

    def finish_analysis(self, analysis_id: str, result: dict[str, Any]) -> AnalysisRecord:
        record = self.session.get(AnalysisRecord, analysis_id)
        if record is None:
            raise LookupError(analysis_id)
        record.status = "completed"
        record.result_json = json.dumps(result, ensure_ascii=False)
        record.updated_at = utcnow()
        self.session.commit()
        return record

    def fail_analysis(self, analysis_id: str, message: str) -> None:
        record = self.session.get(AnalysisRecord, analysis_id)
        if record:
            record.status = "failed"
            record.error_message = message
            record.updated_at = utcnow()
            self.session.commit()

    def get_analysis(self, analysis_id: str) -> AnalysisRecord | None:
        return self.session.get(AnalysisRecord, analysis_id)

    def list_analyses(self, limit: int = 20) -> list[AnalysisRecord]:
        statement = select(AnalysisRecord).order_by(AnalysisRecord.created_at.desc()).limit(limit)
        return list(self.session.scalars(statement))

    def delete_analysis(self, analysis_id: str) -> AnalysisRecord | None:
        record = self.session.get(AnalysisRecord, analysis_id)
        if record is None:
            return None
        self.session.execute(
            delete(AuditEventRecord).where(AuditEventRecord.analysis_id == analysis_id)
        )
        self.session.delete(record)
        self.session.commit()
        return record

    def add_event(
        self,
        analysis_id: str,
        agent: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditEventRecord(
                id=str(uuid.uuid4()),
                analysis_id=analysis_id,
                agent=agent,
                event_type=event_type,
                payload_json=json.dumps(payload or {}, ensure_ascii=False),
            )
        )
        self.session.commit()

    def list_events(self, analysis_id: str) -> list[AuditEventRecord]:
        statement = (
            select(AuditEventRecord)
            .where(AuditEventRecord.analysis_id == analysis_id)
            .order_by(AuditEventRecord.created_at)
        )
        return list(self.session.scalars(statement))

    def remember(
        self,
        *,
        dataset_id: str,
        kind: str,
        content: dict[str, Any],
        version: str = "1.0",
        source: str = "system",
    ) -> MemoryRecord:
        record = MemoryRecord(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            kind=kind,
            version=version,
            source=source,
            content_json=json.dumps(content, ensure_ascii=False),
        )
        self.session.add(record)
        self.session.commit()
        return record

    def recall(self, kind: str, limit: int = 5) -> list[dict[str, Any]]:
        statement = (
            select(MemoryRecord)
            .where(MemoryRecord.kind == kind)
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
        )
        return [
            {
                "id": item.id,
                "version": item.version,
                "source": item.source,
                "content": json.loads(item.content_json),
            }
            for item in self.session.scalars(statement)
        ]

    def delete_dataset(self, dataset_id: str) -> DatasetRecord | None:
        record = self.session.get(DatasetRecord, dataset_id)
        if record is None:
            return None
        # 级联删除该数据集下的分析项目（session）及其业务记录与 Agent 轨迹
        session_ids = list(
            self.session.scalars(
                select(SessionRecord.id).where(SessionRecord.dataset_id == dataset_id)
            )
        )
        if session_ids:
            self.session.execute(
                delete(MessageRecord).where(MessageRecord.session_id.in_(session_ids))
            )
            self.session.execute(
                delete(ConversationRecord).where(ConversationRecord.session_id.in_(session_ids))
            )
            self.session.execute(
                delete(SessionRecord).where(SessionRecord.dataset_id == dataset_id)
            )
        analysis_ids = list(
            self.session.scalars(
                select(AnalysisRecord.id).where(AnalysisRecord.dataset_id == dataset_id)
            )
        )
        if analysis_ids:
            self.session.execute(
                delete(AuditEventRecord).where(AuditEventRecord.analysis_id.in_(analysis_ids))
            )
            self.session.execute(
                delete(AnalysisRecord).where(AnalysisRecord.dataset_id == dataset_id)
            )
        self.session.execute(delete(MemoryRecord).where(MemoryRecord.dataset_id == dataset_id))
        self.session.execute(
            delete(DatasetAnalysisCache).where(DatasetAnalysisCache.dataset_id == dataset_id)
        )
        self.session.delete(record)
        self.session.commit()
        return record

    # ------------------------------------------------------------------
    # Dataset Analysis Cache（数据集洞察资产缓存）
    # ------------------------------------------------------------------
    def get_cache(self, dataset_id: str) -> DatasetAnalysisCache | None:
        return self.session.get(DatasetAnalysisCache, dataset_id)

    def upsert_cache(
        self,
        *,
        dataset_id: str,
        dataset_name: str,
        quality: dict[str, Any],
        result: dict[str, Any],
    ) -> DatasetAnalysisCache:
        record = self.session.get(DatasetAnalysisCache, dataset_id)
        result_copy = {
            key: result.get(key)
            for key in (
                "segments",
                "insights",
                "overall_consumption_insight",
                "income_profile",
                "cluster_quality",
                "segment_method",
                "quality",
            )
        }
        evaluation_artifacts = result.get("evaluation_artifacts", {}) or {}
        result_copy["evaluation_artifacts"] = {
            "schema_version": evaluation_artifacts.get("schema_version", "1.0"),
            "data_agent": evaluation_artifacts.get("data_agent", {}),
        }
        if record is None:
            record = DatasetAnalysisCache(dataset_id=dataset_id)
        record.dataset_name = dataset_name
        record.quality_json = json.dumps(quality, ensure_ascii=False)
        record.result_json = json.dumps(result_copy, ensure_ascii=False)
        record.updated_at = utcnow()
        self.session.add(record)
        self.session.commit()
        return record

    # ------------------------------------------------------------------
    # Session（分析项目）
    # ------------------------------------------------------------------
    def create_session(
        self,
        *,
        dataset_id: str,
        dataset_name: str,
        name: str = "",
        summary: str = "",
    ) -> SessionRecord:
        record = SessionRecord(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            name=name or f"{dataset_name} 分析项目",
            status="active",
            summary=summary,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self.session.get(SessionRecord, session_id)

    def get_session_by_dataset(self, dataset_id: str) -> SessionRecord | None:
        """按数据集查找已有分析项目（一数据集一分析项目：业务问题都归属同一项目）。"""
        from sqlalchemy import select

        statement = (
            select(SessionRecord)
            .where(SessionRecord.dataset_id == dataset_id)
            .order_by(SessionRecord.updated_at.desc())
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_sessions(self, limit: int = 50) -> list[SessionRecord]:
        statement = (
            select(SessionRecord)
            .order_by(SessionRecord.updated_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def update_session(
        self,
        session_id: str,
        *,
        summary: str | None = None,
        status: str | None = None,
    ) -> SessionRecord | None:
        record = self.session.get(SessionRecord, session_id)
        if record is None:
            return None
        if summary is not None:
            record.summary = summary
        if status is not None:
            record.status = status
        record.updated_at = utcnow()
        self.session.commit()
        return record

    def delete_session(self, session_id: str) -> SessionRecord | None:
        record = self.session.get(SessionRecord, session_id)
        if record is None:
            return None
        session_id_field = SessionRecord.id
        self.session.execute(
            delete(MessageRecord).where(MessageRecord.session_id == session_id)
        )
        self.session.execute(
            delete(ConversationRecord).where(ConversationRecord.session_id == session_id)
        )
        self.session.delete(record)
        self.session.commit()
        return record

    # ------------------------------------------------------------------
    # Conversation History
    # ------------------------------------------------------------------
    def add_conversation(
        self,
        *,
        session_id: str,
        analysis_id: str,
        question: str,
        answer_summary: str = "",
        insight_result: list[dict[str, Any]] | None = None,
        strategy_result: list[dict[str, Any]] | None = None,
        agent_trace: list[dict[str, Any]] | None = None,
    ) -> ConversationRecord:
        record = ConversationRecord(
            id=str(uuid.uuid4()),
            session_id=session_id,
            analysis_id=analysis_id,
            question=question,
            answer_summary=answer_summary,
            insight_json=json.dumps(insight_result or [], ensure_ascii=False),
            strategy_json=json.dumps(strategy_result or [], ensure_ascii=False),
            trace_json=json.dumps(agent_trace or [], ensure_ascii=False),
        )
        self.session.add(record)
        self.session.commit()
        return record

    def update_conversation_results(
        self,
        conversation_id: str,
        *,
        answer_summary: str = "",
        insight_result: list[dict[str, Any]] | None = None,
        strategy_result: list[dict[str, Any]] | None = None,
        agent_trace: list[dict[str, Any]] | None = None,
    ) -> ConversationRecord | None:
        """分析完成后把完整结果（洞察/策略/轨迹）回填进业务记录，支持历史独立展示。"""
        record = self.session.get(ConversationRecord, conversation_id)
        if record is None:
            return None
        record.answer_summary = answer_summary
        if insight_result is not None:
            record.insight_json = json.dumps(insight_result, ensure_ascii=False)
        if strategy_result is not None:
            record.strategy_json = json.dumps(strategy_result, ensure_ascii=False)
        if agent_trace is not None:
            record.trace_json = json.dumps(agent_trace, ensure_ascii=False)
        self.session.commit()
        return record

    def list_conversations(self, session_id: str) -> list[ConversationRecord]:
        statement = (
            select(ConversationRecord)
            .where(ConversationRecord.session_id == session_id)
            .order_by(ConversationRecord.created_at)
        )
        return list(self.session.scalars(statement))

    def find_conversation_by_question(
        self, dataset_id: str, question: str
    ) -> ConversationRecord | None:
        """跨该数据集所有分析项目查找相同业务问题的业务记录（去除首尾空白后精确匹配），用于提交前查重。"""
        from sqlalchemy import select

        normalized = (question or "").strip()
        if not normalized:
            return None
        sessions = self.list_sessions_by_dataset(dataset_id)
        session_ids = [s.id for s in sessions]
        if not session_ids:
            return None
        statement = (
            select(ConversationRecord)
            .where(ConversationRecord.session_id.in_(session_ids))
            .order_by(ConversationRecord.created_at.desc())
        )
        for item in self.session.scalars(statement):
            if (item.question or "").strip() == normalized:
                return item
        return None

    def update_conversation_answer(
        self, conversation_id: str, *, answer_summary: str = ""
    ) -> ConversationRecord | None:
        record = self.session.get(ConversationRecord, conversation_id)
        if record is None:
            return None
        record.answer_summary = answer_summary
        self.session.commit()
        return record

    # ------------------------------------------------------------------
    # Agent Trace History（Message）
    # ------------------------------------------------------------------
    def add_message(
        self,
        *,
        session_id: str,
        conversation_id: str,
        agent: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            MessageRecord(
                id=str(uuid.uuid4()),
                session_id=session_id,
                conversation_id=conversation_id,
                agent=agent,
                event_type=event_type,
                payload_json=json.dumps(payload or {}, ensure_ascii=False),
            )
        )
        self.session.commit()

    def list_messages(
        self, session_id: str, conversation_id: str | None = None
    ) -> list[MessageRecord]:
        statement = select(MessageRecord).where(MessageRecord.session_id == session_id)
        if conversation_id:
            statement = statement.where(MessageRecord.conversation_id == conversation_id)
        statement = statement.order_by(MessageRecord.created_at)
        return list(self.session.scalars(statement))
