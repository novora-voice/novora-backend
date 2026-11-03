import pytest
from fastapi.testclient import TestClient

from novora.api.main import create_app
from novora.adapters.repositories import InMemoryScenarioRepository
from novora.core.enums import MessageRole, OverallStatus, RuleSeverity, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationScenario,
    RuleConfig,
)
from novora.evaluation.rules.flow_rules import LatencyThresholdRule, WebhookStatusRule
from novora.providers.capabilities import get_provider_manifest, PROVIDER_MANIFESTS
from novora.providers.elevenlabs.adapter import ElevenLabsExecutionAdapter
from novora.providers.assemblyai.adapter import AssemblyAIExecutionAdapter
from novora.providers.vapi.adapter import VapiExecutionAdapter
from novora.providers.retell.adapter import RetellExecutionAdapter
from novora.providers.huggingface import (
    DEFAULT_HF_JUDGE_MODEL,
    DEFAULT_HF_GENERATOR_MODEL,
    DEFAULT_HF_EVALUATOR_MODEL,
    HuggingFaceClient,
    get_hf_judge_model,
    get_hf_generator_model,
    get_hf_evaluator_model,
)


@pytest.fixture
def test_client():
    repo = InMemoryScenarioRepository(seed_defaults=True)
    app = create_app(scenario_repo=repo)
    return TestClient(app)


def test_provider_categories_and_manifest_metadata():
    """Verify Section 3: Voice vs Infrastructure provider categorization and metadata."""
    elevenlabs = get_provider_manifest("elevenlabs")
    assert elevenlabs.provider_group == "voice_provider"
    assert elevenlabs.ghost_caller_implemented is True
    assert "conversation_test" in elevenlabs.supported_execution_modes
    assert "audio" in elevenlabs.supported_input_modes
    assert "user_transcript" in elevenlabs.supported_event_types

    assemblyai = get_provider_manifest("assemblyai")
    assert assemblyai.provider_group == "voice_provider"
    assert assemblyai.requires_audio_input is True
    assert "audio" in assemblyai.supported_input_modes

    vapi = get_provider_manifest("vapi")
    assert vapi.provider_group == "infrastructure"
    assert vapi.supports_payload_generation is True
    assert vapi.supports_webhook_contract_test is True

    retell = get_provider_manifest("retell")
    assert retell.provider_group == "infrastructure"
    assert retell.supports_payload_generation is True
    assert retell.supports_webhook_contract_test is True


def test_provider_adapter_contract_implementation():
    """Verify Section 5: Strict ProviderAdapterContract implementation across all 4 adapters."""
    adapters = [
        ElevenLabsExecutionAdapter(),
        AssemblyAIExecutionAdapter(),
        VapiExecutionAdapter(),
        RetellExecutionAdapter(),
    ]
    for adapter in adapters:
        assert hasattr(adapter, "provider_name")
        assert hasattr(adapter, "get_declared_capabilities")
        assert hasattr(adapter, "validate_agent_id")
        assert hasattr(adapter, "get_supported_execution_modes")

        manifest = adapter.get_declared_capabilities()
        assert manifest is not None
        assert manifest.provider_name == adapter.provider_name

        assert adapter.validate_agent_id("valid_agent_123") is True
        assert adapter.validate_agent_id("") is False

        modes = adapter.get_supported_execution_modes()
        assert len(modes) > 0


def test_hugging_face_models_configuration():
    """Verify Section 15: Configurable DeepSeek and Llama 3.3 model defaults."""
    assert "DeepSeek" in DEFAULT_HF_JUDGE_MODEL or "deepseek" in DEFAULT_HF_JUDGE_MODEL.lower()
    assert "DeepSeek" in DEFAULT_HF_GENERATOR_MODEL or "deepseek" in DEFAULT_HF_GENERATOR_MODEL.lower()
    assert "Llama" in DEFAULT_HF_EVALUATOR_MODEL

    client = HuggingFaceClient()
    assert client.judge_model is not None
    assert client.generator_model is not None
    assert client.evaluator_model is not None


def test_create_scenario_from_custom_json(test_client):
    """Verify Section 9: Custom JSON instructions scenario creation and validation."""
    custom_payload = {
        "name": "Refund Policy Verification Test",
        "goal": "Determine whether the customer qualifies for a refund under $50.",
        "instructions": [
            "Ask for the customer's order number.",
            "Verify the refund policy.",
            "Do not promise a refund before eligibility is confirmed.",
        ],
        "expected_behavior": [
            "Order number collected",
            "Refund policy checked",
        ],
        "prohibited_behavior": [
            "funds have already been sent to your bank account",
        ],
        "rules": [
            {
                "rule_type": "required_information",
                "name": "Order ID Capture",
                "parameters": {"required_fields": ["order_id"]},
            }
        ],
    }

    res = test_client.post("/api/v1/scenarios/from-json", json=custom_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Refund Policy Verification Test"
    assert data["business_goal"] == custom_payload["goal"]
    assert len(data["success_criteria"]) >= 2
    # Rules should contain the custom rule + the prohibited behavior rule
    assert any(r["rule_type"] == "prohibited_phrase" for r in data["rules"])
    assert any(r["rule_type"] == "required_information" for r in data["rules"])


def test_create_scenario_from_invalid_json(test_client):
    """Verify Section 9: Rejection of invalid custom JSON."""
    bad_payload = {
        "goal": "",
        "instructions": [],
    }
    res = test_client.post("/api/v1/scenarios/from-json", json=bad_payload)
    assert res.status_code == 422


def test_add_and_delete_user_defined_deterministic_rule(test_client):
    """Verify Section 16: User-defined deterministic rules lifecycle."""
    # 1. Fetch existing scenario
    scen_res = test_client.get("/api/v1/scenarios/scen_refund_cap")
    assert scen_res.status_code == 200
    initial_rules_count = len(scen_res.json()["rules"])

    # 2. Add custom rule
    new_rule = {
        "id": "rule_user_custom_phrase_test",
        "rule_type": "required_phrase",
        "name": "Agent Greeting Courtesy",
        "description": "Agent must say thank you or hello",
        "parameters": {"phrases": ["thank you", "hello"]},
    }
    add_res = test_client.post("/api/v1/scenarios/scen_refund_cap/rules", json=new_rule)
    assert add_res.status_code == 200
    updated_data = add_res.json()
    assert len(updated_data["rules"]) == initial_rules_count + 1
    assert any(r["id"] == "rule_user_custom_phrase_test" for r in updated_data["rules"])

    # 3. Delete the custom rule
    del_res = test_client.delete("/api/v1/scenarios/scen_refund_cap/rules/rule_user_custom_phrase_test")
    assert del_res.status_code == 200
    after_del = del_res.json()
    assert len(after_del["rules"]) == initial_rules_count
    assert not any(r["id"] == "rule_user_custom_phrase_test" for r in after_del["rules"])


def test_add_user_defined_llm_criterion(test_client):
    """Verify Section 17: User-defined LLM evaluation criteria."""
    criterion = {
        "criterion_id": "llm_crit_empathy_check",
        "name": "Apology and Empathy Verification",
        "description": "Check whether the agent apologized for delayed shipment before offering a resolution.",
        "expected_behavior": "Agent offered sincere apology for the delay.",
        "failure_conditions": "Agent dismissed caller concerns or showed indifference.",
    }
    res = test_client.post("/api/v1/scenarios/scen_refund_cap/llm-criteria", json=criterion)
    assert res.status_code == 200
    data = res.json()
    assert any(r["id"] == "llm_crit_empathy_check" for r in data["rules"])
    assert "Apology and Empathy Verification" in data["success_criteria"]


def test_latency_threshold_rule():
    """Verify Section 16: LatencyThresholdRule evaluation."""
    rule = LatencyThresholdRule()
    config = RuleConfig(
        id="rule_latency",
        rule_type=RuleType.LATENCY_THRESHOLD,
        parameters={"max_latency_ms": 1000.0},
    )
    scenario = EvaluationScenario(name="Test", business_goal="Goal")

    # Pass case
    pass_conv = Conversation(
        messages=[ConversationMessage(id="m1", role=MessageRole.AGENT, content="Hello", sequence=0)],
        metadata={"latencies_ms": [400.0, 600.0]},
    )
    res_pass = rule.evaluate(config, pass_conv, scenario)
    assert res_pass.status == RuleStatus.PASS

    # Fail case
    fail_conv = Conversation(
        messages=[ConversationMessage(id="m1", role=MessageRole.AGENT, content="Hello", sequence=0)],
        metadata={"latencies_ms": [1200.0, 1500.0]},
    )
    res_fail = rule.evaluate(config, fail_conv, scenario)
    assert res_fail.status == RuleStatus.FAIL


def test_webhook_status_rule():
    """Verify Section 16: WebhookStatusRule evaluation."""
    rule = WebhookStatusRule()
    config = RuleConfig(
        id="rule_webhook_status",
        rule_type=RuleType.WEBHOOK_STATUS,
        parameters={"expected_http_status": 200},
    )
    scenario = EvaluationScenario(name="Test", business_goal="Goal")

    # Pass case
    pass_conv = Conversation(messages=[], metadata={"http_status": 200})
    res_pass = rule.evaluate(config, pass_conv, scenario)
    assert res_pass.status == RuleStatus.PASS

    # Fail case
    fail_conv = Conversation(messages=[], metadata={"http_status": 500})
    res_fail = rule.evaluate(config, fail_conv, scenario)
    assert res_fail.status == RuleStatus.FAIL


def test_missing_agent_id_validation_error(test_client):
    """Verify Section 7: Enforce mandatory agent ID before execution."""
    payload = {
        "scenario": {
            "id": "scen_refund_cap",
            "name": "Refund Cap Test",
            "business_goal": "Test",
            "rules": [],
        },
        "agent": {
            "provider_name": "vapi",
            "external_agent_id": "",  # Empty agent ID
            "name": "Test Agent",
        },
    }
    res = test_client.post("/api/v1/test-runs", json=payload)
    assert res.status_code == 400
    data = res.json()
    assert data["detail"]["code"] == "AGENT_ID_REQUIRED"
    assert "agent id is required" in data["detail"]["message"].lower()


def test_scenario_aliases_resolution(test_client):
    """Verify Section 8: Resolution of template IDs without 'not found' errors."""
    for alias in ["customer_support_receptionist", "scen_refund_cap", "scen_template_customer_support"]:
        res = test_client.get(f"/api/v1/scenarios/{alias}")
        assert res.status_code == 200
        assert res.json()["id"] is not None
