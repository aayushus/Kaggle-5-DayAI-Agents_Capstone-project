# Agent Skills & Model Context Protocol (MCP)

Northstar integrates custom procedural skills and Model Context Protocol (MCP) routing to optimize context window efficiency and extend agent execution capabilities.

## 🧠 Agent Skills Runtime

Procedural skills reside in the standard folder structure under `.agent/skills/scout/`.

*   **`SKILL.md`:** Main runbook specifying the input/output contracts, failure recovery guides, and operator constraints.
*   **YAML Schema (`market_schema.yaml`):** Strictly defines valid properties for generated market briefs.
*   **Active Helpers:** Python modules loaded at runtime to execute discrete tasks:
    *   `verify_links.py`: Checks URL status codes.
    *   `fetch_tam_formula.py`: Performs bottom-up / top-down calculations.
    *   `pricing_normalizer.py`: Discovers pricing structures and overrides standard estimates with verified pricing plans (e.g. PropStream monthly override).

## 🔌 Model Context Protocol Server

Northstar hosts a local FastMCP server mounted over SSE at `/mcp`. It exposes key tools and resources for external system interaction:

*   **`search_competitors`:** Conducts competitor discovery.
*   **`search_market_size`:** Performs bottom-up sizing lookup.
*   **`read_workspace_text` / `write_workspace_text`:** Safely coordinates file modifications.
*   **`read_market_artifact` / `write_market_artifact`:** Coordinates document exports (e.g., PDF generation).
