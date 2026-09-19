from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import ConversationOrchestrator
from app.api.deps import get_orchestrator
from app.models.journey import EscalationCategory
from app.schemas.handoff import HandoffPacket
from app.services.handoff import build_handoff_packet, handoff_store
from app.services.session_store import session_store

router = APIRouter(tags=["handoff"])


class CreateHandoffRequest(BaseModel):
    session_id: str
    reason: EscalationCategory
    reason_detail: str = ""
    confidence: float = 1.0


@router.post("/handoff", response_model=HandoffPacket)
def create_handoff(
    req: CreateHandoffRequest, orchestrator: ConversationOrchestrator = Depends(get_orchestrator)
) -> HandoffPacket:
    machine = session_store.get(req.session_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    return build_handoff_packet(
        machine.state, req.reason, req.reason_detail, req.confidence, orchestrator.summarization_agent
    )


@router.get("/handoff/{handoff_id}", response_model=HandoffPacket)
def get_handoff(handoff_id: str) -> HandoffPacket:
    packet = handoff_store.get(handoff_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="handoff_not_found")
    return packet


@router.get("/handoffs", response_model=list[HandoffPacket])
def list_handoffs() -> list[HandoffPacket]:
    return sorted(handoff_store.list_all(), key=lambda p: p.created_at, reverse=True)
