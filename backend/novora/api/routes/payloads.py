from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Query, status
from novora.payload.judge import PayloadJudge
from novora.payload.models import (
    PayloadGenerationRequest,
    PayloadJudgeVerdict,
    PayloadPipelineResult,
    PayloadTemplate,
    PayloadValidationRequest,
)
from novora.payload.pipeline import PayloadOrchestrator

router = APIRouter(prefix="/api/v1/payloads", tags=["AI-Assisted Payloads & Validation"])

orchestrator = PayloadOrchestrator()
judge = PayloadJudge()

# Built-in valid templates for Vapi and Retell
BUILTIN_TEMPLATES: List[PayloadTemplate] = [
    PayloadTemplate(
        id="tmpl_vapi_customer_service",
        provider="vapi",
        name="Vapi Customer Support Assistant",
        description="Standard customer reception, order authentication, and end-of-call transcript streaming.",
        payload={
            "assistantId": "asst_vapi_support_01",
            "name": "Customer Support Receptionist",
            "transcriber": {"provider": "deepgram", "model": "nova-2"},
            "model": {"provider": "openai", "model": "gpt-4o"},
            "firstMessage": "Hello! How can I assist you with your account or order today?",
            "analysisPlan": {"summaryPlan": {"enabled": True}, "structuredDataPlan": {"enabled": True}},
        },
    ),
    PayloadTemplate(
        id="tmpl_vapi_refund_enforcer",
        provider="vapi",
        name="Vapi Policy & Refund Ceiling Target",
        description="Assistant target configured with $50 refund cap and prohibited unauthorized guarantees.",
        payload={
            "assistantId": "asst_vapi_refund_02",
            "name": "Refund Policy Enforcer",
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [{"role": "system", "content": "Authenticate order ID. Discretionary refund limit is strictly $50."}],
            },
            "firstMessage": "Welcome to Billing Support. Please share your order number.",
        },
    ),
    PayloadTemplate(
        id="tmpl_retell_incident_officer",
        provider="retell",
        name="Retell AI Incident Response Officer",
        description="Multi-turn incident triage assistant with live tool execution hooks.",
        payload={
            "agent_id": "agent_retell_incident_01",
            "agent_name": "Outage Triage Assistant",
            "voice_id": "11labs-Adrian",
            "begin_message": "Incident Response Line. What system or service is currently reporting degraded performance?",
            "general_prompt": "Capture affected services, invoke check_system_status tool, and escalate P1 outages.",
            "dynamic_variables": {"priority": "high", "environment": "production"},
        },
    ),
    PayloadTemplate(
        id="tmpl_retell_concierge",
        provider="retell",
        name="Retell Front Desk Concierge",
        description="Polite business receptionist with conversational turn constraints.",
        payload={
            "agent_id": "agent_retell_concierge_02",
            "agent_name": "Novora Concierge",
            "voice_id": "11labs-Adrian",
            "begin_message": "Good day! Welcome to Novora Services. How may I direct your call?",
            "general_prompt": "Answer caller inquiries politely and route to appropriate departments.",
        },
    ),
]


@router.post("/generate", response_model=PayloadPipelineResult, status_code=status.HTTP_200_OK)
def generate_and_validate_payload(req: PayloadGenerationRequest) -> PayloadPipelineResult:
    """Execute two-stage AI payload generation and LLM-as-a-judge validation pipeline."""
    if not (req.agent_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AGENT_ID_REQUIRED", "message": "An agent ID is required before generating an evaluation payload."},
        )
    return orchestrator.run_pipeline(req)


@router.post("/validate", response_model=PayloadJudgeVerdict, status_code=status.HTTP_200_OK)
def validate_custom_payload(req: PayloadValidationRequest) -> PayloadJudgeVerdict:
    """Validate a user-supplied custom JSON payload using deterministic rules and LLM judge."""
    if not (req.agent_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AGENT_ID_REQUIRED", "message": "An agent ID is required before validating a payload."},
        )
    return judge.evaluate(
        provider=req.provider,
        agent_id=req.agent_id,
        payload=req.payload,
        user_instructions=req.user_instructions,
        scenario_name=req.scenario_id,
    )


@router.get("/templates", response_model=List[PayloadTemplate])
def list_payload_templates(provider: str = Query(default=None)) -> List[PayloadTemplate]:
    """List supported payload templates, optionally filtered by provider."""
    if provider:
        p_clean = provider.lower().strip()
        return [t for t in BUILTIN_TEMPLATES if t.provider == p_clean]
    return BUILTIN_TEMPLATES
