"""
LangChain MCP Agent
===================
Connects to six MCP servers (weather, jira, ec2, github, currency, wikipedia), loads their tools,
and lets an LLM decide which tool to call for each question.

Usage:
    python agent.py                          # interactive chat
    python agent.py "weather in Hyderabad?"  # one question, then exit

Flow:
    You  ->  Agent (LLM)  ->  picks a tool  ->  MCP server  ->  real API
                 ^                                             |
                 +-------------- tool result ------------------+
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()  # local runs: finds the project .env | Docker: env comes from compose

LLM_MODEL = os.getenv("LLM_MODEL", "anthropic:claude-haiku-4-5-20251001")

# ---------------------------------------------------------------------------
# 1) Where are the MCP servers? (all run on this same EC2 instance)
# ---------------------------------------------------------------------------
# name -> (env var with URL, default URL). In Docker, compose sets the URLs to
# service names (http://weather:8001/mcp). Locally the defaults use 127.0.0.1.
_SERVER_URLS = {
    "weather":   ("WEATHER_MCP_URL",   "http://127.0.0.1:8001/mcp"),
    "jira":      ("JIRA_MCP_URL",      "http://127.0.0.1:8002/mcp"),
    "ec2":       ("EC2_MCP_URL",       "http://127.0.0.1:8003/mcp"),
    "github":    ("GITHUB_MCP_URL",    "http://127.0.0.1:8004/mcp"),
    "currency":  ("CURRENCY_MCP_URL",  "http://127.0.0.1:8005/mcp"),
    "wikipedia": ("WIKIPEDIA_MCP_URL", "http://127.0.0.1:8006/mcp"),
}
MCP_SERVERS = {
    name: {"transport": "streamable_http", "url": os.getenv(env, default)}
    for name, (env, default) in _SERVER_URLS.items()
}

SYSTEM_PROMPT = f"""You are a helpful DevOps assistant with access to six tool groups:
- Weather: current weather and forecasts for any city.
- Jira: list projects, search issues with JQL, read, create and comment on issues.
- EC2: list and describe AWS EC2 instances (default region {os.getenv('AWS_REGION', 'ap-south-1')}).
- GitHub: public repo details, issues, latest releases, repo search, user profiles.
- Currency: live and historical exchange rates and conversions.
- Wikipedia: search articles and read summaries (any language, e.g. "te" for Telugu).

Rules:
- Use a tool whenever the question needs live data. Do not make up data.
- You may combine tools from different groups in one answer.
- Before creating a Jira issue or starting/stopping an instance, restate exactly
  what you are about to do. If key details are missing, ask the user.
- Keep answers short and clear. Use bullet points for lists.
"""


# ---------------------------------------------------------------------------
# 2) Load tools from each server (one at a time, so one failure is easy to spot)
# ---------------------------------------------------------------------------
async def load_mcp_tools(client: MultiServerMCPClient) -> list:
    all_tools = []
    for name, cfg in MCP_SERVERS.items():
        try:
            tools = await client.get_tools(server_name=name)
            all_tools.extend(tools)
            print(f"  ✅ {name:<10} {cfg['url']}  -> {[t.name for t in tools]}")
        except Exception as e:  # server down, wrong port, etc.
            print(f"  ❌ {name:<10} {cfg['url']}  -> not reachable ({type(e).__name__})")
    return all_tools


# ---------------------------------------------------------------------------
# 3) Build the agent = LLM + tools
# ---------------------------------------------------------------------------
async def build_agent():
    print("🔌 Connecting to MCP servers...")
    client = MultiServerMCPClient(MCP_SERVERS)
    tools = await load_mcp_tools(client)
    if not tools:
        raise SystemExit("No MCP tools loaded. Are the servers running? "
                         "Try: ./mcp.sh status  (or ./mcp.sh up)")

    print(f"🧠 Model: {LLM_MODEL}   |   {len(tools)} tools loaded\n")
    model = init_chat_model(LLM_MODEL, temperature=0)
    return create_agent(model, tools, system_prompt=SYSTEM_PROMPT)


def print_steps(new_messages: list) -> None:
    """Show which tools the agent called — great for learning how agents think."""
    for msg in new_messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                print(f"   🔧 calling {call['name']}({call['args']})")
        elif isinstance(msg, ToolMessage):
            preview = msg.text.replace("\n", " ")[:100]
            print(f"   📦 result: {preview}...")


async def ask(agent, history: list, question: str) -> list:
    history = history + [{"role": "user", "content": question}]
    result = await agent.ainvoke({"messages": history})
    messages = result["messages"]
    print_steps(messages[len(history):])
    print(f"\n🤖 {messages[-1].text}\n")
    return messages  # full conversation, so follow-up questions have context


# ---------------------------------------------------------------------------
# 4) Run: one-shot question or interactive chat
# ---------------------------------------------------------------------------
async def main():
    agent = await build_agent()

    if len(sys.argv) > 1:
        await ask(agent, [], " ".join(sys.argv[1:]))
        return

    print("💬 Ask me about weather, Jira, EC2, GitHub, currency or Wikipedia. Type 'exit' to quit, 'reset' to clear memory.\n")
    history: list = []
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            break
        if question.lower() == "reset":
            history = []
            print("🧹 Conversation cleared.\n")
            continue
        try:
            history = await ask(agent, history, question)
        except Exception as e:
            print(f"⚠️  Error: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
