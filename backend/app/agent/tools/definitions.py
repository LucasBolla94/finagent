"""
Tool definitions in OpenAI/OpenRouter function-calling format.
These are sent to the AI model so it knows what actions it can take.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_transaction",
            "description": "Registra uma nova transação financeira (receita, despesa ou transferência). Sempre confirme com o cliente antes de chamar esta função.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_type": {
                        "type": "string",
                        "enum": ["income", "expense", "transfer"],
                        "description": "Tipo: income=receita, expense=despesa, transfer=transferência"
                    },
                    "amount": {"type": "number", "description": "Valor em reais (sempre positivo)"},
                    "description": {"type": "string", "description": "Descrição da transação"},
                    "category_name": {"type": "string", "description": "Nome da categoria (ex: 'Energia Elétrica', 'Alimentação')"},
                    "account_name": {"type": "string", "description": "Nome da conta bancária. Se não especificado, usa a conta principal."},
                    "date": {"type": "string", "description": "Data no formato YYYY-MM-DD. Se não informado, usa hoje."},
                    "status": {
                        "type": "string",
                        "enum": ["paid", "pending", "scheduled"],
                        "description": "paid=pago/recebido, pending=a pagar/receber, scheduled=agendado"
                    },
                    "notes": {"type": "string", "description": "Observações adicionais"},
                },
                "required": ["transaction_type", "amount", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": "Retorna o saldo atual de uma ou todas as contas do cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_name": {
                        "type": "string",
                        "description": "Nome da conta. Se vazio, retorna saldo de todas as contas."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "Lista transações com filtros. Use para consultas como 'quanto gastei este mês', 'últimas despesas', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Data início YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "Data fim YYYY-MM-DD"},
                    "transaction_type": {"type": "string", "enum": ["income", "expense", "transfer", "all"]},
                    "category_name": {"type": "string"},
                    "status": {"type": "string", "enum": ["paid", "pending", "all"]},
                    "limit": {"type": "integer", "default": 10, "description": "Máximo de registros"},
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "Gera relatório financeiro: DRE, fluxo de caixa, resumo por categoria, ou resumo mensal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "enum": ["monthly_summary", "dre", "cash_flow", "category_breakdown", "pending_bills"],
                        "description": "Tipo do relatório"
                    },
                    "start_date": {"type": "string", "description": "Data início (padrão: início do mês atual)"},
                    "end_date": {"type": "string", "description": "Data fim (padrão: hoje)"},
                },
                "required": ["report_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_history",
            "description": "Busca semântica no histórico financeiro e de conversas do cliente. Use para perguntas como 'quando paguei a conta de luz?', 'quanto gastei em viagens?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "O que buscar (linguagem natural)"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_balance",
            "description": "Prevê o saldo futuro baseado no histórico e contas pendentes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "default": 30, "description": "Dias para projetar"},
                    "account_name": {"type": "string", "description": "Conta específica ou todas"},
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_alert",
            "description": "Cria um alerta automático que notifica o cliente quando uma condição for atingida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_type": {
                        "type": "string",
                        "enum": ["low_balance", "bill_due", "spending_limit", "custom"],
                    },
                    "name": {"type": "string", "description": "Nome do alerta"},
                    "threshold": {"type": "number", "description": "Valor limite"},
                    "account_name": {"type": "string"},
                    "message": {"type": "string", "description": "Mensagem personalizada do alerta"},
                },
                "required": ["alert_type", "name", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_transaction",
            "description": "Corrige ou atualiza uma transação existente (valor, categoria, data, status).",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "description": {"type": "string"},
                    "category_name": {"type": "string"},
                    "date": {"type": "string"},
                    "status": {"type": "string", "enum": ["paid", "pending", "cancelled"]},
                    "notes": {"type": "string"},
                },
                "required": ["transaction_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_client_context",
            "description": "Retorna um resumo completo do perfil financeiro atual do cliente: contas, saldos, resumo do mês, próximos vencimentos.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
]
