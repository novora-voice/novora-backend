"""Voxia workflow shim — delegates to the real LangGraph StateGraph.

This module preserves the original ``VoxiaWorkflow`` public interface so that
existing tests and the API route need minimal changes, while internally
routing every call through the compiled LangGraph graph defined in
``novora.voxia.langgraph_workflow``.

The Pipecat audio pipeline (``novora.voxia.pipecat_pipeline``) is the
*audio transport* layer and is wired in the API route (``voxia.py``) for
turns that include raw audio bytes.  Plain-text turns go directly through
this shim → LangGraph.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from novora.voxia.adapters.llm import LLMAdapter
from novora.voxia.adapters.tts import TTSAdapter
from novora.voxia.langgraph_workflow import invoke_turn
from novora.voxia.models import EventType, ToolCallRecord, TurnRole, VoxiaEvent, VoxiaTurn

logger = logging.getLogger(__name__)


class VoxiaWorkflow:
    """
    Thin shim over the real LangGraph stateful workflow.

    Keeps the same public interface (``process_utterance``) so that existing
    tests and the FastAPI route need no changes.

    Internally, each call delegates to ``invoke_turn()`` which invokes the
    compiled ``StateGraph`` with ``MemorySaver`` checkpointing.  The
    checkpointer accumulates conversation history across turns automatically,
    keyed by ``session.id``.
    """

    def __init__(
        self,
        llm: Optional[LLMAdapter] = None,
        tts: Optional[TTSAdapter] = None,
        test_mode: bool = False,
    ) -> None:
        # Store adapters so tests / routes can inspect them (e.g. _workflow.llm.model)
        self.llm = llm or LLMAdapter()
        self.tts = tts or TTSAdapter()
        self.test_mode = test_mode
        if test_mode:
            logger.warning(
                "VoxiaWorkflow running in TEST MODE — responses are deterministic, not live inference."
            )

    def process_utterance(
        self,
        session: Any,  # VoxiaSession
        user_text: str,
        audio_provided: bool = False,
    ) -> Dict[str, Any]:
        """
        Main workflow entry point.  Accepts a user utterance and produces an
        agent response by invoking the LangGraph StateGraph.

        Returns:
            {
              'user_turn': VoxiaTurn,
              'agent_turn': VoxiaTurn,
              'audio_bytes': Optional[bytes],
              'content_type': str,
              'tool_calls': List[ToolCallRecord],
              'events': List[VoxiaEvent],
            }
        """
        # ── 1. Record user turn in session ──────────────────────────────────
        user_turn = VoxiaTurn(
            role=TurnRole.USER,
            content=user_text,
            audio_provided=audio_provided,
        )
        session.turns.append(user_turn)
        user_evt = session.add_event(
            EventType.USER_UTTERANCE_RECEIVED,
            {"content": user_text, "turn_id": user_turn.id},
        )

        # ── 2. Invoke LangGraph ─────────────────────────────────────────────
        lg_result = invoke_turn(
            session_id=session.id,
            user_text=user_text,
            audio_provided=audio_provided,
            test_mode=self.test_mode,
            llm=self.llm if not self.test_mode else None,
            tts=self.tts if not self.test_mode else None,
        )

        agent_text: str = lg_result["agent_text"]
        tool_call_dicts: List[Dict[str, Any]] = lg_result.get("tool_calls", [])
        lg_events: List[Dict[str, Any]] = lg_result.get("events", [])
        audio_bytes: Optional[bytes] = lg_result.get("audio_bytes")
        content_type: str = lg_result.get("content_type", "audio/flac")
        tts_error: Optional[str] = lg_result.get("tts_error")

        # ── 3. Reconstruct ToolCallRecord objects from LangGraph dicts ──────
        tool_calls: List[ToolCallRecord] = []
        for tc_dict in tool_call_dicts:
            tc = ToolCallRecord(
                tool_name=tc_dict["tool_name"],
                arguments=tc_dict.get("arguments", {}),
            )
            tc.executed = tc_dict.get("executed", False)
            tc.result = tc_dict.get("result")
            tc.executed_at = tc_dict.get("executed_at")
            tc.error = tc_dict.get("error")
            tool_calls.append(tc)

        # ── 4. Replay LangGraph events onto the session ─────────────────────
        collected_events: List[VoxiaEvent] = [user_evt]
        for evt_dict in lg_events:
            try:
                et = EventType(evt_dict["event_type"])
            except (KeyError, ValueError):
                continue
            evt = session.add_event(et, evt_dict.get("payload", {}))
            collected_events.append(evt)

        # ── 5. Record agent turn ─────────────────────────────────────────────
        agent_turn = VoxiaTurn(
            role=TurnRole.AGENT,
            content=agent_text,
            tool_calls=tool_calls,
        )
        session.turns.append(agent_turn)

        response_evt = session.add_event(
            EventType.AGENT_RESPONSE_GENERATED,
            {
                "content": agent_text,
                "turn_id": agent_turn.id,
                "tts_error": tts_error,
            },
        )
        collected_events.append(response_evt)

        # ── 6. Update workflow state snapshot ───────────────────────────────
        session.workflow_state["last_turn_id"] = agent_turn.id
        session.workflow_state["turn_count"] = len(
            [t for t in session.turns if t.role == TurnRole.USER]
        )

        return {
            "user_turn": user_turn,
            "agent_turn": agent_turn,
            "audio_bytes": audio_bytes,
            "content_type": content_type,
            "tool_calls": tool_calls,
            "events": collected_events,
        }
