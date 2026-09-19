from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.state_view import JourneyStateView, serialize_state
from app.services.journey_sandbox import build_submission_payload, journey_sandbox
from app.services.session_store import session_store

router = APIRouter(tags=["journey"])


class ValidateRequest(BaseModel):
    session_id: str


class ValidateResponse(BaseModel):
    ready: bool
    missing_fields: list[str]


class SubmitRequest(BaseModel):
    session_id: str


class SubmitResponse(BaseModel):
    success: bool
    submission_id: str = ""
    errors: list[str] = []


@router.get("/journeys/{lead_id}", response_model=JourneyStateView)
def get_journey(lead_id: str) -> JourneyStateView:
    machine = session_store.get_latest_for_lead(lead_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="no_session_for_lead")
    return serialize_state(machine)


@router.post("/journey/validate", response_model=ValidateResponse)
def validate_journey(req: ValidateRequest) -> ValidateResponse:
    machine = session_store.get(req.session_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    missing = machine.state.missing_fields
    return ValidateResponse(ready=len(missing) == 0, missing_fields=missing)


@router.post("/journey/submit", response_model=SubmitResponse)
def submit_journey(req: SubmitRequest) -> SubmitResponse:
    machine = session_store.get(req.session_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    payload = build_submission_payload(machine.state, machine.script)
    result = journey_sandbox.submit(payload, machine.script)
    if result.success:
        machine.mark_completed(result.submission_id)
        session_store.save(machine)
    return SubmitResponse(success=result.success, submission_id=result.submission_id, errors=result.errors)
