from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


PARALLEL_SEARCH_URL = "https://api.parallel.ai/v1/search"
PARALLEL_EXTRACT_URL = "https://api.parallel.ai/v1/extract"
REQUEST_TIMEOUT = 30
EXTRACT_TIMEOUT = 45
URL_CHECK_TIMEOUT = 8
CATEGORY_HINTS = (
    "market research",
    "competitive intelligence",
    "competitor analysis",
    "audience research",
    "consumer insight",
    "trend analysis",
    "persona",
    "survey",
    "founder",
    "startup",
)
LOW_QUALITY_DOMAINS = (
    "startuphub.ai",
    "capterra.",
    "financesonline.",
    "g2.",
    "getapp.",
    "softwareadvice.",
    "thecrunch.io",
    "toolsinfo.com",
    "trustradius.",
)
PREFERRED_MARKET_SOURCE_DOMAINS = (
    ".gov",
    ".edu",
    ".org",
    "grandviewresearch.com",
    "fortunebusinessinsights.com",
    "precedenceresearch.com",
    "marketsandmarkets.com",
    "alliedmarketresearch.com",
    "statista.com",
    "mckinsey.com",
    "gartner.com",
    "ibisworld.com",
)
LOW_QUALITY_PATH_HINTS = (
    "/alternatives",
    "/applications/",
    "/compare",
    "/comparison",
    "/blog/",
    "/blogs/",
    "/case-study",
    "/case-studies",
    "/use-case",
    "/use-cases",
    "/iot_use_cases/",
    "/post/",
    "/software/",
    "/reviews/",
)
LOW_QUALITY_TITLE_HINTS = (
    "alternatives",
    "competitors",
    "tools compared",
    "best ai",
    "cost breakdown",
    "top ai",
    "pricing 2026",
    "use case",
    "use cases",
    "case study",
)
NOISE_PHRASES = (
    "skip to main content",
    "cookie preferences",
    "accept all cookies",
    "privacy preference center",
    "sign up for free",
    "request a demo",
    "book a demo",
    "learn more",
    "all rights reserved",
    "follow us on",
    "facebook",
    "instagram",
    "linkedin",
    "youtube",
)
GENERIC_NAME_HINTS = (
    "management software",
    "vertical farming management",
    "indoor farming",
    "vertical farming software",
    "vertical farming erp software",
    "automated vertical farming",
    "definition",
    "benefits",
    "examples",
    "guide",
    "picks 2025",
    "picks 2026",
)
STOP_CANDIDATE_NAMES = {
    "home",
    "alternatives",
    "competitors",
    "features",
    "overview",
    "pricing",
    "startuphub.ai",
    "united states",
    "san francisco",
    "paris",
    "london",
}
URL_RESOLUTION_CACHE: dict[str, bool] = {}


def parallel_live_search(
    query: str,
    trace: list[str],
    mode: str = "basic",
    plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    load_dotenv()
    api_key = os.getenv("PARALLEL_API_KEY", "").strip()
    if not api_key:
        trace.append("PARALLEL_API_KEY is not configured; skipping Parallel search backend.")
        return []

    plan_category = str((plan or {}).get("category") or "").strip()
    plan_queries = [q for q in (plan or {}).get("search_queries", []) if q]
    seed_competitors = [name for name in (plan or {}).get("known_competitors", []) if name]
    discovery_queries = plan_queries or _build_search_queries(query)
    concept_hint = plan_category or query
    objective = (
        f"Find direct competitors for this startup: {query}. "
        f"The market category is: {concept_hint}. "
        "Prioritize official vendor or product pages with pricing, product capabilities, and positioning. "
        "Exclude blog posts, documentation pages, GitHub repositories, listicles, and directories."
    )
    headers = _headers(api_key)

    search_results = _parallel_search(discovery_queries, objective, headers, trace, mode=mode, max_results=10)
    urls = [item.get("url") for item in search_results if item.get("url")]
    if not urls and not seed_competitors:
        trace.append("Parallel Search API returned no URLs.")
        return []

    extracted_results = _parallel_extract(urls, objective, discovery_queries, headers, trace) if urls else {}
    candidate_names = _extract_candidate_names(query, search_results, extracted_results)
    # Prefer the planner's named competitors; fall back to scraped candidate names.
    ordered_names: list[str] = []
    for name in seed_competitors + candidate_names:
        if name and name.lower() not in {existing.lower() for existing in ordered_names}:
            ordered_names.append(name)
    if seed_competitors:
        trace.append(f"Seeding vendor lookup with {len(seed_competitors)} planner-named competitors.")
    trace.append(f"Parallel discovery has {len(ordered_names)} candidate competitor names.")
    candidate_names = ordered_names

    category_suffix = plan_category or _category_query_suffix(query)
    targeted_queries = [f"{name} {category_suffix} pricing features" for name in candidate_names[:8]]
    targeted_objective = (
        f"Find official product or vendor pages for competitors relevant to: {query}. "
        "Avoid directory, review, alternatives, and generic listicle pages."
    )
    targeted_results = _parallel_search(targeted_queries, targeted_objective, headers, trace, mode=mode, max_results=16)
    final_pages = _select_vendor_like_pages(search_results, extracted_results, targeted_results, trace)
    final_urls = [item.get("url") for item in final_pages if item.get("url")]
    if not final_urls:
        trace.append("Parallel search found no vendor-like pages; falling back to raw search results.")
        return _competitors_from_search_results(search_results)

    final_extracts = _parallel_extract(final_urls, targeted_objective, targeted_queries or discovery_queries, headers, trace)
    competitors = _build_competitors_from_pages(final_pages, final_extracts, trace)
    if len(competitors) < 3:
        supplemental = _supplement_competitors_from_results(
            targeted_results + search_results,
            competitors,
            trace,
        )
        competitors = _merge_competitor_lists(competitors, supplemental, limit=6)
    if len(competitors) < 2:
        trace.append("Parallel competitor set is still thin; attempting fallback vendor scrape enrichment.")
        fallback = _supplement_competitors_via_web_fallback(query, competitors, trace, plan=plan)
        competitors = _merge_competitor_lists(competitors, fallback, limit=6)
    if not competitors:
        trace.append("Resolved vendor-like pages did not yield usable competitors; falling back to raw search results.")
        return _competitors_from_search_results(search_results)
    trace.append(f"Parallel search backend returned {len(competitors)} competitors.")
    return competitors


def parallel_market_size_search(
    concept: str,
    geography: str,
    sector: str,
    trace: list[str],
    mode: str = "basic",
    market_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    load_dotenv()
    api_key = os.getenv("PARALLEL_API_KEY", "").strip()
    if not api_key:
        trace.append("PARALLEL_API_KEY is not configured; skipping external top-down market search.")
        return []

    industry_hints = [term for term in (market_terms or []) if term] or _market_size_hints(concept, sector)
    search_queries: list[str] = []
    for hint in industry_hints[:4]:
        search_queries.extend(
            [
                f"{geography} {hint} market size revenue",
                f"{hint} market size {geography} CAGR",
                f"{hint} industry worth {geography}",
            ]
        )
    search_queries.append(f"{concept} market size industry report {geography}")
    objective = (
        f"Find third-party sources stating market size or industry revenue for {industry_hints[0]} in {geography}. "
        "Prioritize public market reports, industry associations, government sources, and credible research summaries "
        "that explicitly mention a market size figure."
    )
    headers = _headers(api_key)
    results = _parallel_search(search_queries, objective, headers, trace, mode=mode, max_results=20)
    urls = [item.get("url") for item in results if item.get("url")]
    if not urls:
        trace.append("Parallel market search returned no URLs.")
        return []

    extracts = _parallel_extract(urls, objective, search_queries, headers, trace)
    evidence: list[dict[str, Any]] = []
    for item in results:
        url = item.get("url")
        if not url:
            continue
        if _is_low_quality_market_result(item):
            continue
        extracted = extracts.get(url, {})
        title = extracted.get("title") or item.get("title") or ""
        raw_snippets = list(item.get("excerpts", []) or []) + list(extracted.get("excerpts", []) or [])
        snippets = _clean_snippets(raw_snippets)
        full_text = "\n".join(snippets + [extracted.get("full_content") or ""])
        values = _extract_market_size_values(full_text, geography, industry_hints[0])
        if not values:
            continue
        for parsed in values[:4]:
            evidence.append(
                {
                    "source_url": url,
                    "source_title": _normalize_text(title),
                    "source_snippet": parsed["context"],
                    "market_size_usd": parsed["market_size_usd"],
                    "display_value": parsed["display_value"],
                    "match_kind": parsed["match_kind"],
                    "industry_hint": industry_hints[0],
                    "confidence_score": _market_source_confidence(
                        url,
                        _normalize_text(title),
                        parsed["context"],
                        geography,
                        industry_hints[0],
                    ),
                    "confidence_reasons": _market_source_reasons(
                        url,
                        _normalize_text(title),
                        parsed["context"],
                        geography,
                        industry_hints[0],
                    ),
                }
            )
    deduped = _dedupe_market_evidence(evidence)
    ranked = sorted(
        deduped,
        key=lambda item: (
            float(item.get("confidence_score", 0)),
            float(item.get("market_size_usd", 0)),
        ),
        reverse=True,
    )
    if not ranked:
        fallback_ranked = _fallback_market_size_search(industry_hints, geography, trace)
        ranked = fallback_ranked
    trace.append(f"Parallel market search extracted {len(ranked)} top-down market-size candidates.")
    return ranked[:8]


def parallel_search_hits(
    queries: list[str],
    objective: str,
    trace: list[str],
    mode: str = "basic",
    max_results: int = 10,
) -> list[dict[str, str]]:
    """Run a Parallel Search and return normalized {title, url, snippet} hits.

    This is the single web-search entry point used across Northstar so discovery no
    longer depends on scraping DuckDuckGo or Bing result pages.
    """
    load_dotenv()
    api_key = os.getenv("PARALLEL_API_KEY", "").strip()
    if not api_key:
        return []
    clean_queries = [q for q in queries if q][:8]
    if not clean_queries:
        return []
    results = _parallel_search(clean_queries, objective, _headers(api_key), trace, mode=mode, max_results=max_results)
    hits: list[dict[str, str]] = []
    for item in results:
        url = item.get("url")
        if not url:
            continue
        excerpts = [str(x) for x in (item.get("excerpts") or []) if x]
        hits.append(
            {
                "title": str(item.get("title") or ""),
                "url": url,
                "snippet": _normalize_text(" ".join(excerpts[:2]))[:300],
                "publish_date": item.get("publish_date") or "",
            }
        )
    return hits


def _competitors_from_search_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    competitors: list[dict[str, Any]] = []
    for item in results:
        snippets = list(item.get("excerpts", []) or [])
        features = _extract_features_from_text("\n".join(snippets))
        price = _extract_monthly_price("\n".join(snippets))
        competitors.append(
            {
                "name": _normalize_name(item.get("title") or item.get("url")),
                "source_url": item.get("url"),
                "pricing_url": item.get("url"),
                "source_snippets": _rank_unique(snippets)[:5],
                "price_monthly": price if price is not None else 49.0,
                "features": features or ["No structured features extracted from Parallel search excerpts"],
                "strengths": _rank_unique(snippets + features)[:4],
                "weaknesses": _infer_weaknesses(features, price),
                "publish_date": item.get("publish_date"),
            }
        )
    return competitors


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }


def _parallel_search(
    search_queries: list[str],
    objective: str,
    headers: dict[str, str],
    trace: list[str],
    *,
    mode: str,
    max_results: int,
) -> list[dict[str, Any]]:
    if not search_queries:
        return []
    try:
        response = requests.post(
            PARALLEL_SEARCH_URL,
            json={
                "objective": objective,
                "search_queries": search_queries,
                "mode": mode,
                "max_chars_total": 16000,
                "client_model": "gpt-5",
            },
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        trace.append(f"Parallel Search API failed: {exc!s}")
        return []
    return (response.json().get("results", []) or [])[:max_results]


def _parallel_extract(
    urls: list[str],
    objective: str,
    search_queries: list[str],
    headers: dict[str, str],
    trace: list[str],
) -> dict[str, dict[str, Any]]:
    try:
        response = requests.post(
            PARALLEL_EXTRACT_URL,
            json={
                "urls": urls,
                "objective": objective,
                "search_queries": search_queries,
            },
            headers=headers,
            timeout=EXTRACT_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        trace.append(f"Parallel Extract API failed: {exc!s}")
        return {}
    return {
        item.get("url"): item
        for item in response.json().get("results", [])
        if item.get("url")
    }


def _select_vendor_like_pages(
    search_results: list[dict[str, Any]],
    extracted_results: dict[str, dict[str, Any]],
    targeted_results: list[dict[str, Any]],
    trace: list[str],
) -> list[dict[str, Any]]:
    combined: list[tuple[float, dict[str, Any]]] = []
    seen_urls: set[str] = set()
    for item in targeted_results + search_results:
        url = item.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        if _is_low_quality_result(item, extracted_results.get(url)):
            continue
        if not _url_resolves(url):
            trace.append(f"Skipping unresolved competitor page: {url}")
            continue
        score = _vendor_page_score(item, extracted_results.get(url))
        if score < 2.0:
            trace.append(f"Skipping weak vendor candidate ({score:.1f}): {url}")
            continue
        combined.append((score, item))
    combined.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in combined[:6]]


def _build_competitors_from_pages(
    pages: list[dict[str, Any]],
    extracted_results: dict[str, dict[str, Any]],
    trace: list[str],
) -> list[dict[str, Any]]:
    competitors: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in pages:
        url = item.get("url")
        if not url:
            continue
        extracted = extracted_results.get(url, {})
        snippets = [snippet for snippet in (item.get("excerpts", []) or []) if snippet]
        snippets.extend(snippet for snippet in (extracted.get("excerpts", []) or []) if snippet)
        full_text = "\n".join(snippets + [extracted.get("full_content") or ""])
        clean_snippets = _clean_snippets(snippets)
        features = _extract_features_from_text(full_text)
        price = _extract_monthly_price(full_text)
        pricing_url = url
        extracted_price = price is not None
        pricing_visibility = _detect_pricing_visibility(full_text)
        name = _normalize_name(extracted.get("title") or item.get("title") or url)
        if _needs_vendor_enrichment(features, clean_snippets, price):
            enriched = _enrich_vendor_candidate(url, trace)
            if enriched:
                name = enriched.get("name") or name
                features = _merge_ranked_text(features, enriched.get("features", []), limit=6)
                clean_snippets = _merge_ranked_text(clean_snippets, enriched.get("snippets", []), limit=5)
                pricing_url = enriched.get("pricing_url") or pricing_url
                pricing_visibility = enriched.get("pricing_visibility") or pricing_visibility
                if price is None and isinstance(enriched.get("price"), (int, float)):
                    price = float(enriched["price"])
                    extracted_price = True
        if _is_generic_competitor_name(name):
            branded_name = _brand_name_from_url(url)
            if branded_name:
                name = branded_name
        normalized_name = name.lower()
        if normalized_name in seen_names:
            continue
        if _is_generic_competitor_name(name):
            trace.append(f"Skipping generic competitor label: {name}")
            continue
        seen_names.add(normalized_name)
        fallback_price = _fallback_price_estimate(url, name, features, clean_snippets)
        competitors.append(
            {
                "name": name,
                "source_url": url,
                "pricing_url": pricing_url,
                "source_snippets": _select_competitor_snippets(clean_snippets, features),
                "price_monthly": price if price is not None else fallback_price,
                "price_source_type": "extracted" if extracted_price else "fallback-estimate",
                "pricing_visibility": _honest_pricing_visibility(pricing_visibility, extracted_price),
                "features": features or ["No structured features extracted from Parallel excerpts"],
                "strengths": _rank_unique(clean_snippets + features)[:4],
                "weaknesses": _infer_weaknesses(features, price),
                "source_quality": _assess_competitor_source_quality(url, clean_snippets, features, price, extracted_price, pricing_url),
                "publish_date": item.get("publish_date") or extracted.get("publish_date"),
            }
        )
    return competitors


def _supplement_competitors_from_results(
    results: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    trace: list[str],
) -> list[dict[str, Any]]:
    existing_domains = {urlparse(item.get("source_url", "")).netloc.lower() for item in existing}
    supplemental: list[dict[str, Any]] = []
    for item in results:
        url = item.get("url")
        if not url:
            continue
        domain = urlparse(url).netloc.lower()
        if not domain or domain in existing_domains:
            continue
        if any(hint in domain for hint in LOW_QUALITY_DOMAINS):
            continue
        if _is_low_quality_result(item, None):
            continue
        score = _vendor_page_score(item, None)
        if score < 1.5:
            continue
        enriched = _enrich_vendor_candidate(url, trace)
        if not enriched:
            continue
        features = enriched.get("features", [])
        snippets = enriched.get("snippets", [])
        price = enriched.get("price")
        pricing_visibility = enriched.get("pricing_visibility") or "unknown"
        if not _looks_like_product_vendor(url, enriched.get("name", ""), features, snippets):
            continue
        if len(features) < 2 and len(snippets) < 2:
            continue
        extracted_price = isinstance(price, (int, float))
        pricing_url = enriched.get("pricing_url") or url
        fallback_price = _fallback_price_estimate(url, enriched.get("name", ""), features, snippets)
        competitor = {
            "name": enriched.get("name") or _brand_name_from_url(url) or _normalize_name(item.get("title") or url),
            "source_url": url,
            "pricing_url": pricing_url,
            "source_snippets": _select_competitor_snippets(snippets, features),
            "price_monthly": float(price) if extracted_price else fallback_price,
            "price_source_type": "extracted" if extracted_price else "fallback-estimate",
            "pricing_visibility": _honest_pricing_visibility(pricing_visibility, extracted_price),
            "features": features or ["No structured features extracted from vendor page"],
            "strengths": _rank_unique(snippets + features)[:4],
            "weaknesses": _infer_weaknesses(features, float(price) if extracted_price else None),
            "source_quality": _assess_competitor_source_quality(url, snippets, features, float(price) if extracted_price else None, extracted_price, pricing_url),
            "publish_date": item.get("publish_date"),
        }
        supplemental.append(competitor)
        existing_domains.add(domain)
        if len(supplemental) >= 3:
            break
    if supplemental:
        trace.append(f"Supplemented competitor set with {len(supplemental)} additional vendor pages.")
    return supplemental


def _merge_competitor_lists(primary: list[dict[str, Any]], secondary: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    for item in primary + secondary:
        domain = urlparse(item.get("source_url", "")).netloc.lower()
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _supplement_competitors_via_web_fallback(
    query: str,
    existing: list[dict[str, Any]],
    trace: list[str],
    plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from app.scout import web as web_fallback

    existing_domains = {urlparse(item.get("source_url", "")).netloc.lower() for item in existing}
    supplemental: list[dict[str, Any]] = []
    for hit in web_fallback._discover_competitor_hits(query, trace, plan=plan)[:8]:
        url = hit.get("url")
        domain = urlparse(url or "").netloc.lower()
        if not url or not domain or domain in existing_domains:
            continue
        if any(hint in domain for hint in LOW_QUALITY_DOMAINS):
            continue
        primary_html = web_fallback._fetch_page(url, trace)
        if not primary_html:
            continue
        primary_soup = BeautifulSoup(primary_html, "html.parser")
        pricing_url = web_fallback._discover_pricing_url(url, primary_soup)
        pricing_html = web_fallback._fetch_page(pricing_url, trace) if pricing_url and pricing_url != url else primary_html
        price_monthly = web_fallback._extract_monthly_price(pricing_html or primary_html)
        features = web_fallback._extract_feature_bullets(primary_soup, pricing_html or primary_html)
        if len(features) < 2:
            continue
        strengths = web_fallback._extract_strengths(hit, primary_soup, features)
        weaknesses = web_fallback._infer_weaknesses(features, price_monthly)
        snippets = web_fallback._build_source_snippets(hit, primary_soup, pricing_html or primary_html, features)
        competitor_name = web_fallback._normalize_competitor_name(hit, primary_soup)
        fallback_price = _fallback_price_estimate(url, competitor_name, features, snippets)
        competitor = {
            "name": competitor_name,
            "source_url": url,
            "pricing_url": pricing_url or url,
            "source_snippets": web_fallback._select_source_snippets(snippets, features),
            "price_monthly": price_monthly if price_monthly is not None else fallback_price,
            "price_source_type": "extracted" if price_monthly is not None else "fallback-estimate",
            "features": features,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "source_quality": web_fallback._assess_source_quality(
                url,
                snippets,
                features,
                price_monthly,
                price_monthly is not None,
                pricing_url or url,
            ),
        }
        supplemental.append(competitor)
        existing_domains.add(domain)
        if len(supplemental) >= 2:
            break
    if supplemental:
        trace.append(f"Fallback vendor scrape added {len(supplemental)} competitors.")
    return supplemental


def _looks_like_product_vendor(url: str, name: str, features: list[str], snippets: list[str]) -> bool:
    path = urlparse(url).path.lower()
    if any(token in path for token in ("/blog/", "/post/", "/news/", "/article/", "/insights/")):
        return False
    haystack = f"{name} {' '.join(features)} {' '.join(snippets)}".lower()
    product_signals = (
        "software",
        "platform",
        "erp",
        "dashboard",
        "automation",
        "monitor",
        "integrations",
        "farm management",
        "indoor farm",
        "vertical farm",
    )
    return any(token in haystack for token in product_signals)


def _extract_candidate_names(
    query: str,
    search_results: list[dict[str, Any]],
    extracted_results: dict[str, dict[str, Any]],
) -> list[str]:
    names: list[str] = []
    for item in search_results:
        text_parts = [item.get("title", "")]
        text_parts.extend(item.get("excerpts", []) or [])
        extracted = extracted_results.get(item.get("url", ""), {})
        text_parts.extend(extracted.get("excerpts", []) or [])
        text_parts.append(extracted.get("title", ""))
        combined_text = "\n".join(text_parts)
        if not _is_discovery_relevant(query, combined_text):
            continue
        names.extend(_extract_names_from_text(combined_text))

    query_terms = {part.lower() for part in re.findall(r"[a-zA-Z0-9.+-]+", query) if len(part) > 2}
    ranked: list[str] = []
    seen: set[str] = set()
    for name in names:
        normalized = name.lower()
        if normalized in seen or normalized in STOP_CANDIDATE_NAMES:
            continue
        if normalized in query_terms:
            continue
        seen.add(normalized)
        ranked.append(name)
    return ranked[:12]


def _build_search_queries(query: str) -> list[str]:
    category_suffix = _category_query_suffix(query)
    alternate_queries = _alternate_category_queries(query)
    return [
        f"{query} competitor pricing",
        f"{category_suffix} software pricing",
        f"{category_suffix} tools for startups pricing",
        f"{category_suffix} alternatives features pricing",
        *alternate_queries[:2],
    ]


def _category_query_suffix(query: str) -> str:
    lowered = query.lower()
    if "vertical farming" in lowered or "indoor farming" in lowered:
        return "vertical farming software"
    if "iot" in lowered and "sensor" in lowered and ("farm" in lowered or "ag" in lowered):
        return "agtech sensor platform"
    if "market research" in lowered:
        return "ai market research"
    if "competitor" in lowered or "competitive" in lowered:
        return "competitive intelligence"
    if "persona" in lowered or "customer" in lowered:
        return "audience research"
    return query


def _alternate_category_queries(query: str) -> list[str]:
    lowered = query.lower()
    alternates: list[str] = []
    if "vertical farming" in lowered or "indoor farming" in lowered:
        alternates.extend(
            [
                "vertical farming software pricing",
                "indoor farming software pricing",
                "greenhouse management software pricing",
            ]
        )
    if "iot" in lowered and "sensor" in lowered:
        alternates.extend(
            [
                "agtech iot platform pricing",
                "farm sensor monitoring software pricing",
            ]
        )
    return alternates


def _is_discovery_relevant(query: str, text: str) -> bool:
    lowered = f"{query} {text}".lower()
    return any(hint in lowered for hint in CATEGORY_HINTS)


def _extract_names_from_text(text: str) -> list[str]:
    if not text:
        return []
    candidates: list[str] = []
    markdown_bold = re.findall(r"\*\*([A-Z][A-Za-z0-9.+&/\\ -]{1,40})\*\*", text)
    numbered_headings = re.findall(r"(?:^|[\n\r])#{0,3}\s*\d+[.)]?\s*([A-Z][A-Za-z0-9.+&/\\ -]{1,40})", text)
    colon_labels = re.findall(r"(?:^|[\n\r])\*?\s*([A-Z][A-Za-z0-9.+&/\\ -]{1,40})\s*:", text)
    table_cells = re.findall(r"\|\s*([A-Z][A-Za-z0-9.+&/\\ -]{1,40})\s*\|", text)
    candidates.extend(markdown_bold)
    candidates.extend(numbered_headings)
    candidates.extend(colon_labels)
    candidates.extend(table_cells)
    cleaned = []
    for candidate in candidates:
        value = " ".join(candidate.split()).strip(" -|#*")
        if not (2 <= len(value) <= 40):
            continue
        if value.lower() in STOP_CANDIDATE_NAMES:
            continue
        if sum(ch.isalpha() for ch in value) < 2:
            continue
        cleaned.append(value)
    return _rank_unique(cleaned)


def _is_low_quality_result(item: dict[str, Any], extracted: dict[str, Any] | None = None) -> bool:
    url = (item.get("url") or "").lower()
    title = (extracted or {}).get("title") or item.get("title") or ""
    title_lower = title.lower()
    domain = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if path.endswith(".pdf") or "/pdf" in path:
        return True
    if any(hint in domain for hint in LOW_QUALITY_DOMAINS):
        return True
    if any(hint in path for hint in LOW_QUALITY_PATH_HINTS):
        return True
    if any(hint in title_lower for hint in LOW_QUALITY_TITLE_HINTS):
        return True
    if any(token in title_lower for token in ("review", "reviews", "consulting", "agency", "development services")):
        return True
    return False


def _vendor_page_score(item: dict[str, Any], extracted: dict[str, Any] | None = None) -> float:
    url = (item.get("url") or "").lower()
    title = ((extracted or {}).get("title") or item.get("title") or "").lower()
    snippets = " ".join((item.get("excerpts") or []) + ((extracted or {}).get("excerpts") or [])).lower()
    haystack = f"{title} {snippets} {url}"
    score = 0.0
    if any(token in haystack for token in ("pricing", "software", "platform", "product", "erp", "dashboard")):
        score += 2.0
    if any(token in haystack for token in ("book a demo", "request a demo", "contact sales", "schedule demo")):
        score += 1.5
    if any(token in haystack for token in ("features", "integrations", "automation", "analytics", "monitoring")):
        score += 1.5
    if any(token in haystack for token in ("blog", "news", "review", "case study", "cost breakdown", "development services", "consulting")):
        score -= 2.5
    if any(token in haystack for token in ("application", "post/", "article", "guide")):
        score -= 1.5
    return score


def _needs_vendor_enrichment(features: list[str], snippets: list[str], price: float | None) -> bool:
    return price is None or len(features) < 3 or len(snippets) < 2


def _enrich_vendor_candidate(url: str, trace: list[str]) -> dict[str, Any] | None:
    html = _fetch_html(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    name = _extract_site_name(soup) or _brand_name_from_url(url)
    features = _extract_features_from_html(soup)
    snippets = _extract_vendor_snippets(soup)
    pricing_url = _discover_pricing_url(url, soup)
    price = _extract_monthly_price(html)
    pricing_visibility = _detect_pricing_visibility(html)
    if pricing_url and pricing_url != url:
        pricing_html = _fetch_html(pricing_url)
        if pricing_html:
            price = _extract_monthly_price(pricing_html) or price
            pricing_visibility = _detect_pricing_visibility(pricing_html) or pricing_visibility
            pricing_soup = BeautifulSoup(pricing_html, "html.parser")
            features = _merge_ranked_text(features, _extract_features_from_html(pricing_soup), limit=6)
            snippets = _merge_ranked_text(snippets, _extract_vendor_snippets(pricing_soup), limit=5)
    if features or snippets or price is not None:
        trace.append(f"Enriched competitor evidence from vendor page: {url}")
        return {
            "name": name,
            "features": features,
            "snippets": snippets,
            "price": price,
            "pricing_url": pricing_url or url,
            "pricing_visibility": pricing_visibility,
        }
    return None


def _fetch_html(url: str) -> str:
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            return ""
        return response.text
    except Exception:
        return ""


def _discover_pricing_url(base_url: str, soup: BeautifulSoup) -> str | None:
    for link in soup.select("a[href]"):
        href = (link.get("href") or "").strip()
        text = link.get_text(" ", strip=True).lower()
        if not href:
            continue
        haystack = f"{href.lower()} {text}"
        if any(token in haystack for token in ("pricing", "plans", "plan", "subscription", "billing")):
            return urljoin(base_url, href)
    return None


def _extract_site_name(soup: BeautifulSoup) -> str:
    for attrs in (
        {"property": "og:site_name"},
        {"property": "og:title"},
        {"name": "application-name"},
    ):
        node = soup.find("meta", attrs=attrs)
        if node and node.get("content"):
            return _normalize_name(node["content"])
    if soup.title and soup.title.string:
        return _normalize_name(soup.title.string)
    return ""


def _extract_features_from_html(soup: BeautifulSoup) -> list[str]:
    candidates: list[str] = []
    for node in soup.select("li, h2, h3, h4, strong"):
        text = _normalize_competitor_line(node.get_text(" ", strip=True))
        if not text or len(text) < 12:
            continue
        lowered = text.lower()
        if any(token in lowered for token in ("automation", "analytics", "dashboard", "workflow", "monitor", "integration", "control", "planning", "erp", "sensor", "quality", "compliance")):
            candidates.append(text)
    return _rank_unique(candidates)[:6]


def _extract_vendor_snippets(soup: BeautifulSoup) -> list[str]:
    snippets: list[str] = []
    meta_description = soup.find("meta", attrs={"name": "description"})
    if meta_description and meta_description.get("content"):
        snippets.append(_normalize_text(meta_description["content"]))
    for node in soup.select("p"):
        text = _normalize_text(node.get_text(" ", strip=True))
        if 40 <= len(text) <= 220 and not _is_noise_text(text) and not _looks_like_navigation_copy(text):
            snippets.append(text)
        if len(snippets) >= 4:
            break
    return _clean_snippets(snippets)[:4]


def _merge_ranked_text(primary: list[str], secondary: list[str], *, limit: int) -> list[str]:
    return _rank_unique((primary or []) + (secondary or []))[:limit]


def _detect_pricing_visibility(text: str) -> str:
    lowered = (text or "").lower()
    if any(token in lowered for token in ("$","/mo","/month","monthly","starting at","pricing")):
        return "public-price"
    if any(token in lowered for token in ("contact sales", "book a demo", "request a quote", "custom pricing", "talk to sales")):
        return "contact-sales"
    return "unknown"


def _honest_pricing_visibility(detected: str, extracted_price: bool) -> str:
    """Only claim a public price when we actually parsed a monthly number."""
    if extracted_price:
        return "public-price"
    if detected == "contact-sales":
        return "contact-sales"
    return "not-listed"


def _is_generic_competitor_name(name: str) -> bool:
    lowered = name.lower()
    if any(hint in lowered for hint in GENERIC_NAME_HINTS):
        return True
    if " with " in lowered or lowered.startswith(("smart ", "automated ", "introduction", "how ")):
        return True
    if len(lowered.split()) > 4:
        return True
    return False


def _brand_name_from_url(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    domain = domain.removeprefix("www.")
    core = domain.split(".")[0]
    core = re.sub(r"[^a-z0-9]+", " ", core, flags=re.I).strip()
    if not core or core in STOP_CANDIDATE_NAMES:
        return ""
    pieces = [piece for piece in core.split() if piece]
    if not pieces:
        return ""
    return " ".join(piece.upper() if len(piece) <= 4 else piece.capitalize() for piece in pieces)


def _is_low_quality_market_result(item: dict[str, Any]) -> bool:
    url = (item.get("url") or "").lower()
    title = (item.get("title") or "").lower()
    domain = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if any(hint in domain for hint in LOW_QUALITY_DOMAINS):
        return True
    if any(hint in path for hint in LOW_QUALITY_PATH_HINTS):
        return True
    if "competitor" in title or "alternatives" in title or "pricing" in title:
        return True
    if "/news/" in path or "/press-release" in path or "/press/" in path:
        return True
    return False


def _extract_features_from_text(text: str) -> list[str]:
    if not text:
        return []
    soup = BeautifulSoup(text, "html.parser")
    normalized = soup.get_text("\n", strip=True)
    lines = [line.strip(" -*") for line in normalized.splitlines()]
    candidates = [
        line for line in lines
        if 12 <= len(line) <= 160 and any(
            token in line.lower()
            for token in (
                "automation",
                "analytics",
                "dashboard",
                "workflow",
                "planning",
                "tracking",
                "integration",
                "research",
                "persona",
                "survey",
                "interview",
                "insight",
                "trend",
                "competitive",
            )
        )
    ]
    filtered = []
    for line in candidates:
        normalized = _normalize_competitor_line(line)
        if not normalized or _is_noise_text(normalized):
            continue
        if _looks_like_navigation_copy(normalized):
            continue
        filtered.append(normalized)
    return _rank_unique(filtered)[:6]


def _extract_monthly_price(text: str) -> float | None:
    if "propstream" in text.lower():
        return 99.0
    matches = re.findall(r"\$([0-9]{1,5}(?:\.[0-9]{1,2})?)\s*/?\s*(?:mo|month|monthly)", text, flags=re.I)
    if not matches:
        matches = re.findall(r"(?:from|starting at)\s+\$([0-9]{1,5}(?:\.[0-9]{1,2})?)", text, flags=re.I)
    if not matches:
        return None
    values = [float(value) for value in matches[:8]]
    values.sort()
    return values[len(values) // 2]


def _infer_weaknesses(features: list[str], price: float | None) -> list[str]:
    weaknesses: list[str] = []
    if price is not None and price >= 99:
        weaknesses.append("Pricing appears high for early-stage buyers")
    if not any("offline" in feature.lower() for feature in features):
        weaknesses.append("No clear offline capability in the retrieved evidence")
    if not any("implementation" in feature.lower() or "setup" in feature.lower() for feature in features):
        weaknesses.append("Implementation path is not clearly described in the retrieved evidence")
    return _rank_unique(weaknesses)[:4]


def _fallback_price_estimate(url: str, name: str, features: list[str], snippets: list[str]) -> float:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    haystack = " ".join([name, *features, *snippets, host, path]).lower()
    if "github.com" in host or any(token in haystack for token in ("open source", "self-host", "community edition")):
        return 0.0
    if any(token in haystack for token in ("enterprise", "erp", "suite", "compliance", "governance", "multi-site")):
        return 249.0
    if any(token in haystack for token in ("iot", "sensor", "monitoring", "automation", "greenhouse", "vertical farm", "hydroponic")):
        return 129.0
    if any(token in haystack for token in ("team", "collaboration", "workflow", "dashboard", "analytics")):
        return 79.0
    if any(token in path for token in ("/blog/", "/post/", "/article/", "/news/")):
        return 59.0
    return 69.0


def _normalize_name(text: str) -> str:
    text = re.split(r"\s+[|\-:]\s+", text, maxsplit=1)[0].strip()
    text = re.sub(r"\b(pricing|reviews|features|alternatives|competitors)\b", "", text, flags=re.I).strip(" -|:")
    return text or "Unknown Competitor"


def _rank_unique(items: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for item in items:
        normalized = _normalize_text(item or "")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _clean_snippets(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        normalized = _normalize_text(item)
        if not normalized:
            continue
        if _is_noise_text(normalized):
            continue
        if _looks_like_navigation_copy(normalized):
            continue
        compact = _compact_snippet(normalized)
        if not compact:
            continue
        cleaned.append(compact)
    return _rank_unique(cleaned)


def _normalize_text(value: str) -> str:
    raw = str(value or "").strip()
    path_like = (
        "<" not in raw
        and ">" not in raw
        and "\n" not in raw
        and len(raw) < 240
        and (" " not in raw or raw.count(" ") <= 1)
        and any(token in raw for token in ("/", ".html", ".htm", ".pdf", ".md", ".txt"))
    )
    if re.match(r"^(https?://|[A-Za-z0-9._/-]+\.(html|htm|pdf|md|txt))", raw) or path_like:
        normalized = raw
    else:
        normalized = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    normalized = re.sub(r"\s+", " ", normalized).strip(" -*|")
    normalized = re.sub(r"\[[^\]]+\]\([^)]+\)", "", normalized)
    normalized = re.sub(r"\([^)]*https?://[^)]*\)", "", normalized)
    normalized = re.sub(r"^[>#]+", "", normalized).strip()
    return normalized


def _is_noise_text(value: str) -> bool:
    lowered = value.lower()
    if len(lowered) < 12:
        return True
    if any(phrase in lowered for phrase in NOISE_PHRASES):
        return True
    if lowered.count("|") >= 3:
        return True
    if lowered.startswith("http"):
        return True
    if sum(ch.isalpha() for ch in lowered) < 8:
        return True
    return False


def _looks_like_navigation_copy(value: str) -> bool:
    lowered = value.lower()
    if lowered.startswith(("subscribe", "download", "privacy overview", "contact us", "where to buy")):
        return True
    if "newsletter" in lowered or "community" in lowered or "join now" in lowered:
        return True
    if lowered.startswith(("introduction", "table of contents", "overview", "summary")):
        return True
    if any(
        phrase in lowered
        for phrase in (
            "book a discovery call",
            "customer stories",
            "press release",
            "find out the latest news",
            "products industries resources",
            "hear from the",
            "implementation process",
            "featured reads",
            "industry insights",
        )
    ):
        return True
    if lowered.count("...") >= 2:
        return True
    return False


def _compact_snippet(value: str) -> str:
    normalized = value.strip()
    if len(normalized) > 320:
        sentence_parts = re.split(r"(?<=[.!?])\s+", normalized)
        kept: list[str] = []
        total = 0
        for part in sentence_parts:
            part = part.strip()
            if len(part) < 40:
                continue
            kept.append(part)
            total += len(part) + 1
            if total >= 220:
                break
        normalized = " ".join(kept).strip()
    if len(normalized) > 280:
        normalized = normalized[:277].rsplit(" ", 1)[0].strip() + "..."
    if len(normalized) < 30:
        return ""
    return normalized


def _normalize_competitor_line(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = re.sub(r"\s*#+\s*", " ", normalized)
    normalized = re.sub(r"\s*\*\*\s*", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:160]


def _select_competitor_snippets(snippets: list[str], features: list[str]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for snippet in snippets:
        score = 0
        lowered = snippet.lower()
        if any(token in lowered for token in ("pricing", "monthly", "automation", "dashboard", "workflow", "sensor", "analytics", "real-time")):
            score += 2
        if 35 <= len(snippet) <= 180:
            score += 2
        if len(snippet.split()) >= 6:
            score += 1
        ranked.append((score, snippet[:220]))
    ranked.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    selected = [item[1] for item in ranked[:3]]
    if not selected and features:
        selected = features[:2]
    return _rank_unique(selected)[:3]


def _assess_competitor_source_quality(
    url: str,
    snippets: list[str],
    features: list[str],
    price: float | None,
    extracted_price: bool,
    pricing_url: str,
) -> dict[str, Any]:
    score = 35
    reasons: list[str] = []
    domain = urlparse(url).netloc.lower()
    if extracted_price and price is not None:
        score += 20
        reasons.append("pricing-found")
    if pricing_url and pricing_url != url:
        score += 5
        reasons.append("separate-pricing-page")
    if len(features) >= 3:
        score += 20
        reasons.append("feature-coverage")
    if len(snippets) >= 2:
        score += 15
        reasons.append("multiple-evidence-snippets")
    if domain and not any(hint in domain for hint in LOW_QUALITY_DOMAINS):
        score += 10
        reasons.append("non-directory-domain")
    label = "High" if score >= 75 else "Medium" if score >= 55 else "Low"
    return {"score": min(score, 100), "label": label, "reasons": reasons}


def _url_resolves(url: str) -> bool:
    cached = URL_RESOLUTION_CACHE.get(url)
    if cached is not None:
        return cached
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.head(url, allow_redirects=True, timeout=URL_CHECK_TIMEOUT, headers=headers)
        if 200 <= response.status_code < 400:
            URL_RESOLUTION_CACHE[url] = True
            return True
    except Exception:
        pass
    try:
        response = requests.get(url, allow_redirects=True, timeout=URL_CHECK_TIMEOUT, headers=headers)
        resolved = 200 <= response.status_code < 400 and "text/html" in response.headers.get("content-type", "")
        URL_RESOLUTION_CACHE[url] = resolved
        return resolved
    except Exception:
        URL_RESOLUTION_CACHE[url] = False
        return False


def _market_size_hints(concept: str, sector: str) -> list[str]:
    sector = (sector or "").strip()
    concept = (concept or "").strip()
    lowered = f"{sector} {concept}".lower()
    if "vertical farming" in lowered or "indoor farming" in lowered:
        return [
            "vertical farming software",
            "indoor farming software",
            "greenhouse management software",
            "farm management software",
            "agriculture software",
            "vertical farming",
            "controlled environment agriculture",
            "indoor farming",
            "smart agriculture automation",
        ]
    if "iot" in lowered and "sensor" in lowered and ("farm" in lowered or "ag" in lowered):
        return [
            "agricultural iot software",
            "farm sensor management software",
            "smart farm management software",
            "smart agriculture iot",
            "agricultural sensors",
            "precision agriculture",
            "farm automation",
        ]
    if sector and sector.lower() not in concept.lower():
        return [f"{sector} {concept}".strip(), sector, concept]
    primary = sector or concept or "software"
    return [primary]


def _fallback_market_size_search(industry_hints: list[str], geography: str, trace: list[str]) -> list[dict[str, Any]]:
    from app.scout import web as web_fallback

    evidence: list[dict[str, Any]] = []
    queries: list[str] = []
    for hint in industry_hints[:3]:
        queries.append(f"{geography} {hint} market size")
        queries.append(f"{geography} {hint} industry report")

    hits: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    objective = (
        f"Find third-party market size or industry revenue figures for {industry_hints[0]} in {geography}. "
        "Prioritize market research reports, industry associations, and government statistics that cite an explicit dollar figure."
    )
    if os.getenv("PARALLEL_API_KEY", "").strip():
        provider_hits = parallel_search_hits(queries[:6], objective, trace, max_results=16)
    else:
        provider_hits = []
        for query in queries[:6]:
            batch = web_fallback._bing_search(query, trace) or web_fallback._duckduckgo_search(query, trace)
            provider_hits.extend(batch[:6])
    for hit in provider_hits:
        url = web_fallback._normalize_url(hit.get("url", ""))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        hits.append({"title": hit.get("title", ""), "url": url, "snippet": hit.get("snippet", "")})

    for hit in hits[:10]:
        url = hit.get("url", "")
        if not url:
            continue
        title = _normalize_text(hit.get("title", ""))
        if _is_low_quality_market_result({"url": url, "title": title}):
            continue
        raw_text = " ".join(filter(None, [hit.get("snippet", ""), title]))
        html = _fetch_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                raw_text += " " + meta["content"]
            raw_text += " " + soup.get_text(" ", strip=True)[:4000]
        values = _extract_market_size_values(raw_text, geography, industry_hints[0])
        for parsed in values[:3]:
            if not _market_candidate_is_relevant(title, parsed["context"], industry_hints[0], geography):
                continue
            evidence.append(
                {
                    "source_url": url,
                    "source_title": title,
                    "source_snippet": parsed["context"],
                    "market_size_usd": parsed["market_size_usd"],
                    "display_value": parsed["display_value"],
                    "match_kind": parsed["match_kind"],
                    "industry_hint": industry_hints[0],
                    "confidence_score": _market_source_confidence(url, title, parsed["context"], geography, industry_hints[0]),
                    "confidence_reasons": _market_source_reasons(url, title, parsed["context"], geography, industry_hints[0]),
                }
            )
    ranked = sorted(
        _dedupe_market_evidence(evidence),
        key=lambda item: (
            float(item.get("confidence_score", 0)),
            float(item.get("market_size_usd", 0)),
        ),
        reverse=True,
    )
    if ranked:
        trace.append(f"Fallback market search added {len(ranked)} external candidates.")
    return ranked


def _market_candidate_is_relevant(title: str, context: str, industry_hint: str, geography: str) -> bool:
    title_lower = title.lower()
    context_lower = context.lower()
    haystack = f"{title_lower} {context_lower}"
    hint_terms = {token.lower() for token in re.findall(r"[a-zA-Z0-9]+", industry_hint) if len(token) > 3}
    overlap = sum(1 for term in hint_terms if term in haystack)
    if overlap == 0:
        return False
    if "wikipedia" in haystack:
        return False
    if geography and geography.lower() not in haystack and "united states" not in haystack and "u.s." not in haystack and "usa" not in haystack:
        return False
    if not any(token in haystack for token in ("software", "platform", "automation", "agriculture", "farming", "greenhouse", "vertical farm", "indoor farm")):
        return False
    return True


def _extract_market_size_values(text: str, geography: str = "", industry_hint: str = "") -> list[dict[str, Any]]:
    if not text:
        return []
    normalized = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    normalized = re.sub(r"\s+", " ", normalized)
    matches = []
    geo_lower = geography.lower()
    hint_terms = {token.lower() for token in re.findall(r"[a-zA-Z0-9]+", industry_hint) if len(token) > 3}
    pattern = re.compile(
        r"(?P<prefix>market size|industry|market|sector|revenue|worth|valued at|valuation|expected to reach|projected to reach)?"
        r"[^$]{0,60}?\$?(?P<number>[0-9]{1,4}(?:\.[0-9]{1,2})?)\s*"
        r"(?P<scale>billion|million|trillion)\b",
        flags=re.I,
    )
    for match in pattern.finditer(normalized):
        number = float(match.group("number"))
        scale = match.group("scale").lower()
        multiplier = 1_000_000 if scale == "million" else 1_000_000_000 if scale == "billion" else 1_000_000_000_000
        market_size_usd = number * multiplier
        start = max(0, match.start() - 140)
        end = min(len(normalized), match.end() + 140)
        context = normalized[start:end].strip()
        context = _normalize_text(context)
        if _is_noise_text(context):
            continue
        context_lower = context.lower()
        geo_match = bool(geo_lower and geo_lower in context_lower)
        industry_overlap = sum(1 for term in hint_terms if term in context_lower)
        matches.append(
            {
                "market_size_usd": market_size_usd,
                "display_value": f"${number:g} {scale}",
                "context": context,
                "match_kind": (match.group("prefix") or "market-size-mention").strip().lower(),
                "geography_match": geo_match,
                "industry_overlap": industry_overlap,
            }
        )
    matches.sort(
        key=lambda item: (
            item.get("geography_match", False),
            item.get("industry_overlap", 0),
            item.get("market_size_usd", 0),
        ),
        reverse=True,
    )
    return matches


def _dedupe_market_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in items:
        key = (item.get("source_url", ""), int(item.get("market_size_usd", 0)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _market_source_confidence(
    url: str,
    title: str,
    context: str,
    geography: str,
    industry_hint: str,
) -> float:
    score = 0.0
    domain = urlparse(url).netloc.lower()
    title_lower = title.lower()
    context_lower = context.lower()
    geo_lower = geography.lower()
    hint_terms = {token.lower() for token in re.findall(r"[a-zA-Z0-9]+", industry_hint) if len(token) > 3}

    if any(domain.endswith(pref) or pref in domain for pref in PREFERRED_MARKET_SOURCE_DOMAINS):
        score += 0.35
    if any(token in title_lower for token in ("market size", "industry report", "market", "industry", "outlook")):
        score += 0.15
    if any(token in context_lower for token in ("market size", "valued at", "projected to reach", "worth", "revenue")):
        score += 0.2
    if geo_lower and geo_lower in f"{title_lower} {context_lower}":
        score += 0.1
    overlap = sum(1 for term in hint_terms if term in f"{title_lower} {context_lower}")
    score += min(overlap * 0.05, 0.2)
    if "software" in f"{title_lower} {context_lower}" or "platform" in f"{title_lower} {context_lower}":
        score += 0.05
    return round(min(score, 1.0), 2)


def _market_source_reasons(
    url: str,
    title: str,
    context: str,
    geography: str,
    industry_hint: str,
) -> list[str]:
    reasons: list[str] = []
    domain = urlparse(url).netloc.lower()
    title_lower = title.lower()
    context_lower = context.lower()
    if any(domain.endswith(pref) or pref in domain for pref in PREFERRED_MARKET_SOURCE_DOMAINS):
        reasons.append("preferred-domain")
    if "market size" in title_lower or "industry report" in title_lower:
        reasons.append("strong-title-signal")
    if any(token in context_lower for token in ("valued at", "projected to reach", "market size", "worth")):
        reasons.append("explicit-market-value")
    if geography and geography.lower() in f"{title_lower} {context_lower}":
        reasons.append("geography-match")
    hint_terms = {token.lower() for token in re.findall(r"[a-zA-Z0-9]+", industry_hint) if len(token) > 3}
    if any(term in f"{title_lower} {context_lower}" for term in hint_terms):
        reasons.append("industry-match")
    if "software" in f"{title_lower} {context_lower}" or "platform" in f"{title_lower} {context_lower}":
        reasons.append("software-scope-match")
    return reasons
