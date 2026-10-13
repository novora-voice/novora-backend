import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from novora.core.enums import MessageRole
from novora.core.models import Conversation, ConversationMessage
from novora.evaluation.engine import EvaluationEngine
try:
    from tests.test_delayed_refund_workflow import create_delayed_refund_scenario
except ModuleNotFoundError:
    from backend.tests.test_delayed_refund_workflow import create_delayed_refund_scenario

def run_demo():
    print("=" * 70)
    print("Novora Platform — Delayed Refund Evaluation Demonstration")
    print("=" * 70)

    scenario = create_delayed_refund_scenario()
    print(f"Scenario: {scenario.name}")
    print(f"Business Goal: {scenario.business_goal}\n")

    # Sample conversation: agent violates refund policy & makes unsupported completion claim
    conv = Conversation(
        id="conv_demo_sample",
        scenario_id=scenario.id,
        messages=[
            ConversationMessage(
                id="msg_1",
                role=MessageRole.CUSTOMER,
                sequence=0,
                content="Hello, my refund for order #9821 has not arrived yet. Email is user@novora.test.",
            ),
            ConversationMessage(
                id="msg_2",
                role=MessageRole.AGENT,
                sequence=1,
                content="Don't worry, I guarantee an instant refund without waiting! In fact, your refund has been processed.",
            ),
            ConversationMessage(
                id="msg_3",
                role=MessageRole.AGENT,
                sequence=2,
                content="I also applied a $120 credit to your statement.",
            ),
        ],
        trusted_action_records=[],  # No backend confirmation!
    )

    engine = EvaluationEngine()
    report = engine.evaluate(conv, scenario)

    print(f"Overall Evaluation Result: {report.overall_status.value}")
    print(f"Summary: {report.summary}\n")
    print("-" * 70)
    print("Detailed Rule Breakdown & Traceable Evidence:")
    print("-" * 70)

    for result in report.rule_results:
        status_symbol = "[PASS]" if result.status == "PASS" else "[FAIL]" if result.status == "FAIL" else "[INCONCLUSIVE]"
        print(f"\n{status_symbol} {result.rule_name} ({result.rule_type.value})")
        print(f"  Explanation: {result.explanation}")
        if result.evidence:
            for ev in result.evidence:
                print(f"  Evidence: Message '{ev.message_id}' [{ev.speaker.value}] chars [{ev.char_start}:{ev.char_end}]: '{ev.snippet}'")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    run_demo()