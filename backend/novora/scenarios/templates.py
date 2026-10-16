from typing import List
from novora.core.enums import RuleType
from novora.core.execution_models import ScriptedTurn, TestCase
from novora.core.models import EvaluationScenario, RuleConfig

def create_customer_support_template() -> EvaluationScenario:
    return EvaluationScenario(
        id="scen_template_customer_support",
        name="Customer Support & Receptionist",
        business_goal="Authenticate customer, retrieve order/account information, follow return policy, and escalate if needed.",
        success_criteria=[
            "Collect customer order ID",
            "Invoke order lookup tool",
            "Enforce return window policy limit",
            "Polite closing and next steps",
        ],
        rules=[
            RuleConfig(
                rule_type=RuleType.REQUIRED_INFORMATION,
                name="Collect Order ID",
                parameters={"required_fields": ["order_id"]},
            ),
            RuleConfig(
                rule_type=RuleType.EXPECTED_TOOL_CALL,
                name="Execute Order Lookup Tool",
                parameters={"tools": ["check_order"]},
            ),
            RuleConfig(
                rule_type=RuleType.REQUIRED_CLOSING,
                name="Provide Clear Next Steps",
                parameters={"closing_patterns": ["thank you", "anything else", "take care", "have a great day"]},
            ),
        ],
    )

def create_incident_response_template() -> EvaluationScenario:
    return EvaluationScenario(
        id="scen_template_incident_response",
        name="Incident Response Officer",
        business_goal="Recognize system incident, capture affected services, invoke status check tools, and escalate.",
        success_criteria=[
            "Identify impacted service",
            "Check system status tool",
            "Escalate to on-call engineer",
            "No unauthorized resolution claims",
        ],
        rules=[
            RuleConfig(
                rule_type=RuleType.EXPECTED_TOOL_CALL,
                name="Check Service Status",
                parameters={"tools": ["check_system_status"]},
            ),
            RuleConfig(
                rule_type=RuleType.REQUIRED_ESCALATION,
                name="Escalate Incident to Human Responder",
                parameters={"escalation_keywords": ["escalat", "human agent", "on-call", "engineer"]},
            ),
            RuleConfig(
                rule_type=RuleType.PROHIBITED_PHRASE,
                name="Prohibit False Incident Resolution Claims",
                parameters={"prohibited_patterns": ["incident is 100% resolved", "no outage occurred"]},
            ),
        ],
    )

def create_language_practitioner_template() -> EvaluationScenario:
    return EvaluationScenario(
        id="scen_template_language_practitioner",
        name="Language Practitioner",
        business_goal="Practice conversation in target language, adapt to proficiency level, and maintain exercise scope.",
        success_criteria=[
            "Maintain conversational turns",
            "Ask clarifying practice questions",
            "Polite closing encouragement",
        ],
        rules=[
            RuleConfig(
                rule_type=RuleType.TURN_CONSTRAINTS,
                name="Sufficient Dialogue Turns",
                parameters={"min_turns": 2, "max_turns": 30},
            ),
            RuleConfig(
                rule_type=RuleType.REQUIRED_QUESTION,
                name="Ask Practice Follow-up Question",
                parameters={"questions": ["?"]},
            ),
        ],
    )

def get_default_scenario_templates() -> List[EvaluationScenario]:
    return [
        create_customer_support_template(),
        create_incident_response_template(),
        create_language_practitioner_template(),
    ]

def get_default_test_case_for_scenario(scenario_id: str) -> TestCase:
    if "incident" in scenario_id:
        return TestCase(
            scenario_id=scenario_id,
            name="Production Outage Report",
            scripted_turns=[
                ScriptedTurn(
                    sequence=1,
                    user_message="Hello, our payment gateway service is down and returning 500 errors.",
                    expected_tools=["check_system_status"],
                    expected_response_keywords=["investigating", "escalat"],
                ),
                ScriptedTurn(
                    sequence=2,
                    user_message="Please escalate this to the on-call engineer right away.",
                    expected_tools=[],
                    expected_response_keywords=["escalated", "on-call"],
                ),
            ],
        )
    elif "language" in scenario_id:
        return TestCase(
            scenario_id=scenario_id,
            name="Beginner Spanish Introduction",
            scripted_turns=[
                ScriptedTurn(
                    sequence=1,
                    user_message="Hola, me llamo Carlos. ¿Cómo estás?",
                    expected_response_keywords=["Hola", "?"],
                ),
                ScriptedTurn(
                    sequence=2,
                    user_message="Estoy aprendiendo español para mi trabajo.",
                    expected_response_keywords=["bien", "práctica"],
                ),
            ],
        )
    else:  # Customer support
        return TestCase(
            scenario_id=scenario_id,
            name="Delayed Order Check & Return Inquiry",
            scripted_turns=[
                ScriptedTurn(
                    sequence=1,
                    user_message="Hi, I need help checking the status of my order #ORD-1234.",
                    expected_tools=["check_order"],
                    expected_response_keywords=["checking", "ORD-1234"],
                ),
                ScriptedTurn(
                    sequence=2,
                    user_message="Thank you for checking, that answers my question.",
                    expected_tools=[],
                    expected_response_keywords=["thank you", "anything else"],
                ),
            ],
        )
