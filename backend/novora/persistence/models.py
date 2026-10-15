from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class DBIntegration(Base):
    __tablename__ = "integrations"

    id = Column(String(64), primary_key=True)
    provider_name = Column(String(32), nullable=False, index=True)
    api_key_masked = Column(String(64), nullable=False)
    api_key_encrypted = Column(Text, nullable=False)
    base_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

class DBAgentConfig(Base):
    __tablename__ = "agents"

    id = Column(String(64), primary_key=True)
    provider_name = Column(String(32), nullable=False, index=True)
    external_agent_id = Column(String(128), nullable=False)
    name = Column(String(128), nullable=False)
    system_prompt = Column(Text, nullable=True)
    permitted_tools = Column(Text, default="[]")  # JSON encoded
    created_at = Column(DateTime, default=utc_now)

class DBTestCase(Base):
    __tablename__ = "test_cases"

    id = Column(String(64), primary_key=True)
    scenario_id = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    scripted_turns = Column(Text, default="[]")  # JSON encoded
    created_at = Column(DateTime, default=utc_now)

class DBTestRun(Base):
    __tablename__ = "test_runs"

    id = Column(String(64), primary_key=True)
    scenario_id = Column(String(64), nullable=False, index=True)
    test_case_id = Column(String(64), nullable=True, index=True)
    provider = Column(String(32), nullable=False, index=True)
    agent_id = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    conversation_id = Column(String(64), nullable=True)
    evaluation_id = Column(String(64), nullable=True)
    events_json = Column(Text, default="[]")
    tool_calls_json = Column(Text, default="[]")
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

class DBBatchEvaluation(Base):
    __tablename__ = "batch_evaluations"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    scenario_id = Column(String(64), nullable=False, index=True)
    test_run_ids = Column(Text, default="[]")  # JSON encoded
    total_runs = Column(Integer, default=0)
    passed_runs = Column(Integer, default=0)
    failed_runs = Column(Integer, default=0)
    inconclusive_runs = Column(Integer, default=0)
    status = Column(String(32), default="pending", index=True)
    created_at = Column(DateTime, default=utc_now)
