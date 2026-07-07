from __future__ import annotations

from statistics import median
from typing import Any
import re

from app.config import load_settings
from app.scout.local_mcp_client import search_market_size as local_mcp_search_market_size
from app.scout.parallel_search import parallel_market_size_search
from app.scout.skill_runtime import load_pricing_normalizer_module, load_tam_formula_module

MAX_TOP_DOWN_AUDIT_RATIO = 9.5
MARKET_SOURCE_CACHE: dict[str, dict[str, Any]] = {}
PRICING_NORMALIZER = load_pricing_normalizer_module()


def estimate_tam(
    competitors: list[dict[str, Any]],
    brief: dict[str, str],
    trace: list[str],
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extracted_prices = [
        c["price_monthly"]
        for c in competitors
        if isinstance(c.get("price_monthly"), (int, float))
        and c.get("price_source_type") == "extracted"
    ]
    all_prices = [c["price_monthly"] for c in competitors if isinstance(c.get("price_monthly"), (int, float))]
    sector = brief.get("sector", "").lower()
    geography = brief.get("geography", "").lower()
    profile = _sector_profile(sector)
    geo_multiplier = 0.22 if "united states" in geography or geography == "us" else 0.12 if geography else 0.18

    buyer_estimates = (plan or {}).get("buyer_estimates") or {}
    plan_global = buyer_estimates.get("n_global_buyers")
    plan_target = buyer_estimates.get("n_target_buyers")
    plan_price = buyer_estimates.get("typical_monthly_price_usd")

    plan_category = str((plan or {}).get("category") or "").strip()
    if isinstance(plan_global, (int, float)) and plan_global > 0:
        n_global = float(plan_global)
        n_target = float(plan_target) if isinstance(plan_target, (int, float)) and plan_target > 0 else max(500.0, round(n_global * geo_multiplier, 0))
        basis_label = plan_category or "Gemini-modeled buyer base"
        trace.append(
            f"Market sizing used Gemini buyer estimates: {int(n_global):,} global / {int(n_target):,} target buyers."
        )
    else:
        n_global = float(profile["global_accounts"])
        n_target = max(5000.0, round(n_global * geo_multiplier, 0))
        basis_label = profile["label"]
        trace.append(
            f"Market sizing model used sector profile '{profile['label']}' with geo multiplier {geo_multiplier:.2f}."
        )

    # Prefer real extracted competitor prices; fall back to the planner's price, then a default.
    if extracted_prices:
        monthly_price = median(extracted_prices)
    elif isinstance(plan_price, (int, float)) and plan_price > 0:
        monthly_price = float(plan_price)
    elif all_prices:
        monthly_price = float(PRICING_NORMALIZER.normalize_price_band(all_prices)["monthly_price"])
    else:
        monthly_price = 49.0
    formula_module = load_tam_formula_module()
    baseline = formula_module.compute(
        [float(monthly_price)],
        n_global_customers=n_global,
        n_target_customers=n_target,
        capture_rate=0.01,
    )
    annual_price = float(baseline["annual_price"])
    bottom_up_tam = float(baseline["tam"])
    bottom_up_sam = float(baseline["sam"])
    bottom_up_som = float(baseline["som"])
    trace.append("Northstar skill runtime supplied the baseline TAM formulas.")
    settings = load_settings()
    cache_key = _market_cache_key(brief)
    market_terms = [term for term in (plan or {}).get("market_size_terms", []) if term]
    external_candidates: list[dict[str, Any]] = []
    if settings.local_mcp_enabled:
        external_candidates = local_mcp_search_market_size(
            concept=brief.get("concept", ""),
            geography=brief.get("geography", ""),
            sector=brief.get("sector", ""),
            trace=trace,
            url=settings.local_mcp_url,
        )
    if not external_candidates:
        external_candidates = parallel_market_size_search(
            brief.get("concept", ""),
            brief.get("geography", ""),
            brief.get("sector", ""),
            trace,
            mode=settings.parallel_search_mode,
            market_terms=market_terms,
        )
    cached_candidate = MARKET_SOURCE_CACHE.get(cache_key)
    candidate_pool = _merge_market_candidates(external_candidates, [cached_candidate] if cached_candidate else [])
    if cached_candidate and not external_candidates:
        trace.append("Reusing cached external top-down market source while live search is sparse.")
    top_down = _select_top_down_market_size(candidate_pool, bottom_up_tam, profile)
    if top_down.get("source_type") == "external":
        MARKET_SOURCE_CACHE[cache_key] = {
            "source_url": top_down.get("source_url"),
            "source_title": top_down.get("source_title"),
            "source_snippet": top_down.get("source_excerpt"),
            "market_size_usd": top_down.get("tam"),
            "display_value": top_down.get("display_value"),
            "match_kind": "cached-selected-market-source",
            "industry_hint": profile["label"],
            "confidence_score": top_down.get("confidence_score", 0.0),
            "confidence_reasons": top_down.get("confidence_reasons", []),
        }
        trace.append(
            f"Top-down TAM sourced from third-party evidence: {top_down.get('display_value')} via {top_down.get('source')}."
        )
    else:
        trace.append("Top-down TAM fell back to the internal benchmark profile because no external candidate passed selection.")

    # Reconcile: a bottom-up TAM cannot exceed the total top-down market it lives
    # inside. When a credible external market size is smaller than the bottom-up
    # figure, the modeled global-buyer count was too broad, so cap it to the
    # buyers that market can actually support (top_down / annual price). This only
    # moves TAM; SAM/SOM depend on the target-segment count and stay put.
    reconciliation_note = None
    top_down_tam_value = float(top_down.get("tam") or 0)
    if (
        top_down.get("source_type") == "external"
        and top_down_tam_value > 0
        and annual_price > 0
        and bottom_up_tam > top_down_tam_value
    ):
        original_tam = bottom_up_tam
        original_global = n_global
        n_global = round(top_down_tam_value / annual_price, 0)
        bottom_up_tam = n_global * annual_price
        top_down["top_down_ratio"] = (top_down_tam_value / bottom_up_tam) if bottom_up_tam else None
        reconciliation_note = (
            f"Bottom-up TAM was capped to the cited market size. The modeled global buyer count was "
            f"reduced from {int(original_global):,} to {int(n_global):,} so bottom-up TAM "
            f"({_fmt_money(original_tam)}) does not exceed the external top-down market "
            f"({_fmt_money(top_down_tam_value)})."
        )
        trace.append(
            f"Reconciled bottom-up TAM {_fmt_money(original_tam)} down to the cited top-down market "
            f"{_fmt_money(top_down_tam_value)} (buyer count too broad)."
        )

    assumptions = {
        "monthly_price": float(monthly_price),
        "annual_price": annual_price,
        "n_global_customers": n_global,
        "n_target_customers": n_target,
        "capture_rate": 0.01,
        "sector_profile": basis_label,
        "geography_scope": brief.get("geography"),
        "formulae": {
            **baseline.get("formulae", {}),
            "top_down_tam": "externally sourced market size when available, otherwise bottom_up_tam * top_down_ratio",
        },
    }
    if reconciliation_note:
        assumptions["reconciliation_note"] = reconciliation_note
    return {
        "assumptions": assumptions,
        "bottom_up": {
            "tam": bottom_up_tam,
            "sam": bottom_up_sam,
            "som": bottom_up_som,
        },
        "top_down": top_down,
        "sources": [c["source_url"] for c in competitors if c.get("source_url")],
    }


def _fmt_money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _sector_profile(sector: str) -> dict[str, Any]:
    if "ag" in sector or "farm" in sector or "food" in sector:
        return {
            "label": "AgTech operators",
            "global_accounts": 220000.0,
            "top_down_ratio": 1.35,
            "benchmark_basis": "Modeled addressable operators across controlled-environment agriculture, greenhouse, and adjacent specialty crop workflows.",
            "benchmark_source": "Northstar internal benchmark library: controlled environment agriculture operator model.",
        }
    if "health" in sector or "med" in sector:
        return {
            "label": "Healthcare providers",
            "global_accounts": 450000.0,
            "top_down_ratio": 1.55,
            "benchmark_basis": "Modeled provider organizations and clinic groups likely to buy workflow software.",
            "benchmark_source": "Northstar internal benchmark library: healthcare provider organization model.",
        }
    if "fin" in sector or "bank" in sector:
        return {
            "label": "Financial services operators",
            "global_accounts": 180000.0,
            "top_down_ratio": 1.45,
            "benchmark_basis": "Modeled banks, lenders, advisory firms, and adjacent financial operators.",
            "benchmark_source": "Northstar internal benchmark library: financial services buyer model.",
        }
    return {
        "label": "General B2B operators",
        "global_accounts": 650000.0,
        "top_down_ratio": 1.4,
        "benchmark_basis": "Modeled B2B operating teams with recurring software budgets.",
        "benchmark_source": "Northstar internal benchmark library: general B2B software buyer model.",
    }


def _select_top_down_market_size(
    candidates: list[dict[str, Any]],
    bottom_up_tam: float,
    profile: dict[str, Any],
) -> dict[str, Any]:
    if candidates:
        scored = []
        for item in candidates:
            market_size = float(item.get("market_size_usd", 0) or 0)
            if market_size <= 0:
                continue
            ratio_gap = _ratio_gap(market_size, bottom_up_tam)
            closeness_score = 1 / (1 + ratio_gap)
            confidence_score = float(item.get("confidence_score", 0) or 0)
            final_score = round(confidence_score * 0.7 + closeness_score * 0.3, 3)
            scored.append((final_score, closeness_score, confidence_score, item))
        scored.sort(key=lambda item: (item[0], item[2], item[1]), reverse=True)
        if scored:
            final_score, closeness_score, confidence_score, chosen = scored[0]
            candidate_value = float(chosen["market_size_usd"])
            candidate_ratio_gap = _ratio_gap(candidate_value, bottom_up_tam)
            reasons = set(chosen.get("confidence_reasons", []))
            strong_scope_match = bool({"geography-match", "industry-match"} & reasons) and (
                "software-scope-match" in reasons or "preferred-domain" in reasons or "strong-title-signal" in reasons
            )
            if confidence_score >= 0.45 and candidate_ratio_gap <= MAX_TOP_DOWN_AUDIT_RATIO:
                return {
                    "tam": candidate_value,
                    "top_down_ratio": candidate_value / bottom_up_tam if bottom_up_tam else None,
                    "benchmark_basis": "Direct third-party market-size citation matched to the current concept/sector/geography query.",
                    "source": chosen.get("source_title") or chosen.get("source_url"),
                    "source_title": chosen.get("source_title"),
                    "source_url": chosen.get("source_url"),
                    "source_excerpt": chosen.get("source_snippet"),
                    "display_value": chosen.get("display_value"),
                    "source_type": "external",
                    "selection_method": "confidence-plus-closeness-ranking",
                    "candidate_count": len(candidates),
                    "confidence_score": confidence_score,
                    "selection_score": final_score,
                    "confidence_reasons": chosen.get("confidence_reasons", []),
                }
            if confidence_score >= 0.35 and candidate_ratio_gap <= 4.0 and strong_scope_match:
                return {
                    "tam": candidate_value,
                    "top_down_ratio": candidate_value / bottom_up_tam if bottom_up_tam else None,
                    "benchmark_basis": "Direct third-party market-size citation matched to the current concept/sector/geography query.",
                    "source": chosen.get("source_title") or chosen.get("source_url"),
                    "source_title": chosen.get("source_title"),
                    "source_url": chosen.get("source_url"),
                    "source_excerpt": chosen.get("source_snippet"),
                    "display_value": chosen.get("display_value"),
                    "source_type": "external",
                    "selection_method": "scope-aware-fallback-selection",
                    "candidate_count": len(candidates),
                    "confidence_score": confidence_score,
                    "selection_score": final_score,
                    "confidence_reasons": chosen.get("confidence_reasons", []),
                }
            chosen["rejected_reason"] = (
                f"candidate rejected because top-down vs bottom-up ratio gap was {candidate_ratio_gap:.2f}x "
                f"which exceeds the audit-safe threshold of {MAX_TOP_DOWN_AUDIT_RATIO:.1f}x"
            )

    top_down_ratio = float(profile["top_down_ratio"])
    top_down_tam = bottom_up_tam * top_down_ratio
    return {
        "tam": top_down_tam,
        "top_down_ratio": top_down_ratio,
        "benchmark_basis": profile["benchmark_basis"],
        "source": profile["benchmark_source"],
        "source_title": profile["benchmark_source"],
        "source_url": "",
        "source_excerpt": "",
        "display_value": "",
        "source_type": "benchmark-fallback",
        "selection_method": "internal-benchmark-fallback",
        "candidate_count": 0,
        "confidence_score": 0.0,
        "selection_score": 0.0,
        "confidence_reasons": [],
    }


def _ratio_gap(a: float, b: float) -> float:
    if a <= 0 or b <= 0:
        return 999.0
    return max(a / b, b / a)


def _market_cache_key(brief: dict[str, str]) -> str:
    geography = (brief.get("geography") or "").strip().lower()
    sector = (brief.get("sector") or "").strip().lower()
    concept = (brief.get("concept") or "").strip().lower()
    tokens = [token for token in re.findall(r"[a-z0-9]+", concept) if len(token) > 3][:8]
    return "|".join([geography, sector, "-".join(tokens)])


def _merge_market_candidates(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in (primary or []) + (secondary or []):
        if not item:
            continue
        key = (str(item.get("source_url") or ""), int(float(item.get("market_size_usd", 0) or 0)))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged
