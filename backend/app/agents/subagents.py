"""Specialist sub-agents, coordinated by ConversationOrchestrator acting as
the supervisor. Each one owns exactly one narrow LLM-backed responsibility
and nothing else — no sub-agent can touch journey state directly; each
returns a typed proposal that the supervisor validates and applies (or
overrides) with deterministic code. This is what "multi-agent orchestration"
means in this build: a supervisor delegating to specialists, not a single
do-everything prompt, and not autonomous agents with their own side effects.

All three are thin wrappers over the same underlying LLMClient (rule-based
offline, or Claude when configured) — the specialization is architectural
(one class, one job, one call site) rather than requiring separate models
or processes, which would add latency and cost with no benefit at this scale.
"""

from app.models.script import FieldScript
from app.schemas.extraction import EscalationSignal, ExtractionResult, Intent
from app.services.llm_client import LLMClient


class ExtractionAgent:
    """Turns a customer utterance into zero or more structured field
    proposals, each with a confidence score and the exact words it came
    from. Never decides what happens with them — that's the supervisor's job
    (validate, accept, reject, or flag for escalation)."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def propose(
        self, missing_fields: list[FieldScript], asked_field, utterance: str, context: str
    ) -> ExtractionResult:
        return self._llm.extract_fields(missing_fields, asked_field, utterance, context)


class IntentAgent:
    """Classifies what the customer is doing with this turn — answering,
    asking for a human, refusing, showing frustration, etc. One label, one
    confidence score; the supervisor owns all branching on it."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def classify(self, utterance: str) -> Intent:
        return self._llm.classify_intent(utterance)


class EscalationSignalAgent:
    """Produces a raw escalation *signal* (e.g. "this reads as angry") from
    the model's read of the conversation. This is a proposal, not a
    decision — app/services/escalation.py's deterministic evaluate_escalation
    is the only place that actually decides to escalate, combining this
    signal with hard rules (retry limits, payment keywords, safety-critical
    field values) that must never depend on model judgment alone."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def propose(self, utterance: str, recent_context: str) -> EscalationSignal:
        return self._llm.detect_escalation_signal(utterance, recent_context)


class SummarizationAgent:
    """Produces the human-readable call summary for a warm-handoff packet.
    Always has a deterministic fallback (the collected-fields summary) if
    this fails or times out — a handoff must never be blocked by an LLM outage."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def summarize(self, transcript_text: str, deterministic_fallback: str) -> str:
        try:
            return self._llm.summarize(transcript_text, deterministic_fallback)
        except Exception:
            return deterministic_fallback
