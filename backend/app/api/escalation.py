from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import ConversationOrchestrator
from app.api.deps import get_orchestrator
from app.schemas.extraction import EscalationDecision
from app.services.escalation import evaluate_escalation
from app.services.session_store import session_store

router = APIRouter(tags=["escalation"])


class EvaluateRequest(BaseModel):
    session_id: str
    text: str


@router.post("/escalation/evaluate", response_model=EscalationDecision)
def evaluate(
    req: EvaluateRequest, orchestrator: ConversationOrchestrator = Depends(get_orchestrator)
) -> EscalationDecision:
    """Side-effect-free escalation probe — evaluates a hypothetical utterance
    against the current session without mutating conversation state. Useful
    for testing/demoing the escalation engine directly.
    """
    machine = session_store.get(req.session_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    intent = orchestrator.llm.classify_intent(req.text)
    llm_signal = orchestrator.llm.detect_escalation_signal(req.text, "")
    asked_field = machine.get_next_required_field()

    return evaluate_escalation(
        intent=intent,
        utterance=req.text,
        llm_signal=llm_signal,
        field_retries_exhausted=bool(asked_field and machine.retries_exhausted(asked_field.field)),
        safety_critical_value_hit=False,
        off_script_repeat_count=machine.state.off_script_count,
        advice_repeat_count=machine.state.advice_request_count,
    )
