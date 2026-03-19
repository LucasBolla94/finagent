# FinAgent — ROADMAP

> Documento vivo. Atualizado a cada sessão de desenvolvimento.
> Última atualização: 19/03/2026

---

## LEGENDA
- ✅ Concluído
- 🔄 Em progresso
- ⬜ Pendente
- 🔒 Bloqueado (depende de outro item)

---

## FASE 1 — FUNDAÇÃO ✅ CONCLUÍDA

> Base do sistema. Tudo que outras partes dependem.

| # | Tarefa | Status |
|---|--------|--------|
| 1.1 | Arquitetura completa do sistema documentada | ✅ |
| 1.2 | Banco de dados PostgreSQL + pgvector estruturado | ✅ |
| 1.3 | Schema isolado por cliente (financeiro + contexto) | ✅ |
| 1.4 | Modelo de Agente com identidade e personalidade | ✅ |
| 1.5 | Modelo de Tenant (cliente) | ✅ |
| 1.6 | Sistema de memória em 3 camadas | ✅ |
| 1.7 | Analisador comportamental (adapta tom ao cliente) | ✅ |
| 1.8 | Seletor de modelo (fast / standard / powerful / vision) | ✅ |
| 1.9 | Cérebro do agente (loop de tool calling) | ✅ |
| 1.10 | 9 ferramentas financeiras (create, balance, report...) | ✅ |
| 1.11 | Docker Compose com todos os serviços | ✅ |
| 1.12 | Repositório no GitHub (público) | ✅ |
| 1.13 | Documento de deploy para Claude Code (`CLAUDE_DEPLOY.md`) | ✅ |

---

## FASE 2 — API & AUTENTICAÇÃO ✅ CONCLUÍDA

> As "portas" do sistema. Sem isso, nada funciona de ponta a ponta.

| # | Tarefa | Status | Arquivo |
|---|--------|--------|---------|
| 2.1 | Migrations Alembic (criar tabelas automaticamente) | ✅ | `backend/alembic/` |
| 2.2 | Endpoint de registro de novo cliente (`POST /auth/register`) | ✅ | `backend/app/api/auth.py` |
| 2.3 | Endpoint de login (`POST /auth/login`) → retorna JWT | ✅ | `backend/app/api/auth.py` |
| 2.4 | Middleware de autenticação (valida JWT em todas as rotas) | ✅ | `backend/app/middleware/auth.py` |
| 2.5 | Endpoint de chat web (`POST /chat/message`) | ✅ | `backend/app/api/chat.py` |
| 2.6 | WebSocket para chat em tempo real (`WS /chat/ws`) | ✅ | `backend/app/api/chat.py` |
| 2.7 | Webhook WhatsApp (recebe mensagem → agente → responde) | ✅ | `backend/app/api/webhooks.py` |
| 2.8 | Webhook Telegram (recebe mensagem → agente → responde) | ✅ | `backend/app/api/webhooks.py` |
| 2.9 | CRUD de transações (`GET/POST/PUT/DELETE /transactions`) | ✅ | `backend/app/api/transactions.py` |
| 2.10 | CRUD de contas bancárias (`/accounts`) | ✅ | `backend/app/api/accounts.py` |
| 2.11 | Endpoint de relatórios (`GET /reports`) | ✅ | `backend/app/api/reports.py` |
| 2.12 | Endpoint de alertas (`GET/POST /alerts`) | ✅ | `backend/app/api/alerts.py` |
| 2.13 | Endpoint de perfil do cliente (`GET/PUT /profile`) | ✅ | `backend/app/api/profile.py` |
| 2.14 | Criar primeiro agente via seed script | ✅ | `scripts/seed_agent.py` |

---

## FASE 3 — LEITURA DE DOCUMENTOS ✅ CONCLUÍDA

> PDF de extrato bancário, foto de recibo, comprovante PIX.
> Sistema de deduplicação inteligente.

| # | Tarefa | Status | Arquivo |
|---|--------|--------|---------|
| 3.1 | Receber upload de arquivo (PDF ou imagem) via API | ✅ | `backend/app/api/documents.py` |
| 3.2 | Detectar tipo de documento (extrato, recibo, boleto) | ✅ | `backend/app/services/document_processor.py` |
| 3.3 | Extração de PDF digital (texto selecionável) via pdfplumber | ✅ | `backend/app/services/pdf_extractor.py` |
| 3.4 | Extração de PDF escaneado / foto via GPT-4o Vision | ✅ | `backend/app/services/vision_extractor.py` |
| 3.5 | Identificar banco pelo layout (Bradesco, Nubank, Itaú...) | ✅ | `backend/app/services/bank_parser.py` |
| 3.6 | Estruturar transações extraídas em JSON padronizado | ✅ | `backend/app/services/document_processor.py` |
| 3.7 | Deduplicação 4 camadas (SHA256 doc → fingerprint → fuzzy → pgvector) | ✅ | `backend/app/services/dedup_service.py` |
| 3.8 | Hash do documento inteiro (evita importar mesmo PDF 2x) | ✅ | `backend/app/services/dedup_service.py` |
| 3.9 | Hash por transação (evita duplicata de transação individual) | ✅ | `backend/app/services/dedup_service.py` |
| 3.10 | Score fuzzy de duplicata (valor + data + descrição similar) | ✅ | `backend/app/services/dedup_service.py` |
| 3.11 | Fluxo de confirmação: "Encontrei X transações. 2 duplicatas. Importar 47?" | ✅ | `backend/app/api/documents.py` |
| 3.12 | Importação em batch com rollback se falhar | ✅ | `backend/app/services/document_processor.py` |

---

## FASE 4 — WORKERS & ALERTAS ✅ CONCLUÍDA

> Celery rodando em background. Alertas, resumos automáticos, índice de embeddings.

| # | Tarefa | Status | Arquivo |
|---|--------|--------|---------|
| 4.1 | Configurar Celery + Redis (broker + beat schedule) | ✅ | `backend/app/workers/celery_app.py` |
| 4.2 | Worker: verificar alertas a cada hora | ✅ | `backend/app/workers/alert_checker.py` |
| 4.3 | Worker: enviar alerta via WhatsApp + Telegram | ✅ | `backend/app/workers/notification_worker.py` |
| 4.4 | Worker: indexar embeddings de novas transações | ✅ | `backend/app/workers/embedding_indexer.py` |
| 4.5 | Worker: gerar resumo semanal por cliente (memória médio prazo) | ✅ | `backend/app/workers/weekly_summary.py` |
| 4.6 | Worker: cobrar promessas pendentes do agente | ✅ | `backend/app/workers/promise_checker.py` |
| 4.7 | Worker: relatório mensal automático no dia 1º | ✅ | `backend/app/workers/monthly_report.py` |

---

## FASE 5 — DASHBOARD WEB ✅ CONCLUÍDA

> Frontend em Next.js. O cliente acessa pelo computador ou celular.

| # | Tarefa | Status | Arquivo |
|---|--------|--------|---------|
| 5.1 | Setup Next.js 14 + TailwindCSS + TypeScript | ✅ | `frontend/` |
| 5.2 | Tela de login + registro (email + senha) | ✅ | `frontend/src/app/login/` |
| 5.3 | Dashboard principal (saldo total, receitas, despesas, lucro) | ✅ | `frontend/src/app/dashboard/` |
| 5.4 | Gráfico AreaChart receitas vs despesas (6 meses) + BarChart categorias | ✅ | `frontend/src/app/dashboard/` |
| 5.5 | Tela de Chat com o agente (estilo WhatsApp Web) | ✅ | `frontend/src/app/chat/` |
| 5.6 | Upload de PDF/foto de extrato direto no chat + fluxo de confirmação | ✅ | `frontend/src/app/chat/` |
| 5.7 | Tela de transações (tabela com filtros, busca e paginação) | ✅ | `frontend/src/app/transactions/` |
| 5.8 | Tela de relatórios (DRE, Fluxo de Caixa, por categoria) | ✅ | `frontend/src/app/reports/` |
| 5.9 | Tela de alertas (criar, listar, ativar/desativar) | ✅ | `frontend/src/app/alerts/` |
| 5.10 | Tela de configurações (conta, contas bancárias, WhatsApp, Telegram) | ✅ | `frontend/src/app/settings/` |
| 5.11 | Painel Admin: login, stats, gerenciar agentes, WhatsApp QR, clientes | ✅ | `frontend/src/app/admin/` |
| 5.12 | Design responsivo (funciona no celular também) | ✅ | global |

---

## FASE 6 — DEPLOY NO SERVIDOR ✅ CONCLUÍDA (infra pronta)

> Toda a infraestrutura de deploy está pronta. Lucas executa no servidor.

| # | Tarefa | Status |
|---|--------|--------|
| 6.1 | Nginx config com HTTPS, WebSocket, proxy para todos serviços | ✅ `docker/nginx.conf` |
| 6.2 | SSL: Let's Encrypt (produção) + auto-geração self-signed (testes) | ✅ `docker/ssl/README.md` |
| 6.3 | Script de deploy one-command (`bash scripts/deploy.sh`) | ✅ `scripts/deploy.sh` |
| 6.4 | Script de update (`bash scripts/deploy.sh update`) | ✅ `scripts/deploy.sh` |
| 6.5 | docker-compose.yml com todos os serviços: postgres, redis, backend, frontend, celery, nginx, evolution | ✅ |
| 6.6 | CLAUDE_DEPLOY.md atualizado com instruções passo-a-passo | ✅ |
| — | **Executar no servidor** (Lucas faz manualmente) | ⬜ |
| — | Instalar Docker no servidor | ⬜ |
| — | Clonar repositório + configurar .env | ⬜ |
| — | Rodar `bash scripts/deploy.sh` | ⬜ |
| — | Escanear QR Code WhatsApp pelo painel Admin | ⬜ |
| — | Criar primeiro agente e atribuir a cliente de teste | ⬜ |

---

## FASE 7 — POLISH & EXTRAS ⬜

> Melhorias depois que o sistema estiver funcionando.

| # | Tarefa | Status |
|---|--------|--------|
| 7.1 | Transcrição de mensagem de voz (WhatsApp) | ⬜ |
| 7.2 | OCR para notas fiscais em foto | ⬜ |
| 7.3 | Exportar relatórios em PDF | ⬜ |
| 7.4 | Multi-idioma automático aprimorado | ⬜ |
| 7.5 | Painel do dono (Lucas) — ver todos os clientes | ⬜ |
| 7.6 | Adicionar segundo agente quando necessário | ⬜ |
| 7.7 | Integração Open Finance (conectar banco direto) | ⬜ |

---

## PROGRESSO GERAL

```
Fase 1 — Fundação          ██████████  100% ✅
Fase 2 — API               ██████████  100% ✅
Fase 3 — Documentos        ██████████  100% ✅
Fase 4 — Workers           ██████████  100% ✅
Fase 5 — Dashboard         ██████████  100% ✅
Fase 6 — Deploy (infra)    █████████░   90% ✅ (execução no servidor pendente)
Fase 7 — Extras            ░░░░░░░░░░    0%

TOTAL: █████████░  ~90% concluído
```

---

## SESSÕES DE DESENVOLVIMENTO

| Data | O que foi feito |
|------|----------------|
| 19/03/2026 | Planejamento completo, Fase 1 inteira concluída, repo GitHub criado |
| 19/03/2026 | Fase 2 completa: auth JWT, chat HTTP+WS, webhooks WhatsApp+Telegram, CRUD completo, Alembic, seed script |
| 19/03/2026 | Fase 3 completa: pdfplumber + GPT-4o Vision, dedup 4 camadas, bank parser (Nubank/Itaú/Bradesco), import confirm flow |
| 19/03/2026 | Fase 4 completa: Celery + Redis Beat, alert_checker, notification_worker (WhatsApp+Telegram), embedding_indexer, weekly/monthly workers |
| 19/03/2026 | Fase 5 completa: Next.js 14 frontend completo (dashboard, chat, transações, relatórios, alertas, settings) + Admin Panel (agents, WhatsApp QR, tenants) |
| 19/03/2026 | Fase 6 completa: Nginx config (HTTPS, WS, proxy), SSL setup (Let's Encrypt + self-signed), deploy.sh one-command script, ROADMAP atualizado |

---

> **Próxima sessão:** Começar Fase 3 — Leitura de Documentos (PDF + foto de extratos)
