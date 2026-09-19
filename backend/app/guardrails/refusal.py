REFUSAL_KEYWORDS = [
    "not interested", "stop calling", "don't call", "do not call", "no thanks",
    "leave me alone", "remove me", "unsubscribe", "take me off",
    "दिलचस्पी नहीं", "कॉल मत करो", "फोन मत करो",
    "hindi interesado", "wag na tumawag", "huwag nang tumawag",
]

BUSY_KEYWORDS = [
    "i'm busy", "im busy", "can't talk", "cant talk", "not a good time", "call back later",
    "व्यस्त हूं", "अभी बात नहीं कर सकता",
    "busy ako", "di ako pwede ngayon",
]

# Close/reschedule lines live in each script's `phrases` block.


def is_hard_refusal(utterance: str) -> bool:
    lowered = utterance.lower()
    return any(kw in lowered for kw in REFUSAL_KEYWORDS)


def is_busy_deferral(utterance: str) -> bool:
    lowered = utterance.lower()
    return any(kw in lowered for kw in BUSY_KEYWORDS)
