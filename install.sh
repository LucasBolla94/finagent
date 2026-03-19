#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  FinAgent — Instalador Automático
#  Uso: bash install.sh
#
#  O que este script faz automaticamente:
#   ✔ Instala Docker e Docker Compose (se não instalados)
#   ✔ Gera SECRET_KEY, POSTGRES_PASSWORD, EVOLUTION_API_KEY automaticamente
#   ✔ Pergunta só o que você PRECISA informar (OpenRouter key + senha admin)
#   ✔ Configura o .env completo
#   ✔ Atualiza o nginx.conf com seu domínio
#   ✔ Obtém certificado SSL via Let's Encrypt (ou self-signed como fallback)
#   ✔ Sobe todos os containers
#   ✔ Roda as migrations do banco
#   ✔ Verifica se tudo está funcionando
#
#  Compatível com: Ubuntu 20.04/22.04/24.04, Debian 10/11/12
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Helpers ──────────────────────────────────────────────────────────────────
log()     { echo -e "${GREEN}${BOLD}[✔]${NC} $1"; }
info()    { echo -e "${CYAN}[→]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
err()     { echo -e "${RED}${BOLD}[✗] ERRO:${NC} $1"; exit 1; }
header()  { echo -e "\n${BLUE}${BOLD}══════════════════════════════════════${NC}"; echo -e "${BLUE}${BOLD}  $1${NC}"; echo -e "${BLUE}${BOLD}══════════════════════════════════════${NC}\n"; }
ask()     { echo -e "${YELLOW}${BOLD}[?]${NC} $1"; }
divider() { echo -e "${BLUE}──────────────────────────────────────${NC}"; }

gen_secret() { openssl rand -hex 32; }
gen_pass()   { openssl rand -base64 20 | tr -dc 'a-zA-Z0-9' | head -c 20; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Banner ───────────────────────────────────────────────────────────────────
clear
echo -e "${BOLD}"
echo "  ███████╗██╗███╗   ██╗ █████╗  ██████╗ ███████╗███╗   ██╗████████╗"
echo "  ██╔════╝██║████╗  ██║██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝"
echo "  █████╗  ██║██╔██╗ ██║███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   "
echo "  ██╔══╝  ██║██║╚██╗██║██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   "
echo "  ██║     ██║██║ ╚████║██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   "
echo "  ╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   "
echo -e "${NC}"
echo -e "${CYAN}  Assistente Financeiro com AI — Instalador Automático${NC}"
echo -e "${CYAN}  v2.0 · finance.bolla.network${NC}"
echo ""
divider

# ─── Step 1: Check root ───────────────────────────────────────────────────────
header "1/8 — Verificando permissões"
if [ "$EUID" -ne 0 ]; then
    warn "Não está rodando como root."
    info "Tentando com sudo quando necessário..."
    SUDO="sudo"
else
    SUDO=""
    log "Rodando como root"
fi

# ─── Step 2: Install dependencies ─────────────────────────────────────────────
header "2/8 — Instalando dependências"

install_docker() {
    info "Instalando Docker..."
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq ca-certificates curl gnupg lsb-release
    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
        | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    $SUDO systemctl enable docker
    $SUDO systemctl start docker
    # Allow current user to run docker without sudo
    $SUDO usermod -aG docker "$USER" 2>/dev/null || true
    log "Docker instalado com sucesso"
}

if ! command -v docker &>/dev/null; then
    install_docker
else
    DOCKER_VER=$(docker --version | cut -d' ' -f3 | tr -d ',')
    log "Docker já instalado: $DOCKER_VER"
fi

if ! docker compose version &>/dev/null 2>&1; then
    info "Instalando Docker Compose plugin..."
    $SUDO apt-get install -y -qq docker-compose-plugin
    log "Docker Compose instalado"
else
    log "Docker Compose já instalado"
fi

for pkg in git curl openssl; do
    if ! command -v $pkg &>/dev/null; then
        info "Instalando $pkg..."
        $SUDO apt-get install -y -qq $pkg
    fi
    log "$pkg OK"
done

# ─── Step 3: Domain & email configuration ─────────────────────────────────────
header "3/8 — Configuração do domínio"

# Default domain
DEFAULT_DOMAIN="finance.bolla.network"
DEFAULT_EMAIL="lucasbolla@icloud.com"

ask "Qual é o domínio do servidor? (Enter para usar: $DEFAULT_DOMAIN)"
read -r INPUT_DOMAIN
DOMAIN="${INPUT_DOMAIN:-$DEFAULT_DOMAIN}"

ask "Email para o certificado SSL Let's Encrypt? (Enter para usar: $DEFAULT_EMAIL)"
read -r INPUT_EMAIL
SSL_EMAIL="${INPUT_EMAIL:-$DEFAULT_EMAIL}"

log "Domínio: $DOMAIN"
log "Email SSL: $SSL_EMAIL"

# ─── Step 4: Collect required secrets ─────────────────────────────────────────
header "4/8 — Configuração das chaves"

echo ""
echo -e "${YELLOW}${BOLD}  Você precisa informar APENAS 2 coisas:${NC}"
echo -e "  ${CYAN}1. Chave do OpenRouter${NC} — obtenha em: https://openrouter.ai/keys"
echo -e "  ${CYAN}2. Senha do painel Admin${NC} — qualquer senha forte"
echo ""

# OpenRouter key
while true; do
    ask "Cole sua OPENROUTER_API_KEY (sk-or-v1-...):"
    read -r OPENROUTER_KEY
    if [[ "$OPENROUTER_KEY" == sk-or-v1-* ]] || [[ ${#OPENROUTER_KEY} -gt 20 ]]; then
        log "Chave OpenRouter configurada"
        break
    else
        warn "Parece inválida (deve começar com sk-or-v1-). Tente novamente."
    fi
done

# Admin password
while true; do
    ask "Crie uma senha para o painel Admin (mín. 8 caracteres):"
    read -rs ADMIN_PASS
    echo ""
    if [ ${#ADMIN_PASS} -ge 8 ]; then
        log "Senha admin configurada"
        break
    else
        warn "Senha muito curta. Use pelo menos 8 caracteres."
    fi
done

# Generate all other secrets automatically
SECRET_KEY=$(gen_secret)
DB_PASS=$(gen_pass)
EVOLUTION_KEY=$(gen_pass)

log "Chaves geradas automaticamente:"
info "  SECRET_KEY:          (gerada)"
info "  POSTGRES_PASSWORD:   (gerada)"
info "  EVOLUTION_API_KEY:   (gerada)"

# ─── Step 5: Write .env ───────────────────────────────────────────────────────
header "5/8 — Criando arquivo .env"

cat > .env << EOF
# ─────────────────────────────────────────────────────────────────────────────
# FinAgent — Produção
# Gerado automaticamente por install.sh em $(date)
# ─────────────────────────────────────────────────────────────────────────────

# App
SECRET_KEY=${SECRET_KEY}
DEBUG=false
ADMIN_SECRET_KEY=${ADMIN_PASS}

# Public URLs
BACKEND_PUBLIC_URL=https://${DOMAIN}
NEXT_PUBLIC_API_URL=https://${DOMAIN}
FRONTEND_URL=https://${DOMAIN}
CORS_ORIGINS=["https://${DOMAIN}"]

# Database
POSTGRES_USER=finagent
POSTGRES_PASSWORD=${DB_PASS}
POSTGRES_DB=finagent
DATABASE_URL=postgresql+asyncpg://finagent:${DB_PASS}@postgres:5432/finagent

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# OpenRouter (AI)
OPENROUTER_API_KEY=${OPENROUTER_KEY}

# Evolution API (WhatsApp)
EVOLUTION_API_URL=http://evolution_api:8080
EVOLUTION_API_KEY=${EVOLUTION_KEY}
EVOLUTION_INSTANCE_NAME=finagent_agent1

# Telegram (optional)
TELEGRAM_BOT_TOKEN=

# Models (optional overrides)
# MODEL_FAST=google/gemini-flash-1.5
# MODEL_STANDARD=anthropic/claude-haiku-4
# MODEL_POWERFUL=anthropic/claude-sonnet-4-5
EOF

chmod 600 .env
log ".env criado com sucesso (permissões 600)"

# ─── Step 6: Configure Nginx with domain ─────────────────────────────────────
header "6/8 — Configurando Nginx"

# Update nginx.conf server_name with actual domain
sed -i "s/server_name _;/server_name ${DOMAIN};/g" docker/nginx.conf 2>/dev/null || true
# Ensure server_name is set on both HTTP and HTTPS blocks
sed -i "s|server_name _.*# Replace with your domain.*|server_name ${DOMAIN};|" docker/nginx.conf 2>/dev/null || true
log "Nginx configurado para: $DOMAIN"

# ─── Step 7: SSL Certificate ──────────────────────────────────────────────────
header "7/8 — Certificado SSL"

mkdir -p docker/ssl

obtain_letsencrypt() {
    info "Tentando obter certificado Let's Encrypt para $DOMAIN..."

    # Install certbot if not present
    if ! command -v certbot &>/dev/null; then
        info "Instalando certbot..."
        $SUDO apt-get install -y -qq certbot
    fi

    # Temporarily start nginx HTTP-only to serve ACME challenge
    # We'll use standalone mode so we don't need nginx running
    $SUDO certbot certonly \
        --standalone \
        --non-interactive \
        --agree-tos \
        --email "$SSL_EMAIL" \
        -d "$DOMAIN" \
        --preferred-challenges http \
        2>/dev/null

    if [ $? -eq 0 ]; then
        CERT_PATH="/etc/letsencrypt/live/${DOMAIN}"
        $SUDO cp "${CERT_PATH}/fullchain.pem" docker/ssl/fullchain.pem
        $SUDO cp "${CERT_PATH}/privkey.pem"   docker/ssl/privkey.pem
        $SUDO chmod 644 docker/ssl/fullchain.pem docker/ssl/privkey.pem
        log "Certificado Let's Encrypt obtido para $DOMAIN ✅"

        # Add auto-renewal cron
        if ! $SUDO crontab -l 2>/dev/null | grep -q "certbot renew"; then
            ($SUDO crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'cp /etc/letsencrypt/live/${DOMAIN}/*.pem $(pwd)/docker/ssl/ && docker compose -f $(pwd)/docker-compose.yml exec nginx nginx -s reload'") | $SUDO crontab -
            log "Auto-renovação SSL configurada (cron diário às 3h)"
        fi
        return 0
    else
        return 1
    fi
}

generate_self_signed() {
    warn "Usando certificado self-signed (HTTPS com aviso no browser)"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout docker/ssl/privkey.pem \
        -out docker/ssl/fullchain.pem \
        -subj "/C=BR/ST=SP/L=SaoPaulo/O=FinAgent/CN=${DOMAIN}" \
        2>/dev/null
    chmod 644 docker/ssl/*.pem
    log "Certificado self-signed gerado"
}

# Try Let's Encrypt first (only if port 80 is free)
SSL_METHOD="selfsigned"
if [ ! -f "docker/ssl/fullchain.pem" ]; then
    # Check if port 80 is available for ACME challenge
    if ! ss -tlnp 2>/dev/null | grep -q ':80 ' && ! netstat -tlnp 2>/dev/null | grep -q ':80 '; then
        info "Porta 80 disponível — tentando Let's Encrypt..."
        if obtain_letsencrypt; then
            SSL_METHOD="letsencrypt"
        else
            warn "Let's Encrypt falhou (domínio pode não apontar para este IP ainda)"
            generate_self_signed
        fi
    else
        warn "Porta 80 em uso — usando self-signed por agora"
        warn "Após o deploy, rode: bash scripts/ssl-renew.sh"
        generate_self_signed
    fi
else
    log "Certificado SSL já existe"
    SSL_METHOD="existing"
fi

# ─── Step 8: Start services ───────────────────────────────────────────────────
header "8/8 — Iniciando serviços"

info "Fazendo pull das imagens Docker..."
docker compose pull --quiet 2>/dev/null || true

info "Fazendo build dos containers..."
docker compose build --quiet

info "Iniciando todos os serviços..."
docker compose up -d

# Wait for services to be healthy
info "Aguardando banco de dados ficar pronto..."
MAX_RETRIES=30
RETRY=0
until docker compose exec -T postgres pg_isready -U finagent -q 2>/dev/null; do
    RETRY=$((RETRY+1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        err "Banco de dados não ficou pronto em tempo. Veja: docker compose logs postgres"
    fi
    sleep 2
done
log "PostgreSQL pronto"

info "Rodando migrations do banco..."
docker compose exec -T backend alembic upgrade head
log "Migrations concluídas"

# Verify backend is responding
info "Verificando saúde da API..."
RETRY=0
until curl -sf "http://localhost:8000/health" >/dev/null 2>&1; do
    RETRY=$((RETRY+1))
    if [ $RETRY -ge 20 ]; then
        warn "API não respondeu no tempo esperado (pode ainda estar inicializando)"
        break
    fi
    sleep 3
done

if curl -sf "http://localhost:8000/health" >/dev/null 2>&1; then
    log "API respondendo"
fi

# ─── Done! ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║        FinAgent instalado com sucesso! 🚀            ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

divider
echo -e "${BOLD}  URLs:${NC}"
echo -e "  ${CYAN}🌐 Sistema:${NC}       https://${DOMAIN}"
echo -e "  ${CYAN}🔑 Admin Panel:${NC}   https://${DOMAIN}/admin"
echo -e "  ${CYAN}📚 API Docs:${NC}      https://${DOMAIN}/api/docs"
echo ""
echo -e "${BOLD}  Credenciais:${NC}"
echo -e "  ${CYAN}Admin senha:${NC}      ${ADMIN_PASS}"
echo -e "  ${CYAN}DB senha:${NC}         ${DB_PASS} (salvo no .env)"
echo ""
echo -e "${BOLD}  SSL:${NC}             ${SSL_METHOD}"
divider
echo ""
echo -e "${YELLOW}${BOLD}  Próximos passos:${NC}"
echo -e "  ${BOLD}1.${NC} Acesse https://${DOMAIN}/admin"
echo -e "  ${BOLD}2.${NC} Faça login com a senha admin"
echo -e "  ${BOLD}3.${NC} Vá em WhatsApp → Conectar WhatsApp → Escaneie o QR Code"
echo -e "  ${BOLD}4.${NC} Vá em Agentes → Criar Agente"
echo -e "  ${BOLD}5.${NC} Vá em Clientes → Atribuir agente ao cliente"
echo ""
if [ "$SSL_METHOD" = "selfsigned" ]; then
    echo -e "${YELLOW}  ⚠️  SSL self-signed: o browser mostrará aviso.${NC}"
    echo -e "${YELLOW}     Para SSL real, garanta que DNS aponte para este IP e rode:${NC}"
    echo -e "${YELLOW}     bash scripts/ssl-renew.sh${NC}"
    echo ""
fi
echo -e "${BOLD}  Comandos úteis:${NC}"
echo -e "  ${CYAN}Ver logs:${NC}         docker compose logs -f backend"
echo -e "  ${CYAN}Status:${NC}           docker compose ps"
echo -e "  ${CYAN}Atualizar:${NC}        bash scripts/deploy.sh update"
echo -e "  ${CYAN}Parar:${NC}            docker compose down"
echo ""
divider
echo ""

# Save install summary
cat > .install-summary.txt << SUMMARY
FinAgent Install Summary
========================
Date: $(date)
Domain: ${DOMAIN}
SSL: ${SSL_METHOD}
Admin URL: https://${DOMAIN}/admin
Admin Password: ${ADMIN_PASS}
DB Password: ${DB_PASS}
Evolution Key: ${EVOLUTION_KEY}
SUMMARY
chmod 600 .install-summary.txt
log "Resumo salvo em .install-summary.txt"
