"""
Wikipedia MCP Server
====================
Tools for looking things up on Wikipedia (any language edition):
  - search_wikipedia(query, limit, language)
  - get_wikipedia_summary(title, language)

API: Wikimedia REST + Action API -> free, NO API key needed.
Wikimedia asks every client to send a descriptive User-Agent (done below).

Run:  python server.py      ->  http://<MCP_HOST>:8006/mcp
"""

import html
import os
import re
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()  # local runs: finds the project .env | Docker: env comes from compose

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("WIKIPEDIA_PORT", "8006"))
USER_AGENT = os.getenv(
    "WIKIPEDIA_USER_AGENT",
    "mcp-langchain-lab/1.0 (training project; contact: admin@example.com)",
)

mcp = FastMCP("wikipedia", host=HOST, port=PORT)


def _lang(language: str) -> str:
    code = (language or "en").strip().lower()
    return code if re.fullmatch(r"[a-z\-]{2,12}", code) else "en"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15,
                             follow_redirects=True)


@mcp.tool()
async def search_wikipedia(query: str, limit: int = 5, language: str = "en") -> str:
    """Search Wikipedia and return matching article titles with a short snippet.

    Args:
        query: What to search for, e.g. "Model Context Protocol".
        limit: Number of results (1-10). Default 5.
        language: Wikipedia language code: "en" (default), "te" Telugu, "hi" Hindi, ...
    """
    lang = _lang(language)
    params = {
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": max(1, min(int(limit), 10)), "format": "json",
    }
    try:
        async with _client() as client:
            resp = await client.get(f"https://{lang}.wikipedia.org/w/api.php", params=params)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        return f"Wikipedia error: {e}"

    results = resp.json().get("query", {}).get("search", [])
    if not results:
        return f"No Wikipedia articles found for '{query}' ({lang})."
    lines = [f"Wikipedia ({lang}) results for '{query}':"]
    for r in results:
        snippet = html.unescape(re.sub(r"<[^>]+>", "", r.get("snippet", "")))
        lines.append(f"- {r['title']}: {snippet[:120]}...")
    lines.append("Use get_wikipedia_summary with an exact title for details.")
    return "\n".join(lines)


@mcp.tool()
async def get_wikipedia_summary(title: str, language: str = "en") -> str:
    """Get the introduction/summary of a Wikipedia article.

    Args:
        title: Exact or close article title, e.g. "Hyderabad" or "Kubernetes".
        language: Wikipedia language code, default "en".
    """
    lang = _lang(language)
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.strip().replace(' ', '_'))}"
    try:
        async with _client() as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        return f"Wikipedia error: {e}"

    if resp.status_code == 404:
        return f"No article titled '{title}'. Try search_wikipedia first."
    if resp.status_code != 200:
        return f"Wikipedia error {resp.status_code}: {resp.text[:200]}"

    d = resp.json()
    if d.get("type") == "disambiguation":
        return (f"'{d['title']}' has several meanings. "
                f"Use search_wikipedia to pick a more specific title.")
    link = d.get("content_urls", {}).get("desktop", {}).get("page", "")
    desc = f" — {d['description']}" if d.get("description") else ""
    return f"{d['title']}{desc}\n\n{d.get('extract', '(no summary)')}\n\nSource: {link}"


if __name__ == "__main__":
    print(f"📚 Wikipedia MCP server running at http://{HOST}:{PORT}/mcp")
    mcp.run(transport="streamable-http")
