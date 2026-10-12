import pytest
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationReport,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
)

def test_conversation_message_sequence_order_validation():
    # Sequence numbers strictly ascending
    valid_msgs = [
        ConversationMessage(role=MessageRole.CUSTOMER, content="Hello", sequence=0),
        ConversationMessage(role=MessageRole.AGENT, content="Hi there", sequence=1),
    ]
    conv = Conversation(messages=valid_msgs)
    assert len(conv.messages) == 2

    # Sequence numbers out of order must raise validation error
    invalid_msgs = [
        ConversationMessage(role=MessageRole.AGENT, content="Hi there", sequence=2),
        ConversationMessage(role=MessageRole.CUSTOMER, content="Hello", sequence=1),
    ]
    with pytest.raises(ValueError, match="strictly ordered"):
        Conversation(messages=invalid_msgs)

def test_evaluation_report_auto_counts():
    r1 = RuleResult(
        rule_id="r1",
        rule_name="Rule 1",
        rule_type=RuleType.REQUIRED_INFORMATION,
        status=RuleStatus.PASS,
        explanation="Passed",
    )
    r2 = RuleResult(
        rule_id="r2",
        rule_name="Rule 2",
        rule_type=RuleType.PROHIBITED_CLAIMS,
        status=RuleStatus.FAIL,
        explanation="Failed",
    )
    report = EvaluationReport(
        scenario_id="scen_1",
        conversation_id="conv_1",
        overall_status="FAIL",
        summary="Test summary",
        rule_results=[r1, r2],
    )
    assert report.total_rules == 2
    assert report.passed_rules == 1
    assert report.failed_rules == 1
    assert report.inconclusive_rules == 0
