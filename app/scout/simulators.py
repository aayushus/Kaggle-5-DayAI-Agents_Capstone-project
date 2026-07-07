from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from app.scout.competitor_names import sanitize_competitor_name


def simulate_customer_advisory_board(
    report: dict[str, Any],
    prompt: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    history = history or []
    blueprints = report.get("customer_agent_blueprints", [])
    personas = report.get("customer_personas", [])
    persona_specs = []
    if blueprints:
        for item in blueprints:
            constraints = item.get("system_constraints", {})
            persona_specs.append(
                {
                    "name": item.get("persona_name"),
                    "buying_triggers": constraints.get("buying_triggers", []),
                    "value_proposition": constraints.get("value_proposition"),
                    "tech_adoption_curve": constraints.get("tech_adoption_curve"),
                }
            )
    else:
        persona_specs = personas
    lower_prompt = prompt.lower()
    mentions_price = "$" in prompt or "price" in lower_prompt or "month" in lower_prompt
    mentions_pilot = "pilot" in lower_prompt or "trial" in lower_prompt
    mentions_roi = "roi" in lower_prompt or "payback" in lower_prompt or "savings" in lower_prompt
    turn_number = max(1, len(history) // 2 + 1)
    feedback = []
    fit_scores = {
        "problem_urgency": 78 if mentions_roi else 70,
        "budget_fit": 74 if mentions_price else 62,
        "implementation_clarity": 76 if mentions_pilot else 64,
        "trust_readiness": 68 + min(turn_number * 3, 12),
    }
    for persona in persona_specs:
        name = persona.get("name", "Unknown persona")
        is_growth = "growth" in name.lower()
        base_score = 80 if is_growth else 66
        base_score += 4 if mentions_roi else 0
        base_score += 3 if mentions_pilot else 0
        base_score -= 5 if not mentions_price else 0
        sentiment = max(48, min(92, base_score + turn_number))
        decision = "Buy" if sentiment >= 80 else "Pilot First" if sentiment >= 68 else "Request Changes"
        objections = [
            f"{name} wants a sharper statement of measurable business value.",
            f"{name} needs proof that onboarding is controlled and low-friction.",
        ]
        if not mentions_price:
            objections.append(f"{name} says willingness to pay cannot be judged without a pricing anchor.")
        if is_growth and not mentions_roi:
            objections.append(f"{name} wants the pitch tied to speed, experiment velocity, or revenue lift.")
        if not is_growth and not mentions_pilot:
            objections.append(f"{name} prefers a smaller pilot scope before a full subscription commitment.")
        feedback.append(
            {
                "persona": name,
                "sentiment_score": sentiment,
                "buying_decision": decision,
                "product_fit": "Strong" if sentiment >= 80 else "Promising" if sentiment >= 68 else "Fragile",
                "friction_points": objections[:3],
                "requested_changes": [
                    "Add a quantified before/after outcome.",
                    "Clarify rollout timeline, support, and first success milestone.",
                ],
                "quote": (
                    f"{name}: I see the value, but I need proof this can deliver predictable results "
                    "without creating another operational burden."
                ),
            }
        )
    average = round(sum(item["sentiment_score"] for item in feedback) / len(feedback), 1) if feedback else 0.0
    recommendation = (
        "Advance with the current offer."
        if average >= 80
        else "Advance with a pilot-first offer and stronger proof points."
        if average >= 68
        else "Revise the pitch before launch."
    )
    main_blocker = "pricing clarity" if not mentions_price else "implementation proof" if not mentions_pilot else "ROI specificity"
    return {
        "mode": "advisory-board",
        "turn_number": turn_number,
        "prompt": prompt,
        "average_sentiment": average,
        "recommendation": recommendation,
        "fit_scores": fit_scores,
        "blocking_issue": main_blocker,
        "reply": (
            f"The board response is {average:.1f}/100. Main blocker: {main_blocker}. "
            f"Recommendation: {recommendation}"
        ),
        "next_questions": [
            "What is the first pilot package and success metric?",
            "How do buyers justify the monthly fee internally?",
        ],
        "responses": feedback,
    }


def simulate_competitor_war_room(
    report: dict[str, Any],
    scenario: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    history = history or []
    blueprints = report.get("competitor_agent_blueprints", [])
    competitors = report.get("competitors", [])
    competitor_specs = []
    if blueprints:
        seen_names: set[str] = set()
        for item in blueprints:
            constraints = item.get("system_constraints", {})
            competitor_name = sanitize_competitor_name(item.get("competitor_name"), item.get("source_url"))
            normalized = competitor_name.lower()
            if not competitor_name or normalized in seen_names:
                continue
            seen_names.add(normalized)
            competitor_specs.append(
                {
                    "name": competitor_name,
                    "price_monthly": constraints.get("price_monthly"),
                    "features": constraints.get("features", []),
                    "weaknesses": constraints.get("weaknesses", []),
                }
            )
    else:
        seen_names: set[str] = set()
        for item in competitors:
            competitor_name = sanitize_competitor_name(item.get("name"), item.get("source_url"))
            normalized = competitor_name.lower()
            if not competitor_name or normalized in seen_names:
                continue
            seen_names.add(normalized)
            competitor_specs.append(item | {"name": competitor_name})
    lower_scenario = scenario.lower()
    turn_number = max(1, len(history) // 2 + 1)
    responses = []
    threat_level = "Low"
    for competitor in competitor_specs:
        weaknesses = competitor.get("weaknesses", [])
        price = float(competitor.get("price_monthly") or 0)
        price_reaction = "Undercut with a discount bundle" if "$49" in scenario or "49" in lower_scenario else "Hold pricing and add annual incentives"
        feature_reaction = f"Accelerate fixes around {weaknesses[0]}" if weaknesses else "Ship parity features to neutralize the launch"
        channel_reaction = "Lean on incumbent distribution and existing buyer trust"
        risk = "High" if "offline" in lower_scenario or "enterprise" in lower_scenario else "Medium" if weaknesses else "Low"
        confidence = "High" if price >= 99 or risk == "High" else "Medium"
        responses.append(
            {
                "competitor": competitor.get("name"),
                "pricing_reaction": price_reaction,
                "feature_reaction": feature_reaction,
                "channel_reaction": channel_reaction,
                "defensive_risk": risk,
                "confidence": confidence,
            }
        )
        if risk == "High":
            threat_level = "High"
        elif risk == "Medium" and threat_level != "High":
            threat_level = "Medium"
    risk_matrix = [
        _risk_item("Pricing retaliation", 4 if "$49" in scenario or "discount" in lower_scenario else 3, 4, "Protect margin with a pilot bundle and annual contract framing."),
        _risk_item("Feature parity sprint", 4 if competitors else 2, 3, "Differentiate on workflow proof, not just check-box features."),
        _risk_item("Distribution lockout", 4 if "enterprise" in lower_scenario else 3, 4, "Win a narrow ICP wedge with faster onboarding and proof assets."),
        _risk_item("Trust narrative attack", 3 + min(turn_number - 1, 1), 3, "Publish evidence, references, and quantified rollout outcomes."),
    ]
    return {
        "mode": "war-room",
        "turn_number": turn_number,
        "scenario": scenario,
        "threat_level": threat_level,
        "reply": (
            f"The war room grades this scenario as {threat_level} threat. "
            "Expect incumbents to defend on price, parity, and trust."
        ),
        "counter_moves": [
            "Launch with a narrow ICP and a constrained pilot scope.",
            "Lead with proof of speed-to-value rather than full-suite parity.",
            "Package switching risk reduction into onboarding and guarantees.",
        ],
        "risk_matrix": risk_matrix,
        "responses": responses,
    }


async def stream_customer_advisory_board(
    report: dict[str, Any],
    prompt: str,
    history: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    payload = simulate_customer_advisory_board(report, prompt, history=history)
    async for event in _stream_payload(
        ["Customer advisory board is reviewing the updated pitch.", "Panelists are scoring budget fit and rollout clarity."],
        payload,
    ):
        yield event


async def stream_competitor_war_room(
    report: dict[str, Any],
    scenario: str,
    history: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    payload = simulate_competitor_war_room(report, scenario, history=history)
    async for event in _stream_payload(
        ["Competitor war room is modeling defensive reactions.", "Incumbent pricing, roadmap, and channel responses are being mapped."],
        payload,
    ):
        yield event


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_payload(messages: list[str], payload: dict[str, Any]) -> AsyncIterator[str]:
    for message in messages:
        yield _sse({"type": "trace", "message": message})
        await asyncio.sleep(0)
    yield _sse({"type": "result", "payload": payload})


def _risk_item(title: str, likelihood: int, impact: int, counter: str) -> dict[str, Any]:
    score = likelihood * impact
    if score >= 16:
        severity = "High"
    elif score >= 9:
        severity = "Medium"
    else:
        severity = "Low"
    return {
        "title": title,
        "likelihood": likelihood,
        "impact": impact,
        "severity": severity,
        "counter_move": counter,
    }
