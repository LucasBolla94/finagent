#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  FinAgent — Instalador / Atualizador Automático
#  Uso: bash install.sh
#
#  INSTALL (primeira vez):
#   Instala Docker, gera segredos, configura .env, SSL, sobe containers
#
#  UPDATE (sistema já instalado — detectado automaticamente):
#   git pull, rebuild seletivo, migrations, restart sem perda de dados
#
#  Compatível com: Ubuntu 20.04/22.04/24.04, Debian 10/11/12
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()     { echo -e "${GREEN}${BOLD}[OK]${NC} $1"; }
info()    { echo -e "${CYAN}[->]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
err()     { echo -e "${RED}${BOLD}[ERRO]${NC} $1"; exit 1; }
header()  { echo -e "\n${BLUE}${BOLD}== $1 ==${NC}\n"; }
divider() { echo -e "${BLUE}------------------------------------------${NC}"; }
ok_skip() { echo -e "${GREEN}[OK]${NC} $1 ${CYAN}(existente - mantido)${NC}"; }

gen_secret() { openssl rand -hex 32; }
gen_pass()   { openssl rand -base64 20 | tr -dc 'a-zA-Z0-9' | head -c 20; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Leitura segura de senha (funciona em terminal E em pipe/automacao) ────────
# Uso: VALUE=$(read_secret "Prompt" "NOME_ENV_VAR")
# Se a env var NOME_ENV_VAR existir, usa ela (bom para CI/pipe).
# Em terminal: esconde a digitacao com stty.
# Em pipe/nao-interativo: le normalmente do stdin.
read_secret() {
    local prompt="$1"
    local envvar="${2:-}"
    local value=""

    # Prioridade 1: variavel de ambiente (CI, automacao, pipe)
    if [ -n "$envvar" ] && [ -n "${!envvar:-}" ]; then
        value="${!envvar}"
        info "Usando ${envvar} do ambiente"
        printf '%s' "$value"
        return
    fi

    # Prioridade 2: terminal interativo - oculta a digitacao
    if [ -t 0 ]; then
        printf '%b' "${YELLOW}${BOLD}[?]${NC} ${prompt}: " >&2
        local saved_tty
        saved_tty=$(stty -g 2>/dev/null || echo "")
        stty -echo 2>/dev/null || true
        IFS= read -r value </dev/tty || true
        if [ -n "$saved_tty" ]; then
            stty "$saved_tty" 2>/dev/null || true
        else
            stty echo 2>/dev/null || true
        fi
        echo "" >&2
    else
        # Prioridade 3: stdin nao-interativo (pipe)
        IFS= read -r value || true
    fi

    printf '%s' "$value"
}

# ─── Banner ───────────────────────────────────────────────────────────────────
clear 2>/dev/null || true
echo -e "${BOLD}"
echo "  ███████╗██╗███╗   ██╗ █████╗  ██████╗ ███████╗███╗   ██╗████████╗"
echo "  ██╔════╝██║████╗  ██║██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝"
echo "  █████╗  ██║██╔██╗ ██║███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   "
echo "  ██╔══╝  ██║██║╚██╗██║██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   "
echo "  ██║     ██║██║ ╚████║██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   "
echo "  ╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   "
echo -e "${NC}"
echo -e "${CYAN}  Assistente Financeiro com AI — v2.1${NC}"
echo -e "${CYAN}  Instalador Inteligente (Install + Update)${NC}"
echo ""; divider

# ─── Sudo ─────────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    warn "Nao e root. Usando sudo quando necessario."
    SUDO="sudo"
else
    SUDO=""
fi

# ═══════════════════════════════════════════════════════════════════════════════
#  DETECCAO DO MODO: INSTALL ou UPDATE
# ═══════════════════════════════════════════════════════════════════════════════
detect_mode() {
    # Considera UPDATE se:
    #  (a) .env tem o marker FINAGENT_INSTALLED=true, OU
    #  (b) .env existe E containers estao rodando
    local has_env=false has_marker=false has_containers=false

    [ -f ".env" ]                                          && has_env=true
    grep -q "FINAGENT_INSTALLED=true" ".env" 2>/dev/null   && has_marker=true

    if command -v docker &>/dev/null; then
        docker compose ps 2>/dev/null | grep -qE "running|Up" && has_containers=true
    fi

    if $has_marker || ( $has_env && $has_containers ); then
        echo "update"
    else
        echo "install"
    fi
}

MODE=$(detect_mode)

if [ "$MODE" = "update" ]; then
    echo -e "${GREEN}${BOLD}  Instalacao existente detectada - Modo UPDATE${NC}"
    echo -e "${CYAN}  Seus dados e configuracoes serao preservados.${NC}"
else
    echo -e "${BLUE}${BOLD}  Nenhuma instalacao encontrada - Modo INSTALL${NC}"
    echo -e "${CYAN}  Configuracao completa do zero.${NC}"
fi
echo ""; divider

# ═══════════════════════════════════════════════════════════════════════════════
#  FUNCOES COMPARTILHADAS
# ═══════════════════════════════════════════════════════════════════════════════

install_docker() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        ok_skip "Docker e Docker Compose"; return
    fi
    info "Instalando Docker..."
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq ca-certificates curl gnupg lsb-release
    $SUDO install -m 0755 -d /etc/apt/keyrings
    local OS_ID; OS_ID=$(. /etc/os-release && echo "$ID")
    curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" | \
        $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${OS_ID} $(lsb_release -cs) stable" | \
        $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    $SUDO systemctl enable docker --now
    log "Docker instalado"
}

setup_ssl() {
    local domain="$1" email="$2"
    mkdir -p ./docker/ssl

    # Reutiliza cert valido por mais de 7 dias
    if [ -f "./docker/ssl/fullchain.pem" ] && [ -f "./docker/ssl/privkey.pem" ]; then
        if openssl x509 -checkend 604800 -noout -in ./docker/ssl/fullchain.pem 2>/dev/null; then
            ok_skip "Certificado SSL (valido por mais de 7 dias)"; return
        fi
        warn "Certificado proximo do vencimento. Renovando..."
    fi

    info "Tentando Let's Encrypt para ${domain}..."
    if $SUDO apt-get install -y -qq certbot 2>/dev/null && \
       $SUDO certbot certonly --standalone --non-interactive --agree-tos \
           --email "$email" -d "$domain" 2>/dev/null; then
        $SUDO cp "/etc/letsencrypt/live/${domain}/fullchain.pem" ./docker/ssl/fullchain.pem
        $SUDO cp "/etc/letsencrypt/live/${domain}/privkey.pem"   ./docker/ssl/privkey.pem
        $SUDO chmod 644 ./docker/ssl/fullchain.pem ./docker/ssl/privkey.pem
        log "Certificado Let's Encrypt obtido"
        if ! crontab -l 2>/dev/null | grep -q "ssl-renew.sh"; then
            (crontab -l 2>/dev/null; \
             echo "0 3 * * 1 bash ${SCRIPT_DIR}/scripts/ssl-renew.sh >> /var/log/finagent-ssl.log 2>&1") \
             | crontab -
            log "Renovacao SSL automatica configurada (segunda-feira 3h)"
        fi
    else
        warn "Let's Encrypt falhou. Gerando certificado self-signed..."
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout ./docker/ssl/privkey.pem \
            -out    ./docker/ssl/fullchain.pem \
            -subj "/C=BR/ST=SP/L=SaoPaulo/O=FinAgent/CN=${domain}" 2>/dev/null
        warn "AVISO: Certificado self-signed gerado. Substitua por Let's Encrypt em producao."
    fi
}

wait_healthy() {
    local container="$1" max="${2:-30}" i=0
    info "Aguardando ${container} ficar saudavel..."
    while [ $i -lt $max ]; do
        local st; st=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "")
        [ "$st" = "healthy" ] && { log "${container} OK"; return 0; }
        sleep 3; i=$((i+1)); printf '.'
    done
    echo ""
    warn "${container} demorou para responder. Verifique: docker logs ${container}"
}

update_nginx_domain() {
    local domain="$1"
    if grep -q "finance\.bolla\.network" ./docker/nginx.conf 2>/dev/null; then
        sed -i "s/finance\.bolla\.network/${domain}/g" ./docker/nginx.conf
        log "nginx.conf atualizado: server_name ${domain}"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
#  MODO UPDATE
# ═══════════════════════════════════════════════════════════════════════════════
run_update() {
    header "Atualizando FinAgent"

    # Carrega variaveis do .env existente
    set -a
    # shellcheck disable=SC1091
    source .env 2>/dev/null || true
    set +a
    DOMAIN="${DOMAIN:-finance.bolla.network}"

    info "Dominio: ${DOMAIN}"
    info "Branch:  $(git branch --show-current 2>/dev/null || echo 'n/a')"
    echo ""

    # -- 1. Git pull -----------------------------------------------------------
    header "1/5 - Buscando atualizacoes"
    OLD_HASH=""
    CHANGED_FILES=""

    if git remote get-url origin &>/dev/null; then
        OLD_HASH=$(git rev-parse HEAD 2>/dev/null || echo "")
        git fetch origin 2>/dev/null || warn "git fetch falhou (sem rede?)"

        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse "@{u}" 2>/dev/null || echo "$LOCAL")

        if [ "$LOCAL" = "$REMOTE" ]; then
            log "Codigo ja esta na versao mais recente"
        else
            git pull --rebase origin "$(git branch --show-current)" 2>/dev/null
            NEW_HASH=$(git rev-parse HEAD)
            CHANGED_FILES=$(git diff --name-only "$OLD_HASH" "$NEW_HASH" 2>/dev/null || echo "")
            log "Atualizado: $(git log --oneline -1)"
            if [ -n "$CHANGED_FILES" ]; then
                info "Arquivos modificados:"
                echo "$CHANGED_FILES" | head -15 | sed 's/^/   - /'
            fi
        fi
    else
        warn "Sem remote git. Pulando git pull."
    fi

    # -- 2. Rebuild seletivo ---------------------------------------------------
    header "2/5 - Rebuild dos containers"
    REBUILD_LIST=""

    needs_rebuild() {
        local svc="$1" prefix="$2"
        # Reconstroi se: sem info de mudancas, OU se prefix foi modificado
        if [ -z "$CHANGED_FILES" ] || echo "$CHANGED_FILES" | grep -q "^${prefix}"; then
            REBUILD_LIST="${REBUILD_LIST} ${svc}"
            info "Reconstruindo: ${svc}"
        else
            ok_skip "$svc"
        fi
    }

    needs_rebuild "backend"       "backend/"
    needs_rebuild "celery_worker" "backend/"
    needs_rebuild "celery_beat"   "backend/"
    needs_rebuild "frontend"      "frontend/"

    if [ -n "${REBUILD_LIST# }" ]; then
        info "Build:${REBUILD_LIST}..."
        # shellcheck disable=SC2086
        docker compose build --parallel ${REBUILD_LIST}
        log "Build concluido"
    else
        log "Nenhum container precisa ser reconstruido"
    fi

    # -- 3. Migrations ---------------------------------------------------------
    header "3/5 - Migrations"
    docker compose run --rm backend alembic upgrade head
    log "Migrations aplicadas"

    # -- 4. Restart seletivo ---------------------------------------------------
    header "4/5 - Reiniciando servicos"
    if [ -n "${REBUILD_LIST# }" ]; then
        # shellcheck disable=SC2086
        docker compose up -d --no-deps ${REBUILD_LIST}
        log "Reiniciados:${REBUILD_LIST}"
    else
        info "Nenhum servico precisou reiniciar"
    fi

    # -- 5. Verificacao --------------------------------------------------------
    header "5/5 - Verificacao"
    sleep 5

    if curl -sf --max-time 10 "https://${DOMAIN}/health" -o /dev/null 2>/dev/null; then
        log "API respondendo em https://${DOMAIN}/health"
    else
        warn "API nao respondeu. Verifique: docker compose logs backend"
    fi

    RUNNING=$(docker compose ps 2>/dev/null | grep -cE "running|Up" || echo "?")
    log "${RUNNING} containers rodando"

    # Atualiza timestamp
    if grep -q "LAST_UPDATE=" .env 2>/dev/null; then
        sed -i "s/LAST_UPDATE=.*/LAST_UPDATE=$(date +%Y-%m-%dT%H:%M:%S)/" .env
    else
        echo "LAST_UPDATE=$(date +%Y-%m-%dT%H:%M:%S)" >> .env
    fi

    echo ""; divider
    echo -e "\n${GREEN}${BOLD}  [OK] FinAgent atualizado com sucesso!${NC}\n"
    echo -e "  Painel:  ${CYAN}https://${DOMAIN}/admin${NC}"
    echo -e "  API:     ${CYAN}https://${DOMAIN}/api/docs${NC}"
    echo -e "  Logs:    ${CYAN}docker compose logs -f${NC}"
    echo ""; divider
}

# ═══════════════════════════════════════════════════════════════════════════════
#  MODO INSTALL (primeira vez)
# ═══════════════════════════════════════════════════════════════════════════════
run_install() {

    # -- 1. Docker -------------------------------------------------------------
    header "1/8 - Instalando dependencias"
    install_docker

    # -- 2. Configuracao -------------------------------------------------------
    header "2/8 - Configuracao inicial"
    echo -e "${CYAN}Precisamos de poucas informacoes para configurar tudo:${NC}\n"

    # Dominio
    if [ -t 0 ]; then
        printf '%b' "${YELLOW}${BOLD}[?]${NC} Dominio [finance.bolla.network]: "
        IFS= read -r DOMAIN </dev/tty || true
    fi
    DOMAIN="${DOMAIN:-finance.bolla.network}"
    log "Dominio: ${DOMAIN}"

    # Email SSL
    if [ -t 0 ]; then
        printf '%b' "${YELLOW}${BOLD}[?]${NC} E-mail para SSL [admin@${DOMAIN}]: "
        IFS= read -r ADMIN_EMAIL </dev/tty || true
    fi
    ADMIN_EMAIL="${ADMIN_EMAIL:-admin@${DOMAIN}}"
    log "E-mail SSL: ${ADMIN_EMAIL}"

    # OpenRouter key
    echo -e "\n  ${CYAN}Obtenha sua chave gratis: https://openrouter.ai/keys${NC}"
    OPENROUTER_KEY=$(read_secret "OpenRouter API Key (sk-or-v1-...)" "OPENROUTER_API_KEY")
    [ -z "$OPENROUTER_KEY" ] && err "OpenRouter API Key e obrigatoria."
    log "OpenRouter key configurada"

    # Senha admin
    echo -e "\n  ${CYAN}Senha para o painel admin (minimo 8 caracteres)${NC}"
    ADMIN_PASSWORD=$(read_secret "Senha do Admin" "ADMIN_API_KEY")
    [ "${#ADMIN_PASSWORD}" -lt 8 ] && err "Senha deve ter pelo menos 8 caracteres."
    log "Senha admin configurada"
    echo ""; divider

    # -- 3. Segredos -----------------------------------------------------------
    header "3/8 - Gerando segredos"
    SECRET_KEY=$(gen_secret)
    POSTGRES_PASSWORD=$(gen_pass)
    EVOLUTION_API_KEY=$(gen_secret)
    log "SECRET_KEY, POSTGRES_PASSWORD, EVOLUTION_API_KEY gerados"

    # -- 4. .env ---------------------------------------------------------------
    header "4/8 - Criando .env"
    cat > .env <<ENVEOF
# FinAgent - Environment Variables
# Gerado automaticamente em $(date)
# NAO commite este arquivo no git
FINAGENT_INSTALLED=true
INSTALL_DATE=$(date +%Y-%m-%dT%H:%M:%S)
LAST_UPDATE=$(date +%Y-%m-%dT%H:%M:%S)

# Dominio e URLs publicas
DOMAIN=${DOMAIN}
BACKEND_PUBLIC_URL=https://${DOMAIN}
NEXT_PUBLIC_API_URL=https://${DOMAIN}

# CORS: URLs que podem chamar a API. Inclui o dominio de producao e localhost.
# O frontend Next.js usa o mesmo dominio que o backend (via Nginx), entao e same-origin.
CORS_ORIGINS=https://${DOMAIN},http://localhost:3000,http://localhost:8000

# App
SECRET_KEY=${SECRET_KEY}
ADMIN_API_KEY=${ADMIN_PASSWORD}
DEBUG=false
ENVIRONMENT=production

# Database
POSTGRES_USER=finagent
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=finagent
DATABASE_URL=postgresql+asyncpg://finagent:${POSTGRES_PASSWORD}@postgres:5432/finagent

# Redis / Celery
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# AI
OPENROUTER_API_KEY=${OPENROUTER_KEY}
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEFAULT_MODEL=anthropic/claude-3.5-haiku

# Evolution API (WhatsApp)
EVOLUTION_API_URL=http://evolution_api:8080
EVOLUTION_API_KEY=${EVOLUTION_API_KEY}
EVOLUTION_INSTANCE_NAME=finagent
ENVEOF
    log ".env criado"

    # -- 5. Nginx --------------------------------------------------------------
    header "5/8 - Configurando Nginx"
    update_nginx_domain "$DOMAIN"

    # -- 6. SSL ----------------------------------------------------------------
    header "6/8 - Certificado SSL"
    setup_ssl "$DOMAIN" "$ADMIN_EMAIL"

    # -- 7. Containers ---------------------------------------------------------
    header "7/8 - Subindo containers"
    info "Build das imagens (pode demorar na primeira vez)..."
    docker compose build --parallel

    info "Iniciando todos os servicos..."
    docker compose up -d

    info "Aguardando PostgreSQL..."
    wait_healthy "finagent_postgres" 30

    info "Rodando migrations do banco..."
    sleep 5
    docker compose run --rm backend alembic upgrade head
    log "Migrations aplicadas"

    info "Aguardando API ficar disponivel..."
    for i in $(seq 1 20); do
        curl -sf --max-time 5 "http://localhost:8000/health" -o /dev/null 2>/dev/null \
            && { log "API OK"; break; } || true
        [ "$i" -eq 20 ] && warn "API demorou. Verifique: docker compose logs backend"
        sleep 3
    done

    # -- 8. Verificacao final --------------------------------------------------
    header "8/8 - Verificacao final"
    docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null \
        | tail -n +2 \
        | while IFS=$'\t' read -r name status; do
            if echo "$status" | grep -qiE "running|Up"; then
                echo -e "  ${GREEN}[OK]${NC} $name"
            else
                echo -e "  ${RED}[!!]${NC} $name  <- PROBLEMA: $status"
            fi
          done

    # Resumo
    cat > .install-summary.txt <<SUMEOF
============================
 FinAgent - Resumo Instalacao
 $(date)
============================

Painel Admin:  https://${DOMAIN}/admin
API Docs:      https://${DOMAIN}/api/docs
Evolution API: http://${DOMAIN}:8080

Senha Admin:   ${ADMIN_PASSWORD}
  GUARDE ESTA SENHA!

Proximos passos:
  1. Acesse https://${DOMAIN}/admin
  2. Conecte WhatsApp: Admin -> WhatsApp
  3. Crie agentes: Admin -> Agentes
  4. Cadastre clientes: Admin -> Clientes

Para atualizar no futuro:
  git pull && bash install.sh

============================
SUMEOF
    log "Resumo salvo em .install-summary.txt"

    echo ""; divider
    echo -e "\n${GREEN}${BOLD}  [OK] FinAgent instalado com sucesso!${NC}\n"
    echo -e "  Painel Admin:   ${CYAN}https://${DOMAIN}/admin${NC}"
    echo -e "  API Docs:       ${CYAN}https://${DOMAIN}/api/docs${NC}"
    echo -e "  Evolution API:  ${CYAN}http://${DOMAIN}:8080${NC}"
    echo ""
    echo -e "  Senha Admin:    ${YELLOW}${BOLD}${ADMIN_PASSWORD}${NC}"
    echo -e "  ${YELLOW}Salve esta senha! Tambem esta em .install-summary.txt${NC}"
    echo ""
    echo -e "  Logs:    ${CYAN}docker compose logs -f${NC}"
    echo -e "  Update:  ${CYAN}git pull && bash install.sh${NC}"
    echo -e "  Parar:   ${CYAN}docker compose down${NC}"
    echo ""; divider
}

# ═══════════════════════════════════════════════════════════════════════════════
#  EXECUCAO
# ═══════════════════════════════════════════════════════════════════════════════
if [ "$MODE" = "update" ]; then
    run_update
else
    run_install
fi
