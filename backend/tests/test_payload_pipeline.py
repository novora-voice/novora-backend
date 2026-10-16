import pytest
from fastapi.testclient import TestClient
from novora.api.main import create_app
from novora.payload.generator import PayloadGenerator
from novora.payload.judge import PayloadJudge
from novora.payload.models import PayloadGenerationRequest, PayloadValidationRequest
from novora.payload.pipeline import PayloadOrchestrator


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_scenario_resolution_and_refund_cap(client):
    """Verify that scen_refund_cap is resolved cleanly from seeded scenarios,
    and nonexistent scenario returns the exact expected error message."""
    # 1. Fetching seeded scenario scen_refund_cap succeeds
    res = client.get("/api/v1/scenarios/scen_refund_cap")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "scen_refund_cap"
    assert "Refund Cap" in data["name"]

    # 2. Querying nonexistent scenario returns clear error
    bad_res = client.post(
        "/api/v1/evaluations",
        json={
            "scenario_id": "nonexistent_scenario_12345",
            "conversation": {"messages": [{"role": "customer", "content": "Hello", "sequence": 0}]},
        },
    )
    assert bad_res.status_code == 404
    assert "Scenario with id 'nonexistent_scenario_12345' not found. Cannot evaluate." in bad_res.json()["detail"]


def test_payload_generator_and_agent_id_validation():
    generator = PayloadGenerator()

    # Vapi payload generation
    vapi_req = PayloadGenerationRequest(
        provider="vapi",
        agent_id="asst_vapi_test_99",
        user_instructions="Ensure customer account is verified before quoting pricing.",
    )
    vapi_payload = generator.generate(vapi_req)
    assert vapi_payload["assistantId"] == "asst_vapi_test_99"
    assert "nova-2" in vapi_payload["transcriber"]["model"]
    assert "Ensure customer account is verified" in vapi_payload["model"]["messages"][0]["content"]

    # Retell payload generation
    retell_req = PayloadGenerationRequest(
        provider="retell",
        agent_id="agent_retell_test_77",
        user_instructions="Verify billing policy adherence.",
    )
    retell_payload = generator.generate(retell_req)
    assert retell_payload["agent_id"] == "agent_retell_test_77"
    assert "11labs-Adrian" in retell_payload["voice_id"]
    assert "Verify billing policy adherence" in retell_payload["general_prompt"]


def test_payload_judge_deterministic_checks():
    judge = PayloadJudge()

    # Reject missing agent ID
    res = judge.evaluate(
        provider="vapi",
        agent_id="",
        payload={"assistantId": "asst_123"},
    )
    assert res.decision == "reject"
    assert "mandatory" in res.feedback.lower()

    # Reject mismatched agent ID
    res2 = judge.evaluate(
        provider="vapi",
        agent_id="asst_expected",
        payload={"assistantId": "asst_different", "name": "Test"},
    )
    assert res2.decision == "revise"
    assert "does not match" in res2.feedback

    # Pass valid payload
    valid_payload = {
        "assistantId": "asst_valid_123",
        "name": "Assistant Valid",
        "model": {"provider": "openai", "model": "gpt-4o"},
    }
    res3 = judge.evaluate(
        provider="vapi",
        agent_id="asst_valid_123",
        payload=valid_payload,
    )
    assert res3.decision == "pass"


def test_payload_pipeline_end_to_end_api(client):
    # Test POST /api/v1/payloads/generate
    payload_req = {
        "provider": "vapi",
        "agent_id": "asst_eval_api_01",
        "user_instructions": "Authenticate customer before applying discounts.",
    }
    gen_res = client.post("/api/v1/payloads/generate", json=payload_req)
    assert gen_res.status_code == 200
    data = gen_res.json()
    assert data["status"] in ["pass", "revised"]
    assert data["final_payload"]["assistantId"] == "asst_eval_api_01"
    assert len(data["history"]) >= 1

    # Test POST /api/v1/payloads/validate
    val_res = client.post(
        "/api/v1/payloads/validate",
        json={
            "provider": "retell",
            "agent_id": "agent_retell_val_01",
            "payload": {
                "agent_id": "agent_retell_val_01",
                "agent_name": "Test Retell Assistant",
                "voice_id": "11labs-Adrian",
            },
        },
    )
    assert val_res.status_code == 200
    assert val_res.json()["decision"] == "pass"

    # Test GET /api/v1/payloads/templates
    tmpl_res = client.get("/api/v1/payloads/templates?provider=vapi")
    assert tmpl_res.status_code == 200
    templates = tmpl_res.json()
    assert len(templates) >= 2
    assert all(t["provider"] == "vapi" for t in templates)
