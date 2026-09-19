from datetime import datetime

from pydantic import BaseModel, Field

from app.models.journey import ConversationTurn, EscalationCategory, JourneyStep
from app.models.journey import utcnow


class HandoffPacket(BaseModel):
    handoff_id: str
    lead_id: str
    session_id: str
    reason: EscalationCategory
    reason_detail: str
    current_step: JourneyStep
    completed_fields: dict[str, str]
    missing_fields: list[str]
    last_customer_message: str
    conversation_summary: str
    confidence: float
    transcript: list[ConversationTurn]
    created_at: datetime = Field(default_factory=utcnow)
