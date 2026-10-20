import pytest
from fastapi.testclient import TestClient
from novora.api.routes import test_runs
from novora.api.main import create_app
from novora.core.enums import OverallStatus, TestRunStatus
from novora.core.execution_models import TestRun
from novora.core.models import Conversation, EvaluationReport
from novora.scenarios.templates import create_customer_support_template

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_list_providers_and_capabilities(client):
    res = client.get("/api/v1/providers")
    assert res.status_code == 200
    providers = res.json()
    names = [p["provider_name"] for p in providers]
    assert "elevenlabs" in names
    assert "assemblyai" in names
    assert "vapi" in names
    assert "retell" in names

    # Get specific capabilities
    cap_res = client.get("/api/v1/providers/elevenlabs/capabilities")
    assert cap_res.status_code == 200
    assert "programmatic_ghost_caller" in cap_res.json()["supported_capabilities"]

def test_integrations_and_connectivity(client):
    payload = {
        "provider_name": "elevenlabs",
        "api_key": "sk_test_secret_12345",
    }
    create_res = client.post("/api/v1/integrations", json=payload)
    assert create_res.status_code == 201
    cfg = create_res.json()
    assert "sk_test_secret_12345" not in cfg["api_key_masked"]
    assert cfg["api_key_masked"].startswith("sk_")

    # Connectivity test
    conn_res = client.post(f"/api/v1/integrations/{cfg['id']}/test-connectivity")
    assert conn_res.status_code == 200
    assert conn_res.json()["is_healthy"] is True


def test_vapi_integration_is_saved_and_connection_checks_vapi_api(client, monkeypatch):
    from novora.providers.vapi import adapter as vapi_adapter

    requests = []

    def fake_vapi_assistants(method, url, *, headers, timeout):
        requests.append((method, url, headers, timeout))
        return [{"id": "assistant-1"}]

    monkeypatch.setattr(vapi_adapter, "request_json_value", fake_vapi_assistants)
    first = client.post("/api/v1/integrations", json={
        "provider_name": "vapi",
        "api_key": "vapi_private_test_key_one",
    })
    assert first.status_code == 201
    assert "vapi_private_test_key_one" not in first.text

    second = client.post("/api/v1/integrations", json={
        "provider_name": "vapi",
        "api_key": "vapi_private_test_key_two",
    })
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    saved = client.get("/api/v1/integrations").json()
    assert len([item for item in saved if item["provider_name"] == "vapi"]) == 1
    connection = client.post(f"/api/v1/integrations/{second.json()['id']}/test-connectivity")
    assert connection.status_code == 200
    assert connection.json()["is_healthy"] is True
    assert requests == [(
        "GET",
        "https://api.vapi.ai/assistant?limit=1",
        {"Authorization": "Bearer vapi_private_test_key_two"},
        15,
    )]

def test_scenario_templates_endpoints(client):
    res = client.get("/api/v1/scenarios/templates")
    assert res.status_code == 200
    templates = res.json()
    assert len(templates) >= 3

    # Instantiate from template
    inst_res = client.post(
        "/api/v1/scenarios/from-template",
        json={"template_id": "scen_template_customer_support", "custom_name": "My Custom Support Scenario"},
    )
    assert inst_res.status_code == 201
    assert inst_res.json()["name"] == "My Custom Support Scenario"

def test_test_run_execution_and_retrieval(client, monkeypatch):
    scenario = create_customer_support_template()
    payload = {
        "scenario": scenario.model_dump(mode="json"),
        "agent": {
            "provider_name": "elevenlabs",
            "external_agent_id": "agent_test_42",
            "name": "ElevenLabs Test Agent",
            "permitted_tools": ["check_order"],
        },
        "provider_config": {"simulated": True},
        "enable_llm_judge": True,
    }
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-used")

    def fake_run_pipeline(scenario, test_case, agent, provider_config, enable_llm_judge=True):
        conversation = Conversation(scenario_id=scenario.id)
        report = EvaluationReport(
            scenario_id=scenario.id,
            agent_id=agent.external_agent_id,
            conversation_id=conversation.id,
            overall_status=OverallStatus.PASS,
            summary="Test report persisted",
        )
        run = TestRun(
            scenario_id=scenario.id,
            test_case_id=test_case.id,
            provider=agent.provider_name,
            agent_id=agent.external_agent_id,
            status=TestRunStatus.COMPLETED,
            conversation_id=conversation.id,
            evaluation_id=report.id,
        )
        return run, report, conversation

    monkeypatch.setattr(test_runs.pipeline, "run_pipeline", fake_run_pipeline)
    run_res = client.post("/api/v1/test-runs", json=payload)
    assert run_res.status_code == 201
    data = run_res.json()
    assert "test_run" in data
    assert "evaluation_report" in data
    assert data["test_run"]["status"] == "completed"
    assert data["evaluation_report"]["agent_id"] == "agent_test_42"
    assert data["evaluation_report"]["agent_name"] == "ElevenLabs Test Agent"

    run_id = data["test_run"]["id"]
    get_res = client.get(f"/api/v1/test-runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id
    persisted_reports = client.get(f"/api/v1/evaluations?scenario_id={scenario.id}")
    assert persisted_reports.status_code == 200
    assert any(
        report["id"] == data["evaluation_report"]["id"]
        and report["agent_id"] == "agent_test_42"
        and report["agent_name"] == "ElevenLabs Test Agent"
        for report in persisted_reports.json()
    )

def test_batch_evaluations(client):
    scenario = create_customer_support_template()
    payload = {
        "name": "Nightly Regression Suite",
        "scenario": scenario.model_dump(mode="json"),
        "agent": {
            "provider_name": "elevenlabs",
            "external_agent_id": "agent_batch_01",
            "name": "Batch Test Agent",
            "permitted_tools": ["check_order"],
        },
        "provider_config": {"simulated": True},
    }
    batch_res = client.post("/api/v1/batches", json=payload)
    assert batch_res.status_code == 201
    batch_id = batch_res.json()["id"]

    get_batch = client.get(f"/api/v1/batches/{batch_id}")
    assert get_batch.status_code == 200
    assert get_batch.json()["batch"]["total_runs"] >= 1
