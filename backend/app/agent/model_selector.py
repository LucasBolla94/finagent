"""
Model Selector — Smart routing to the right AI model per task.

Cheap/fast models for simple tasks.
Powerful models for analysis, reports, and complex decisions.
Vision models for PDF and image processing.
"""

import re
from app.config import settings


class ModelSelector:

    # Keywords that indicate complex analysis needed
    COMPLEX_PATTERNS = [
        r'\brelat[oó]rio\b', r'\bDRE\b', r'\bbal[aâ]n[cç]o\b',
        r'\bfluxo de caixa\b', r'\bprevis[aã]o\b', r'\ban[aá]lise\b',
        r'\btend[eê]ncia\b', r'\bcompar[ae]\b', r'\bprojet[ao]\b',
        r'\bdetalhado\b', r'\bexplica[rq]\b', r'\bpor que\b',
    ]

    # Keywords for simple/fast tasks
    SIMPLE_PATTERNS = [
        r'\bsaldo\b', r'\bquanto\b', r'\bpaguei\b', r'\brecebi\b',
        r'\blancei\b', r'\bokay\b', r'\bsim\b', r'\bn[aã]o\b',
        r'\bobrigad[oa]\b', r'\bvaleu\b', r'\bblz\b',
    ]

    def select(self, message: str, history: list[dict]) -> str:
        msg_lower = message.lower()
        msg_len = len(message)

        # Very short message = fast model
        if msg_len < 30:
            return settings.MODEL_FAST

        # Complex analysis keywords
        complex_count = sum(
            1 for p in self.COMPLEX_PATTERNS if re.search(p, msg_lower)
        )
        if complex_count >= 2:
            return settings.MODEL_POWERFUL

        # Simple keywords
        simple_count = sum(
            1 for p in self.SIMPLE_PATTERNS if re.search(p, msg_lower)
        )
        if simple_count >= 2 and complex_count == 0:
            return settings.MODEL_FAST

        # Long message or has financial keywords = standard
        if msg_len > 200:
            return settings.MODEL_STANDARD

        # Default: standard
        return settings.MODEL_STANDARD

    def select_for_vision(self) -> str:
        """Model for reading PDFs and images."""
        return settings.MODEL_VISION

    def select_for_extraction(self) -> str:
        """Model for background intelligence extraction (cheap)."""
        return settings.MODEL_FAST
