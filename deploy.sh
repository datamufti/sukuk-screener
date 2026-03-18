#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh — Pull latest code and (re)deploy via Docker Compose
#
# Called by GitHub Actions over SSH, or manually:
#   cd ~/webapps/sukuk-screener && ./deploy.sh
# ---------------------------------------------------------------------------
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-$HOME/webapps/sukuk-screener}"
COMPOSE_FILE="docker-compose.prod.yml"

cd "$DEPLOY_DIR"

echo "──────────────────────────────────────"
echo "Deploying sukuk-screener"
echo "  Dir:  $DEPLOY_DIR"
echo "  Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "──────────────────────────────────────"

# Pull latest code
echo "→ Pulling latest from origin/main..."
git fetch --prune origin
git reset --hard origin/main

# Build and restart containers (minimal downtime)
echo "→ Building and restarting containers..."
docker compose -f "$COMPOSE_FILE" build --pull
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Clean up dangling images
echo "→ Pruning old images..."
docker image prune -f

# Wait for health check
echo "→ Waiting for health check..."
MAX_WAIT=60
WAITED=0
until docker inspect --format='{{.State.Health.Status}}' sukuk-screener 2>/dev/null | grep -q "healthy"; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "✗ Health check failed after ${MAX_WAIT}s"
        echo "  Logs:"
        docker compose -f "$COMPOSE_FILE" logs --tail=30 sukuk-screener
        exit 1
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "  …waiting (${WAITED}s)"
done

echo "✓ Deployed successfully — app is healthy"
echo "  Commit: $(git rev-parse --short HEAD)"
docker compose -f "$COMPOSE_FILE" ps
