from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import anyio
import httpx


DEFAULT_MCP_URL = "https://search.parallel.ai/mcp"
DEFAULT_MODEL_NAME = "gemini-2.5-flash"
MCP_TIMEOUT = 30.0
MCP_READ_TIMEOUT = 300.0
MCP_SESSION_ID = uuid4().hex


def web_search(
    *,
    objective: str,
    search_queries: list[str],
    trace: list[str],
    url: str = DEFAULT_MCP_URL,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, Any]:
    queries = [str(item).strip() for item in search_queries if str(item).strip()]
    if not objective.strip() or not queries:
        return {}
    trace.append("Researcher agent called Parallel MCP web_search.")
    try:
        payload = anyio.run(
            _call_tool,
            url,
            "web_search",
            {
                "objective": objective[:500],
                "search_queries": queries[:4],
                "session_id": MCP_SESSION_ID,
                "model_name": model_name,
            },
        )
    except Exception as exc:
        trace.append(f"Parallel MCP web_search failed: {exc!s}")
        return {}
    results = payload.get("results", [])
    trace.append(f"Parallel MCP web_search returned {len(results)} results.")
    return payload


def web_fetch(
    *,
    urls: list[str],
    trace: list[str],
    objective: str | None = None,
    search_queries: list[str] | None = None,
    full_content: bool = False,
    url: str = DEFAULT_MCP_URL,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, Any]:
    clean_urls = [str(item).strip() for item in urls if str(item).strip()]
    if not clean_urls:
        return {}
    trace.append(f"Researcher agent called Parallel MCP web_fetch for {len(clean_urls[:5])} URL(s).")
    args: dict[str, Any] = {
        "urls": clean_urls[:5],
        "full_content": bool(full_content),
        "session_id": MCP_SESSION_ID,
        "model_name": model_name,
    }
    if objective:
        args["objective"] = objective[:200]
    if search_queries:
        args["search_queries"] = [str(item).strip() for item in search_queries if str(item).strip()][:4]
    try:
        payload = anyio.run(_call_tool, url, "web_fetch", args)
    except Exception as exc:
        trace.append(f"Parallel MCP web_fetch failed: {exc!s}")
        return {}
    results = payload.get("results", [])
    trace.append(f"Parallel MCP web_fetch returned {len(results)} result(s).")
    return payload


async def _call_tool(mcp_url: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    headers: dict[str, str] = {}
    api_key = os.getenv("PARALLEL_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = httpx.Timeout(MCP_TIMEOUT, read=MCP_READ_TIMEOUT)
    async with create_mcp_http_client(headers or None, timeout=timeout) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if result.isError:
                    raise RuntimeError(f"{tool_name} returned MCP error.")
                return _decode_result_content(result.content)


def _decode_result_content(content: list[Any]) -> dict[str, Any]:
    if not content:
        return {}
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {}
