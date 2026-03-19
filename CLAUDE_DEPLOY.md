# CLAUDE — LEIA ESTE ARQUIVO PRIMEIRO

> Este documento foi escrito para **você, Claude Code**, que está abrindo este projeto
> **sem nenhum contexto da conversa anterior**.
>
> **LEIA TODO ESTE DOCUMENTO ANTES DE TOCAR EM QUALQUER ARQUIVO.**
> Erros críticos já foram cometidos e corrigidos — não os repita.

---

## O QUE É ESTE PROJETO

O **FinAgent** é um assistente financeiro pessoal baseado em AI. Funciona como um contador humano inteligente que atende clientes pelo **WhatsApp**, **Telegram** e **Web App**.

- **Dono:** Lucas Bolla (lucasbolla@icloud.com / GitHub: LucasBolla94)
- **Repo:** github.com/LucasBolla94/finagent
- **Uso:** Pessoal — para Lucas e amigos. Não comercial ainda.
- **Status:** Sistema completo, branch `main` estável.

---

## SERVIDOR DO LUCAS

```
CPU:  Intel Xeon E5-1620v2 — 4 cores / 8 threads — 3.7GHz
RAM:  32 GB ECC
Disk: 1x 120 GB SSD
GPU:  NENHUMA — todos os modelos AI são via API (OpenRouter)
OS:   Ubuntu/Debian
```

---

## ESTRUTURA COMPLETA DE PASTAS

```
finagent/
├── CLAUDE_DEPLOY.md              ← você está aqui
├── README.md
├── ROADMAP.md                    ← progresso do projeto
├── .env.example                  ← template de variáveis
├── .env.dev                      ← variáveis pré-preenchidas para dev local
├── start-dev.sh                  ← UM COMANDO para subir em dev
├── docker-compose.yml            ← produção (com Nginx + SSL)
├── docker-compose.dev.yml        ← dev (sem Nginx, portas abertas)
│
├── docker/
│   ├── nginx.conf                ← proxy reverso (só prod)
│   └── ssl/
│       └── README.md             ← instruções SSL
│
├── scripts/
│   ├── init_postgres.sql         ← cria extensões e tabelas base
│   └── deploy.sh                 ← script de deploy para produção
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               ← FastAPI entry point
│       ├── config.py             ← settings (lê .env)
│       ├── database.py           ← conexão async PostgreSQL
│       ├── models/
│       │   ├── tenant.py         ← SQLAlchemy model: clientes
│       │   └── agent.py          ← SQLAlchemy model: agentes
│       ├── middleware/
│       │   └── auth.py           ← JWT auth middleware
│       ├── api/
│       │   ├── auth.py           ← POST /login, /register
│       │   ├── chat.py           ← POST /chat/message + WS /chat/ws
│       │   ├── transactions.py   ← CRUD transações
│       │   ├── reports.py        ← GET relatórios
│       │   ├── alerts.py         ← CRUD alertas
│       │   ├── documents.py      ← POST /upload, /confirm
│       │   ├── webhooks.py       ← WhatsApp + Telegram webhooks
│       │   └── admin.py          ← painel admin (X-Admin-Key)
│       ├── agent/
│       │   ├── core.py           ← FinAgent STATELESS (CRÍTICO — veja abaixo)
│       │   ├── behavioral_analyzer.py
│       │   ├── memory.py
│       │   ├── model_selector.py
│       │   └── tools/
│       │       ├── definitions.py
│       │       └── executor.py
│       ├── services/
│       │   └── document_processor.py  ← analisa PDFs e fotos
│       └── workers/
│           ├── celery_app.py          ← configuração Celery + beat schedule
│           ├── notification_worker.py ← envia msg WhatsApp/Telegram
│           ├── alert_checker.py       ← verifica alertas (cada hora)
│           ├── weekly_summary.py      ← resumo semanal (segunda 8h)
│           ├── monthly_report.py      ← relatório mensal (dia 1, 8h)
│           └── promise_checker.py     ← follow-up de promessas (manhã)
│
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│       ├── 001_add_auth_fields.py
│       └── 002_add_agent_system_prompt_model.py
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── next.config.js
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx            ← login
        │   ├── dashboard/          ← dashboard principal
        │   ├── chat/               ← chat web
        │   └── admin/
        │       ├── page.tsx        ← painel admin (stats + WhatsApp)
        │       ├── agents/         ← CRUD agentes
        │       └── tenants/        ← lista clientes + assign agent
        └── lib/
            └── api.ts              ← funções de API (authApi, adminApi)
```

---

## DESIGN CRÍTICO: FinAgent É STATELESS

> **ATENÇÃO:** Este é o ponto mais importante. Não quebre isso.

### O que era antes (ERRADO — não faça assim):

```python
# ERRADO — FinAgent NÃO aceita parâmetros no __init__
agent = FinAgent(tenant_id="...", db=db, agent_config=..., ...)  # ← QUEBRA

# ERRADO — respond() NÃO retorna string
response = await agent.respond(message)
send(response)  # ← TypeError: AgentResponse não é string
```

### Como funciona AGORA (CORRETO):

```python
# CORRETO — FinAgent sem parâmetros
agent = FinAgent()

# CORRETO — respond() aceita esses parâmetros
agent_response = await agent.respond(
    tenant_id="uuid-do-cliente",
    message="texto da mensagem",
    channel="whatsapp",        # ou "telegram", "web", "system"
    session_id="opcional",
    db=db,                     # opcional — cria própria sessão se None
)

# CORRETO — .content para pegar o texto
text_to_send = agent_response.content
```

### Por que é stateless?

O mesmo `FinAgent()` serve **todos os tenants** simultaneamente. Cada chamada a `respond()` carrega o contexto do tenant do banco de dados. Isso é eficiente e thread-safe.

Se `db=None`, o agente cria sua própria sessão SQLAlchemy e fecha no final. Isso permite que workers Celery usem o agente sem gerenciar sessões.

---

## FLUXO COMPLETO DE UMA MENSAGEM WHATSAPP

```
WhatsApp do cliente
     │
     ▼
Evolution API (webhook)
     │  POST /api/v1/webhooks/whatsapp
     ▼
webhooks.py → _process_whatsapp_message()
     │
     ├─ Busca tenant pelo número de WhatsApp
     ├─ FinAgent().respond(tenant_id=..., message=..., channel="whatsapp", db=db)
     │       │
     │       ├─ Carrega agente atribuído ao tenant (DB)
     │       ├─ Carrega behavioral_profile (DB)
     │       ├─ Busca histórico de conversa (DB)
     │       ├─ Executa tools financeiras (se necessário)
     │       ├─ Chama OpenRouter API
     │       ├─ Salva resposta no histórico
     │       └─ Retorna AgentResponse
     │
     ├─ Extrai agent_response.content
     └─ Envia via Evolution API para o WhatsApp do cliente
```

---

## COMO RODAR LOCALMENTE (DEV)

### Pré-requisitos
- Docker + Docker Compose instalados
- Uma chave OpenRouter em https://openrouter.ai/keys

### Um único comando:

```bash
cd finagent
bash start-dev.sh
```

O script:
1. Copia `.env.dev` se `.env` não existir
2. Pede pra você preencher `OPENROUTER_API_KEY` se ainda for placeholder
3. Sobe tudo com `docker-compose.dev.yml`
4. Roda migrations
5. Imprime URLs de todos os serviços

### URLs no dev:
- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health
- **Evolution API:** http://localhost:8080
- **Banco direto:** localhost:5432 (user: finagent, db: finagent)

### Credenciais dev padrão:
```
Admin Key: admin123  (header X-Admin-Key)
DB User:   finagent
DB Pass:   devpassword123
Redis:     localhost:6379
```

---

## AUTENTICAÇÃO — DOIS SISTEMAS SEPARADOS

### 1. JWT (clientes / usuários do app)
- `POST /api/v1/auth/login` → retorna `access_token`
- Todas as rotas da API requerem `Authorization: Bearer {token}`
- Token expira em 7 dias
- Middleware em `app/middleware/auth.py` → `get_current_tenant()`

### 2. X-Admin-Key (painel admin — só Lucas)
- Todas as rotas `/api/admin/*` requerem header `X-Admin-Key: {ADMIN_SECRET_KEY}`
- Usar `secrets.compare_digest()` para prevenir timing attacks (já implementado)
- Se `ADMIN_SECRET_KEY` não estiver no `.env` → retorna 503

---

## BANCO DE DADOS — SCHEMA COMPLETO

### Tabelas globais (compartilhadas entre todos)
```sql
tenants          -- clientes registrados
agents           -- personas dos agentes
imported_documents -- controle de PDFs importados (deduplicação)
```

### Por cliente — schema financeiro: `tenant_{uuid_sem_hifens}_financial`
```sql
accounts         -- contas bancárias, cartão, caixa
categories       -- categorias de despesas/receitas
transactions     -- TODAS as transações
alerts           -- alertas configurados (balance, expense, bill_due, category)
reports          -- relatórios gerados (mensal, semanal)
```

### Por cliente — schema de contexto: `tenant_{uuid_sem_hifens}_context`
```sql
conversation_history  -- todo histórico de mensagens
key_moments           -- memórias importantes salvas pelo agente
agent_promises        -- promessas do agente (follow-up)
behavioral_profiles   -- perfil comportamental adaptativo
embeddings            -- vetores pgvector para busca semântica
```

### Como os schemas são criados?
Automaticamente pela função SQL `create_tenant_schemas(tenant_id)` definida em `scripts/init_postgres.sql`. Chamada quando um novo tenant é registrado via `database.py`.

---

## VARIÁVEIS DE AMBIENTE

| Variável | Obrigatória | Padrão (dev) | Descrição |
|----------|-------------|--------------|-----------|
| `SECRET_KEY` | ✅ | `dev-secret-key-change-in-production` | Assinar tokens JWT |
| `ADMIN_SECRET_KEY` | ✅ | `admin123` | Header X-Admin-Key |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://finagent:devpassword123@postgres:5432/finagent` | PostgreSQL async |
| `POSTGRES_PASSWORD` | ✅ | `devpassword123` | Senha do banco |
| `REDIS_URL` | ✅ | `redis://redis:6379/0` | Para Celery |
| `OPENROUTER_API_KEY` | ✅ | *(vazio — PREENCHER)* | API de AI |
| `EVOLUTION_API_KEY` | ✅ | `dev-evolution-key` | WhatsApp API key |
| `EVOLUTION_API_URL` | ✅ | `http://evolution_api:8080` | URL interna Evolution |
| `EVOLUTION_INSTANCE_NAME` | ✅ | `finagent_dev` | Nome da instância WA |
| `TELEGRAM_BOT_TOKEN` | ❌ | *(vazio)* | Só se usar Telegram |
| `FRONTEND_URL` | ✅ | `http://localhost:3000` | Para CORS |
| `CORS_ORIGINS` | ✅ | `["http://localhost:3000"]` | CORS allowlist |
| `BACKEND_PUBLIC_URL` | ✅ | `http://localhost:8000` | URL pública backend |
| `MODEL_FAST` | ❌ | `google/gemini-flash-1.5` | Override modelo rápido |
| `MODEL_POWERFUL` | ❌ | `anthropic/claude-haiku-4` | Override modelo padrão |
| `DEBUG` | ❌ | `true` | Logs detalhados |

---

## WORKERS CELERY — SCHEDULE

| Worker | Schedule | O que faz |
|--------|----------|-----------|
| `check_all_alerts` | A cada 1 hora | Verifica alertas de saldo, despesa, vencimento |
| `send_weekly_summaries` | Segunda-feira 8h | Resumo da semana para cada cliente |
| `send_monthly_reports` | Dia 1 de cada mês 8h | Relatório mensal completo com AI |
| `check_promises` | Toda manhã 9h | Follow-up de promessas feitas pelo agente |
| `send_notification` | On-demand | Envia mensagem via WhatsApp/Telegram |

---

## FLUXO DO UPLOAD DE DOCUMENTO (PDF/Foto)

```
Usuário faz upload no web app
     │
     ▼
POST /api/v1/documents/upload
     │
     ├─ Valida: tamanho < 20MB, tipo suportado (PDF/JPEG/PNG/WebP/HEIC)
     ├─ document_processor.analyze_document() → extrai transações via AI Vision
     ├─ Verifica duplicatas (hash do documento)
     ├─ Armazena análise em _pending_imports (TTL 30 min)
     └─ Retorna preview: {import_id, total_found, to_import, duplicates, transactions[]}
          │
          ▼
Usuário revisa preview, confirma
          │
          ▼
POST /api/v1/documents/confirm
     │
     ├─ Busca análise pelo import_id (expira após 30 min)
     ├─ confirm_import() → salva transações no banco
     └─ Remove da memória temporária
```

---

## PAINEL ADMIN — FLUXO DE USO

### Acessar
```
URL: http://localhost:3000/admin  (dev)
     https://seudominio.com/admin  (prod)
Header: X-Admin-Key: admin123  (dev)
```

### Conectar WhatsApp
1. Ir em **WhatsApp** no admin
2. Clicar **Conectar WhatsApp**
3. Backend chama Evolution API → `/instance/create`
4. Clicar **Ver QR Code**
5. Escanear com o celular no WhatsApp → Aparelhos Conectados → Conectar aparelho
6. Status muda para "connected"

### Criar Agente
1. Ir em **Agentes** → **Novo Agente**
2. Preencher: nome, description, system_prompt (personalidade completa), model
3. System prompt é o mais importante — define comportamento completo do agente
4. Exemplo de system prompt mínimo:
```
Você é Rafael Oliveira, assistente financeiro pessoal. Direto, confiável.
Você conhece finanças pessoais e ajuda seus clientes a organizar dinheiro.
Sempre que o cliente mencionar gastos, registre como transações.
```

### Atribuir Agente a Cliente
1. Ir em **Clientes**
2. Clicar no cliente → **Atribuir Agente**
3. Selecionar o agente → salvar

---

## REGRAS — O QUE NÃO QUEBRAR

### ❌ NUNCA faça isso:

```python
# 1. NÃO passe parâmetros no FinAgent()
agent = FinAgent(tenant_id=x, db=db)  # ← QUEBRA

# 2. NÃO trate respond() como string
text = await agent.respond(...)  # ← retorna AgentResponse, não string
send_message(text)               # ← QUEBRA — texto não é string

# 3. NÃO use date.replace() para somar dias
future = today.replace(day=today.day + 5)  # ← QUEBRA no fim do mês

# 4. NÃO compare strings com == para autenticação
if key == secret:  # ← vulnerável a timing attacks

# 5. NÃO esqueça de fechar sessões async fora de request context
db = AsyncSessionLocal()
# ... esquece db.close()  # ← leak de conexão
```

### ✅ SEMPRE faça assim:

```python
# 1. FinAgent sem parâmetros
agent = FinAgent()

# 2. Usar .content para extrair texto
agent_response = await agent.respond(tenant_id=..., message=..., channel=..., db=db)
send_message(agent_response.content)

# 3. timedelta para somar dias
from datetime import timedelta
future = today + timedelta(days=5)

# 4. secrets.compare_digest para auth
import secrets
if not secrets.compare_digest(key.encode(), secret.encode()):
    raise HTTPException(403)

# 5. Usar context manager para sessões async
async with AsyncSessionLocal() as db:
    result = await db.execute(...)
```

---

## ERROS COMUNS E SOLUÇÕES

### `AttributeError: 'FinAgent' object has no attribute 'X'`
O FinAgent foi reformulado para ser stateless. Qualquer atributo de instância que você procura provavelmente foi movido para dentro do método `respond()`.

### `AttributeError: 'str' object has no attribute 'content'`
Você está chamando `agent_response.content` mas `agent_response` é uma string. Isso acontece se alguém (errado) fizer `agent_response = await agent.respond(...).content` no lugar de armazenar o objeto completo primeiro.

### `TypeError: respond() got unexpected keyword argument`
O `respond()` aceita: `tenant_id`, `message`, `channel`, `session_id`, `sent_at`, `db`. Verifique ortografia.

### `Import session not found or expired`
O upload de documento expirou (TTL 30 min). Faça o upload novamente.

### `Admin key not configured. Set ADMIN_SECRET_KEY in .env`
`ADMIN_SECRET_KEY` está vazio no `.env`. Adicione qualquer string.

### `sqlalchemy.exc.InterfaceError: connection already closed`
Sessão SQLAlchemy sendo usada após fechamento. Use `async with AsyncSessionLocal() as db:` para garantir escopo correto.

### Container `backend` reinicia em loop
```bash
docker compose logs backend  # ver o erro exato
```
Causas comuns: `.env` não existe, `DATABASE_URL` incorreta, migration pendente.

### Migration falha: `column X already exists`
A migration já foi aplicada. Verifique:
```bash
docker compose exec backend alembic current
```

### `connection refused` no Evolution API
A instância WhatsApp não foi criada. Vá ao painel admin → WhatsApp → Conectar.

---

## MIGRATIONS — COMO RODAR

```bash
# Ver migration atual
docker compose exec backend alembic current

# Aplicar todas as migrations pendentes
docker compose exec backend alembic upgrade head

# Criar nova migration (depois de mudar models)
docker compose exec backend alembic revision --autogenerate -m "descricao"

# Rollback uma migration
docker compose exec backend alembic downgrade -1
```

**Ordem das migrations:**
```
001_add_auth_fields
  └─ 002_add_agent_system_prompt_model
```

---

## DEPLOY EM PRODUÇÃO

### 1. Clonar e configurar

```bash
git clone https://github.com/LucasBolla94/finagent.git
cd finagent
cp .env.example .env
nano .env
```

**Preencher no .env de produção:**
```env
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_hex(32))">
ADMIN_SECRET_KEY=<senha forte — não use admin123>
POSTGRES_PASSWORD=<senha forte>
DATABASE_URL=postgresql+asyncpg://finagent:<senha>@postgres:5432/finagent
OPENROUTER_API_KEY=sk-or-v1-...
EVOLUTION_API_KEY=<string aleatória>
BACKEND_PUBLIC_URL=https://seudominio.com
NEXT_PUBLIC_API_URL=https://seudominio.com
CORS_ORIGINS=["https://seudominio.com"]
FRONTEND_URL=https://seudominio.com
```

### 2. Deploy com um comando

```bash
bash scripts/deploy.sh
```

O script: verifica deps → gera SSL self-signed → build → sobe → migrations.

### 3. SSL real com Let's Encrypt

```bash
sudo apt install certbot -y
docker compose stop nginx
sudo certbot certonly --standalone -d seudominio.com \
  --agree-tos --email lucasbolla@icloud.com
sudo cp /etc/letsencrypt/live/seudominio.com/fullchain.pem docker/ssl/
sudo cp /etc/letsencrypt/live/seudominio.com/privkey.pem docker/ssl/
sudo chmod 644 docker/ssl/*.pem
# Editar docker/nginx.conf: server_name seudominio.com;
docker compose start nginx
```

### 4. Comandos úteis

```bash
bash scripts/deploy.sh update   # pull + rebuild + restart
bash scripts/deploy.sh stop     # para tudo
bash scripts/deploy.sh logs     # logs em tempo real
bash scripts/deploy.sh status   # status dos containers
docker stats                     # uso de CPU/memória
```

---

## MODELOS AI DISPONÍVEIS (OpenRouter)

| ID no sistema | Modelo real | Uso |
|---------------|-------------|-----|
| `google/gemini-flash-1.5` | Gemini Flash | Respostas rápidas simples |
| `anthropic/claude-haiku-4` | Claude Haiku | Padrão — bom custo/benefício |
| `anthropic/claude-sonnet-4-5` | Claude Sonnet | Análises complexas |
| `openai/gpt-4o-mini` | GPT-4o mini | Alternativa econômica |
| `openai/gpt-4o` | GPT-4o | Tarefas críticas / leitura de imagem |

O agente auto-seleciona o modelo baseado na complexidade via `model_selector.py`.
Cada agente também pode ter um `model` padrão configurado no banco (campo `agents.model`).

---

## SEGURANÇA — REGRAS

1. **Nunca commite `.env`** — está no `.gitignore`
2. Em produção: `ADMIN_SECRET_KEY` deve ser uma senha forte, nunca `admin123`
3. Em produção: porta 5432 (postgres) e 6379 (redis) NÃO devem ser expostas externamente
4. OpenRouter cobra por token — monitorar em https://openrouter.ai/activity
5. Evolution API key é interna — não expor ao frontend

---

## CONTATO / OWNER

**Lucas Bolla**
- Email: lucasbolla@icloud.com
- GitHub: github.com/LucasBolla94
- Repo: github.com/LucasBolla94/finagent

---

*Documento v2 — atualizado em 19/03/2026 após refatoração stateless do FinAgent e correção de bugs críticos. Branch `fix/bugs-v1` mergeado em `main`.*
