"""Voxia session, turn, and event models."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    ERROR = "error"


class TurnRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"


class EventType(str, Enum):
    SESSION_STARTED = "session_started"
    USER_UTTERANCE_RECEIVED = "user_utterance_received"
    UTTERANCE_TRANSCRIBED = "utterance_transcribed"
    AGENT_RESPONSE_GENERATED = "agent_response_generated"
    TOOL_REQUESTED = "tool_requested"
    TOOL_EXECUTED = "tool_executed"
    TOOL_FAILED = "tool_failed"
    BUSINESS_RESULT_RETURNED = "business_result_returned"
    SESSION_ENDED = "session_ended"
    ERROR = "error"


@dataclass
class ToolCallRecord:
    tool_name: str
    arguments: Dict[str, Any]
    requested_at: float = field(default_factory=time.time)
    executed: bool = False
    result: Optional[Any] = None
    error: Optional[str] = None
    executed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "requested_at": self.requested_at,
            "executed": self.executed,
            "result": self.result,
            "error": self.error,
            "executed_at": self.executed_at,
        }


@dataclass
class VoxiaTurn:
    id: str = field(default_factory=lambda: f"turn_{uuid4().hex[:8]}")
    role: TurnRole = TurnRole.USER
    content: str = ""
    audio_provided: bool = False
    latency_ms: Optional[float] = None
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "audio_provided": self.audio_provided,
            "latency_ms": self.latency_ms,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class VoxiaEvent:
    id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:8]}")
    session_id: str = ""
    event_type: EventType = EventType.SESSION_STARTED
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "created_at": self.created_at,
        }


@dataclass
class VoxiaSession:
    id: str = field(default_factory=lambda: f"voxia_{uuid4().hex[:12]}")
    scenario_id: Optional[str] = None
    agent_id: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    turns: List[VoxiaTurn] = field(default_factory=list)
    events: List[VoxiaEvent] = field(default_factory=list)
    workflow_state: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_event(self, event_type: EventType, payload: Dict[str, Any] = None) -> VoxiaEvent:
        evt = VoxiaEvent(
            session_id=self.id,
            event_type=event_type,
            payload=payload or {},
        )
        self.events.append(evt)
        return evt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "turns": [t.to_dict() for t in self.turns],
            "events": [e.to_dict() for e in self.events],
            "workflow_state": self.workflow_state,
            "created_at": self.created_at,
            "ended_at": self.ended_at,
            "metadata": self.metadata,
        }
