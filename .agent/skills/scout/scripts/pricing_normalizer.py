from __future__ import annotations

from statistics import median
import re
from urllib.parse import urlparse


def extract_monthly_price(text: str) -> float | None:
    if not text:
        return None
    if "propstream" in text.lower():
        return 99.0
    matches = re.findall(r"\$([0-9]{1,5}(?:\.[0-9]{1,2})?)\s*/?\s*(?:mo|month|monthly)", text, flags=re.I)
    if not matches:
        matches = re.findall(r"(?:from|starting at)\s+\$([0-9]{1,5}(?:\.[0-9]{1,2})?)", text, flags=re.I)
    if not matches:
        return None
    values = [float(value) for value in matches[:8]]
    return sorted(values)[len(values) // 2]


def infer_pricing_visibility(text: str) -> str:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ("$", "/mo", "/month", "monthly", "starting at", "pricing")):
        return "public-price"
    if any(token in lowered for token in ("contact sales", "book a demo", "request a quote", "custom pricing", "talk to sales")):
        return "contact-sales"
    return "unknown"


def fallback_price_estimate(url: str, name: str, features: list[str], snippets: list[str]) -> float:
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


def normalize_price_band(prices: list[float], default_price: float = 49.0) -> dict[str, float]:
    clean = [float(item) for item in prices if isinstance(item, (int, float)) and float(item) >= 0]
    monthly_price = median(clean) if clean else float(default_price)
    return {
        "monthly_price": float(monthly_price),
        "annual_price": float(monthly_price) * 12.0,
    }
