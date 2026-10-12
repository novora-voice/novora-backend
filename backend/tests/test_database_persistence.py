from novora.adapters.database import (
    DatabaseSessionManager,
    SQLAlchemyEvaluationRepository,
    SQLAlchemyScenarioRepository,
    SQLAlchemyTelephonyRepository,
    SQLAlchemyWebhookEventRepository,
)
from novora.core.enums import OverallStatus, RuleStatus, RuleType
from novora.core.models import (
    EvaluationReport,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
    TelephonyCallRecord,
    WebhookEventRecord,
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
        conversation_id="conv_01",
        overall_status=OverallStatus.PASS,
        summary="Persisted report summary",
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
    assert len(fetched.rule_results) == 1
    assert fetched.rule_results[0].rule_name == "Check account id"

    listed = repo.list_by_scenario("scen_db_01")
    assert len(listed) == 1

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
