"""
Smoke test for the MCP servers — NO LLM / API key needed.

For each server it:
  1. connects and lists the tools
  2. calls one safe, read-only tool

Usage:
    python test_servers.py
"""

import asyncio
import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()  # local runs: finds the project .env | Docker: env comes from compose

SERVERS = {
    "weather": os.getenv("WEATHER_MCP_URL", "http://127.0.0.1:8001/mcp"),
    "jira": os.getenv("JIRA_MCP_URL", "http://127.0.0.1:8002/mcp"),
    "ec2": os.getenv("EC2_MCP_URL", "http://127.0.0.1:8003/mcp"),
    "github": os.getenv("GITHUB_MCP_URL", "http://127.0.0.1:8004/mcp"),
    "currency": os.getenv("CURRENCY_MCP_URL", "http://127.0.0.1:8005/mcp"),
    "wikipedia": os.getenv("WIKIPEDIA_MCP_URL", "http://127.0.0.1:8006/mcp"),
}

# One safe test call per server
TEST_CALLS = {
    "weather": ("get_current_weather", {"city": "Hyderabad"}),
    "jira": ("list_projects", {}),
    "ec2": ("get_instance_summary", {}),
    "github": ("get_repo", {"repo": "modelcontextprotocol/python-sdk"}),
    "currency": ("convert_currency", {"amount": 100, "from_currency": "USD", "to_currency": "INR"}),
    "wikipedia": ("get_wikipedia_summary", {"title": "Hyderabad"}),
}


def as_text(result) -> str:
    if isinstance(result, list):  # list of content blocks
        return " ".join(b.get("text", str(b)) if isinstance(b, dict) else str(b) for b in result)
    return str(result)


async def main():
    client = MultiServerMCPClient(
        {name: {"transport": "streamable_http", "url": url} for name, url in SERVERS.items()}
    )
    passed = 0
    for name, url in SERVERS.items():
        print(f"\n=== {name.upper()}  ({url}) ===")
        try:
            tools = {t.name: t for t in await client.get_tools(server_name=name)}
        except Exception as e:
            print(f"❌ Cannot connect: {type(e).__name__}. Is the server running?")
            continue
        print(f"✅ Tools: {', '.join(tools)}")

        tool_name, args = TEST_CALLS[name]
        if tool_name in tools:
            result = as_text(await tools[tool_name].ainvoke(args))
            print(f"▶ {tool_name}({args}):\n{result[:600]}")
        passed += 1

    print(f"\n{passed}/{len(SERVERS)} servers reachable.")


if __name__ == "__main__":
    asyncio.run(main())
