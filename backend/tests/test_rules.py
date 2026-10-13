import pytest
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationScenario,
    RuleConfig,
)
from novora.evaluation.rules.policy_compliance import PolicyComplianceRule
from novora.evaluation.rules.prohibited_claims import ProhibitedClaimsRule
from novora.evaluation.rules.required_info import RequiredInfoRule
from novora.evaluation.rules.required_steps import RequiredStepsRule
from novora.evaluation.rules.unresolved_work import UnresolvedWorkRule
from novora.evaluation.rules.unsupported_completion import UnsupportedCompletionClaimsRule

@pytest.fixture
def empty_scenario():
    return EvaluationScenario(
        id="scen_test",
        name="Test Scenario",
        business_goal="Test",
    )

def test_required_info_passes_when_all_fields_present(empty_scenario):
    rule = RequiredInfoRule()
    cfg = RuleConfig(
        rule_type=RuleType.REQUIRED_INFORMATION,
        parameters={"required_fields": ["order_id", "email"]},
    )
    conv = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.CUSTOMER, content="My order is #48291 and email is alice@example.com", sequence=0),
            ConversationMessage(role=MessageRole.AGENT, content="Thank you for confirming.", sequence=1),
        ]
    )
    res = rule.evaluate(cfg, conv, empty_scenario)
    assert res.status == RuleStatus.PASS
    assert len(res.evidence) == 2
    assert "order_id" in res.details["collected_fields"]

def test_required_info_fails_when_field_missing(empty_scenario):
    rule = RequiredInfoRule()
    cfg = RuleConfig(
        rule_type=RuleType.REQUIRED_INFORMATION,
        parameters={"required_fields": ["order_id", "phone"]},
    )
    conv = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.CUSTOMER, content="My order is #48291", sequence=0),
        ]
    )
    res = rule.evaluate(cfg, conv, empty_scenario)
    assert res.status == RuleStatus.FAIL
    assert "phone" in res.details["missing_fields"]

def test_prohibited_claims_flags_unauthorized_phrases(empty_scenario):
    rule = ProhibitedClaimsRule()
    cfg = RuleConfig(
        rule_type=RuleType.PROHIBITED_CLAIMS,
        parameters={"prohibited_patterns": [r"guarantee 100% refund", r"waive the fee"]},
    )
    # Agent utters prohibited phrase
    conv_violation = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.AGENT, content="Don't worry, I can guarantee 100% refund right away.", sequence=0),
        ]
    )
    res = rule.evaluate(cfg, conv_violation, empty_scenario)
    assert res.status == RuleStatus.FAIL
    assert len(res.evidence) == 1
    assert res.evidence[0].char_start is not None

    # Agent says clean phrase
    conv_clean = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.AGENT, content="I will review your request under our 30-day policy.", sequence=0),
        ]
    )
    assert rule.evaluate(cfg, conv_clean, empty_scenario).status == RuleStatus.PASS

def test_unsupported_completion_flags_claim_without_backend_record(empty_scenario):
    rule = UnsupportedCompletionClaimsRule()
    cfg = RuleConfig(
        rule_type=RuleType.UNSUPPORTED_COMPLETION,
        parameters={"action_type": "refund"},
    )
    # Agent claims refund was processed, but NO trusted_action_records exist
    conv = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.AGENT, content="I have processed your refund now.", sequence=0),
        ],
        trusted_action_records=[],
    )
    res = rule.evaluate(cfg, conv, empty_scenario)
    assert res.status == RuleStatus.FAIL
    assert "no authoritative trusted backend record" in res.explanation
    assert len(res.evidence) == 1

def test_unsupported_completion_passes_with_verified_backend_record(empty_scenario):
    rule = UnsupportedCompletionClaimsRule()
    cfg = RuleConfig(
        rule_type=RuleType.UNSUPPORTED_COMPLETION,
        parameters={"action_type": "refund"},
    )
    conv = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.AGENT, content="I have processed your refund now.", sequence=0),
        ],
        trusted_action_records=[
            {"action_type": "refund", "status": "completed", "record_id": "tx_998877"}
        ],
    )
    res = rule.evaluate(cfg, conv, empty_scenario)
    assert res.status == RuleStatus.PASS
    assert "verified by trusted system record" in res.explanation

def test_policy_compliance_within_threshold_and_violations(empty_scenario):
    rule = PolicyComplianceRule()
    cfg = RuleConfig(
        rule_type=RuleType.POLICY_COMPLIANCE,
        parameters={"max_refund_amount": 100.0},
    )
    # Offered $50 <= $100 -> PASS
    conv_ok = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.AGENT, content="I can issue a courtesy credit of $50.", sequence=0)
        ]
    )
    assert rule.evaluate(cfg, conv_ok, empty_scenario).status == RuleStatus.PASS

    # Offered $150 > $100 -> FAIL
    conv_violation = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.AGENT, content="I will issue an exceptional refund of $150.", sequence=0)
        ]
    )
    res_violation = rule.evaluate(cfg, conv_violation, empty_scenario)
    assert res_violation.status == RuleStatus.FAIL
    assert "violates policy limit" in res_violation.explanation

    # No monetary amount stated -> INCONCLUSIVE
    conv_missing = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.AGENT, content="Let me see what I can do.", sequence=0)
        ]
    )
    assert rule.evaluate(cfg, conv_missing, empty_scenario).status == RuleStatus.INCONCLUSIVE

def test_unresolved_work_flags_unresolved_customer_queries(empty_scenario):
    rule = UnresolvedWorkRule()
    cfg = RuleConfig(rule_type=RuleType.UNRESOLVED_WORK)

    # Customer left dangling
    conv_dangling = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.CUSTOMER, content="Wait, you didn't help me with my order at all!", sequence=0)
        ]
    )
    assert rule.evaluate(cfg, conv_dangling, empty_scenario).status == RuleStatus.FAIL

    # Proper escalation
    conv_escalated = Conversation(
        messages=[
            ConversationMessage(role=MessageRole.CUSTOMER, content="My order never arrived.", sequence=0),
            ConversationMessage(role=MessageRole.AGENT, content="I have escalated this to a supervisor and created ticket #5921.", sequence=1)
        ]
    )
    assert rule.evaluate(cfg, conv_escalated, empty_scenario).status == RuleStatus.PASS
