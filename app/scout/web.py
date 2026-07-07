from __future__ import annotations

from collections import Counter
import base64
import re
from typing import Any
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from app.config import load_settings
from app.scout.competitor_names import sanitize_competitor_name
from app.scout.parallel_mcp_client import web_fetch as parallel_mcp_web_fetch
from app.scout.parallel_mcp_client import web_search as parallel_mcp_web_search
from app.scout.parallel_search import parallel_live_search, parallel_search_hits
from app.scout.skill_runtime import load_evidence_normalizer_module, load_pricing_normalizer_module


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
REQUEST_HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = 12
SKIP_DOMAINS = {
    "duckduckgo.com",
    "google.com",
    "myaccount.google.com",
    "bing.com",
    "yahoo.com",
    "youtube.com",
    "reddit.com",
    "facebook.com",
    "linkedin.com",
    "microsoft.com",
    "support.microsoft.com",
    "account.microsoft.com",
    "wikipedia.org",
    "oxfordlearnersdictionaries.com",
    "matematrix.net",
    "hellosubscription.com",
    "merriam-webster.com",
    "x.com",
    "twitter.com",
}
MIN_PARALLEL_COMPETITORS = 3
PRICING_HINTS = ("pricing", "plans", "plan", "price", "subscription", "billing")
FEATURE_HINTS = ("feature", "features", "automation", "integration", "analytics", "dashboard", "workflow", "reporting")
WEAKNESS_HINTS = ("manual", "slow", "complex", "limited", "offline", "expensive", "setup", "implementation")
EVIDENCE_NORMALIZER = load_evidence_normalizer_module()
PRICING_NORMALIZER = load_pricing_normalizer_module()


def live_search(query: str, trace: list[str], plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    display_query = _plan_category(plan) or query
    trace.append(f"Searching the web for competitors in '{display_query}'.")
    settings = load_settings()
    if settings.parallel_search_mcp_enabled:
        trace.append("Researcher is using Parallel MCP as the primary search path.")
        search_hits = _discover_competitor_hits(query, trace, plan=plan)
        competitors = _competitors_from_hits(search_hits, trace)
        unique_competitors = _dedupe_competitors(competitors)
        if unique_competitors:
            trace.append(f"Research pipeline found {len(unique_competitors)} competitor candidates via MCP-first flow.")
            return unique_competitors
        trace.append("Parallel MCP search path returned no usable competitors; falling back.")

    parallel_competitors: list[dict[str, Any]] = []
    if settings.parallel_api_key_present:
        parallel_competitors = parallel_live_search(query, trace, mode=settings.parallel_search_mode, plan=plan)
        if parallel_competitors and _parallel_result_is_sufficient(parallel_competitors):
            return parallel_competitors
        # Parallel Search is the authoritative source. Only fall back to open-web
        # scraping when Parallel returns too few vendors to work with; otherwise a
        # usable Parallel set gets polluted by unrelated Bing/DuckDuckGo pages.
        if len(parallel_competitors) >= MIN_PARALLEL_COMPETITORS:
            trace.append(
                f"Using Parallel Search competitor set ({len(parallel_competitors)}); "
                "skipping open-web scrape fallback."
            )
            return parallel_competitors
        if parallel_competitors:
            trace.append("Parallel competitor set is thin; augmenting with direct vendor-page fallback.")
    else:
        trace.append("PARALLEL_API_KEY not configured; using open-web scrape discovery.")

    search_hits = _discover_competitor_hits(query, trace, plan=plan)
    competitors = _competitors_from_hits(search_hits, trace)
    unique_competitors = _dedupe_competitors(competitors)
    if parallel_competitors:
        unique_competitors = _merge_competitor_sets(parallel_competitors, unique_competitors)
    if unique_competitors:
        trace.append(f"Research pipeline found {len(unique_competitors)} competitor candidates.")
        return unique_competitors

    trace.append("Live search returned no parsed competitors; using minimal fallback entries.")
    return [
        {
            "name": "Competitor Alpha",
            "source_url": "https://example.com/alpha",
            "pricing_url": "https://example.com/alpha/pricing",
            "source_snippets": ["Fallback source because live research returned no usable competitor pages."],
            "price_monthly": 49.0,
            "features": ["Fast onboarding", "Usage analytics", "Basic automation"],
            "strengths": ["Clear pricing", "Fast onboarding"],
            "weaknesses": ["Limited offline support"],
        },
        {
            "name": "Competitor Beta",
            "source_url": "https://example.com/beta",
            "pricing_url": "https://example.com/beta/pricing",
            "source_snippets": ["Fallback source because live research returned no usable competitor pages."],
            "price_monthly": 99.0,
            "features": ["Enterprise controls", "Admin workflows", "Reporting"],
            "strengths": ["Enterprise features"],
            "weaknesses": ["High cost", "Complex setup"],
        },
    ]


def _competitors_from_hits(search_hits: list[dict[str, str]], trace: list[str]) -> list[dict[str, Any]]:
    competitors: list[dict[str, Any]] = []
    for hit in search_hits[:5]:
        trace.append(f"Fetching competitor candidate: {hit['url']}")
        primary_html = _fetch_page(hit["url"], trace)
        if not primary_html:
            continue
        primary_soup = BeautifulSoup(primary_html, "html.parser")
        pricing_url = _discover_pricing_url(hit["url"], primary_soup)
        pricing_html = _fetch_page(pricing_url, trace) if pricing_url and pricing_url != hit["url"] else primary_html
        price_monthly = _extract_monthly_price(pricing_html or primary_html)
        features = _extract_feature_bullets(primary_soup, pricing_html or primary_html)
        strengths = _extract_strengths(hit, primary_soup, features)
        weaknesses = _infer_weaknesses(features, price_monthly)
        snippets = _build_source_snippets(hit, primary_soup, pricing_html or primary_html, features)
        competitor_name = _normalize_competitor_name(hit, primary_soup)
        fallback_price = _fallback_price_estimate(hit["url"], competitor_name, features, snippets)

        competitor = {
            "name": competitor_name,
            "source_url": hit["url"],
            "pricing_url": pricing_url or hit["url"],
            "source_snippets": _select_source_snippets(snippets, features),
            "price_monthly": price_monthly if price_monthly is not None else fallback_price,
            "price_source_type": "extracted" if price_monthly is not None else "fallback-estimate",
            "pricing_visibility": "public-price" if price_monthly is not None else ("contact-sales" if _detect_pricing_visibility(pricing_html or primary_html) == "contact-sales" else "not-listed"),
            "features": features,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "source_quality": _assess_source_quality(hit["url"], snippets, features, price_monthly, price_monthly is not None, pricing_url or hit["url"]),
        }
        competitors.append(competitor)
    return competitors


def _plan_category(plan: dict[str, Any] | None) -> str:
    return str((plan or {}).get("category") or "").strip()


def _discover_competitor_hits(query: str, trace: list[str], plan: dict[str, Any] | None = None) -> list[dict[str, str]]:
    normalized_query = _plan_category(plan) or _normalized_competitor_query(query)
    known = [name for name in (plan or {}).get("known_competitors", []) if name]
    plan_queries = [q for q in (plan or {}).get("search_queries", []) if q]
    # Seed the exact brand names the planner surfaced so we fetch real vendor pages.
    seed_queries = [f"{name} pricing" for name in known[:6]]
    queries = plan_queries or [
        f"{normalized_query} competitor software pricing",
        f"{normalized_query} alternatives pricing",
        f"{normalized_query} market leaders pricing",
    ]
    queries = seed_queries + queries
    hits: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    settings = load_settings()

    if settings.parallel_search_mcp_enabled:
        provider_hits = _parallel_mcp_search_hits(queries, normalized_query, query, trace, settings.parallel_search_mcp_url)
    elif settings.parallel_api_key_present:
        provider_hits = parallel_search_hits(
            queries,
            (
                f"Find official competitor product or vendor pages for this startup: {query}. "
                f"Market category: {normalized_query}. "
                "Prioritize pricing and product pages. Exclude blog posts, documentation, GitHub repos, and listicles."
            ),
            trace,
            mode=settings.parallel_search_mode,
            max_results=16,
        )
    else:
        provider_hits = []

    if not provider_hits:
        provider_hits = []
        for item in queries:
            hit_batch = _duckduckgo_search(item, trace) or _bing_search(item, trace)
            provider_hits.extend(hit_batch)

    for hit in provider_hits:
        normalized_url = _normalize_url(hit["url"])
        domain = urlparse(normalized_url).netloc.lower()
        if not normalized_url or domain in SKIP_DOMAINS:
            continue
        # When the planner named the category, trust the LLM validator downstream
        # instead of the hardcoded keyword category filter.
        if not plan and not _hit_matches_competitor_category(normalized_query, hit):
            continue
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        hits.append(hit | {"url": normalized_url})
    return hits


def _parallel_mcp_search_hits(
    queries: list[str],
    normalized_query: str,
    query: str,
    trace: list[str],
    mcp_url: str,
) -> list[dict[str, str]]:
    objective = (
        f"Find official competitor product or vendor pages for this startup: {query}. "
        f"Market category: {normalized_query}. "
        "Prioritize pricing and product pages. Exclude blog posts, documentation pages, GitHub repositories, and generic listicles."
    )
    payload = parallel_mcp_web_search(
        objective=objective,
        search_queries=queries[:4],
        trace=trace,
        url=mcp_url,
    )
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    return [
        {
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "snippet": " ".join(str(part).strip() for part in (item.get("excerpts") or []) if str(part).strip())[:4000],
        }
        for item in results
        if item.get("url")
    ]


def _normalized_competitor_query(query: str) -> str:
    lowered = query.lower()
    if "vertical farming" in lowered or "indoor farming" in lowered:
        return "vertical farming software"
    if "iot" in lowered and "sensor" in lowered and ("farm" in lowered or "ag" in lowered):
        return "agtech farm monitoring software"
    if "market research" in lowered:
        return "ai market research software"
    if "startup founders" in lowered or "founder" in lowered:
        return "startup research software"
    return query


def _hit_matches_competitor_category(normalized_query: str, hit: dict[str, str]) -> bool:
    haystack = f"{hit.get('title', '')} {hit.get('snippet', '')} {hit.get('url', '')}".lower()
    if "vertical farming" in normalized_query or "indoor farming" in normalized_query:
        return any(token in haystack for token in ("farm", "farming", "greenhouse", "indoor", "hydroponic", "crop", "agri"))
    if "market research" in normalized_query or "startup research" in normalized_query:
        return any(token in haystack for token in ("market research", "research", "survey", "insight", "analytics", "customer"))
    if "agtech" in normalized_query or "farm monitoring" in normalized_query:
        return any(token in haystack for token in ("farm", "agri", "crop", "greenhouse", "sensor", "iot"))
    return True


def _duckduckgo_search(query: str, trace: list[str]) -> list[dict[str, str]]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except Exception as exc:
        trace.append(f"Search provider unavailable: {exc!s}")
        return []

    if response.status_code == 202 or "anomaly.js" in response.text:
        trace.append("DuckDuckGo returned an anti-bot page; falling back to Bing.")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, str]] = []
    for node in soup.select(".result"):
        title_node = node.select_one(".result__title a")
        snippet_node = node.select_one(".result__snippet")
        if not title_node or not title_node.get("href"):
            continue
        results.append(
            {
                "title": title_node.get_text(" ", strip=True),
                "url": title_node["href"],
                "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
            }
        )
    return results


def _bing_search(query: str, trace: list[str]) -> list[dict[str, str]]:
    url = f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except Exception as exc:
        trace.append(f"Bing unavailable: {exc!s}")
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        trace.append(f"Bing RSS parse failed: {exc!s}")
        return []

    results: list[dict[str, str]] = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        snippet = (node.findtext("description") or "").strip()
        if not title or not link:
            continue
        results.append(
            {
                "title": title,
                "url": link,
                "snippet": snippet,
            }
        )
    return results


def _fetch_page(url: str, trace: list[str]) -> str:
    settings = load_settings()
    if settings.parallel_search_mcp_enabled:
        payload = parallel_mcp_web_fetch(
            urls=[url],
            objective="Fetch the page content for competitor research and product/pricing extraction.",
            search_queries=["pricing features", "product capabilities"],
            trace=trace,
            url=settings.parallel_search_mcp_url,
            full_content=True,
        )
        results = payload.get("results", [])
        if isinstance(results, list) and results:
            content = str(results[0].get("full_content") or "").strip()
            if content:
                return content
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            return ""
        return response.text
    except Exception as exc:
        trace.append(f"Could not fetch {url}: {exc!s}")
        return ""


def _discover_pricing_url(base_url: str, soup: BeautifulSoup) -> str | None:
    for link in soup.select("a[href]"):
        href = (link.get("href") or "").strip()
        text = link.get_text(" ", strip=True).lower()
        if not href:
            continue
        haystack = f"{href.lower()} {text}"
        if any(hint in haystack for hint in PRICING_HINTS):
            return _normalize_url(urljoin(base_url, href))
    return None


def _extract_monthly_price(text: str) -> float | None:
    return PRICING_NORMALIZER.extract_monthly_price(text)


def _extract_feature_bullets(soup: BeautifulSoup, html: str) -> list[str]:
    bullets = [node.get_text(" ", strip=True) for node in soup.select("li, h2, h3") if node.get_text(" ", strip=True)]
    cleaned = [_clean_text(item) for item in bullets if 12 <= len(_clean_text(item)) <= 140]
    feature_candidates = [
        item for item in cleaned
        if any(hint in item.lower() for hint in FEATURE_HINTS)
        or len(item.split()) <= 8
    ]
    if not feature_candidates and html:
        text = _extract_visible_text(BeautifulSoup(html, "html.parser"))
        lines = [_clean_text(line) for line in text.splitlines()]
        feature_candidates = [line for line in lines if any(hint in line.lower() for hint in FEATURE_HINTS)]
    filtered = [
        item for item in feature_candidates
        if not _looks_like_noise(item)
    ]
    ranked = _rank_strings(filtered)
    return ranked[:6]


def _extract_strengths(hit: dict[str, str], soup: BeautifulSoup, features: list[str]) -> list[str]:
    strengths = []
    if hit.get("snippet"):
        strengths.append(_clean_text(hit["snippet"]))
    strengths.extend(features[:3])
    return _rank_strings(strengths)[:4]


def _infer_weaknesses(features: list[str], price_monthly: float | None) -> list[str]:
    weaknesses: list[str] = []
    feature_blob = " ".join(features).lower()
    if not any("offline" in feature.lower() for feature in features):
        weaknesses.append("No clear offline capability in public feature copy")
    if not any("setup" in feature.lower() or "implementation" in feature.lower() for feature in features):
        weaknesses.append("Setup and implementation path is not clearly explained")
    if price_monthly is not None and price_monthly >= 99:
        weaknesses.append("Pricing appears high for early-stage buyers")
    if not weaknesses and feature_blob:
        weaknesses.append("Public messaging emphasizes features more than buyer outcomes")
    return _rank_strings(weaknesses)[:4]


def _fallback_price_estimate(url: str, name: str, features: list[str], snippets: list[str]) -> float:
    return float(PRICING_NORMALIZER.fallback_price_estimate(url, name, features, snippets))


def _build_source_snippets(hit: dict[str, str], soup: BeautifulSoup, html: str, features: list[str]) -> list[str]:
    snippets: list[str] = []
    if hit.get("snippet"):
        snippets.append(_clean_text(hit["snippet"]))
    meta_description = soup.find("meta", attrs={"name": "description"})
    if meta_description and meta_description.get("content"):
        snippets.append(_clean_text(meta_description["content"]))
    snippets.extend(features[:2])
    visible_text = _extract_visible_text(soup if html else BeautifulSoup("", "html.parser"))
    if visible_text:
        snippets.extend([_clean_text(line) for line in visible_text.splitlines() if 20 <= len(_clean_text(line)) <= 180][:2])
    cleaned = [item for item in _rank_strings(snippets) if not _looks_like_noise(item)]
    return cleaned[:5]


def _normalize_competitor_name(hit: dict[str, str], soup: BeautifulSoup) -> str:
    og_site_name = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site_name and og_site_name.get("content"):
        return sanitize_competitor_name(_clean_title(og_site_name["content"]), hit.get("url"))
    title = hit.get("title", "")
    return sanitize_competitor_name(_clean_title(title or urlparse(hit["url"]).netloc), hit.get("url"))


def _extract_visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _rank_strings(items: list[str]) -> list[str]:
    counts = Counter(item for item in items if item)
    ranked = sorted(counts, key=lambda item: (-counts[item], len(item)))
    return ranked


def _dedupe_competitors(competitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_domain: dict[str, dict[str, Any]] = {}
    for competitor in competitors:
        domain = urlparse(competitor["source_url"]).netloc.lower()
        existing = by_domain.get(domain)
        if existing is None or len(competitor.get("features", [])) > len(existing.get("features", [])):
            by_domain[domain] = competitor
    return list(by_domain.values())


def _merge_competitor_sets(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for competitor in primary + secondary:
        domain = urlparse(competitor["source_url"]).netloc.lower()
        if not domain:
            continue
        existing = merged.get(domain)
        if existing is None:
            merged[domain] = competitor
            continue
        existing_score = int((existing.get("source_quality") or {}).get("score", 0))
        candidate_score = int((competitor.get("source_quality") or {}).get("score", 0))
        if candidate_score > existing_score or (
            candidate_score == existing_score and len(competitor.get("features", [])) > len(existing.get("features", []))
        ):
            merged[domain] = competitor
    ranked = sorted(
        merged.values(),
        key=lambda item: (
            int((item.get("source_quality") or {}).get("score", 0)),
            len(item.get("features", [])),
        ),
        reverse=True,
    )
    return ranked[:6]


def _parallel_result_is_sufficient(competitors: list[dict[str, Any]]) -> bool:
    if len(competitors) < MIN_PARALLEL_COMPETITORS:
        return False
    high_or_medium = [
        item for item in competitors
        if int((item.get("source_quality") or {}).get("score", 0)) >= 60
    ]
    # A real vendor's monthly price is often behind "contact sales" or missed by the
    # price regex, so we no longer require an extracted price here. Prices are clearly
    # labeled as verified vs. estimated downstream, and TAM prefers extracted prices.
    return len(high_or_medium) >= 3


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return _normalize_url(unquote(target))
    if "bing.com" in parsed.netloc and parsed.path.startswith("/ck/"):
        target = parse_qs(parsed.query).get("u", [""])[0]
        if target:
            decoded = _decode_bing_target(target)
            if decoded:
                return _normalize_url(decoded)
    if not parsed.scheme:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def _clean_title(title: str) -> str:
    cleaned = re.split(r"\s+[|\-:]\s+", title, maxsplit=1)[0]
    return _clean_text(cleaned)


def _clean_text(text: str) -> str:
    return EVIDENCE_NORMALIZER.clean_text(text)


def _detect_pricing_visibility(text: str) -> str:
    return PRICING_NORMALIZER.infer_pricing_visibility(text)


def _looks_like_noise(text: str) -> bool:
    return bool(EVIDENCE_NORMALIZER.looks_like_noise(text))


def _select_source_snippets(snippets: list[str], features: list[str]) -> list[str]:
    return list(EVIDENCE_NORMALIZER.select_source_snippets(snippets, features, limit=3))


def _assess_source_quality(
    url: str,
    snippets: list[str],
    features: list[str],
    price_monthly: float | None,
    extracted_price: bool,
    pricing_url: str,
) -> dict[str, Any]:
    score = 35
    reasons: list[str] = []
    if extracted_price and price_monthly is not None:
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
    domain = urlparse(url).netloc.lower()
    if domain and domain not in SKIP_DOMAINS:
        score += 10
        reasons.append("direct-domain")
    label = "High" if score >= 75 else "Medium" if score >= 55 else "Low"
    return {"score": min(score, 100), "label": label, "reasons": reasons}


def _decode_bing_target(value: str) -> str:
    if value.startswith("a1"):
        value = value[2:]
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.b64decode(value + padding).decode("utf-8", "ignore")
    except Exception:
        return ""
