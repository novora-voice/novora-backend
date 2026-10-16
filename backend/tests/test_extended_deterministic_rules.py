import pytest
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationScenario,
    RuleConfig,
)
from novora.evaluation.rules.content_rules import (
    ProhibitedPhraseRule,
    RequiredClosingRule,
    RequiredPhraseRule,
    RequiredQuestionRule,
)
from novora.evaluation.rules.flow_rules import (
    EvidenceAvailabilityRule,
    RequiredConfirmationRule,
    RequiredEscalationRule,
    TurnConstraintsRule,
)
from novora.evaluation.rules.tool_rules import (
    ExpectedToolCallRule,
    ForbiddenToolCallRule,
    ToolCallOrderingRule,
)

@pytest.fixture
def dummy_scenario():
    return EvaluationScenario(name="Test Scenario", business_goal="Verification")

def test_required_phrase_rule(dummy_scenario):
    rule = RequiredPhraseRule()
    conv = Conversation(
        messages=[
            ConversationMessage(id="m1", role=MessageRole.CUSTOMER, content="Hi", sequence=0),
            ConversationMessage(id="m2", role=MessageRole.AGENT, content="Welcome to customer support!", sequence=1),
        ]
    )
    # PASS when phrase present
    cfg_pass = RuleConfig(rule_type=RuleType.REQUIRED_PHRASE, parameters={"phrases": ["customer support"]})
    res_pass = rule.evaluate(cfg_pass, conv, dummy_scenario)
    assert res_pass.status == RuleStatus.PASS

    # FAIL when phrase missing
    cfg_fail = RuleConfig(rule_type=RuleType.REQUIRED_PHRASE, parameters={"phrases": ["unrelated phrase"]})
    res_fail = rule.evaluate(cfg_fail, conv, dummy_scenario)
    assert res_fail.status == RuleStatus.FAIL

def test_prohibited_phrase_rule(dummy_scenario):
    rule = ProhibitedPhraseRule()
    conv = Conversation(
        messages=[
            ConversationMessage(id="m1", role=MessageRole.CUSTOMER, content="Help", sequence=0),
            ConversationMessage(id="m2", role=MessageRole.AGENT, content="I promise a 100% instant refund now.", sequence=1),
        ]
    )
    cfg = RuleConfig(rule_type=RuleType.PROHIBITED_PHRASE, parameters={"prohibited_patterns": ["100% instant refund"]})
    res = rule.evaluate(cfg, conv, dummy_scenario)
    assert res.status == RuleStatus.FAIL
    assert len(res.evidence) == 1

def test_tool_rules(dummy_scenario):
    expected_rule = ExpectedToolCallRule()
    forbidden_rule = ForbiddenToolCallRule()
    ordering_rule = ToolCallOrderingRule()

    conv = Conversation(
        messages=[ConversationMessage(id="m1", role=MessageRole.AGENT, content="Done", sequence=0)],
        trusted_action_records=[
            {"action_type": "check_order", "result": {"status": "ok"}},
            {"action_type": "refund_tool", "result": {"amount": 20}},
        ],
    )

    # Expected tool call
    res_exp = expected_rule.evaluate(
        RuleConfig(rule_type=RuleType.EXPECTED_TOOL_CALL, parameters={"tools": ["check_order"]}),
        conv,
        dummy_scenario,
    )
    assert res_exp.status == RuleStatus.PASS

    # Forbidden tool call
    res_forbid = forbidden_rule.evaluate(
        RuleConfig(rule_type=RuleType.FORBIDDEN_TOOL_CALL, parameters={"forbidden_tools": ["delete_account"]}),
        conv,
        dummy_scenario,
    )
    assert res_forbid.status == RuleStatus.PASS

    # Tool call ordering (check_order before refund_tool)
    res_order = ordering_rule.evaluate(
        RuleConfig(rule_type=RuleType.TOOL_CALL_ORDERING, parameters={"first_tool": "check_order", "second_tool": "refund_tool"}),
        conv,
        dummy_scenario,
    )
    assert res_order.status == RuleStatus.PASS

def test_flow_rules(dummy_scenario):
    escalation_rule = RequiredEscalationRule()
    confirmation_rule = RequiredConfirmationRule()
    turn_rule = TurnConstraintsRule()

    conv = Conversation(
        messages=[
            ConversationMessage(id="m1", role=MessageRole.CUSTOMER, content="I need supervisor", sequence=0),
            ConversationMessage(id="m2", role=MessageRole.AGENT, content="I will escalate you to a human agent right away.", sequence=1),
            ConversationMessage(id="m3", role=MessageRole.AGENT, content="Can you confirm your account?", sequence=2),
        ]
    )

    res_esc = escalation_rule.evaluate(RuleConfig(rule_type=RuleType.REQUIRED_ESCALATION), conv, dummy_scenario)
    assert res_esc.status == RuleStatus.PASS

    res_conf = confirmation_rule.evaluate(RuleConfig(rule_type=RuleType.REQUIRED_CONFIRMATION), conv, dummy_scenario)
    assert res_conf.status == RuleStatus.PASS

    res_turn = turn_rule.evaluate(
        RuleConfig(rule_type=RuleType.TURN_CONSTRAINTS, parameters={"min_turns": 2, "max_turns": 5}),
        conv,
        dummy_scenario,
    )
    assert res_turn.status == RuleStatus.PASS
