from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings
from app.scout.adk_runtime import AdkRuntime
from app.scout.agents import AuditAgentAdapter, ResearchAgentAdapter
from app.scout.artifact_store import save_market_artifact
from app.scout.google_adk_bridge import GoogleAdkBridge


class StreamingTrace:
    def __init__(self, sink: list[str], emit=None):
        self._sink = sink
        self._emit = emit

    def append(self, message: str) -> None:
        self._sink.append(message)
        if self._emit:
            self._emit(message)


@dataclass
class ScoutResult:
    market_markdown_path: str
    market_markdown: str
    report: dict[str, Any]
    thinking_trace: list[str]


class ScoutOrchestrator:
    def __init__(self, output_dir: Path, settings: Settings):
        self.output_dir = output_dir
        self.settings = settings
        self.google_adk = GoogleAdkBridge(settings)
        self.runtime = AdkRuntime(
            [ResearchAgentAdapter(bridge=self.google_adk), AuditAgentAdapter()],
            backend_preference=settings.adk_backend,
        )

    def run(self, brief: dict[str, str], emit=None) -> ScoutResult:
        trace: list[str] = []
        self._log(trace, emit, "Received startup concept and required context fields.")
        self._log(trace, emit, f"Using agent backend: {self.runtime.backend}.")
        if self.runtime.backend == "google-unavailable":
            raise RuntimeError("ADK_BACKEND=google was requested, but no supported Google ADK package is installed.")
        self._log(trace, emit, "Northstar skill runtime loaded schema and helper scripts.")
        runtime_trace = StreamingTrace(trace, emit)
        draft = self.runtime.run(brief, runtime_trace)
        audit = draft.get("audit", {})

        retries = 0
        while not audit.get("passed") and retries < 2:
            self._log(trace, emit, "Audit failed; researcher is revising the draft.")
            draft.setdefault("audit_notes", []).extend(audit.get("feedback", []))
            draft = self.runtime.run({**brief, "audit_feedback": audit.get("feedback", [])}, runtime_trace)
            audit = draft.get("audit", {})
            retries += 1

        adk_status = self.google_adk.status
        if adk_status.ready:
            self._log(trace, emit, f"Google ADK synthesis ready ({adk_status.reason}).")
        else:
            self._log(trace, emit, f"Google ADK synthesis skipped: {adk_status.reason}.")
        if adk_status.ready and self.settings.adk_backend != "local":
            self._log(trace, emit, "Running Google ADK synthesis step.")
            adk_result = self.google_adk.summarize_market_brief(brief, draft)
            if adk_result:
                draft.update(adk_result)
        elif self.settings.adk_backend == "google":
            raise RuntimeError(f"Google ADK requested but unavailable: {adk_status.reason}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        market_path = self.output_dir / f"{self._slugify(brief['concept'])}.market.md"
        draft["audit_notes"] = [f"Audit passed: {audit.get('passed')}"] + list(audit.get("feedback", []))
        final_audit = audit
        if not final_audit.get("passed"):
            self._log(trace, emit, f"Final audit failed: {final_audit.get('feedback', [])}")
            raise ValueError(f"Draft failed validation: {final_audit.get('feedback', [])}")
        market_markdown = save_market_artifact(str(market_path), draft)
        self._log(trace, emit, f"Wrote market document to {market_path.name}.")
        return ScoutResult(str(market_path), market_markdown, draft | {"audit": final_audit}, trace)

    def _log(self, trace: list[str], emit, message: str) -> None:
        trace.append(message)
        if emit:
            emit(message)

    def _slugify(self, text: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
        words = [part for part in cleaned.split("-") if part]
        # Accumulate whole words up to ~80 chars so the slug never cuts mid-word.
        slug_parts: list[str] = []
        length = 0
        for word in words:
            add = len(word) + (1 if slug_parts else 0)
            if length + add > 80:
                break
            slug_parts.append(word)
            length += add
        return "-".join(slug_parts) or "scout-project"
