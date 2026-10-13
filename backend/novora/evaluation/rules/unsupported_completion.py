import re
from typing import Any, Dict, List
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    EvaluationScenario,
    EvidenceReference,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule

DEFAULT_COMPLETION_PATTERNS = [
    r"(?:have|has)\s+(?:been\s+)?(?:processed|issued|sent|credited)\s+(?:your\s+)?(?:refund|payment|credit)",
    r"refund\s+(?:has\s+been|is|was)\s+(?:processed|completed|issued)",
    r"(?:processed|issued)\s+(?:the\s+)?refund",
    r"(?:booked|scheduled|reserved)\s+(?:your\s+)?(?:appointment|ride|flight|hotel)",
    r"(?:cancelled|canceled)\s+(?:your\s+)?(?:subscription|account|order)",
]

class UnsupportedCompletionClaimsRule(BaseRule):
    """Rule 4: Detects cases where the agent claims an external action succeeded

    without verification from an authoritative backend record.
    """

    @property
    def rule_type(self) -> RuleType:
        return RuleType.UNSUPPORTED_COMPLETION

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        claim_patterns = config.parameters.get("claim_patterns", DEFAULT_COMPLETION_PATTERNS)
        action_type = config.parameters.get("action_type")

        # Compile claim detection patterns
        compiled = [re.compile(p, re.IGNORECASE) for p in claim_patterns]

        claim_evidences: List[EvidenceReference] = []

        # Find any agent utterances claiming external completion
        for msg in conversation.messages:
            if msg.role != MessageRole.AGENT:
                continue

            for regex in compiled:
                for match in regex.finditer(msg.content):
                    ev = self.extract_evidence(
                        msg,
                        match,
                        note="Agent claimed external action was completed",
                    )
                    claim_evidences.append(ev)

        # If agent never claimed an external action was completed
        if not claim_evidences:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Unsupported Completion Claim Detection",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="Agent did not make unverified external action completion claims.",
                evidence=[],
                details={"claims_made": 0},
            )

        # Agent claimed completion -> check for trusted action records
        trusted_records = conversation.trusted_action_records or []
        verified_record: Dict[str, Any] = {}

        for rec in trusted_records:
            status = str(rec.get("status", "")).lower()
            rec_type = str(rec.get("action_type", "")).lower()

            if status in {"success", "completed", "verified"}:
                if not action_type or rec_type == action_type.lower():
                    verified_record = rec
                    break

        if verified_record:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Unsupported Completion Claim Detection",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation=(
                    f"Agent claimed completion, and action was verified by trusted system record "
                    f"({verified_record.get('record_id', verified_record.get('action_type', 'verified'))})."
                ),
                evidence=claim_evidences,
                details={"verified_record": verified_record},
            )

        # FAILURE: Agent verbally claimed action was completed, but NO backend record confirms it
        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Unsupported Completion Claim Detection",
            rule_type=self.rule_type,
            status=RuleStatus.FAIL,
            explanation=(
                f"Agent claimed an external action was completed ({len(claim_evidences)} claim(s)), "
                "but no authoritative trusted backend record confirmed the transaction."
            ),
            evidence=claim_evidences,
            details={
                "unsupported_claim_count": len(claim_evidences),
                "trusted_records_found": len(trusted_records),
            },
        )
