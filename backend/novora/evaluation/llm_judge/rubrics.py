from typing import Dict, List
from novora.core.judge_models import RubricCriterion

STANDARD_RUBRICS: Dict[str, RubricCriterion] = {
    "intent_understanding": RubricCriterion(
        criterion_id="intent_understanding",
        name="User Intent Understanding",
        description="Assesses whether the agent accurately comprehended the user's root objective.",
        rubric_guidance=(
            "PASS if agent demonstrated clear understanding of user needs. "
            "FAIL if agent repeatedly misunderstood or answered unrelated queries. "
            "INCONCLUSIVE if dialogue was too short."
        ),
    ),
    "role_adherence": RubricCriterion(
        criterion_id="role_adherence",
        name="Role Adherence",
        description="Assesses whether the agent maintained its configured professional persona and role.",
        rubric_guidance="PASS if within persona; FAIL if breaks character or takes unauthorized stance.",
    ),
    "helpfulness_clarity": RubricCriterion(
        criterion_id="helpfulness_clarity",
        name="Helpfulness & Clarity",
        description="Assesses whether agent explanations were concise, actionable, and free of jargon.",
        rubric_guidance="PASS if clear and helpful; FAIL if misleading or unhelpful.",
    ),
    "frustration_handling": RubricCriterion(
        criterion_id="frustration_handling",
        name="Frustration & Ambiguity Handling",
        description="Assesses whether agent responded empathetically to user frustration or ambiguity.",
        rubric_guidance="PASS if calm, polite, and clarifying; FAIL if dismissive or argumentative.",
    ),
    "language_level_match": RubricCriterion(
        criterion_id="language_level_match",
        name="Language Level Match",
        description="For language practice scenarios, assesses alignment with target CEFR level.",
        rubric_guidance="PASS if vocabulary and grammar match target level; FAIL if inappropriate complexity.",
    ),
    "incident_response_process": RubricCriterion(
        criterion_id="incident_response_process",
        name="Incident Response Process Adherence",
        description="Assesses whether agent followed structured incident response workflow.",
        rubric_guidance="PASS if followed escalation and status procedures; FAIL if omitted critical steps.",
    ),
    "customer_resolution": RubricCriterion(
        criterion_id="customer_resolution",
        name="Customer Issue Resolution",
        description="Assesses whether customer issue reached a satisfactory resolution or clear next step.",
        rubric_guidance="PASS if issue resolved or clean handoff provided; FAIL if abandoned.",
    ),
}

def get_rubrics_for_scenario(scenario_type: str) -> List[RubricCriterion]:
    st = scenario_type.lower()
    if "language" in st:
        return [
            STANDARD_RUBRICS["intent_understanding"],
            STANDARD_RUBRICS["language_level_match"],
            STANDARD_RUBRICS["helpfulness_clarity"],
        ]
    elif "incident" in st:
        return [
            STANDARD_RUBRICS["intent_understanding"],
            STANDARD_RUBRICS["incident_response_process"],
            STANDARD_RUBRICS["role_adherence"],
        ]
    else:  # Customer support / default
        return [
            STANDARD_RUBRICS["intent_understanding"],
            STANDARD_RUBRICS["customer_resolution"],
            STANDARD_RUBRICS["helpfulness_clarity"],
            STANDARD_RUBRICS["frustration_handling"],
        ]
