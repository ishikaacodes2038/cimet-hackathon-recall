"""Generic-question handling, "trained" against a synthetic corpus.

There's no neural net in the rule-based fallback to fine-tune — "training"
here means what it can honestly mean for a deterministic, keyword-based
classifier: a labeled corpus of realistic utterances
(data/synthetic/generic_questions.json) that app/services/llm_client.py's
INTENT_KEYWORDS list is verified — and, over time, expanded — against, so
coverage is a regression-tested fact, not a vibe. Every case in the corpus
runs through classify_intent() here; a new phrasing that should be
recognised gets ADDED to the corpus and to INTENT_KEYWORDS together, so the
two can never silently drift apart.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_client import RuleBasedLLMClient

client = TestClient(app)

CORPUS_PATH = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "generic_questions.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

llm = RuleBasedLLMClient()


def start(lead_id: str) -> str:
    return client.post("/voice/session", json={"lead_id": lead_id}).json()["session_id"]


def say(session_id: str, text: str) -> dict:
    return client.post("/voice/message", json={"session_id": session_id, "text": text}).json()


@pytest.mark.parametrize("case", CORPUS["generic_question"], ids=lambda c: c["text"])
def test_synthetic_corpus_generic_questions_are_recognised(case):
    intent = llm.classify_intent(case["text"])
    assert intent.intent == "generic_question", f"expected generic_question for {case['text']!r}, got {intent.intent!r}"


@pytest.mark.parametrize("case", CORPUS["not_generic_question"], ids=lambda c: c["text"])
def test_synthetic_corpus_real_answers_are_not_misclassified(case):
    intent = llm.classify_intent(case["text"])
    assert intent.intent != "generic_question", f"{case['text']!r} was wrongly classified as generic_question"
    if "expected" in case:
        assert intent.intent == case["expected"]


def test_generic_question_gets_a_brief_answer_and_returns_to_the_pending_question():
    sid = start("LEAD-1004")
    say(sid, "yes")  # consent
    result = say(sid, "wait, who are you exactly?")
    assert result["turn"]["escalated"] is False
    assert "CIMET" in result["turn"]["agent_text"]
    # the pending full_name question is still asked, not silently dropped
    assert "name" in result["turn"]["agent_text"].lower()
    assert "full_name" not in result["state"]["collected_fields"]


def test_generic_question_does_not_cost_a_retry():
    """Asking a legitimate meta-question shouldn't count against the
    customer the way a genuine mishear/capture-failure does — they get the
    graceful fallback offer only after real failed attempts, not after
    curiosity."""
    sid = start("LEAD-1004")
    say(sid, "yes")
    say(sid, "is this a scam?")
    say(sid, "how did you get my number?")
    result = say(sid, "why do you need my address for this?")
    assert result["turn"]["escalated"] is False
    assert "connect you with someone" not in result["turn"]["agent_text"]


def test_generic_question_asked_during_confirmation_still_reads_back_the_summary():
    sid = start("LEAD-1001")
    say(sid, "Yes that's fine")
    from tests.test_conversation_scenarios import answer  # reuse the confirm-each-field helper

    answer(sid, "14th of March 1990")
    answer(sid, "12 Smith Street, Richmond VIC 3121")
    answer(sid, "residential")
    answer(sid, "AGL")
    answer(sid, "electricity")
    say(sid, "no")
    answer(sid, "around 350 dollars")
    answer(sid, "no")
    answer(sid, "no")
    answer(sid, "not moving, existing address")
    result = answer(sid, "afternoon is best")
    assert result["state"]["current_step"] == "CONFIRMATION"

    generic = say(sid, "how long will this take?")
    assert generic["turn"]["escalated"] is False
    assert "submit" in generic["turn"]["agent_text"].lower() or "confirm" in generic["turn"]["agent_text"].lower()
