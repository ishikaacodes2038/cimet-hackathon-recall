from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def start(lead_id: str) -> str:
    return client.post("/voice/session", json={"lead_id": lead_id}).json()["session_id"]


def say(session_id: str, text: str) -> dict:
    return client.post("/voice/message", json={"session_id": session_id, "text": text}).json()


def test_metrics_summary_reflects_live_session_state():
    before = client.get("/metrics/summary").json()

    sid = start("LEAD-1004")
    say(sid, "sure")
    say(sid, "can I speak to a real person please")

    after = client.get("/metrics/summary").json()
    assert after["total_sessions"] == before["total_sessions"] + 1
    assert after["escalated"] == before["escalated"] + 1


def test_list_handoffs_includes_new_escalation():
    sid = start("LEAD-1004")
    say(sid, "sure")
    result = say(sid, "can I speak to a real person please")
    handoff_id = result["turn"]["handoff_id"]

    listing = client.get("/handoffs").json()
    assert any(h["handoff_id"] == handoff_id for h in listing)
