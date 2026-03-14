"""
Web search tool using DuckDuckGo (no API key required).

Strategy:
  1. Try the DuckDuckGo Instant Answer API (JSON endpoint) for quick facts.
  2. If no useful result, scrape the DuckDuckGo HTML search page.
"""

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DDG_API_URL = "https://api.duckduckgo.com/"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


async def web_search(query: str, num_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo.

    Returns a formatted string with search results.
    """
    logger.info("web_search: query=%r num_results=%d", query, num_results)

    # ── 1. Try Instant Answer API ─────────────────────────────────────────────
    instant = await _ddg_instant(query)

    # ── 2. Scrape HTML results ────────────────────────────────────────────────
    results = await _ddg_html(query, num_results)

    parts: list[str] = [f"Search results for: {query!r}\n"]

    if instant:
        parts.append(f"📌 Instant Answer: {instant}\n")

    if results:
        for i, r in enumerate(results, 1):
            parts.append(f"{i}. **{r['title']}**")
            parts.append(f"   {r['url']}")
            if r.get("snippet"):
                parts.append(f"   {r['snippet']}")
            parts.append("")
    else:
        parts.append("No results found.")

    return "\n".join(parts)


async def _ddg_instant(query: str) -> Optional[str]:
    """Fetch DuckDuckGo instant answer (Abstract or Answer fields)."""
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            resp = await client.get(
                DDG_API_URL,
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        text = data.get("AbstractText") or data.get("Answer") or ""
        if text:
            source = data.get("AbstractSource", "")
            return f"{text} (Source: {source})" if source else text
    except Exception as exc:
        logger.debug("DDG instant API failed: %s", exc)
    return None


async def _ddg_html(query: str, num_results: int) -> list[dict]:
    """Scrape DuckDuckGo HTML search results."""
    results = []
    try:
        async with httpx.AsyncClient(
            timeout=15,
            headers=HEADERS,
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                DDG_HTML_URL,
                data={"q": query, "b": "", "kl": ""},
            )
            resp.raise_for_status()
            html = resp.text

        # Extract result blocks  ─ <div class="result__body">
        # Use simple regex since we want zero extra deps
        # Result links: <a class="result__a" href="...">title</a>
        # Snippets:     <a class="result__snippet">...</a>

        link_pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets_raw = snippet_pattern.findall(html)

        snippets = [_strip_tags(s) for s in snippets_raw]

        for idx, (url, title) in enumerate(links[:num_results]):
            # DuckDuckGo wraps external links; unwrap if needed
            url = _unwrap_ddg_url(url)
            title_clean = _strip_tags(title)
            snippet = snippets[idx] if idx < len(snippets) else ""
            results.append({"title": title_clean, "url": url, "snippet": snippet})

    except Exception as exc:
        logger.warning("DDG HTML scrape failed: %s", exc)

    return results


def _strip_tags(html: str) -> str:
    """Remove HTML tags and decode basic entities."""
    text = re.sub(r"<[^>]+>", "", html)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def _unwrap_ddg_url(url: str) -> str:
    """DuckDuckGo sometimes wraps URLs; return the real URL."""
    if url.startswith("//duckduckgo.com/l/?uddg="):
        # Extract the real URL from the query string
        m = re.search(r"uddg=([^&]+)", url)
        if m:
            from urllib.parse import unquote
            return unquote(m.group(1))
    return url
