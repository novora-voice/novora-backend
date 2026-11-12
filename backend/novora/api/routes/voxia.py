"""Voxia voice runtime API routes.

Audio turns are processed through the Pipecat audio pipeline
(VoxiaAudioPipeline) which handles frame buffering and routes the completed
transcript into the LangGraph StateGraph (invoke_turn).

Plain-text turns skip Pipecat and go directly to the LangGraph graph via
VoxiaWorkflow.process_utterance, which internally calls invoke_turn.
"""
from __future__ import annotations
import asyncio
import base64
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from novora.voxia.adapters.stt import STTAdapter
from novora.voxia.adapters.tts import TTSAdapter
from novora.voxia.models import SessionStatus, VoxiaSession
from novora.voxia.novora_bridge import session_to_conversation
from novora.voxia.pipecat_pipeline import VoxiaAudioPipeline
from novora.voxia.session_store import VoxiaSessionStore
from novora.voxia.workflow import VoxiaWorkflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/voxia", tags=["Voxia"])

# Module-level singletons (initialized at import time, not at request time)
_stt = STTAdapter()
_tts = TTSAdapter()
_session_store = VoxiaSessionStore(max_sessions=int(os.getenv("VOXIA_MAX_CONCURRENT_SESSIONS", "50")))
_workflow = VoxiaWorkflow(llm=None, tts=_tts)  # LLM created inside workflow


class StartSessionRequest(BaseModel):
    scenario_id: Optional[str] = None
    agent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubmitTurnRequest(BaseModel):
    text: Optional[str] = None
    audio_base64: Optional[str] = None
    audio_mime_type: str = "audio/webm"


class SessionResponse(BaseModel):
    session_id: str
    status: str
    turn_count: int
    events: list


@router.post("/sessions", status_code=201)
def start_session(req: StartSessionRequest) -> Dict[str, Any]:
    """Start a new Voxia voice session."""
    session = VoxiaSession(scenario_id=req.scenario_id, agent_id=req.agent_id, metadata=req.metadata)
    from novora.voxia.models import EventType
    session.add_event(EventType.SESSION_STARTED, {"scenario_id": req.scenario_id, "agent_id": req.agent_id})
    _session_store.create(session)
    logger.info("Started Voxia session %s", session.id)
    return {"session_id": session.id, "status": session.status.value, "created_at": session.created_at}


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    """Get session state."""
    session = _session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session.to_dict()


@router.post("/sessions/{session_id}/turns")
async def submit_turn(session_id: str, req: SubmitTurnRequest) -> Dict[str, Any]:
    """
    Submit a user turn. Accepts either 'text' or 'audio_base64'.

    - Audio turns are routed through the Pipecat audio pipeline
      (VoxiaAudioPipeline) which handles VAD / turn detection before passing
      the transcript to the LangGraph StateGraph.
    - Plain-text turns bypass Pipecat and go directly to the LangGraph graph
      via VoxiaWorkflow.process_utterance.

    Returns the agent's text response and base64-encoded audio.
    """
    session = _session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Session is not active.")

    user_text = req.text
    audio_provided = False

    if req.audio_base64 and not user_text:
        # ── Audio turn: route through Pipecat pipeline ─────────────────────
        try:
            audio_bytes = base64.b64decode(req.audio_base64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 audio.")

        pipeline = VoxiaAudioPipeline(
            session_id=session.id,
            test_mode=_workflow.test_mode,
            stt=_stt,
            llm=_workflow.llm if not _workflow.test_mode else None,
            tts=_workflow.tts if not _workflow.test_mode else None,
        )
        try:
            lg_result = await pipeline.process_audio_turn(audio_bytes, req.audio_mime_type)
        except Exception as exc:
            logger.warning("Pipecat audio pipeline failed (%s); falling back to direct STT+LLM", exc)
            stt_result = _stt.transcribe(audio_bytes, req.audio_mime_type)
            if stt_result.get("error"):
                raise HTTPException(status_code=502, detail=f"STT error: {stt_result['error']}")
            user_text = stt_result.get("text", "")
            audio_provided = True
            lg_result = None

        if lg_result is not None:
            # Pipecat pipeline succeeded — reconstruct session turns from result
            result = _reconcile_pipeline_result(session, req.audio_base64, lg_result)
            _session_store.save(session)
            audio_resp = result.get("audio_bytes")
            audio_b64 = base64.b64encode(audio_resp).decode() if audio_resp else None
            return {
                "session_id": session_id,
                "user_turn": result["user_turn"].to_dict(),
                "agent_turn": result["agent_turn"].to_dict(),
                "agent_text": result["agent_turn"].content,
                "audio_base64": audio_b64,
                "audio_content_type": result.get("content_type", "audio/flac"),
                "events": [e.to_dict() for e in result["events"]],
            }

        # Fallthrough: user_text was set by the fallback STT above
    else:
        audio_provided = False

    if not user_text:
        raise HTTPException(status_code=400, detail="Either 'text' or 'audio_base64' must be provided.")

    # ── Text turn: route directly through VoxiaWorkflow → LangGraph ────────
    result = _workflow.process_utterance(session, user_text, audio_provided=audio_provided)
    _session_store.save(session)

    audio_resp = result.get("audio_bytes")
    audio_b64 = base64.b64encode(audio_resp).decode() if audio_resp else None

    return {
        "session_id": session_id,
        "user_turn": result["user_turn"].to_dict(),
        "agent_turn": result["agent_turn"].to_dict(),
        "agent_text": result["agent_turn"].content,
        "audio_base64": audio_b64,
        "audio_content_type": result.get("content_type", "audio/flac"),
        "events": [e.to_dict() for e in result["events"]],
    }


def _reconcile_pipeline_result(
    session: VoxiaSession,
    audio_base64: str,
    lg_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    After a successful Pipecat→LangGraph pipeline run, record the turns and
    events on the session object so the session store stays consistent.
    This mirrors what VoxiaWorkflow.process_utterance does.
    """
    from novora.voxia.models import EventType, ToolCallRecord, TurnRole, VoxiaTurn

    # Derive transcribed text from LangGraph result events if available
    # (The pipeline already transcribed; we reconstruct from agent_text context)
    user_text = lg_result.get("user_text") or _extract_user_text_from_lg_result(lg_result, session)

    user_turn = VoxiaTurn(role=TurnRole.USER, content=user_text, audio_provided=True)
    session.turns.append(user_turn)
    user_evt = session.add_event(
        EventType.USER_UTTERANCE_RECEIVED,
        {"content": user_text, "turn_id": user_turn.id},
    )

    # Reconstruct ToolCallRecord objects
    tool_calls = []
    for tc_dict in lg_result.get("tool_calls", []):
        from novora.voxia.models import ToolCallRecord
        tc = ToolCallRecord(
            tool_name=tc_dict["tool_name"],
            arguments=tc_dict.get("arguments", {}),
        )
        tc.executed = tc_dict.get("executed", False)
        tc.result = tc_dict.get("result")
        tc.executed_at = tc_dict.get("executed_at")
        tc.error = tc_dict.get("error")
        tool_calls.append(tc)

    # Replay LangGraph events
    from novora.voxia.models import EventType as ET
    collected_events = [user_evt]
    for evt_dict in lg_result.get("events", []):
        try:
            et = ET(evt_dict["event_type"])
        except (KeyError, ValueError):
            continue
        evt = session.add_event(et, evt_dict.get("payload", {}))
        collected_events.append(evt)

    agent_turn = VoxiaTurn(
        role=TurnRole.AGENT,
        content=lg_result["agent_text"],
        tool_calls=tool_calls,
    )
    session.turns.append(agent_turn)

    response_evt = session.add_event(
        EventType.AGENT_RESPONSE_GENERATED,
        {
            "content": lg_result["agent_text"],
            "turn_id": agent_turn.id,
            "tts_error": lg_result.get("tts_error"),
        },
    )
    collected_events.append(response_evt)

    session.workflow_state["last_turn_id"] = agent_turn.id
    session.workflow_state["turn_count"] = len(
        [t for t in session.turns if t.role == TurnRole.USER]
    )

    return {
        "user_turn": user_turn,
        "agent_turn": agent_turn,
        "audio_bytes": lg_result.get("audio_bytes"),
        "content_type": lg_result.get("content_type", "audio/flac"),
        "tool_calls": tool_calls,
        "events": collected_events,
    }


def _extract_user_text_from_lg_result(
    lg_result: Dict[str, Any], session: VoxiaSession
) -> str:
    """Best-effort extraction of the user's transcribed text from the pipeline result."""
    # LangGraph events may contain USER_UTTERANCE_RECEIVED payload
    for evt_dict in lg_result.get("events", []):
        if evt_dict.get("event_type") == "user_utterance_received":
            payload = evt_dict.get("payload", {})
            if payload.get("content"):
                return payload["content"]
    # Fall back to a placeholder — the real text is in the Pipecat processor
    return "[transcribed audio]"


@router.post("/sessions/{session_id}/end")
def end_session(session_id: str, request: Request) -> Dict[str, Any]:
    """End a session and optionally submit it to Novora for evaluation."""
    session = _session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    import time
    session.status = SessionStatus.ENDED
    session.ended_at = time.time()
    from novora.voxia.models import EventType
    session.add_event(EventType.SESSION_ENDED, {"turn_count": len(session.turns)})
    _session_store.save(session)

    # Optionally convert to Novora conversation and persist
    conversation_id = None
    try:
        conv_repo = getattr(request.app.state, "conversation_repository", None)
        if conv_repo:
            conv = session_to_conversation(session)
            conv_repo.save(conv)
            conversation_id = conv.id
            logger.info("Voxia session %s saved as conversation %s", session_id, conversation_id)
    except Exception as exc:
        logger.warning("Could not persist Voxia session to Novora: %s", exc)

    return {
        "session_id": session_id,
        "status": session.status.value,
        "conversation_id": conversation_id,
        "turn_count": len(session.turns),
    }


@router.get("/sessions/{session_id}/events")
def get_events(session_id: str) -> Dict[str, Any]:
    """Get all runtime events for a session."""
    session = _session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"session_id": session_id, "events": [e.to_dict() for e in session.events]}


class STTRequest(BaseModel):
    audio_base64: Optional[str] = None
    audio_mime_type: str = "audio/webm"


@router.post("/stt")
async def transcribe_audio(request: Request) -> Dict[str, Any]:
    """Transcribe audio via HF remote STT. Accepts raw audio bytes or JSON with audio_base64."""
    content_type = request.headers.get("content-type", "")
    audio_bytes: bytes = b""
    mime_type = "audio/webm"

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body.")
        b64_data = body.get("audio_base64")
        if not b64_data:
            raise HTTPException(status_code=400, detail="Missing 'audio_base64' in JSON body.")
        try:
            audio_bytes = base64.b64decode(b64_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 audio data.")
        mime_type = body.get("audio_mime_type", "audio/webm")
    else:
        audio_bytes = await request.body()
        mime_type = content_type or "audio/webm"

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    result = _stt.transcribe(audio_bytes, mime_type)
    if result.get("error"):
        raise HTTPException(status_code=502, detail=f"STT error: {result['error']}")
    return result


@router.post("/tts")
def synthesize_speech(body: Dict[str, str] = Body(...)) -> Response:
    """Synthesize text to speech via HF remote TTS. Returns audio bytes."""
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="'text' field is required.")
    result = _tts.synthesize(text)
    if result.get("error"):
        raise HTTPException(status_code=502, detail=f"TTS error: {result['error']}")
    return Response(
        content=result["audio_bytes"],
        media_type=result.get("content_type", "audio/flac"),
    )


@router.get("/status")
def voxia_status() -> Dict[str, Any]:
    """Report Voxia runtime status."""
    return {
        "active_sessions": _session_store.count(),
        "stt_configured": _stt.is_configured(),
        "tts_configured": _tts.is_configured(),
        "stt_model": _stt.model,
        "tts_model": _tts.model,
        "llm_model": _workflow.llm.model,
    }
