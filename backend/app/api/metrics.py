from pydantic import BaseModel

from fastapi import APIRouter

from app.models.journey import JourneyStatus
from app.services.handoff import handoff_store
from app.services.session_store import session_store

router = APIRouter(tags=["metrics"])


class MetricsSummary(BaseModel):
    total_sessions: int
    completed: int
    escalated: int
    ended_by_customer: int
    in_progress: int
    completion_rate: float
    escalation_rate: float
    total_handoffs: int
    avg_fields_captured: float
    avg_turns: int


@router.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary() -> MetricsSummary:
    """Live-computed from actual session state in this running server —
    never a hand-typed or cached number, so it can't drift from reality
    during a demo."""
    sessions = session_store.list_all()
    total = len(sessions)

    completed = sum(1 for m in sessions if m.state.journey_status == JourneyStatus.COMPLETED)
    escalated = sum(1 for m in sessions if m.state.journey_status == JourneyStatus.ESCALATED)
    ended = sum(1 for m in sessions if m.state.journey_status == JourneyStatus.ENDED_BY_CUSTOMER)
    in_progress = sum(1 for m in sessions if m.state.journey_status == JourneyStatus.IN_PROGRESS)

    fields_counts = [len(m.state.collected_fields) for m in sessions] or [0]
    turn_counts = [len(m.state.conversation_history) for m in sessions] or [0]

    return MetricsSummary(
        total_sessions=total,
        completed=completed,
        escalated=escalated,
        ended_by_customer=ended,
        in_progress=in_progress,
        completion_rate=(completed / total) if total else 0.0,
        escalation_rate=(escalated / total) if total else 0.0,
        total_handoffs=len(handoff_store.list_all()),
        avg_fields_captured=sum(fields_counts) / len(fields_counts),
        avg_turns=round(sum(turn_counts) / len(turn_counts)),
    )
