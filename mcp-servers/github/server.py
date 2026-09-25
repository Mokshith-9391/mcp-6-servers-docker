"""
GitHub MCP Server
=================
Tools for public GitHub data:
  - get_repo(repo)                          e.g. "langchain-ai/langchain"
  - list_repo_issues(repo, state, limit)
  - get_latest_release(repo)
  - search_repositories(query, limit)
  - get_user(username)

Auth: optional. Without GITHUB_TOKEN you get 60 requests/hour.
      With a token (no scopes needed for public data) you get 5,000/hour.
      Create one: https://github.com/settings/tokens

Run:  python server.py      ->  http://<MCP_HOST>:8004/mcp
"""

import os

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()  # local runs: finds the project .env | Docker: env comes from compose

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("GITHUB_PORT", "8004"))
TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

mcp = FastMCP("github", host=HOST, port=PORT)


def _client() -> httpx.AsyncClient:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "mcp-langchain-lab",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return httpx.AsyncClient(base_url="https://api.github.com", headers=headers, timeout=15)


def _error(resp: httpx.Response) -> str:
    if resp.status_code == 404:
        return "Not found on GitHub. Check the name (format: owner/repo)."
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        return "GitHub rate limit reached. Add GITHUB_TOKEN to .env for 5,000 requests/hour."
    return f"GitHub API error {resp.status_code}: {resp.text[:200]}"


@mcp.tool()
async def get_repo(repo: str) -> str:
    """Get details about a GitHub repository: stars, forks, language, open issues.

    Args:
        repo: Repository in "owner/name" format, e.g. "kubernetes/kubernetes".
    """
    async with _client() as client:
        resp = await client.get(f"/repos/{repo.strip()}")
    if resp.status_code != 200:
        return _error(resp)
    r = resp.json()
    return (
        f"{r['full_name']} — {r.get('description') or 'no description'}\n"
        f"- ⭐ Stars: {r['stargazers_count']:,}   🍴 Forks: {r['forks_count']:,}\n"
        f"- Language: {r.get('language') or '-'}   License: {(r.get('license') or {}).get('spdx_id', '-')}\n"
        f"- Open issues + PRs: {r['open_issues_count']:,}\n"
        f"- Default branch: {r['default_branch']}   Last push: {r['pushed_at']}\n"
        f"- URL: {r['html_url']}"
    )


@mcp.tool()
async def list_repo_issues(repo: str, state: str = "open", limit: int = 5) -> str:
    """List recent issues (not pull requests) in a GitHub repository.

    Args:
        repo: Repository in "owner/name" format.
        state: "open", "closed" or "all". Default "open".
        limit: How many issues to return (1-20). Default 5.
    """
    limit = max(1, min(int(limit), 20))
    params = {"state": state, "per_page": 50, "sort": "created", "direction": "desc"}
    async with _client() as client:
        resp = await client.get(f"/repos/{repo.strip()}/issues", params=params)
    if resp.status_code != 200:
        return _error(resp)
    # GitHub returns pull requests in this endpoint too — filter them out
    issues = [i for i in resp.json() if "pull_request" not in i][:limit]
    if not issues:
        return f"No {state} issues found in {repo}."
    lines = [f"Latest {len(issues)} {state} issue(s) in {repo}:"]
    for i in issues:
        labels = ", ".join(l["name"] for l in i.get("labels", [])) or "no labels"
        lines.append(f"- #{i['number']} {i['title']} ({labels}) — {i['html_url']}")
    return "\n".join(lines)


@mcp.tool()
async def get_latest_release(repo: str) -> str:
    """Get the latest published release (version) of a GitHub repository.

    Args:
        repo: Repository in "owner/name" format, e.g. "hashicorp/terraform".
    """
    async with _client() as client:
        resp = await client.get(f"/repos/{repo.strip()}/releases/latest")
    if resp.status_code == 404:
        return f"{repo} has no published releases (or the repo does not exist)."
    if resp.status_code != 200:
        return _error(resp)
    r = resp.json()
    notes = (r.get("body") or "").strip().replace("\r", "")[:400]
    return (
        f"Latest release of {repo}: {r['tag_name']} ({r.get('name') or ''})\n"
        f"- Published: {r['published_at']}\n"
        f"- URL: {r['html_url']}\n"
        f"- Notes (start): {notes or '(none)'}"
    )


@mcp.tool()
async def search_repositories(query: str, limit: int = 5) -> str:
    """Search public GitHub repositories, sorted by stars.

    Args:
        query: Search words, e.g. "mcp server python" or "language:go kubernetes operator".
        limit: How many results (1-10). Default 5.
    """
    limit = max(1, min(int(limit), 10))
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
    async with _client() as client:
        resp = await client.get("/search/repositories", params=params)
    if resp.status_code != 200:
        return _error(resp)
    items = resp.json().get("items", [])
    if not items:
        return f"No repositories found for '{query}'."
    lines = [f"Top {len(items)} repositories for '{query}':"]
    for r in items:
        desc = (r.get("description") or "")[:90]
        lines.append(f"- {r['full_name']} ⭐{r['stargazers_count']:,} [{r.get('language') or '-'}] {desc}")
    return "\n".join(lines)


@mcp.tool()
async def get_user(username: str) -> str:
    """Get a GitHub user's or organisation's public profile.

    Args:
        username: GitHub login, e.g. "torvalds" or "aws".
    """
    async with _client() as client:
        resp = await client.get(f"/users/{username.strip()}")
    if resp.status_code != 200:
        return _error(resp)
    u = resp.json()
    return (
        f"{u.get('name') or u['login']} (@{u['login']}, {u['type']})\n"
        f"- Bio: {u.get('bio') or '-'}\n"
        f"- Company: {u.get('company') or '-'}   Location: {u.get('location') or '-'}\n"
        f"- Public repos: {u['public_repos']}   Followers: {u['followers']:,}\n"
        f"- Joined: {u['created_at'][:10]}   URL: {u['html_url']}"
    )


if __name__ == "__main__":
    auth = "with token" if TOKEN else "no token (60 req/hour)"
    print(f"🐙 GitHub MCP server running at http://{HOST}:{PORT}/mcp  ({auth})")
    mcp.run(transport="streamable-http")
