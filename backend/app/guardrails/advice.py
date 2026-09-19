ADVICE_KEYWORDS = [
    "which plan should i", "what do you recommend", "which is better",
    "what would you suggest", "should i choose", "best plan for me",
    "what should i do", "which one is best",
    "कौन सा प्लान", "क्या सुझाव", "कौन सा बेहतर",
    "aling plano", "ano ang irerekomenda", "alin ang mas maganda",
]

# The refusal line itself lives in each script's `phrases.advice_refusal` —
# this module only detects, it doesn't speak.


def is_advice_request(utterance: str) -> bool:
    lowered = utterance.lower()
    return any(kw in lowered for kw in ADVICE_KEYWORDS)
