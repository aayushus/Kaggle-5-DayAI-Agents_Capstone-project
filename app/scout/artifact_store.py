from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml

from app.scout.render import render_market_doc
from app.scout.skill_runtime import load_artifact_qa_module


YAML_BLOCK_RE = re.compile(r"```yaml\n(.*)```", re.DOTALL)
ARTIFACT_QA = load_artifact_qa_module()


def load_market_artifact(path: str) -> tuple[dict[str, Any], str]:
    artifact_path = Path(path)
    text = artifact_path.read_text(encoding="utf-8")
    match = YAML_BLOCK_RE.search(text)
    if not match:
        raise ValueError(f"Artifact YAML block missing: {artifact_path}")
    payload = yaml.safe_load(match.group(1)) or {}
    report = {
        "project_name": payload.get("project_name"),
        "brief": payload.get("brief", {}),
        "audit": payload.get("audit", {}),
        "competitors": payload.get("competitors", []),
        "market_sizing": payload.get("market_sizing", {}),
        "provenance": payload.get("provenance", {}),
        "customer_personas": payload.get("customer_personas", []),
        "customer_agent_blueprints": payload.get("customer_agent_blueprints", []),
        "competitor_agent_blueprints": payload.get("competitor_agent_blueprints", []),
        "landing_page_blueprint": payload.get("landing_page_blueprint", {}),
        "audit_notes": payload.get("audit_notes", []),
        "adk_metadata": payload.get("adk_metadata"),
        "simulation_state": payload.get("simulation_state") or {},
        "artifact_qa": payload.get("artifact_qa") or {},
    }
    return report, text


def save_market_artifact(path: str, report: dict[str, Any]) -> str:
    artifact_path = Path(path)
    report["artifact_qa"] = ARTIFACT_QA.summarize(report)
    market_markdown = render_market_doc(report)
    artifact_path.write_text(market_markdown, encoding="utf-8")
    return market_markdown
