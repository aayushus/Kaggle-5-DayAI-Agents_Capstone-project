from __future__ import annotations

from collections import Counter
import re


NOISE_PHRASES = (
    "skip to main content",
    "privacy overview",
    "cookie preferences",
    "cookie policy",
    "download a pdf",
    "join now",
    "newsletter",
    "request a demo",
    "book a demo",
    "follow us on",
)


def clean_text(text: str, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip(" -|\t\r\n")
    return value[:limit]


def looks_like_noise(text: str) -> bool:
    lowered = clean_text(text).lower()
    if len(lowered) < 18:
        return True
    return any(token in lowered for token in NOISE_PHRASES)


def rank_strings(items: list[str]) -> list[str]:
    counts = Counter(item for item in items if item)
    return sorted(counts, key=lambda item: (-counts[item], len(item)))


def select_source_snippets(snippets: list[str], features: list[str] | None = None, limit: int = 3) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for snippet in snippets:
        cleaned = clean_text(snippet)
        if not cleaned or looks_like_noise(cleaned):
            continue
        score = 0
        lowered = cleaned.lower()
        if any(token in lowered for token in ("pricing", "automation", "dashboard", "workflow", "sensor", "analytics", "real-time")):
            score += 2
        if 35 <= len(cleaned) <= 180:
            score += 2
        if len(cleaned.split()) >= 6:
            score += 1
        ranked.append((score, cleaned))
    ranked.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    selected = [item[1] for item in ranked[:limit]]
    if not selected and features:
        selected = [clean_text(item) for item in features[:limit] if clean_text(item)]
    return rank_strings(selected)[:limit]
