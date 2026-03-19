# CLAUDE — LEIA ESTE ARQUIVO PRIMEIRO

> Este documento foi escrito para você, Claude Code, que está abrindo este projeto
> **sem nenhum contexto da conversa anterior**. Leia tudo antes de fazer qualquer coisa.

---

## O QUE É ESTE PROJETO

O **FinAgent** é um assistente financeiro pessoal baseado em AI. Ele funciona como um contador humano inteligente que atende clientes pelo **WhatsApp**, **Telegram** e **Web App**.

Este projeto pertence ao **Lucas Bolla** (lucasbolla@icloud.com / GitHub: LucasBolla94).

É um projeto **pessoal**, criado para Lucas e seus amigos. Não é comercial por enquanto.

---

## COMO O SISTEMA FUNCIONA (contexto essencial)

### Os Agentes são Atendentes — não bots genéricos
O sistema tem "agentes" que são **personas com identidade própria**. Cada agente tem nome, personalidade, estilo de comunicação. Eles constroem vínculo real com cada cliente ao longo do tempo, como um funcionário humano faria. Começa com 1 agente e cresce conforme a demanda.

### Cada cliente tem dados completamente isolados
No banco de dados, **cada cliente tem dois schemas PostgreSQL separados**:
- `tenant_{id}_financial` — transações, contas, saldos, relatórios, alertas
- `tenant_{id}_context` — histórico de conversas, memória, perfil comportamental

Isso é criado automaticamente pela função SQL `create_tenant_schemas()` em `scripts/init_postgres.sql`.

### O agente tem 3 camadas de memória
1. **Curto prazo** — últimas 20 mensagens da sessão
2. **Médio prazo** — momentos importantes e promessas feitas ao cliente
3. **Longo prazo** — embeddings vetoriais (pgvector) para busca semântica

### O sistema adapta o tom ao cliente automaticamente
O `behavioral_analyzer.py` analisa cada mensagem e vai moldando o estilo do agente ao jeito de cada cliente falar — formalidade, comprimento, uso de emoji, estado emocional.

### Multi-model via OpenRouter
O sistema usa o OpenRouter (não a OpenAI diretamente) para ter acesso a múltiplos modelos:
- Mensagens simples → Gemini Flash (barato, rápido)
- Tarefas padrão → Claude Haiku
- Análises complexas → Claude Sonnet ou GPT-4
- Leitura de PDF/foto → GPT-4o Vision

---

## SERVIDOR DO LUCAS (onde você está rodando)

```
CPU:  Intel Xeon E5-1620v2 — 4 cores / 8 threads — 3.7GHz
RAM:  32 GB ECC
Disco: 1x 120 GB SSD
GPU:  Nenhuma
OS:   Linux (provavelmente Ubuntu)
```

**Sem GPU** — todos os modelos de AI são via API (OpenRouter), não rodamos nada local.

---

## ESTRUTURA DE PASTAS

```
finagent/
├── CLAUDE_DEPLOY.md          ← você está aqui
├── README.md
├── .env.example              ← copie para .env e preencha
├── docker-compose.yml        ← sobe todo o sistema
├── scripts/
│   └── init_postgres.sql     ← cria extensões e tabelas base do banco
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    └── app/
        ├── main.py           ← FastAPI — ponto de entrada
        ├── config.py         ← todas as configurações (lê do .env)
        ├── database.py       ← conexão PostgreSQL + criação de schemas
        ├── models/
        │   ├── tenant.py     ← modelo do cliente
        │   └── agent.py      ← modelo do agente (persona)
        └── agent/
            ├── core.py              ← cérebro principal do agente
            ├── behavioral_analyzer.py ← analisa comportamento do cliente
            ├── memory.py            ← gerencia memória em 3 camadas
            ├── model_selector.py    ← escolhe qual modelo usar
            └── tools/
                ├── definitions.py   ← lista de tools para o modelo AI
                └── executor.py      ← executa as tools no banco de dados
```

---

## O QUE AINDA PRECISA SER CONSTRUÍDO

O projeto tem a **fundação pronta** (banco de dados, agente core, memória, ferramentas financeiras). O que falta implementar:

### Prioridade 1 — Para o sistema funcionar
- [ ] `backend/app/api/auth.py` — login/registro de clientes e agentes (JWT)
- [ ] `backend/app/api/webhooks.py` — receber mensagens do WhatsApp e Telegram
- [ ] `backend/app/api/chat.py` — endpoint de chat para o web app
- [ ] `backend/app/api/transactions.py` — CRUD de transações
- [ ] `backend/app/api/reports.py` — geração de relatórios
- [ ] `backend/app/services/document_processor.py` — ler PDFs e fotos de extratos bancários
- [ ] `backend/app/workers/celery_app.py` — configuração do Celery
- [ ] `backend/app/workers/alert_checker.py` — verificar alertas a cada hora
- [ ] Migrations Alembic — criar as tabelas no banco via código
- [ ] `frontend/` — Next.js dashboard com login, chat e relatórios

### Prioridade 2 — Melhorias
- [ ] Sistema de deduplicação de transações (está no `executor.py` mas precisa da extensão `pg_trgm`)
- [ ] Transcrição de áudio (mensagens de voz no WhatsApp)
- [ ] OCR para notas fiscais em foto
- [ ] Exportar relatórios em PDF

---

## COMO FAZER O DEPLOY — PASSO A PASSO

### Pré-requisitos no servidor

```bash
# Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Instalar Docker Compose
sudo apt-get install docker-compose-plugin -y

# Verificar
docker --version
docker compose version
```

### 1. Clonar o repositório

```bash
git clone https://github.com/LucasBolla94/finagent.git
cd finagent
```

### 2. Configurar o arquivo .env

```bash
cp .env.example .env
nano .env
```

**Preencha obrigatoriamente:**

```env
# Chave secreta — gere uma com: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=cole_aqui_a_chave_gerada

# Banco de dados — mude a senha!
POSTGRES_PASSWORD=uma_senha_forte_aqui
DATABASE_URL=postgresql+asyncpg://finagent:uma_senha_forte_aqui@postgres:5432/finagent

# OpenRouter — chave de API em: https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-v1-sua_chave_aqui

# Evolution API (WhatsApp) — pode deixar assim por ora
EVOLUTION_API_KEY=uma_chave_qualquer_aqui

# URL do seu servidor (IP ou domínio)
FRONTEND_URL=http://SEU_IP_AQUI:3000
CORS_ORIGINS=["http://SEU_IP_AQUI:3000"]
```

### 3. Subir os containers

```bash
# Primeira vez — constrói as imagens e sobe tudo
docker compose up -d --build

# Ver se está tudo rodando
docker compose ps

# Ver logs em tempo real
docker compose logs -f backend
```

**Serviços que sobem:**
| Serviço | Porta | O que é |
|---------|-------|---------|
| postgres | 5432 | Banco de dados |
| redis | 6379 | Cache e filas |
| backend | 8000 | API FastAPI |
| frontend | 3000 | Dashboard web |
| celery_worker | — | Tarefas assíncronas |
| celery_beat | — | Agendador (alertas) |
| evolution_api | 8080 | WhatsApp |
| nginx | 80/443 | Proxy reverso |

### 4. Verificar se a API está respondendo

```bash
curl http://localhost:8000/health
# Esperado: {"status": "ok", "version": "0.1.0"}
```

### 5. Conectar o WhatsApp

```bash
# Abrir no browser: http://SEU_IP:8080
# Ou via API:
curl -X POST http://localhost:8080/instance/create \
  -H "apikey: SUA_EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"instanceName": "finagent_agent1", "qrcode": true}'

# Pegar o QR code para escanear:
curl http://localhost:8080/instance/qrcode/finagent_agent1 \
  -H "apikey: SUA_EVOLUTION_API_KEY"
```

### 6. Comandos úteis do dia a dia

```bash
# Parar tudo
docker compose down

# Reiniciar só o backend
docker compose restart backend

# Ver logs do banco
docker compose logs postgres

# Entrar no banco de dados
docker compose exec postgres psql -U finagent -d finagent

# Atualizar código e reiniciar
git pull
docker compose up -d --build backend
```

---

## COMO CRIAR O PRIMEIRO AGENTE E CLIENTE

Depois que a API estiver rodando, criar o primeiro agente via banco:

```sql
-- Conectar no banco:
-- docker compose exec postgres psql -U finagent -d finagent

INSERT INTO agents (name, backstory, personality) VALUES (
  'Rafael Oliveira',
  'Você é Rafael Oliveira, assistente financeiro pessoal há 8 anos. Tem experiência com pequenos negócios e autônomos. Direto, confiável, sempre lembra dos detalhes que o cliente contou.',
  '{
    "tone": "professional_friendly",
    "communication_style": "direct",
    "formality_base": 3,
    "emoji_usage": "low",
    "response_length": "concise",
    "proactivity": "high",
    "strengths": ["analysis", "cash_flow", "reporting"]
  }'
);
```

Para criar um cliente (tenant) e seus schemas:

```sql
-- Inserir o tenant
INSERT INTO tenants (name, email, whatsapp_number)
VALUES ('Nome do Cliente', 'email@cliente.com', '5511999999999')
RETURNING id;

-- Usar o ID retornado para criar os schemas:
SELECT create_tenant_schemas('ID_RETORNADO_AQUI');
```

---

## VARIÁVEIS DE AMBIENTE — REFERÊNCIA COMPLETA

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `SECRET_KEY` | ✅ | Chave para assinar tokens JWT |
| `ADMIN_SECRET_KEY` | ✅ | Senha de acesso ao painel /admin |
| `DATABASE_URL` | ✅ | URL de conexão com PostgreSQL |
| `OPENROUTER_API_KEY` | ✅ | Chave da API OpenRouter |
| `EVOLUTION_API_KEY` | ✅ | Chave da Evolution API (WhatsApp) |
| `TELEGRAM_BOT_TOKEN` | ❌ | Opcional — só se usar Telegram |
| `FRONTEND_URL` | ✅ | URL do frontend (para CORS) |
| `DEBUG` | ❌ | `true` para desenvolvimento |
| `MODEL_FAST` | ❌ | Override do modelo rápido |
| `MODEL_POWERFUL` | ❌ | Override do modelo poderoso |

---

## ARQUITETURA DO BANCO DE DADOS

### Tabelas globais (compartilhadas)
- `tenants` — clientes do sistema
- `agents` — personas dos agentes
- `imported_documents` — controle de PDFs importados (evita duplicatas)

### Por cliente — schema financeiro (`tenant_{id}_financial`)
- `accounts` — contas bancárias, cartão, caixa
- `categories` — categorias de despesas/receitas
- `transactions` — todas as transações
- `alerts` — alertas configurados
- `reports` — relatórios gerados

### Por cliente — schema de contexto (`tenant_{id}_context`)
- `conversation_history` — todo histórico de mensagens
- `key_moments` — memórias importantes salvas pelo agente
- `agent_promises` — promessas que o agente fez e deve cumprir
- `behavioral_profiles` — perfil comportamental do cliente
- `embeddings` — vetores para busca semântica (pgvector)

---

## SEGURANÇA — PONTOS IMPORTANTES

1. **Nunca commite o arquivo `.env`** — ele está no `.gitignore`
2. O token do GitHub está salvo em `~/.git-credentials` — não mova esse arquivo
3. A API OpenRouter cobra por uso — monitore os custos em https://openrouter.ai/activity
4. O banco PostgreSQL só deve ser acessível internamente (não expor porta 5432 externamente)

---

## DEPLOY NO SERVIDOR — PASSO A PASSO COMPLETO

### 1. Instalar Docker (Ubuntu/Debian)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version  # deve mostrar versão
```

### 2. Clonar o repositório

```bash
git clone https://github.com/LucasBolla94/finagent.git
cd finagent
```

### 3. Configurar o .env

```bash
cp .env.example .env
nano .env   # ou vim .env
```

Preencher obrigatoriamente:
- `SECRET_KEY` — gere com: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `ADMIN_SECRET_KEY` — senha para acessar /admin (invente uma senha forte)
- `POSTGRES_PASSWORD` — senha do banco (invente uma senha forte)
- `DATABASE_URL` — atualizar com a mesma senha do postgres
- `OPENROUTER_API_KEY` — pegar em https://openrouter.ai/keys
- `EVOLUTION_API_KEY` — qualquer string aleatória (é a chave interna da Evolution API)
- `BACKEND_PUBLIC_URL` — URL pública do servidor, ex: `https://seudominio.com`
- `NEXT_PUBLIC_API_URL` — URL pública do backend, ex: `https://seudominio.com`
- `CORS_ORIGINS` — ex: `["https://seudominio.com"]`

### 4. Fazer o deploy (um comando só)

```bash
bash scripts/deploy.sh
```

O script automaticamente:
- Verifica dependências
- Gera certificado SSL self-signed (se não houver)
- Faz build dos containers
- Sobe todos os serviços
- Roda as migrations do banco

### 5. SSL com domínio real (Let's Encrypt)

```bash
# Instalar certbot
sudo apt install certbot -y

# Primeiro pare o nginx para liberar a porta 80
docker compose stop nginx

# Gerar certificado
sudo certbot certonly --standalone \
  -d seudominio.com \
  --agree-tos \
  --email lucasbolla@icloud.com

# Copiar certificados
sudo cp /etc/letsencrypt/live/seudominio.com/fullchain.pem docker/ssl/
sudo cp /etc/letsencrypt/live/seudominio.com/privkey.pem docker/ssl/
sudo chmod 644 docker/ssl/*.pem

# Atualizar nginx.conf com seu domínio
# Editar linha: server_name seudominio.com;

# Reiniciar nginx
docker compose start nginx
```

### 6. Configurar no painel Admin

```
Acesse: https://seudominio.com/admin
Senha: o ADMIN_SECRET_KEY que você colocou no .env
```

- Vá em **WhatsApp** → clique **Conectar WhatsApp** → escaneie o QR Code com seu celular
- Vá em **Agentes** → clique **Novo Agente** → crie seu primeiro agente
- Vá em **Clientes** → atribua o agente ao cliente

### 7. Comandos úteis no dia a dia

```bash
# Ver status de todos os containers
docker compose ps

# Ver logs em tempo real
docker compose logs -f backend
docker compose logs -f celery_worker

# Atualizar para nova versão
bash scripts/deploy.sh update

# Parar tudo
bash scripts/deploy.sh stop

# Monitorar uso de recursos
docker stats
```

---

## SE ALGO DER ERRADO

```bash
# Container não sobe — ver logs de erro
docker compose logs nome_do_servico

# Banco não inicializou — recriar
docker compose down -v  # CUIDADO: apaga os dados!
docker compose up -d

# Extensão pgvector não encontrada
docker compose exec postgres psql -U finagent -d finagent -c "CREATE EXTENSION vector;"

# Permission denied no Docker
sudo chmod 666 /var/run/docker.sock

# Nginx erro de SSL — reconstruir self-signed
cd docker/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem -out fullchain.pem \
  -subj "/CN=localhost"
docker compose restart nginx

# QR code não aparece — verificar Evolution API
docker compose logs evolution_api
# Reiniciar instância
curl -X DELETE http://localhost:8080/instance/delete/finagent_agent1 \
  -H "apikey: SEU_EVOLUTION_API_KEY"
```

---

## CONTATO / OWNER

**Lucas Bolla**
- Email: lucasbolla@icloud.com
- GitHub: github.com/LucasBolla94
- Repo: github.com/LucasBolla94/finagent

---

*Este documento foi gerado pelo Claude (Cowork) em 19/03/2026 com base em toda a conversa de arquitetura e desenvolvimento do projeto.*
