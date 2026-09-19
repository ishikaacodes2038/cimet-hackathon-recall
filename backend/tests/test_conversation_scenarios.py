"""End-to-end conversation scenarios, driven through the real HTTP API exactly
like a live call would be (via the mock voice provider's text interface).

These encode the 12 messy-conversation scenarios from the hackathon brief,
plus a couple more that were found by hand during adversarial testing
(optional-field infinite loop, optional-field-ordering skip bug) and are
kept here as permanent regressions so they can't silently come back.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def start(lead_id: str) -> str:
    resp = client.post("/voice/session", json={"lead_id": lead_id})
    assert resp.status_code == 200
    return resp.json()["session_id"]


def say(session_id: str, text: str) -> dict:
    resp = client.post("/voice/message", json={"session_id": session_id, "text": text})
    assert resp.status_code == 200
    return resp.json()


def answer(session_id: str, text: str) -> dict:
    """Give an answer AND confirm it — every successfully-captured field now
    gets read back ("I heard 'X' — is that correct?") before being locked
    in, so a normal multi-field conversation needs two turns per field: the
    answer, then the confirmation. Returns the result AFTER confirming."""
    result = say(session_id, text)
    assert result["state"]["awaiting_confirmation_for"] is not None, (
        f"expected a reconfirmation prompt after '{text}', got: {result['turn']['agent_text']!r}"
    )
    return say(session_id, "yes")


def test_scenario_happy_path_completes_and_submits():
    sid = start("LEAD-1001")
    say(sid, "Yes that's fine")  # consent — not a field capture, no reconfirm
    answer(sid, "14th of March 1990")
    answer(sid, "12 Smith Street, Richmond VIC 3121")
    answer(sid, "residential")
    answer(sid, "AGL")
    answer(sid, "electricity")
    say(sid, "no")  # NMI/MIRN — optional, declined & skipped, no reconfirm for a skip
    answer(sid, "around 350 dollars")
    answer(sid, "no")  # concession
    answer(sid, "no")  # life support
    answer(sid, "not moving, existing address")
    answer(sid, "afternoon is best")
    result = say(sid, "yes go ahead")  # final read-back summary confirmation -> submit
    assert result["turn"]["completed"] is True
    assert result["turn"]["submission_id"]
    assert result["state"]["journey_status"] == "COMPLETED"
    assert result["state"]["collected_fields"]["date_of_birth"]["value"] == "14-03-1990"


def test_scenario_customer_interrupts_with_multiple_fields_at_once():
    sid = start("LEAD-1004")
    say(sid, "yes okay")
    result = say(sid, "Jordan Lee, and by the way this is for a residential place, mostly electricity")
    collected = result["state"]["collected_fields"]
    assert "full_name" in collected
    assert "property_type" in collected
    assert "fuel_type" in collected


def test_scenario_customer_says_im_busy():
    sid = start("LEAD-1004")
    say(sid, "sure")
    result = say(sid, "sorry I'm busy right now can't talk")
    assert result["turn"]["ended"] is True
    assert result["state"]["journey_status"] == "ENDED_BY_CUSTOMER"


def test_scenario_customer_says_not_interested():
    sid = start("LEAD-1004")
    say(sid, "sure")
    result = say(sid, "not interested, please stop calling me")
    assert result["turn"]["ended"] is True
    assert result["state"]["journey_status"] == "ENDED_BY_CUSTOMER"


def test_scenario_customer_requests_human():
    sid = start("LEAD-1004")
    say(sid, "yes go ahead")
    result = say(sid, "Actually can I just speak to a real person please")
    assert result["turn"]["escalated"] is True
    assert result["turn"]["escalation_category"] == "CUSTOMER_REQUEST"
    assert result["turn"]["handoff_id"]


def test_scenario_customer_becomes_frustrated():
    sid = start("LEAD-1004")
    say(sid, "sure")
    result = say(sid, "I've already told you three times, this is ridiculous!!")
    assert result["turn"]["escalated"] is True
    assert result["turn"]["escalation_category"] == "ANGER_FRUSTRATION"


def test_scenario_ambiguous_information_low_confidence_escalates():
    sid = start("LEAD-1004")
    say(sid, "sure")
    answer(sid, "Priya Sharma")
    answer(sid, "14/03/1990")
    answer(sid, "123 Test St")
    answer(sid, "residential")
    result = say(sid, "I think it's AGL, not totally sure though")
    assert result["turn"]["escalated"] is True
    assert result["turn"]["escalation_category"] == "LOW_CONFIDENCE"


def test_scenario_agent_mishears_repeatedly_escalates_not_loops():
    """max_retries=2 for date_of_birth, but retry-exhaustion now offers a
    graceful fallback (type it in / human) once before actually escalating —
    so this takes 3 bad answers, not 2. See test_fallback_offer_* below for
    the offer message itself."""
    sid = start("LEAD-1004")
    say(sid, "yes")
    answer(sid, "Jordan Lee")
    say(sid, "banana")  # invalid date, attempt 1
    offer = say(sid, "purple elephant")  # invalid date, attempt 2 -> exhausted, offers fallback
    assert offer["turn"]["escalated"] is False
    assert "type it in" in offer["turn"]["agent_text"]
    result = say(sid, "still purple elephant")  # invalid again after the offer -> now escalates
    assert result["turn"]["escalated"] is True
    assert result["turn"]["escalation_category"] == "CONFUSION_REPEATED_FAILURE"


def test_scenario_off_script_advice_request_redirected_then_escalated():
    sid = start("LEAD-1004")
    say(sid, "sure")
    first = say(sid, "Which plan should I choose?")
    assert first["turn"]["escalated"] is False
    second = say(sid, "No really, which plan should I choose, what do you recommend?")
    assert second["turn"]["escalated"] is True
    assert second["turn"]["escalation_category"] == "OFF_SCRIPT"


def test_scenario_payment_mention_never_collected_always_escalates():
    sid = start("LEAD-1004")
    say(sid, "sure")
    result = say(sid, "Can I just give you my card number to sort this out, it's 4111 1111 1111 1111")
    assert result["turn"]["escalated"] is True
    assert result["turn"]["escalation_category"] == "SENSITIVE_PAYMENT"
    # the raw card number must never be persisted into the transcript
    transcript_text = " ".join(t["text"] for t in result["state"]["conversation_history"])
    assert "4111 1111 1111 1111" not in transcript_text
    assert "REDACTED" in transcript_text


def test_scenario_customer_gives_refusal_at_consent():
    sid = start("LEAD-1004")
    result = say(sid, "No I'm not comfortable being recorded")
    assert result["turn"]["ended"] is True
    assert result["state"]["journey_status"] == "ENDED_BY_CUSTOMER"
    assert result["state"]["consent_status"] == "DECLINED"
    assert result["state"]["collected_fields"] == {}


def test_scenario_low_confidence_field_is_still_captured_for_human_review():
    sid = start("LEAD-1004")
    say(sid, "sure")
    answer(sid, "Priya Sharma")
    answer(sid, "14/03/1990")
    answer(sid, "123 Test St")
    answer(sid, "residential")
    result = say(sid, "maybe it's Origin Energy, I could be wrong")
    collected = result["state"]["collected_fields"].get("current_provider")
    assert collected is not None
    assert collected["confidence"] < 0.5


# --- Regressions found during adversarial testing (kept permanently) ---


def test_regression_optional_field_declined_is_skipped_not_looped():
    """An optional field (NMI/MIRN) the customer doesn't have must be skipped,
    not re-asked forever and not silently un-escalatable."""
    sid = start("LEAD-1001")
    say(sid, "Yes that's fine")
    answer(sid, "14th of March 1990")
    answer(sid, "12 Smith Street, Richmond VIC 3121")
    answer(sid, "residential")
    answer(sid, "AGL")
    answer(sid, "electricity")
    result = say(sid, "no")  # decline the optional NMI/MIRN once — skip has no reconfirm
    # must have moved on to the next question, not repeated the same one
    assert "quarterly bill" in result["turn"]["agent_text"].lower()


def test_regression_optional_fields_after_last_required_field_are_still_asked():
    """Optional fields ordered AFTER the last required field in the script
    must still be asked, not skipped by jumping straight to confirmation."""
    sid = start("LEAD-1001")
    say(sid, "Yes that's fine")
    answer(sid, "14th of March 1990")
    answer(sid, "12 Smith Street, Richmond VIC 3121")
    answer(sid, "residential")
    answer(sid, "AGL")
    answer(sid, "electricity")
    say(sid, "no")  # NMI/MIRN skip, no reconfirm
    answer(sid, "around 350 dollars")
    answer(sid, "no")  # concession
    result = say(sid, "no")  # life_support — last REQUIRED field, "no" doesn't escalate
    assert result["state"]["awaiting_confirmation_for"] == "life_support_status"
    result = say(sid, "yes")  # confirm life_support_status
    # next question must be the optional move_in_date field, not confirmation
    assert "move-in" in result["turn"]["agent_text"].lower() or "existing address" in result["turn"]["agent_text"].lower()
    assert result["state"]["current_step"] != "CONFIRMATION"


def test_regression_dnc_listed_number_blocks_session_before_any_call():
    resp = client.post("/voice/session", json={"lead_id": "LEAD-1003"})
    body = resp.json()
    assert body["blocked"] is True
    assert body["block_reason"] == "DNC_LISTED"
    assert body["session_id"] == ""


def test_regression_hard_refusal_writes_back_to_dnc_registry():
    """'Don't call me again' must be treated as a standing no-contact
    request — logged to the DNC registry, not just ending this one call."""
    # LEAD-1004 is not DNC-listed at the start of this test.
    sid = start("LEAD-1004")
    say(sid, "sure")
    result = say(sid, "not interested, please stop calling me")
    assert result["turn"]["ended"] is True

    second_attempt = client.post("/voice/session", json={"lead_id": "LEAD-1004"})
    body = second_attempt.json()
    assert body["blocked"] is True
    assert body["block_reason"] == "DNC_LISTED"
