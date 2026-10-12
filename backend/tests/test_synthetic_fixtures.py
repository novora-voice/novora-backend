import json
import os
import pytest
from novora.adapters.providers.neutral_ingestion import NeutralIngestionAdapter
from novora.core.enums import OverallStatus
from novora.core.exceptions import PayloadValidationError
from novora.evaluation.engine import EvaluationEngine
from tests.test_delayed_refund_workflow import create_delayed_refund_scenario

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

def load_fixture(name: str):
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def test_successful_customer_service_fixture():
    payload = load_fixture("successful_customer_service.json")
    conv = NeutralIngestionAdapter.ingest(payload)
    assert len(conv.messages) == 6

    engine = EvaluationEngine()
    scenario = create_delayed_refund_scenario()
    report = engine.evaluate(conv, scenario)

    assert report.overall_status == OverallStatus.PASS
    assert report.passed_rules == 6
    assert report.failed_rules == 0

def test_incomplete_interaction_fixture():
    payload = load_fixture("incomplete_interaction.json")
    conv = NeutralIngestionAdapter.ingest(payload)
    assert len(conv.messages) == 3

    engine = EvaluationEngine()
    scenario = create_delayed_refund_scenario()
    report = engine.evaluate(conv, scenario)

    # Incomplete interaction fails required information & unresolved work
    assert report.overall_status == OverallStatus.FAIL
    assert report.failed_rules > 0

def test_malformed_payload_fixture():
    payload = load_fixture("malformed_payload.json")
    with pytest.raises(PayloadValidationError):
        NeutralIngestionAdapter.ingest(payload)

def test_prohibited_claims_fixture():
    payload = load_fixture("prohibited_claims.json")
    conv = NeutralIngestionAdapter.ingest(payload)

    engine = EvaluationEngine()
    scenario = create_delayed_refund_scenario()
    report = engine.evaluate(conv, scenario)

    assert report.overall_status == OverallStatus.FAIL
    # Prohibited claims rule must fail
    assert any(r.rule_name == "Prohibited Instant Refund Guarantees" and r.status == "FAIL" for r in report.rule_results)

def test_duplicated_messages_reindexing():
    payload = load_fixture("duplicated_messages.json")
    conv = NeutralIngestionAdapter.ingest(payload)

    # Sequence numbers must be strictly sequential (0, 1, 2)
    assert [m.sequence for m in conv.messages] == [0, 1, 2]
