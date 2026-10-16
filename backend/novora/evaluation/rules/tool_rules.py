from typing import Any, Dict, List
from novora.core.enums import RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule

class ExpectedToolCallRule(BaseRule):
    """Verifies that mandatory tools were invoked during the interaction."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.EXPECTED_TOOL_CALL

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        expected_tools = config.parameters.get("tools", [])
        executed = [
            r.get("action_type") for r in conversation.trusted_action_records if r.get("action_type")
        ]
        missing = [t for t in expected_tools if t not in executed]

        if missing:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Expected Tool Call Check",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Expected tool(s) were not called: {', '.join(missing)}",
                details={"executed": executed, "missing": missing},
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Expected Tool Call Check",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation=f"All {len(expected_tools)} required tool(s) were successfully invoked.",
            details={"executed": executed},
        )

class ForbiddenToolCallRule(BaseRule):
    """Verifies that disallowed tools were not called."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.FORBIDDEN_TOOL_CALL

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        forbidden = config.parameters.get("forbidden_tools", [])
        executed = [r.get("action_type") for r in conversation.trusted_action_records]
        violations = [t for t in executed if t in forbidden]

        if violations:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Forbidden Tool Call Check",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Forbidden tool(s) were invoked: {', '.join(violations)}",
                details={"violations": violations},
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Forbidden Tool Call Check",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation="No forbidden tools were invoked.",
            details={"executed": executed},
        )

class ToolArgumentValidationRule(BaseRule):
    """Validates that tool calls had required arguments."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.TOOL_ARGUMENT_VALIDATION

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        tool_name = config.parameters.get("tool_name")
        required_keys = config.parameters.get("required_keys", [])
        matching_actions = [
            r for r in conversation.trusted_action_records if r.get("action_type") == tool_name
        ]

        if not matching_actions:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Tool Argument Validation",
                rule_type=self.rule_type,
                status=RuleStatus.INCONCLUSIVE,
                explanation=f"Tool '{tool_name}' was not called; cannot validate arguments.",
            )

        for act in matching_actions:
            res = act.get("result", {})
            missing = [k for k in required_keys if k not in res and k not in act]
            if missing:
                return RuleResult(
                    rule_id=config.id,
                    rule_name=config.name or "Tool Argument Validation",
                    rule_type=self.rule_type,
                    status=RuleStatus.FAIL,
                    explanation=f"Tool '{tool_name}' missing required parameters: {', '.join(missing)}",
                )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Tool Argument Validation",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation=f"Tool '{tool_name}' arguments passed schema validation.",
        )

class ToolCallOrderingRule(BaseRule):
    """Ensures tool A was called before tool B."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.TOOL_CALL_ORDERING

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        first_tool = config.parameters.get("first_tool")
        second_tool = config.parameters.get("second_tool")
        call_order = [r.get("action_type") for r in conversation.trusted_action_records]

        if first_tool not in call_order or second_tool not in call_order:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Tool Call Ordering",
                rule_type=self.rule_type,
                status=RuleStatus.INCONCLUSIVE,
                explanation=f"Both '{first_tool}' and '{second_tool}' must be called to verify ordering.",
            )

        idx_first = call_order.index(first_tool)
        idx_second = call_order.index(second_tool)

        if idx_first > idx_second:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Tool Call Ordering",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Tool '{second_tool}' was called before prerequisite '{first_tool}'.",
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Tool Call Ordering",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation=f"Tool '{first_tool}' was properly executed before '{second_tool}'.",
        )
