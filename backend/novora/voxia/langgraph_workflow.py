"""Real LangGraph stateful workflow for Voxia multi-turn conversations.

Architecture
------------
Browser audio (or text) → FastAPI route
  → pipecat_pipeline.py (audio frames, VAD, transcription)
    → LangGraph StateGraph (this file)
      ├── agent_node       (HF LLM via LLMAdapter)
      └── synthesize_node  (HF TTS via TTSAdapter)
    → LangGraph MemorySaver checkpointer persists state per thread_id=session_id

The graph is compiled once at module level and reused across all requests.
Each turn calls:
    _graph.invoke(state, config={"configurable": {"thread_id": session_id}})
The MemorySaver automatically accumulates messages across turns for true
stateful multi-turn conversations.

Adapter injection
-----------------
To support unit tests that inject mock LLM/TTS adapters, we use a lightweight
per-turn adapter registry (``_turn_adapters``).  Before invoking the graph,
callers may call ``register_turn_adapters(session_id, llm, tts)`` to register
non-default adapters.  The node functions look up the registry using the
session_id stored in the graph state.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from novora.voxia.adapters.llm import LLMAdapter
from novora.voxia.adapters.tts import TTSAdapter
from novora.voxia.models import EventType, ToolCallRecord, TurnRole, VoxiaEvent, VoxiaTurn
from novora.voxia.tools import execute_tool, get_tool_schemas

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-turn adapter registry
# Maps session_id → {"llm": LLMAdapter|None, "tts": TTSAdapter|None}
# Populated by register_turn_adapters() before graph.invoke(); cleared after.
# ---------------------------------------------------------------------------
_turn_adapters: Dict[str, Dict[str, Any]] = {}


def register_turn_adapters(
    session_id: str,
    llm: Optional[LLMAdapter] = None,
    tts: Optional[TTSAdapter] = None,
) -> None:
    """Register custom adapters for the next turn of a session."""
    _turn_adapters[session_id] = {"llm": llm, "tts": tts}


def _get_llm(session_id: str) -> LLMAdapter:
    """Return the registered LLM adapter for this session, or a fresh default."""
    adapters = _turn_adapters.get(session_id, {})
    return adapters.get("llm") or LLMAdapter()


def _get_tts(session_id: str) -> TTSAdapter:
    """Return the registered TTS adapter for this session, or a fresh default."""
    adapters = _turn_adapters.get(session_id, {})
    return adapters.get("tts") or TTSAdapter()


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class VoxiaState(TypedDict):
    """LangGraph state — accumulated across turns via MemorySaver checkpointer."""

    # Conversation messages (user + assistant); add_messages reducer appends
    messages: Annotated[list, add_messages]

    # Per-turn data (reset each invocation via state merging)
    session_id: str
    test_mode: bool
    audio_bytes: Optional[bytes]
    content_type: str
    user_text: str
    audio_provided: bool

    # Knowledge Base retrieval context (injected per-turn when KB IDs are configured)
    knowledge_base_ids: List[str]           # KB IDs authorized for this agent
    knowledge_org_id: str                   # Org the agent belongs to
    retrieval_mode: str                     # "vector" | "graph" | "hybrid"
    retrieval_top_k: int                    # number of chunks to retrieve
    retrieval_evidence: List[Dict[str, Any]]  # evidence items from KBs (serialised)
    retrieval_latency_ms: float             # total retrieval time

    # Outputs produced during this turn
    agent_text: str
    tool_calls: List[Dict[str, Any]]  # serialised ToolCallRecord dicts
    events: List[Dict[str, Any]]       # serialised VoxiaEvent dicts
    tts_error: Optional[str]


# ---------------------------------------------------------------------------
# Node helpers
# ---------------------------------------------------------------------------

def _make_event_dict(event_type: EventType, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": f"evt_{int(time.time() * 1000)}",
        "event_type": event_type.value,
        "payload": payload,
        "timestamp": time.time(),
    }


def _deterministic_response(
    user_text: str,
    turn_count: int,
    events: List[Dict[str, Any]],
) -> tuple[str, List[Dict[str, Any]]]:
    """Return a deterministic text response for test_mode (no HF calls)."""
    tool_call_dicts: List[Dict[str, Any]] = []

    match = re.search(r"ORD-\d+", user_text.upper())
    if match:
        order_id = match.group(0)
        req_evt = _make_event_dict(
            EventType.TOOL_REQUESTED,
            {"tool": "lookup_order", "arguments": {"order_id": order_id}},
        )
        events.append(req_evt)
        try:
            result = execute_tool("lookup_order", {"order_id": order_id})
            tc_dict = {
                "tool_name": "lookup_order",
                "arguments": {"order_id": order_id},
                "executed": True,
                "result": result,
                "executed_at": time.time(),
                "error": None,
            }
            tool_call_dicts.append(tc_dict)
            exec_evt = _make_event_dict(
                EventType.TOOL_EXECUTED, {"tool": "lookup_order", "result": result}
            )
            events.append(exec_evt)
            biz_evt = _make_event_dict(
                EventType.BUSINESS_RESULT_RETURNED,
                {"tool": "lookup_order", "result": result},
            )
            events.append(biz_evt)

            if result.get("found"):
                order = result["order"]
                return (
                    f"[TEST MODE] Order {order_id}: {order['product']} is {order['status']}.",
                    tool_call_dicts,
                )
            return f"[TEST MODE] Order {order_id} was not found.", tool_call_dicts
        except Exception as exc:
            fail_evt = _make_event_dict(
                EventType.TOOL_FAILED, {"tool": "lookup_order", "error": str(exc)}
            )
            events.append(fail_evt)
            tc_dict = {
                "tool_name": "lookup_order",
                "arguments": {"order_id": order_id},
                "executed": False,
                "result": None,
                "executed_at": None,
                "error": str(exc),
            }
            tool_call_dicts.append(tc_dict)
            return f"[TEST MODE] Could not look up order: {exc}", tool_call_dicts

    if turn_count == 1:
        return "[TEST MODE] Hello! I'm Voxia, your customer support agent. How can I help you today?", []
    if "order" in user_text.lower():
        return "[TEST MODE] Could you please provide your order reference number?", []
    return "[TEST MODE] I understand. Is there anything else I can help you with?", []


# ---------------------------------------------------------------------------
# Knowledge Base Retrieval helper
# ---------------------------------------------------------------------------

def _retrieve_knowledge(
    state: VoxiaState,
) -> tuple[List[Dict[str, Any]], float]:
    """Retrieve relevant chunks from authorized knowledge bases.

    Returns (evidence_dicts, latency_ms). Never raises — retrieval failures
    are logged and an empty list is returned so the agent can still answer.
    """
    kb_ids: List[str] = state.get("knowledge_base_ids") or []
    org_id: str = state.get("knowledge_org_id", "")
    if not kb_ids or not org_id:
        return [], 0.0

    query = state.get("user_text", "")
    if not query:
        return [], 0.0

    try:
        from novora.adapters.knowledge.retrieval import KnowledgeRetrievalService
        from novora.api.auth_utils import SessionLocal
        from novora.persistence.models import DBKnowledgeBase

        retrieval_svc = KnowledgeRetrievalService()
        retrieval_mode = state.get("retrieval_mode") or "vector"
        top_k = int(state.get("retrieval_top_k") or 5)
        t0 = time.time()
        all_evidence: List[Dict[str, Any]] = []

        db = SessionLocal()
        try:
            for kb_id in kb_ids:
                kb = db.query(DBKnowledgeBase).filter(
                    DBKnowledgeBase.id == kb_id,
                    DBKnowledgeBase.org_id == org_id,
                ).first()
                if not kb:
                    logger.warning("KB %s not found or org mismatch — skipping", kb_id)
                    continue
                try:
                    trace = retrieval_svc.retrieve(
                        kb=kb,
                        query=query,
                        org_id=org_id,
                        retrieval_mode=retrieval_mode,
                        top_k=top_k,
                    )
                    for ev in trace.evidence:
                        all_evidence.append({
                            "document_id": ev.document_id,
                            "chunk_id": ev.chunk_id,
                            "text": ev.text,
                            "score": ev.score,
                            "metadata": ev.metadata,
                            "source": ev.source,
                            "knowledge_base_id": kb_id,
                        })
                except Exception as kb_exc:
                    logger.warning("Retrieval from KB %s failed: %s", kb_id, kb_exc)
        finally:
            db.close()

        latency_ms = round((time.time() - t0) * 1000.0, 2)
        # Deduplicate by chunk_id and sort by score descending
        seen: set = set()
        deduped = []
        for ev in sorted(all_evidence, key=lambda x: x["score"], reverse=True):
            if ev["chunk_id"] not in seen:
                seen.add(ev["chunk_id"])
                deduped.append(ev)
        return deduped[:top_k], latency_ms

    except Exception as exc:
        logger.warning("Knowledge retrieval failed — continuing without KB context: %s", exc)
        return [], 0.0


def _build_kb_context_preamble(evidence: List[Dict[str, Any]]) -> str:
    """Format retrieved evidence as a system preamble for the LLM."""
    if not evidence:
        return ""
    lines = ["[KNOWLEDGE BASE CONTEXT — use this information to answer accurately]"]
    for i, ev in enumerate(evidence, 1):
        lines.append(f"\n--- Source {i} (score: {ev['score']:.2f}) ---")
        lines.append(ev["text"])
    lines.append("\n[END KNOWLEDGE BASE CONTEXT]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def agent_node(state: VoxiaState) -> Dict[str, Any]:
    """LLM decision node — calls HF LLM or deterministic test response.

    When knowledge_base_ids are configured in state, retrieves relevant chunks
    from the authorized knowledge bases and injects them as context before the
    LLM call. The retrieval evidence is stored in the returned state so the
    evaluation engine can inspect it.
    """
    user_text = state["user_text"]
    test_mode = state.get("test_mode", False)
    session_id = state["session_id"]
    events: List[Dict[str, Any]] = list(state.get("events", []))

    # ── Knowledge Base retrieval ──────────────────────────────────────────
    evidence, retrieval_latency = _retrieve_knowledge(state)
    kb_preamble = _build_kb_context_preamble(evidence)
    if evidence:
        logger.info(
            "KB retrieval: %d chunks retrieved in %.1fms for session %s",
            len(evidence), retrieval_latency, session_id,
        )
        events.append(_make_event_dict(
            EventType.BUSINESS_RESULT_RETURNED,
            {"type": "kb_retrieval", "chunks": len(evidence), "latency_ms": retrieval_latency},
        ))

    # Count user messages already in the conversation to determine turn number
    turn_count = sum(
        1
        for m in state["messages"]
        if (getattr(m, "type", None) == "human")
        or (isinstance(m, dict) and m.get("role") == "user")
    )

    if test_mode:
        agent_text, tool_call_dicts = _deterministic_response(user_text, turn_count, events)
        return {
            "agent_text": agent_text,
            "tool_calls": tool_call_dicts,
            "events": events,
            "audio_bytes": b"",
            "content_type": "audio/wav",
            "tts_error": None,
            "retrieval_evidence": evidence,
            "retrieval_latency_ms": retrieval_latency,
            # Append assistant message to the LangGraph conversation
            "messages": [{"role": "assistant", "content": agent_text}],
        }

    # Live mode: build history from accumulated messages then call LLM
    history: List[Dict[str, str]] = []

    # Inject KB context as a system message if we have evidence
    if kb_preamble:
        history.append({"role": "system", "content": kb_preamble})

    for msg in state["messages"]:
        if isinstance(msg, dict):
            history.append({"role": msg["role"], "content": msg["content"]})
        else:
            # LangGraph BaseMessage objects
            role = "user" if getattr(msg, "type", "") == "human" else "assistant"
            history.append({"role": role, "content": msg.content})

    llm = _get_llm(session_id)
    llm_result = llm.chat(history, tool_result=None)
    content = llm_result.get("content", "")
    tool_call_spec = llm_result.get("tool_call")

    tool_call_dicts: List[Dict[str, Any]] = []

    if tool_call_spec:
        tool_name = tool_call_spec.get("tool", "")
        arguments = tool_call_spec.get("arguments", {})

        req_evt = _make_event_dict(
            EventType.TOOL_REQUESTED, {"tool": tool_name, "arguments": arguments}
        )
        events.append(req_evt)

        try:
            result = execute_tool(tool_name, arguments)
            tc_dict = {
                "tool_name": tool_name,
                "arguments": arguments,
                "executed": True,
                "result": result,
                "executed_at": time.time(),
                "error": None,
            }
            exec_evt = _make_event_dict(
                EventType.TOOL_EXECUTED, {"tool": tool_name, "result": result}
            )
            events.append(exec_evt)
            biz_evt = _make_event_dict(
                EventType.BUSINESS_RESULT_RETURNED,
                {"tool": tool_name, "result": result},
            )
            events.append(biz_evt)
            tool_result_text = str(result)

        except Exception as exc:
            tc_dict = {
                "tool_name": tool_name,
                "arguments": arguments,
                "executed": False,
                "result": None,
                "executed_at": None,
                "error": str(exc),
            }
            fail_evt = _make_event_dict(
                EventType.TOOL_FAILED, {"tool": tool_name, "error": str(exc)}
            )
            events.append(fail_evt)
            tool_result_text = f"Tool error: {exc}"

        tool_call_dicts.append(tc_dict)

        # Second LLM pass with tool result injected
        history_with_tool = list(history) + [{"role": "assistant", "content": content}]
        llm_result2 = llm.chat(history_with_tool, tool_result=tool_result_text)
        content = llm_result2.get("content", content)

    return {
        "agent_text": content,
        "tool_calls": tool_call_dicts,
        "events": events,
        "retrieval_evidence": evidence,
        "retrieval_latency_ms": retrieval_latency,
        "messages": [{"role": "assistant", "content": content}],
    }


def synthesize_node(state: VoxiaState) -> Dict[str, Any]:
    """TTS synthesis node — converts agent text to audio bytes."""
    test_mode = state.get("test_mode", False)
    if test_mode:
        # Already set audio_bytes=b"" in agent_node for test mode
        return {}

    session_id = state["session_id"]
    tts = _get_tts(session_id)
    agent_text = state.get("agent_text", "")
    tts_result = tts.synthesize(agent_text)
    return {
        "audio_bytes": tts_result.get("audio_bytes"),
        "content_type": tts_result.get("content_type", "audio/flac"),
        "tts_error": tts_result.get("error"),
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_voxia_graph() -> StateGraph:
    """Build the VoxiaStateGraph (not yet compiled)."""
    graph = StateGraph(VoxiaState)

    graph.add_node("agent", agent_node)
    graph.add_node("synthesize", synthesize_node)

    graph.add_edge(START, "agent")
    graph.add_edge("agent", "synthesize")
    graph.add_edge("synthesize", END)

    return graph


# ---------------------------------------------------------------------------
# Module-level singleton — compiled once, reused across all requests
# ---------------------------------------------------------------------------

_checkpointer = MemorySaver()
_graph = build_voxia_graph().compile(checkpointer=_checkpointer)


# ---------------------------------------------------------------------------
# Public API — used by workflow.py shim and pipecat_pipeline.py
# ---------------------------------------------------------------------------

def invoke_turn(
    session_id: str,
    user_text: str,
    audio_provided: bool = False,
    test_mode: bool = False,
    llm: Optional[LLMAdapter] = None,
    tts: Optional[TTSAdapter] = None,
) -> Dict[str, Any]:
    """
    Invoke one turn of the LangGraph workflow for a given session.

    Registers ``llm`` / ``tts`` adapters (if provided) in the per-turn
    registry so the graph nodes pick them up; clears the registry after the
    turn completes.

    Returns a dict with keys:
        agent_text, tool_calls, events, audio_bytes, content_type, tts_error
    """
    # Register custom adapters for this turn (supports mock injection in tests)
    if llm is not None or tts is not None:
        register_turn_adapters(session_id, llm=llm, tts=tts)

    input_state: Dict[str, Any] = {
        "messages": [{"role": "user", "content": user_text}],
        "session_id": session_id,
        "test_mode": test_mode,
        "user_text": user_text,
        "audio_provided": audio_provided,
        "audio_bytes": None,
        "content_type": "audio/flac",
        "agent_text": "",
        "tool_calls": [],
        "events": [],
        "tts_error": None,
    }
    config = {"configurable": {"thread_id": session_id}}
    try:
        result = _graph.invoke(input_state, config=config)
    finally:
        # Always clear the adapter registry after the turn
        _turn_adapters.pop(session_id, None)

    return {
        "agent_text": result.get("agent_text", ""),
        "tool_calls": result.get("tool_calls", []),
        "events": result.get("events", []),
        "audio_bytes": result.get("audio_bytes", b""),
        "content_type": result.get("content_type", "audio/flac"),
        "tts_error": result.get("tts_error"),
    }
