#!/usr/bin/env bash
# =====================================================================
#  mcp.sh — day-to-day commands for the 6-server Docker stack
#
#    ./mcp.sh up                  build (if needed) + start all 6 MCP servers
#    ./mcp.sh down                stop and remove containers
#    ./mcp.sh status              container status + health
#    ./mcp.sh logs [name]         follow logs (all, or one server)
#    ./mcp.sh restart [name]      recreate containers (after editing .env)
#    ./mcp.sh rebuild [name]      rebuild image(s) + recreate (after editing code)
#    ./mcp.sh test                smoke-test all servers (no LLM needed)
#    ./mcp.sh agent               interactive chat with the agent
#    ./mcp.sh ask "question"      ask one question and exit
#    ./mcp.sh shell <name>        bash shell inside a container
#    ./mcp.sh clean               remove containers, network AND images
#
#  Server names: weather jira ec2 github currency wikipedia
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

if docker info >/dev/null 2>&1; then DOCKER="docker"; else DOCKER="sudo docker"; fi
COMPOSE="$DOCKER compose"
SERVERS=(weather jira ec2 github currency wikipedia)

need_env() {
  [ -f .env ] || { echo "❌ .env not found. Run: cp .env.example .env && nano .env"; exit 1; }
}

check_name() {
  local n="$1"
  for s in "${SERVERS[@]}" agent; do [ "$s" = "$n" ] && return 0; done
  echo "❌ Unknown service '$n'. Use one of: ${SERVERS[*]} agent"; exit 1
}

cmd="${1:-help}"; shift || true

case "$cmd" in
  up)
    need_env
    $COMPOSE up -d --build
    $COMPOSE ps
    ;;
  down)
    $COMPOSE down
    ;;
  status|ps)
    $COMPOSE ps
    ;;
  logs)
    if [ $# -gt 0 ]; then check_name "$1"; $COMPOSE logs -f --tail=100 "$1"
    else $COMPOSE logs -f --tail=30; fi
    ;;
  restart)
    need_env
    if [ $# -gt 0 ]; then check_name "$1"; $COMPOSE up -d --force-recreate "$1"
    else $COMPOSE up -d --force-recreate "${SERVERS[@]}"; fi
    $COMPOSE ps
    ;;
  rebuild)
    need_env
    if [ $# -gt 0 ]; then
      check_name "$1"
      $COMPOSE --profile cli build "$1"
      [ "$1" = agent ] || $COMPOSE up -d --force-recreate "$1"
    else
      $COMPOSE --profile cli build
      $COMPOSE up -d --force-recreate "${SERVERS[@]}"
    fi
    $COMPOSE ps
    ;;
  test)
    need_env
    $COMPOSE run --rm -T agent python test_servers.py
    ;;
  agent|chat)
    need_env
    $COMPOSE run --rm agent
    ;;
  ask)
    need_env
    [ $# -gt 0 ] || { echo 'Usage: ./mcp.sh ask "your question"'; exit 1; }
    $COMPOSE run --rm -T agent python agent.py "$*"
    ;;
  shell)
    [ $# -gt 0 ] || { echo "Usage: ./mcp.sh shell <name>"; exit 1; }
    check_name "$1"
    $COMPOSE exec "$1" bash
    ;;
  clean)
    $COMPOSE --profile cli down --remove-orphans
    for s in "${SERVERS[@]}" agent; do $DOCKER image rm "mcp-$s:latest" 2>/dev/null || true; done
    echo "Cleaned containers, network and images."
    ;;
  help|*)
    echo "Usage: ./mcp.sh <command>"
    sed -n '5,19p' "$0" | sed 's/^#//'
    ;;
esac
