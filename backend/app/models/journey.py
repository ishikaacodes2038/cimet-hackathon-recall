from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JourneyStep(str, Enum):
    START = "START"
    CONSENT = "CONSENT"
    LOAD_EXISTING_DATA = "LOAD_EXISTING_DATA"
    IDENTITY = "IDENTITY"
    PROPERTY = "PROPERTY"
    ENERGY_USAGE = "ENERGY_USAGE"
    SAFETY_CONCESSION = "SAFETY_CONCESSION"
    PREFERENCES = "PREFERENCES"
    CONFIRMATION = "CONFIRMATION"
    SUBMISSION = "SUBMISSION"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"
    ENDED = "ENDED"


class EscalationCategory(str, Enum):
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    ANGER_FRUSTRATION = "ANGER_FRUSTRATION"
    CONFUSION_REPEATED_FAILURE = "CONFUSION_REPEATED_FAILURE"
    OFF_SCRIPT = "OFF_SCRIPT"
    SENSITIVE_PAYMENT = "SENSITIVE_PAYMENT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    OTHER_SAFETY_BOUNDARY = "OTHER_SAFETY_BOUNDARY"


class ConsentStatus(str, Enum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    DECLINED = "DECLINED"


class DncStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    CLEAR = "CLEAR"
    LISTED = "LISTED"


class JourneyStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"
    ENDED_BY_CUSTOMER = "ENDED_BY_CUSTOMER"
    DROPPED_NETWORK = "DROPPED_NETWORK"
    BLOCKED_DNC = "BLOCKED_DNC"
    FAILED = "FAILED"


# Terminal statuses a call cannot progress past without a fresh session.
TERMINAL_STATUSES = {
    JourneyStatus.COMPLETED,
    JourneyStatus.ESCALATED,
    JourneyStatus.ENDED_BY_CUSTOMER,
    JourneyStatus.DROPPED_NETWORK,
    JourneyStatus.FAILED,
}

MAX_CALLBACK_ATTEMPTS = 3


class CallEndReason(str, Enum):
    """Exhaustive taxonomy of every way a call can terminate — every code
    path that reaches a terminal JourneyStatus must set exactly one of
    these, so "why did this call end" is always answerable from the record
    alone, never re-derived by guessing from journey_status + transcript.

    Mapping notes (journey_status doesn't have a 1:1 slot for each reason):
    - A consent DECLINE maps to SOFT_DEFERRAL, not HARD_REFUSAL — declining
      to be recorded on THIS call is not the same as "never contact me
      again" (no DNC write-back happens for a consent decline, same as a
      busy deferral).
    - ABRUPT_DISCONNECT and SILENCE_TIMEOUT both currently reuse
      JourneyStatus.DROPPED_NETWORK (same redial/MAX_CALLBACK_ATTEMPTS
      machinery — the customer didn't choose to end the call in either
      case) — end_reason is what actually distinguishes them.
    - PROVIDER_ERROR uses the previously-unused JourneyStatus.FAILED, for
      the case where the call never even connects (e.g. Vapi rejects the
      placement) — logged so it's visible in history, not silently dropped.
    """

    COMPLETED = "completed"
    ESCALATED = "escalated"
    HARD_REFUSAL = "hard_refusal"
    SOFT_DEFERRAL = "soft_deferral"
    ABRUPT_DISCONNECT = "abrupt_disconnect"
    SILENCE_TIMEOUT = "silence_timeout"
    PROVIDER_ERROR = "provider_error"


class SubmissionStatus(str, Enum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"


class ConversationTurn(BaseModel):
    speaker: str  # "agent" | "customer" | "system"
    text: str
    timestamp: datetime = Field(default_factory=utcnow)
    event: Optional[str] = None  # e.g. "ESCALATION_TRIGGERED", for the event timeline


class CollectedField(BaseModel):
    field: str
    value: Any
    confidence: float
    evidence: str
    confirmed: bool = False


class JourneyState(BaseModel):
    lead_id: str
    session_id: str
    call_id: Optional[str] = None  # set when a real voice-provider call was placed (Vapi mode only)
    language: str = "en"
    current_step: JourneyStep = JourneyStep.START
    completed_steps: list[JourneyStep] = Field(default_factory=list)

    # Callback/redial lineage — a dropped call (network issue, not customer
    # choice) can be redialed picking up exactly where it left off, the same
    # way a dropped WEB journey is resumed. Capped so the agent doesn't just
    # keep auto-redialing a customer forever.
    callback_attempt: int = 0
    previous_session_ids: list[str] = Field(default_factory=list)

    customer_reconfirmed: bool = False
    call_record_saved: bool = False

    required_fields: list[str] = Field(default_factory=list)
    collected_fields: dict[str, CollectedField] = Field(default_factory=dict)
    retry_counts: dict[str, int] = Field(default_factory=dict)
    off_script_count: int = 0
    advice_request_count: int = 0
    # Fields where retries were exhausted and the customer was already
    # offered a graceful fallback (type it in / connect to a human) once —
    # a second exhaustion on the same field escalates for real. Prevents an
    # abrupt hard-escalate on the very first run of bad luck with STT.
    fallback_offered_fields: set[str] = Field(default_factory=set)

    # A date field the customer is answering piece by piece (e.g. "20
    # September" this turn, "2005" the next) accumulates here instead of
    # each partial answer being evaluated — and failed — in isolation. Keyed
    # by field name, e.g. {"day": 20, "month": 9}. Cleared once the field is
    # fully captured or the customer declines it at reconfirmation.
    partial_date_components: dict[str, dict[str, int]] = Field(default_factory=dict)

    # Fields where the customer has already been given one warm/soft
    # redirect back to the question (rather than a bare repeat) — only the
    # first miss per field gets the softer phrasing, so it can't just repeat
    # forever without ever counting toward the normal retry ladder's tone.
    soft_redirect_offered_fields: set[str] = Field(default_factory=set)

    # Set right after a field is captured, cleared once the customer
    # confirms or corrects it. While set, the customer's next reply is
    # interpreted as yes/no about THIS field, not a new answer or intent.
    awaiting_confirmation_for: Optional[str] = None

    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    last_customer_utterance: Optional[str] = None

    escalation_status: bool = False
    escalation_reason: Optional[EscalationCategory] = None
    escalation_evidence: Optional[str] = None

    consent_status: ConsentStatus = ConsentStatus.PENDING
    dnc_status: DncStatus = DncStatus.UNKNOWN

    journey_status: JourneyStatus = JourneyStatus.IN_PROGRESS
    end_reason: Optional[CallEndReason] = None
    submission_status: SubmissionStatus = SubmissionStatus.NOT_SUBMITTED
    submission_id: Optional[str] = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def missing_fields(self) -> list[str]:
        return [f for f in self.required_fields if f not in self.collected_fields]
