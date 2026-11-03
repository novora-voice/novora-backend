"""Bridge between Voxia sessions and the Novora evaluation pipeline."""
from __future__ import annotations
import logging
from typing import Any, Optional

from novora.core.enums import ConversationSource, MessageRole
from novora.core.models import Conversation, ConversationMessage
from novora.voxia.models import TurnRole, VoxiaSession

logger = logging.getLogger(__name__)


def session_to_conversation(session: VoxiaSession) -> Conversation:
    """Convert a completed VoxiaSession to a Novora Conversation for evaluation."""
    messages = []
    seq = 0
    for turn in session.turns:
        if turn.role == TurnRole.USER:
            role = MessageRole.CUSTOMER
        elif turn.role == TurnRole.AGENT:
            role = MessageRole.AGENT
        elif turn.role == TurnRole.TOOL:
            role = MessageRole.TOOL
        else:
            role = MessageRole.SYSTEM

        if turn.content:
            msg = ConversationMessage(
                role=role,
                content=turn.content,
                sequence=seq,
                metadata={"voxia_turn_id": turn.id, "audio_provided": turn.audio_provided},
            )
            messages.append(msg)
            seq += 1

    trusted_actions = []
    for turn in session.turns:
        for tc in turn.tool_calls:
            trusted_actions.append({
                "action_type": f"tool_call:{tc.tool_name}",
                "status": "success" if tc.executed and not tc.error else "failure",
                "payload": {"arguments": tc.arguments, "result": tc.result, "error": tc.error},
                "verified": tc.executed,
            })

    conv = Conversation(
        scenario_id=session.scenario_id,
        source=ConversationSource.VOXIA_SESSION,
        messages=messages,
        trusted_action_records=trusted_actions,
        metadata={
            "voxia_session_id": session.id,
            "agent_id": session.agent_id,
            "turn_count": len(session.turns),
        },
    )
    return conv
