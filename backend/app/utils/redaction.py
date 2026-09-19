import re

CARD_NUMBER_RE = re.compile(r"(?:\d[ -]*?){13,19}")
CVV_CONTEXT_RE = re.compile(r"(cvv|cvc)\s*[:\-]?\s*\d{3,4}", re.IGNORECASE)


def redact_sensitive(text: str) -> str:
    """Strip anything that looks like a card number or CVV before it's ever
    logged, stored in a transcript, or shown in the ops console. Guardrail:
    "no card data by voice" — this is the defense-in-depth backstop in case
    a customer volunteers one anyway before the agent can redirect.
    """
    redacted = CARD_NUMBER_RE.sub("[REDACTED CARD NUMBER]", text)
    redacted = CVV_CONTEXT_RE.sub("[REDACTED CVV]", redacted)
    return redacted
