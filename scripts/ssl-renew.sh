#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# FinAgent — Obter/Renovar Certificado SSL Let's Encrypt
# Uso: bash scripts/ssl-renew.sh [dominio] [email]
#
# Quando usar:
#   - Após instalar com self-signed e querer SSL real
#   - Renovação manual do certificado
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'
log()  { echo -e "${GREEN}${BOLD}[✔]${NC} $1"; }
info() { echo -e "${CYAN}[→]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}${BOLD}[✗]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# Load domain from .env if not provided
if [ -f ".env" ]; then
    DOMAIN_FROM_ENV=$(grep "BACKEND_PUBLIC_URL" .env | sed 's/.*https:\/\///' | tr -d '"' | tr -d "'")
else
    DOMAIN_FROM_ENV=""
fi

DOMAIN="${1:-${DOMAIN_FROM_ENV:-finance.bolla.network}}"
EMAIL="${2:-lucasbolla@icloud.com}"

echo ""
echo -e "${BOLD}  SSL Let's Encrypt — FinAgent${NC}"
echo -e "  Domínio: ${CYAN}${DOMAIN}${NC}"
echo -e "  Email:   ${CYAN}${EMAIL}${NC}"
echo ""

# Check certbot
if ! command -v certbot &>/dev/null; then
    info "Instalando certbot..."
    sudo apt-get install -y -qq certbot
    log "certbot instalado"
fi

# Stop nginx to free port 80
info "Parando Nginx para liberar porta 80..."
docker compose stop nginx 2>/dev/null || true
sleep 2

# Obtain certificate
info "Obtendo certificado para $DOMAIN..."
sudo certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    -d "$DOMAIN" \
    --preferred-challenges http

CERT_PATH="/etc/letsencrypt/live/${DOMAIN}"

# Copy to project
info "Copiando certificados..."
mkdir -p docker/ssl
sudo cp "${CERT_PATH}/fullchain.pem" docker/ssl/fullchain.pem
sudo cp "${CERT_PATH}/privkey.pem"   docker/ssl/privkey.pem
sudo chmod 644 docker/ssl/fullchain.pem docker/ssl/privkey.pem
log "Certificados copiados para docker/ssl/"

# Restart nginx
info "Reiniciando Nginx..."
docker compose start nginx 2>/dev/null || docker compose up -d nginx
log "Nginx reiniciado"

# Add auto-renewal cron
if ! sudo crontab -l 2>/dev/null | grep -q "certbot renew"; then
    RENEW_CMD="certbot renew --quiet --post-hook 'cp /etc/letsencrypt/live/${DOMAIN}/*.pem ${SCRIPT_DIR}/docker/ssl/ && docker compose -f ${SCRIPT_DIR}/docker-compose.yml exec nginx nginx -s reload'"
    (sudo crontab -l 2>/dev/null; echo "0 3 * * * $RENEW_CMD") | sudo crontab -
    log "Auto-renovação SSL configurada (todos os dias às 3h)"
fi

echo ""
log "SSL Let's Encrypt configurado com sucesso para ${DOMAIN}! ✅"
echo ""
echo -e "  ${CYAN}Teste:${NC} curl -I https://${DOMAIN}/health"
echo ""
