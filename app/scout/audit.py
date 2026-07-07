from __future__ import annotations

from typing import Any

from app.scout.verify import audit_market_doc


class AuditorAgent:
    def audit(self, draft: dict[str, Any], trace: list[str]) -> dict[str, Any]:
        trace.append("Auditor agent is validating structure, URLs, and numeric sanity.")
        audit = audit_market_doc(draft)
        link_summary = audit.get("link_summary", {})
        trace.append(
            "Northstar skill audit loaded schema and URL verifier."
        )
        trace.append(
            "Audit checked "
            f"{link_summary.get('checked', 0)} link(s); "
            f"{link_summary.get('failed', 0)} failed."
        )
        return audit
