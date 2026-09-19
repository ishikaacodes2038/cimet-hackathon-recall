from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AGENT_HEADERS = {"X-Demo-Token": "agent-demo-token"}


def start(lead_id: str, language: str = "en") -> dict:
    resp = client.post("/voice/session", json={"lead_id": lead_id, "language": language})
    assert resp.status_code == 200
    return resp.json()


def say(session_id: str, text: str) -> dict:
    resp = client.post("/voice/message", json={"session_id": session_id, "text": text})
    assert resp.status_code == 200
    return resp.json()


def answer(session_id: str, text: str, yes_word: str = "yes") -> dict:
    """Give an answer and confirm it in whatever language/word the caller
    specifies — a successfully-captured field is read back for confirmation
    before being locked in."""
    result = say(session_id, text)
    assert result["state"]["awaiting_confirmation_for"] is not None
    return say(session_id, yes_word)


# --- Multilingual ---


def test_hindi_session_asks_consent_and_questions_in_hindi():
    body = start("LEAD-1004", language="hi")
    assert "नमस्ते" in body["agent_text"]
    assert body["state"]["language"] == "hi"

    consent_result = say(body["session_id"], "हां")
    assert "पूरा नाम" in consent_result["turn"]["agent_text"]  # full_name — LEAD-1004 has no prefill

    result = answer(body["session_id"], "Jordan Lee", yes_word="हां")
    assert "जन्मतिथि" in result["turn"]["agent_text"]


def test_filipino_session_asks_consent_and_questions_in_filipino():
    body = start("LEAD-1004", language="fil")
    assert "Kumusta" in body["agent_text"]
    assert body["state"]["language"] == "fil"

    consent_result = say(body["session_id"], "oo")
    assert "buong pangalan" in consent_result["turn"]["agent_text"]  # full_name — LEAD-1004 has no prefill

    result = answer(body["session_id"], "Jordan Lee", yes_word="oo")
    assert "petsa ng kapanganakan" in result["turn"]["agent_text"]


def test_hindi_consent_acknowledgement_has_no_english_leak():
    """Regression: the consent-grant acknowledgement used to be a hardcoded
    English literal glued onto the translated question — e.g. a Hindi call
    would say "Great, thank you. <Hindi question>". Caught by inspection
    while reviewing the code against the reference transcript, not by an
    earlier test, because prior tests only checked a Hindi substring was
    present — never that the WHOLE line was Hindi."""
    body = start("LEAD-1004", language="hi")
    consent_result = say(body["session_id"], "हां")
    text = consent_result["turn"]["agent_text"]
    assert "Great" not in text
    assert "thank you" not in text.lower()


def test_hindi_opener_has_no_english_leak_from_last_activity_date():
    """Regression: LEAD-1004's last_activity_date used to be the raw English
    string "earlier today", interpolated straight into the Hindi consent
    opener ("...aap ne earlier today ko jo...") — the same bug class as the
    parenthetical-gloss leak, just from lead data instead of script text.
    Caught by live testing, not an earlier test, because no test checked the
    OPENING line (before consent is even granted) for an English leak."""
    body = start("LEAD-1004", language="hi")
    assert "earlier today" not in body["agent_text"]
    assert "आज" in body["agent_text"]


def test_filipino_opener_has_no_english_leak_from_last_activity_date():
    body = start("LEAD-1004", language="fil")
    assert "earlier today" not in body["agent_text"]
    assert "kanina" in body["agent_text"]


def test_filipino_advice_refusal_has_no_english_leak():
    body = start("LEAD-1004", language="fil")
    say(body["session_id"], "oo")
    result = say(body["session_id"], "Aling plano ang dapat kong piliin?")
    text = result["turn"]["agent_text"]
    assert "I can't recommend" not in text
    assert "Hindi ako makakapagrekomenda" in text


def test_resume_acknowledgement_mentions_carried_over_data_in_hindi():
    """LEAD-1001 has a prefilled field — the consent-grant acknowledgement
    should use the resume-specific phrase (evidence-based enhancement: real
    CIMET-family calls read back what's already on file rather than silently
    sitting on it — see the reference transcript's address-confirmation
    pattern), not the generic one used for a lead with nothing on file."""
    body = start("LEAD-1001", language="hi")
    consent_result = say(body["session_id"], "हां")
    assert "पहले से" in consent_result["turn"]["agent_text"]  # "already" — resume-specific phrase


def test_generic_ack_used_when_nothing_was_prefilled():
    body = start("LEAD-1004", language="en")
    consent_result = say(body["session_id"], "yes")
    assert "already have some of your details" not in consent_result["turn"]["agent_text"]
    assert "Great, thank you" in consent_result["turn"]["agent_text"]


def test_hindi_yes_no_and_enum_synonyms_resolve_to_canonical_english_values():
    body = start("LEAD-1004", language="hi")
    sid = body["session_id"]
    say(sid, "हां")  # consent
    answer(sid, "प्रिया शर्मा", yes_word="हां")  # full_name (non_empty, any text ok)
    answer(sid, "14/03/1990", yes_word="हां")  # date_of_birth
    answer(sid, "12 Test Street", yes_word="हां")  # address
    result = say(sid, "आवासीय")  # property_type in Hindi -> should store canonical "residential"
    collected = result["state"]["collected_fields"]["property_type"]
    assert collected["value"] == "residential"


def test_unsupported_language_falls_back_to_default():
    body = start("LEAD-1004", language="xx-not-real")
    assert body["state"]["language"] == "en-AU"
    assert "Hi Jordan" in body["agent_text"]


def test_languages_endpoint_lists_supported_languages():
    resp = client.get("/languages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == "en-AU"
    assert set(body["supported"].keys()) == {"en", "en-AU", "hi", "fil"}


def test_en_and_en_au_are_distinct_selections_same_script_content():
    """Same wording (there's no content difference between "English" and
    "English (Australian)" — the AU-specific consent line already exists for
    both), but they must be genuinely independent, selectable options, not
    one hidden behind the other."""
    generic = start("LEAD-1004", language="en")
    australian = start("LEAD-1004", language="en-AU")
    assert generic["state"]["language"] == "en"
    assert australian["state"]["language"] == "en-AU"
    assert generic["agent_text"] == australian["agent_text"]


# --- Network-drop callback / redial ---


def test_network_drop_and_redial_carries_over_collected_fields():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")
    say(sid, "Jordan Lee")  # full_name captured before the "line drops"

    drop_resp = client.post("/voice/simulate-drop", json={"session_id": sid})
    assert drop_resp.status_code == 200
    assert drop_resp.json()["state"]["journey_status"] == "DROPPED_NETWORK"

    pending = client.get("/voice/callbacks/pending").json()
    assert any(p["session_id"] == sid for p in pending)

    redial_resp = client.post("/voice/redial", json={"session_id": sid})
    redial_body = redial_resp.json()
    assert redial_resp.status_code == 200
    assert redial_body["state"]["callback_attempt"] == 1
    # full_name was already captured before the drop — must not be re-asked.
    assert "full_name" in redial_body["state"]["collected_fields"]
    assert redial_body["state"]["collected_fields"]["full_name"]["value"] == "Jordan Lee"

    # A redial is a new call — consent is disclosed again (guardrail: consent
    # first, every call), THEN it should skip straight past full_name.
    assert "recorded" in redial_body["agent_text"].lower()
    consent_result = say(redial_body["session_id"], "yes")
    assert "date of birth" in consent_result["turn"]["agent_text"].lower()


def test_max_callback_attempts_escalates_instead_of_redialling_forever():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")

    # Drop and redial repeatedly until the cap is hit.
    for _ in range(3):
        client.post("/voice/simulate-drop", json={"session_id": sid})
        redial_resp = client.post("/voice/redial", json={"session_id": sid})
        sid = redial_resp.json()["session_id"]

    final_state = redial_resp.json()["state"]
    assert final_state["callback_attempt"] == 3
    assert final_state["journey_status"] == "ESCALATED"
    assert final_state["escalation_reason"] == "OTHER_SAFETY_BOUNDARY"


def test_redial_on_non_dropped_session_is_rejected():
    body = start("LEAD-1004")
    resp = client.post("/voice/redial", json={"session_id": body["session_id"]})
    assert resp.status_code == 400


# --- Persistent call records ---


def test_completed_call_is_persisted_with_reconfirmation_flag():
    body = start("LEAD-1001")
    sid = body["session_id"]
    say(sid, "Yes that's fine")
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
    answer(sid, "afternoon is best")
    result = say(sid, "yes go ahead")
    assert result["turn"]["completed"] is True

    record = client.get(f"/call-records/{sid}", headers=AGENT_HEADERS).json()
    assert record["journey_status"] == "COMPLETED"
    assert record["end_reason"] == "completed"
    assert record["customer_reconfirmed"] is True
    assert record["consent_status"] == "GRANTED"
    assert record["collected_fields"]["full_name"] == "Priya Sharma"
    assert record["collected_fields"]["date_of_birth"] == "14-03-1990"

    listing = client.get("/call-records", headers=AGENT_HEADERS).json()
    assert any(r["session_id"] == sid for r in listing)


def test_escalated_call_is_persisted_without_reconfirmation():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")
    say(sid, "can I speak to a real person please")

    record = client.get(f"/call-records/{sid}", headers=AGENT_HEADERS).json()
    assert record["journey_status"] == "ESCALATED"
    assert record["end_reason"] == "escalated"
    assert record["customer_reconfirmed"] is False
