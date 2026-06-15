#!/usr/bin/env bash
set -euo pipefail

SERVER_HOST="${SERVER_HOST:-}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_PORT="${SERVER_PORT:-22}"
SERVER_DIR="${SERVER_DIR:-/opt/travel-any}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:6688/api/health}"

if [[ -z "$SERVER_HOST" ]]; then
  echo "请先设置 SERVER_HOST，例如：SERVER_HOST=1.2.3.4 $0"
  exit 1
fi

remote_dir=$(printf '%q' "$SERVER_DIR")
remote_branch=$(printf '%q' "$BRANCH")
remote_health=$(printf '%q' "$HEALTH_URL")

ssh -p "$SERVER_PORT" "$SERVER_USER@$SERVER_HOST" "set -euo pipefail
cd $remote_dir
git fetch origin
git checkout $remote_branch
git reset --hard origin/$remote_branch
docker compose $COMPOSE_FILES up -d --build --remove-orphans
docker compose $COMPOSE_FILES ps
curl -fsS $remote_health >/dev/null
echo 'sync ok'
"
