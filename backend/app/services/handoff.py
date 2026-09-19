import uuid
from typing import Optional

from app.agents.subagents import SummarizationAgent
from app.models.journey import EscalationCategory, JourneyState
from app.schemas.handoff import HandoffPacket


class HandoffStore:
    def __init__(self):
        self._packets: dict[str, HandoffPacket] = {}

    def save(self, packet: HandoffPacket) -> None:
        self._packets[packet.handoff_id] = packet

    def get(self, handoff_id: str) -> Optional[HandoffPacket]:
        return self._packets.get(handoff_id)

    def list_all(self) -> list[HandoffPacket]:
        return list(self._packets.values())


handoff_store = HandoffStore()


def _deterministic_summary(state: JourneyState) -> str:
    collected = ", ".join(f"{f}={cf.value}" for f, cf in state.collected_fields.items()) or "nothing yet"
    return (
        f"Energy dropout-recovery call for lead {state.lead_id}, currently at step "
        f"{state.current_step.value}. Collected so far: {collected}. "
        f"Still missing: {', '.join(state.missing_fields) or 'none'}."
    )


def build_handoff_packet(
    state: JourneyState,
    reason: EscalationCategory,
    reason_detail: str,
    confidence: float,
    summarization_agent: SummarizationAgent,
) -> HandoffPacket:
    collected_summary = _deterministic_summary(state)
    transcript_text = "\n".join(f"{t.speaker}: {t.text}" for t in state.conversation_history)

    # Guardrail: an LLM outage must never block a handoff — the deterministic
    # summary is always present (SummarizationAgent falls back to it on any
    # failure); the LLM can only improve on it, never gate it.
    summary = summarization_agent.summarize(transcript_text, collected_summary)

    packet = HandoffPacket(
        handoff_id=str(uuid.uuid4()),
        lead_id=state.lead_id,
        session_id=state.session_id,
        reason=reason,
        reason_detail=reason_detail,
        current_step=state.current_step,
        completed_fields={f: str(cf.value) for f, cf in state.collected_fields.items()},
        missing_fields=state.missing_fields,
        last_customer_message=state.last_customer_utterance or "",
        conversation_summary=summary,
        confidence=confidence,
        transcript=list(state.conversation_history),
    )
    handoff_store.save(packet)
    return packet
