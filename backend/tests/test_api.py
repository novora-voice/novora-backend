from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from novora.api.main import create_app
from novora.core.enums import MessageRole, OverallStatus, RuleStatus, RuleType
from novora.core.models import Conversation, ConversationMessage, EvaluationReport, RuleResult

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_compare_reports_missing_candidate_transcript_as_inconclusive(client):
    app = client.app
    baseline = EvaluationReport(
        id="eval_integrity_base",
        scenario_id="scen_integrity",
        conversation_id="conv_integrity_base",
        scenario_fingerprint="scenario-v1",
        expected_rule_ids=["rule_order"],
        overall_status=OverallStatus.PASS,
        summary="Pass",
        rule_results=[RuleResult(
            rule_id="rule_order",
            rule_name="Order ID",
            rule_type=RuleType.REQUIRED_INFORMATION,
            status=RuleStatus.PASS,
            explanation="Order ID was collected.",
        )],
    )
    candidate = baseline.model_copy(update={
        "id": "eval_integrity_candidate",
        "conversation_id": "conv_missing_candidate",
        "test_run_id": "trun_missing_candidate",
        "overall_status": OverallStatus.FAIL,
        "rule_results": [baseline.rule_results[0].model_copy(update={"status": RuleStatus.FAIL})],
    })
    app.state.evaluation_repository.save(baseline)
    app.state.evaluation_repository.save(candidate)
    app.state.conversation_repository.save(Conversation(
        id=baseline.conversation_id,
        scenario_id=baseline.scenario_id,
        messages=[ConversationMessage(role=MessageRole.CUSTOMER, content="Order ORD-1001", sequence=0)],
    ))

    response = client.post("/api/v1/evaluations/compare", json={
        "baseline_evaluation_id": baseline.id,
        "candidate_evaluation_id": candidate.id,
    })

    assert response.status_code == 200
    result = response.json()
    assert result["comparison_status"] == "INCONCLUSIVE"
    assert result["coverage_complete"] is False
    assert result["regression_detected"] is False
    assert any("Candidate transcript" in issue for issue in result["coverage_issues"])
    assert any("Candidate test run" in issue for issue in result["coverage_issues"])


def test_agent_evaluation_query_returns_latest_for_exact_agent_id(client):
    app = client.app
    older = EvaluationReport(
        id="eval_agent_old",
        scenario_id="scen_agent_old",
        agent_id="provider-agent-1",
        agent_name="Support Agent",
        conversation_id="conv_old",
        overall_status=OverallStatus.PASS,
        summary="Older",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    newest = older.model_copy(update={
        "id": "eval_agent_new",
        "scenario_id": "scen_agent_new",
        "conversation_id": "conv_new",
        "overall_status": OverallStatus.FAIL,
        "summary": "Newest",
        "created_at": datetime(2025, 2, 1, tzinfo=timezone.utc),
    })
    other_agent_same_name = older.model_copy(update={
        "id": "eval_other_agent",
        "agent_id": "provider-agent-2",
        "scenario_id": "scen_other",
        "conversation_id": "conv_other",
        "overall_status": OverallStatus.PASS,
        "created_at": datetime(2025, 3, 1, tzinfo=timezone.utc),
    })
    for report in (older, newest, other_agent_same_name):
        app.state.evaluation_repository.save(report)

    response = client.get("/api/v1/evaluations?agent_id=provider-agent-1&agent_name=Support%20Agent&limit=1")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["eval_agent_new"]

def test_scenario_creation_and_retrieval(client):
    payload = {
        "name": "Refund Policy Scenario",
        "business_goal": "Ensure refund verification compliance",
        "success_criteria": ["Collect order id", "Enforce $100 limit"],
        "rules": [
            {
                "rule_type": "required_information",
                "name": "Check order id",
                "parameters": {"required_fields": ["order_id"]},
            },
            {
                "rule_type": "policy_compliance",
                "name": "Max $100 refund",
                "parameters": {"max_refund_amount": 100.0},
            },
        ],
    }
    create_res = client.post("/api/v1/scenarios", json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert "id" in data
    assert data["name"] == "Refund Policy Scenario"
    scenario_id = data["id"]

    # Retrieve
    get_res = client.get(f"/api/v1/scenarios/{scenario_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == scenario_id

    # Not found
    nf_res = client.get("/api/v1/scenarios/non_existent")
    assert nf_res.status_code == 404

def test_evaluate_conversation_api_flow(client):
    # 1. Create Scenario
    scen_payload = {
        "name": "Agent Prohibited Language",
        "business_goal": "Prevent fee waivers",
        "rules": [
            {
                "rule_type": "prohibited_claims",
                "parameters": {"prohibited_patterns": ["waive fee", "free money"]},
            }
        ],
    }
    scen_res = client.post("/api/v1/scenarios", json=scen_payload)
    scenario_id = scen_res.json()["id"]

    # 2. Evaluate Conversation that violates the rule
    eval_payload = {
        "scenario_id": scenario_id,
        "conversation": {
            "id": "conv_test_1",
            "messages": [
                {
                    "id": "m1",
                    "role": "customer",
                    "content": "Can you waive my fee?",
                    "sequence": 0,
                },
                {
                    "id": "m2",
                    "role": "agent",
                    "content": "Sure, I can waive fee for you.",
                    "sequence": 1,
                },
            ],
        },
    }
    eval_res = client.post("/api/v1/evaluations", json=eval_payload)
    assert eval_res.status_code == 201
    report = eval_res.json()
    assert report["overall_status"] == OverallStatus.FAIL
    assert report["failed_rules"] == 1
    assert len(report["rule_results"][0]["evidence"]) == 1
    eval_id = report["id"]

    # 3. Retrieve evaluation report by ID
    get_report = client.get(f"/api/v1/evaluations/{eval_id}")
    assert get_report.status_code == 200
    assert get_report.json()["id"] == eval_id
    get_conversation = client.get("/api/v1/conversations/conv_test_1")
    assert get_conversation.status_code == 200
    assert get_conversation.json()["id"] == "conv_test_1"

    # 4. List reports by scenario
    list_reports = client.get(f"/api/v1/evaluations?scenario_id={scenario_id}")
    assert list_reports.status_code == 200
    assert len(list_reports.json()) == 1
