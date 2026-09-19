"""The reconfirm-before-lock feature: every successfully-captured field is
read back to the customer before being treated as final, so an STT mishear
or misrecognition gets caught before it's ever submitted — rather than
silently trusting the first guess, per the exact scenario a live test
surfaced (a mis-heard date of birth being stored wrong)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def start(lead_id: str) -> str:
    return client.post("/voice/session", json={"lead_id": lead_id}).json()["session_id"]


def say(session_id: str, text: str) -> dict:
    return client.post("/voice/message", json={"session_id": session_id, "text": text}).json()


def test_field_is_read_back_before_being_locked():
    sid = start("LEAD-1004")
    say(sid, "sure")
    result = say(sid, "Jordan Lee")
    assert result["state"]["awaiting_confirmation_for"] == "full_name"
    assert "Jordan Lee" in result["turn"]["agent_text"]
    # collected but NOT confirmed yet
    assert result["state"]["collected_fields"]["full_name"]["value"] == "Jordan Lee"


def test_confirming_locks_the_field_and_moves_on():
    sid = start("LEAD-1004")
    say(sid, "sure")
    say(sid, "Jordan Lee")
    result = say(sid, "yes that's right")
    assert result["state"]["awaiting_confirmation_for"] is None
    assert "date of birth" in result["turn"]["agent_text"].lower()


def test_declining_discards_the_wrong_value_and_reasks():
    """The exact reported scenario: an STT mishear captures the wrong value;
    the customer should be able to say "no" and have it discarded and
    re-asked, not silently kept."""
    sid = start("LEAD-1004")
    say(sid, "sure")
    say(sid, "Jordan Lee")
    result = say(sid, "no that's not right")
    assert result["state"]["awaiting_confirmation_for"] is None
    assert "full_name" not in result["state"]["collected_fields"]
    # re-asked (clarification_question for full_name)
    assert "spell" in result["turn"]["agent_text"].lower() or "name" in result["turn"]["agent_text"].lower()


def test_repeated_corrections_eventually_get_the_graceful_fallback_offer():
    sid = start("LEAD-1004")
    say(sid, "sure")
    say(sid, "Jordan Lee")
    say(sid, "no")  # correction 1 -> re-ask (max_retries=2 for full_name)
    result = say(sid, "Jordan Lee again")
    assert result["state"]["awaiting_confirmation_for"] == "full_name"
    offer = say(sid, "no")  # correction 2 -> retries exhausted -> graceful offer, not escalate
    assert offer["turn"]["escalated"] is False
    assert "connect you with someone" in offer["turn"]["agent_text"]


def test_asking_for_human_during_a_reconfirmation_still_escalates_immediately():
    """Guardrails must win even while a reconfirmation is pending — a
    customer isn't stuck answering yes/no if they want a human instead."""
    sid = start("LEAD-1004")
    say(sid, "sure")
    say(sid, "Jordan Lee")
    result = say(sid, "connect me to a person please")
    assert result["turn"]["escalated"] is True
    assert result["turn"]["escalation_category"] == "CUSTOMER_REQUEST"


def test_prefilled_carried_over_fields_are_not_reconfirmed():
    """Fields already on file from the dropped web journey are pre-marked
    confirmed — re-litigating them would undercut "ask only what's missing"."""
    sid = start("LEAD-1001")
    result = say(sid, "yes")  # grant consent
    assert result["state"]["awaiting_confirmation_for"] is None
    assert "date of birth" in result["turn"]["agent_text"].lower()  # skipped straight past full_name


def test_opportunistically_captured_fields_are_not_individually_reconfirmed():
    """Only the field actively being asked about gets read back — fields
    volunteered ahead of being asked are captured normally (re-confirming
    every incidental detail would undercut efficiency)."""
    sid = start("LEAD-1004")
    say(sid, "yes okay")
    result = say(sid, "Jordan Lee, and by the way this is for a residential place, mostly electricity")
    # full_name was the asked field -> queued for reconfirmation
    assert result["state"]["awaiting_confirmation_for"] == "full_name"
    # property_type/fuel_type were volunteered, not asked -> captured directly
    assert result["state"]["collected_fields"]["property_type"]["value"] == "residential"
    assert result["state"]["collected_fields"]["fuel_type"]["value"] == "electricity"
