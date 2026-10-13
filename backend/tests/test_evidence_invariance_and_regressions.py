"""Regression and Evidence Invariance Verification Suite.

Guarantees:
1. Missing evidence NEVER produces PASS.
2. Unsupported action claims are caught and flagged as FAIL.
3. Deterministic idempotency: evaluating the same conversation multiple times
   yields identical reports, statuses, and evidence references.
"""

from novora.core.enums import MessageRole, OverallStatus, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationScenario,
    RuleConfig,
)
from novora.evaluation.engine import EvaluationEngine

def test_missing_evidence_cannot_produce_pass():
    """Verify that absent required data or empty dialogue never defaults to PASS."""
    engine = EvaluationEngine()

    scenario = EvaluationScenario(
        id="scen_strict_evidence",
        name="Strict Evidence Check",
        business_goal="Enforce evidence presence",
        rules=[
            RuleConfig(
                rule_type=RuleType.REQUIRED_INFORMATION,
                parameters={"required_fields": ["order_id", "email"]},
            ),
            RuleConfig(
                rule_type=RuleType.POLICY_COMPLIANCE,
                parameters={"max_refund_amount": 50.0},
            ),
        ],
    )

    # Empty conversation
    empty_conv = Conversation(id="conv_empty", messages=[])
    report = engine.evaluate(empty_conv, scenario)

    # Missing evidence must NOT result in PASS
    assert report.overall_status != OverallStatus.PASS
    assert report.overall_status in (OverallStatus.FAIL, OverallStatus.INCONCLUSIVE)

    info_result = next(r for r in report.rule_results if r.rule_type == RuleType.REQUIRED_INFORMATION)
    assert info_result.status == RuleStatus.FAIL

    policy_result = next(r for r in report.rule_results if r.rule_type == RuleType.POLICY_COMPLIANCE)
    assert policy_result.status == RuleStatus.INCONCLUSIVE

def test_unsupported_action_claims_flagged_with_exact_evidence_span():
    """Verify that verbal claims without backend action records are flagged with exact span."""
    engine = EvaluationEngine()

    scenario = EvaluationScenario(
        id="scen_unsupported",
        name="Flag Unsupported Claims",
        business_goal="Never trust agent verbal assertions of external success",
        rules=[
            RuleConfig(
                rule_type=RuleType.UNSUPPORTED_COMPLETION,
                parameters={
                    "action_type": "refund",
                    "claim_patterns": [r"processed your refund"],
                },
            )
        ],
    )

    sentence = "No worries, I processed your refund for you today."
    conv = Conversation(
        id="conv_verbal_claim",
        messages=[
            ConversationMessage(
                id="msg_claim_10",
                role=MessageRole.AGENT,
                sequence=0,
                content=sentence,
            )
        ],
        trusted_action_records=[],  # No backend confirmation
    )

    report = engine.evaluate(conv, scenario)
    assert report.overall_status == OverallStatus.FAIL
    res = report.rule_results[0]
    assert res.status == RuleStatus.FAIL
    assert len(res.evidence) == 1

    ev = res.evidence[0]
    assert ev.message_id == "msg_claim_10"
    assert ev.speaker == MessageRole.AGENT
    # Verify the char span extracts the exact words
    extracted_text = sentence[ev.char_start:ev.char_end]
    assert extracted_text.lower() == "processed your refund"

def test_deterministic_idempotency_regression():
    """Evaluating identical fixture multiple times must produce identical output."""
    engine = EvaluationEngine()

    scenario = EvaluationScenario(
        id="scen_idem",
        name="Idempotency Test",
        business_goal="Ensure deterministic behavior",
        rules=[
            RuleConfig(
                rule_type=RuleType.REQUIRED_INFORMATION,
                parameters={"required_fields": ["order_id"]},
            ),
            RuleConfig(
                rule_type=RuleType.PROHIBITED_CLAIMS,
                parameters={"prohibited_patterns": ["waive fees"]},
            ),
        ],
    )

    conv = Conversation(
        id="conv_idem",
        messages=[
            ConversationMessage(
                id="m1",
                role=MessageRole.CUSTOMER,
                sequence=0,
                content="Here is order #10492.",
            ),
            ConversationMessage(
                id="m2",
                role=MessageRole.AGENT,
                sequence=1,
                content="Thanks, checking order #10492 now.",
            ),
        ],
    )

    initial_report = engine.evaluate(conv, scenario)

    for _ in range(5):
        subsequent_report = engine.evaluate(conv, scenario)
        assert subsequent_report.overall_status == initial_report.overall_status
        assert subsequent_report.total_rules == initial_report.total_rules
        assert subsequent_report.passed_rules == initial_report.passed_rules
        assert subsequent_report.failed_rules == initial_report.failed_rules
        assert [r.status for r in subsequent_report.rule_results] == [r.status for r in initial_report.rule_results]
        assert [r.explanation for r in subsequent_report.rule_results] == [r.explanation for r in initial_report.rule_results]
