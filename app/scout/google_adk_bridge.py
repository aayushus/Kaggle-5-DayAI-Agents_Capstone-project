from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import re
import uuid

from app.config import Settings


@dataclass
class GoogleAdkStatus:
    package_available: bool
    credentials_available: bool
    ready: bool
    reason: str


def get_google_adk_status(settings: Settings) -> GoogleAdkStatus:
    try:
        from google.adk import Agent, Runner  # noqa: F401
        from google.adk.sessions import InMemorySessionService  # noqa: F401
        from google.genai import types  # noqa: F401
    except Exception as exc:
        return GoogleAdkStatus(
            package_available=False,
            credentials_available=False,
            ready=False,
            reason=f"package unavailable: {exc}",
        )

    credentials_available = settings.google_api_key_present or settings.google_use_vertexai
    if not credentials_available:
        return GoogleAdkStatus(
            package_available=True,
            credentials_available=False,
            ready=False,
            reason="missing GOOGLE_API_KEY or GOOGLE_GENAI_USE_VERTEXAI=true",
        )

    return GoogleAdkStatus(
        package_available=True,
        credentials_available=True,
        ready=True,
        reason="ready",
    )


class GoogleAdkBridge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.status = get_google_adk_status(settings)
        self._session_service = None
        if self.status.package_available:
            try:
                from google.adk.sessions import InMemorySessionService

                self._session_service = InMemorySessionService()
            except Exception:
                self._session_service = None

    def summarize_market_brief(self, brief: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any] | None:
        if not self.status.ready:
            return None

        from google.adk import Agent, Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        prompt = self._build_prompt(brief, draft)
        agent = Agent(
            name="scout_adk_summary_agent",
            model=self.settings.google_model,
            instruction=(
                "You are Northstar's ADK synthesis agent. Produce concise, factual market synthesis. "
                "Do not invent URLs or numeric inputs. Use the provided draft only."
            ),
        )
        runner = Runner(
            app_name="scout",
            agent=agent,
            session_service=InMemorySessionService(),
            auto_create_session=True,
        )
        content = types.Content(role="user", parts=[types.Part(text=prompt)])
        summary_text = ""
        for event in runner.run(
            user_id="scout-user",
            session_id=f"scout-{uuid.uuid4()}",
            new_message=content,
        ):
            text = _extract_event_text(event)
            if text:
                summary_text = text

        if not summary_text:
            return None

        return {
            "adk_summary": summary_text,
            "adk_metadata": {
                "backend": "google-adk",
                "model": self.settings.google_model,
            },
        }

    def simulate_advisory_board_turn(
        self,
        report: dict[str, Any],
        prompt: str,
        history: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        payload = self._run_dynamic_panel(
            workflow=self._build_board_workflow(report),
            prompt=prompt,
            session_id=session_id,
        )
        if not payload:
            return None
        payload.setdefault("mode", "advisory-board")
        payload.setdefault("reply", "The advisory board reviewed the prompt.")
        payload["generator"] = "google-adk"
        payload["agent_graph"] = "dynamic-adk-board-workflow"
        return payload

    def simulate_war_room_turn(
        self,
        report: dict[str, Any],
        scenario: str,
        history: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        payload = self._run_dynamic_panel(
            workflow=self._build_war_workflow(report),
            prompt=scenario,
            session_id=session_id,
        )
        if not payload:
            return None
        payload.setdefault("mode", "war-room")
        payload.setdefault("reply", "The war room modeled likely competitive responses.")
        payload["generator"] = "google-adk"
        payload["agent_graph"] = "dynamic-adk-war-workflow"
        return payload

    def _build_prompt(self, brief: dict[str, Any], draft: dict[str, Any]) -> str:
        competitors = draft.get("competitors", [])
        competitor_lines = []
        for item in competitors[:5]:
            competitor_lines.append(
                f"- {item.get('name')}: ${item.get('price_monthly')}/mo, weaknesses={', '.join(item.get('weaknesses', []))}"
            )
        return (
            f"Concept: {brief.get('concept')}\n"
            f"Geography: {brief.get('geography')}\n"
            f"Sector: {brief.get('sector')}\n"
            f"Funding scale: {brief.get('funding_scale')}\n"
            "Competitors:\n"
            f"{chr(10).join(competitor_lines)}\n"
            f"Market sizing: {draft.get('market_sizing')}\n"
            "Write a 3-4 sentence executive summary and one differentiation angle."
        )

    def _build_board_prompt(self, report: dict[str, Any], prompt: str, history: list[dict[str, Any]]) -> str:
        blueprints = report.get("customer_agent_blueprints", [])
        history_lines = [f"{turn.get('role')}: {turn.get('content')}" for turn in history[-6:]]
        persona_lines = []
        if blueprints:
            persona_lines = [
                (
                    f"- {item.get('persona_name')}: demographics={item.get('system_constraints', {}).get('demographics')}; "
                    f"psychographics={item.get('system_constraints', {}).get('psychographics')}; "
                    f"triggers={', '.join(item.get('system_constraints', {}).get('buying_triggers', []))}; "
                    f"tech_adoption={item.get('system_constraints', {}).get('tech_adoption_curve')}; "
                    f"value_prop={item.get('system_constraints', {}).get('value_proposition')}"
                )
                for item in blueprints[:4]
            ]
        else:
            personas = report.get("customer_personas", [])
            persona_lines = [
                (
                    f"- {item.get('name')}: demographics={item.get('demographics')}; "
                    f"psychographics={item.get('psychographics')}; triggers={', '.join(item.get('buying_triggers', []))}; "
                    f"value_prop={item.get('value_proposition')}"
                )
                for item in personas[:4]
            ]
        return (
            "Return JSON with keys: "
            "turn_number, average_sentiment, recommendation, blocking_issue, fit_scores, next_questions, reply, responses. "
            "Each item in responses must contain persona, sentiment_score, buying_decision, product_fit, friction_points, requested_changes, quote.\n"
            "Strict roleplay rule: each response must stay inside the supplied buyer blueprint and its constraints.\n"
            f"Personas:\n{chr(10).join(persona_lines)}\n"
            f"Conversation history:\n{chr(10).join(history_lines) or 'none'}\n"
            f"User prompt: {prompt}"
        )

    def _build_war_prompt(self, report: dict[str, Any], scenario: str, history: list[dict[str, Any]]) -> str:
        blueprints = report.get("competitor_agent_blueprints", [])
        history_lines = [f"{turn.get('role')}: {turn.get('content')}" for turn in history[-6:]]
        competitor_lines = []
        if blueprints:
            competitor_lines = [
                (
                    f"- {item.get('competitor_name')}: "
                    f"price={item.get('system_constraints', {}).get('price_monthly')}; "
                    f"features={', '.join(item.get('system_constraints', {}).get('features', []))}; "
                    f"strengths={', '.join(item.get('system_constraints', {}).get('strengths', []))}; "
                    f"weaknesses={', '.join(item.get('system_constraints', {}).get('weaknesses', []))}"
                )
                for item in blueprints[:6]
            ]
        else:
            competitors = report.get("competitors", [])
            competitor_lines = [
                (
                    f"- {item.get('name')}: price={item.get('price_monthly')}; "
                    f"features={', '.join(item.get('features', [])[:4])}; "
                    f"weaknesses={', '.join(item.get('weaknesses', [])[:3])}"
                )
                for item in competitors[:6]
            ]
        return (
            "Return JSON with keys: "
            "turn_number, threat_level, reply, counter_moves, risk_matrix, responses. "
            "Each risk_matrix item must contain title, likelihood, impact, severity, counter_move. "
            "Each responses item must contain competitor, pricing_reaction, feature_reaction, channel_reaction, defensive_risk, confidence.\n"
            "Strict roleplay rule: each competitor response must stay inside the supplied competitor blueprint and its constraints.\n"
            f"Competitors:\n{chr(10).join(competitor_lines)}\n"
            f"Conversation history:\n{chr(10).join(history_lines) or 'none'}\n"
            f"Launch scenario: {scenario}"
        )

    def _build_board_workflow(self, report: dict[str, Any]):
        from google.adk import Agent
        from google.adk.agents.parallel_agent import ParallelAgent
        from google.adk.agents.sequential_agent import SequentialAgent

        report_brief = report.get("brief", {})
        concept = report.get("project_name") or report_brief.get("concept") or "Northstar concept"
        blueprints = report.get("customer_agent_blueprints") or []
        if not blueprints:
            blueprints = [
                {
                    "agent_id": item.get("name", f"persona-{index + 1}").lower().replace(" ", "-"),
                    "role": "customer-persona",
                    "persona_name": item.get("name", f"Persona {index + 1}"),
                    "system_constraints": {
                        "demographics": item.get("demographics"),
                        "psychographics": item.get("psychographics"),
                        "buying_triggers": item.get("buying_triggers", []),
                        "tech_adoption_curve": item.get("tech_adoption_curve"),
                        "value_proposition": item.get("value_proposition"),
                    },
                    "evaluation_style": "Respond as this exact buyer. Judge value, budget fit, and rollout trust. Stay in role.",
                    "rating_scale": {
                        "sentiment_score": "0-100",
                        "buying_decision": ["Buy", "Pilot First", "Request Changes", "Pass"],
                    },
                }
                for index, item in enumerate(report.get("customer_personas", [])[:4])
            ]

        output_keys: list[str] = []
        sub_agents = []
        for index, blueprint in enumerate(blueprints[:4], start=1):
            output_key = f"board_persona_{index}_response"
            output_keys.append(output_key)
            constraints = blueprint.get("system_constraints", {})
            instruction = (
                f"You are {blueprint.get('persona_name')} reviewing the startup concept '{concept}'. "
                "Stay fully inside this persona and never break role.\n"
                f"Demographics: {constraints.get('demographics')}\n"
                f"Psychographics: {constraints.get('psychographics')}\n"
                f"Buying triggers: {', '.join(constraints.get('buying_triggers', []))}\n"
                f"Tech adoption curve: {constraints.get('tech_adoption_curve')}\n"
                f"Value proposition fit: {constraints.get('value_proposition')}\n"
                f"Evaluation style: {blueprint.get('evaluation_style')}\n"
                "Respond in strict JSON only with keys persona, sentiment_score, buying_decision, product_fit, friction_points, requested_changes, quote."
            )
            sub_agents.append(
                Agent(
                    name=f"board_persona_{index}",
                    description=f"Customer persona panelist for {blueprint.get('persona_name')}.",
                    model=self.settings.google_model,
                    instruction=instruction,
                    output_key=output_key,
                )
            )

        panel_agent = ParallelAgent(
            name="board_panel",
            description="Runs all customer persona panelists in parallel.",
            sub_agents=sub_agents,
        )
        synthesizer = Agent(
            name="board_synthesizer",
            description="Combines customer persona responses into the final advisory-board payload.",
            model=self.settings.google_model,
            instruction=self._build_board_synthesizer_instruction(output_keys, concept, report_brief),
        )
        return SequentialAgent(
            name="northstar_board_workflow",
            description="Dynamic advisory-board workflow sourced from artifact blueprints.",
            sub_agents=[panel_agent, synthesizer],
        )

    def _build_war_workflow(self, report: dict[str, Any]):
        from google.adk import Agent
        from google.adk.agents.parallel_agent import ParallelAgent
        from google.adk.agents.sequential_agent import SequentialAgent

        report_brief = report.get("brief", {})
        concept = report.get("project_name") or report_brief.get("concept") or "Northstar concept"
        blueprints = report.get("competitor_agent_blueprints") or []
        if not blueprints:
            blueprints = [
                {
                    "agent_id": item.get("name", f"competitor-{index + 1}").lower().replace(" ", "-"),
                    "role": "competitor-executive",
                    "competitor_name": item.get("name", f"Competitor {index + 1}"),
                    "source_url": item.get("source_url"),
                    "system_constraints": {
                        "price_monthly": item.get("price_monthly"),
                        "features": item.get("features", [])[:4],
                        "strengths": item.get("strengths", [])[:3],
                        "weaknesses": item.get("weaknesses", [])[:3],
                        "source_quality": item.get("source_quality", {}),
                    },
                    "response_style": "Defend market position with pricing, feature, and channel counter-moves grounded in this competitor profile.",
                }
                for index, item in enumerate(report.get("competitors", [])[:6])
            ]

        output_keys: list[str] = []
        sub_agents = []
        for index, blueprint in enumerate(blueprints[:6], start=1):
            output_key = f"war_competitor_{index}_response"
            output_keys.append(output_key)
            constraints = blueprint.get("system_constraints", {})
            instruction = (
                f"You are the executive response unit for {blueprint.get('competitor_name')} reacting to threats against '{concept}'. "
                "Stay fully inside this competitor profile and never break role.\n"
                f"Price point: {constraints.get('price_monthly')}\n"
                f"Features: {', '.join(constraints.get('features', []))}\n"
                f"Strengths: {', '.join(constraints.get('strengths', []))}\n"
                f"Weaknesses: {', '.join(constraints.get('weaknesses', []))}\n"
                f"Response style: {blueprint.get('response_style')}\n"
                "Respond in strict JSON only with keys competitor, pricing_reaction, feature_reaction, channel_reaction, defensive_risk, confidence."
            )
            sub_agents.append(
                Agent(
                    name=f"war_competitor_{index}",
                    description=f"Competitor executive for {blueprint.get('competitor_name')}.",
                    model=self.settings.google_model,
                    instruction=instruction,
                    output_key=output_key,
                )
            )

        panel_agent = ParallelAgent(
            name="war_room_panel",
            description="Runs all competitor executive agents in parallel.",
            sub_agents=sub_agents,
        )
        synthesizer = Agent(
            name="war_room_synthesizer",
            description="Combines competitor reactions into the final war-room payload.",
            model=self.settings.google_model,
            instruction=self._build_war_synthesizer_instruction(output_keys, concept, report_brief),
        )
        return SequentialAgent(
            name="northstar_war_workflow",
            description="Dynamic competitor war-room workflow sourced from artifact blueprints.",
            sub_agents=[panel_agent, synthesizer],
        )

    def _build_board_synthesizer_instruction(self, output_keys: list[str], concept: str, brief: dict[str, Any]) -> str:
        placeholder_block = "\n".join(f"{key}: {{{key}}}" for key in output_keys)
        return (
            f"You are Northstar's advisory-board coordinator for '{concept}'. "
            f"Geography: {brief.get('geography')}. Sector: {brief.get('sector')}. Funding scale: {brief.get('funding_scale')}.\n"
            "Use the latest user message in session history as the prompt under review. "
            "Combine the persona JSON responses below into one strict JSON object with keys: "
            "turn_number, average_sentiment, recommendation, blocking_issue, fit_scores, next_questions, reply, responses.\n"
            "Requirements:\n"
            "- responses must be an array formed from the persona JSON objects.\n"
            "- fit_scores must include budget_fit, urgency, trust, and ease_of_adoption as 0-100 numeric values.\n"
            "- recommendation and blocking_issue must be concise.\n"
            "- next_questions must contain 2-3 concrete follow-up questions.\n"
            "- reply must summarize the board's advice in 2-4 sentences.\n"
            "- Return strict JSON only.\n"
            f"Persona outputs:\n{placeholder_block}"
        )

    def _build_war_synthesizer_instruction(self, output_keys: list[str], concept: str, brief: dict[str, Any]) -> str:
        placeholder_block = "\n".join(f"{key}: {{{key}}}" for key in output_keys)
        return (
            f"You are Northstar's competitor war-room coordinator for '{concept}'. "
            f"Geography: {brief.get('geography')}. Sector: {brief.get('sector')}. Funding scale: {brief.get('funding_scale')}.\n"
            "Use the latest user message in session history as the launch scenario. "
            "Combine the competitor JSON responses below into one strict JSON object with keys: "
            "turn_number, threat_level, reply, counter_moves, risk_matrix, responses.\n"
            "Requirements:\n"
            "- responses must be an array formed from the competitor JSON objects.\n"
            "- counter_moves must contain 2-4 concise defensive moves.\n"
            "- risk_matrix must contain 3-4 objects with keys title, likelihood, impact, severity, counter_move.\n"
            "- threat_level must be one of Low, Moderate, High, Critical.\n"
            "- reply must summarize the likely market reaction in 2-4 sentences.\n"
            "- Return strict JSON only.\n"
            f"Competitor outputs:\n{placeholder_block}"
        )

    def generate_json(self, name: str, instruction: str, prompt: str) -> dict[str, Any] | None:
        """Run a one-shot JSON agent and return the parsed object (or None).

        Public entry point used by the research planner and competitor validator.
        """
        instruction = (
            instruction
            + "\nReturn only valid JSON. Do not wrap it in markdown code fences or add commentary."
        )
        return self._run_json_agent(name, instruction, prompt)

    def _run_dynamic_panel(self, workflow: Any, prompt: str, session_id: str | None = None) -> dict[str, Any] | None:
        text = self._run_workflow_text(workflow, prompt, session_id=session_id)
        if not text:
            return None
        return _extract_json_object(text)

    def _run_json_agent(self, name: str, instruction: str, prompt: str) -> dict[str, Any] | None:
        text = self._run_text_agent(name, instruction, prompt)
        if not text:
            return None
        return _extract_json_object(text)

    def _run_workflow_text(self, workflow: Any, prompt: str, session_id: str | None = None) -> str:
        if not self.status.ready or self._session_service is None:
            return ""

        from google.adk import Runner
        from google.genai import types

        adk_session_id = session_id or f"northstar-{uuid.uuid4()}"
        self._ensure_session(adk_session_id)
        runner = Runner(
            app_name="northstar",
            agent=workflow,
            session_service=self._session_service,
            auto_create_session=True,
        )
        content = types.Content(role="user", parts=[types.Part(text=prompt)])
        response_text = ""
        for event in runner.run(
            user_id="northstar-user",
            session_id=adk_session_id,
            new_message=content,
        ):
            text = _extract_event_text(event)
            if text:
                response_text = text
        return response_text

    def _run_text_agent(self, name: str, instruction: str, prompt: str) -> str:
        if not self.status.ready or self._session_service is None:
            return ""

        from google.adk import Agent, Runner
        from google.genai import types

        agent = Agent(
            name=name,
            model=self.settings.google_model,
            instruction=instruction,
        )
        runner = Runner(
            app_name="northstar",
            agent=agent,
            session_service=self._session_service,
            auto_create_session=True,
        )
        adk_session_id = f"northstar-{uuid.uuid4()}"
        self._ensure_session(adk_session_id)
        content = types.Content(role="user", parts=[types.Part(text=prompt)])
        response_text = ""
        for event in runner.run(
            user_id="northstar-user",
            session_id=adk_session_id,
            new_message=content,
        ):
            text = _extract_event_text(event)
            if text:
                response_text = text
        return response_text

    def _ensure_session(self, session_id: str) -> None:
        if self._session_service is None:
            return
        existing = self._session_service.get_session_sync(
            app_name="northstar",
            user_id="northstar-user",
            session_id=session_id,
        )
        if existing is None:
            self._session_service.create_session_sync(
                app_name="northstar",
                user_id="northstar-user",
                session_id=session_id,
                state={},
            )


def _extract_event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    if not content or not getattr(content, "parts", None):
        return ""
    texts: list[str] = []
    for part in content.parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None
