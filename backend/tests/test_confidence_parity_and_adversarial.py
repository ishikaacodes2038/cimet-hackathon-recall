"""Two gaps flagged in the priority re-prioritization pass:

1. Confidence parity — `evaluate_escalation` (escalation.py) is the single
   place that decides LOW_CONFIDENCE, and it only ever looks at the
   `Intent.confidence` float it's handed — it has no idea which LLMClient
   produced that float. These tests prove that directly: build an `Intent`
   the way each client's `classify_intent` return type looks, and confirm
   the same 0.5 threshold escalates identically either way. This can't
   prove Claude's *real* confidence numbers in production stay well-
   calibrated (that needs a live key), but it proves the decision logic
   itself has no client-specific special-casing that could silently
   under-escalate for one client and not the other.

2. Adversarial scenarios beyond the textbook six: mid-utterance interruption
   with a correction, and a garbled/talked-over utterance that should read
   as low confidence rather than a confident wrong guess.
"""

from fastapi.testclient import TestClient

from app.guardrails.payment import mentions_payment
from app.main import app
from app.schemas.extraction import EscalationSignal, Intent
from app.services.escalation import evaluate_escalation

client = TestClient(app)


def _baseline_kwargs(**overrides):
    kwargs = dict(
        utterance="",
        llm_signal=EscalationSignal(category=None, confidence=0.0, evidence=""),
        field_retries_exhausted=False,
        safety_critical_value_hit=False,
        off_script_repeat_count=0,
        advice_repeat_count=0,
    )
    kwargs.update(overrides)
    return kwargs


def test_low_confidence_intent_escalates_regardless_of_which_client_produced_it():
    # Same shape RuleBasedLLMClient.classify_intent returns on no strong match.
    rule_based_intent = Intent(intent="provide_information", confidence=0.3, evidence="no strong signal; default")
    # Same shape an AnthropicLLMClient tool-call response would deserialize into.
    anthropic_intent = Intent(intent="other", confidence=0.35, evidence="ambiguous, hedged phrasing")

    for intent in (rule_based_intent, anthropic_intent):
        decision = evaluate_escalation(intent=intent, **_baseline_kwargs())
        assert decision.should_escalate is True
        assert decision.category == "LOW_CONFIDENCE"


def test_high_confidence_intent_does_not_escalate_regardless_of_which_client_produced_it():
    rule_based_intent = Intent(intent="provide_information", confidence=0.9, evidence="matched phrase")
    anthropic_intent = Intent(intent="provide_information", confidence=0.85, evidence="clear, unambiguous")

    for intent in (rule_based_intent, anthropic_intent):
        decision = evaluate_escalation(intent=intent, **_baseline_kwargs())
        assert decision.should_escalate is False


def start(lead_id: str) -> str:
    resp = client.post("/voice/session", json={"lead_id": lead_id})
    assert resp.status_code == 200
    return resp.json()["session_id"]


def send(session_id: str, text: str) -> dict:
    resp = client.post("/voice/message", json={"session_id": session_id, "text": text})
    assert resp.status_code == 200
    return resp.json()


def test_scenario_customer_talks_over_agent_mid_question_then_corrects():
    session_id = start("LEAD-1002")
    send(session_id, "yes go ahead")
    # Customer starts answering before the question finishes, cuts themself
    # off, then immediately corrects — should land as a normal capture on
    # the correction, not a confused/garbled escalation.
    r = send(session_id, "wait sorry— actually no, hold on, it's Jamie Lee")
    assert r["state"]["journey_status"] in ("IN_PROGRESS", "COMPLETED")


def test_spoken_digit_word_card_number_is_caught_like_numeral_digits():
    numerals = "my card number is 4222111111111111"
    spoken_words = (
        "it's four two two two, one one one one, one one one one, one one one one"
    )
    assert mentions_payment(numerals) is True
    assert mentions_payment(spoken_words) is True


def test_a_couple_of_spoken_numbers_in_normal_conversation_is_not_flagged():
    assert mentions_payment("I moved in about two years ago, maybe three") is False


def test_scenario_garbled_talked_over_utterance_is_low_confidence_not_a_confident_wrong_guess():
    session_id = start("LEAD-1002")
    # Whatever free-text field is being actively asked about right now —
    # not any already-prefilled field carried over from the web journey.
    before = send(session_id, "yes go ahead")["state"]["collected_fields"]
    # Simulates STT garbage from cross-talk / background noise — no clean
    # field-shaped content, should not be silently accepted as a value.
    r = send(session_id, "[unintelligible crosstalk] mm hm yeah no wait what")
    after = r["state"]["collected_fields"]
    newly_captured = {k: v for k, v in after.items() if k not in before}
    for field in newly_captured.values():
        assert field["confidence"] < 0.7
