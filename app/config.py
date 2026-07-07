from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    adk_backend: str = "auto"
    google_model: str = "gemini-3.1-pro-preview"
    google_api_key_present: bool = False
    google_use_vertexai: bool = False
    parallel_api_key_present: bool = False
    parallel_search_mode: str = "advanced"
    parallel_search_mcp_enabled: bool = True
    parallel_search_mcp_url: str = "https://search.parallel.ai/mcp"
    local_mcp_enabled: bool = True
    local_mcp_url: str = "http://127.0.0.1:8000/mcp/sse"
    rate_limit_enabled: bool = True
    rate_limit_run_per_minute: int = 6
    rate_limit_run_stream_per_minute: int = 4
    rate_limit_session_start_per_minute: int = 20
    rate_limit_session_turn_per_minute: int = 30
    rate_limit_artifact_pdf_per_minute: int = 40


def load_settings() -> Settings:
    backend = os.getenv("ADK_BACKEND", "auto").strip().lower() or "auto"
    if backend not in {"auto", "local", "google"}:
        backend = "auto"
    google_api_key_present = bool(os.getenv("GOOGLE_API_KEY"))
    google_use_vertexai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() == "true"
    google_model = os.getenv("GOOGLE_MODEL", "gemini-3.1-pro-preview").strip() or "gemini-3.1-pro-preview"
    parallel_api_key_present = bool(os.getenv("PARALLEL_API_KEY"))
    parallel_search_mode = os.getenv("PARALLEL_SEARCH_MODE", "advanced").strip().lower() or "advanced"
    if parallel_search_mode not in {"basic", "advanced"}:
        parallel_search_mode = "advanced"
    parallel_search_mcp_enabled = os.getenv("PARALLEL_SEARCH_MCP_ENABLED", "true").strip().lower() != "false"
    parallel_search_mcp_url = os.getenv("PARALLEL_SEARCH_MCP_URL", "https://search.parallel.ai/mcp").strip() or "https://search.parallel.ai/mcp"
    local_mcp_enabled = os.getenv("NORTHSTAR_LOCAL_MCP_ENABLED", "true").strip().lower() != "false"
    local_mcp_url = os.getenv("NORTHSTAR_LOCAL_MCP_URL", "http://127.0.0.1:8000/mcp/sse").strip() or "http://127.0.0.1:8000/mcp/sse"
    rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() != "false"

    def env_int(name: str, default: int) -> int:
        raw = os.getenv(name, str(default)).strip()
        try:
            value = int(raw)
        except ValueError:
            return default
        return value if value > 0 else default

    return Settings(
        adk_backend=backend,
        google_model=google_model,
        google_api_key_present=google_api_key_present,
        google_use_vertexai=google_use_vertexai,
        parallel_api_key_present=parallel_api_key_present,
        parallel_search_mode=parallel_search_mode,
        parallel_search_mcp_enabled=parallel_search_mcp_enabled,
        parallel_search_mcp_url=parallel_search_mcp_url,
        local_mcp_enabled=local_mcp_enabled,
        local_mcp_url=local_mcp_url,
        rate_limit_enabled=rate_limit_enabled,
        rate_limit_run_per_minute=env_int("RATE_LIMIT_RUN_PER_MINUTE", 6),
        rate_limit_run_stream_per_minute=env_int("RATE_LIMIT_RUN_STREAM_PER_MINUTE", 4),
        rate_limit_session_start_per_minute=env_int("RATE_LIMIT_SESSION_START_PER_MINUTE", 20),
        rate_limit_session_turn_per_minute=env_int("RATE_LIMIT_SESSION_TURN_PER_MINUTE", 30),
        rate_limit_artifact_pdf_per_minute=env_int("RATE_LIMIT_ARTIFACT_PDF_PER_MINUTE", 40),
    )
