from __future__ import annotations

import os
import shutil
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

try:
    importlib.import_module("mcp.client.session")
except Exception:
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")

    class _FastMCPStub:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self, *_args, **_kwargs):
            def decorator(fn):
                return fn
            return decorator

        def resource(self, *_args, **_kwargs):
            def decorator(fn):
                return fn
            return decorator

        def sse_app(self):
            async def app(*_args, **_kwargs):
                return None
            return app

    fastmcp_module.FastMCP = _FastMCPStub
    sys.modules.setdefault("mcp", types.ModuleType("mcp"))
    sys.modules.setdefault("mcp.server", types.ModuleType("mcp.server"))
    sys.modules["mcp.server.fastmcp"] = fastmcp_module

try:
    importlib.import_module("bs4")
except Exception:
    bs4_module = types.ModuleType("bs4")

    class _BeautifulSoupStub:
        def __init__(self, *_args, **_kwargs):
            pass

    bs4_module.BeautifulSoup = _BeautifulSoupStub
    sys.modules["bs4"] = bs4_module

os.environ["NORTHSTAR_LOCAL_MCP_ENABLED"] = "false"

from app.config import load_settings
from app.main import (
    OUTPUT_DIR,
    _apply_board_feedback_to_report,
    _apply_war_feedback_to_report,
    _persist_session_report,
    _resolve_session_report,
    artifact_pdf,
)
from app.scout.artifact_store import load_market_artifact, save_market_artifact
from app.scout.chat_sessions import create_session
from app.scout.competitor_names import sanitize_competitor_name
from app.scout.orchestrator import ScoutOrchestrator
from app.scout.skill_runtime import load_pricing_normalizer_module


def sample_report() -> dict:
    return {
        "project_name": "Northstar Test",
        "brief": {
            "concept": "Automated indoor vertical farming using IoT sensors",
            "geography": "United States",
            "sector": "AgTech",
            "funding_scale": "Seed",
        },
        "audit": {
            "passed": True,
            "feedback": [],
            "schema_issue_count": 0,
            "link_summary": {"checked": 1, "failed": 0, "passed": 1},
            "link_checks": [
                {
                    "kind": "competitor_source",
                    "subject": "Acme",
                    "url": "https://example.com",
                    "ok": True,
                    "status_code": 200,
                    "final_url": "https://example.com",
                    "content_type": "text/html",
                    "error": "",
                }
            ],
        },
        "competitors": [
            {
                "name": "Acme",
                "source_url": "https://example.com",
                "pricing_url": "https://example.com/pricing",
                "source_snippets": ["Realtime dashboard for indoor farm operators."],
                "price_monthly": 79.0,
                "price_source_type": "extracted",
                "pricing_visibility": "public-price",
                "features": ["Sensor automation", "Realtime dashboard", "Alerts"],
                "strengths": ["Clear positioning"],
                "weaknesses": ["No clear offline capability in public feature copy"],
                "source_quality": {"label": "High", "score": 90},
            }
        ],
        "market_sizing": {
            "assumptions": {
                "monthly_price": 79.0,
                "annual_price": 948.0,
                "n_global_customers": 220000.0,
                "n_target_customers": 50000.0,
                "capture_rate": 0.01,
                "sector_profile": "AgTech operators",
                "formulae": {"annual_price": "monthly_price * 12"},
            },
            "bottom_up": {"tam": 1000.0, "sam": 500.0, "som": 5.0},
            "top_down": {"tam": 900.0, "source": "Benchmark", "source_type": "benchmark"},
        },
        "provenance": {
            "source_facts": [
                {
                    "type": "competitor_evidence",
                    "subject": "Acme",
                    "facts": {
                        "source_url": "https://example.com",
                        "pricing_url": "https://example.com/pricing",
                        "price_monthly": 79.0,
                        "price_source_type": "extracted",
                        "pricing_visibility": "public-price",
                        "features": ["Sensor automation"],
                        "source_quality": {"label": "High"},
                    },
                    "evidence": ["Realtime dashboard for indoor farm operators."],
                }
            ],
            "estimated_assumptions": [
                {
                    "type": "market_sizing_assumption",
                    "subject": "Northstar Test",
                    "assumptions": {"monthly_price": 79.0},
                    "reasoning": "modeled",
                }
            ],
        },
        "customer_personas": [
            {
                "name": "Persona One",
                "demographics": "d1",
                "psychographics": "p1",
                "buying_triggers": ["ROI"],
                "tech_adoption_curve": "Early adopter",
                "value_proposition": "v1",
            },
            {
                "name": "Persona Two",
                "demographics": "d2",
                "psychographics": "p2",
                "buying_triggers": ["Ease"],
                "tech_adoption_curve": "Late majority",
                "value_proposition": "v2",
            },
        ],
        "customer_agent_blueprints": [],
        "competitor_agent_blueprints": [
            {
                "competitor_name": "pricing",
                "source_url": "https://github.com/calcom/cal.diy",
                "system_constraints": {
                    "price_monthly": 0,
                    "features": ["Self-hosted"],
                    "weaknesses": ["Offline unclear"],
                },
            }
        ],
        "market_matrix": [
            {
                "competitor": "Acme",
                "price_monthly": 79.0,
                "features": {"Sensor automation": True},
                "sources": ["Realtime dashboard for indoor farm operators."],
            }
        ],
        "landing_page_blueprint": {
            "hero_title": "Title",
            "hero_subheader": "Subheader",
            "differentiation": "Audited market research",
            "value_hooks": ["Audited market research"],
            "objection_handling_copy": ["Pilot first"],
        },
        "audit_notes": ["Audit passed: True"],
        "simulation_state": {},
    }


class NorthstarFlowTests(unittest.TestCase):
    def test_competitor_name_sanitization_uses_url_fallback(self):
        self.assertEqual(
            sanitize_competitor_name("pricing", "https://github.com/calcom/cal.diy"),
            "cal.diy",
        )
        self.assertEqual(
            sanitize_competitor_name("  Acme Pricing  ", "https://acme.com"),
            "Acme",
        )

    def test_artifact_reload_preserves_audit_and_artifact_qa(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "artifact.market.md"
            original = sample_report()
            save_market_artifact(str(artifact_path), original)
            loaded, _ = load_market_artifact(str(artifact_path))

            self.assertTrue(loaded["audit"]["passed"])
            self.assertIn("artifact_qa", loaded)
            self.assertTrue(loaded["artifact_qa"]["passed"])

            resolved = _resolve_session_report({}, str(artifact_path))
            self.assertTrue(resolved["audit"]["passed"])
            self.assertTrue(resolved["artifact_qa"]["passed"])

    def test_board_to_war_room_continuity_persists_same_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "continuity.market.md"
            report = sample_report()
            save_market_artifact(str(artifact_path), report)

            session = create_session("board", report, "Start", market_markdown_path=str(artifact_path))
            board_payload = {
                "recommendation": "Advance with a pilot-first offer.",
                "blocking_issue": "implementation proof",
                "fit_scores": {"trust_readiness": 82},
                "responses": [
                    {
                        "friction_points": ["Needs rollout proof"],
                        "requested_changes": ["Add a quantified before/after outcome."],
                    }
                ],
            }
            updated_report = _apply_board_feedback_to_report(session.report, board_payload)
            _persist_session_report(session, updated_report)

            reloaded = _resolve_session_report({}, str(artifact_path))
            self.assertIn("latest_board_feedback", reloaded["simulation_state"])

            war_payload = {
                "counter_moves": ["Launch with a narrow ICP and a constrained pilot scope."],
                "responses": [],
            }
            updated_report = _apply_war_feedback_to_report(reloaded, war_payload)
            session = create_session("war-room", updated_report, "Scenario", market_markdown_path=str(artifact_path))
            _persist_session_report(session, updated_report)

            final_report, _ = load_market_artifact(str(artifact_path))
            self.assertIn("latest_board_feedback", final_report["simulation_state"])
            self.assertIn("latest_war_room", final_report["simulation_state"])
            self.assertTrue(
                any("Defensive edge:" in hook for hook in final_report["landing_page_blueprint"]["value_hooks"])
            )

    def test_pdf_export_endpoint_returns_pdf(self):
        artifact_path = OUTPUT_DIR / "_test_pdf_export.market.md"
        save_market_artifact(str(artifact_path), sample_report())
        try:
            response = artifact_pdf(str(artifact_path))
            self.assertEqual(response.media_type, "application/pdf")
            self.assertEqual(Path(response.path).suffix, ".pdf")
            self.assertTrue(Path(response.path).exists())
            self.assertGreater(Path(response.path).stat().st_size, 100)
        finally:
            artifact_path.unlink(missing_ok=True)
            artifact_path.with_suffix(".pdf").unlink(missing_ok=True)

    def test_md_to_html_formatting(self):
        from app.scout.pdf_export import _md_to_html
        text = "This is **bold** and *italic* and `code` and [link](https://example.com)."
        html = _md_to_html(text)
        self.assertIn("<b>bold</b>", html)
        self.assertIn("<i>italic</i>", html)
        self.assertIn('<font face="Courier">code</font>', html)
        self.assertIn('<a href="https://example.com"><font color="blue"><u>link</u></font></a>', html)

    def test_propstream_pricing_override(self):
        pricing = load_pricing_normalizer_module()
        self.assertEqual(pricing.extract_monthly_price("PropStream pricing is $81/mo billed annually or $99/mo monthly"), 99.0)

    def test_citation_source_label_formatting(self):
        from app.scout.parallel_search import _assess_competitor_source_quality
        
        # Test High quality source
        high_quality = _assess_competitor_source_quality(
            url="https://acme.com",
            snippets=["Evidence snippet 1", "Evidence snippet 2"],
            features=["Feature A", "Feature B", "Feature C"],
            price=99.0,
            extracted_price=True,
            pricing_url="https://acme.com/pricing"
        )
        self.assertEqual(high_quality["label"], "High")
        self.assertGreaterEqual(high_quality["score"], 75)

        # Test Low quality source
        low_quality = _assess_competitor_source_quality(
            url="https://capterra.com",
            snippets=[],
            features=[],
            price=None,
            extracted_price=False,
            pricing_url=""
        )
        self.assertEqual(low_quality["label"], "Low")
        self.assertLess(low_quality["score"], 55)

    def test_session_update_flows(self):
        from app.main import _apply_board_feedback_to_report, _apply_war_feedback_to_report
        report = sample_report()
        
        board_payload = {
            "recommendation": "Try X",
            "blocking_issue": "friction",
            "fit_scores": {"trust": 90},
            "responses": [
                {
                    "friction_points": ["too expensive"],
                    "requested_changes": ["reduce price"],
                }
            ]
        }
        updated_board = _apply_board_feedback_to_report(report, board_payload)
        self.assertIn("Buyer concern: too expensive", updated_board["landing_page_blueprint"]["objection_handling_copy"])
        self.assertIn("Try X", updated_board["landing_page_blueprint"]["value_hooks"])

        war_payload = {
            "counter_moves": ["Move A"],
            "responses": []
        }
        updated_war = _apply_war_feedback_to_report(updated_board, war_payload)
        self.assertIn("Defensive edge: Move A", updated_war["landing_page_blueprint"]["value_hooks"])

    def test_security_middlewares(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        large_body = "x" * (5 * 1024 * 1024 + 100)
        response = client.post("/api/run", content=large_body)
        self.assertEqual(response.status_code, 413)
        self.assertIn("Request body too large", response.json()["detail"])

    def test_fallback_pricing_behavior(self):
        pricing = load_pricing_normalizer_module()
        self.assertEqual(pricing.extract_monthly_price("Starting at $79 monthly"), 79.0)
        self.assertEqual(
            pricing.fallback_price_estimate(
                "https://github.com/calcom/cal.diy",
                "pricing",
                ["Self-hosted"],
                ["Open source community edition"],
            ),
            0.0,
        )
        self.assertEqual(
            pricing.fallback_price_estimate(
                "https://vendor.example/agtech",
                "FarmOS",
                ["IoT monitoring", "Sensor automation"],
                ["Vertical farm analytics"],
            ),
            129.0,
        )

    def test_orchestrator_retries_after_audit_failure(self):
        tempdir = tempfile.mkdtemp()
        try:
            orchestrator = ScoutOrchestrator(output_dir=Path(tempdir), settings=load_settings())
            failing = sample_report()
            failing["audit"] = {"passed": False, "feedback": ["No competitors found."]}
            passing = sample_report()
            passing["audit"] = {"passed": True, "feedback": []}

            orchestrator.runtime.backend = "local"
            orchestrator.runtime.run = Mock(side_effect=[failing, passing])
            orchestrator.google_adk.status.ready = False
            orchestrator.google_adk.status.reason = "disabled for test"

            result = orchestrator.run(
                {
                    "concept": "Retry Test",
                    "geography": "United States",
                    "sector": "AgTech",
                    "funding_scale": "Seed",
                }
            )

            self.assertEqual(orchestrator.runtime.run.call_count, 2)
            self.assertTrue(result.report["audit"]["passed"])
            self.assertTrue(any("Audit failed; researcher is revising the draft." in item for item in result.thinking_trace))
            self.assertTrue(Path(result.market_markdown_path).exists())
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
