from typing import Optional

from app.state.machine import JourneyStateMachine


class SessionStore:
    """In-memory session state. A 12-hour hackathon build has no business
    standing up Postgres for this — sessions are ephemeral by design and a
    restart simply means starting a fresh call.
    """

    def __init__(self):
        self._sessions: dict[str, JourneyStateMachine] = {}
        self._latest_by_lead: dict[str, str] = {}

    def save(self, machine: JourneyStateMachine) -> None:
        self._sessions[machine.state.session_id] = machine
        self._latest_by_lead[machine.state.lead_id] = machine.state.session_id

    def get(self, session_id: str) -> Optional[JourneyStateMachine]:
        return self._sessions.get(session_id)

    def get_latest_for_lead(self, lead_id: str) -> Optional[JourneyStateMachine]:
        session_id = self._latest_by_lead.get(lead_id)
        return self._sessions.get(session_id) if session_id else None

    def list_all(self) -> list[JourneyStateMachine]:
        return list(self._sessions.values())


session_store = SessionStore()
