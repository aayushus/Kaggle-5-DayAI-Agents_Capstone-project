from __future__ import annotations

from typing import Any

from app.scout.audit import AuditorAgent
from app.scout.research import ResearcherAgent


class ResearchAgentAdapter:
    name = "researcher"

    def __init__(self, bridge: Any = None) -> None:
        self._impl = ResearcherAgent(bridge=bridge)

    def run(self, context: dict[str, Any], trace: list[str]) -> dict[str, Any]:
        return self._impl.research(context, trace)


class AuditAgentAdapter:
    name = "auditor"

    def __init__(self) -> None:
        self._impl = AuditorAgent()

    def run(self, context: dict[str, Any], trace: list[str]) -> dict[str, Any]:
        audit = self._impl.audit(context, trace)
        return {"audit": audit}
