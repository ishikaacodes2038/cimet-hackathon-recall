"""This call exists to finish one specific journey — a customer who keeps
giving off-topic chatter instead of answering gets a couple of chances
(a warm redirect, then a firmer reminder that this call is specifically for
the energy comparison), and escalates to a human if that still doesn't
work. The underlying bug this closes: off-topic prose ("I saw a really cute
dog outside today") used to sail straight into a non_empty field as if it
were the actual answer — full_name literally became that sentence — so the
retry ladder never even engaged in the first place."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def start(lead_id: str) -> str:
    return client.post("/voice/session", json={"lead_id": lead_id}).json()["session_id"]


def say(session_id: str, text: str) -> dict:
    return client.post("/voice/message", json={"session_id": session_id, "text": text}).json()


def test_off_topic_chatter_is_rejected_not_stored_as_the_answer():
    sid = start("LEAD-1004")
    say(sid, "yes")
    result = say(sid, "I saw a really cute dog outside today")
    assert "full_name" not in result["state"]["collected_fields"]
    assert result["turn"]["escalated"] is False


def test_real_looking_answer_is_still_accepted_normally():
    sid = start("LEAD-1004")
    say(sid, "yes")
    result = say(sid, "Jordan Lee")
    assert result["state"]["collected_fields"]["full_name"]["value"] == "Jordan Lee"


def test_second_off_topic_reply_gets_the_fallback_offer_naming_the_calls_purpose():
    sid = start("LEAD-1004")
    say(sid, "yes")
    say(sid, "I saw a really cute dog outside today")  # attempt 1 -> soft redirect
    offer = say(sid, "anyway, did you catch the game last night")  # attempt 2 -> exhausted, fallback offer
    assert offer["turn"]["escalated"] is False
    assert "energy comparison" in offer["turn"]["agent_text"].lower()
    assert "connect you with someone" in offer["turn"]["agent_text"]


def test_third_off_topic_reply_escalates_to_a_human():
    """Give it 2 tries; a third deviation escalates rather than looping."""
    sid = start("LEAD-1004")
    say(sid, "yes")
    say(sid, "I saw a really cute dog outside today")  # attempt 1
    say(sid, "anyway, did you catch the game last night")  # attempt 2 -> fallback offer
    result = say(sid, "random question but do you like pizza")  # attempt 3 -> escalate
    assert result["turn"]["escalated"] is True
    assert result["turn"]["escalation_category"] == "CONFUSION_REPEATED_FAILURE"


def test_generic_questions_about_the_call_are_not_treated_as_off_topic():
    """A legitimate meta-question ("who are you", "is this a scam") is a
    fundamentally different signal from genuine off-topic chit-chat and must
    never push the customer toward escalation just for asking it."""
    sid = start("LEAD-1004")
    say(sid, "yes")
    say(sid, "is this a scam?")
    say(sid, "how did you get my number?")
    result = say(sid, "why do you need my address for this?")
    assert result["turn"]["escalated"] is False
    assert result["turn"]["escalation_category"] is None
    assert "full_name" not in result["state"]["collected_fields"]


def test_declining_an_optional_field_is_not_treated_as_off_topic():
    """Saying "no, don't have it" to an optional field (e.g. NMI/MIRN) is
    normal, on-topic behavior — it must be skipped gracefully, not treated
    as the customer deviating from the call's purpose."""
    sid = start("LEAD-1001")
    say(sid, "Yes that's fine")
    from tests.test_conversation_scenarios import answer

    answer(sid, "14th of March 1990")
    answer(sid, "12 Smith Street, Richmond VIC 3121")
    answer(sid, "residential")
    answer(sid, "AGL")
    answer(sid, "electricity")
    result = say(sid, "no")  # decline NMI/MIRN — optional, must not count as deviation
    assert result["turn"]["escalated"] is False
    assert "quarterly bill" in result["turn"]["agent_text"].lower()


def test_partial_date_progress_does_not_count_as_off_topic():
    """A customer answering a date one piece at a time is being perfectly
    cooperative, not deviating — three separate helpful pieces must never
    accidentally trip escalation."""
    sid = start("LEAD-1004")
    say(sid, "yes")
    result = say(sid, "Jordan Lee")
    assert result["state"]["awaiting_confirmation_for"] == "full_name"
    say(sid, "yes")  # confirm
    say(sid, "the twentieth")
    say(sid, "of September")
    result = say(sid, "2005")
    assert result["turn"]["escalated"] is False
    assert result["state"]["collected_fields"]["date_of_birth"]["value"] == "20-09-2005"
