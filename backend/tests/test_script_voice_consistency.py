"""A TTS voice can only speak in one grammatical gender at a time. Hindi verb
forms inflect for the speaker's gender (e.g. "कर रही हूं" vs "कर रहा हूं"), and
early drafts of the Hindi script used the written convention of listing both
forms separated by a slash (comprehensible to a human reader choosing their
own gender, meaningless — and broken-sounding — read aloud by a single TTS
voice). This is a permanent regression test for that class of bug: every
script file must commit to one consistent persona, never a written "A/B"
alternative, in any customer-facing text."""

import re
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "energy"
DEVANAGARI_SLASH_PAIR = re.compile(r"[ऀ-ॿ]+/[ऀ-ॿ]+")


def _all_customer_facing_text(script_dict: dict) -> str:
    parts = [script_dict.get("consent_line", ""), script_dict.get("handoff_line", "")]
    parts.extend(script_dict.get("phrases", {}).values())
    for section in script_dict.get("sections", []):
        if section.get("opening_line"):
            parts.append(section["opening_line"])
    for field in script_dict.get("fields", {}).values():
        parts.append(field.get("question", ""))
        parts.append(field.get("clarification_question") or "")
    return "\n".join(parts)


@pytest.mark.parametrize("script_file", sorted(SCRIPTS_DIR.glob("recovery.*.yaml")))
def test_script_has_no_dual_gender_written_forms(script_file):
    with open(script_file, encoding="utf-8") as f:
        script_dict = yaml.safe_load(f)

    text = _all_customer_facing_text(script_dict)
    matches = DEVANAGARI_SLASH_PAIR.findall(text)
    assert matches == [], f"{script_file.name} has dual-gender written forms that break TTS: {matches}"


# Regression: these parenthetical English glosses of ordinary common nouns
# ("आवासीय (residential)") were a translation-time aid left in the spoken
# text by mistake — read aloud by a single Hindi TTS voice, they sound like
# the agent switching languages mid-sentence. Removed for the words that
# have a natural Hindi equivalent; genuine Australia-specific technical
# terms/proper nouns without a Hindi equivalent (NMI, MIRN, official
# concession card names, the CIMET brand name) are intentionally still
# said in English — that's authentic bilingual speech, not this bug.
REMOVED_ENGLISH_GLOSSES = [
    "(residential)", "(business)", "(electricity)", "(gas)", "(concession)", "(life-support)",
]


def test_hindi_script_has_no_redundant_english_glosses():
    hi_path = SCRIPTS_DIR / "recovery.hi.yaml"
    with open(hi_path, encoding="utf-8") as f:
        script_dict = yaml.safe_load(f)
    text = _all_customer_facing_text(script_dict)
    for gloss in REMOVED_ENGLISH_GLOSSES:
        assert gloss not in text, f"redundant English gloss '{gloss}' leaked into spoken Hindi text"
