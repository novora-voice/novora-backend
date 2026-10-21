import json
import base64
import hashlib
import os
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from sqlalchemy import and_, create_engine, inspect, or_, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from novora.adapters.db_models import (
    Base,
    DBEvaluationReport,
    DBApplicationRecord,
    DBConversation,
    DBScenario,
    DBTelephonyCall,
    DBWebhookEvent,
)
from novora.adapters.telephony_repositories import (
    SQLAlchemyTelephonyRepository,
    SQLAlchemyWebhookEventRepository,
)
from novora.core.enums import OverallStatus
from novora.core.models import (
    Conversation,
    EvaluationReport,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
    TelephonyCallRecord,
    WebhookEventRecord,
)
from novora.core.execution_models import (
    BatchEvaluation,
    HttpToolEndpointConfig,
    HttpToolEvaluationResult,
    ProviderConfig,
    TestCase,
    TestRun,
)
from pydantic import BaseModel
from cryptography.fernet import Fernet

RecordT = TypeVar("RecordT", bound=BaseModel)

class DatabaseSessionManager:
    def __init__(self, db_url: str) -> None:
        is_sqlite = db_url.startswith("sqlite")
        engine_options: Dict[str, Any] = {}
        if is_sqlite:
            engine_options["connect_args"] = {"check_same_thread": False}
            if ":memory:" in db_url or db_url == "sqlite://":
                engine_options["poolclass"] = StaticPool
        self.engine = create_engine(
            db_url,
            **engine_options,
        )
        Base.metadata.create_all(bind=self.engine)
        self._ensure_evaluation_agent_columns()
        self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def _ensure_evaluation_agent_columns(self) -> None:
        columns = {
            column["name"]
            for column in inspect(self.engine).get_columns("evaluation_reports")
        }
        with self.engine.begin() as connection:
            if "agent_id" not in columns:
                connection.execute(
                    text("ALTER TABLE evaluation_reports ADD COLUMN agent_id VARCHAR(255)")
                )
            if "agent_name" not in columns:
                connection.execute(
                    text("ALTER TABLE evaluation_reports ADD COLUMN agent_name VARCHAR(255)")
                )
            if "test_run_id" not in columns:
                connection.execute(
                    text("ALTER TABLE evaluation_reports ADD COLUMN test_run_id VARCHAR(64)")
                )
            if "scenario_fingerprint" not in columns:
                connection.execute(
                    text("ALTER TABLE evaluation_reports ADD COLUMN scenario_fingerprint VARCHAR(64)")
                )
            if "expected_rule_ids" not in columns:
                connection.execute(
                    text("ALTER TABLE evaluation_reports ADD COLUMN expected_rule_ids TEXT DEFAULT '[]'")
                )
            if "integrity_issues" not in columns:
                connection.execute(
                    text("ALTER TABLE evaluation_reports ADD COLUMN integrity_issues TEXT DEFAULT '[]'")
                )

    def get_session(self) -> Session:
        return self.session_factory()


@lru_cache(maxsize=4)
def get_database_session_manager(db_url: str) -> DatabaseSessionManager:
    return DatabaseSessionManager(db_url)


class SQLAlchemyConversationRepository:
    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self.sm = session_manager

    def save(self, conversation: Conversation) -> Conversation:
        with self.sm.get_session() as session:
            session.merge(DBConversation(
                id=conversation.id,
                scenario_id=conversation.scenario_id,
                payload=json.dumps(conversation.model_dump(mode="json")),
                created_at=conversation.created_at,
            ))
            session.commit()
        return conversation

    def get(self, conversation_id: str) -> Optional[Conversation]:
        with self.sm.get_session() as session:
            row = session.query(DBConversation).filter(DBConversation.id == conversation_id).first()
            return Conversation.model_validate(json.loads(row.payload)) if row else None

    def list_all(self, limit: int = 50, offset: int = 0) -> List[Conversation]:
        with self.sm.get_session() as session:
            rows = (
                session.query(DBConversation)
                .order_by(DBConversation.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [Conversation.model_validate(json.loads(row.payload)) for row in rows]


class SQLAlchemyRecordRepository(Generic[RecordT]):
    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        record_type: str,
        model_type: Type[RecordT],
    ) -> None:
        self.sm = session_manager
        self.record_type = record_type
        self.model_type = model_type

    def save(self, record: RecordT) -> RecordT:
        data = record.model_dump(mode="json")
        timestamp = data.get("created_at") or data.get("started_at")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        with self.sm.get_session() as session:
            session.merge(DBApplicationRecord(
                id=str(data["id"]),
                record_type=self.record_type,
                scenario_id=data.get("scenario_id"),
                provider_name=data.get("provider_name") or data.get("provider"),
                created_at=timestamp,
                payload=json.dumps(data),
            ))
            session.commit()
        return record

    def get(self, record_id: str) -> Optional[RecordT]:
        with self.sm.get_session() as session:
            row = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == self.record_type,
                    DBApplicationRecord.id == record_id,
                )
                .first()
            )
            return self.model_type.model_validate(json.loads(row.payload)) if row else None

    def list_all(self, limit: int = 50, offset: int = 0) -> List[RecordT]:
        with self.sm.get_session() as session:
            rows = (
                session.query(DBApplicationRecord)
                .filter(DBApplicationRecord.record_type == self.record_type)
                .order_by(DBApplicationRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self.model_type.model_validate(json.loads(row.payload)) for row in rows]

    def list_by_scenario(self, scenario_id: str, limit: int = 50, offset: int = 0) -> List[RecordT]:
        with self.sm.get_session() as session:
            rows = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == self.record_type,
                    DBApplicationRecord.scenario_id == scenario_id,
                )
                .order_by(DBApplicationRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self.model_type.model_validate(json.loads(row.payload)) for row in rows]

    def get_by_provider(self, provider_name: str) -> Optional[RecordT]:
        with self.sm.get_session() as session:
            row = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == self.record_type,
                    DBApplicationRecord.provider_name == provider_name.lower(),
                )
                .order_by(DBApplicationRecord.created_at.desc())
                .first()
            )
            return self.model_type.model_validate(json.loads(row.payload)) if row else None


class SQLAlchemyIntegrationRepository(SQLAlchemyRecordRepository[ProviderConfig]):
    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        super().__init__(session_manager, "integration", ProviderConfig)

    @staticmethod
    def _cipher() -> Fernet:
        secret = os.environ.get(
            "NOVORA_SECRET_ENCRYPTION_KEY",
            os.environ["NOVORA_JWT_SECRET"],
        )
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return Fernet(key)

    def _deserialize(self, row: DBApplicationRecord) -> ProviderConfig:
        data = json.loads(row.payload)
        encrypted_key = data.pop("_encrypted_api_key", None)
        if encrypted_key:
            metadata = data.setdefault("metadata", {})
            metadata["raw_key"] = self._cipher().decrypt(encrypted_key.encode("ascii")).decode("utf-8")
        return ProviderConfig.model_validate(data)

    def save(self, record: ProviderConfig) -> ProviderConfig:
        data = record.model_dump(mode="json")
        api_key = data.get("metadata", {}).pop("raw_key", None)
        if api_key:
            data["_encrypted_api_key"] = self._cipher().encrypt(api_key.encode("utf-8")).decode("ascii")
        timestamp = data.get("created_at")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        with self.sm.get_session() as session:
            session.merge(DBApplicationRecord(
                id=record.id,
                record_type=self.record_type,
                provider_name=record.provider_name.lower(),
                created_at=timestamp,
                payload=json.dumps(data),
            ))
            session.commit()
        return record

    def get(self, record_id: str) -> Optional[ProviderConfig]:
        with self.sm.get_session() as session:
            row = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == self.record_type,
                    DBApplicationRecord.id == record_id,
                )
                .first()
            )
            return self._deserialize(row) if row else None

    def list_all(self, limit: int = 50, offset: int = 0) -> List[ProviderConfig]:
        with self.sm.get_session() as session:
            rows = (
                session.query(DBApplicationRecord)
                .filter(DBApplicationRecord.record_type == self.record_type)
                .order_by(DBApplicationRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self._deserialize(row) for row in rows]

    def get_by_provider(self, provider_name: str) -> Optional[ProviderConfig]:
        with self.sm.get_session() as session:
            row = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == self.record_type,
                    DBApplicationRecord.provider_name == provider_name.lower(),
                )
                .order_by(DBApplicationRecord.created_at.desc())
                .first()
            )
            return self._deserialize(row) if row else None


class SQLAlchemyHttpToolEndpointRepository:
    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self.sm = session_manager

    @staticmethod
    def _cipher() -> Fernet:
        return SQLAlchemyIntegrationRepository._cipher()

    def save(
        self,
        owner_id: str,
        config: HttpToolEndpointConfig,
        bearer_token: Optional[str] = None,
    ) -> HttpToolEndpointConfig:
        data = config.model_dump(mode="json")
        if bearer_token:
            data["_encrypted_api_key"] = self._cipher().encrypt(
                bearer_token.encode("utf-8")
            ).decode("ascii")
            data["has_auth"] = True
        timestamp = config.created_at
        with self.sm.get_session() as session:
            session.merge(DBApplicationRecord(
                id=config.id,
                record_type="http_tool_endpoint",
                scenario_id=owner_id,
                provider_name=config.provider,
                created_at=timestamp,
                payload=json.dumps(data),
            ))
            session.commit()
        return config

    def get(
        self,
        owner_id: str,
        endpoint_id: str,
    ) -> Optional[tuple[HttpToolEndpointConfig, Optional[str]]]:
        with self.sm.get_session() as session:
            row = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == "http_tool_endpoint",
                    DBApplicationRecord.scenario_id == owner_id,
                    DBApplicationRecord.id == endpoint_id,
                )
                .first()
            )
            if not row:
                return None
            data = json.loads(row.payload)
            encrypted_key = data.pop("_encrypted_api_key", None)
            token = (
                self._cipher().decrypt(encrypted_key.encode("ascii")).decode("utf-8")
                if encrypted_key
                else None
            )
            config = HttpToolEndpointConfig.model_validate(data)
            return config, token

    def list_all(self, owner_id: str) -> List[HttpToolEndpointConfig]:
        with self.sm.get_session() as session:
            rows = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == "http_tool_endpoint",
                    DBApplicationRecord.scenario_id == owner_id,
                )
                .order_by(DBApplicationRecord.created_at.desc())
                .all()
            )
            result = []
            for row in rows:
                data = json.loads(row.payload)
                data.pop("_encrypted_api_key", None)
                result.append(HttpToolEndpointConfig.model_validate(data))
            return result

    def delete(self, owner_id: str, endpoint_id: str) -> bool:
        with self.sm.get_session() as session:
            row = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == "http_tool_endpoint",
                    DBApplicationRecord.scenario_id == owner_id,
                    DBApplicationRecord.id == endpoint_id,
                )
                .first()
            )
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True

    def save_result(
        self,
        owner_id: str,
        result: HttpToolEvaluationResult,
    ) -> HttpToolEvaluationResult:
        data = result.model_dump(mode="json")
        with self.sm.get_session() as session:
            session.merge(DBApplicationRecord(
                id=result.id,
                record_type="http_tool_evaluation",
                scenario_id=owner_id,
                provider_name=f"{result.provider}:{result.endpoint_id}",
                created_at=result.created_at,
                payload=json.dumps(data),
            ))
            session.commit()
        return result

    def list_results(
        self,
        owner_id: str,
        endpoint_id: str,
        limit: int = 20,
    ) -> List[HttpToolEvaluationResult]:
        with self.sm.get_session() as session:
            rows = (
                session.query(DBApplicationRecord)
                .filter(
                    DBApplicationRecord.record_type == "http_tool_evaluation",
                    DBApplicationRecord.scenario_id == owner_id,
                    DBApplicationRecord.provider_name.like(f"%:{endpoint_id}"),
                )
                .order_by(DBApplicationRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                HttpToolEvaluationResult.model_validate(json.loads(row.payload))
                for row in rows
            ]


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
                agent_id=report.agent_id,
                agent_name=report.agent_name,
                conversation_id=report.conversation_id,
                test_run_id=report.test_run_id,
                scenario_fingerprint=report.scenario_fingerprint,
                expected_rule_ids=json.dumps(report.expected_rule_ids),
                integrity_issues=json.dumps(report.integrity_issues),
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
                agent_id=row.agent_id,
                agent_name=row.agent_name,
                conversation_id=row.conversation_id,
                test_run_id=row.test_run_id,
                scenario_fingerprint=row.scenario_fingerprint,
                expected_rule_ids=json.loads(row.expected_rule_ids or "[]"),
                integrity_issues=json.loads(row.integrity_issues or "[]"),
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
            rows = (
                session.query(DBEvaluationReport)
                .filter(DBEvaluationReport.scenario_id == scenario_id)
                .order_by(DBEvaluationReport.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            result = []
            for row in rows:
                rules = [RuleResult(**r) for r in json.loads(row.rule_results)]
                result.append(
                    EvaluationReport(
                        id=row.id,
                        scenario_id=row.scenario_id,
                        agent_id=row.agent_id,
                        agent_name=row.agent_name,
                        conversation_id=row.conversation_id,
                        test_run_id=row.test_run_id,
                        scenario_fingerprint=row.scenario_fingerprint,
                        expected_rule_ids=json.loads(row.expected_rule_ids or "[]"),
                        integrity_issues=json.loads(row.integrity_issues or "[]"),
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

    def list_by_agent(
        self,
        agent_id: Optional[str],
        agent_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[EvaluationReport]:
        with self.sm.get_session() as session:
            identity_filters = []
            if agent_id:
                identity_filters.append(DBEvaluationReport.agent_id == agent_id)
            if agent_name:
                # Name fallback is restricted to legacy reports without an agent ID.
                name_filter = DBEvaluationReport.agent_name == agent_name
                identity_filters.append(
                    and_(DBEvaluationReport.agent_id.is_(None), name_filter) if agent_id else name_filter
                )
            if not identity_filters:
                return []
            rows = (
                session.query(DBEvaluationReport)
                .filter(or_(*identity_filters))
                .order_by(DBEvaluationReport.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                EvaluationReport(
                    id=row.id,
                    scenario_id=row.scenario_id,
                    agent_id=row.agent_id,
                    agent_name=row.agent_name,
                    conversation_id=row.conversation_id,
                    test_run_id=row.test_run_id,
                    scenario_fingerprint=row.scenario_fingerprint,
                    expected_rule_ids=json.loads(row.expected_rule_ids or "[]"),
                    integrity_issues=json.loads(row.integrity_issues or "[]"),
                    overall_status=OverallStatus(row.overall_status),
                    summary=row.summary,
                    rule_results=[RuleResult(**item) for item in json.loads(row.rule_results)],
                    total_rules=row.total_rules,
                    passed_rules=row.passed_rules,
                    failed_rules=row.failed_rules,
                    inconclusive_rules=row.inconclusive_rules,
                    created_at=row.created_at,
                )
                for row in rows
            ]
