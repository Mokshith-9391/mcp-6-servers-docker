"""
Jira MCP Server
===============
Gives the agent five tools for Jira Cloud:
  - list_projects()
  - search_issues(jql, max_results)
  - get_issue(issue_key)
  - create_issue(project_key, summary, description, issue_type)
  - add_comment(issue_key, comment)

Needs in .env:  JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN
Create a token: https://id.atlassian.com/manage-profile/security/api-tokens

Run it:
    python server.py
It listens at: http://127.0.0.1:8002/mcp
"""

import os

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()  # local runs: finds the project .env | Docker: env comes from compose

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("JIRA_PORT", "8002"))

JIRA_URL = os.getenv("JIRA_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

mcp = FastMCP("jira", host=HOST, port=PORT)


# ---------------------------------------------------------------- helpers
def _config_error() -> str | None:
    """Return a friendly message if Jira settings are missing."""
    missing = [k for k, v in {"JIRA_URL": JIRA_URL, "JIRA_EMAIL": JIRA_EMAIL,
                              "JIRA_API_TOKEN": JIRA_API_TOKEN}.items()
               if not v or "your-domain" in v]
    if missing:
        return f"Jira is not configured. Set these in .env: {', '.join(missing)}"
    return None


def _client() -> httpx.AsyncClient:
    """HTTP client with Jira Cloud basic auth (email + API token)."""
    return httpx.AsyncClient(
        base_url=JIRA_URL,
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=20,
    )


def _api_error(resp: httpx.Response) -> str:
    return f"Jira API error {resp.status_code}: {resp.text[:300]}"


def _to_adf(text: str) -> dict:
    """Jira API v3 needs rich text in 'Atlassian Document Format' (ADF)."""
    paragraphs = [p for p in (text or "").split("\n") if p.strip()] or ["(no description)"]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}]}
            for p in paragraphs
        ],
    }


def _from_adf(node) -> str:
    """Pull plain text back out of an ADF document."""
    if not node:
        return ""
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        text = "".join(_from_adf(c) for c in node.get("content", []))
        return text + ("\n" if node.get("type") == "paragraph" else "")
    if isinstance(node, list):
        return "".join(_from_adf(c) for c in node)
    return str(node)


def _issue_line(issue: dict) -> str:
    f = issue.get("fields", {})
    assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
    status = (f.get("status") or {}).get("name", "?")
    itype = (f.get("issuetype") or {}).get("name", "?")
    return f"- {issue['key']} [{itype} | {status}] {f.get('summary', '')} (assignee: {assignee})"


# ---------------------------------------------------------------- tools
@mcp.tool()
async def list_projects() -> str:
    """List the Jira projects (key and name) the user can access."""
    if err := _config_error():
        return err
    async with _client() as client:
        resp = await client.get("/rest/api/3/project/search", params={"maxResults": 50})
    if resp.status_code != 200:
        return _api_error(resp)
    projects = resp.json().get("values", [])
    if not projects:
        return "No projects found."
    return "Jira projects:\n" + "\n".join(f"- {p['key']}: {p['name']}" for p in projects)


@mcp.tool()
async def search_issues(jql: str, max_results: int = 10) -> str:
    """Search Jira issues using JQL (Jira Query Language).

    Args:
        jql: A JQL query, for example:
             'project = DEMO AND status = "To Do" ORDER BY created DESC'
             'assignee = currentUser() AND statusCategory != Done'
        max_results: Maximum issues to return (1-50). Default 10.
    """
    if err := _config_error():
        return err
    params = {
        "jql": jql,
        "maxResults": max(1, min(int(max_results), 50)),
        "fields": "summary,status,assignee,issuetype,priority",
    }
    async with _client() as client:
        resp = await client.get("/rest/api/3/search/jql", params=params)
    if resp.status_code != 200:
        return _api_error(resp)
    issues = resp.json().get("issues", [])
    if not issues:
        return f"No issues found for JQL: {jql}"
    return f"Found {len(issues)} issue(s):\n" + "\n".join(_issue_line(i) for i in issues)


@mcp.tool()
async def get_issue(issue_key: str) -> str:
    """Get full details of one Jira issue.

    Args:
        issue_key: The issue key, for example "DEMO-12".
    """
    if err := _config_error():
        return err
    fields = "summary,status,assignee,reporter,priority,issuetype,description,created,updated"
    async with _client() as client:
        resp = await client.get(f"/rest/api/3/issue/{issue_key}", params={"fields": fields})
    if resp.status_code != 200:
        return _api_error(resp)
    data = resp.json()
    f = data["fields"]
    return (
        f"{data['key']}: {f.get('summary')}\n"
        f"Type: {(f.get('issuetype') or {}).get('name')}\n"
        f"Status: {(f.get('status') or {}).get('name')}\n"
        f"Priority: {(f.get('priority') or {}).get('name')}\n"
        f"Assignee: {(f.get('assignee') or {}).get('displayName', 'Unassigned')}\n"
        f"Reporter: {(f.get('reporter') or {}).get('displayName')}\n"
        f"Created: {f.get('created')}  Updated: {f.get('updated')}\n"
        f"Description:\n{_from_adf(f.get('description')).strip() or '(none)'}\n"
        f"Link: {JIRA_URL}/browse/{data['key']}"
    )


@mcp.tool()
async def create_issue(project_key: str, summary: str,
                       description: str = "", issue_type: str = "Task") -> str:
    """Create a new Jira issue.

    Args:
        project_key: Project key, for example "DEMO".
        summary: One-line title of the issue.
        description: Longer details (plain text).
        issue_type: "Task", "Bug" or "Story" (must exist in the project). Default "Task".
    """
    if err := _config_error():
        return err
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": _to_adf(description),
            "issuetype": {"name": issue_type},
        }
    }
    async with _client() as client:
        resp = await client.post("/rest/api/3/issue", json=payload)
    if resp.status_code not in (200, 201):
        return _api_error(resp)
    key = resp.json()["key"]
    return f"Created {key}: {summary}\nLink: {JIRA_URL}/browse/{key}"


@mcp.tool()
async def add_comment(issue_key: str, comment: str) -> str:
    """Add a comment to a Jira issue.

    Args:
        issue_key: The issue key, for example "DEMO-12".
        comment: The comment text.
    """
    if err := _config_error():
        return err
    async with _client() as client:
        resp = await client.post(f"/rest/api/3/issue/{issue_key}/comment",
                                 json={"body": _to_adf(comment)})
    if resp.status_code not in (200, 201):
        return _api_error(resp)
    return f"Comment added to {issue_key}."


if __name__ == "__main__":
    print(f"🎫 Jira MCP server running at http://{HOST}:{PORT}/mcp")
    if err := _config_error():
        print(f"⚠️  {err} (server will start, tools will return this message)")
    mcp.run(transport="streamable-http")
