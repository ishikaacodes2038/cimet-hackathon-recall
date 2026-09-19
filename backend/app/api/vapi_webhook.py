"""Vapi "Custom LLM" webhook.

Vapi's Custom LLM mode POSTs an OpenAI-chat-completions-shaped request to a
server URL you configure on the Assistant, and expects an OpenAI-chat-
completions-shaped response back. This endpoint adapts that into a call to
the same ConversationOrchestrator used by /voice/message — the orchestration
logic doesn't know or care whether the words came from a text box or a
transcribed phone call.

Unverified against a live Vapi account (see providers/voice/vapi.py) — the
exact request/response envelope should be confirmed against the Vapi
dashboard on-site before the live demo, but the adapter boundary here is
intentionally the only thing that would need to change.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import ConversationOrchestrator
from app.api.deps import get_orchestrator
from app.models.journey import ConsentStatus
from app.services.call_records import save_call_recording
from app.services.lead_service import get_lead
from app.services.session_store import session_store
from app.state.machine import JourneyStateMachine

logger = logging.getLogger("cimet.api.vapi_webhook")

router = APIRouter(prefix="/vapi", tags=["vapi"])


class VapiChatMessage(BaseModel):
    role: str
    content: str


class VapiWebhookRequest(BaseModel):
    messages: list[VapiChatMessage]
    call: dict[str, Any] = {}


@router.post("/webhook")
def vapi_webhook(
    req: VapiWebhookRequest, orchestrator: ConversationOrchestrator = Depends(get_orchestrator)
) -> dict:
    # The session must already exist — created by POST /voice/session, which
    # is what actually places the outbound call via VapiVoiceProvider.start_call
    # and passes session_id through as call metadata. If Vapi's real metadata
    # envelope shape differs from this assumption, this lookup is the first
    # thing to fix on-site.
    session_id = (req.call.get("metadata") or {}).get("session_id")
    machine = session_store.get(session_id) if session_id else None
    if machine is None:
        raise HTTPException(status_code=404, detail="session_not_found_for_call")

    last_user_message = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    lead = get_lead(machine.state.lead_id)
    first_name = lead.first_name if lead else "there"

    turn = orchestrator.handle_utterance(machine, last_user_message, first_name=first_name)
    session_store.save(machine)

    _try_capture_recording(machine, req.call)

    return {
        "choices": [{"message": {"role": "assistant", "content": turn.agent_text}}],
    }


def _try_capture_recording(machine: JourneyStateMachine, call: dict[str, Any]) -> None:
    """Best-effort capture of a Vapi call recording reference. Per Vapi's
    docs as of this build, an artifactPlan.recordingEnabled call exposes the
    recording at call.artifact.recording (private, authenticated URL — we
    store the reference, never download/re-host the audio ourselves).
    UNVERIFIED against a live payload — different Vapi doc pages describe
    this as `call.artifact.recording` vs. `call.artifact.recordingUrl`, and
    Custom-LLM chat-completion turns (what this endpoint mainly handles)
    aren't necessarily the same webhook message as an end-of-call report in
    the first place. Confirm the exact field on-site; this never raises, so
    a shape mismatch can only mean a recording silently isn't captured, not
    that the call breaks.
    """
    try:
        artifact = call.get("artifact") or {}
        recording_url: Optional[str] = artifact.get("recording") or artifact.get("recordingUrl")
        if not recording_url:
            return
        if machine.state.consent_status != ConsentStatus.GRANTED:
            # A recording is never stored without a logged consent, full stop.
            return
        save_call_recording(
            session_id=machine.state.session_id,
            lead_id=machine.state.lead_id,
            recording_url=recording_url,
            consent_confirmed=True,
            duration_seconds=artifact.get("recordingDurationSeconds") or call.get("durationSeconds"),
            format=artifact.get("recordingFormat"),
        )
    except Exception:
        logger.exception("Failed to capture call recording artifact for session %s", machine.state.session_id)
