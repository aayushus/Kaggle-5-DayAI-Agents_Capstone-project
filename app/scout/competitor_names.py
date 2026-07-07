from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


GENERIC_COMPETITOR_NAMES = {
    "",
    "github",
    "self",
    "techradar",
    "medium",
    "substack",
    "wordpress",
    "blog",
    "docs",
    "documentation",
    "pricing",
    "home",
    "overview",
    "article",
    "news",
}
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
)


def sanitize_competitor_name(name: Any, source_url: Any) -> str:
    candidate = str(name or "").strip()
    candidate = re.sub(r"\s+", " ", candidate).strip(" -|:#")
    candidate = re.sub(
        r"\b(pricing|reviews|features|alternatives|competitors)\b",
        "",
        candidate,
        flags=re.I,
    ).strip(" -|:#")
    if is_generic_competitor_name(candidate):
        candidate = brand_name_from_url(source_url)
    return candidate or "Unknown Competitor"


def is_generic_competitor_name(name: str) -> bool:
    lowered = str(name or "").lower()
    normalized = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
    generic_normalized = {re.sub(r"[^a-z0-9]+", "", item) for item in GENERIC_COMPETITOR_NAMES}
    if not normalized or normalized in generic_normalized:
        return True
    if any(hint in lowered for hint in GENERIC_NAME_HINTS):
        return True
    if len(normalized) <= 2:
        return True
    if normalized in {"selfhosted", "opensource"}:
        return True
    if " with " in lowered or lowered.startswith(("best ", "smart ", "automated ", "introduction", "how ")):
        return True
    if len(lowered.split()) > 4:
        return True
    return False


def brand_name_from_url(source_url: Any) -> str:
    parsed = urlparse(str(source_url or ""))
    host = parsed.netloc.lower().replace("www.", "")
    if not host:
        return ""
    if host == "github.com":
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2:
            return path_parts[1]
        return "GitHub Project"
    brand = host.split(".")[0]
    if not brand:
        return ""
    return brand.replace("-", " ").replace("_", " ").title()
