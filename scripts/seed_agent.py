#!/usr/bin/env python3
"""
Seed script — creates the first agent (Rafael Oliveira) in the database.

Run AFTER the database is up:
    docker compose exec backend python scripts/seed_agent.py

Or directly:
    cd backend && python ../scripts/seed_agent.py

The agent is only created if one doesn't already exist.
"""
import asyncio
import sys
import os
import json
import uuid

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text


# ─── Agent definition ──────────────────────────────────────────────────────

AGENT_RAFAEL = {
    "id": str(uuid.uuid4()),
    "name": "Rafael Oliveira",
    "backstory": (
        "Você é Rafael Oliveira, assistente financeiro pessoal com 8 anos de experiência. "
        "Trabalhou com pequenos empreendedores, autônomos e pessoas físicas em todo o Brasil. "
        "É conhecido por ser direto, confiável, e por lembrar de cada detalhe que os clientes contam. "
        "Quando um cliente menciona que vai viajar no mês que vem ou que tem uma conta grande para pagar, "
        "você anota mentalmente e traz de volta quando é relevante. "
        "Você não é um robô — é um profissional de verdade que se preocupa com o bem-estar financeiro "
        "das pessoas que atende."
    ),
    "personality": {
        "tone": "professional_friendly",
        "communication_style": "direct",
        "formality_base": 3,
        "emoji_usage": "low",
        "response_length": "concise",
        "proactivity": "high",
        "strengths": ["analysis", "cash_flow", "reporting", "budgeting"],
        "language": "pt-BR",
    },
    "greeting_templates": [
        "Olá! Aqui é o Rafael. Como posso te ajudar hoje?",
        "Oi! Tudo bem? Sou o Rafael, seu assistente financeiro. No que posso ajudar?",
        "Olá! Rafael aqui. Precisando de ajuda com suas finanças?",
    ],
    "confirmation_style": "brief",
}


# ─── Main ──────────────────────────────────────────────────────────────────

async def seed():
    # Get database URL from environment
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://finagent:finagent@localhost:5432/finagent",
    )

    print(f"🔌 Connecting to database...")
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        # Check if any agent already exists
        result = await conn.execute(text("SELECT COUNT(*) FROM agents"))
        count = result.scalar()

        if count > 0:
            print(f"✅ {count} agent(s) already exist. Skipping seed.")
            print("\nExisting agents:")
            rows = await conn.execute(text("SELECT id, name, is_active, created_at FROM agents"))
            for row in rows.fetchall():
                d = dict(row._mapping)
                status = "✅ active" if d["is_active"] else "❌ inactive"
                print(f"  {status} | {d['name']} | ID: {d['id']}")
        else:
            # Insert first agent
            print(f"🌱 Creating agent: {AGENT_RAFAEL['name']}...")
            await conn.execute(
                text("""
                    INSERT INTO agents (id, name, backstory, personality, greeting_templates, confirmation_style, is_active)
                    VALUES (
                        :id::uuid,
                        :name,
                        :backstory,
                        :personality::jsonb,
                        :greeting_templates::jsonb,
                        :confirmation_style,
                        true
                    )
                """),
                {
                    "id": AGENT_RAFAEL["id"],
                    "name": AGENT_RAFAEL["name"],
                    "backstory": AGENT_RAFAEL["backstory"],
                    "personality": json.dumps(AGENT_RAFAEL["personality"]),
                    "greeting_templates": json.dumps(AGENT_RAFAEL["greeting_templates"]),
                    "confirmation_style": AGENT_RAFAEL["confirmation_style"],
                },
            )
            print(f"✅ Agent created!")
            print(f"   Name: {AGENT_RAFAEL['name']}")
            print(f"   ID: {AGENT_RAFAEL['id']}")
            print()
            print("📋 Next steps:")
            print("   1. Go to the dashboard settings to assign this agent to your clients")
            print("   2. Or use the API: PUT /api/v1/profile → set agent_id")
            print(f"   3. Agent ID to use: {AGENT_RAFAEL['id']}")

    await engine.dispose()
    print("\n🎉 Done!")


if __name__ == "__main__":
    asyncio.run(seed())
