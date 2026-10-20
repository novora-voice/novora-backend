from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

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
    agent_id = Column(String(255), nullable=True)
    agent_name = Column(String(255), nullable=True)
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

class DBConversation(Base):
    __tablename__ = "conversations"

    id = Column(String(64), primary_key=True)
    scenario_id = Column(String(64), nullable=True, index=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class DBApplicationRecord(Base):
    __tablename__ = "application_records"

    id = Column(String(128), primary_key=True)
    record_type = Column(String(64), primary_key=True)
    scenario_id = Column(String(64), nullable=True, index=True)
    provider_name = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    payload = Column(Text, nullable=False)
