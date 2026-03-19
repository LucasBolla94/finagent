#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# FinAgent — Iniciar modo DEV (testes locais)
# Uso: bash start-dev.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

# Verificar se existe .env.dev
if [ ! -f ".env.dev" ]; then
    echo "❌ Arquivo .env.dev não encontrado!"
    exit 1
fi

# Verificar se a chave OpenRouter foi preenchida
if grep -q "COLOQUE-SUA-CHAVE-AQUI" .env.dev; then
    echo ""
    warn "Você ainda não colocou sua chave OpenRouter no .env.dev!"
    warn "Edite o arquivo e substitua a linha:"
    warn "  OPENROUTER_API_KEY=sk-or-v1-COLOQUE-SUA-CHAVE-AQUI"
    warn "Pegue sua chave em: https://openrouter.ai/keys"
    echo ""
    read -p "Pressione ENTER após editar .env.dev, ou Ctrl+C para sair..."
fi

log "Subindo FinAgent em modo DEV..."
docker compose -f docker-compose.dev.yml up -d --build

log "Aguardando banco ficar pronto..."
sleep 8

log "Rodando migrations..."
docker compose -f docker-compose.dev.yml exec -T backend alembic upgrade head

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  FinAgent DEV rodando! 🚀${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "  📱 App:         http://localhost:3000"
echo "  🔧 Admin:       http://localhost:3000/admin"
echo "  📚 API Docs:    http://localhost:8000/docs"
echo "  💬 WhatsApp:    http://localhost:8080"
echo ""
echo "  🔑 Senha admin: admin123"
echo ""
echo "  Para ver logs:  docker compose -f docker-compose.dev.yml logs -f backend"
echo "  Para parar:     docker compose -f docker-compose.dev.yml down"
echo ""
