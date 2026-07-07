from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Iterable

import requests


REQUEST_TIMEOUT = 8
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}


@dataclass
class LinkCheckResult:
    url: str
    ok: bool
    status_code: int | None
    final_url: str
    content_type: str
    error: str = ""


def check_url(url: str) -> LinkCheckResult:
    try:
        response = requests.head(url, allow_redirects=True, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        if not (200 <= response.status_code < 400):
            response = requests.get(url, allow_redirects=True, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        return LinkCheckResult(
            url=url,
            ok=200 <= response.status_code < 400,
            status_code=response.status_code,
            final_url=str(response.url),
            content_type=response.headers.get("content-type", ""),
        )
    except Exception as exc:
        return LinkCheckResult(
            url=url,
            ok=False,
            status_code=None,
            final_url=url,
            content_type="",
            error=str(exc),
        )


def check_urls(urls: Iterable[str]) -> dict[str, LinkCheckResult]:
    return {url: check_url(url) for url in urls if url}


def main() -> int:
    urls = [value for value in sys.argv[1:] if value]
    if not urls:
        return 0
    for url, result in check_urls(urls).items():
        status = "ok" if result.ok else "fail"
        code = result.status_code if result.status_code is not None else "-"
        print(f"{status}\t{code}\t{url}\t{result.final_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
