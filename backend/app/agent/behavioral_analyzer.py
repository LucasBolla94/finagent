"""
Behavioral Analyzer — The Intelligence Behind Human-Like Bonding

This module analyzes every message from a client and builds a behavioral profile
that the agent uses to adapt its tone, style, length, and approach over time.

The goal: make every client feel like the agent has known them for years.

How it works:
1. Every incoming message is analyzed for signals
2. These signals update the client's behavioral profile (with smoothing)
3. Before each response, the agent receives dynamic instructions based on the profile
4. Over time, the agent naturally mirrors the client's communication style
"""

import re
from typing import Optional
from datetime import datetime, time
import json
import logging

logger = logging.getLogger(__name__)


# --- Signal Weights ---
# How much each new message influences the rolling profile (0-1)
# Lower = slower adaptation (more stable), Higher = faster adaptation
ADAPTATION_RATE = 0.15


class MessageSignals:
    """Signals extracted from a single message."""

    def __init__(
        self,
        formality: float,           # 1.0 = very informal, 5.0 = very formal
        urgency: float,             # 1.0 = relaxed, 5.0 = very urgent
        sentiment: str,             # positive | neutral | negative | anxious
        length: int,                # character count
        emoji_count: int,
        question_count: int,
        uses_punctuation: bool,
        hour_of_day: int,
        language: str,              # pt-BR | en | es | auto
    ):
        self.formality = formality
        self.urgency = urgency
        self.sentiment = sentiment
        self.length = length
        self.emoji_count = emoji_count
        self.question_count = question_count
        self.uses_punctuation = uses_punctuation
        self.hour_of_day = hour_of_day
        self.language = language


class BehavioralProfile:
    """
    The living profile of how a client communicates.
    Updated after every message. Used to generate dynamic agent instructions.
    """

    def __init__(self, data: Optional[dict] = None):
        d = data or {}
        # Communication style (rolling averages)
        self.formality_avg: float = d.get("formality_avg", 2.5)
        self.urgency_avg: float = d.get("urgency_avg", 2.0)
        self.avg_message_length: float = d.get("avg_message_length", 100.0)
        self.emoji_frequency: float = d.get("emoji_frequency", 0.0)  # 0-1

        # Temporal patterns
        self.active_hours: list[int] = d.get("active_hours", [])
        self.most_active_hour: Optional[int] = d.get("most_active_hour", None)

        # Sentiment trend
        self.sentiment_history: list[str] = d.get("sentiment_history", [])
        self.dominant_sentiment: str = d.get("dominant_sentiment", "neutral")

        # Stress / anxiety indicators
        self.stress_words: list[str] = d.get("stress_words", [])
        self.anxiety_triggers: list[str] = d.get("anxiety_triggers", [])

        # Preferred language (detected automatically)
        self.preferred_language: str = d.get("preferred_language", "auto")

        # Rapport level — how close the relationship has become
        self.rapport_level: float = d.get("rapport_level", 0.0)  # 0-100
        self.total_interactions: int = d.get("total_interactions", 0)

        # Evolution tracking
        self.formality_trend: str = d.get("formality_trend", "stable")  # becoming_more_casual | stable | becoming_more_formal

    def to_dict(self) -> dict:
        return {
            "formality_avg": round(self.formality_avg, 2),
            "urgency_avg": round(self.urgency_avg, 2),
            "avg_message_length": round(self.avg_message_length, 1),
            "emoji_frequency": round(self.emoji_frequency, 3),
            "active_hours": self.active_hours[-20:],  # keep last 20 data points
            "most_active_hour": self.most_active_hour,
            "sentiment_history": self.sentiment_history[-30:],
            "dominant_sentiment": self.dominant_sentiment,
            "stress_words": list(set(self.stress_words))[:20],
            "anxiety_triggers": list(set(self.anxiety_triggers))[:10],
            "preferred_language": self.preferred_language,
            "rapport_level": round(self.rapport_level, 1),
            "total_interactions": self.total_interactions,
            "formality_trend": self.formality_trend,
        }

    def update(self, signals: MessageSignals) -> None:
        """Update profile using exponential moving average — recent behavior weighs more."""
        prev_formality = self.formality_avg

        # Smooth update (EMA)
        self.formality_avg = (
            (1 - ADAPTATION_RATE) * self.formality_avg + ADAPTATION_RATE * signals.formality
        )
        self.urgency_avg = (
            (1 - ADAPTATION_RATE) * self.urgency_avg + ADAPTATION_RATE * signals.urgency
        )
        self.avg_message_length = (
            (1 - ADAPTATION_RATE) * self.avg_message_length + ADAPTATION_RATE * signals.length
        )

        # Emoji frequency
        msg_has_emoji = 1.0 if signals.emoji_count > 0 else 0.0
        self.emoji_frequency = (
            (1 - ADAPTATION_RATE) * self.emoji_frequency + ADAPTATION_RATE * msg_has_emoji
        )

        # Active hours
        self.active_hours.append(signals.hour_of_day)
        if len(self.active_hours) > 0:
            hour_counts = {}
            for h in self.active_hours[-50:]:  # last 50 interactions
                hour_counts[h] = hour_counts.get(h, 0) + 1
            self.most_active_hour = max(hour_counts, key=hour_counts.get)

        # Sentiment
        self.sentiment_history.append(signals.sentiment)
        if len(self.sentiment_history) >= 5:
            recent = self.sentiment_history[-10:]
            from collections import Counter
            self.dominant_sentiment = Counter(recent).most_common(1)[0][0]

        # Language detection
        if signals.language != "auto":
            self.preferred_language = signals.language

        # Rapport grows with each interaction
        self.total_interactions += 1
        rapport_gain = 0.5 if signals.sentiment == "positive" else 0.2
        self.rapport_level = min(100.0, self.rapport_level + rapport_gain)

        # Formality trend
        if self.formality_avg < prev_formality - 0.1:
            self.formality_trend = "becoming_more_casual"
        elif self.formality_avg > prev_formality + 0.1:
            self.formality_trend = "becoming_more_formal"
        else:
            self.formality_trend = "stable"

    def generate_agent_instructions(self, agent_name: str) -> str:
        """
        Generates dynamic instructions injected into the agent's system prompt.
        This is how the agent knows HOW to talk to this specific client right now.
        """
        first_name = agent_name.split()[0]
        instructions = [f"\n## COMO SE COMUNICAR COM ESTE CLIENTE AGORA\n"]

        # Formality adaptation
        if self.formality_avg <= 2.0:
            instructions.append(
                "Tom: Muito informal. Use linguagem casual, pode usar gírias leves. "
                "Trate como um amigo próximo."
            )
        elif self.formality_avg <= 3.0:
            instructions.append(
                "Tom: Informal-amigável. Direto e descontraído, mas profissional. "
                "É o tom natural de quem se conhece há tempo."
            )
        elif self.formality_avg <= 4.0:
            instructions.append(
                "Tom: Semi-formal. Profissional mas acessível. Evite ser frio."
            )
        else:
            instructions.append(
                "Tom: Formal. Este cliente prefere comunicação mais estruturada e profissional."
            )

        # Message length mirroring
        if self.avg_message_length < 50:
            instructions.append(
                "Comprimento: Mensagens CURTAS. Cliente é direto — espelhe isso. "
                "Máximo 2-3 linhas por resposta na maioria dos casos."
            )
        elif self.avg_message_length < 150:
            instructions.append(
                "Comprimento: Mensagens MÉDIAS. Seja objetivo mas completo."
            )
        else:
            instructions.append(
                "Comprimento: Cliente escreve bastante — pode dar mais detalhes nas respostas."
            )

        # Emoji usage
        if self.emoji_frequency > 0.5:
            instructions.append("Emojis: Cliente usa bastante — use com moderação e naturalidade.")
        elif self.emoji_frequency > 0.2:
            instructions.append("Emojis: Use ocasionalmente, quando fizer sentido.")
        else:
            instructions.append("Emojis: Evite ou use muito raramente — cliente não usa.")

        # Sentiment / emotional state
        if self.dominant_sentiment == "anxious":
            instructions.append(
                "Estado emocional: Cliente tende a ser ansioso com finanças. "
                "Seja tranquilizador, apresente soluções antes dos problemas."
            )
        elif self.dominant_sentiment == "negative":
            instructions.append(
                "Estado emocional: Cliente está em momento difícil. "
                "Seja empático, prático, foque em ações concretas."
            )

        # Rapport level
        if self.rapport_level < 10:
            instructions.append(
                f"Relacionamento: Início da relação. {first_name} ainda está construindo confiança. "
                "Seja mais cuidadoso, explique mais, faça perguntas para conhecer melhor."
            )
        elif self.rapport_level < 40:
            instructions.append(
                f"Relacionamento: Relação em desenvolvimento. "
                "Pode ser um pouco mais familiar, já se conhecem bem."
            )
        elif self.rapport_level < 70:
            instructions.append(
                "Relacionamento: Boa relação estabelecida. "
                "Pode ser mais direto, já conhece bem as preferências do cliente."
            )
        else:
            instructions.append(
                "Relacionamento: Relação sólida e próxima. "
                "Fale como alguém que se conhece há anos. Natural, confiante."
            )

        # Active hours context
        now_hour = datetime.now().hour
        if self.most_active_hour and abs(now_hour - self.most_active_hour) > 4:
            instructions.append(
                f"Timing: Cliente geralmente é ativo por volta das {self.most_active_hour}h — "
                "está fora do seu horário usual. Pode estar ocupado ou com algo urgente."
            )

        return "\n".join(instructions)


class BehavioralAnalyzer:
    """
    Analyzes incoming messages and extracts behavioral signals.
    Works entirely offline — no AI call needed for basic analysis.
    For deeper sentiment analysis, uses the AI model.
    """

    # Portuguese informal indicators
    INFORMAL_INDICATORS = [
        r'\bvc\b', r'\bpra\b', r'\bta\b', r'\btá\b', r'\bné\b', r'\brsrs\b',
        r'\bkkk+\b', r'\bhuahua\b', r'\bobg\b', r'\bvlw\b', r'\bfala\b',
        r'\bsaudades\b', r'\bcaramba\b', r'\bbicho\b', r'\bmano\b'
    ]

    FORMAL_INDICATORS = [
        r'\bsenhor\b', r'\bsenhora\b', r'\bcordialmente\b', r'\batenciosamente\b',
        r'\bprezado\b', r'\bvenho por meio\b', r'\bsolicito\b', r'\bpedido formal\b'
    ]

    URGENCY_INDICATORS = [
        r'\burgente\b', r'\bemerg[eê]ncia\b', r'\br[aá]pido\b', r'\bagora\b',
        r'\bjá\b', r'\bimediato\b', r'\bdesesperado\b', r'\bcrisis\b',
        r'\!{2,}', r'\bsocorro\b', r'\bpreciso hoje\b'
    ]

    ANXIETY_WORDS = [
        'preocupado', 'nervoso', 'ansioso', 'medo', 'assustado', 'perdido',
        'confuso', 'dívida', 'devendo', 'negativado', 'inadimplente',
        'stressed', 'worried', 'scared'
    ]

    POSITIVE_WORDS = [
        'ótimo', 'excelente', 'perfeito', 'maravilhoso', 'feliz', 'animado',
        'consegui', 'ganhei', 'aprovado', 'lucro', 'great', 'perfect', 'amazing'
    ]

    EMOJI_PATTERN = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0\U000024C2-\U0001F251]+",
        flags=re.UNICODE
    )

    def analyze(self, message: str, sent_at: Optional[datetime] = None) -> MessageSignals:
        """Extract behavioral signals from a single message."""
        msg_lower = message.lower()
        hour = (sent_at or datetime.now()).hour

        # Formality score (1-5)
        informal_score = sum(1 for p in self.INFORMAL_INDICATORS if re.search(p, msg_lower))
        formal_score = sum(1 for p in self.FORMAL_INDICATORS if re.search(p, msg_lower))
        has_proper_caps = message[0].isupper() if message else False

        formality = 2.5  # neutral start
        formality -= informal_score * 0.4
        formality += formal_score * 0.5
        formality += 0.3 if has_proper_caps else 0
        formality = max(1.0, min(5.0, formality))

        # Urgency score (1-5)
        urgency_matches = sum(1 for p in self.URGENCY_INDICATORS if re.search(p, msg_lower))
        urgency = min(5.0, 1.0 + urgency_matches * 1.0)

        # Sentiment detection
        anxiety_count = sum(1 for w in self.ANXIETY_WORDS if w in msg_lower)
        positive_count = sum(1 for w in self.POSITIVE_WORDS if w in msg_lower)

        if anxiety_count > positive_count and anxiety_count > 0:
            sentiment = "anxious"
        elif positive_count > anxiety_count and positive_count > 0:
            sentiment = "positive"
        elif urgency >= 3:
            sentiment = "stressed"
        else:
            sentiment = "neutral"

        # Emojis
        emojis = self.EMOJI_PATTERN.findall(message)
        emoji_count = len(emojis)

        # Questions
        question_count = message.count('?')

        # Language detection (basic)
        language = self._detect_language(msg_lower)

        return MessageSignals(
            formality=formality,
            urgency=urgency,
            sentiment=sentiment,
            length=len(message),
            emoji_count=emoji_count,
            question_count=question_count,
            uses_punctuation=bool(re.search(r'[.,;!?]', message)),
            hour_of_day=hour,
            language=language,
        )

    def _detect_language(self, text: str) -> str:
        """Basic language detection without external libraries."""
        pt_words = ['de', 'que', 'para', 'com', 'uma', 'não', 'por', 'como', 'mas', 'eu', 'você', 'ele']
        en_words = ['the', 'and', 'for', 'with', 'that', 'this', 'not', 'are', 'you', 'have']
        es_words = ['que', 'para', 'con', 'una', 'por', 'como', 'pero', 'yo', 'usted', 'él']

        words = text.split()
        pt_count = sum(1 for w in words if w in pt_words)
        en_count = sum(1 for w in words if w in en_words)
        es_count = sum(1 for w in words if w in es_words)

        scores = {'pt-BR': pt_count, 'en': en_count, 'es': es_count}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else 'pt-BR'  # default to PT-BR
