#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# FinAgent — Deploy Script
# Run on your server: bash scripts/deploy.sh
#
# Usage:
#   First deploy:  bash scripts/deploy.sh
#   Update:        bash scripts/deploy.sh update
#   Stop all:      bash scripts/deploy.sh stop
#   View logs:     bash scripts/deploy.sh logs [service]
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

CMD="${1:-deploy}"

# ─── Helpers ─────────────────────────────────────────────────────────────────
check_deps() {
    command -v docker  >/dev/null 2>&1 || err "Docker not installed. Run: curl -fsSL https://get.docker.com | sh"
    command -v git     >/dev/null 2>&1 || err "Git not installed. Run: sudo apt install git -y"
    log "Dependencies OK"
}

check_env() {
    if [ ! -f ".env" ]; then
        warn ".env not found! Copying .env.example → .env"
        cp .env.example .env
        warn "⚠️  EDIT .env with your real values before continuing!"
        warn "   Required: SECRET_KEY, ADMIN_SECRET_KEY, POSTGRES_PASSWORD,"
        warn "             OPENROUTER_API_KEY, EVOLUTION_API_KEY, TELEGRAM_BOT_TOKEN"
        echo ""
        read -p "Press ENTER after editing .env to continue, or Ctrl+C to abort..."
    fi
    log ".env present"
}

check_ssl() {
    if [ ! -f "docker/ssl/fullchain.pem" ] || [ ! -f "docker/ssl/privkey.pem" ]; then
        warn "SSL certificates not found in docker/ssl/"
        warn "Generating self-signed certificate for testing..."
        mkdir -p docker/ssl
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout docker/ssl/privkey.pem \
            -out docker/ssl/fullchain.pem \
            -subj "/C=BR/ST=SP/L=SaoPaulo/O=FinAgent/CN=localhost" \
            2>/dev/null
        chmod 644 docker/ssl/fullchain.pem docker/ssl/privkey.pem
        warn "Self-signed cert created. Read docker/ssl/README.md for production SSL setup."
    else
        log "SSL certificates found"
    fi
}

# ─── Commands ─────────────────────────────────────────────────────────────────
deploy() {
    log "Starting FinAgent deploy..."
    check_deps
    check_env
    check_ssl

    log "Pulling latest images..."
    docker compose pull --quiet

    log "Building services..."
    docker compose build --quiet

    log "Starting all services..."
    docker compose up -d

    log "Waiting for database to be ready..."
    sleep 8

    log "Running database migrations..."
    docker compose exec -T backend alembic upgrade head

    echo ""
    log "════════════════════════════════════════"
    log "  FinAgent is up and running! 🚀"
    log "════════════════════════════════════════"
    echo ""
    echo "  Frontend:    https://your-ip-or-domain"
    echo "  Backend API: https://your-ip-or-domain/api/docs"
    echo "  Admin Panel: https://your-ip-or-domain/admin"
    echo ""
    echo "  Next steps:"
    echo "  1. Go to /admin and enter your ADMIN_SECRET_KEY"
    echo "  2. Go to WhatsApp → Connect and scan the QR Code"
    echo "  3. Go to Agents → Create your first agent"
    echo "  4. Assign the agent to your tenant"
    echo ""
    warn "Don't forget to create your first agent: bash scripts/seed_agent.py"
}

update() {
    log "Updating FinAgent..."
    check_deps
    check_env

    log "Pulling latest code..."
    git pull origin main

    log "Rebuilding changed services..."
    docker compose build --quiet backend frontend

    log "Restarting services..."
    docker compose up -d --no-deps backend frontend celery_worker celery_beat

    log "Running database migrations..."
    sleep 3
    docker compose exec -T backend alembic upgrade head

    log "Reload Nginx..."
    docker compose exec -T nginx nginx -s reload 2>/dev/null || true

    log "Update complete! ✅"
}

stop_all() {
    warn "Stopping all FinAgent services..."
    docker compose down
    log "All services stopped."
}

show_logs() {
    SERVICE="${2:-}"
    if [ -n "$SERVICE" ]; then
        docker compose logs -f --tail=100 "$SERVICE"
    else
        docker compose logs -f --tail=50
    fi
}

status() {
    echo ""
    docker compose ps
    echo ""
    log "Disk usage:"
    docker system df 2>/dev/null || true
}

# ─── Router ──────────────────────────────────────────────────────────────────
case "$CMD" in
    deploy|"")  deploy ;;
    update)     update ;;
    stop)       stop_all ;;
    logs)       show_logs "$@" ;;
    status)     status ;;
    *)
        echo "Usage: $0 {deploy|update|stop|logs [service]|status}"
        exit 1
        ;;
esac
