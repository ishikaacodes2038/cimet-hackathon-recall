from pydantic import BaseModel

from app.models.journey import CallEndReason, ConversationTurn, EscalationCategory, JourneyStatus, JourneyStep
from typing import Optional


class CollectedFieldView(BaseModel):
    value: str
    confidence: float
    evidence: str


class CallEfficiencyView(BaseModel):
    fields_captured: int
    fields_captured_first_try: int
    fields_needing_retry: int
    duration_seconds: float
    no_human_touch: bool


class JourneyStateView(BaseModel):
    lead_id: str
    session_id: str
    language: str
    current_step: JourneyStep
    journey_status: JourneyStatus
    end_reason: Optional[CallEndReason]
    consent_status: str
    collected_fields: dict[str, CollectedFieldView]
    missing_fields: list[str]
    escalation_status: bool
    escalation_reason: Optional[EscalationCategory]
    submission_status: str
    submission_id: Optional[str]
    customer_reconfirmed: bool
    callback_attempt: int
    awaiting_confirmation_for: Optional[str]
    conversation_history: list[ConversationTurn]
    efficiency: CallEfficiencyView


def _efficiency(state) -> CallEfficiencyView:
    captured = list(state.collected_fields.keys())
    first_try = [f for f in captured if state.retry_counts.get(f, 0) == 0]
    duration = 0.0
    if len(state.conversation_history) >= 2:
        duration = (
            state.conversation_history[-1].timestamp - state.conversation_history[0].timestamp
        ).total_seconds()
    return CallEfficiencyView(
        fields_captured=len(captured),
        fields_captured_first_try=len(first_try),
        fields_needing_retry=len(captured) - len(first_try),
        duration_seconds=round(duration, 1),
        no_human_touch=state.journey_status == JourneyStatus.COMPLETED,
    )


def serialize_state(machine) -> JourneyStateView:
    state = machine.state
    return JourneyStateView(
        lead_id=state.lead_id,
        session_id=state.session_id,
        language=state.language,
        current_step=state.current_step,
        journey_status=state.journey_status,
        end_reason=state.end_reason,
        consent_status=state.consent_status.value,
        collected_fields={
            name: CollectedFieldView(
                value="(not provided)" if cf.value is None else str(cf.value),
                confidence=cf.confidence,
                evidence=cf.evidence,
            )
            for name, cf in state.collected_fields.items()
        },
        missing_fields=state.missing_fields,
        escalation_status=state.escalation_status,
        escalation_reason=state.escalation_reason,
        submission_status=state.submission_status.value,
        submission_id=state.submission_id,
        customer_reconfirmed=state.customer_reconfirmed,
        callback_attempt=state.callback_attempt,
        awaiting_confirmation_for=state.awaiting_confirmation_for,
        conversation_history=state.conversation_history,
        efficiency=_efficiency(state),
    )
