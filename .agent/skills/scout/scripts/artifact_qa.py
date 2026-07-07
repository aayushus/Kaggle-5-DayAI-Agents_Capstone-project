from __future__ import annotations

from typing import Any


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    audit = report.get("audit") or {}
    competitors = report.get("competitors") or []
    provenance = report.get("provenance") or {}
    top_down = ((report.get("market_sizing") or {}).get("top_down") or {})
    checks: list[dict[str, Any]] = [
        _check("has_competitors", bool(competitors), "Competitor set is empty."),
        _check("has_primary_facts", bool(provenance.get("source_facts")), "No primary facts were recorded."),
        _check("has_estimated_assumptions", bool(provenance.get("estimated_assumptions")), "No modeled assumptions were recorded."),
        _check("has_top_down_basis", bool(top_down.get("source") or top_down.get("benchmark_basis")), "Top-down TAM basis is missing."),
        _check("audit_passed", bool(audit.get("passed")), "Audit did not pass."),
    ]
    failing = [item for item in checks if not item["passed"]]
    return {
        "passed": not failing,
        "failing_checks": failing,
        "check_count": len(checks),
        "passed_count": len(checks) - len(failing),
    }


def _check(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "message": message,
    }
