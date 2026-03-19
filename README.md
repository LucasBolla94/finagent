# FinAgent 🤖💰

> Assistente financeiro pessoal com AI — atende via WhatsApp, Telegram e Web App.
> Cada agente tem personalidade própria, memória real e constrói vínculo genuíno com cada cliente.

## Stack

- **Backend**: Python 3.11 + FastAPI + SQLAlchemy (async)
- **AI**: OpenRouter (multi-model: Gemini Flash, Claude, GPT-4o)
- **Banco**: PostgreSQL 16 + pgvector (schema isolado por cliente)
- **Fila**: Redis + Celery
- **WhatsApp**: Evolution API (self-hosted)
- **Telegram**: python-telegram-bot
- **Frontend**: Next.js 14 + TailwindCSS

## Funcionalidades

- 💬 Agentes com personalidade e memória real por cliente
- 🧠 Análise comportamental — adapta tom e estilo ao cliente
- 📊 Lançamentos, relatórios (DRE, fluxo de caixa), alertas
- 📄 Leitura de extratos bancários (PDF e foto)
- 🔁 Deduplicação inteligente de transações
- 🌍 Multi-idioma automático
- 🔒 Dados isolados por cliente (schemas PostgreSQL separados)

## Setup

```bash
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/finagent.git
cd finagent

# 2. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env com suas chaves (OpenRouter, PostgreSQL, Evolution API)

# 3. Suba os containers
docker-compose up -d

# 4. Acesse
# Backend API:   http://localhost:8000/api/docs
# Frontend:      http://localhost:3000
# Evolution API: http://localhost:8080
```

## Estrutura

```
finagent/
├── backend/
│   └── app/
│       ├── agent/           # Cérebro da AI
│       │   ├── core.py              # Orquestrador principal
│       │   ├── behavioral_analyzer.py  # Análise de comportamento
│       │   ├── memory.py            # Memória curto/médio/longo prazo
│       │   ├── model_selector.py    # Seleção inteligente de modelo
│       │   └── tools/              # Ferramentas do agente
│       ├── models/          # SQLAlchemy models
│       ├── api/             # Rotas FastAPI
│       ├── services/        # Lógica de negócio
│       └── workers/         # Celery tasks
├── frontend/                # Next.js dashboard
├── scripts/                 # SQL de inicialização
└── docker-compose.yml
```

## Agentes

Cada agente é uma persona com identidade, personalidade e memória própria.
Começa com 1 agente, escala conforme demanda.

O sistema de análise comportamental detecta automaticamente:
- Tom e formalidade preferidos do cliente
- Comprimento ideal das respostas
- Padrão de horários e frequência
- Estado emocional e nível de ansiedade
- Idioma preferido (automático)

E adapta cada resposta de acordo.

---

*Desenvolvido com ❤️ — para uso pessoal e de amigos*
