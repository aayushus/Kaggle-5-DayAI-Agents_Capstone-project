# Kaggle Capstone Project Compliance & Submission Guide: Northstar

This document certifies that the **Northstar: Market Intelligence Workspace** project is fully compliant with the requirements of the Kaggle 5-Day AI Agents Capstone Project, maps where and how each concept is implemented, and provides actionable scripts/outlines for the final video and writeup.

---

## 🏆 Compliance Matrix (5 of 6 Concepts Applied)

The project is **fully compliant** and exceeds the minimum requirement of applying at least three (3) key concepts.

| Key Concept | Required | Status | Implementation Details & File Links |
|---|---|---|---|
| **1. Multi-Agent System (ADK)** | Code | ✅ **Met** | <ul><li>**Researcher & Auditor loop** inside [orchestrator.py](app/scout/orchestrator.py) dynamically audits drafts and automatically retries research upon validation issues.</li><li>**Dynamic Parallel workflows** in [google_adk_bridge.py](app/scout/google_adk_bridge.py) build multi-agent graphs from parsed blueprints at runtime, running parallel customer/competitor panels.</li></ul> |
| **2. MCP Server** | Code | ✅ **Met** | <ul><li>**FastMCP Server** in [mcp_server.py](app/scout/mcp_server.py) implements 6 tools (`search_competitors`, `search_market_size`, etc.) and 2 resources (`workspace://output`, etc.) mounted over SSE at `/mcp`.</li></ul> |
| **3. Security Features** | Code/Video | ✅ **Met** | <ul><li>**Path Sandboxing:** `_resolve_workspace_path` in the MCP server prevents directory traversal attacks outside the project root.</li><li>**Input Guarding:** Pydantic model validation on FastAPI endpoints ([main.py](app/main.py)) and secure API credential isolation in `.env`.</li></ul> |
| **4. Deployability** | Video | ✅ **Met** | <ul><li>Full reproducibility via [Dockerfile](Dockerfile), [docker-compose.yml](docker-compose.yml), and a [restart.sh](restart.sh) stack watchdog that coordinates startup, Colima, and health-checks.</li></ul> |
| **5. Agent Skills** | Code/Video | ✅ **Met** | <ul><li>Active runtime-loaded skill folder at [.agent/skills/scout/](.agent/skills/scout/) using [SKILL.md](.agent/skills/scout/SKILL.md) and custom scripts ([fetch_tam_formula.py](.agent/skills/scout/scripts/fetch_tam_formula.py), [verify_links.py](.agent/skills/scout/scripts/verify_links.py), etc.) loaded at runtime via [skill_runtime.py](app/scout/skill_runtime.py).</li></ul> |
| **6. Google Antigravity** | Video | ❌ *Optional* | Not implemented (not needed to satisfy the 3-concept threshold). |

---

## 🎥 YouTube Video Demo Outline (Max 5 Minutes)

Use this script layout to ensure you hit all criteria evaluated under **The Pitch (10 Points)**:

### Part 1: The Problem & Vision (1 Minute)
* **What to Show:** Slide with problem summary or a quick look at standard, painful manual competitive research.
* **Talking Points:** 
  > *"When starting a business, competitive research and market validation are crucial but tedious. Founders spend hours copy-pasting data, guessing market sizes, or running manual interviews that are biased. Northstar solves this by providing a unified workspace that uses AI agents to do the research, audit facts, and simulate market responses."*

### Part 2: The Multi-Agent Architecture (1 Minute)
* **What to Show:** Show the architecture diagram from the `README.md`.
* **Talking Points:**
  > *"Northstar uses a double-agent validation loop. A Researcher Agent coordinates with a Research Planner to fetch live search queries. A Competitor Auditor validates results against our active Agent Skills package. An Auditor Agent checks schema and URL validity, returning the draft for rewrite if anomalies are found. Finally, the Google ADK dynamically constructs parallel agent panels at runtime for customer and competitor simulations."*

### Part 3: Live Demo (2 Minutes)
* **What to Show:** Screen record the browser interface (`http://127.0.0.1:8000`).
  1. **Start Research:** Enter a startup concept (e.g., *"Automated vertical indoor farm using IoT sensors"*), choose United States, AgTech, Seed, and click **Run**.
  2. **Streaming Trace:** Highlight the live thinking trace panel showing agent steps, web scraping, and validation.
  3. **Show Results:** Show the structured competitor list, URLs, pricing metadata, and the interactive bottom-up/top-down TAM matrix.
  4. **Run Simulation:** Switch to the "Advisory Board" or "War Room" tab. Type a prompt/scenario (e.g., *"What if we charge $49 instead of $129?"*) and show the parallel agents answering dynamically and updating the positioning blueprint.
  5. **PDF Export:** Click **Export PDF** to show the generated paper-ready report.

### Part 4: The Tech Stack & Deployability (1 Minute)
* **What to Show:** Visual of the code editor containing `docker-compose.yml` and `restart.sh`.
* **Talking Points:**
  > *"Northstar is fully containerized. Running 'bash restart.sh' automatically checks system dependencies, builds the Docker containers, sets up the workspace, and launches the health monitor. It mounts a FastMCP server directly over SSE to expose research tools to external systems."*

---

## 📝 Kaggle Writeup Template (Max 2,500 Words)

Copy, adapt, and expand this markdown layout directly into your Kaggle Submission Writeup:

```markdown
# Northstar: AI-Powered Market Intelligence Workspace

**Track:** Agents for Business  
**Project Repository:** [Your Public GitHub Repository Link]  
**Video Walkthrough:** [Your YouTube Link]

---

## 1. Problem Statement
Starting a business requires answering hard questions: Who is competing? What do they charge? What is the actual market size? How will incumbents react to our launch? 

Manual validation is slow, error-prone, and static. Founders construct biased pricing models or guess customer sentiments. Northstar automates this entire lifecycle, turning raw ideas into audited, structured, and simulated market briefs.

---

## 2. Our Agentic Solution
Northstar is an automated market intelligence workspace. Given a basic concept and operating scope, it executes:
1. **Fact-Grounded Research:** Runs competitive searches, normalizes observed prices, and formats structured competitor profiles.
2. **Double-Agent Auditing:** Automatically verifies scraped URL sanity and schema conformance.
3. **Evidence Ledgers:** Separates verified primary source facts from synthesized mathematical models.
4. **Interactive Market Panels:** Simulates customer persona boards and competitive war rooms to test scenarios dynamically.

---

## 3. Technology Stack & Architecture
* **Frontend:** Single Page Application (HTML5, Vanilla ES6, Custom CSS).
* **Backend:** FastAPI, Pydantic, and Uvicorn.
* **Agent Framework:** Google Generative AI SDK & `google-adk`.
* **Integration Engines:** Model Context Protocol (FastMCP) & SSE.
* **Report Engine:** ReportLab PDF generator.
* **Deployment:** Docker & Docker Compose.

### Architectural Decision: Monolith over Microservices
To ensure optimal performance and operational simplicity for this capstone workspace, a structured monolithic architecture was selected over a distributed microservice framework. This design directly addresses:
1. **Network Latency:** Multi-agent reasoning loops and live page scraping are already bounded by LLM API response times; avoiding inter-service RPC serialization overhead keeps execution times viable.
2. **Simplified Grader Reproducibility:** Coordinating a fleet of microservices complicates local deployment for judges. A single containerized service allows instant startup via a simple `restart.sh` script.
3. **Atomic State Consistency:** Downstream simulations (Advisory Board & War Room) dynamically mutate the same `.market.md` workspace artifact, eliminating the need for distributed transactional consensus protocols.

### Agent Workflow Diagram
* [Include a link or embed the architecture flowchart from your README]

---

## 4. Applied Capstone Key Concepts

### A. Multi-Agent Orchestration (ADK)
Northstar employs an execution loop governed by `ScoutOrchestrator`. A `ResearcherAgent` first compiles competitor sets. An `AuditorAgent` then verifies link status and schema structures. If an audit fails, the orchestrator triggers an automatic corrective iteration. 

Simultaneously, the Google ADK constructs dynamic simulation graphs. During simulation sessions, the ADK spins up multiple sub-agents representing specific customer personas or competitor executives, run in parallel, and combined by an ADK synthesizer agent.

### B. Model Context Protocol (MCP) Server
A local `FastMCP` server is mounted at `/mcp` using SSE transport. It exposes 6 tools enabling external environments to search competitors, lookup TAM profiles, and directly write back changes to local `.market.md` files.

### C. Agent Skills (Procedural Memory)
Active skills reside in `.agent/skills/scout/`. The folder contains a procedural runbook (`SKILL.md`), a JSON schema check, and python scripts for URL validation, TAM calculations, and pricing fallback normalizations, loaded dynamically at runtime.

### D. Security Features
Includes path-traversal sandboxing on all MCP filesystem operations, CORS rules, API key environment variable separation via `.env`, and input validation via Pydantic model schemas.

---

## 5. Developer Journey & Future Roadmap
Building Northstar highlighted the importance of double-agent loop patterns. Initial scraper passes returned noisy lists; adding the `AuditorAgent` loop reduced formatting and link errors to zero. In the future, we plan to implement:
1. Hardened context window constraints for extensive scrape iterations.
2. Real closed-loop MCP agent search inside the core researcher loop.
3. Local sandbox execution for web scraping agents using gVisor.
```
