"""Coverage for the follow-up spec: call-end taxonomy, RBAC on call-records/
recordings, multi-call-per-lead, the reconnect (vs. scheduled redial) path,
silence-timeout simulation, and the "Terminate" lead-closing gate."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AGENT = {"X-Demo-Token": "agent-demo-token"}
TEAM_LEAD = {"X-Demo-Token": "lead-demo-token"}
ADMIN = {"X-Demo-Token": "admin-demo-token"}


def start(lead_id: str) -> dict:
    return client.post("/voice/session", json={"lead_id": lead_id}).json()


def say(session_id: str, text: str) -> dict:
    return client.post("/voice/message", json={"session_id": session_id, "text": text}).json()


def answer(session_id: str, text: str) -> dict:
    result = say(session_id, text)
    assert result["state"]["awaiting_confirmation_for"] is not None
    return say(session_id, "yes")


# --- Call-end taxonomy ---


def test_hard_refusal_sets_hard_refusal_end_reason():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")
    result = say(sid, "not interested, please stop calling me")
    assert result["state"]["end_reason"] == "hard_refusal"


def test_busy_deferral_sets_soft_deferral_end_reason():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")
    result = say(sid, "sorry I'm busy right now can't talk")
    assert result["state"]["end_reason"] == "soft_deferral"


def test_consent_decline_sets_soft_deferral_end_reason():
    body = start("LEAD-1004")
    sid = body["session_id"]
    result = say(sid, "no I'm not comfortable being recorded")
    assert result["state"]["end_reason"] == "soft_deferral"


def test_escalation_sets_escalated_end_reason():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")
    result = say(sid, "can I speak to a real person please")
    assert result["state"]["end_reason"] == "escalated"


def test_simulate_drop_sets_abrupt_disconnect_end_reason():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")
    resp = client.post("/voice/simulate-drop", json={"session_id": sid})
    assert resp.json()["state"]["end_reason"] == "abrupt_disconnect"


def test_simulate_silence_timeout_sets_silence_timeout_end_reason():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")
    resp = client.post("/voice/simulate-silence-timeout", json={"session_id": sid})
    result = resp.json()
    assert result["state"]["end_reason"] == "silence_timeout"
    assert result["state"]["journey_status"] == "DROPPED_NETWORK"


# --- RBAC ---


def test_call_records_requires_a_demo_token():
    resp = client.get("/call-records")
    assert resp.status_code == 401


def test_call_records_rejects_an_unknown_token():
    resp = client.get("/call-records", headers={"X-Demo-Token": "not-a-real-token"})
    assert resp.status_code == 401


def test_agent_role_can_view_call_records():
    resp = client.get("/call-records", headers=AGENT)
    assert resp.status_code == 200


def test_agent_role_cannot_view_recordings():
    body = start("LEAD-1004")
    resp = client.get(f"/call-records/{body['session_id']}/recording", headers=AGENT)
    assert resp.status_code == 403


def test_team_lead_role_can_attempt_to_view_recordings():
    """Team Lead clears the role gate — a 404 (no recording exists for this
    session, since nothing in this offline test environment produces a real
    Vapi recording artifact) proves the ROLE CHECK passed; a 403 would mean
    it didn't."""
    body = start("LEAD-1004")
    resp = client.get(f"/call-records/{body['session_id']}/recording", headers=TEAM_LEAD)
    assert resp.status_code == 404


# --- Multi-call-per-lead ---


def test_a_lead_can_have_multiple_call_records_not_one_overwriting_the_last():
    # Two escalations, not a hard refusal — a hard refusal correctly writes
    # back to the DNC registry and blocks the second attempt, which is
    # itself tested elsewhere; that's not what this test is checking.
    lead_id = "LEAD-1004"

    first = start(lead_id)
    say(first["session_id"], "sure")
    say(first["session_id"], "can I speak to a real person please")

    second = start(lead_id)
    say(second["session_id"], "sure")
    say(second["session_id"], "can I speak to a real person please")

    records = client.get(f"/leads/{lead_id}/call-records", headers=AGENT).json()
    session_ids = {r["session_id"] for r in records}
    assert first["session_id"] in session_ids
    assert second["session_id"] in session_ids
    assert len(records) >= 2


# --- Reconnect (immediate) vs. redial (scheduled) ---


def test_reconnect_endpoint_behaves_like_redial_and_carries_fields_forward():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")
    say(sid, "Jordan Lee")  # captured before the "drop"

    client.post("/voice/simulate-drop", json={"session_id": sid})
    resp = client.post("/voice/reconnect", json={"session_id": sid})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"]["callback_attempt"] == 1
    assert "full_name" in body["state"]["collected_fields"]
    assert body["state"]["collected_fields"]["full_name"]["value"] == "Jordan Lee"


def test_reconnect_still_respects_max_callback_attempts():
    body = start("LEAD-1004")
    sid = body["session_id"]
    say(sid, "sure")

    for _ in range(3):
        client.post("/voice/simulate-drop", json={"session_id": sid})
        resp = client.post("/voice/reconnect", json={"session_id": sid})
        sid = resp.json()["session_id"]

    final_state = resp.json()["state"]
    assert final_state["callback_attempt"] == 3
    assert final_state["journey_status"] == "ESCALATED"


# --- Terminate lead ---


def test_terminating_a_lead_blocks_further_call_attempts():
    resp = client.post("/leads/LEAD-1002/terminate")
    assert resp.status_code == 200
    assert resp.json()["closed"] is True

    blocked = start("LEAD-1002")
    assert blocked["blocked"] is True
    assert blocked["block_reason"] == "LEAD_CLOSED"


def test_lead_not_closed_by_default():
    resp = client.get("/leads/LEAD-1003/closed")
    assert resp.json()["closed"] is False
