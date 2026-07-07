from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass
class SimulationSession:
    session_id: str
    kind: str
    report: dict[str, Any]
    seed_prompt: str
    market_markdown_path: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


_SESSIONS: dict[str, SimulationSession] = {}


def create_session(kind: str, report: dict[str, Any], seed_prompt: str, market_markdown_path: str | None = None) -> SimulationSession:
    session = SimulationSession(
        session_id=str(uuid.uuid4()),
        kind=kind,
        report=report,
        seed_prompt=seed_prompt,
        market_markdown_path=market_markdown_path,
    )
    _SESSIONS[session.session_id] = session
    return session


def get_session(session_id: str, kind: str) -> SimulationSession:
    session = _SESSIONS.get(session_id)
    if session is None or session.kind != kind:
        raise KeyError(session_id)
    return session


def append_turn(session: SimulationSession, role: str, content: str, payload: dict[str, Any] | None = None) -> None:
    session.history.append(
        {
            "role": role,
            "content": content,
            "payload": payload or {},
        }
    )
