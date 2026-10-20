"""Stable scenario identities used to validate evaluation coverage."""

import hashlib
import json
from typing import Optional, Sequence

from novora.core.judge_models import RubricCriterion
from novora.core.models import EvaluationScenario


def fingerprint_scenario(
    scenario: EvaluationScenario,
    rubrics: Optional[Sequence[RubricCriterion]] = None,
    *,
    judge_enabled: bool = False,
) -> str:
    payload = {
        "scenario": scenario.model_dump(mode="json", exclude={"created_at"}),
        "judge_enabled": judge_enabled,
        "rubrics": [rubric.model_dump(mode="json") for rubric in (rubrics or [])]
        if judge_enabled
        else [],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
