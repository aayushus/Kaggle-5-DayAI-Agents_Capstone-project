from __future__ import annotations

from math import isfinite
from typing import Any

from app.scout.skill_runtime import load_market_schema, load_verify_links_module


def audit_market_doc(draft: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    schema_issues = _validate_against_skill_schema(draft)
    issues.extend(schema_issues)
    link_checks: list[dict[str, Any]] = []

    brief = draft.get("brief", {})
    required_brief_fields = ["concept", "geography", "sector", "funding_scale"]
    for field in required_brief_fields:
        if not brief.get(field):
            issues.append(f"Brief field {field} is missing.")

    competitors = draft.get("competitors", [])
    if not competitors:
        issues.append("No competitors found.")
    for competitor in competitors:
        competitor_name = competitor.get("name", "unknown")
        if not competitor.get("source_url"):
            issues.append(f"Competitor {competitor_name} is missing a source URL.")
        if not competitor.get("source_snippets"):
            issues.append(f"Competitor {competitor_name} is missing source snippets.")
        if not isinstance(competitor.get("price_monthly"), (int, float)):
            issues.append(f"Competitor {competitor_name} price must be numeric.")
        elif not isfinite(float(competitor["price_monthly"])):
            issues.append(f"Competitor {competitor_name} price must be finite.")
        if not competitor.get("features"):
            issues.append(f"Competitor {competitor_name} is missing extracted features.")

        link_checks.extend(
            _audit_link_targets(
                [
                    ("competitor_source", competitor_name, competitor.get("source_url")),
                    ("competitor_pricing", competitor_name, competitor.get("pricing_url")),
                ]
            )
        )

    market_sizing = draft.get("market_sizing", {})
    assumptions = market_sizing.get("assumptions", {})
    bottom_up = market_sizing.get("bottom_up", {})
    top_down = market_sizing.get("top_down", {})

    for key in ["monthly_price", "annual_price", "n_global_customers", "n_target_customers", "capture_rate"]:
        if not isinstance(assumptions.get(key), (int, float)):
            issues.append(f"Market sizing assumption {key} must be numeric.")
        elif not isfinite(float(assumptions[key])):
            issues.append(f"Market sizing assumption {key} must be finite.")
    if not assumptions.get("formulae"):
        issues.append("Market sizing formulas are missing.")

    for key in ["tam", "sam", "som"]:
        if not isinstance(bottom_up.get(key), (int, float)):
            issues.append(f"Bottom-up {key} must be numeric.")
        elif not isfinite(float(bottom_up[key])):
            issues.append(f"Bottom-up {key} must be finite.")

    if not isinstance(top_down.get("tam"), (int, float)):
        issues.append("Top-down TAM must be numeric.")
    elif isfinite(float(top_down["tam"])) and isfinite(float(bottom_up.get("tam", 0))):
        if float(bottom_up["tam"]) > 0:
            ratio = max(float(top_down["tam"]) / float(bottom_up["tam"]), float(bottom_up["tam"]) / float(top_down["tam"]))
            if ratio > 10:
                issues.append("Top-down TAM and bottom-up TAM differ by more than 10x.")
    if not top_down.get("source"):
        issues.append("Top-down TAM source/basis is missing.")
    if top_down.get("source_type") == "external":
        if not top_down.get("source_url"):
            issues.append("Externally sourced top-down TAM is missing a source URL.")
        if not top_down.get("source_excerpt"):
            issues.append("Externally sourced top-down TAM is missing a source excerpt.")
    link_checks.extend(_audit_link_targets([("top_down_source", "Top-down TAM", top_down.get("source_url"))]))

    if not draft.get("customer_personas"):
        issues.append("At least two customer personas are required.")
    elif len(draft["customer_personas"]) < 2:
        issues.append("At least two distinct customer personas are required.")

    blueprint = draft.get("landing_page_blueprint", {})
    if not blueprint.get("hero_title"):
        issues.append("Landing page hero title is missing.")
    if not blueprint.get("value_hooks"):
        issues.append("Landing page value hooks are missing.")

    if not draft.get("market_matrix"):
        issues.append("Structured market matrix is missing.")
    provenance = draft.get("provenance", {})
    if not provenance.get("source_facts"):
        issues.append("Primary-source facts are missing from provenance.")
    if not provenance.get("estimated_assumptions"):
        issues.append("Estimated assumptions are missing from provenance.")

    if not isinstance(market_sizing.get("bottom_up", {}).get("tam"), (int, float)):
        issues.append("TAM must be numeric.")

    for link_check in link_checks:
        if not link_check["ok"]:
            issues.append(
                f"{link_check['subject']} {link_check['kind'].replace('_', ' ')} URL did not resolve."
            )

    failed_link_checks = [item for item in link_checks if not item["ok"]]
    return {
        "passed": not issues,
        "feedback": issues,
        "schema_issue_count": len(schema_issues),
        "link_summary": {
            "checked": len(link_checks),
            "failed": len(failed_link_checks),
            "passed": len(link_checks) - len(failed_link_checks),
        },
        "link_checks": link_checks,
    }


def validate_market_doc(draft: dict[str, Any]) -> list[str]:
    return list(audit_market_doc(draft).get("feedback", []))


def _audit_link_targets(targets: list[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for kind, subject, url in targets:
        text = str(url or "").strip()
        if not text:
            continue
        dedupe_key = (kind, subject, text)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        checks.append(_check_url(kind, subject, text))
    return checks


def _check_url(kind: str, subject: str, url: str) -> dict[str, Any]:
    verify_links = load_verify_links_module()
    result = verify_links.check_url(url)
    return {
        "kind": kind,
        "subject": subject,
        "url": url,
        "ok": bool(result.ok),
        "status_code": result.status_code,
        "final_url": result.final_url,
        "content_type": result.content_type,
        "error": result.error,
    }


def _validate_against_skill_schema(draft: dict[str, Any]) -> list[str]:
    schema = load_market_schema()
    issues: list[str] = []
    if not isinstance(schema, dict):
        return issues
    _walk_schema(schema, draft, "", issues)
    return issues


def _walk_schema(schema_node: Any, value: Any, path: str, issues: list[str]) -> None:
    label = path or "root"
    if isinstance(schema_node, str):
        if schema_node == "string" and not isinstance(value, str):
            issues.append(f"Schema check failed: {label} must be a string.")
        elif schema_node == "number" and not isinstance(value, (int, float)):
            issues.append(f"Schema check failed: {label} must be numeric.")
        return
    if isinstance(schema_node, dict):
        if not isinstance(value, dict):
            issues.append(f"Schema check failed: {label} must be an object.")
            return
        for key, child_schema in schema_node.items():
            child_path = f"{label}.{key}" if path else key
            if key not in value:
                issues.append(f"Schema check failed: {child_path} is missing.")
                continue
            _walk_schema(child_schema, value.get(key), child_path, issues)
        return
    if isinstance(schema_node, list) and schema_node:
        if not isinstance(value, list):
            issues.append(f"Schema check failed: {label} must be a list.")
            return
        child_schema = schema_node[0]
        for index, item in enumerate(value[:3]):
            _walk_schema(child_schema, item, f"{label}[{index}]", issues)
