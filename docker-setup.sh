#!/usr/bin/env bash
# =====================================================================
#  docker-setup.sh — ONE script to go from a fresh Ubuntu EC2 instance
#  to 6 running MCP server containers (one per API).
#
#  Usage (inside the project folder on the EC2 instance):
#      bash docker-setup.sh
#
#  Steps:
#    1. Install Docker Engine + Compose plugin (official Docker repo)
#    2. Create .env from .env.example (asks for your keys)
#    3. Build 7 images (6 MCP servers + agent)
#    4. Start weather/jira/ec2/github/currency/wikipedia containers
#    5. Wait until healthy, run smoke tests
#    6. Check the containers can use the EC2 IAM role (IMDS hop limit)
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo -e "\n${GREEN}==> $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
fail() { echo -e "${RED}❌ $*${NC}"; exit 1; }

# ---------------------------------------------------------------- 1. Docker
step "[1/6] Installing Docker"
if ! command -v apt-get >/dev/null 2>&1; then
  fail "This script supports Ubuntu. Launch an Ubuntu 24.04 EC2 instance."
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "Docker already installed: $(docker --version)"
else
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                          docker-buildx-plugin docker-compose-plugin
  sudo systemctl enable --now docker
  echo "Installed: $(docker --version)"
fi

# Let the current user run docker without sudo (takes effect after re-login)
if ! id -nG "$USER" | grep -qw docker; then
  sudo usermod -aG docker "$USER"
  warn "Added $USER to the 'docker' group. Log out/in later to drop 'sudo'."
fi

# Use sudo for this run if the group change is not active yet
if docker info >/dev/null 2>&1; then DOCKER="docker"; else DOCKER="sudo docker"; fi
COMPOSE="$DOCKER compose"

# ---------------------------------------------------------------- 2. .env
step "[2/6] Configuring .env"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env

  set_env() {  # set_env KEY VALUE  -> replace the line KEY=... in .env
    local key="$1" val="$2"
    val="${val//\\/\\\\}"; val="${val//|/\\|}"; val="${val//&/\\&}"
    sed -i "s|^${key}=.*|${key}=${val}|" .env
  }

  if [ -t 0 ]; then
    echo "Press Enter to skip any value (you can edit .env later)."
    read -rp "LLM provider [anthropic/openai] (default anthropic): " PROVIDER
    PROVIDER="${PROVIDER:-anthropic}"
    if [ "$PROVIDER" = "openai" ]; then
      set_env LLM_MODEL "openai:gpt-4o-mini"
      read -rsp "OPENAI_API_KEY: " KEY; echo; [ -n "$KEY" ] && set_env OPENAI_API_KEY "$KEY"
    else
      read -rsp "ANTHROPIC_API_KEY: " KEY; echo; [ -n "$KEY" ] && set_env ANTHROPIC_API_KEY "$KEY"
    fi
    read -rp "JIRA_URL (https://xxx.atlassian.net): " V; [ -n "$V" ] && set_env JIRA_URL "$V"
    read -rp "JIRA_EMAIL: " V;                          [ -n "$V" ] && set_env JIRA_EMAIL "$V"
    read -rsp "JIRA_API_TOKEN: " V; echo;                [ -n "$V" ] && set_env JIRA_API_TOKEN "$V"
    read -rp "AWS_REGION (default ap-south-1): " V;      [ -n "$V" ] && set_env AWS_REGION "$V"
    read -rsp "GITHUB_TOKEN (optional): " V; echo;       [ -n "$V" ] && set_env GITHUB_TOKEN "$V"
  else
    warn "Non-interactive shell: created .env from template. Edit it with: nano .env"
  fi
  echo ".env created (permissions 600)."
else
  echo ".env already exists — keeping it."
fi

# ---------------------------------------------------------------- 3. Build
step "[3/6] Building images (one per API + agent)"
$COMPOSE --profile cli build

# ---------------------------------------------------------------- 4. Start
step "[4/6] Starting 6 MCP server containers"
$COMPOSE up -d

# ---------------------------------------------------------------- 5. Health + tests
step "[5/6] Waiting for containers to become healthy"
for i in $(seq 1 45); do
  healthy=$($DOCKER ps --filter "name=mcp-" --filter "health=healthy" --format '{{.Names}}' | wc -l)
  [ "$healthy" -ge 6 ] && break
  sleep 2
done
$COMPOSE ps
[ "$healthy" -ge 6 ] || fail "Not all servers are healthy. Check: $COMPOSE logs"

echo -e "\nRunning smoke tests (no LLM needed)..."
$COMPOSE run --rm -T agent python test_servers.py || warn "Smoke test reported problems."

# ---------------------------------------------------------------- 6. IAM from container
step "[6/6] Checking the ec2 container can use the instance IAM role"
if $COMPOSE exec -T ec2 python -c \
   "import boto3; print(boto3.client('sts').get_caller_identity()['Arn'])" 2>/dev/null; then
  echo "IAM role reachable from containers ✅"
else
  TOKEN=$(curl -s -m 2 -X PUT "http://169.254.169.254/latest/api/token" \
          -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || true)
  IID=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $TOKEN" \
          http://169.254.169.254/latest/meta-data/instance-id || echo "<instance-id>")
  warn "Containers cannot get AWS credentials. Two common causes:"
  echo "  a) No IAM role attached -> EC2 console > Actions > Security > Modify IAM role"
  echo "  b) IMDSv2 hop limit is 1 (blocks containers). Fix from CloudShell/laptop:"
  echo "     aws ec2 modify-instance-metadata-options --instance-id $IID \\"
  echo "         --http-put-response-hop-limit 2 --http-endpoint enabled"
  echo "  Then: ./mcp.sh restart"
fi

cat <<MSG

$(echo -e "${GREEN}✅ Done! 6 MCP servers are running in Docker.${NC}")

  Chat with the agent : ./mcp.sh agent
  One question        : ./mcp.sh ask "convert 500 USD to INR"
  Status / logs       : ./mcp.sh status   |   ./mcp.sh logs ec2
  After editing .env  : ./mcp.sh restart
  All commands        : ./mcp.sh help
MSG
