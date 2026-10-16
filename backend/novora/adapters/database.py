import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from novora.adapters.db_models import (
    Base,
    DBEvaluationReport,
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
    EvaluationReport,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
    TelephonyCallRecord,
    WebhookEventRecord,
)

class DatabaseSessionManager:
    def __init__(self, db_url: str = "sqlite:///:memory:") -> None:
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
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
