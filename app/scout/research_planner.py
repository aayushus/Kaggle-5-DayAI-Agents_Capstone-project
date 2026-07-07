"""LLM-backed research planning and competitor validation.

The heuristic search pipeline needs concept-aware guidance: which market
category this idea belongs to, which vendors actually compete with it, and
which industry phrases will surface market-size reports. Gemini supplies that
context up front; every consumer falls back to the old heuristics when the
model is unavailable, so the pipeline still runs offline.
"""

from __future__ import annotations

import json
from typing import Any

PLAN_AGENT_INSTRUCTION = (
    "You are Northstar's market research planner. You receive a startup brief and "
    "return strict JSON only (no markdown fences, no commentary) with exactly these keys:\n"
    "category: 2-6 word market category label for the concept (e.g. 'AI agent tool integration platform').\n"
    "search_queries: 4-6 web search queries that will surface DIRECT competitor vendor/product pages "
    "(not blog posts, not documentation, not listicles).\n"
    "known_competitors: 4-8 real, currently operating products or companies that directly compete "
    "with this concept. Use their actual brand names.\n"
    "market_size_terms: 2-4 short industry phrases suitable for finding third-party market-size reports "
    "(e.g. 'iPaaS market', 'AI agents market').\n"
    "buyer_estimates: object with n_global_buyers (integer, worldwide organizations/individuals that could buy "
    "this category), n_target_buyers (integer, the subset reachable given the brief's geography and stage), "
    "typical_monthly_price_usd (number), and rationale (one sentence).\n"
    "personas: exactly 2 buyer personas for this concept, each an object with name, demographics, "
    "psychographics, buying_triggers (list of 3 short strings), tech_adoption_curve, value_proposition.\n"
    "positioning: object with hero_title (max 8 punchy words, no colons), hero_subheader (one sentence), "
    "value_hooks (list of 3 short benefit statements specific to this concept), "
    "differentiation (one sentence naming the specific wedge versus the named competitors — what this does "
    "that they do not), and objection_handling (list of exactly 2 short strings, each answering a likely "
    "buyer objection specific to this concept).\n"
    "Ground everything in the concept itself. Never invent URLs."
)

VALIDATE_AGENT_INSTRUCTION = (
    "You are Northstar's competitor auditor. You receive a startup concept, its market category, and a list "
    "of candidate competitor records scraped from the web. For each candidate decide whether it is a real, "
    "directly competing product or company for that concept.\n"
    "Reject: blog posts or articles ABOUT other products, documentation pages, GitHub repositories mislabeled "
    "as the hosting site, broad AI brands that do not sell a competing product, directories, and listicles.\n"
    "Keep: actual vendors whose product overlaps with what the concept sells.\n"
    "Return strict JSON only: {\"verdicts\": [{\"url\": string (echo the candidate url), \"keep\": boolean, "
    "\"canonical_name\": string (the real brand/product name, fix mislabeled names), "
    "\"reason\": one short sentence, "
    "\"weakness_vs_concept\": one short sentence naming a real gap this competitor has versus the concept "
    "(only when keep is true)}]}"
)


def build_research_plan(bridge: Any, brief: dict[str, str], trace: list[str]) -> dict[str, Any] | None:
    """Ask Gemini for a concept-aware research plan. Returns None when unavailable."""
    if bridge is None or not getattr(bridge, "status", None) or not bridge.status.ready:
        trace.append("Research planner skipped: Gemini backend not ready; using heuristic queries.")
        return None
    prompt = (
        f"Startup concept: {brief.get('concept', '')}\n"
        f"Geography: {brief.get('geography', '')}\n"
        f"Sector: {brief.get('sector', '')}\n"
        f"Funding / scale: {brief.get('funding_scale', '')}"
    )
    try:
        plan = bridge.generate_json("northstar_research_planner", PLAN_AGENT_INSTRUCTION, prompt)
    except Exception as exc:
        trace.append(f"Research planner failed ({exc!s}); using heuristic queries.")
        return None
    plan = _sanitize_plan(plan)
    if not plan:
        trace.append("Research planner returned no usable plan; using heuristic queries.")
        return None
    trace.append(
        f"Gemini research planner set category '{plan['category']}' "
        f"with {len(plan.get('known_competitors', []))} seed competitors."
    )
    return plan


def validate_competitor_set(
    bridge: Any,
    brief: dict[str, str],
    plan: dict[str, Any] | None,
    competitors: list[dict[str, Any]],
    trace: list[str],
) -> list[dict[str, Any]]:
    """Ask Gemini to reject non-competitors and fix mislabeled names."""
    if not competitors:
        return competitors
    if bridge is None or not getattr(bridge, "status", None) or not bridge.status.ready:
        return competitors
    category = (plan or {}).get("category") or brief.get("sector") or "this market"
    candidate_lines = []
    for item in competitors[:8]:
        candidate_lines.append(
            json.dumps(
                {
                    "name": item.get("name"),
                    "url": item.get("source_url"),
                    "evidence": (item.get("source_snippets") or [])[:2],
                    "features": (item.get("features") or [])[:3],
                },
                ensure_ascii=False,
            )
        )
    prompt = (
        f"Startup concept: {brief.get('concept', '')}\n"
        f"Market category: {category}\n"
        "Candidates (one JSON object per line):\n" + "\n".join(candidate_lines)
    )
    try:
        result = bridge.generate_json("northstar_competitor_auditor", VALIDATE_AGENT_INSTRUCTION, prompt)
    except Exception as exc:
        trace.append(f"Competitor validation failed ({exc!s}); keeping scraped set.")
        return competitors
    verdicts = (result or {}).get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        trace.append("Competitor validation returned no verdicts; keeping scraped set.")
        return competitors

    by_url = {str(v.get("url") or ""): v for v in verdicts if isinstance(v, dict)}
    kept: list[dict[str, Any]] = []
    rejected: list[str] = []
    for item in competitors:
        verdict = by_url.get(str(item.get("source_url") or ""))
        if verdict is None:
            kept.append(item)
            continue
        if not verdict.get("keep"):
            rejected.append(f"{item.get('name')} ({verdict.get('reason', 'not a direct competitor')})")
            continue
        canonical = str(verdict.get("canonical_name") or "").strip()
        if canonical:
            item["name"] = canonical
        weakness = str(verdict.get("weakness_vs_concept") or "").strip()
        if weakness:
            price_notes = [
                w for w in item.get("weaknesses", [])
                if "pricing appears high" in w.lower()
            ]
            item["weaknesses"] = [weakness, *price_notes][:3]
        item["validation"] = {"kept": True, "reason": verdict.get("reason", "")}
        kept.append(item)
    if rejected:
        trace.append(f"Competitor auditor rejected {len(rejected)}: " + "; ".join(rejected[:4]))
    if kept:
        trace.append(f"Competitor auditor kept {len(kept)} of {len(competitors)} candidates.")
        return kept
    trace.append("Competitor auditor rejected every candidate; keeping scraped set for transparency.")
    return competitors


def _sanitize_plan(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None
    category = str(plan.get("category") or "").strip()
    if not category:
        return None
    def _str_list(value: Any, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:limit]

    sanitized: dict[str, Any] = {
        "category": category[:80],
        "search_queries": _str_list(plan.get("search_queries"), 6),
        "known_competitors": _str_list(plan.get("known_competitors"), 8),
        "market_size_terms": _str_list(plan.get("market_size_terms"), 4),
    }
    buyer = plan.get("buyer_estimates")
    if isinstance(buyer, dict):
        try:
            sanitized["buyer_estimates"] = {
                "n_global_buyers": max(1000.0, float(buyer.get("n_global_buyers", 0))),
                "n_target_buyers": max(500.0, float(buyer.get("n_target_buyers", 0))),
                "typical_monthly_price_usd": max(1.0, float(buyer.get("typical_monthly_price_usd", 0))),
                "rationale": str(buyer.get("rationale") or "").strip(),
            }
        except Exception:
            pass
    personas = plan.get("personas")
    if isinstance(personas, list):
        cleaned_personas = []
        for item in personas[:2]:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            cleaned_personas.append(
                {
                    "name": str(item.get("name")).strip(),
                    "demographics": str(item.get("demographics") or "").strip(),
                    "psychographics": str(item.get("psychographics") or "").strip(),
                    "buying_triggers": _str_list(item.get("buying_triggers"), 4),
                    "tech_adoption_curve": str(item.get("tech_adoption_curve") or "").strip(),
                    "value_proposition": str(item.get("value_proposition") or "").strip(),
                }
            )
        if len(cleaned_personas) >= 2:
            sanitized["personas"] = cleaned_personas
    positioning = plan.get("positioning")
    if isinstance(positioning, dict) and positioning.get("hero_title"):
        sanitized["positioning"] = {
            "hero_title": str(positioning.get("hero_title")).strip()[:90],
            "hero_subheader": str(positioning.get("hero_subheader") or "").strip()[:180],
            "value_hooks": _str_list(positioning.get("value_hooks"), 3),
            "differentiation": str(positioning.get("differentiation") or "").strip()[:220],
            "objection_handling": _str_list(positioning.get("objection_handling"), 2),
        }
    return sanitized
