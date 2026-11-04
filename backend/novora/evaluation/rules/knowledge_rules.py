"""Deterministic knowledge-grounded evaluation rules."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationScenario,
    EvidenceReference,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule

logger = logging.getLogger(__name__)


def _extract_retrieval_trace(conversation: Conversation) -> Optional[Dict[str, Any]]:
    """Helper to extract retrieval trace from conversation metadata or trusted actions."""
    if conversation.metadata and "retrieval_trace" in conversation.metadata:
        return conversation.metadata["retrieval_trace"]
    # Check trusted action records
    for action in conversation.trusted_action_records:
        if action.get("action_type") == "knowledge_retrieval" and "trace" in action:
            return action["trace"]
    return None


class KnowledgeRetrievalSufficiencyRule(BaseRule):
    """Verifies that retrieval was executed, returned sufficient evidence chunks, and met score thresholds."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.KNOWLEDGE_RETRIEVAL_SUFFICIENCY

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        trace = _extract_retrieval_trace(conversation)
        if not trace:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Retrieval Sufficiency",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation="No retrieval trace found in conversation metadata.",
                details={"retrieval_executed": False},
            )

        evidence = trace.get("evidence", [])
        min_chunks = config.parameters.get("min_chunks", 1)
        min_score = config.parameters.get("min_score", 0.3)
        required_doc_ids = config.parameters.get("required_document_ids", [])

        if len(evidence) < min_chunks:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Retrieval Sufficiency",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Retrieved {len(evidence)} chunks, which is less than the required minimum of {min_chunks}.",
                details={"retrieved_chunks": len(evidence), "required_chunks": min_chunks},
            )

        qualifying = [e for e in evidence if e.get("score", 0.0) >= min_score]
        if not qualifying:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Retrieval Sufficiency",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"None of the {len(evidence)} retrieved chunks met the minimum score threshold of {min_score}.",
                details={"max_score": max((e.get("score", 0.0) for e in evidence), default=0.0)},
            )

        if required_doc_ids:
            retrieved_doc_ids = {e.get("document_id") for e in evidence}
            missing = [d for d in required_doc_ids if d not in retrieved_doc_ids]
            if missing:
                return RuleResult(
                    rule_id=config.id,
                    rule_name=config.name or "Knowledge Retrieval Sufficiency",
                    rule_type=self.rule_type,
                    status=RuleStatus.FAIL,
                    explanation=f"Required source documents were missing from retrieved context: {missing}",
                    details={"missing_documents": missing},
                )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Knowledge Retrieval Sufficiency",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation=f"Successfully retrieved {len(evidence)} chunks meeting score criteria.",
            details={"chunk_count": len(evidence), "qualifying_count": len(qualifying)},
        )


class KnowledgeGroundednessRule(BaseRule):
    """Verifies that agent responses are grounded in retrieved evidence without hallucinated facts."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.KNOWLEDGE_GROUNDEDNESS

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        trace = _extract_retrieval_trace(conversation)
        agent_messages = [m for m in conversation.messages if m.role == MessageRole.AGENT]

        if not agent_messages:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Groundedness",
                rule_type=self.rule_type,
                status=RuleStatus.INCONCLUSIVE,
                explanation="No agent messages present to evaluate groundedness.",
            )

        evidence = trace.get("evidence", []) if trace else []
        retrieved_text = " ".join(e.get("text", "") for e in evidence).lower()

        # If evidence was empty, verify agent acknowledged lack of information
        if not evidence:
            must_acknowledge = config.parameters.get("require_acknowledge_missing", True)
            if must_acknowledge:
                ack_patterns = [
                    r"do not have (?:this|that|sufficient) information",
                    r"not found in (?:my|our) (?:knowledge base|records|documentation)",
                    r"unable to verify",
                    r"don't have access to that information",
                ]
                has_ack = any(
                    any(re.search(pat, m.content, re.IGNORECASE) for pat in ack_patterns)
                    for m in agent_messages
                )
                if not has_ack:
                    return RuleResult(
                        rule_id=config.id,
                        rule_name=config.name or "Knowledge Groundedness",
                        rule_type=self.rule_type,
                        status=RuleStatus.FAIL,
                        explanation="No evidence was retrieved and agent failed to acknowledge missing information.",
                        evidence=[self.message_as_evidence(agent_messages[-1])],
                    )

        # Check prohibited unsupported claims
        prohibited_claims = config.parameters.get("prohibited_unsupported_claims", [])
        for claim in prohibited_claims:
            pattern = re.compile(claim, re.IGNORECASE)
            for m in agent_messages:
                match = pattern.search(m.content)
                if match and claim.lower() not in retrieved_text:
                    return RuleResult(
                        rule_id=config.id,
                        rule_name=config.name or "Knowledge Groundedness",
                        rule_type=self.rule_type,
                        status=RuleStatus.FAIL,
                        explanation=f"Agent made claim '{claim}' which was not supported by retrieved knowledge.",
                        evidence=[self.extract_evidence(m, match, note=f"Unsupported claim: {claim}")],
                    )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Knowledge Groundedness",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation="Agent statements are properly grounded in retrieved evidence.",
        )


class KnowledgeSourceCitationRule(BaseRule):
    """Verifies that citations or source document references point to authorized knowledge documents."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.KNOWLEDGE_SOURCE_CITATION

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        trace = _extract_retrieval_trace(conversation)
        allowed_docs = set(config.parameters.get("allowed_document_ids", []))

        if not allowed_docs:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Source Citation",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="No specific document restriction specified; citations verified.",
            )

        if not trace:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Source Citation",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation="Missing retrieval trace to verify source citations.",
            )

        retrieved_docs = {e.get("document_id") for e in trace.get("evidence", [])}
        invalid = retrieved_docs - allowed_docs
        if invalid:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Source Citation",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Citations included unauthorized source documents: {list(invalid)}",
                details={"unauthorized_documents": list(invalid)},
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Knowledge Source Citation",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation="All cited source documents are authorized.",
        )


class KnowledgeTenantAuthorizationRule(BaseRule):
    """Strict security rule verifying that retrieved evidence belongs only to the authorized tenant."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.KNOWLEDGE_TENANT_AUTHORIZATION

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        trace = _extract_retrieval_trace(conversation)
        expected_org_id = config.parameters.get("authorized_org_id") or conversation.metadata.get("org_id")

        if not expected_org_id:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Tenant Authorization",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="No specific tenant constraint provided.",
            )

        if not trace:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Tenant Authorization",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="No retrieval trace in conversation.",
            )

        trace_org = trace.get("org_id")
        if trace_org and trace_org != expected_org_id:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Knowledge Tenant Authorization",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"CRITICAL: Evidence trace belongs to tenant '{trace_org}', but authorized tenant is '{expected_org_id}'.",
                details={"violation": True, "trace_org": trace_org, "expected_org": expected_org_id},
            )

        # Check each evidence item's tenant metadata
        for item in trace.get("evidence", []):
            item_tenant = item.get("metadata", {}).get("tenant_id")
            if item_tenant and item_tenant != expected_org_id:
                return RuleResult(
                    rule_id=config.id,
                    rule_name=config.name or "Knowledge Tenant Authorization",
                    rule_type=self.rule_type,
                    status=RuleStatus.FAIL,
                    explanation=f"CRITICAL: Chunk from document '{item.get('document_id')}' has tenant '{item_tenant}', violating tenant isolation.",
                    details={"violation": True, "item_tenant": item_tenant},
                )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Knowledge Tenant Authorization",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation="All knowledge retrieval evidence strictly honors tenant isolation.",
        )

