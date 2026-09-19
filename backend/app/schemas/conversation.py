from typing import Optional

from pydantic import BaseModel

from app.models.journey import EscalationCategory


class AgentTurn(BaseModel):
    agent_text: str
    escalated: bool = False
    escalation_category: Optional[EscalationCategory] = None
    handoff_id: Optional[str] = None
    ended: bool = False
    completed: bool = False
    submission_id: Optional[str] = None
    no_contact_requested: bool = False
