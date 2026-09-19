"""Guardrail: a free-text ("non_empty") field must reject a vague/generic
non-answer ("yes", "ok", "sure") rather than silently storing it as the
literal field value — e.g. answering "what's your address?" with "yes"
used to be stored as address="yes". Only a plausibly relevant answer is
accepted; the customer is re-asked (through the normal capture-failure
ladder) for anything that looks like generic filler instead."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.validation import _is_generic_filler

client = TestClient(app)


def start(lead_id: str) -> str:
    return client.post("/voice/session", json={"lead_id": lead_id}).json()["session_id"]


def say(session_id: str, text: str) -> dict:
    return client.post("/voice/message", json={"session_id": session_id, "text": text}).json()


def test_is_generic_filler_matches_whole_answer_only():
    assert _is_generic_filler("yes")
    assert _is_generic_filler("Yes.")
    assert _is_generic_filler("  OK  ")
    assert _is_generic_filler("sure")
    assert _is_generic_filler("I guess")
    # Never a substring match — a real address that happens to CONTAIN one
    # of these words must not be caught by this.
    assert not _is_generic_filler("123 Yes Street")
    assert not _is_generic_filler("Sure Valley Road")


def test_vague_yes_is_not_accepted_as_a_full_name():
    sid = start("LEAD-1004")
    say(sid, "yes")  # consent
    result = say(sid, "yes")  # answering the full_name question with filler
    assert "full_name" not in result["state"]["collected_fields"]
    # re-asked, not silently accepted and moved on
    assert "name" in result["turn"]["agent_text"].lower() or "spell" in result["turn"]["agent_text"].lower()


def test_vague_ok_is_not_accepted_as_an_address():
    sid = start("LEAD-1004")
    say(sid, "yes")
    say(sid, "Jordan Lee")
    confirm = say(sid, "yes")
    assert confirm["state"]["awaiting_confirmation_for"] is None
    result = say(sid, "okay")  # answering the address question with filler
    assert "address" not in result["state"]["collected_fields"]


def test_real_looking_answer_is_still_accepted_normally():
    sid = start("LEAD-1004")
    say(sid, "yes")
    result = say(sid, "Jordan Lee")
    assert result["state"]["collected_fields"]["full_name"]["value"] == "Jordan Lee"
    assert result["state"]["awaiting_confirmation_for"] == "full_name"
