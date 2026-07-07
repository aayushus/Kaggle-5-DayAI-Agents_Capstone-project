Technical Requirements & System Architecture
This document describes the technical blueprint, agent topology, and data flow for SCOUT.

## System Overview
SCOUT is a locally run, production-minded market intelligence agent. The first build will be a small but complete stack:

1. A lightweight web UI for entering the startup concept, viewing the thinking trace, and previewing outputs.
2. A Python backend orchestrator built with Google ADK.
3. A multi-agent workflow for research, audit, customer simulation, competitor simulation, and copy generation.
4. Two MCP servers: one for live web search/scrape and one for filesystem read/write operations.
5. A reusable Agent Skills package for the SCOUT workflow.

## Core Agent Topology
The implementation must include the following agents:

1. Researcher Agent
   - Collects live competitor data, pricing, features, and source URLs.
   - Computes TAM, SAM, and SOM from sourced assumptions.
   - Writes the initial draft of the `.market.md` file.
2. Auditor Agent
   - Verifies links, checks YAML structure, and validates that the numbers and assumptions are coherent.
   - Flags invented claims, broken citations, and mismatched calculations.
   - Sends the draft back to the Researcher when corrections are needed.
3. Customer Persona Agents
   - Dynamically spawned from YAML persona data in the market document.
   - Used for live pitch testing and friction discovery.
   - Must preserve role constraints for demographics, budget, and tech adoption.
4. Competitor Agents
   - Dynamically spawned from the competitor section of the market document.
   - Used to simulate defensive reactions to a launch scenario.
   - Must respond with pricing, feature, and positioning counter-moves.

## Orchestration Flow
The orchestrator should run an explicit loop rather than a single prompt:

1. Ask the user for the startup concept.
2. Ask the three required context questions before any document generation.
3. Run the Researcher Agent to gather market data and draft the report.
4. Run the Auditor Agent to verify the draft.
5. If the audit fails, feed the audit findings back to the Researcher and re-run.
6. Serialize the final output to `[project_name].market.md`.
7. Load the YAML content from that file to power the customer advisory board and competitor war room.
8. Use the same saved document to generate the landing page blueprint.

## MCP Integration
SCOUT should expose or consume MCP servers for the following responsibilities:

1. Web Search and Scrape MCP
   - Search live web sources for competitors and market data.
   - Scrape pricing pages and feature pages.
   - Return titles, snippets, URLs, and extracted page content.
2. Filesystem MCP
   - Read and write the `.market.md` file.
   - Store generated YAML blocks and supporting artifacts.
   - Keep the agent state grounded in files instead of chat memory.

## Agent Skills
The SCOUT workflow should live behind a dedicated skill package at `.agent/skills/scout/`.

Required contents:

1. `SKILL.md`
   - Defines when the skill triggers.
   - Documents the end-to-end workflow.
   - Specifies output expectations and guardrails.
2. `scripts/fetch_tam_formula.py`
   - Encapsulates the market sizing math and validation logic.
3. `scripts/verify_links.py`
   - Checks that cited URLs resolve before the draft is accepted.
4. `schemas/market_schema.yaml`
   - Defines the expected structure for the market intelligence document.

The skill should be loaded only when the SCOUT workflow is active so the general agent context stays small.

## Output Format
The final artifact should be a hybrid Markdown document with embedded YAML sections.
It should contain:

1. Executive summary.
2. Structured market matrix.
3. Customer personas.
4. Competitor analysis.
5. Landing page blueprint.

## Runtime Stack
1. Backend: Python with Google ADK for orchestration.
2. Frontend: Vanilla HTML/CSS/JS for the research and simulation UI.
3. Model: Gemini for reasoning, roleplay, and auditing.
4. Sandbox: Local Docker or equivalent isolated execution for scraper and validation scripts.

## Build Constraints
1. API keys must live in environment variables.
2. Web scraping and validation scripts must run without interactive shell access.
3. Generated numbers must be stored as numeric values, not strings.
4. All sources used in market sizing must be recorded in the document.
