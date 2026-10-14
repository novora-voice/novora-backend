import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from novora.core.enums import OverallStatus, RuleStatus, RuleType
from novora.core.models import (
    EvaluationReport,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
    TelephonyCallRecord,
    WebhookEventRecord,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")

Base = declarative_base()

class DBScenario(Base):
    __tablename__ = "scenarios"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    business_goal = Column(Text, nullable=False)
    success_criteria = Column(Text, default="[]")  # JSON encoded
    rules = Column(Text, default="[]")             # JSON encoded
    created_at = Column(DateTime, default=datetime.utcnow)

class DBEvaluationReport(Base):
    __tablename__ = "evaluation_reports"

    id = Column(String(64), primary_key=True)
    scenario_id = Column(String(64), nullable=False, index=True)
    conversation_id = Column(String(64), nullable=False, index=True)
    overall_status = Column(String(32), nullable=False)
    summary = Column(Text, nullable=False)
    rule_results = Column(Text, default="[]")      # JSON encoded
    total_rules = Column(Integer, default=0)
    passed_rules = Column(Integer, default=0)
    failed_rules = Column(Integer, default=0)
    inconclusive_rules = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class DBTelephonyCall(Base):
    __tablename__ = "telephony_calls"

    id = Column(String(64), primary_key=True)
    provider = Column(String(32), default="twilio")
    call_sid = Column(String(64), unique=True, nullable=False, index=True)
    from_number = Column(String(64), nullable=True)
    to_number = Column(String(64), nullable=True)
    call_status = Column(String(32), nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    recording_sid = Column(String(64), nullable=True)
    recording_url = Column(Text, nullable=True)
    call_metadata = Column(Text, default="{}")     # JSON encoded
    created_at = Column(DateTime, default=datetime.utcnow)

class DBWebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(String(64), primary_key=True)
    provider = Column(String(32), nullable=False, index=True)
    event_id = Column(String(128), nullable=False, index=True)
    signature_verified = Column(Boolean, default=False)
    payload = Column(Text, default="{}")           # JSON encoded
    status = Column(String(32), default="processed")
    created_at = Column(DateTime, default=datetime.utcnow)

class DatabaseSessionManager:
    def __init__(self, db_url: Optional[str] = None) -> None:
        db_url = db_url or os.getenv("NOVORA_DATABASE_URL", "sqlite:///:memory:")
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False} if db_url.startswith("sqlite:") else {},
            pool_pre_ping=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self) -> Session:
        return self.session_factory()

class SQLAlchemyScenarioRepository:
    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self.sm = session_manager

    def save(self, scenario: EvaluationScenario) -> EvaluationScenario:
        with self.sm.get_session() as session:
            db_item = DBScenario(
                id=scenario.id,
                name=scenario.name,
                business_goal=scenario.business_goal,
                success_criteria=json.dumps(scenario.success_criteria),
                rules=json.dumps([r.model_dump() for r in scenario.rules]),
                created_at=scenario.created_at,
            )
            session.merge(db_item)
            session.commit()
        return scenario

    def get(self, scenario_id: str) -> Optional[EvaluationScenario]:
        with self.sm.get_session() as session:
            db_item = session.query(DBScenario).filter(DBScenario.id == scenario_id).first()
            if not db_item:
                return None
            rules_data = json.loads(db_item.rules)
            return EvaluationScenario(
                id=db_item.id,
                name=db_item.name,
                business_goal=db_item.business_goal,
                success_criteria=json.loads(db_item.success_criteria),
                rules=[RuleConfig(**r) for r in rules_data],
                created_at=db_item.created_at,
            )

    def list_all(self, limit: int = 50, offset: int = 0) -> List[EvaluationScenario]:
        with self.sm.get_session() as session:
            rows = session.query(DBScenario).offset(offset).limit(limit).all()
            result = []
            for r in rows:
                rules_data = json.loads(r.rules)
                result.append(
                    EvaluationScenario(
                        id=r.id,
                        name=r.name,
                        business_goal=r.business_goal,
                        success_criteria=json.loads(r.success_criteria),
                        rules=[RuleConfig(**x) for x in rules_data],
                        created_at=r.created_at,
                    )
                )
            return result

class SQLAlchemyEvaluationRepository:
    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self.sm = session_manager

    def save(self, report: EvaluationReport) -> EvaluationReport:
        with self.sm.get_session() as session:
            db_report = DBEvaluationReport(
                id=report.id,
                scenario_id=report.scenario_id,
                conversation_id=report.conversation_id,
                overall_status=report.overall_status.value,
                summary=report.summary,
                rule_results=json.dumps([r.model_dump() for r in report.rule_results]),
                total_rules=report.total_rules,
                passed_rules=report.passed_rules,
                failed_rules=report.failed_rules,
                inconclusive_rules=report.inconclusive_rules,
                created_at=report.created_at,
            )
            session.merge(db_report)
            session.commit()
        return report

    def get(self, report_id: str) -> Optional[EvaluationReport]:
        with self.sm.get_session() as session:
            row = session.query(DBEvaluationReport).filter(DBEvaluationReport.id == report_id).first()
            if not row:
                return None
            rules = [RuleResult(**r) for r in json.loads(row.rule_results)]
            return EvaluationReport(
                id=row.id,
                scenario_id=row.scenario_id,
                conversation_id=row.conversation_id,
                overall_status=OverallStatus(row.overall_status),
                summary=row.summary,
                rule_results=rules,
                total_rules=row.total_rules,
                passed_rules=row.passed_rules,
                failed_rules=row.failed_rules,
                inconclusive_rules=row.inconclusive_rules,
                created_at=row.created_at,
            )

    def list_by_scenario(self, scenario_id: str, limit: int = 50, offset: int = 0) -> List[EvaluationReport]:
        with self.sm.get_session() as session:
            rows = session.query(DBEvaluationReport).filter(DBEvaluationReport.scenario_id == scenario_id).offset(offset).limit(limit).all()
            result = []
            for row in rows:
                rules = [RuleResult(**r) for r in json.loads(row.rule_results)]
                result.append(
                    EvaluationReport(
                        id=row.id,
                        scenario_id=row.scenario_id,
                        conversation_id=row.conversation_id,
                        overall_status=OverallStatus(row.overall_status),
                        summary=row.summary,
                        rule_results=rules,
                        total_rules=row.total_rules,
                        passed_rules=row.passed_rules,
                        failed_rules=row.failed_rules,
                        inconclusive_rules=row.inconclusive_rules,
                        created_at=row.created_at,
                    )
                )
            return result

class SQLAlchemyTelephonyRepository:
    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self.sm = session_manager

    def save(self, record: TelephonyCallRecord) -> TelephonyCallRecord:
        with self.sm.get_session() as session:
            db_call = DBTelephonyCall(
                id=record.id,
                provider=record.provider,
                call_sid=record.call_sid,
                from_number=record.from_number,
                to_number=record.to_number,
                call_status=record.call_status,
                duration_seconds=record.duration_seconds,
                recording_sid=record.recording_sid,
                recording_url=record.recording_url,
                call_metadata=json.dumps(record.metadata),
                created_at=record.created_at,
            )
            session.merge(db_call)
            session.commit()
        return record

    def get(self, call_sid: str) -> Optional[TelephonyCallRecord]:
        with self.sm.get_session() as session:
            row = session.query(DBTelephonyCall).filter(DBTelephonyCall.call_sid == call_sid).first()
            if not row:
                return None
            return TelephonyCallRecord(
                id=row.id,
                provider=row.provider,
                call_sid=row.call_sid,
                from_number=row.from_number,
                to_number=row.to_number,
                call_status=row.call_status,
                duration_seconds=row.duration_seconds,
                recording_sid=row.recording_sid,
                recording_url=row.recording_url,
                metadata=json.loads(row.call_metadata),
                created_at=row.created_at,
            )

    def list_all(self, limit: int = 50, offset: int = 0) -> List[TelephonyCallRecord]:
        with self.sm.get_session() as session:
            rows = session.query(DBTelephonyCall).offset(offset).limit(limit).all()
            return [
                TelephonyCallRecord(
                    id=r.id,
                    provider=r.provider,
                    call_sid=r.call_sid,
                    from_number=r.from_number,
                    to_number=r.to_number,
                    call_status=r.call_status,
                    duration_seconds=r.duration_seconds,
                    recording_sid=r.recording_sid,
                    recording_url=r.recording_url,
                    metadata=json.loads(r.call_metadata),
                    created_at=r.created_at,
                )
                for r in rows
            ]

class SQLAlchemyWebhookEventRepository:
    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self.sm = session_manager

    def record_event(self, event: WebhookEventRecord) -> WebhookEventRecord:
        with self.sm.get_session() as session:
            db_evt = DBWebhookEvent(
                id=event.id,
                provider=event.provider,
                event_id=event.event_id,
                signature_verified=event.signature_verified,
                payload=json.dumps(event.payload),
                status=event.status,
                created_at=event.created_at,
            )
            session.merge(db_evt)
            session.commit()
        return event

    def is_processed(self, provider: str, event_id: str) -> bool:
        with self.sm.get_session() as session:
            count = session.query(DBWebhookEvent).filter(
                DBWebhookEvent.provider == provider,
                DBWebhookEvent.event_id == event_id,
            ).count()
            return count > 0

    def get(self, event_id: str) -> Optional[WebhookEventRecord]:
        with self.sm.get_session() as session:
            row = session.query(DBWebhookEvent).filter(DBWebhookEvent.event_id == event_id).first()
            if not row:
                return None
            return WebhookEventRecord(
                id=row.id,
                provider=row.provider,
                event_id=row.event_id,
                signature_verified=row.signature_verified,
                payload=json.loads(row.payload),
                status=row.status,
                created_at=row.created_at,
            )
