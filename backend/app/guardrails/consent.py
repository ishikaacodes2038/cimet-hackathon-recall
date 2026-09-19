import re

from app.models.script import JourneyScript

DECLINE_MARKERS = [
    "don't record", "dont record", "no recording", "not okay", "not ok",
    "not comfortable", "don't want to be recorded", "stop recording",
    "no i'm not", "no im not", "not fine with that",
]


def build_consent_opener(script: JourneyScript, first_name: str, last_activity_date: str) -> str:
    return script.consent_line.format(first_name=first_name, last_activity_date=last_activity_date)


def is_consent_decline(utterance: str) -> bool:
    lowered = utterance.lower()
    if any(marker in lowered for marker in DECLINE_MARKERS):
        return True
    # A bare "no" (not "no problem", "no worries", etc.) directly in response
    # to the consent question counts as a decline.
    stripped = re.sub(r"[^\w\s]", "", lowered).strip()
    return stripped in {"no", "nope", "nah", "no thanks", "no thank you"}
