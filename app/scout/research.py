from __future__ import annotations

from collections import Counter
import re
from typing import Any

from app.scout.competitor_names import sanitize_competitor_name
from app.scout.web import live_search
from app.scout.tam import estimate_tam
from app.scout.research_planner import build_research_plan, validate_competitor_set


DEFAULT_PERSONAS = [
    {
        "name": "Budget-conscious operator",
        "demographics": "Small team, early-stage operator",
        "psychographics": "Risk-aware, practical, and ROI driven",
        "buying_triggers": ["Clear payback", "Simple setup", "Low monthly cost"],
        "tech_adoption_curve": "Late majority",
        "value_proposition": "Lower operational overhead with minimal change management.",
    },
    {
        "name": "Growth-minded founder",
        "demographics": "Founder-led startup or small business",
        "psychographics": "Likes speed, automation, and metrics",
        "buying_triggers": ["Faster decisions", "Automation", "Insight quality"],
        "tech_adoption_curve": "Early adopter",
        "value_proposition": "Rapid testing and better market clarity with less manual research.",
    },
]


class ResearcherAgent:
    def __init__(self, bridge: Any = None) -> None:
        self.bridge = bridge
        self._plan_cache: dict[str, dict[str, Any] | None] = {}

    def research(self, brief: dict[str, str], trace: list[str]) -> dict[str, Any]:
        trace.append("Researcher agent is searching for competitors and market signals.")
        brief_snapshot = {
            "concept": brief.get("concept", ""),
            "geography": brief.get("geography", ""),
            "sector": brief.get("sector", ""),
            "funding_scale": brief.get("funding_scale", ""),
        }
        plan = self._get_plan(brief, trace)
        competitors = live_search(brief["concept"], trace, plan=plan)
        competitors = validate_competitor_set(self.bridge, brief, plan, competitors, trace)
        competitors = self._anchor_estimated_prices(competitors, plan, trace)
        tam = estimate_tam(competitors, brief, trace, plan=plan)
        differentiation = self._build_differentiation(competitors, plan)
        market_matrix = self._build_market_matrix(competitors)
        provenance = self._build_provenance(brief_snapshot, competitors, tam, differentiation)
        customer_personas = self._resolve_personas(plan)
        customer_agent_blueprints = self._build_customer_agent_blueprints(customer_personas)
        competitor_agent_blueprints = self._build_competitor_agent_blueprints(competitors)
        return {
            "project_name": brief["concept"],
            "brief": brief_snapshot,
            "competitors": competitors,
            "market_matrix": market_matrix,
            "market_sizing": tam,
            "provenance": provenance,
            "customer_personas": customer_personas,
            "customer_agent_blueprints": customer_agent_blueprints,
            "competitor_agent_blueprints": competitor_agent_blueprints,
            "landing_page_blueprint": self._build_landing_blueprint(brief, plan, differentiation),
            "audit_notes": [],
        }

    def _anchor_estimated_prices(
        self,
        competitors: list[dict[str, Any]],
        plan: dict[str, Any] | None,
        trace: list[str],
    ) -> list[dict[str, Any]]:
        """Anchor fallback price estimates to the concept's real price band.

        The keyword-bucket estimator can emit wildly off numbers (e.g. $249/mo for a
        consumer tool). When the planner gave a typical price for the category, use it
        for any competitor whose price was not directly extracted — a defensible
        category estimate rather than a guess.
        """
        typical = ((plan or {}).get("buyer_estimates") or {}).get("typical_monthly_price_usd")
        if not isinstance(typical, (int, float)) or typical <= 0:
            return competitors
        adjusted = 0
        for competitor in competitors:
            if competitor.get("price_source_type") != "extracted":
                competitor["price_monthly"] = float(typical)
                adjusted += 1
        if adjusted:
            trace.append(
                f"Anchored {adjusted} estimated competitor price(s) to the category typical of "
                f"${float(typical):,.0f}/mo."
            )
        return competitors

    def _get_plan(self, brief: dict[str, str], trace: list[str]) -> dict[str, Any] | None:
        key = (brief.get("concept") or "").strip().lower()
        if key not in self._plan_cache:
            self._plan_cache[key] = build_research_plan(self.bridge, brief, trace)
        return self._plan_cache[key]

    def _resolve_personas(self, plan: dict[str, Any] | None) -> list[dict[str, Any]]:
        personas = (plan or {}).get("personas")
        if isinstance(personas, list) and len(personas) >= 2:
            return personas
        return [dict(item) for item in DEFAULT_PERSONAS]

    def _build_landing_blueprint(
        self,
        brief: dict[str, str],
        plan: dict[str, Any] | None,
        differentiation: str,
    ) -> dict[str, Any]:
        positioning = (plan or {}).get("positioning") or {}
        concise_concept = self._concise_concept(brief.get("concept", ""))
        hero_title = positioning.get("hero_title") or f"A sharper wedge into {concise_concept}"
        hero_subheader = positioning.get("hero_subheader") or "Turn a vague startup idea into a verified market plan."
        value_hooks = positioning.get("value_hooks") or [
            differentiation,
            "Audited TAM/SAM/SOM sizing",
            "Persona and war-room simulations",
        ]
        objection_copy = positioning.get("objection_handling") or [
            "If buyers worry about cost, the system shows a quantified payback path.",
            "If buyers worry about complexity, the workflow surfaces the smallest viable rollout.",
        ]
        return {
            "hero_title": hero_title,
            "hero_subheader": hero_subheader,
            "differentiation": differentiation,
            "value_hooks": value_hooks[:4],
            "objection_handling_copy": objection_copy[:4],
        }

    @staticmethod
    def _concise_concept(concept: str) -> str:
        first = re.split(r"[.\n]", str(concept or ""), maxsplit=1)[0].strip()
        return (first[:80] + "…") if len(first) > 80 else (first or "this market")

    def _build_differentiation(self, competitors: list[dict[str, Any]], plan: dict[str, Any] | None) -> str:
        positioning = (plan or {}).get("positioning") or {}
        if positioning.get("differentiation"):
            return positioning["differentiation"]
        hooks = positioning.get("value_hooks") or []
        if hooks:
            return hooks[0]
        weaknesses = [item for competitor in competitors for item in competitor.get("weaknesses", [])]
        if not weaknesses:
            return "Own the market with faster verification and clearer decisions."
        return f"Exploit common gaps like {weaknesses[0].lower()} with a verified, auditable workflow."

    def _build_market_matrix(self, competitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        feature_counts = Counter(
            feature
            for competitor in competitors
            for feature in competitor.get("features", [])
        )
        top_features = [feature for feature, _ in feature_counts.most_common(6)]
        matrix: list[dict[str, Any]] = []
        for competitor in competitors:
            matrix.append(
                {
                    "competitor": competitor["name"],
                    "price_monthly": competitor.get("price_monthly"),
                    "features": {
                        feature: feature in competitor.get("features", [])
                        for feature in top_features
                    },
                    "sources": competitor.get("source_snippets", [])[:2],
                }
            )
        return matrix

    def _build_provenance(
        self,
        brief: dict[str, str],
        competitors: list[dict[str, Any]],
        market_sizing: dict[str, Any],
        differentiation: str,
    ) -> dict[str, list[dict[str, Any]]]:
        source_facts: list[dict[str, Any]] = []
        estimated_assumptions: list[dict[str, Any]] = []

        for competitor in competitors:
            source_facts.append(
                {
                    "type": "competitor_evidence",
                    "subject": competitor["name"],
                    "facts": {
                        "source_url": competitor.get("source_url"),
                        "pricing_url": competitor.get("pricing_url"),
                        "price_monthly": competitor.get("price_monthly"),
                        "price_source_type": competitor.get("price_source_type"),
                        "pricing_visibility": competitor.get("pricing_visibility"),
                        "features": competitor.get("features", [])[:4],
                        "source_quality": competitor.get("source_quality"),
                    },
                    "evidence": competitor.get("source_snippets", [])[:3],
                }
            )

        assumptions = market_sizing.get("assumptions", {})
        top_down = market_sizing.get("top_down", {})
        if top_down.get("source_type") == "external" and top_down.get("source_url"):
            source_facts.append(
                {
                    "type": "top_down_market_source",
                    "subject": brief.get("concept"),
                    "facts": {
                        "source_url": top_down.get("source_url"),
                        "market_size_usd": top_down.get("tam"),
                        "display_value": top_down.get("display_value"),
                        "selection_method": top_down.get("selection_method"),
                    },
                    "evidence": [top_down.get("source_excerpt") or top_down.get("source") or ""],
                }
            )
        estimated_assumptions.append(
            {
                "type": "market_sizing_assumption",
                "subject": brief.get("concept"),
                "assumptions": {
                    "monthly_price": assumptions.get("monthly_price"),
                    "annual_price": assumptions.get("annual_price"),
                    "n_global_customers": assumptions.get("n_global_customers"),
                    "n_target_customers": assumptions.get("n_target_customers"),
                    "capture_rate": assumptions.get("capture_rate"),
                    "formulae": assumptions.get("formulae"),
                    "sector_profile": assumptions.get("sector_profile"),
                },
                "reasoning": (
                    "Bottom-up sizing uses competitor pricing and modeled customer counts. "
                    "Top-down sizing prefers a direct third-party market-size citation when the live search path finds one; "
                    "otherwise it falls back to a sector benchmark profile and geography scope."
                ),
            }
        )
        if top_down.get("source_type") != "external":
            estimated_assumptions.append(
                {
                    "type": "top_down_market_basis",
                    "subject": brief.get("concept"),
                    "assumptions": {
                        "benchmark_basis": top_down.get("benchmark_basis"),
                        "benchmark_source": top_down.get("source"),
                        "top_down_ratio": top_down.get("top_down_ratio"),
                    },
                    "reasoning": "Top-down TAM fell back to Northstar's benchmark profile because a direct third-party market-size citation was not confidently selected.",
                }
            )
        estimated_assumptions.append(
            {
                "type": "positioning_inference",
                "subject": brief.get("concept"),
                "assumptions": {
                    "primary_differentiation": differentiation,
                    "landing_page_hook": "Generated from competitor gaps and persona fit, not directly sourced from the web.",
                },
                "reasoning": "Differentiation and copywriting are synthesized from research evidence and product assumptions.",
            }
        )

        return {
            "source_facts": source_facts,
            "estimated_assumptions": estimated_assumptions,
        }

    def _build_customer_agent_blueprints(self, personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blueprints: list[dict[str, Any]] = []
        for persona in personas:
            blueprints.append(
                {
                    "agent_id": persona["name"].lower().replace(" ", "-"),
                    "role": "customer-persona",
                    "persona_name": persona["name"],
                    "system_constraints": {
                        "demographics": persona.get("demographics"),
                        "psychographics": persona.get("psychographics"),
                        "buying_triggers": persona.get("buying_triggers", []),
                        "tech_adoption_curve": persona.get("tech_adoption_curve"),
                        "value_proposition": persona.get("value_proposition"),
                    },
                    "evaluation_style": "Respond as this exact buyer. Judge value, budget fit, and rollout trust. Stay in role.",
                    "rating_scale": {
                        "sentiment_score": "0-100",
                        "buying_decision": ["Buy", "Pilot First", "Request Changes", "Pass"],
                    },
                }
            )
        return blueprints

    def _build_competitor_agent_blueprints(self, competitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blueprints: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for competitor in competitors:
            competitor_name = sanitize_competitor_name(competitor.get("name"), competitor.get("source_url"))
            normalized = competitor_name.lower()
            if not competitor_name or normalized in seen_names:
                continue
            seen_names.add(normalized)
            blueprints.append(
                {
                    "agent_id": competitor_name.lower().replace(" ", "-"),
                    "role": "competitor-executive",
                    "competitor_name": competitor_name,
                    "source_url": competitor.get("source_url"),
                    "system_constraints": {
                        "price_monthly": competitor.get("price_monthly"),
                        "features": competitor.get("features", [])[:4],
                        "strengths": competitor.get("strengths", [])[:3],
                        "weaknesses": competitor.get("weaknesses", [])[:3],
                        "source_quality": competitor.get("source_quality", {}),
                    },
                    "response_style": "Defend market position with pricing, feature, and channel counter-moves grounded in this competitor profile.",
                }
            )
        return blueprints
