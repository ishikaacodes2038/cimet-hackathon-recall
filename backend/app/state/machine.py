from typing import Optional

from app.models.journey import (
    CallEndReason,
    CollectedField,
    ConsentStatus,
    JourneyState,
    JourneyStatus,
    JourneyStep,
    SubmissionStatus,
    utcnow,
)
from app.models.script import FieldScript, JourneyScript
from app.services.validation import validate_field_value

# Section name -> JourneyStep, so "current_step" always reflects where the
# state machine is, independent of which field within the section is active.
SECTION_TO_STEP = {
    "IDENTITY": JourneyStep.IDENTITY,
    "PROPERTY": JourneyStep.PROPERTY,
    "ENERGY_USAGE": JourneyStep.ENERGY_USAGE,
    "SAFETY_CONCESSION": JourneyStep.SAFETY_CONCESSION,
    "PREFERENCES": JourneyStep.PREFERENCES,
}


class FieldUpdateResult:
    def __init__(self, accepted: bool, reason: str = "", escalate_value: bool = False):
        self.accepted = accepted
        self.reason = reason
        self.escalate_value = escalate_value


class JourneyStateMachine:
    """Deterministic journey progression. Owns required fields, validation,
    step advancement, and submission readiness. The LLM never touches this
    directly — it only proposes field values, which this class accepts,
    rejects, or asks to be re-collected.
    """

    def __init__(self, state: JourneyState, script: JourneyScript):
        self.state = state
        self.script = script

    @classmethod
    def start(
        cls,
        lead_id: str,
        session_id: str,
        script: JourneyScript,
        prefilled_fields: Optional[dict[str, str]] = None,
        last_completed_step: Optional[str] = None,
        language: str = "en",
        callback_attempt: int = 0,
        previous_session_ids: Optional[list[str]] = None,
        resume_evidence: str = "carried over from the dropped-off web journey",
    ) -> "JourneyStateMachine":
        state = JourneyState(
            lead_id=lead_id,
            session_id=session_id,
            language=language,
            required_fields=script.required_field_names(),
            current_step=JourneyStep.START,
            callback_attempt=callback_attempt,
            previous_session_ids=previous_session_ids or [],
        )
        machine = cls(state, script)

        # LOAD_EXISTING_DATA: resume from what's already captured — either the
        # dropped-off web journey, or (for a redialled call) everything the
        # customer already gave us before the line dropped — so nothing already
        # answered is ever re-asked.
        for field_name, value in (prefilled_fields or {}).items():
            if field_name in script.fields:
                state.collected_fields[field_name] = CollectedField(
                    field=field_name,
                    value=value,
                    confidence=1.0,
                    evidence=resume_evidence,
                    confirmed=True,
                )
        if last_completed_step:
            state.conversation_history.append(
                _system_event(f"Resuming after previously completed step: {last_completed_step}")
            )
        state.completed_steps.append(JourneyStep.LOAD_EXISTING_DATA)
        return machine

    def get_next_required_field(self) -> Optional[FieldScript]:
        for name in self.script.field_order():
            if name not in self.state.collected_fields:
                field_script = self.script.fields[name]
                if field_script.required or self.state.retry_counts.get(name, 0) == 0:
                    return field_script
        return None

    def apply_field_value(self, field_name: str, raw_value: str, confidence: float, evidence: str) -> FieldUpdateResult:
        field_script = self.script.fields[field_name]
        result = validate_field_value(field_script, raw_value)

        if not result.valid:
            # Retry counting is centralized in the orchestrator's capture-failure
            # handler, which runs for BOTH "no candidate extracted at all" and
            # "candidate extracted but invalid" — incrementing here too would
            # double-count the invalid-candidate case.
            return FieldUpdateResult(False, reason=result.reason)

        self.state.collected_fields[field_name] = CollectedField(
            field=field_name,
            value=result.normalized_value,
            confidence=confidence,
            evidence=evidence,
        )
        self._sync_current_step(field_script)

        escalate = result.normalized_value is not None and str(result.normalized_value).lower() in {
            v.lower() for v in field_script.escalate_on_values
        }
        return FieldUpdateResult(True, escalate_value=escalate)

    def record_retry(self, field_name: str) -> None:
        self.state.retry_counts[field_name] = self.state.retry_counts.get(field_name, 0) + 1

    def skip_optional_field(self, field_name: str, reason: str) -> None:
        """An optional field the customer couldn't/wouldn't answer after max
        retries is skipped, not escalated — only REQUIRED fields escalate on
        retry exhaustion. This keeps the call moving instead of derailing it
        over an ancillary detail like a meter number.
        """
        self.state.collected_fields[field_name] = CollectedField(
            field=field_name, value=None, confidence=0.0, evidence=reason
        )

    def retries_exhausted(self, field_name: str) -> bool:
        field_script = self.script.fields[field_name]
        return self.state.retry_counts.get(field_name, 0) >= field_script.max_retries

    def _sync_current_step(self, field_script: FieldScript) -> None:
        step = SECTION_TO_STEP.get(field_script.section)
        if step and step not in self.state.completed_steps:
            self.state.current_step = step

    def is_ready_for_confirmation(self) -> bool:
        return len(self.state.missing_fields) == 0

    def advance_to_confirmation(self) -> None:
        for step in SECTION_TO_STEP.values():
            if step not in self.state.completed_steps:
                self.state.completed_steps.append(step)
        self.state.current_step = JourneyStep.CONFIRMATION

    def advance_to_submission(self) -> None:
        self.state.current_step = JourneyStep.SUBMISSION

    def mark_completed(self, submission_id: str) -> None:
        self.state.current_step = JourneyStep.COMPLETED
        self.state.journey_status = JourneyStatus.COMPLETED
        self.state.end_reason = CallEndReason.COMPLETED
        self.state.submission_status = SubmissionStatus.SUBMITTED
        self.state.submission_id = submission_id

    def mark_escalated(self) -> None:
        self.state.current_step = JourneyStep.ESCALATED
        self.state.journey_status = JourneyStatus.ESCALATED
        self.state.end_reason = CallEndReason.ESCALATED
        self.state.escalation_status = True

    def mark_ended_by_customer(self, reason: CallEndReason) -> None:
        self.state.current_step = JourneyStep.ENDED
        self.state.journey_status = JourneyStatus.ENDED_BY_CUSTOMER
        self.state.end_reason = reason

    def grant_consent(self) -> None:
        self.state.consent_status = ConsentStatus.GRANTED
        self.state.completed_steps.append(JourneyStep.CONSENT)

    def decline_consent(self) -> None:
        self.state.consent_status = ConsentStatus.DECLINED
        # Declining to be recorded on THIS call isn't "never contact me
        # again" — no DNC write-back happens here, same as a busy deferral,
        # so it shares that end_reason rather than HARD_REFUSAL.
        self.mark_ended_by_customer(CallEndReason.SOFT_DEFERRAL)

    def touch(self) -> None:
        self.state.updated_at = utcnow()


def _system_event(text: str):
    from app.models.journey import ConversationTurn

    return ConversationTurn(speaker="system", text=text, event="RESUMED_JOURNEY")
