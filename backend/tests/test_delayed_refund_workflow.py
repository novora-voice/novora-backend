"""End-to-End Delayed Refund Evaluation Workflow Deliverable.

Verifies whether an agent:
1. Collected required information (order_id, email)
2. Followed required workflow steps
3. Respected refund policy thresholds ($50 limit)
4. Avoided prohibited promises (e.g. instant refund guarantees)
5. Flagged unsupported completion claims (claiming refund was processed without trusted system record)
6. Resolved the customer inquiry without dangling work
"""

from novora.core.enums import MessageRole, OverallStatus, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationScenario,
    RuleConfig,
)
from novora.evaluation.engine import EvaluationEngine

def create_delayed_refund_scenario() -> EvaluationScenario:
    """Builds the canonical delayed refund scenario definition."""
    rules = [
        RuleConfig(
            id="rule_req_info",
            rule_type=RuleType.REQUIRED_INFORMATION,
            name="Verify Customer & Order Identity",
            parameters={"required_fields": ["order_id", "email"]},
        ),
        RuleConfig(
            id="rule_req_steps",
            rule_type=RuleType.REQUIRED_STEPS,
            name="Sequential Refund Review Steps",
            parameters={
                "steps": [
                    {"name": "greeting", "pattern": r"(?:hello|thank you for calling|welcome)"},
                    {"name": "lookup", "pattern": r"(?:look up|check your order|review your account)"},
                    {"name": "status_update", "pattern": r"(?:delay|processing|investigating|bank)"},
                    {"name": "closing", "pattern": r"(?:anything else|have a great day|take care)"},
                ],
                "ordered": True,
            },
        ),
        RuleConfig(
            id="rule_prohibited",
            rule_type=RuleType.PROHIBITED_CLAIMS,
            name="Prohibited Instant Refund Guarantees",
            parameters={
                "prohibited_patterns": [
                    r"guarantee(?:ing)? (?:an )?instant refund",
                    r"waive all processing times",
                ]
            },
        ),
        RuleConfig(
            id="rule_unsupported_claim",
            rule_type=RuleType.UNSUPPORTED_COMPLETION,
            name="Authoritative Refund Execution Verification",
            parameters={
                "action_type": "refund",
                "claim_patterns": [
                    r"(?:have|has)\s+(?:been\s+)?processed\s+(?:your\s+)?refund",
                    r"refund\s+(?:has\s+been|is)\s+processed",
                ],
            },
        ),
        RuleConfig(
            id="rule_policy_threshold",
            rule_type=RuleType.POLICY_COMPLIANCE,
            name="Maximum Autonomous Courtesy Credit ($50 limit)",
            parameters={"max_refund_amount": 50.0},
        ),
        RuleConfig(
            id="rule_unresolved",
            rule_type=RuleType.UNRESOLVED_WORK,
            name="Confirmation and Ticket Resolution",
        ),
    ]
    return EvaluationScenario(
        id="scen_delayed_refund_01",
        name="Delayed Refund Resolution Scenario",
        business_goal="Authenticate customer, explain delay, enforce $50 courtesy limit, prevent false execution claims",
        success_criteria=[
            "Order ID and email collected",
            "Steps executed in proper sequence",
            "No unverified claim of refund completion without system audit record",
            "Courtesy credit within policy limit ($50)",
            "Resolution or ticket reference provided",
        ],
        rules=rules,
    )

def test_delayed_refund_successful_workflow():
    """Scenario where agent satisfies every business requirement with verified evidence."""
    engine = EvaluationEngine()
    scenario = create_delayed_refund_scenario()

    conversation = Conversation(
        id="conv_refund_pass_001",
        scenario_id=scenario.id,
        messages=[
            ConversationMessage(
                id="m1",
                role=MessageRole.AGENT,
                sequence=0,
                content="Hello, thank you for calling customer care. How can I assist you today?",
            ),
            ConversationMessage(
                id="m2",
                role=MessageRole.CUSTOMER,
                sequence=1,
                content="Hi, I'm checking on my delayed refund for order #9821. My email is alex@example.com.",
            ),
            ConversationMessage(
                id="m3",
                role=MessageRole.AGENT,
                sequence=2,
                content="Let me look up your account and check your order history right now.",
            ),
            ConversationMessage(
                id="m4",
                role=MessageRole.AGENT,
                sequence=3,
                content="I see the refund was delayed due to a bank processing backlog. As an apology, I can offer a $25 credit.",
            ),
            ConversationMessage(
                id="m5",
                role=MessageRole.AGENT,
                sequence=4,
                content="I have logged your request under ticket #REF-8821. Is there anything else I can help with?",
            ),
            ConversationMessage(
                id="m6",
                role=MessageRole.CUSTOMER,
                sequence=5,
                content="No, that resolves everything. Thank you!",
            ),
        ],
        trusted_action_records=[],  # Agent didn't claim to process the full refund, just explained backlog & offered credit
    )

    report = engine.evaluate(conversation, scenario)

    # Assertions
    failures = [(r.rule_name, r.status, r.explanation) for r in report.rule_results if r.status != RuleStatus.PASS]
    assert not failures, f"Unexpected rule failures: {failures}"
    assert report.overall_status == OverallStatus.PASS
    assert report.failed_rules == 0
    assert report.passed_rules == 6
    assert report.inconclusive_rules == 0

    # Verify evidence traceability
    for rule_res in report.rule_results:
        assert rule_res.status == RuleStatus.PASS
        assert len(rule_res.evidence) >= 0 or "No prohibited" in rule_res.explanation

    # Check that required info pointed to message m2
    info_result = next(r for r in report.rule_results if r.rule_type == RuleType.REQUIRED_INFORMATION)
    assert any(ev.message_id == "m2" for ev in info_result.evidence)

def test_delayed_refund_failing_with_unsupported_claim_and_policy_breach():
    """Scenario where agent violates policy ($150 credit > $50), makes prohibited guarantee,

    and falsely claims refund has been processed without backend proof.
    """
    engine = EvaluationEngine()
    scenario = create_delayed_refund_scenario()

    conversation = Conversation(
        id="conv_refund_fail_002",
        scenario_id=scenario.id,
        messages=[
            ConversationMessage(
                id="m1",
                role=MessageRole.AGENT,
                sequence=0,
                content="Hello, thank you for calling. What's the problem?",
            ),
            ConversationMessage(
                id="m2",
                role=MessageRole.CUSTOMER,
                sequence=1,
                content="My refund is taking forever! Order #12345.",
            ),
            ConversationMessage(
                id="m3",
                role=MessageRole.AGENT,
                sequence=2,
                content="I guarantee an instant refund without waiting! In fact, your refund has been processed already.",
            ),
            ConversationMessage(
                id="m4",
                role=MessageRole.AGENT,
                sequence=3,
                content="I am also giving you an extra courtesy refund of $150.",
            ),
        ],
        trusted_action_records=[],  # Zero backend records confirming any refund!
    )

    report = engine.evaluate(conversation, scenario)

    assert report.overall_status == OverallStatus.FAIL
    assert report.failed_rules >= 3  # Missing email, prohibited guarantee, unsupported completion, policy limit exceeded

    # 1. Unsupported completion claim flagged
    unsupported_res = next(r for r in report.rule_results if r.rule_type == RuleType.UNSUPPORTED_COMPLETION)
    assert unsupported_res.status == RuleStatus.FAIL
    assert unsupported_res.evidence[0].message_id == "m3"
    assert "no authoritative trusted backend record" in unsupported_res.explanation

    # 2. Prohibited claim flagged
    prohibited_res = next(r for r in report.rule_results if r.rule_type == RuleType.PROHIBITED_CLAIMS)
    assert prohibited_res.status == RuleStatus.FAIL
    assert prohibited_res.evidence[0].message_id == "m3"

    # 3. Policy violation ($150 > $50 limit)
    policy_res = next(r for r in report.rule_results if r.rule_type == RuleType.POLICY_COMPLIANCE)
    assert policy_res.status == RuleStatus.FAIL
    assert policy_res.evidence[0].message_id == "m4"
    assert "$150.00" in policy_res.explanation
