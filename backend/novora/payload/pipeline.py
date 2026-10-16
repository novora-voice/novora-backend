from typing import Any, Dict, List, Optional
from novora.payload.generator import PayloadGenerator
from novora.payload.judge import PayloadJudge
from novora.payload.models import (
    PayloadGenerationRequest,
    PayloadPipelineResult,
)


class PayloadOrchestrator:
    """Orchestrates the two-stage AI payload generation and LLM-as-a-judge validation pipeline."""

    def __init__(
        self,
        generator: Optional[PayloadGenerator] = None,
        judge: Optional[PayloadJudge] = None,
        max_retries: int = 3,
    ) -> None:
        self.generator = generator or PayloadGenerator()
        self.judge = judge or PayloadJudge()
        self.max_retries = max_retries

    def run_pipeline(self, request: PayloadGenerationRequest) -> PayloadPipelineResult:
        agent_id = request.agent_id.strip() if request.agent_id else ""
        if not agent_id:
            return PayloadPipelineResult(
                status="rejected",
                provider=request.provider,
                agent_id="",
                final_payload={},
                error_message="Agent ID is required before generating an evaluation payload.",
            )

        history: List[Dict[str, Any]] = []
        feedback: Optional[str] = None
        current_payload: Dict[str, Any] = {}
        verdict = None

        for attempt in range(self.max_retries + 1):
            # Stage 1: Payload Generation
            current_payload = self.generator.generate(request, feedback=feedback)

            # Stage 2: LLM-as-a-Judge Validation
            verdict = self.judge.evaluate(
                provider=request.provider,
                agent_id=agent_id,
                payload=current_payload,
                user_instructions=request.user_instructions,
                scenario_name=request.scenario.name if request.scenario else request.scenario_id,
            )

            history.append({
                "iteration": attempt + 1,
                "payload": current_payload,
                "decision": verdict.decision,
                "feedback": verdict.feedback,
                "issues": verdict.issues,
                "model_used": verdict.model_used,
            })

            if verdict.decision == "pass":
                return PayloadPipelineResult(
                    status="pass" if attempt == 0 else "revised",
                    provider=request.provider,
                    agent_id=agent_id,
                    final_payload=current_payload,
                    revision_count=attempt,
                    history=history,
                    judge_verdict=verdict,
                    schema_validation={
                        "valid_json": True,
                        "required_fields_present": True,
                        "agent_id_match": True,
                    },
                )
            elif verdict.decision == "reject":
                return PayloadPipelineResult(
                    status="rejected",
                    provider=request.provider,
                    agent_id=agent_id,
                    final_payload=current_payload,
                    revision_count=attempt,
                    history=history,
                    judge_verdict=verdict,
                    error_message=verdict.feedback,
                )
            elif verdict.decision == "revise":
                feedback = verdict.feedback
                # continue to next revision iteration if within max_retries

        # If retries exhausted without passing
        return PayloadPipelineResult(
            status="rejected",
            provider=request.provider,
            agent_id=agent_id,
            final_payload=current_payload,
            revision_count=self.max_retries,
            history=history,
            judge_verdict=verdict,
            error_message=f"Exhausted {self.max_retries} automated revision cycles. Last issue: {feedback}",
        )
