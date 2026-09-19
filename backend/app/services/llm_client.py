"""LLM client abstraction.

Two implementations:
  - RuleBasedLLMClient: deterministic, zero external dependency. Used whenever
    no LLM_API_KEY is configured, and as the engine behind the offline
    evaluation suite (tests must not depend on a live API call).
  - AnthropicLLMClient: real structured-output calls via Claude tool-calling.

Both implement the same interface, so swapping one for the other never
touches orchestrator/state-machine code — matching the "no external
dependency should block development" rule from the project brief.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

from app.models.script import FieldScript
from app.schemas.extraction import EscalationSignal, ExtractionResult, FieldExtraction, Intent
from app.services.date_parsing import find_date_span

logger = logging.getLogger("cimet.llm")


class LLMClient(ABC):
    @abstractmethod
    def extract_fields(
        self,
        missing_fields: list[FieldScript],
        asked_field: Optional[FieldScript],
        utterance: str,
        context: str,
    ) -> ExtractionResult: ...

    @abstractmethod
    def classify_intent(self, utterance: str) -> Intent: ...

    @abstractmethod
    def detect_escalation_signal(self, utterance: str, recent_context: str) -> EscalationSignal: ...

    @abstractmethod
    def summarize(self, transcript_text: str, collected_summary: str) -> str: ...


# ---------------------------------------------------------------------------
# Rule-based (default / offline) implementation
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    # Each list mixes English, Hindi (Devanagari + common transliteration),
    # and Filipino/Tagalog phrases — the rule-based fallback's best-effort
    # multilingual coverage. A live Claude call (AnthropicLLMClient) handles
    # this natively and far more robustly; this hardcoded list only exists so
    # the offline fallback isn't English-only.
    "request_human": [
        "speak to a person", "speak to someone", "talk to a human", "talk to a person",
        "real person", "human agent", "speak to a manager", "get me a human",
        "transfer me", "put me through to", "connect me to a person", "connect me with a person",
        "connect me to someone", "connect me with someone", "connect me to a human",
        "someone who can help", "speak with a representative", "talk to somebody",
        "इंसान से बात", "व्यक्ति से बात", "किसी और से बात", "एजेंट से बात करा",
        "makausap ang tao", "kausapin ang tao", "kumausap ng tao", "totoong tao",
    ],
    "refuse_decline": [
        "not interested", "stop calling", "don't call", "do not call", "no thanks",
        "i'm busy", "im busy", "can't talk", "cant talk", "not now", "leave me alone",
        "remove me", "unsubscribe",
        "दिलचस्पी नहीं", "कॉल मत करो", "फोन मत करो", "व्यस्त हूं", "अभी बात नहीं कर सकता",
        "hindi interesado", "wag na tumawag", "huwag nang tumawag", "busy ako", "di ako pwede ngayon",
    ],
    "anger_frustration": [
        "ridiculous", "already told you", "told you three times", "told this",
        "this is the second call", "waste of time", "fed up", "sick of",
        "unacceptable", "furious", "angry", "annoyed", "frustrat",
        "पहले ही बता चुका", "तीन बार बता चुका", "बेकार है", "परेशान हो गया",
        "gulo naman", "sinabi ko na", "nakakainis", "nakakagalit", "galit na ako",
    ],
    "payment_mention": [
        "card number", "credit card", "debit card", "cvv", "cvc", "card details",
        "bank account number", "sort code", "routing number", "expiry date of my card",
        "कार्ड नंबर", "क्रेडिट कार्ड", "डेबिट कार्ड",
        "numero ng card", "credit card number", "debit card number",
    ],
    "advice_request": [
        "which plan should i", "what do you recommend", "which is better",
        "what would you suggest", "should i choose", "best plan for me",
        "कौन सा प्लान", "क्या सुझाव", "कौन सा बेहतर",
        "aling plano", "ano ang irerekomenda", "alin ang mas maganda",
    ],
    "confusion": [
        "don't understand", "dont understand", "what do you mean", "come again",
        "say that again", "repeat that", "not following", "confused",
        "समझ नहीं आया", "फिर से बताओ", "दोबारा कहो",
        "hindi ko maintindihan", "ano ibig sabihin", "ulitin mo", "hindi maintindihan",
    ],
    # Meta-questions about the call itself ("who are you", "is this a scam",
    # "how long will this take") — legitimate, common, and deserve a brief,
    # honest answer before continuing, not a bare repeat of the last question
    # (which reads as the bot ignoring them) and not an OFF_SCRIPT escalation
    # (that's reserved for repeated product/financial advice requests).
    # Deliberately NOT greetings/small-talk ("how are you") — those overlap
    # too easily with a genuine answer being given alongside pleasantries,
    # which would misfire and swallow a real answer.
    "generic_question": [
        "who are you", "who is this", "what is cimet", "what's cimet", "is this cimet",
        "scam", "is this legit", "is this legitimate", "is this real",
        "are you a bot", "are you a robot", "am i talking to a robot", "am i speaking to a robot",
        "am i talking to a real person", "is this recorded", "why is this recorded",
        "how did you get my number", "how did you get my details", "where did you get my number",
        "why do you need this", "why do you need my", "why do you want my", "what do you need this for",
        "how long will this take", "how long does this take", "how long is this going to take",
        "what happens after", "what happens next", "what happens once", "does this work",
        "is this a call center", "is this a call centre",
        "आप कौन हैं", "यह कौन बोल रहा है", "सीमेट क्या है", "क्या यह असली है", "क्या यह धोखा है",
        "क्या यह स्कैम है", "आपको मेरा नंबर कैसे मिला", "क्यों चाहिए", "इसमें कितना समय लगेगा",
        "आगे क्या होगा", "यह कैसे काम करता है",
        "sino ka", "sino ito", "ang cimet", "totoo ba ito", "scam ba ito", "legit ba ito",
        "robot ka ba", "paano mo nakuha ang number ko", "bakit kailangan mo ito", "bakit mo kailangan",
        "gaano katagal ito", "ano ang susunod", "paano ito gumagana",
    ],
}

PROFANITY_MARKERS = ["damn", "hell", "crap", "stupid", "idiot"]

CARD_NUMBER_RE = re.compile(r"(?:\d[ -]*?){13,19}")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
POSTCODE_RE = re.compile(r"\b\d{4}\b")
YES_WORDS = {
    "yes", "yeah", "yep", "correct", "affirmative", "sure", "definitely",
    "हां", "हाँ", "जी", "ठीक", "opo", "oo", "sige",
}
NO_WORDS = {
    "no", "nope", "nah", "negative", "not",
    "नहीं", "नही", "hindi", "wala", "ayaw",
}
DECLINE_TO_PROVIDE = {
    "no", "nope", "nah", "i dont know", "i don't know", "dont know", "not sure",
    "no idea", "i dont have it", "i don't have it", "dont have it", "cant find it",
    "can't find it", "no i dont", "no i don't",
    "नहीं", "पता नहीं", "मालूम नहीं", "नहीं है",
    "hindi ko alam", "wala akong alam", "wala akong ideya", "wala",
}
ENUM_SYNONYMS = {
    "residential": ["आवासीय", "ghar", "bahay", "tirahan"],
    "business": ["व्यावसायिक", "negosyo", "business"],
    "electricity": ["बिजली", "kuryente", "de-kuryente"],
    "gas": ["गैस"],
    "dual": ["दोनों", "pareho", "dalawa"],
}

# Hedging language signals the customer themselves is unsure — captured at low
# confidence so the LOW_CONFIDENCE escalation path is reachable even without
# a live LLM call (the rule-based client would otherwise only ever emit
# confident matches or nothing, making that escalation category unreachable
# whenever the system falls back to offline/rule-based mode).
HEDGE_MARKERS = [
    "i think", "maybe", "not sure but", "something like", "possibly",
    "i guess", "sort of", "kind of", "could be", "i believe",
]


class RuleBasedLLMClient(LLMClient):
    def classify_intent(self, utterance: str) -> Intent:
        lowered = utterance.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw in lowered:
                    return Intent(intent=intent, confidence=0.9, evidence=f"matched phrase '{kw}'")
        return Intent(intent="provide_information", confidence=0.55, evidence="no strong signal; default")

    def extract_fields(
        self,
        missing_fields: list[FieldScript],
        asked_field: Optional[FieldScript],
        utterance: str,
        context: str,
    ) -> ExtractionResult:
        extractions: list[FieldExtraction] = []
        lowered = utterance.lower()

        for field_script in missing_fields:
            vtype = field_script.validation.type
            value: Optional[str] = None
            confidence = 0.0
            evidence = ""

            if vtype == "email":
                match = EMAIL_RE.search(utterance)
                if match:
                    value, confidence, evidence = match.group(0), 0.9, f"customer said: '{utterance.strip()}'"

            elif vtype == "date":
                date_span = find_date_span(utterance)
                if date_span:
                    value, confidence, evidence = date_span, 0.8, f"customer said: '{utterance.strip()}'"

            elif vtype == "postcode_au":
                match = POSTCODE_RE.search(utterance)
                if match:
                    value, confidence, evidence = match.group(0), 0.75, f"customer said: '{utterance.strip()}'"

            elif vtype == "enum":
                for option in field_script.validation.options or []:
                    matched = option.lower() in lowered
                    if not matched:
                        # Non-English synonym still resolves to the canonical
                        # English option, so stored/submitted data stays
                        # consistent regardless of which language the call ran in.
                        matched = any(syn in lowered for syn in ENUM_SYNONYMS.get(option.lower(), []))
                    if matched:
                        value, confidence, evidence = option, 0.85, f"customer said: '{utterance.strip()}'"
                        break

            elif vtype == "yes_no":
                # Only attribute a bare yes/no to this field if it's the one just asked —
                # otherwise a stray "yes" earlier in the call could mis-tag an unrelated field.
                if asked_field and asked_field.field == field_script.field:
                    # \w matches Unicode word characters by default in Python's re
                    # module (no re.ASCII flag), so this also tokenizes Devanagari.
                    tokens = set(re.findall(r"[\w']+", lowered, re.UNICODE))
                    if tokens & YES_WORDS:
                        value, confidence, evidence = "yes", 0.85, f"customer said: '{utterance.strip()}'"
                    elif tokens & NO_WORDS:
                        value, confidence, evidence = "no", 0.85, f"customer said: '{utterance.strip()}'"

            elif vtype == "non_empty":
                # Free text with no fixed shape — only safe to attribute when it's the
                # field we just asked about, and only if the utterance doesn't look like
                # an off-topic remark (very short/keyword-only replies are skipped).
                cleaned = utterance.strip()
                declined = re.sub(r"[^\w\s]", "", cleaned.lower()).strip() in DECLINE_TO_PROVIDE
                if asked_field and asked_field.field == field_script.field and len(cleaned) >= 2 and not declined:
                    hedged = any(marker in lowered for marker in HEDGE_MARKERS)
                    confidence = 0.4 if hedged else 0.65
                    value, evidence = cleaned, f"customer said: '{cleaned}'"

            if value:
                extractions.append(
                    FieldExtraction(field=field_script.field, value=value, confidence=confidence, evidence=evidence)
                )

        return ExtractionResult(extractions=extractions)

    def detect_escalation_signal(self, utterance: str, recent_context: str) -> EscalationSignal:
        from app.models.journey import EscalationCategory

        lowered = utterance.lower()
        anger_hits = sum(1 for kw in INTENT_KEYWORDS["anger_frustration"] if kw in lowered)
        anger_hits += sum(1 for kw in PROFANITY_MARKERS if kw in lowered)
        exclamations = utterance.count("!")

        if anger_hits >= 1 or exclamations >= 2:
            return EscalationSignal(
                category=EscalationCategory.ANGER_FRUSTRATION,
                confidence=min(0.6 + 0.15 * anger_hits, 0.95),
                evidence=f"customer said: '{utterance.strip()}'",
            )
        return EscalationSignal(category=None, confidence=0.0, evidence="")

    def summarize(self, transcript_text: str, collected_summary: str) -> str:
        return collected_summary


# ---------------------------------------------------------------------------
# Anthropic (Claude) implementation — used when LLM_API_KEY is configured
# ---------------------------------------------------------------------------


class AnthropicLLMClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        # Imported lazily so the anthropic package is only required when this
        # client is actually selected.
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._fallback = RuleBasedLLMClient()

    def extract_fields(
        self,
        missing_fields: list[FieldScript],
        asked_field: Optional[FieldScript],
        utterance: str,
        context: str,
    ) -> ExtractionResult:
        if not missing_fields:
            return ExtractionResult(extractions=[])

        tool = {
            "name": "record_extractions",
            "description": "Record any of the target fields whose value is present in the customer's utterance.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "extractions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "value": {"type": "string"},
                                "confidence": {"type": "number"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["field", "value", "confidence", "evidence"],
                        },
                    }
                },
                "required": ["extractions"],
            },
        }
        field_descriptions = "\n".join(
            f"- {f.field}: {f.purpose} (hints: {', '.join(f.extraction_hints)})" for f in missing_fields
        )
        prompt = (
            f"Conversation so far:\n{context}\n\n"
            f"Customer just said: \"{utterance}\"\n\n"
            f"Target fields still missing:\n{field_descriptions}\n\n"
            "Only extract a field if the customer's utterance actually states it. "
            "Do not guess. Do not invent values."
        )
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[tool],
                tool_choice={"type": "tool", "name": "record_extractions"},
                messages=[{"role": "user", "content": prompt}],
            )
            for block in response.content:
                if block.type == "tool_use" and block.name == "record_extractions":
                    return ExtractionResult.model_validate(block.input)
            return ExtractionResult(extractions=[])
        except Exception:
            logger.exception("Anthropic extract_fields failed; falling back to rule-based extraction")
            return self._fallback.extract_fields(missing_fields, asked_field, utterance, context)

    def classify_intent(self, utterance: str) -> Intent:
        tool = {
            "name": "record_intent",
            "description": "Classify the customer's intent.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": [
                            "provide_information", "request_human", "refuse_decline",
                            "anger_frustration", "payment_mention", "advice_request",
                            "confusion", "generic_question", "other",
                        ],
                    },
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["intent", "confidence", "evidence"],
            },
        }
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                tools=[tool],
                tool_choice={"type": "tool", "name": "record_intent"},
                messages=[{"role": "user", "content": (
                    f"Customer said: \"{utterance}\"\n\n"
                    "Calibrate confidence honestly: use a low confidence (below 0.5) when the "
                    "utterance is ambiguous, hedged (\"I think\", \"not sure\", \"maybe\"), garbled, "
                    "or could plausibly fit more than one intent. Reserve high confidence for "
                    "utterances that are clear and unambiguous."
                )}],
            )
            for block in response.content:
                if block.type == "tool_use" and block.name == "record_intent":
                    return Intent.model_validate(block.input)
            return self._fallback.classify_intent(utterance)
        except Exception:
            logger.exception("Anthropic classify_intent failed; falling back to rule-based classification")
            return self._fallback.classify_intent(utterance)

    def detect_escalation_signal(self, utterance: str, recent_context: str) -> EscalationSignal:
        try:
            # Kept conservative: anger/off-script nuance benefits from the LLM,
            # but we still trust the deterministic keyword pass as a floor.
            fallback_signal = self._fallback.detect_escalation_signal(utterance, recent_context)
            return fallback_signal
        except Exception:
            logger.exception("Anthropic detect_escalation_signal failed; falling back")
            return self._fallback.detect_escalation_signal(utterance, recent_context)

    def summarize(self, transcript_text: str, collected_summary: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarise this customer service call in 2-3 sentences for a human "
                            f"agent who is about to take over:\n\n{transcript_text}"
                        ),
                    }
                ],
            )
            text_blocks = [b.text for b in response.content if b.type == "text"]
            return text_blocks[0] if text_blocks else collected_summary
        except Exception:
            logger.exception("Anthropic summarize failed; falling back to deterministic summary")
            return collected_summary


# ---------------------------------------------------------------------------
# Sarvam AI implementation
#
# UNVERIFIED against a live Sarvam account — same status as VapiVoiceProvider
# (providers/voice/vapi.py) before it was checked against a real key: built
# against Sarvam's documented OpenAI-compatible chat-completions endpoint
# (POST {base_url}/chat/completions, Bearer auth, response_format=
# json_object), but this repo has no live SARVAM_API_KEY to test against.
# Every call is wrapped so a bad assumption about the exact request/response
# envelope can only mean a silent fallback to RuleBasedLLMClient, never a
# broken call — confirm the real shape (auth header name, endpoint path,
# whether json_object mode is actually supported) against a live key before
# trusting this in a demo, and fix it here; nothing else should need to change.
# ---------------------------------------------------------------------------

SARVAM_DEFAULT_BASE_URL = "https://api.sarvam.ai/v1"


class SarvamLLMClient(LLMClient):
    def __init__(self, api_key: str, base_url: str, model: str):
        import httpx

        self._model = model
        self._fallback = RuleBasedLLMClient()
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=15.0,
        )

    def _chat_json(self, system_prompt: str, user_prompt: str) -> Optional[dict]:
        import json

        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except (ValueError, KeyError):
            # Some providers wrap JSON in a code fence even when asked not
            # to — salvage the first {...} block before giving up.
            match = re.search(r"\{.*\}", content, re.DOTALL)
            return json.loads(match.group(0)) if match else None

    def extract_fields(
        self,
        missing_fields: list[FieldScript],
        asked_field: Optional[FieldScript],
        utterance: str,
        context: str,
    ) -> ExtractionResult:
        if not missing_fields:
            return ExtractionResult(extractions=[])
        field_descriptions = "\n".join(
            f"- {f.field}: {f.purpose} (hints: {', '.join(f.extraction_hints)})" for f in missing_fields
        )
        system_prompt = (
            "You extract structured field values from a customer's spoken utterance during a "
            "phone call. Only extract a field if the utterance actually states it — never guess "
            "or invent a value. Respond with a JSON object shaped exactly like: "
            '{"extractions": [{"field": "...", "value": "...", "confidence": 0.0, "evidence": "..."}]}. '
            "Use an empty list if nothing is extractable."
        )
        user_prompt = (
            f"Conversation so far:\n{context}\n\n"
            f"Customer just said: \"{utterance}\"\n\n"
            f"Target fields still missing:\n{field_descriptions}"
        )
        try:
            data = self._chat_json(system_prompt, user_prompt)
            if data is None:
                raise ValueError("no JSON object in Sarvam response")
            return ExtractionResult.model_validate(data)
        except Exception:
            logger.exception("Sarvam extract_fields failed; falling back to rule-based extraction")
            return self._fallback.extract_fields(missing_fields, asked_field, utterance, context)

    def classify_intent(self, utterance: str) -> Intent:
        system_prompt = (
            "You classify a phone customer's intent. Respond with a JSON object shaped exactly "
            'like: {"intent": "...", "confidence": 0.0, "evidence": "..."}. intent must be one of: '
            "provide_information, request_human, refuse_decline, anger_frustration, payment_mention, "
            "advice_request, confusion, generic_question, other. "
            "Calibrate confidence honestly: use a low confidence (below 0.5) when the utterance is "
            "ambiguous, hedged (\"I think\", \"not sure\", \"maybe\"), garbled, or could plausibly fit "
            "more than one intent. Reserve high confidence for clear, unambiguous utterances."
        )
        try:
            data = self._chat_json(system_prompt, f'Customer said: "{utterance}"')
            if data is None:
                raise ValueError("no JSON object in Sarvam response")
            return Intent.model_validate(data)
        except Exception:
            logger.exception("Sarvam classify_intent failed; falling back to rule-based classification")
            return self._fallback.classify_intent(utterance)

    def detect_escalation_signal(self, utterance: str, recent_context: str) -> EscalationSignal:
        try:
            # Kept conservative, same reasoning as AnthropicLLMClient: anger/
            # off-script nuance could benefit from the LLM, but the
            # deterministic keyword pass is trusted as the floor for now.
            return self._fallback.detect_escalation_signal(utterance, recent_context)
        except Exception:
            logger.exception("Sarvam detect_escalation_signal failed; falling back")
            return self._fallback.detect_escalation_signal(utterance, recent_context)

    def summarize(self, transcript_text: str, collected_summary: str) -> str:
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Summarise this customer service call in 2-3 sentences for a human "
                                f"agent who is about to take over:\n\n{transcript_text}"
                            ),
                        }
                    ],
                    "temperature": 0,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return content.strip() if content and content.strip() else collected_summary
        except Exception:
            logger.exception("Sarvam summarize failed; falling back to deterministic summary")
            return collected_summary


def build_llm_client(
    provider: str, api_key: str, model: str, base_url: str = ""
) -> LLMClient:
    if provider == "anthropic" and api_key:
        try:
            return AnthropicLLMClient(api_key=api_key, model=model)
        except Exception:
            logger.exception("Failed to initialise AnthropicLLMClient; falling back to rule-based client")
            return RuleBasedLLMClient()
    if provider == "sarvam" and api_key:
        try:
            return SarvamLLMClient(api_key=api_key, base_url=base_url or SARVAM_DEFAULT_BASE_URL, model=model)
        except Exception:
            logger.exception("Failed to initialise SarvamLLMClient; falling back to rule-based client")
            return RuleBasedLLMClient()
    return RuleBasedLLMClient()
