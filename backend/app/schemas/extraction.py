from typing import Optional

from pydantic import BaseModel, Field

from app.models.journey import EscalationCategory

# Every confidence score in this module is clamped to [0, 1] at the schema
# level — a structural guarantee, not just a convention both LLMClient
# implementations are trusted to follow. This matters because
# RuleBasedLLMClient's confidence values are hand-picked constants
# (0.4-0.9, see llm_client.py) tuned against LOW_CONFIDENCE_THRESHOLD=0.5 in
# escalation.py, while AnthropicLLMClient asks a live Claude call to invent
# its own confidence float per extraction/classification with no fixed
# reference scale. Bounding the field here prevents a wildly out-of-range
# value from silently breaking the "< 0.5" comparisons; it does NOT confirm
# the two clients' confidence DISTRIBUTIONS behave comparably in practice
# (e.g. Claude being systematically more or less "confident" than the
# rule-based constants for equivalent inputs) — that needs an empirical
# check against a live API key (run both clients over the same evaluation
# transcripts and compare), which this offline-only build environment
# cannot do. Flagged, not silently assumed.
Confidence = Field(ge=0.0, le=1.0)


class FieldExtraction(BaseModel):
    field: str
    value: Optional[str] = None
    confidence: float = Confidence
    evidence: str


class ExtractionResult(BaseModel):
    extractions: list[FieldExtraction] = []


class Intent(BaseModel):
    intent: str
    confidence: float = Confidence
    evidence: str = ""


class EscalationSignal(BaseModel):
    """LLM-assisted signal only — the final should_escalate decision is made
    deterministically in services/escalation.py, which combines this with
    hard rules (retry limits, payment keywords, safety-critical field values)
    that must never depend on model judgment alone.
    """

    category: Optional[EscalationCategory] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str = ""


class EscalationDecision(BaseModel):
    should_escalate: bool
    category: Optional[EscalationCategory] = None
    reason: str
    confidence: float = Confidence
    evidence: str
