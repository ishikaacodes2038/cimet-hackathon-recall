import re
import string
from typing import Optional

from app.models.script import FieldScript
from app.services.date_parsing import normalize_to_ddmmyyyy

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
POSTCODE_RE = re.compile(r"\b\d{4}\b")
YES_WORDS = {"yes", "yeah", "yep", "correct", "that's right", "affirmative", "sure", "true"}
NO_WORDS = {"no", "nope", "nah", "negative", "not really", "false"}

# A guardrail for free-text ("non_empty") fields: without this, a bare
# "yes"/"ok"/"sure" said in response to "what's your address?" gets stored
# as a literal address, because a non_empty field otherwise accepts any
# non-blank string. Matched as an EXACT phrase (after stripping punctuation
# and collapsing whitespace) against the whole answer, never a substring —
# a real address like "123 Yes Street" must never be caught by this just
# because it contains the word "yes" somewhere in it.
GENERIC_FILLER_PHRASES = {
    "yes", "yeah", "yep", "yup", "ya", "no", "nope", "nah",
    "ok", "okay", "k", "sure", "fine", "alright", "all right",
    "whatever", "maybe", "i guess", "not sure", "dont know", "don't know",
    "idk", "hmm", "umm", "uh", "well", "right", "correct", "good", "great",
    "yes please", "no thanks", "sure thing",
    "हां", "हाँ", "नहीं", "ठीक", "ठीक है", "शायद", "पता नहीं", "अच्छा",
    "oo", "opo", "hindi", "sige", "siguro", "ewan", "di ko alam", "sigurado",
}


def _is_generic_filler(value: str) -> bool:
    normalized = " ".join(value.lower().strip(string.punctuation).split())
    return normalized in GENERIC_FILLER_PHRASES


# A longer step beyond GENERIC_FILLER_PHRASES: a rambling off-topic sentence
# ("I saw a really cute dog outside today") isn't a bare filler word, so the
# exact-phrase check above never catches it — and being a normal-looking
# non-blank string, it used to sail straight into a non_empty field as if it
# were the actual name/address/provider. These are substring markers
# (unlike GENERIC_FILLER_PHRASES, which must match the WHOLE answer).
#
# Deliberately conservative — a false POSITIVE here (wrongly rejecting a
# real answer) is worse than a false negative (letting an occasional
# off-topic remark through, which the normal retry ladder still catches on
# repetition). "I think it's AGL, not totally sure though" and "Jordan Lee,
# and by the way this is a residential place" are both genuine, legitimate
# answers that happen to contain ordinary hedging/discourse language ("I
# think", "by the way") — broader phrasing like that was tried and reverted
# after it broke exactly those two real scenarios. Only phrases that are
# essentially never part of a genuine name/address/date/provider answer
# belong here.
OFF_TOPIC_CHATTER_MARKERS = {
    "i saw a", "i went to", "guess what happened", "funny story",
    "did you catch the game", "did you see the game", "have you seen the game",
    "how's your day going", "hows your day going", "how was your weekend",
    "off topic but", "off-topic but", "random question but", "unrelated question but",
    "speaking of which", "that reminds me",
    "क्या आपने देखा", "अजीब बात है ना", "वैसे एक बात बताऊं",
    "sa totoo lang biro lang", "nakakatawa na kwento",
}


def _looks_like_off_topic_chatter(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in OFF_TOPIC_CHATTER_MARKERS)


class ValidationResult:
    def __init__(self, valid: bool, normalized_value: Optional[str] = None, reason: str = ""):
        self.valid = valid
        self.normalized_value = normalized_value
        self.reason = reason


def validate_field_value(field_script: FieldScript, raw_value: str) -> ValidationResult:
    """Deterministic validation — never delegated to the LLM."""
    value = (raw_value or "").strip()
    vtype = field_script.validation.type

    if not value:
        return ValidationResult(False, reason="empty value")

    if vtype == "non_empty":
        if field_script.validation.reject_generic_filler and _is_generic_filler(value):
            return ValidationResult(False, reason="that doesn't look like an answer to this question — too vague")
        if field_script.validation.reject_generic_filler and _looks_like_off_topic_chatter(value):
            return ValidationResult(False, reason="that reads as off-topic chatter, not an answer to this question")
        if len(value) < field_script.validation.min_length:
            return ValidationResult(
                False, reason=f"too short to be a real answer (need at least {field_script.validation.min_length} characters)"
            )
        return ValidationResult(True, value)

    if vtype == "email":
        if EMAIL_RE.match(value):
            return ValidationResult(True, value.lower())
        return ValidationResult(False, reason="not a valid email address")

    if vtype == "date":
        # The stored value is always canonical DD-MM-YYYY, regardless of what
        # format or language the customer said it in — this is the one place
        # that normalization happens, so it can never drift from what was
        # actually captured (find_date_span picks the longest, not first,
        # matching span — see date_parsing.py for the bug that fix closed).
        normalized = normalize_to_ddmmyyyy(value)
        if normalized:
            return ValidationResult(True, normalized)
        return ValidationResult(False, reason="not a recognisable date")

    if vtype == "postcode_au":
        # Same first-match-instead-of-best-match bug class the date parser
        # had: .search() would return the FIRST 4-digit run in the
        # utterance, not necessarily the postcode — an AU address reads
        # "<street>, <suburb> <STATE> <postcode>", so the postcode is always
        # the LAST 4-digit run, not the first one that happens to appear
        # (e.g. a house/unit number mentioned earlier in the same sentence).
        matches = POSTCODE_RE.findall(value)
        if matches:
            return ValidationResult(True, matches[-1])
        return ValidationResult(False, reason="no 4-digit Australian postcode found")

    if vtype == "enum":
        # Picks whichever valid option was mentioned LAST in the answer, not
        # the first one that happens to appear in the script's options list
        # — "not really residential, more like business" must resolve to
        # "business", not silently lock in "residential" just because that
        # option was listed/checked first. By the time validation runs the
        # extractor has already narrowed this to a single-word candidate in
        # the common case, but this stays correct even if a fuller phrase
        # reaches here (e.g. a live LLM extraction passing more raw text).
        options = field_script.validation.options or []
        lowered = value.lower()
        best_option = None
        best_pos = -1
        for option in options:
            pos = lowered.rfind(option.lower())
            if pos > best_pos:
                best_pos = pos
                best_option = option
        if best_option is not None:
            return ValidationResult(True, best_option)
        return ValidationResult(False, reason=f"expected one of {options}")

    if vtype == "yes_no":
        lowered = value.lower()
        if any(word in lowered for word in YES_WORDS):
            return ValidationResult(True, "yes")
        if any(word in lowered for word in NO_WORDS):
            return ValidationResult(True, "no")
        return ValidationResult(False, reason="expected a yes/no answer")

    # Unknown validation type — fail closed rather than silently accept.
    return ValidationResult(False, reason=f"unknown validation type '{vtype}'")
