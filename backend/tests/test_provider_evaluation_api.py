import pytest
from fastapi.testclient import TestClient
from novora.api.main import create_app
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

def test_test_run_execution_and_retrieval(client):
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
    run_res = client.post("/api/v1/test-runs", json=payload)
    assert run_res.status_code == 201
    data = run_res.json()
    assert "test_run" in data
    assert "evaluation_report" in data
    assert data["test_run"]["status"] == "completed"

    run_id = data["test_run"]["id"]
    get_res = client.get(f"/api/v1/test-runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id

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
