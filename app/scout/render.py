from __future__ import annotations

import re
from typing import Any

import yaml


def _money(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"${value:,.0f}"
    return "N/A"


def _percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    return "N/A"


def _line(label: str, value: Any) -> str:
    text = value if isinstance(value, str) else str(value)
    return f"- **{label}:** {_clean_text(text)}"


def _url_line(label: str, value: Any) -> str:
    text = str(value or "").strip()
    return f"- **{label}:** {text or 'N/A'}"


def _bullet_list(label: str, items: list[str]) -> str:
    clean_items = [_clean_text(item) for item in items if item]
    if not clean_items:
        return ""
    joined = "; ".join(clean_items[:4])
    return f"- **{label}:** {joined}"


def _audit_link_lines(audit: dict[str, Any]) -> str:
    link_checks = audit.get("link_checks") or []
    if not link_checks:
        return "- **Link checks:** No audited links recorded."
    lines = []
    for item in link_checks[:10]:
        status = "OK" if item.get("ok") else "Fail"
        code = item.get("status_code") if item.get("status_code") is not None else "-"
        target = item.get("subject") or item.get("kind") or "Link"
        url = item.get("final_url") or item.get("url") or "N/A"
        lines.append(f"- **{target}:** {status} ({code}) {url}")
    return "\n".join(lines)


def _clean_text(value: Any, limit: int = 220) -> str:
    text = str(value or "")
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"\b(skip to main content|download pdf copy|view supplier profile|request quote|linkedin|facebook|reddit|x|sponsored by|reviewed by)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("**", "").replace("##", "").replace("*", " ").replace("`", "").strip(" .")
    return text[:limit] or "N/A"


def render_market_doc(draft: dict[str, Any]) -> str:
    sizing = draft["market_sizing"]
    bottom_up = sizing.get("bottom_up", {})
    top_down = sizing.get("top_down", {})
    assumptions = sizing.get("assumptions", {})
    competitors = draft.get("competitors", [])
    audit = draft.get("audit", {})
    personas = draft.get("customer_personas", [])
    provenance = draft.get("provenance", {})
    source_facts = provenance.get("source_facts", [])
    estimated_assumptions = provenance.get("estimated_assumptions", [])
    landing = draft["landing_page_blueprint"]
    artifact_qa = draft.get("artifact_qa") or {}
    artifact_qa_score = f"{artifact_qa.get('passed_count', 0)}/{artifact_qa.get('check_count', 0)}"
    payload = {
        "project_name": draft["project_name"],
        "brief": draft["brief"],
        "audit": audit,
        "executive_summary": {
            "positioning": draft.get("adk_summary") or landing["hero_subheader"],
            "primary_differentiation": landing.get("differentiation") or landing["value_hooks"][0],
        },
        "competitors": competitors,
        "market_sizing": sizing,
        "provenance": provenance,
        "customer_personas": personas,
        "customer_agent_blueprints": draft.get("customer_agent_blueprints", []),
        "competitor_agent_blueprints": draft.get("competitor_agent_blueprints", []),
        "landing_page_blueprint": landing,
        "audit_notes": draft.get("audit_notes", []),
        "adk_metadata": draft.get("adk_metadata"),
        "simulation_state": draft.get("simulation_state"),
        "artifact_qa": artifact_qa,
    }
    yaml_block = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False, default_flow_style=False)
    competitor_sections = []
    for competitor in competitors:
        competitor_sections.append(
            "\n".join(
                    [
                        f"### {competitor.get('name', 'Unknown competitor')}",
                        _line("Monthly price", _money(competitor.get("price_monthly"))),
                        _url_line("Primary source", competitor.get("source_url") or "N/A"),
                        _url_line("Pricing source", competitor.get("pricing_url") or competitor.get("source_url") or "N/A"),
                        _line("Price basis", competitor.get("price_source_type") or "N/A"),
                        _line("Pricing visibility", competitor.get("pricing_visibility") or "N/A"),
                        _line("Source quality", (competitor.get("source_quality") or {}).get("label") or "N/A"),
                    _bullet_list("Features", competitor.get("features") or []),
                    _bullet_list("Strengths", competitor.get("strengths") or []),
                    _bullet_list("Weaknesses", competitor.get("weaknesses") or []),
                ]
            ).strip()
        )
    fact_sections = []
    for fact in source_facts:
        fact_bag = fact.get("facts", {})
        fact_sections.append(
            "\n".join(
                    [
                        f"### {fact.get('subject', 'Source')}",
                        _url_line("Primary URL", fact_bag.get("source_url") or "N/A"),
                        _url_line("Pricing URL", fact_bag.get("pricing_url") or fact_bag.get("source_url") or "N/A"),
                        _line("Price", _money(fact_bag.get("price_monthly"))),
                        _line("Price basis", fact_bag.get("price_source_type") or "N/A"),
                        _line("Pricing visibility", fact_bag.get("pricing_visibility") or "N/A"),
                    _line("Source quality", (fact_bag.get("source_quality") or {}).get("label") or "N/A"),
                    _bullet_list("Features", fact_bag.get("features") or []),
                    _bullet_list("Evidence", fact.get("evidence") or []),
                ]
            ).strip()
        )
    assumption_sections = []
    for item in estimated_assumptions:
        assumptions_block = item.get("assumptions", {})
        assumption_sections.append(
            "\n".join(
                [
                    f"### {str(item.get('type', 'assumption')).replace('_', ' ').title()}",
                    _line("Subject", item.get("subject") or "N/A"),
                    _line("Reasoning", item.get("reasoning") or "N/A"),
                    *[_line(key.replace('_', ' ').title(), value) for key, value in assumptions_block.items()],
                ]
            ).strip()
        )
    competitors_block = "\n\n".join(competitor_sections) if competitor_sections else "No competitors captured."
    facts_block = "\n\n".join(fact_sections) if fact_sections else "No primary facts recorded."
    assumptions_block = "\n\n".join(assumption_sections) if assumption_sections else "No modeled assumptions recorded."
    personas_block = "\n\n".join(
        [
            "\n".join(
                [
                    f"### {persona.get('name', 'Persona')}",
                    _line("Profile", persona.get("demographics") or "N/A"),
                    _line("Mindset", persona.get("psychographics") or "N/A"),
                    _line("Adoption curve", persona.get("tech_adoption_curve") or "N/A"),
                    _line("Value proposition", persona.get("value_proposition") or "N/A"),
                    _bullet_list("Buying triggers", persona.get("buying_triggers") or []),
                ]
            ).strip()
            for persona in personas
        ]
    ) or "No customer personas recorded."
    return (
        f"# {str(draft['project_name']).rstrip('.').strip()}.market\n\n"
        "Northstar research artifact.\n\n"
        "## Executive Summary\n\n"
        f"{draft.get('adk_summary') or landing['hero_subheader']}\n\n"
        f"{_line('Primary differentiation', landing.get('differentiation') or landing['value_hooks'][0])}\n\n"
        "## Market Sizing Snapshot\n\n"
        f"{_line('TAM', _money(bottom_up.get('tam')))}\n"
        f"{_line('SAM', _money(bottom_up.get('sam')))}\n"
        f"{_line('SOM', _money(bottom_up.get('som')))}\n"
        f"{_line('Average monthly price', _money(assumptions.get('monthly_price')))}\n"
        f"{_line('Capture rate', _percent(assumptions.get('capture_rate')))}\n"
        f"{_line('Top-down TAM', top_down.get('display_value') or _money(top_down.get('tam')))}\n"
        f"{_line('Top-down basis', top_down.get('source_type') or 'N/A')}\n"
        f"{_line('Top-down source', top_down.get('source') or top_down.get('benchmark_basis') or 'N/A')}\n"
        f"{_url_line('Top-down URL', top_down.get('source_url') or 'N/A')}\n"
        f"{(_line('Reconciliation', assumptions.get('reconciliation_note')) + chr(10)) if assumptions.get('reconciliation_note') else ''}\n"
        "## Audit Summary\n\n"
        f"{_line('Passed', 'Yes' if audit.get('passed') else 'No')}\n"
        f"{_line('Schema issues', audit.get('schema_issue_count', 0))}\n"
        f"{_line('Links checked', (audit.get('link_summary') or {}).get('checked', 0))}\n"
        f"{_line('Links failed', (audit.get('link_summary') or {}).get('failed', 0))}\n"
        f"{_bullet_list('Audit notes', draft.get('audit_notes') or [])}\n"
        f"{_audit_link_lines(audit)}\n\n"
        "## Artifact QA\n\n"
        f"{_line('Passed', 'Yes' if artifact_qa.get('passed') else 'No')}\n"
        f"{_line('Checks passed', artifact_qa_score)}\n"
        f"{_bullet_list('Failing checks', [item.get('message') for item in artifact_qa.get('failing_checks', []) if item.get('message')])}\n\n"
        "## Competitive Field\n\n"
        f"{competitors_block}\n\n"
        "## Evidence Discipline\n\n"
        "Primary-source facts are separated from model assumptions so judges can distinguish direct evidence from Northstar synthesis.\n\n"
        "### Primary Facts\n\n"
        f"{facts_block}\n\n"
        "### Modeled Assumptions\n\n"
        f"{assumptions_block}\n\n"
        "## Customer Personas\n\n"
        f"{personas_block}\n\n"
        "## Landing Page Blueprint\n\n"
        f"{_line('Hero title', landing.get('hero_title') or 'N/A')}"
        f"{_line('Hero subheader', landing.get('hero_subheader') or 'N/A')}\n"
        f"{_bullet_list('Value hooks', landing.get('value_hooks') or [])}\n"
        f"{_bullet_list('Objection handling', landing.get('objection_handling_copy') or [])}\n"
        "## Structured Market Matrix\n\n"
        "```yaml\n"
        f"{yaml_block}"
        "```\n"
    )
