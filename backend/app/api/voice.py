import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import ConversationOrchestrator
from app.api.deps import get_orchestrator, get_voice_provider
from app.config import get_settings
from app.guardrails.dnc import add_to_dnc, check_dnc
from app.models.journey import (
    MAX_CALLBACK_ATTEMPTS,
    TERMINAL_STATUSES,
    CallEndReason,
    ConversationTurn,
    JourneyState,
    JourneyStatus,
)
from app.providers.voice.base import VoiceProvider
from app.schemas.conversation import AgentTurn
from app.schemas.state_view import JourneyStateView, serialize_state
from app.services.call_records import is_lead_closed, log_call_event, save_call_record
from app.services.lead_service import get_lead
from app.services.script_loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, load_energy_script
from app.services.session_store import session_store
from app.state.machine import JourneyStateMachine

logger = logging.getLogger("cimet.api.voice")

router = APIRouter(prefix="/voice", tags=["voice"])


class StartSessionRequest(BaseModel):
    lead_id: str
    language: str = DEFAULT_LANGUAGE


class StartSessionResponse(BaseModel):
    session_id: str = ""
    call_id: Optional[str] = None
    blocked: bool = False
    block_reason: str = ""
    agent_text: str = ""
    state: Optional[JourneyStateView] = None
    call_placement_error: Optional[str] = None


class MessageRequest(BaseModel):
    session_id: str
    text: str


class MessageResponse(BaseModel):
    turn: AgentTurn
    state: JourneyStateView


@router.post("/session", response_model=StartSessionResponse)
def start_session(
    req: StartSessionRequest,
    background_tasks: BackgroundTasks,
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    voice_provider: VoiceProvider = Depends(get_voice_provider),
) -> StartSessionResponse:
    lead = get_lead(req.lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead_not_found")

    # DNC gate sits before call initiation, per the guardrail brief — no
    # session/call is created at all for a DNC-listed number.
    if not check_dnc(lead.phone):
        return StartSessionResponse(blocked=True, block_reason="DNC_LISTED")

    # A lead explicitly closed out ("Terminate" — post-call follow-up option
    # #2) gets no further recovery attempts, same gate shape as DNC.
    if is_lead_closed(lead.lead_id):
        return StartSessionResponse(blocked=True, block_reason="LEAD_CLOSED")

    language = req.language if req.language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    script = load_energy_script(language)
    machine = JourneyStateMachine.start(
        lead_id=lead.lead_id,
        session_id=str(uuid.uuid4()),
        script=script,
        prefilled_fields=lead.prefilled_fields,
        last_completed_step=lead.last_completed_step,
        language=language,
    )

    # Places the real outbound call when VOICE_PROVIDER=vapi; a no-op id
    # generator when running on the mock provider. If a REAL call fails to
    # place (bad credentials, network), that failure is surfaced to the
    # caller rather than silently continuing as if a call were live —
    # never fabricate a successful call.
    try:
        call_id = voice_provider.start_call(lead.phone, machine.state.session_id)
        machine.state.call_id = call_id
    except Exception as exc:
        settings = get_settings()
        if settings.voice_provider == "vapi":
            logger.exception("Failed to place live Vapi call for lead %s", lead.lead_id)
            # A call that never even connects still gets logged — visible in
            # History as FAILED/PROVIDER_ERROR rather than silently vanishing.
            failed_state = JourneyState(
                lead_id=lead.lead_id,
                session_id=machine.state.session_id,
                language=language,
                journey_status=JourneyStatus.FAILED,
                end_reason=CallEndReason.PROVIDER_ERROR,
            )
            save_call_record(failed_state)
            background_tasks.add_task(
                log_call_event, machine.state.session_id, lead.lead_id, "provider_error", {"error": str(exc)}
            )
            return StartSessionResponse(call_placement_error=str(exc))
        # Mock provider never raises in practice; re-raise defensively if it somehow does.
        raise

    opener = orchestrator.opening_message(machine, lead.first_name, lead.last_activity_date)
    session_store.save(machine)
    background_tasks.add_task(
        log_call_event, machine.state.session_id, lead.lead_id, "call_started", {"language": language}
    )

    return StartSessionResponse(
        session_id=machine.state.session_id,
        call_id=machine.state.call_id,
        agent_text=opener,
        state=serialize_state(machine),
    )


@router.post("/message", response_model=MessageResponse)
def send_message(
    req: MessageRequest,
    background_tasks: BackgroundTasks,
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    voice_provider: VoiceProvider = Depends(get_voice_provider),
) -> MessageResponse:
    machine = session_store.get(req.session_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    lead = get_lead(machine.state.lead_id)
    first_name = lead.first_name if lead else "there"

    turn = orchestrator.handle_utterance(machine, req.text, first_name=first_name)
    session_store.save(machine)

    if turn.escalated:
        background_tasks.add_task(
            log_call_event,
            machine.state.session_id,
            machine.state.lead_id,
            "escalation_triggered",
            {"category": turn.escalation_category, "handoff_id": turn.handoff_id},
        )
    if turn.completed or turn.ended:
        background_tasks.add_task(
            log_call_event,
            machine.state.session_id,
            machine.state.lead_id,
            "call_ended",
            {"end_reason": machine.state.end_reason.value if machine.state.end_reason else None},
        )

    # "Don't call me again" is a standing preference, not just an instruction
    # for this call — write it back to the DNC registry so the next dropout-
    # recovery attempt for this lead is blocked before it dials.
    if turn.no_contact_requested and lead:
        add_to_dnc(lead.phone)

    # Drive the real call-control action for a live call. Best-effort: the
    # journey state above is already correct regardless of whether the
    # underlying telephony action succeeds, so a failure here is logged, not
    # raised — the demo shouldn't break because a call-control side-call failed.
    if machine.state.call_id:
        settings = get_settings()
        try:
            if turn.escalated and settings.human_transfer_destination:
                voice_provider.transfer_call(machine.state.call_id, settings.human_transfer_destination)
            elif turn.ended or turn.completed:
                voice_provider.end_call(machine.state.call_id)
        except Exception:
            # The mock provider's end_call/transfer_call are no-ops and never
            # raise; a real Vapi HTTP failure lands here and is logged, not
            # raised — the demo's conversational state is already correct.
            logger.exception("Call-control action failed for call %s", machine.state.call_id)

    # Persist a durable record the moment a call reaches a terminal state —
    # consent, language, everything collected, and whether the customer
    # explicitly reconfirmed it — so it's queryable later, not just held in
    # the in-memory session store.
    if machine.state.journey_status in TERMINAL_STATUSES and not machine.state.call_record_saved:
        save_call_record(machine.state)
        machine.state.call_record_saved = True
        session_store.save(machine)

    return MessageResponse(turn=turn, state=serialize_state(machine))


class SimulateDropRequest(BaseModel):
    session_id: str


@router.post("/simulate-drop", response_model=MessageResponse)
def simulate_network_drop(req: SimulateDropRequest, background_tasks: BackgroundTasks) -> MessageResponse:
    """Represents what a Vapi webhook 'call ended, reason=network' event
    would do in production: the call didn't end because of anything the
    customer chose, so it's eligible for an automatic callback rather than
    being treated as a completed or refused call."""
    machine = session_store.get(req.session_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    machine.state.journey_status = JourneyStatus.DROPPED_NETWORK
    machine.state.end_reason = CallEndReason.ABRUPT_DISCONNECT
    machine.state.conversation_history.append(
        ConversationTurn(speaker="system", text="Call dropped — network issue.", event="CALL_DROPPED_NETWORK")
    )
    if not machine.state.call_record_saved:
        save_call_record(machine.state)
        machine.state.call_record_saved = True
    session_store.save(machine)
    background_tasks.add_task(
        log_call_event, machine.state.session_id, machine.state.lead_id, "disconnect_detected",
        {"end_reason": CallEndReason.ABRUPT_DISCONNECT.value},
    )

    turn = AgentTurn(agent_text="", ended=True)
    return MessageResponse(turn=turn, state=serialize_state(machine))


class SimulateSilenceRequest(BaseModel):
    session_id: str


@router.post("/simulate-silence-timeout", response_model=MessageResponse)
def simulate_silence_timeout(req: SimulateSilenceRequest, background_tasks: BackgroundTasks) -> MessageResponse:
    """The customer stopped responding — distinct from a network drop
    (ABRUPT_DISCONNECT) in end_reason, but reuses the exact same
    DROPPED_NETWORK/redial machinery, since in both cases the call didn't
    end because the customer chose to end it, and the same
    "carry forward what's captured, retry up to MAX_CALLBACK_ATTEMPTS"
    handling applies. There's no live wall-clock inactivity timer in this
    build (the API is a per-turn request/response model, not a persistent
    connection) — this is the demo-simulated trigger, the same pattern
    already established for /voice/simulate-drop."""
    machine = session_store.get(req.session_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    machine.state.journey_status = JourneyStatus.DROPPED_NETWORK
    machine.state.end_reason = CallEndReason.SILENCE_TIMEOUT
    machine.state.conversation_history.append(
        ConversationTurn(speaker="system", text="Customer stopped responding.", event="CALL_SILENCE_TIMEOUT")
    )
    if not machine.state.call_record_saved:
        save_call_record(machine.state)
        machine.state.call_record_saved = True
    session_store.save(machine)
    background_tasks.add_task(
        log_call_event, machine.state.session_id, machine.state.lead_id, "disconnect_detected",
        {"end_reason": CallEndReason.SILENCE_TIMEOUT.value},
    )

    turn = AgentTurn(agent_text="", ended=True)
    return MessageResponse(turn=turn, state=serialize_state(machine))


class PendingCallback(BaseModel):
    session_id: str
    lead_id: str
    callback_attempt: int
    fields_captured: int
    can_retry: bool


@router.get("/callbacks/pending", response_model=list[PendingCallback])
def list_pending_callbacks() -> list[PendingCallback]:
    return [
        PendingCallback(
            session_id=m.state.session_id,
            lead_id=m.state.lead_id,
            callback_attempt=m.state.callback_attempt,
            fields_captured=len(m.state.collected_fields),
            can_retry=m.state.callback_attempt < MAX_CALLBACK_ATTEMPTS,
        )
        for m in session_store.list_all()
        if m.state.journey_status == JourneyStatus.DROPPED_NETWORK
    ]


class RedialRequest(BaseModel):
    session_id: str  # the dropped session to redial


def _resume_dropped_session(
    req: RedialRequest,
    orchestrator: ConversationOrchestrator,
    voice_provider: VoiceProvider,
    background_tasks: BackgroundTasks,
    trigger: str,  # "scheduled_redial" | "immediate_reconnect" — for the event log only
) -> StartSessionResponse:
    """Shared by both /voice/redial (the scheduled/background retry, driven
    from the Callbacks page) and /voice/reconnect (the immediate,
    human-in-the-loop "reconnect now" popup on an abrupt disconnect) — same
    prefill-from-prior-call logic, same MAX_CALLBACK_ATTEMPTS cap either
    way. Only the event-log trigger label differs, so a manual reconnect can
    never bypass the loop-prevention cap the scheduled path already respects."""
    dropped = session_store.get(req.session_id)
    if dropped is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    if dropped.state.journey_status != JourneyStatus.DROPPED_NETWORK:
        raise HTTPException(status_code=400, detail="session_not_dropped")

    lead = get_lead(dropped.state.lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead_not_found")

    next_attempt = dropped.state.callback_attempt + 1
    script = load_energy_script(dropped.state.language)

    # Resume from EVERYTHING the customer already gave us before the line
    # dropped, not just the original web-journey prefill — the same
    # "never re-ask what's already answered" guarantee, now applied to a
    # mid-call network drop instead of a web-form drop-off.
    carried_over = {name: cf.value for name, cf in dropped.state.collected_fields.items()}

    machine = JourneyStateMachine.start(
        lead_id=lead.lead_id,
        session_id=str(uuid.uuid4()),
        script=script,
        prefilled_fields=carried_over,
        last_completed_step=dropped.state.current_step.value,
        language=dropped.state.language,
        callback_attempt=next_attempt,
        previous_session_ids=dropped.state.previous_session_ids + [dropped.state.session_id],
        resume_evidence=f"carried over from callback attempt {dropped.state.callback_attempt} ({dropped.state.end_reason.value if dropped.state.end_reason else 'dropped'})",
    )
    background_tasks.add_task(
        log_call_event, machine.state.session_id, lead.lead_id, "reconnect_attempted",
        {"trigger": trigger, "attempt": next_attempt, "previous_session_id": dropped.state.session_id},
    )

    try:
        call_id = voice_provider.start_call(lead.phone, machine.state.session_id)
        machine.state.call_id = call_id
    except Exception as exc:
        settings = get_settings()
        if settings.voice_provider == "vapi":
            logger.exception("Failed to place callback for lead %s", lead.lead_id)
            failed_state = JourneyState(
                lead_id=lead.lead_id,
                session_id=machine.state.session_id,
                language=dropped.state.language,
                journey_status=JourneyStatus.FAILED,
                end_reason=CallEndReason.PROVIDER_ERROR,
                callback_attempt=next_attempt,
            )
            save_call_record(failed_state)
            return StartSessionResponse(call_placement_error=str(exc))
        raise

    if next_attempt >= MAX_CALLBACK_ATTEMPTS:
        # Third strike — don't just keep auto-redialling a customer forever.
        # Connect, then hand straight to a human with everything collected so
        # far. Deterministic call, not routed through intent classification.
        orchestrator.opening_message(machine, lead.first_name, "LAST_CALLBACK_ATTEMPT")
        turn = orchestrator.escalate_max_callbacks_reached(machine)
        if machine.state.journey_status in TERMINAL_STATUSES and not machine.state.call_record_saved:
            save_call_record(machine.state)
            machine.state.call_record_saved = True
        session_store.save(machine)
        return StartSessionResponse(
            session_id=machine.state.session_id,
            call_id=machine.state.call_id,
            agent_text=turn.agent_text,
            state=serialize_state(machine),
        )

    opener = orchestrator.opening_message(machine, lead.first_name, "TODAY")
    session_store.save(machine)

    return StartSessionResponse(
        session_id=machine.state.session_id,
        call_id=machine.state.call_id,
        agent_text=opener,
        state=serialize_state(machine),
    )


@router.post("/redial", response_model=StartSessionResponse)
def redial(
    req: RedialRequest,
    background_tasks: BackgroundTasks,
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    voice_provider: VoiceProvider = Depends(get_voice_provider),
) -> StartSessionResponse:
    """The scheduled/background retry path — triggered from the Callbacks
    page, not a live human watching the console."""
    return _resume_dropped_session(req, orchestrator, voice_provider, background_tasks, trigger="scheduled_redial")


@router.post("/reconnect", response_model=StartSessionResponse)
def reconnect(
    req: RedialRequest,
    background_tasks: BackgroundTasks,
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    voice_provider: VoiceProvider = Depends(get_voice_provider),
) -> StartSessionResponse:
    """The immediate, human-in-the-loop path — the Console's "reconnect
    now?" popup, shown only when end_reason == ABRUPT_DISCONNECT. Same
    prefill/cap logic as /voice/redial; sits on top of it, doesn't replace it."""
    return _resume_dropped_session(req, orchestrator, voice_provider, background_tasks, trigger="immediate_reconnect")
