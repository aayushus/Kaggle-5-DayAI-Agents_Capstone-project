from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from mcp.server.fastmcp import FastMCP

from app.config import Settings
from app.scout.artifact_store import load_market_artifact, save_market_artifact
from app.scout.parallel_search import parallel_live_search, parallel_market_size_search


def build_mcp_server(workspace_root: Path, output_dir: Path, settings: Settings) -> FastMCP:
    mcp = FastMCP("Northstar MCP")

    def _resolve_workspace_path(path: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = workspace_root / candidate
        resolved = candidate.resolve()
        root = workspace_root.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"Path is outside the Northstar workspace: {path}")
        return resolved

    @mcp.tool()
    def search_competitors(query: str, mode: str | None = None) -> list[dict[str, Any]]:
        """Search the web for direct and indirect competitors using Parallel search."""
        trace: list[str] = []
        return parallel_live_search(query, trace, mode=(mode or settings.parallel_search_mode))

    @mcp.tool()
    def search_market_size(concept: str, geography: str, sector: str, mode: str | None = None) -> list[dict[str, Any]]:
        """Search the web for top-down market-size evidence using Parallel search."""
        trace: list[str] = []
        return parallel_market_size_search(
            concept=concept,
            geography=geography,
            sector=sector,
            trace=trace,
            mode=(mode or settings.parallel_search_mode),
        )

    @mcp.tool()
    def read_workspace_text(path: str) -> str:
        """Read a UTF-8 text file from the Northstar workspace."""
        resolved = _resolve_workspace_path(path)
        return resolved.read_text(encoding="utf-8")

    @mcp.tool()
    def write_workspace_text(path: str, content: str) -> str:
        """Write a UTF-8 text file inside the Northstar workspace."""
        resolved = _resolve_workspace_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return str(resolved)

    @mcp.tool()
    def read_market_artifact(path: str) -> dict[str, Any]:
        """Load a Northstar `.market.md` artifact and return its parsed report payload."""
        report, text = load_market_artifact(str(_resolve_workspace_path(path)))
        return {
            "report": report,
            "market_markdown": text,
        }

    @mcp.tool()
    def write_market_artifact(path: str, report_json: str) -> str:
        """Persist a Northstar report payload into a `.market.md` artifact."""
        resolved = _resolve_workspace_path(path)
        payload = json.loads(report_json)
        if not isinstance(payload, dict):
            raise ValueError("report_json must decode to an object")
        return save_market_artifact(str(resolved), payload)

    @mcp.resource("workspace://output")
    def output_listing() -> str:
        """List generated market artifacts in the output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(path.name for path in output_dir.glob("*.market.md"))
        return json.dumps({"output_dir": str(output_dir), "artifacts": files}, indent=2)

    @mcp.resource("workspace://artifact/{filename}")
    def artifact_contents(filename: str) -> str:
        """Return the contents of a generated market artifact by filename."""
        resolved = _resolve_workspace_path(str(output_dir / filename))
        return resolved.read_text(encoding="utf-8")

    return mcp
