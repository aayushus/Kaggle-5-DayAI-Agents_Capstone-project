from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from typing import Any, Protocol


class Agent(Protocol):
    name: str

    def run(self, context: dict[str, Any], trace: list[str]) -> dict[str, Any]:
        ...


@dataclass
class AgentStep:
    name: str
    output: dict[str, Any]


class AdkRuntime:
    """
    Minimal ADK-compatible orchestration boundary.

    This keeps the app structured like an agent pipeline today and lets us swap
    in the real Google ADK runtime once the package is available in the image.
    """

    def __init__(self, steps: list[Agent], backend_preference: str = "auto"):
        self.steps = steps
        self.backend_preference = backend_preference
        self.backend = self._detect_backend()

    def run(self, context: dict[str, Any], trace: list[str]) -> dict[str, Any]:
        trace.append(f"ADK backend selected: {self.backend}.")
        state = dict(context)
        executed: list[AgentStep] = []
        for step in self.steps:
            trace.append(f"Running agent step: {step.name}.")
            output = step.run(state, trace)
            executed.append(AgentStep(name=step.name, output=output))
            state.update(output)
        state["agent_steps"] = [{"name": item.name, "output": item.output} for item in executed]
        return state

    def _detect_backend(self) -> str:
        google_candidates = ("google.adk", "google.genai", "adk")
        if self.backend_preference == "local":
            return "local-fallback"
        if self.backend_preference == "google":
            for module_name in google_candidates:
                if find_spec(module_name) is not None:
                    return module_name
            return "google-unavailable"
        for module_name in google_candidates:
            if find_spec(module_name) is not None:
                return "google-adk"
        return "local-fallback"
