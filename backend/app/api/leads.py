from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.lead import Lead
from app.services.call_records import close_lead, is_lead_closed
from app.services.lead_service import get_lead, list_leads

router = APIRouter(tags=["leads"])


@router.get("/leads/{lead_id}", response_model=Lead)
def read_lead(lead_id: str) -> Lead:
    lead = get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead_not_found")
    return lead


@router.get("/leads", response_model=list[Lead])
def read_leads() -> list[Lead]:
    return list_leads()


class TerminateResponse(BaseModel):
    lead_id: str
    closed: bool


@router.post("/leads/{lead_id}/terminate", response_model=TerminateResponse)
def terminate_lead(lead_id: str) -> TerminateResponse:
    """Post-call follow-up option #2: "Terminate / close out" — no further
    recovery attempts for this lead. Checked by POST /voice/session the same
    way the DNC registry is, before a new session/call is even created."""
    if get_lead(lead_id) is None:
        raise HTTPException(status_code=404, detail="lead_not_found")
    close_lead(lead_id)
    return TerminateResponse(lead_id=lead_id, closed=True)


@router.get("/leads/{lead_id}/closed", response_model=TerminateResponse)
def check_lead_closed(lead_id: str) -> TerminateResponse:
    return TerminateResponse(lead_id=lead_id, closed=is_lead_closed(lead_id))
