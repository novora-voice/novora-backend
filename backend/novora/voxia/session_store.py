"""In-memory session store for Voxia sessions (thread-safe)."""
from __future__ import annotations
import logging
import threading
from typing import Dict, Optional

from novora.voxia.models import VoxiaSession

logger = logging.getLogger(__name__)


class VoxiaSessionStore:
    """Simple in-memory store for active Voxia sessions."""

    def __init__(self, max_sessions: int = 50) -> None:
        self._sessions: Dict[str, VoxiaSession] = {}
        self._lock = threading.Lock()
        self.max_sessions = max_sessions

    def create(self, session: VoxiaSession) -> VoxiaSession:
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise RuntimeError(f"Maximum concurrent sessions ({self.max_sessions}) reached.")
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Optional[VoxiaSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def save(self, session: VoxiaSession) -> VoxiaSession:
        with self._lock:
            self._sessions[session.id] = session
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
