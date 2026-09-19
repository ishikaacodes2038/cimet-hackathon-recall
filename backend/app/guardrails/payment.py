import re

CARD_NUMBER_RE = re.compile(r"(?:\d[ -]*?){13,19}")

# STT frequently transcribes a customer reading their card number aloud one
# digit at a time as number WORDS ("four... two... two... two...") rather
# than numerals, especially with pauses between groups — CARD_NUMBER_RE
# never sees a single \d in that case. A long run of consecutive digit-words
# is exactly as suspicious as a long run of numeral digits.
_DIGIT_WORDS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_SPOKEN_DIGIT_RUN_THRESHOLD = 12


def _has_long_spoken_digit_run(utterance: str) -> bool:
    tokens = re.findall(r"[a-zA-Z]+", utterance.lower())
    run = 0
    for tok in tokens:
        run = run + 1 if tok in _DIGIT_WORDS else 0
        if run >= _SPOKEN_DIGIT_RUN_THRESHOLD:
            return True
    return False
PAYMENT_KEYWORDS = [
    "card number", "credit card", "debit card", "cvv", "cvc", "card details",
    "bank account number", "sort code", "routing number", "expiry date",
    "gift card value", "pay now", "take a payment", "process a payment",
    "कार्ड नंबर", "क्रेडिट कार्ड", "डेबिट कार्ड",
    "numero ng card", "credit card number", "debit card number",
]

# The refusal line itself lives in each script's `phrases.payment_refusal`.
# Real CIMET-family calls handle payment by muting the recording and
# directing the customer to enter card details into a self-service web form
# (confirmed by the redaction notes on the reference transcript) — an AI
# voice agent has no "mute" available, so it escalates instead, but the
# phrase reflects the same self-service-link pattern rather than only
# offering a live human transfer.


def mentions_payment(utterance: str) -> bool:
    lowered = utterance.lower()
    if CARD_NUMBER_RE.search(utterance):
        return True
    if _has_long_spoken_digit_run(utterance):
        return True
    return any(kw in lowered for kw in PAYMENT_KEYWORDS)
