import pytest
from fastapi.testclient import TestClient
from novora.api.main import create_app
from novora.core.enums import MessageRole, OverallStatus, RuleType

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

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

    # 4. List reports by scenario
    list_reports = client.get(f"/api/v1/evaluations?scenario_id={scenario_id}")
    assert list_reports.status_code == 200
    assert len(list_reports.json()) == 1
