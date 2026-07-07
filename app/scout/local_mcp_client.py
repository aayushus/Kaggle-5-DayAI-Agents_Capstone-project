from __future__ import annotations

import json
from typing import Any

import anyio


DEFAULT_LOCAL_MCP_URL = "http://127.0.0.1:8000/mcp/sse"
SSE_TIMEOUT_SECONDS = 2.0
SSE_READ_TIMEOUT_SECONDS = 60.0


def search_market_size(
    *,
    concept: str,
    geography: str,
    sector: str,
    trace: list[str],
    url: str = DEFAULT_LOCAL_MCP_URL,
) -> list[dict[str, Any]]:
    trace.append("Researcher agent called Northstar MCP search_market_size.")
    try:
        payload = anyio.run(
            _call_tool,
            url,
            "search_market_size",
            {
                "concept": concept,
                "geography": geography,
                "sector": sector,
            },
        )
    except Exception as exc:
        trace.append(f"Northstar MCP search_market_size failed: {exc!s}")
        return []
    if not isinstance(payload, list):
        return []
    trace.append(f"Northstar MCP search_market_size returned {len(payload)} candidate(s).")
    return [item for item in payload if isinstance(item, dict)]


def read_market_artifact(path: str, url: str = DEFAULT_LOCAL_MCP_URL) -> dict[str, Any] | None:
    try:
        payload = anyio.run(_call_tool, url, "read_market_artifact", {"path": path})
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_market_artifact(path: str, report: dict[str, Any], url: str = DEFAULT_LOCAL_MCP_URL) -> str | None:
    try:
        payload = anyio.run(
            _call_tool,
            url,
            "write_market_artifact",
            {
                "path": path,
                "report_json": json.dumps(report),
            },
        )
    except Exception:
        return None
    return payload if isinstance(payload, str) else None


async def _call_tool(mcp_url: str, tool_name: str, arguments: dict[str, Any]) -> Any:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    async with sse_client(mcp_url, timeout=SSE_TIMEOUT_SECONDS, sse_read_timeout=SSE_READ_TIMEOUT_SECONDS) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                raise RuntimeError(f"{tool_name} returned MCP error.")
            return _decode_result_content(result.content)


def _decode_result_content(content: list[Any]) -> Any:
    if not content:
        return None
    parsed_items: list[Any] = []
    for item in content:
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        text = text.strip()
        if not text:
            continue
        try:
            parsed_items.append(json.loads(text))
        except json.JSONDecodeError:
            parsed_items.append(text)
    if not parsed_items:
        return None
    if len(parsed_items) == 1:
        return parsed_items[0]
    return parsed_items
