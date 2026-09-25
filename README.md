<p align="center">
  <img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-blueviolet?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZD0iTTEyIDJMMiA3djEwbDEwIDUgMTAtNVY3TDEyIDJ6IiBmaWxsPSJ3aGl0ZSIvPjwvc3ZnPg==" alt="MCP"/>
  <br/>
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/LangChain-Agent-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangChain"/>
</p>

# 🚀 MCP 6-Servers Docker

> **A production-ready, Dockerized multi-server MCP (Model Context Protocol) stack with 6 independent API servers and a LangChain-powered AI agent — all orchestrated with Docker Compose.**

Ask a single question in natural language and the AI agent automatically picks the right tool, calls the right API, and returns a clear answer.

```
You: What's the weather in Hyderabad and convert 500 USD to INR?

🔧 calling get_current_weather({"city": "Hyderabad"})
🔧 calling convert_currency({"amount": 500, "from_currency": "USD", "to_currency": "INR"})

🤖 Here's what I found:
  • Hyderabad: 32°C, Partly cloudy, Humidity 65%, Wind 12 km/h
  • 500 USD = 41,825.00 INR (rate: 1 USD = 83.65 INR)
```

---

## 📋 Table of Contents

- [Architecture](#-architecture)
- [Servers & Tools](#-servers--tools)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [CLI Reference](#-cli-reference-mcpsh)
- [How It Works](#-how-it-works)
- [Project Structure](#-project-structure)
- [AWS EC2 Deployment](#-aws-ec2-deployment)
- [Testing](#-testing)
- [Tech Stack](#-tech-stack)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Docker Network (mcp-net)                  │
│                                                                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐           │
│  │ Weather  │  │  Jira   │  │   EC2   │  │  GitHub  │           │
│  │  :8001   │  │  :8002  │  │  :8003  │  │  :8004   │           │
│  └────┬─────┘  └────┬────┘  └────┬────┘  └────┬─────┘           │
│       │             │            │             │                  │
│  ┌────┴─────┐  ┌────┴────┐      │             │                  │
│  │ Currency │  │Wikipedia│      │             │                  │
│  │  :8005   │  │  :8006  │      │             │                  │
│  └────┬─────┘  └────┬────┘      │             │                  │
│       │             │            │             │                  │
│       └──────┬──────┴────────┬──┘─────────────┘                  │
│              │               │                                   │
│         ┌────▼───────────────▼────┐                              │
│         │     LangChain Agent     │                              │
│         │   (interactive / CLI)   │                              │
│         │                         │                              │
│         │  LLM ←→ Tool Selection  │                              │
│         │  (Claude / GPT / etc.)  │                              │
│         └─────────────────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
                          ▲
                          │  Streamable HTTP (/mcp)
                          ▼
            ┌───────────────────────┐
            │   External APIs       │
            │  Open-Meteo · Jira    │
            │  AWS · GitHub · ECB   │
            │  Wikipedia            │
            └───────────────────────┘
```

Each MCP server runs in its **own container**, receives **only the env vars it needs**, and exposes tools via the **Streamable HTTP** transport on `/mcp`.

---

## 🔧 Servers & Tools

| Server | Port | API Source | API Key? | Tools |
|--------|------|-----------|----------|-------|
| **🌤 Weather** | `8001` | [Open-Meteo](https://open-meteo.com) | ❌ No | `get_current_weather`, `get_forecast` |
| **🎫 Jira** | `8002` | [Jira Cloud REST API v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/) | ✅ Yes | `list_projects`, `search_issues`, `get_issue`, `create_issue`, `add_comment` |
| **🖥 EC2** | `8003` | [AWS EC2 (boto3)](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html) | IAM Role | `list_instances`, `describe_instance`, `get_instance_summary`, `start_instance`*, `stop_instance`* |
| **🐙 GitHub** | `8004` | [GitHub REST API](https://docs.github.com/en/rest) | 🔶 Optional | `get_repo`, `list_repo_issues`, `get_latest_release`, `search_repositories`, `get_user` |
| **💱 Currency** | `8005` | [Frankfurter (ECB)](https://frankfurter.dev) | ❌ No | `convert_currency`, `get_exchange_rates`, `list_currencies` |
| **📚 Wikipedia** | `8006` | [Wikimedia REST API](https://en.wikipedia.org/api/rest_v1/) | ❌ No | `search_wikipedia`, `get_wikipedia_summary` |

> **\*** EC2 start/stop tools are disabled by default. Set `EC2_ALLOW_WRITE=true` in `.env` to enable.
>
> **🔶** GitHub works without a token (60 req/hr). Add a token for 5,000 req/hr.

**Total: 22 tools** across 6 servers, all available to the AI agent simultaneously.

---

## ⚡ Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose plugin (v2)
- An LLM API key (Anthropic or OpenAI)

### 1. Clone & Configure

```bash
git clone https://github.com/Mokshith-9391/mcp-6-servers-docker.git
cd mcp-6-servers-docker

cp .env.example .env
nano .env   # Add your API keys
```

### 2. Start All Servers

```bash
# Build & start all 6 MCP servers in the background
docker compose up -d --build

# Verify everything is healthy
docker compose ps
```

### 3. Chat with the Agent

```bash
# Interactive chat mode
docker compose run --rm agent

# Or ask a single question
docker compose run --rm -T agent python agent.py "What's the latest release of kubernetes/kubernetes?"
```

### One-Line Setup (EC2 / Fresh Ubuntu)

```bash
git clone https://github.com/Mokshith-9391/mcp-6-servers-docker.git
cd mcp-6-servers-docker && bash docker-setup.sh
```

This installs Docker, prompts for API keys, builds images, starts containers, runs health checks, and verifies IAM role access — all in one go.

---

## ⚙ Configuration

All configuration lives in a single `.env` file. Copy the template and fill in your values:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Container | Required | Description |
|----------|-----------|----------|-------------|
| `LLM_MODEL` | agent | Yes | LLM to use. Examples: `anthropic:claude-haiku-4-5-20251001`, `openai:gpt-4o-mini` |
| `ANTHROPIC_API_KEY` | agent | If using Anthropic | Your Anthropic API key |
| `OPENAI_API_KEY` | agent | If using OpenAI | Your OpenAI API key |
| `JIRA_URL` | jira | For Jira tools | `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | jira | For Jira tools | Your Atlassian account email |
| `JIRA_API_TOKEN` | jira | For Jira tools | [Create one here](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `AWS_REGION` | ec2, agent | No | Default: `ap-south-1` |
| `EC2_ALLOW_WRITE` | ec2 | No | `false` (default) or `true` to enable start/stop |
| `GITHUB_TOKEN` | github | No | [Personal access token](https://github.com/settings/tokens) (no scopes needed) |
| `WIKIPEDIA_USER_AGENT` | wikipedia | No | Custom User-Agent string for Wikimedia |

> **Security**: Each container receives **only** the variables it needs. The weather container never sees your Jira token. The `.env` file is created with `chmod 600` permissions and is git-ignored.

---

## 📖 CLI Reference (`mcp.sh`)

A convenience wrapper around `docker compose`:

| Command | Description |
|---------|-------------|
| `./mcp.sh up` | Build (if needed) & start all 6 MCP servers |
| `./mcp.sh down` | Stop and remove all containers |
| `./mcp.sh status` | Show container status + health |
| `./mcp.sh logs [name]` | Follow logs (all servers, or one specific server) |
| `./mcp.sh restart [name]` | Recreate containers (after editing `.env`) |
| `./mcp.sh rebuild [name]` | Rebuild image(s) + recreate (after editing code) |
| `./mcp.sh test` | Run smoke tests against all servers (no LLM needed) |
| `./mcp.sh agent` | Start interactive chat with the AI agent |
| `./mcp.sh ask "question"` | Ask a single question and exit |
| `./mcp.sh shell <name>` | Open a bash shell inside a container |
| `./mcp.sh clean` | Remove containers, network **and** images |

**Server names**: `weather` · `jira` · `ec2` · `github` · `currency` · `wikipedia`

```bash
# Examples
./mcp.sh logs ec2           # Follow EC2 server logs
./mcp.sh restart jira       # Restart just the Jira container
./mcp.sh ask "List my Jira projects"
```

---

## 🧠 How It Works

```
┌──────┐     ┌───────────┐     ┌───────────┐     ┌──────────┐
│ User │────>│ LangChain │────>│ MCP Server│────>│ Real API │
│      │     │   Agent   │     │ (Docker)  │     │          │
│      │<────│           │<────│           │<────│          │
└──────┘     └───────────┘     └───────────┘     └──────────┘
              "Which tool        Executes         Returns
               should I          the tool          live
               call?"            function          data
```

1. **You ask a question** in natural language
2. **The LLM** (Claude/GPT) reads all 22 tool descriptions and decides which tool(s) to call
3. **LangChain** routes the tool call to the correct MCP server via Streamable HTTP
4. **The MCP server** calls the real external API (Open-Meteo, GitHub, AWS, etc.)
5. **The result** flows back through the chain and the LLM formats a human-friendly answer
6. **Multi-tool queries** work automatically — ask about weather AND currency in one question

### Key Design Decisions

- **One container per API** — isolated failures, independent scaling, minimal attack surface
- **Streamable HTTP transport** — standard HTTP, works through proxies and load balancers
- **No API keys baked into images** — all secrets flow through `.env` → Docker Compose → container env
- **Health checks on every server** — `docker compose` waits for all servers to be healthy before starting the agent
- **Read-only by default** — EC2 write operations require explicit opt-in via `EC2_ALLOW_WRITE=true`

---

## 📁 Project Structure

```
mcp-6-servers-docker/
├── docker-compose.yml          # Orchestrates all 7 containers
├── docker-setup.sh             # One-click setup for fresh Ubuntu/EC2
├── mcp.sh                      # CLI wrapper for day-to-day commands
├── .env.example                # Template for environment variables
├── .gitignore
│
├── agent/                      # LangChain AI agent
│   ├── agent.py                # Main agent: connects to 6 servers, runs chat loop
│   ├── test_servers.py         # Smoke tests (no LLM needed)
│   ├── Dockerfile
│   └── requirements.txt
│
├── mcp-servers/                # One folder per MCP server
│   ├── weather/
│   │   ├── server.py           # Open-Meteo: current weather + forecast
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── jira/
│   │   ├── server.py           # Jira Cloud: projects, issues, comments
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── ec2/
│   │   ├── server.py           # AWS EC2: list, describe, start/stop
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── github/
│   │   ├── server.py           # GitHub: repos, issues, releases, users
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── currency/
│   │   ├── server.py           # ECB rates: convert, exchange rates
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── wikipedia/
│       ├── server.py           # Wikipedia: search + summaries (multi-lang)
│       ├── Dockerfile
│       └── requirements.txt
│
└── deploy/                     # AWS deployment helpers
    ├── fix_imds_hop_limit.sh   # Fix IMDSv2 for Docker containers
    └── iam/
        ├── create_role.sh      # Create IAM role + instance profile
        ├── ec2-trust-policy.json
        ├── ec2-readonly-policy.json
        └── ec2-startstop-policy.json
```

---

## ☁ AWS EC2 Deployment

### Launch an EC2 Instance

1. **AMI**: Ubuntu 24.04 LTS
2. **Instance type**: `t3.medium` or larger (agent uses ~512 MB RAM)
3. **Security group**: Open port **22** (SSH) only — MCP servers bind to `127.0.0.1`
4. **Storage**: 20 GB gp3

### Attach an IAM Role (for EC2 tools)

```bash
# From your laptop or CloudShell (not the instance):
bash deploy/iam/create_role.sh              # read-only
bash deploy/iam/create_role.sh --with-write # + start/stop

# Then: EC2 Console → Actions → Security → Modify IAM role → select "mcp-ec2-agent-role"
```

### Fix IMDSv2 Hop Limit

Docker containers can't reach the EC2 metadata service by default (hop limit = 1). Fix it:

```bash
bash deploy/fix_imds_hop_limit.sh
# Or manually:
aws ec2 modify-instance-metadata-options \
    --instance-id i-0abc123 \
    --http-put-response-hop-limit 2 \
    --http-endpoint enabled
```

### Full Setup

```bash
ssh ubuntu@<your-ec2-ip>
git clone https://github.com/Mokshith-9391/mcp-6-servers-docker.git
cd mcp-6-servers-docker
bash docker-setup.sh    # Does everything: Docker, .env, build, start, test
./mcp.sh agent          # Start chatting!
```

---

## 🧪 Testing

### Smoke Tests (No LLM Required)

```bash
./mcp.sh test
```

This connects to each server, lists its tools, and makes one safe read-only call per server:

| Server | Test Call |
|--------|----------|
| Weather | `get_current_weather("Hyderabad")` |
| Jira | `list_projects()` |
| EC2 | `get_instance_summary()` |
| GitHub | `get_repo("modelcontextprotocol/python-sdk")` |
| Currency | `convert_currency(100, "USD", "INR")` |
| Wikipedia | `get_wikipedia_summary("Hyderabad")` |

### Manual Testing

```bash
# Test a single server with curl
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

---

## 🛠 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Protocol** | [Model Context Protocol (MCP)](https://modelcontextprotocol.io) — Streamable HTTP transport |
| **MCP SDK** | [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (Python) |
| **Agent Framework** | [LangChain](https://python.langchain.com/) + [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) |
| **LLM** | Anthropic Claude / OpenAI GPT (configurable) |
| **HTTP Client** | [httpx](https://www.python-httpx.org/) (async) |
| **AWS SDK** | [boto3](https://boto3.amazonaws.com/) |
| **Container Runtime** | Docker + Docker Compose v2 |
| **Language** | Python 3.12 |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-server`)
3. Add your MCP server in `mcp-servers/<name>/`
4. Add a service block in `docker-compose.yml`
5. Register the URL in `agent/agent.py` (`_SERVER_URLS`)
6. Run `./mcp.sh test` to verify
7. Submit a Pull Request

### Adding a New MCP Server

```python
# mcp-servers/myapi/server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("myapi", host="127.0.0.1", port=8007)

@mcp.tool()
async def my_tool(param: str) -> str:
    """Description the LLM reads to decide when to use this tool."""
    return f"Result for {param}"

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/Mokshith-9391">Mokshith Reddy</a>
  <br/>
  <sub>If you found this useful, give it a ⭐!</sub>
</p>
