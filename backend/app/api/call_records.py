import random

from fastapi import APIRouter, Depends, HTTPException

from app.auth import DemoUser, Role, require_role
from app.services.call_records import (
    CallEvent,
    CallRecord,
    CallRecording,
    get_call_record,
    get_call_recording,
    list_call_events,
    list_call_records,
    list_call_records_for_lead,
    list_call_recordings_for_lead,
    log_call_event,
    save_call_recording,
)

router = APIRouter(tags=["call-records"])


@router.get("/call-records", response_model=list[CallRecord])
def list_records(limit: int = 100, user: DemoUser = Depends(require_role(Role.AGENT))) -> list[CallRecord]:
    return list_call_records(limit=limit)


@router.get("/call-records/{session_id}", response_model=CallRecord)
def get_record(session_id: str, user: DemoUser = Depends(require_role(Role.AGENT))) -> CallRecord:
    record = get_call_record(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="call_record_not_found")
    return record


@router.get("/leads/{lead_id}/call-records", response_model=list[CallRecord])
def list_records_for_lead(lead_id: str, user: DemoUser = Depends(require_role(Role.AGENT))) -> list[CallRecord]:
    """Every attempt for this lead, newest first — a lead can now have
    multiple call records instead of one overwriting the last."""
    return list_call_records_for_lead(lead_id)


@router.get("/leads/{lead_id}/call-events", response_model=list[CallEvent])
def list_events_for_lead(lead_id: str, user: DemoUser = Depends(require_role(Role.AGENT))) -> list[CallEvent]:
    return list_call_events(lead_id=lead_id)


@router.get("/call-records/{session_id}/events", response_model=list[CallEvent])
def list_events_for_session(session_id: str, user: DemoUser = Depends(require_role(Role.AGENT))) -> list[CallEvent]:
    return list_call_events(session_id=session_id)


@router.get("/call-records/{session_id}/recording", response_model=CallRecording)
def get_recording(session_id: str, user: DemoUser = Depends(require_role(Role.TEAM_LEAD))) -> CallRecording:
    recording = get_call_recording(session_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="recording_not_found")
    # Access to a recording is itself logged — a guardrail worth demoing on
    # its own, given how compliance-heavy this brief already is.
    log_call_event(
        session_id=session_id,
        lead_id=recording.lead_id,
        event_type="recording_accessed",
        payload={"accessed_by": user.username, "role": user.role.name},
    )
    return recording


@router.get("/leads/{lead_id}/recordings", response_model=list[CallRecording])
def list_recordings_for_lead(lead_id: str, user: DemoUser = Depends(require_role(Role.TEAM_LEAD))) -> list[CallRecording]:
    return list_call_recordings_for_lead(lead_id)


@router.post("/call-records/{session_id}/simulate-recording", response_model=CallRecording)
def simulate_recording(session_id: str, user: DemoUser = Depends(require_role(Role.TEAM_LEAD))) -> CallRecording:
    """No live Vapi account exists in this build, so nothing ever produces a
    REAL recording — the webhook path in app/api/vapi_webhook.py that would
    normally capture one is simply never exercised. This is the same
    "demo affordance for an otherwise-unreachable path" pattern already used
    for /voice/simulate-drop and /voice/simulate-silence-timeout: it
    generates a placeholder reference URL (never a real audio file) so the
    STORAGE, RBAC-gated RETRIEVAL, and ACCESS-LOGGING can all be exercised
    and demoed end-to-end without a live telephony account.
    """
    record = get_call_record(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="call_record_not_found")
    if record.consent_status != "GRANTED":
        # A recording is never stored without a logged consent, full stop —
        # matches the same rule the real Vapi-webhook path enforces.
        raise HTTPException(status_code=400, detail="cannot simulate a recording without granted consent")

    duration = round(random.uniform(45.0, 240.0), 1)
    recording_url = f"https://demo-recordings.invalid/{session_id}.mp3"
    save_call_recording(
        session_id=session_id,
        lead_id=record.lead_id,
        recording_url=recording_url,
        consent_confirmed=True,
        duration_seconds=duration,
        format="mp3",
    )
    log_call_event(
        session_id=session_id,
        lead_id=record.lead_id,
        event_type="recording_simulated",
        payload={"simulated_by": user.username, "role": user.role.name},
    )
    return get_call_recording(session_id)
