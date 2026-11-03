"""LangGraph stateful workflow for Voxia multi-turn conversations."""
from __future__ import annotations
import logging
import time
from typing import Any, Dict, List, Optional

from novora.voxia.adapters.llm import LLMAdapter
from novora.voxia.adapters.tts import TTSAdapter
from novora.voxia.models import EventType, ToolCallRecord, TurnRole, VoxiaEvent, VoxiaTurn
from novora.voxia.tools import execute_tool, get_tool_schemas

logger = logging.getLogger(__name__)


class VoxiaWorkflow:
    """
    Stateful LangGraph-style workflow for multi-turn voice conversations.
    
    State flows: receive_utterance → decide_action → [tool_call | generate_response] → synthesize
    """

    def __init__(
        self,
        llm: Optional[LLMAdapter] = None,
        tts: Optional[TTSAdapter] = None,
        test_mode: bool = False,
    ) -> None:
        self.llm = llm or LLMAdapter()
        self.tts = tts or TTSAdapter()
        self.test_mode = test_mode
        if test_mode:
            logger.warning("VoxiaWorkflow running in TEST MODE — responses are deterministic, not live inference.")

    def process_utterance(
        self,
        session: Any,  # VoxiaSession
        user_text: str,
        audio_provided: bool = False,
    ) -> Dict[str, Any]:
        """
        Main workflow entry point. Receives a user utterance and produces an agent response.
        Returns: {
          'user_turn': VoxiaTurn,
          'agent_turn': VoxiaTurn,
          'audio_bytes': Optional[bytes],
          'content_type': str,
          'tool_calls': List[ToolCallRecord],
          'events': List[VoxiaEvent],
        }
        """
        events: List[VoxiaEvent] = []

        # 1. Record user turn
        user_turn = VoxiaTurn(
            role=TurnRole.USER,
            content=user_text,
            audio_provided=audio_provided,
        )
        session.turns.append(user_turn)
        evt = session.add_event(EventType.USER_UTTERANCE_RECEIVED, {"content": user_text, "turn_id": user_turn.id})
        events.append(evt)

        # 2. Build conversation history for LLM
        history = self._build_history(session)

        # 3. Decide: tool call or direct response?
        if self.test_mode:
            agent_response, tool_calls = self._deterministic_response(session, user_text, events)
            audio_bytes = b""
            content_type = "audio/wav"
            tts_error = None
        else:
            agent_response, tool_calls = self._run_llm_with_tools(session, history, events)
            # 4. Synthesize audio
            tts_result = self.tts.synthesize(agent_response)
            audio_bytes = tts_result.get("audio_bytes")
            content_type = tts_result.get("content_type", "audio/flac")
            tts_error = tts_result.get("error")

        # 5. Record agent turn
        agent_turn = VoxiaTurn(
            role=TurnRole.AGENT,
            content=agent_response,
            tool_calls=tool_calls,
        )
        session.turns.append(agent_turn)

        response_evt = session.add_event(
            EventType.AGENT_RESPONSE_GENERATED,
            {"content": agent_response, "turn_id": agent_turn.id, "tts_error": tts_error},
        )
        events.append(response_evt)

        # 6. Update workflow state
        session.workflow_state["last_turn_id"] = agent_turn.id
        session.workflow_state["turn_count"] = len([t for t in session.turns if t.role == TurnRole.USER])

        return {
            "user_turn": user_turn,
            "agent_turn": agent_turn,
            "audio_bytes": audio_bytes,
            "content_type": content_type,
            "tool_calls": tool_calls,
            "events": events,
        }

    def _run_llm_with_tools(
        self,
        session: Any,
        history: List[Dict[str, str]],
        events: List[VoxiaEvent],
    ) -> tuple[str, List[ToolCallRecord]]:
        """Run LLM, possibly executing a tool and re-running the LLM with its result."""
        tool_calls: List[ToolCallRecord] = []
        tool_result_text: Optional[str] = None

        # First LLM pass
        llm_result = self.llm.chat(history, tool_result=tool_result_text)
        content = llm_result.get("content", "")
        tool_call_spec = llm_result.get("tool_call")

        if tool_call_spec:
            tool_name = tool_call_spec.get("tool", "")
            arguments = tool_call_spec.get("arguments", {})

            tc = ToolCallRecord(tool_name=tool_name, arguments=arguments)
            tool_req_evt = session.add_event(
                EventType.TOOL_REQUESTED,
                {"tool": tool_name, "arguments": arguments},
            )
            events.append(tool_req_evt)

            try:
                result = execute_tool(tool_name, arguments)
                tc.executed = True
                tc.result = result
                tc.executed_at = time.time()
                tool_result_text = str(result)

                exec_evt = session.add_event(
                    EventType.TOOL_EXECUTED,
                    {"tool": tool_name, "result": result},
                )
                events.append(exec_evt)

                biz_evt = session.add_event(
                    EventType.BUSINESS_RESULT_RETURNED,
                    {"tool": tool_name, "result": result},
                )
                events.append(biz_evt)

            except Exception as exc:
                tc.error = str(exc)
                tool_result_text = f"Tool error: {exc}"
                fail_evt = session.add_event(
                    EventType.TOOL_FAILED,
                    {"tool": tool_name, "error": str(exc)},
                )
                events.append(fail_evt)

            tool_calls.append(tc)

            # Second LLM pass with tool result
            history_with_tool = list(history) + [
                {"role": "assistant", "content": content},
            ]
            llm_result2 = self.llm.chat(history_with_tool, tool_result=tool_result_text)
            content = llm_result2.get("content", content)

        return content, tool_calls

    def _deterministic_response(
        self, session: Any, user_text: str, events: Optional[List[VoxiaEvent]] = None
    ) -> tuple[str, List[ToolCallRecord]]:
        """Deterministic test-mode response — clearly not live inference."""
        turn_count = len([t for t in session.turns if t.role == TurnRole.USER])
        tool_calls: List[ToolCallRecord] = []

        import re
        match = re.search(r'ORD-\d+', user_text.upper())
        if match:
            order_id = match.group(0)
            tc = ToolCallRecord(tool_name="lookup_order", arguments={"order_id": order_id})
            req_evt = session.add_event(
                EventType.TOOL_REQUESTED,
                {"tool": "lookup_order", "arguments": {"order_id": order_id}},
            )
            if events is not None:
                events.append(req_evt)
            try:
                result = execute_tool("lookup_order", {"order_id": order_id})
                tc.executed = True
                tc.result = result
                tc.executed_at = time.time()
                tool_calls.append(tc)
                exec_evt = session.add_event(
                    EventType.TOOL_EXECUTED,
                    {"tool": "lookup_order", "result": result},
                )
                if events is not None:
                    events.append(exec_evt)
                biz_evt = session.add_event(
                    EventType.BUSINESS_RESULT_RETURNED,
                    {"tool": "lookup_order", "result": result},
                )
                if events is not None:
                    events.append(biz_evt)

                if result.get("found"):
                    order = result["order"]
                    return f"[TEST MODE] Order {order_id}: {order['product']} is {order['status']}.", tool_calls
                return f"[TEST MODE] Order {order_id} was not found.", tool_calls
            except Exception as exc:
                tc.error = str(exc)
                tool_calls.append(tc)
                fail_evt = session.add_event(
                    EventType.TOOL_FAILED,
                    {"tool": "lookup_order", "error": str(exc)},
                )
                if events is not None:
                    events.append(fail_evt)
                return f"[TEST MODE] Could not look up order: {exc}", tool_calls

        if turn_count == 1:
            return "[TEST MODE] Hello! I'm Voxia, your customer support agent. How can I help you today?", []
        elif "order" in user_text.lower():
            return "[TEST MODE] Could you please provide your order reference number?", []
        else:
            return "[TEST MODE] I understand. Is there anything else I can help you with?", []

    @staticmethod
    def _build_history(session: Any) -> List[Dict[str, str]]:
        history = []
        for turn in session.turns:
            if turn.role == TurnRole.USER:
                history.append({"role": "user", "content": turn.content})
            elif turn.role == TurnRole.AGENT:
                history.append({"role": "assistant", "content": turn.content})
        return history
