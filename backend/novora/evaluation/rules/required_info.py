import re
import json
from typing import Dict, List
from novora.core.enums import RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    EvaluationScenario,
    EvidenceReference,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule

DEFAULT_FIELD_PATTERNS: Dict[str, str] = {
    "order_id": r"(?:order|ref|invoice)\s*(?:#|id|number)?\s*[:\s]?\s*([a-zA-Z0-9_-]{4,})|#\d{4,}",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b",
    "account_number": r"(?:account|acct)\s*(?:#|id|number)?\s*[:\s]?\s*([a-zA-Z0-9_-]{5,})",
    "zip_code": r"\b\d{5}(?:-\d{4})?\b",
}


def _normalize_required_fields(value: object) -> List[str]:
    """Read legacy stringified rule parameters without treating JSON as a field name."""
    normalized: List[str] = []
    pending = [value]
    for _ in range(8):
        if not pending:
            break
        item = pending.pop(0)
        if isinstance(item, str):
            try:
                decoded = json.loads(item)
            except (TypeError, json.JSONDecodeError):
                normalized.append(item.strip())
            else:
                pending.insert(0, decoded)
        elif isinstance(item, dict):
            if "required_fields" in item:
                pending.insert(0, item["required_fields"])
            elif item.get("field"):
                pending.append(str(item["field"]))
        elif isinstance(item, (list, tuple, set)):
            pending[0:0] = list(item)
    return [field for field in normalized if field]

class RequiredInfoRule(BaseRule):
    """Rule 1: Verifies whether required customer info was collected."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.REQUIRED_INFORMATION

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        fields_config = _normalize_required_fields(config.parameters.get("required_fields", []))
        if not fields_config:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Information Verification",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="No required fields were specified in the rule configuration.",
                evidence=[],
            )

        collected: Dict[str, EvidenceReference] = {}
        missing: List[str] = []

        if not conversation.messages:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Information Verification",
                rule_type=self.rule_type,
                status=RuleStatus.INCONCLUSIVE,
                explanation="No transcript messages are available to verify required information.",
                evidence=[],
            )

        for field_item in fields_config:
            if isinstance(field_item, dict):
                field_name = field_item.get("field", "")
                pattern_str = field_item.get("pattern", DEFAULT_FIELD_PATTERNS.get(field_name, rf"\b{re.escape(field_name)}\b"))
            else:
                field_name = str(field_item)
                pattern_str = DEFAULT_FIELD_PATTERNS.get(field_name, rf"\b{re.escape(field_name)}\b")

            regex = re.compile(pattern_str, re.IGNORECASE)
            found_evidence = None

            for msg in conversation.messages:
                m = regex.search(msg.content)
                if m:
                    found_evidence = self.extract_evidence(
                        msg,
                        m,
                        note=f"Captured required field '{field_name}' value: '{m.group(0)}'",
                    )
                    break

            if found_evidence:
                collected[field_name] = found_evidence
            else:
                missing.append(field_name)

        if not missing:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Information Verification",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation=f"All {len(collected)} required fields were successfully collected: {', '.join(collected.keys())}.",
                evidence=list(collected.values()),
                details={"collected_fields": list(collected.keys()), "missing_fields": []},
            )
        else:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Information Verification",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Missing required information: {', '.join(missing)}. Collected: {list(collected.keys())}.",
                evidence=list(collected.values()),
                details={"collected_fields": list(collected.keys()), "missing_fields": missing},
            )
