from datetime import datetime
from novora.adapters.database import (
    DatabaseSessionManager,
    SQLAlchemyConversationRepository,
    SQLAlchemyEvaluationRepository,
    SQLAlchemyIntegrationRepository,
    SQLAlchemyRecordRepository,
    SQLAlchemyScenarioRepository,
    SQLAlchemyTelephonyRepository,
    SQLAlchemyWebhookEventRepository,
)
from novora.adapters.db_models import DBApplicationRecord
from sqlalchemy import create_engine, inspect, text
from novora.core.enums import OverallStatus, RuleStatus, RuleType
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
    EvaluationJobState,
    ProviderConfig,
    ScriptedTurn,
    TestCase,
)

def test_sqlalchemy_scenario_repository():
    sm = DatabaseSessionManager("sqlite:///:memory:")
    repo = SQLAlchemyScenarioRepository(sm)

    scen = EvaluationScenario(
        id="scen_db_01",
        name="Database Persisted Scenario",
        business_goal="Ensure SQL persistence works reliably",
        success_criteria=["Criterion 1"],
        rules=[
            RuleConfig(
                rule_type=RuleType.REQUIRED_INFORMATION,
                name="Check account id",
                parameters={"required_fields": ["account_id"]},
            )
        ],
    )
    repo.save(scen)

    fetched = repo.get("scen_db_01")
    assert fetched is not None
    assert fetched.name == "Database Persisted Scenario"
    assert len(fetched.rules) == 1
    assert fetched.rules[0].name == "Check account id"

def test_sqlalchemy_evaluation_repository():
    sm = DatabaseSessionManager("sqlite:///:memory:")
    repo = SQLAlchemyEvaluationRepository(sm)

    report = EvaluationReport(
        id="rep_db_01",
        scenario_id="scen_db_01",
        agent_id="agent_db_01",
        agent_name="Persisted Agent",
        conversation_id="conv_01",
        test_run_id="trun_01",
        scenario_fingerprint="scenario-fingerprint-v1",
        expected_rule_ids=["r1", "judge_tone"],
        integrity_issues=["Transcript was unavailable during the original run."],
        overall_status=OverallStatus.PASS,
        summary="Persisted report summary",
        created_at=datetime(2024, 1, 1),
        rule_results=[
            RuleResult(
                rule_id="r1",
                rule_name="Check account id",
                rule_type=RuleType.REQUIRED_INFORMATION,
                status=RuleStatus.PASS,
                explanation="Found account_id",
            )
        ],
    )
    repo.save(report)

    fetched = repo.get("rep_db_01")
    assert fetched is not None
    assert fetched.overall_status == OverallStatus.PASS
    assert fetched.agent_id == "agent_db_01"
    assert fetched.agent_name == "Persisted Agent"
    assert fetched.test_run_id == "trun_01"
    assert fetched.scenario_fingerprint == "scenario-fingerprint-v1"
    assert fetched.expected_rule_ids == ["r1", "judge_tone"]
    assert fetched.integrity_issues == ["Transcript was unavailable during the original run."]
    assert len(fetched.rule_results) == 1
    assert fetched.rule_results[0].rule_name == "Check account id"

    repo.save(EvaluationReport(
        id="rep_db_02",
        scenario_id="scen_db_01",
        agent_id="agent_db_01",
        agent_name="Persisted Agent",
        conversation_id="conv_02",
        overall_status=OverallStatus.PASS,
        summary="Newer report",
        created_at=datetime(2024, 1, 2),
    ))
    listed = repo.list_by_scenario("scen_db_01")
    assert [item.id for item in listed] == ["rep_db_02", "rep_db_01"]
    assert listed[0].agent_id == "agent_db_01"
    assert listed[0].agent_name == "Persisted Agent"
    assert repo.list_by_agent("agent_db_01", limit=1)[0].id == "rep_db_02"

def test_database_manager_adds_agent_columns_to_existing_evaluation_table(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{db_path}")
    with legacy_engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE evaluation_reports (
                id VARCHAR(64) PRIMARY KEY,
                scenario_id VARCHAR(64) NOT NULL,
                conversation_id VARCHAR(64) NOT NULL,
                overall_status VARCHAR(32) NOT NULL,
                summary TEXT NOT NULL,
                rule_results TEXT,
                total_rules INTEGER,
                passed_rules INTEGER,
                failed_rules INTEGER,
                inconclusive_rules INTEGER,
                created_at DATETIME
            )
        """))
    legacy_engine.dispose()

    manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    column_names = {
        column["name"]
        for column in inspect(manager.engine).get_columns("evaluation_reports")
    }
    assert {"agent_id", "agent_name", "test_run_id", "scenario_fingerprint", "expected_rule_ids", "integrity_issues"} <= column_names

def test_sqlalchemy_telephony_and_webhook_repositories():
    sm = DatabaseSessionManager("sqlite:///:memory:")
    tel_repo = SQLAlchemyTelephonyRepository(sm)
    wh_repo = SQLAlchemyWebhookEventRepository(sm)

    # Telephony
    call = TelephonyCallRecord(
        call_sid="CA_db_test_01",
        from_number="+15550001",
        to_number="+15550002",
        call_status="completed",
        duration_seconds=42,
    )
    tel_repo.save(call)
    fetched_call = tel_repo.get("CA_db_test_01")
    assert fetched_call is not None
    assert fetched_call.duration_seconds == 42

    # Webhook Idempotency
    evt = WebhookEventRecord(
        provider="elevenlabs",
        event_id="evt_unique_100",
        signature_verified=True,
        payload={"conv_id": "c1"},
    )
    assert wh_repo.is_processed("elevenlabs", "evt_unique_100") is False
    wh_repo.record_event(evt)
    assert wh_repo.is_processed("elevenlabs", "evt_unique_100") is True


def test_sqlalchemy_persists_conversations_execution_records_and_encrypted_integrations():
    sm = DatabaseSessionManager("sqlite:///:memory:")
    conversations = SQLAlchemyConversationRepository(sm)
    cases = SQLAlchemyRecordRepository(sm, "test_case", TestCase)
    jobs = SQLAlchemyRecordRepository(sm, "evaluation_job", EvaluationJobState)
    integrations = SQLAlchemyIntegrationRepository(sm)
    conversation = Conversation(scenario_id="scen_persisted")
    test_case = TestCase(
        scenario_id="scen_persisted",
        name="Saved scripted case",
        scripted_turns=[ScriptedTurn(sequence=1, user_message="Please check my order.")],
    )
    integration = ProviderConfig(
        provider_name="vapi",
        api_key_masked="sk_...1234",
        metadata={"raw_key": "provider-secret-value"},
    )

    conversations.save(conversation)
    cases.save(test_case)
    integrations.save(integration)
    jobs.save(EvaluationJobState(
        id="evaljob_persisted",
        status="completed",
        attempt=1,
        request_data={"scenario": {"id": "scen_persisted"}},
    ))

    assert conversations.get(conversation.id) == conversation
    assert cases.get(test_case.id) == test_case
    assert integrations.get(integration.id).metadata["raw_key"] == "provider-secret-value"
    assert integrations.get_by_provider("VAPI").id == integration.id
    assert jobs.get("evaljob_persisted").status == "completed"
    with sm.get_session() as session:
        row = (
            session.query(DBApplicationRecord)
            .filter(DBApplicationRecord.record_type == "integration")
            .one()
        )
        assert "provider-secret-value" not in row.payload
