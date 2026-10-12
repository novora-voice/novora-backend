import hashlib
import hmac
import time
import pytest
from fastapi.testclient import TestClient
from novora.api.main import create_app
from novora.core.enums import OverallStatus, RuleType

@pytest.fixture
def client():
    app = create_app(elevenlabs_secret="test_secret_key", twilio_auth_token="test_twilio_token")
    return TestClient(app)

def test_api_import_transcript_endpoint(client):
    res = client.post(
        "/api/v1/conversations/import-transcript",
        json={
            "text": "Customer: I need a refund.\nAgent: I can help with that.",
            "scenario_id": "scen_1",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "messages" in data
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "customer"
    assert data["messages"][1]["role"] == "agent"

def test_api_elevenlabs_webhook_with_signature_and_idempotency(client):
    secret = "test_secret_key"
    payload = {
        "conversation_id": "conv_api_el_01",
        "transcript": [
            {"role": "user", "message": "My order #1234 is late."},
            {"role": "agent", "message": "Let me check that."},
        ],
    }
    raw_body = client.app.router.lifespan_context  # just get json bytes
    import json
    body_bytes = json.dumps(payload).encode("utf-8")
    ts = str(int(time.time()))
    payload_to_sign = f"{ts}.".encode("utf-8") + body_bytes
    sig_hex = hmac.new(secret.encode("utf-8"), payload_to_sign, hashlib.sha256).hexdigest()
    sig_header = f"t={ts},v1={sig_hex}"

    # First request -> 200 processed
    res = client.post(
        "/api/v1/webhooks/elevenlabs",
        content=body_bytes,
        headers={"elevenlabs-signature": sig_header, "Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert res.json()["conversation_id"] == "conv_api_el_01"

    # Second request with same event ID -> 200 already_processed
    res_dup = client.post(
        "/api/v1/webhooks/elevenlabs",
        content=body_bytes,
        headers={"elevenlabs-signature": sig_header, "Content-Type": "application/json"},
    )
    assert res_dup.status_code == 200
    assert res_dup.json()["status"] == "already_processed"

def test_api_twilio_webhook_endpoint(client):
    payload = {
        "CallSid": "CA_api_call_123",
        "From": "+15551111",
        "To": "+15552222",
        "CallStatus": "completed",
        "Duration": "85",
    }
    res = client.post("/api/v1/webhooks/twilio", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["call_sid"] == "CA_api_call_123"
    assert data["duration_seconds"] == 85

    # Check listed in telephony endpoint
    list_res = client.get("/api/v1/telephony/calls")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

def test_api_evaluation_history_and_compare(client):
    # 1. Create Scenario
    scen_res = client.post(
        "/api/v1/scenarios",
        json={
            "name": "Refund Comparison Test",
            "business_goal": "Check $50 max limit",
            "rules": [
                {
                    "rule_type": "policy_compliance",
                    "name": "Limit $50",
                    "parameters": {"max_refund_amount": 50.0},
                }
            ],
        },
    )
    scen_id = scen_res.json()["id"]

    # 2. Run Baseline Evaluation ($25 <= $50 -> PASS)
    eval1 = client.post(
        "/api/v1/evaluations",
        json={
            "scenario_id": scen_id,
            "conversation": {
                "id": "c1",
                "messages": [{"id": "m1", "role": "agent", "sequence": 0, "content": "I offer $25."}],
            },
        },
    )
    eval1_id = eval1.json()["id"]
    assert eval1.json()["overall_status"] == OverallStatus.PASS

    # 3. Run Candidate Evaluation ($100 > $50 -> FAIL)
    eval2 = client.post(
        "/api/v1/evaluations",
        json={
            "scenario_id": scen_id,
            "conversation": {
                "id": "c2",
                "messages": [{"id": "m2", "role": "agent", "sequence": 0, "content": "I offer $100."}],
            },
        },
    )
    eval2_id = eval2.json()["id"]
    assert eval2.json()["overall_status"] == OverallStatus.FAIL

    # 4. Check scenario history
    hist_res = client.get(f"/api/v1/scenarios/{scen_id}/history")
    assert hist_res.status_code == 200
    assert len(hist_res.json()) == 2

    # 5. Compare runs (regression detection!)
    cmp_res = client.post(
        "/api/v1/evaluations/compare",
        json={"baseline_evaluation_id": eval1_id, "candidate_evaluation_id": eval2_id},
    )
    assert cmp_res.status_code == 200
    diff = cmp_res.json()
    assert diff["regression_detected"] is True
    assert diff["net_status_change"] == "regressed"
    assert diff["rule_comparisons"][0]["change"] == "regressed"
