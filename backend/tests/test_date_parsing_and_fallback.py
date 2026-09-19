"""Regression coverage for three related edge cases found by direct user
testing: a spelled-out ordinal date ("first January 2026") not being
recognised, no targeted help when only part of a date is given, and an
abrupt hard-escalate the moment retries ran out instead of offering a
graceful way out first."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.date_parsing import (
    components_to_ddmmyyyy,
    extract_date_components,
    find_date_span,
    matches_date,
    merge_date_components,
    normalize_to_ddmmyyyy,
    partial_date_hint,
)

client = TestClient(app)


def start(lead_id: str) -> str:
    return client.post("/voice/session", json={"lead_id": lead_id}).json()["session_id"]


def say(session_id: str, text: str) -> dict:
    return client.post("/voice/message", json={"session_id": session_id, "text": text}).json()


def answer(session_id: str, text: str) -> dict:
    """Give an answer and confirm it — a successfully-captured field is now
    read back for confirmation before being locked in."""
    result = say(session_id, text)
    assert result["state"]["awaiting_confirmation_for"] is not None
    return say(session_id, "yes")


# --- Unit-level: the date parser itself ---


def test_spelled_ordinal_date_is_recognised():
    assert matches_date("first January 2026")
    assert matches_date("first of January 2026")
    assert matches_date("twenty-first of March 1990")
    assert matches_date("January first 2026")


def test_regression_full_year_not_truncated_to_a_prefix():
    """The exact reported bug: "first january 2006" (a real STT transcription
    of "first January 2026") used to store as "january 20" — the generic
    "month + short day number" pattern matched a two-digit PREFIX of the
    four-digit year before the correct, longer ordinal-date pattern got a
    chance to. find_date_span must return the full span, and normalization
    must turn it into a real, complete date — not a fragment."""
    span = find_date_span("first january 2006")
    assert span == "first january 2006"
    assert normalize_to_ddmmyyyy("first january 2006") == "01-01-2006"


def test_date_of_birth_without_a_year_is_incomplete_not_valid():
    # "March 14" alone used to be accepted as a complete date — a
    # date-of-birth missing its year is not complete.
    assert not matches_date("March 14")
    assert normalize_to_ddmmyyyy("March 14") is None


def test_digit_and_iso_dates_still_recognised():
    assert matches_date("14/03/1990")
    assert matches_date("1990-03-14")
    assert matches_date("14th of March 1990")


def test_normalize_always_produces_canonical_dd_mm_yyyy():
    """The customer can say a date in any format/language; the STORED value
    is always DD-MM-YYYY, so downstream systems see one consistent format
    regardless of how the call was conducted."""
    assert normalize_to_ddmmyyyy("14/03/1990") == "14-03-1990"
    assert normalize_to_ddmmyyyy("1990-03-14") == "14-03-1990"
    assert normalize_to_ddmmyyyy("14th of March 1990") == "14-03-1990"
    assert normalize_to_ddmmyyyy("March 14th, 1990") == "14-03-1990"
    assert normalize_to_ddmmyyyy("twenty-first of March 1990") == "21-03-1990"


def test_normalize_rejects_impossible_calendar_dates():
    # 31 Feb doesn't exist — must fail closed, not silently store garbage.
    assert normalize_to_ddmmyyyy("31st of February 1990") is None


def test_partial_date_hint_names_specifically_whats_missing():
    assert "year" in partial_date_hint("January")
    assert "day" not in partial_date_hint("January") or "month" not in partial_date_hint("January")
    hint_month_only = partial_date_hint("just 2026")
    assert hint_month_only is not None
    assert "month" in hint_month_only


def test_no_partial_hint_for_pure_gibberish():
    # Nothing date-shaped at all -> no targeted hint, falls through to the
    # normal clarification_question instead.
    assert partial_date_hint("banana") is None


def test_extract_date_components_finds_partial_pieces_independently():
    assert extract_date_components("20 September") == {"day": 20, "month": 9}
    assert extract_date_components("2005") == {"year": 2005}
    assert extract_date_components("the twentieth") == {"day": 20}
    assert extract_date_components("banana") == {}


def test_extract_date_components_does_not_mistake_the_year_for_a_day():
    # A bare year alone must not also register as a "day" via its own digits.
    assert extract_date_components("2005") == {"year": 2005}


def test_merge_date_components_lets_new_turns_fill_in_or_correct_gaps():
    assert merge_date_components({"day": 20, "month": 9}, {"year": 2005}) == {"day": 20, "month": 9, "year": 2005}
    # A later turn correcting an earlier one wins.
    assert merge_date_components({"month": 1}, {"month": 9}) == {"month": 9}


def test_components_to_ddmmyyyy_requires_all_three_and_validates():
    assert components_to_ddmmyyyy({"day": 20, "month": 9, "year": 2005}) == "20-09-2005"
    assert components_to_ddmmyyyy({"day": 20, "month": 9}) is None
    assert components_to_ddmmyyyy({"day": 31, "month": 2, "year": 2005}) is None  # impossible date


# --- End-to-end: the orchestrator actually captures it on the first try ---


def test_spelled_ordinal_date_captured_end_to_end():
    sid = start("LEAD-1004")
    say(sid, "yes")
    answer(sid, "Jordan Lee")
    result = say(sid, "first January 2026")
    assert result["state"]["collected_fields"]["date_of_birth"]["value"] == "01-01-2026"
    assert "date_of_birth" not in result["state"]["missing_fields"]


def test_regression_stt_style_mishear_still_stores_a_complete_date():
    """The exact live-tested scenario: an STT mishearing turns "2026" into
    "2006" (nothing this codebase can fix — that's a transcription accuracy
    issue, not a parsing one), but whatever year it DOES hear must be stored
    as a complete, correct date — not truncated to "january 20"."""
    sid = start("LEAD-1004")
    say(sid, "yes")
    answer(sid, "Jordan Lee")
    result = say(sid, "first january 2006")
    assert result["state"]["collected_fields"]["date_of_birth"]["value"] == "01-01-2006"


def test_partial_date_gets_targeted_followup_not_generic_retry():
    sid = start("LEAD-1004")
    say(sid, "yes")
    answer(sid, "Jordan Lee")
    result = say(sid, "just January")
    assert result["turn"]["escalated"] is False
    assert "day" in result["turn"]["agent_text"].lower() or "year" in result["turn"]["agent_text"].lower()
    # And a full date on the next turn completes it — no wasted retry spent.
    follow = say(sid, "14/03/1990")
    assert "date_of_birth" not in follow["state"]["missing_fields"]


def test_regression_customer_answers_missing_piece_alone_completes_the_date():
    """The exact reported gap: a customer who says a day+month ("20
    September", no year), gets asked for the year, and then answers with
    JUST the year ("2005") — not the whole date again — must have that
    complete the capture. Previously each half was evaluated in isolation:
    "20 September" found no year so it failed, then a bare "2005" (no day or
    month in THAT utterance) also failed to parse as a full date, burning a
    second retry and landing on the fallback offer after only two perfectly
    reasonable answers."""
    sid = start("LEAD-1004")
    say(sid, "yes")
    answer(sid, "Jordan Lee")

    partial = say(sid, "20 September")
    assert partial["turn"]["escalated"] is False
    assert "capture_fallback_offer" not in partial["turn"]["agent_text"]
    assert "year" in partial["turn"]["agent_text"].lower()
    assert "date_of_birth" not in partial["state"]["collected_fields"]

    completed = say(sid, "2005")
    assert completed["turn"]["escalated"] is False
    # Merged, not lost — and routed through the normal reconfirm-before-lock
    # step, not silently trusted.
    assert completed["state"]["awaiting_confirmation_for"] == "date_of_birth"
    assert completed["state"]["collected_fields"]["date_of_birth"]["value"] == "20-09-2005"

    confirmed = say(sid, "yes that's right")
    assert confirmed["state"]["awaiting_confirmation_for"] is None
    assert "date_of_birth" not in confirmed["state"]["missing_fields"]


def test_regression_three_separate_pieces_across_three_turns_still_combine():
    """Day, month, and year each given on their own turn — the most
    fragmented realistic case — must still combine into one date, costing
    zero retries along the way."""
    sid = start("LEAD-1004")
    say(sid, "yes")
    answer(sid, "Jordan Lee")

    say(sid, "the twentieth")
    say(sid, "of September")
    result = say(sid, "2005")
    assert result["turn"]["escalated"] is False
    assert result["state"]["collected_fields"]["date_of_birth"]["value"] == "20-09-2005"


# --- Graceful fallback offer before hard escalation ---


def test_fallback_offer_appears_before_hard_escalation():
    sid = start("LEAD-1004")
    say(sid, "yes")
    answer(sid, "Jordan Lee")
    say(sid, "banana")
    offer = say(sid, "gibberish again")
    assert offer["turn"]["escalated"] is False
    assert "connect you with someone" in offer["turn"]["agent_text"]

    escalated = say(sid, "still gibberish")
    assert escalated["turn"]["escalated"] is True
    assert escalated["turn"]["escalation_category"] == "CONFUSION_REPEATED_FAILURE"


def test_asking_for_human_during_fallback_offer_escalates_immediately():
    sid = start("LEAD-1004")
    say(sid, "yes")
    answer(sid, "Jordan Lee")
    say(sid, "banana")
    offer = say(sid, "gibberish again")
    assert offer["turn"]["escalated"] is False

    result = say(sid, "just connect me to a person please")
    assert result["turn"]["escalated"] is True
    assert result["turn"]["escalation_category"] == "CUSTOMER_REQUEST"
