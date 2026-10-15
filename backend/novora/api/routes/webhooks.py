from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Query, Request, status

from novora.adapters.providers.assemblyai import AssemblyAIAdapter
from novora.adapters.providers.elevenlabs import ElevenLabsAdapter
from novora.adapters.providers.retell import RetellAdapter
from novora.adapters.providers.transcript_importer import TranscriptImporter
from novora.adapters.providers.twilio import TwilioAdapter
from novora.adapters.providers.vapi import VapiAdapter
from novora.api.schemas import (
    ConversationResponse,
    ImportTranscriptRequest,
    TelephonyCallResponse,
)

def register_webhook_routes(
    app: FastAPI,
    conversations: Any,
    scenarios: Any,
    evaluations: Any,
    telephony: Any,
    webhooks: Any,
    engine: Any,
    elevenlabs_secret: str,
    twilio_auth_token: str,
) -> None:
    el_adapter = ElevenLabsAdapter(webhook_repo=webhooks)
    tw_adapter = TwilioAdapter()
    aai_adapter = AssemblyAIAdapter()
    vapi_adapter = VapiAdapter()
    retell_adapter = RetellAdapter()

    @app.post("/api/v1/conversations/import-transcript", response_model=ConversationResponse, tags=["Ingestion"])
    def import_transcript(req: ImportTranscriptRequest) -> ConversationResponse:
        if req.text:
            conv = TranscriptImporter.from_text(text=req.text, scenario_id=req.scenario_id)
        elif req.records:
            conv = TranscriptImporter.from_records(records=req.records, scenario_id=req.scenario_id)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either 'text' or 'records' must be provided.")
        conversations.save(conv)
        return ConversationResponse.model_validate(conv.model_dump())

    @app.post("/api/v1/webhooks/elevenlabs", status_code=status.HTTP_200_OK, tags=["Webhooks"])
    async def elevenlabs_webhook(
        request: Request,
        elevenlabs_signature: Optional[str] = Header(None, alias="elevenlabs-signature"),
        x_timestamp: Optional[str] = Header(None, alias="x-timestamp"),
        scenario_id: Optional[str] = Query(None),
        auto_evaluate: bool = Query(False),
    ):
        raw_body = await request.body()
        payload = await request.json()
        verified = False
        if elevenlabs_signature:
            verified = el_adapter.verify_webhook_signature(
                raw_body=raw_body, signature=elevenlabs_signature, secret=elevenlabs_secret, timestamp=x_timestamp or ""
            )
            if not verified:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ElevenLabs webhook signature.")

        event_id = str(payload.get("conversation_id", payload.get("id", "")))
        is_dup, conv = el_adapter.process_webhook_idempotent(
            event_id=event_id, payload=payload, signature_verified=verified, scenario_id=scenario_id
        )
        if is_dup:
            return {"status": "already_processed", "event_id": event_id}
        if conv:
            conversations.save(conv)

        result: Dict[str, Any] = {
            "status": "processed",
            "conversation_id": conv.id if conv else None,
            "message_count": len(conv.messages) if conv else 0,
        }
        if auto_evaluate and scenario_id and conv:
            scen = scenarios.get(scenario_id)
            if scen:
                report = engine.evaluate(conversation=conv, scenario=scen)
                evaluations.save(report)
                result["evaluation_report_id"] = report.id
                result["overall_status"] = report.overall_status.value
        return result

    @app.post("/api/v1/webhooks/twilio", response_model=TelephonyCallResponse, tags=["Webhooks"])
    async def twilio_webhook(
        request: Request,
        x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
    ) -> TelephonyCallResponse:
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            payload = dict(await request.form())
        else:
            payload = await request.json()

        if x_twilio_signature and twilio_auth_token:
            params = {k: str(v) for k, v in payload.items()}
            if not tw_adapter.verify_webhook_signature(url=str(request.url), params=params, signature=x_twilio_signature, auth_token=twilio_auth_token):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Twilio signature header.")

        record = tw_adapter.parse_telephony_event(payload)
        saved = telephony.save(record)
        return TelephonyCallResponse.model_validate(saved.model_dump())

    @app.post("/api/v1/webhooks/assemblyai", response_model=ConversationResponse, tags=["Webhooks"])
    async def assemblyai_webhook(payload: Dict[str, Any], scenario_id: Optional[str] = Query(None)) -> ConversationResponse:
        conv = aai_adapter.parse_transcription_result(payload=payload, scenario_id=scenario_id)
        conversations.save(conv)
        return ConversationResponse.model_validate(conv.model_dump())

    @app.post("/api/v1/webhooks/vapi", response_model=ConversationResponse, tags=["Webhooks"])
    async def vapi_webhook(payload: Dict[str, Any], scenario_id: Optional[str] = Query(None)) -> ConversationResponse:
        conv = vapi_adapter.parse_conversation_webhook(payload=payload, scenario_id=scenario_id)
        conversations.save(conv)
        return ConversationResponse.model_validate(conv.model_dump())

    @app.post("/api/v1/webhooks/retell", response_model=ConversationResponse, tags=["Webhooks"])
    async def retell_webhook(payload: Dict[str, Any], scenario_id: Optional[str] = Query(None)) -> ConversationResponse:
        conv = retell_adapter.parse_conversation_webhook(payload=payload, scenario_id=scenario_id)
        conversations.save(conv)
        return ConversationResponse.model_validate(conv.model_dump())

    @app.get("/api/v1/telephony/calls", response_model=List[TelephonyCallResponse], tags=["Telephony"])
    def list_telephony_calls(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> List[TelephonyCallResponse]:
        items = telephony.list_all(limit=limit, offset=offset)
        return [TelephonyCallResponse.model_validate(r.model_dump()) for r in items]

    @app.get("/api/v1/telephony/{call_sid}", response_model=TelephonyCallResponse, tags=["Telephony"])
    def get_telephony_call(call_sid: str) -> TelephonyCallResponse:
        record = telephony.get(call_sid)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Call SID '{call_sid}' not found.")
        return TelephonyCallResponse.model_validate(record.model_dump())

