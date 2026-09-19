"""Deterministic escalation engine.

Hard rules (explicit request, payment mention, safety-critical field value,
retry exhaustion) always win and never depend on model judgment. The LLM's
escalation signal (from LLMClient.detect_escalation_signal) is only consulted
for the fuzzier ANGER_FRUSTRATION case, and only as a suggestion — this
function is the single place that produces the final EscalationDecision.
"""

from app.guardrails.advice import is_advice_request
from app.guardrails.payment import mentions_payment
from app.models.journey import EscalationCategory
from app.schemas.extraction import EscalationDecision, EscalationSignal, Intent

LOW_CONFIDENCE_THRESHOLD = 0.5


def evaluate_escalation(
    *,
    intent: Intent,
    utterance: str,
    llm_signal: EscalationSignal,
    field_retries_exhausted: bool,
    safety_critical_value_hit: bool,
    off_script_repeat_count: int,
    advice_repeat_count: int,
) -> EscalationDecision:
    # 1. Explicit ask for a human — always wins, no threshold.
    if intent.intent == "request_human":
        return EscalationDecision(
            should_escalate=True,
            category=EscalationCategory.CUSTOMER_REQUEST,
            reason="Customer explicitly asked to speak to a person.",
            confidence=intent.confidence,
            evidence=intent.evidence,
        )

    # 2. Payment / card data — never collected, always escalated immediately.
    if intent.intent == "payment_mention" or mentions_payment(utterance):
        return EscalationDecision(
            should_escalate=True,
            category=EscalationCategory.SENSITIVE_PAYMENT,
            reason="Customer raised payment/card details, which this channel cannot collect.",
            confidence=0.95,
            evidence=f"customer said: '{utterance.strip()}'",
        )

    # 3. Safety-critical field value (e.g. life support = yes) — vulnerable customer.
    if safety_critical_value_hit:
        return EscalationDecision(
            should_escalate=True,
            category=EscalationCategory.OTHER_SAFETY_BOUNDARY,
            reason="A safety-critical field indicates a vulnerable customer (e.g. life support).",
            confidence=1.0,
            evidence="safety-critical field value matched an escalate-on-value rule",
        )

    # 4. Repeated mishear/failure to capture the same field.
    if field_retries_exhausted:
        return EscalationDecision(
            should_escalate=True,
            category=EscalationCategory.CONFUSION_REPEATED_FAILURE,
            reason="Failed to capture the same field after the maximum allowed retries.",
            confidence=0.85,
            evidence=f"customer said: '{utterance.strip()}'",
        )

    # 5. Anger/frustration — LLM-assisted signal.
    if llm_signal.category == EscalationCategory.ANGER_FRUSTRATION and llm_signal.confidence >= 0.6:
        return EscalationDecision(
            should_escalate=True,
            category=EscalationCategory.ANGER_FRUSTRATION,
            reason="Customer sentiment indicates frustration or anger.",
            confidence=llm_signal.confidence,
            evidence=llm_signal.evidence,
        )

    # 6. Off-script questions repeated more than once.
    if off_script_repeat_count >= 2:
        return EscalationDecision(
            should_escalate=True,
            category=EscalationCategory.OFF_SCRIPT,
            reason="Customer repeatedly asked questions outside the script's scope.",
            confidence=0.7,
            evidence=f"customer said: '{utterance.strip()}'",
        )

    # 7. Advice requests — first one is redirected by the advice guardrail, not
    # escalated; repeating it is treated as off-script product-advice pressure.
    if is_advice_request(utterance) and advice_repeat_count >= 1:
        return EscalationDecision(
            should_escalate=True,
            category=EscalationCategory.OFF_SCRIPT,
            reason="Customer repeated a request for product/financial advice after being redirected.",
            confidence=0.7,
            evidence=f"customer said: '{utterance.strip()}'",
        )

    # 8. Low confidence with no other explanation.
    if intent.confidence < LOW_CONFIDENCE_THRESHOLD:
        return EscalationDecision(
            should_escalate=True,
            category=EscalationCategory.LOW_CONFIDENCE,
            reason="Agent has low confidence in understanding what the customer said or wants.",
            confidence=1 - intent.confidence,
            evidence=f"customer said: '{utterance.strip()}'",
        )

    return EscalationDecision(should_escalate=False, category=None, reason="", confidence=0.0, evidence="")
