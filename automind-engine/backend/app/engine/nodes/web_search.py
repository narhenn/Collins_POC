"""
Web Search Node - searches the web using DuckDuckGo.
No API key required.
"""

import logging
import re

import httpx

from app.engine.nodes.base import BaseNodeExecutor
from app.engine.variables import interpolate

logger = logging.getLogger(__name__)

DDGS_URL = "https://html.duckduckgo.com/html/"


class WebSearchNodeExecutor(BaseNodeExecutor):
    async def execute(self, config: dict, variables: dict, **kwargs) -> dict:
        query_template = config.get("query", "")
        query = interpolate(query_template, variables)
        max_results = config.get("max_results", 5)
        output_variable = config.get("output_variable", "search_results")

        if not query or (isinstance(query, str) and not query.strip()):
            return {"output_variables": {output_variable: []}}

        query_str = str(query).strip()

        try:
            results = await self._search(query_str, max_results)
            return {"output_variables": {output_variable: results}}
        except Exception as exc:
            logger.exception("Web search failed")
            return {
                "output_variables": {output_variable: []},
                "error": str(exc),
            }

    async def _search(self, query: str, max_results: int) -> list[dict]:
        """Search DuckDuckGo and parse results."""
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(
                DDGS_URL,
                data={"q": query, "b": ""},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AutoMind/1.0)"},
            )
            resp.raise_for_status()
            html = resp.text

        # Parse results from HTML
        results: list[dict] = []

        # DuckDuckGo HTML results are in <a class="result__a"> tags
        # and snippets in <a class="result__snippet">
        links = re.findall(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', html
        )
        snippets = re.findall(
            r'class="result__snippet"[^>]*>([^<]*(?:<[^/][^>]*>[^<]*</[^>]*>)*[^<]*)</a>',
            html,
        )

        for i, (url, title) in enumerate(links[:max_results]):
            snippet = snippets[i] if i < len(snippets) else ""
            # Clean HTML tags from snippet
            snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            results.append(
                {
                    "title": title.strip(),
                    "url": url,
                    "snippet": snippet,
                    "rank": i + 1,
                }
            )

        if not results:
            # Fallback: try a simpler regex pattern
            titles = re.findall(
                r'<a[^>]*class="[^"]*result[^"]*"[^>]*>([^<]+)</a>', html
            )
            for i, title in enumerate(titles[:max_results]):
                results.append(
                    {
                        "title": title.strip(),
                        "url": "",
                        "snippet": "",
                        "rank": i + 1,
                    }
                )

        return results
