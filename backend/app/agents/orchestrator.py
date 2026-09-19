"""Conversation orchestrator — the supervisor agent.

This is the only place that decides what the agent says next, and the only
one of the agents below allowed to touch journey state. It is deliberately
NOT an LLM-driven agent loop: every branch is plain Python control flow.

Multi-agent orchestration, concretely: this supervisor delegates to three
specialist sub-agents (app/agents/subagents.py) — ExtractionAgent,
IntentAgent, EscalationSignalAgent — each scoped to exactly one narrow
LLM-backed judgment call. Every sub-agent returns a typed *proposal*; the
supervisor is the only place a proposal can become a state change, and it
always runs the proposal through deterministic validation/gating first.
That's what "the LLM never mutates application state directly" means here.

Every user-facing line — including guardrail refusals, confirmation, and
submission outcome, not just field questions — comes from `machine.script`,
never a hardcoded Python string. That's what makes a Hindi or Filipino call
actually run end-to-end in that language rather than switching languages
mid-sentence.
"""

import logging
import re
import string
from typing import Optional

from app.agents.subagents import EscalationSignalAgent, ExtractionAgent, IntentAgent, SummarizationAgent
from app.guardrails.advice import is_advice_request
from app.guardrails.consent import build_consent_opener, is_consent_decline
from app.guardrails.payment import mentions_payment
from app.guardrails.refusal import is_busy_deferral, is_hard_refusal
from app.models.journey import CallEndReason, ConversationTurn, EscalationCategory, JourneyStatus
from app.schemas.conversation import AgentTurn
from app.services.date_parsing import (
    components_to_ddmmyyyy,
    extract_date_components,
    hint_for_missing_components,
    merge_date_components,
    partial_date_hint,
)
from app.services.escalation import evaluate_escalation
from app.services.handoff import build_handoff_packet
from app.services.llm_client import LLMClient
from app.services.journey_sandbox import build_submission_payload, journey_sandbox
from app.state.machine import JourneyStateMachine
from app.utils.redaction import redact_sensitive

logger = logging.getLogger("cimet.orchestrator")

# Shared across both reconfirmation moments (per-field, and the final
# read-back summary) — one word list, not three copies drifting apart.
#
# Split into single WORDS (matched by token, never by substring) and full
# PHRASES (safe to substring-match — long/specific enough not to appear
# accidentally). A single-word list matched with plain `in` is a trap: "not
# right" contains "right", "incorrect" contains "correct", "not sure"
# contains "sure" — every one of those would have silently flipped a
# customer's correction into a false confirmation. Negation is checked
# FIRST and wins outright, precisely to catch exactly that case.
AFFIRMATIVE_PHRASES = ["that's right", "thats right", "go ahead", "sounds good"]
AFFIRMATIVE_WORDS = {
    "yes", "yeah", "yep", "correct", "sure", "right", "confirmed",
    "हां", "हाँ", "opo", "oo", "sige", "tama",
}
NEGATIVE_WORDS = {
    "no", "not", "nope", "nah", "incorrect", "wrong", "negative",
    "नहीं", "नही", "hindi", "mali", "wala",
}


_TOKEN_STRIP_CHARS = string.punctuation + "।"  # include the Devanagari danda


def _tokenize(text: str) -> set:
    # Split on whitespace rather than a \w-based regex: Python's \w excludes
    # combining marks (Unicode category Mn/Mc), which is how Devanagari
    # matras/anusvara are encoded — "हां" is base "ह" + combining "ा" + "ं",
    # so a \w regex would silently drop them and tokenize it down to just
    # "ह", never matching "हां" in AFFIRMATIVE_WORDS/NEGATIVE_WORDS. Stripping
    # only ASCII punctuation (plus the Devanagari sentence-ending danda) from
    # each whitespace-delimited word's edges keeps combining marks intact.
    return {w.strip(_TOKEN_STRIP_CHARS) for w in text.split()}


def _is_affirmative(text: str) -> bool:
    lowered = text.lower()
    tokens = _tokenize(lowered)
    if tokens & NEGATIVE_WORDS:
        return False
    if any(phrase in lowered for phrase in AFFIRMATIVE_PHRASES):
        return True
    return bool(tokens & AFFIRMATIVE_WORDS)


class ConversationOrchestrator:
    """The supervisor. Holds the shared LLMClient (for summarization, used
    directly by handoff.py) and builds the three specialist sub-agents from
    it — same underlying model/fallback, separate scoped responsibilities."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.extraction_agent = ExtractionAgent(llm_client)
        self.intent_agent = IntentAgent(llm_client)
        self.escalation_signal_agent = EscalationSignalAgent(llm_client)
        self.summarization_agent = SummarizationAgent(llm_client)

    def opening_message(self, machine: JourneyStateMachine, first_name: str, last_activity_date: str) -> str:
        # last_activity_date is a canonical token (e.g. "TODAY"), never
        # freeform English prose — resolved to this call's own language so it
        # can never leak an English fragment into an otherwise-translated
        # opener (see RELATIVE_DATE_DEFAULTS in app/models/script.py).
        localized_date = machine.script.relative_date(last_activity_date)
        opener = build_consent_opener(machine.script, first_name, localized_date)
        self._say(machine, "agent", opener)
        return opener

    def escalate_max_callbacks_reached(self, machine: JourneyStateMachine) -> AgentTurn:
        """Deterministic, not routed through intent classification — after
        MAX_CALLBACK_ATTEMPTS network-drop redials, hand straight to a human
        rather than keep auto-redialling the customer. This must never depend
        on keyword matching a fake utterance; it's called directly by the
        redial endpoint once the attempt cap is hit."""
        return self._escalate(
            machine,
            category=EscalationCategory.OTHER_SAFETY_BOUNDARY,
            reason=f"Reached the maximum of {machine.state.callback_attempt} callback attempts after repeated network drops.",
            confidence=1.0,
            evidence="system: callback attempt cap reached",
        )

    def handle_utterance(self, machine: JourneyStateMachine, utterance: str, first_name: str = "there") -> AgentTurn:
        state = machine.state
        script = machine.script

        if state.journey_status != JourneyStatus.IN_PROGRESS:
            return AgentTurn(agent_text="This call has already ended.", ended=True)

        clean_utterance = redact_sensitive(utterance)
        state.last_customer_utterance = clean_utterance
        self._say(machine, "customer", clean_utterance)
        machine.touch()

        # --- Consent gate: nothing else happens until this resolves. ---
        if state.consent_status.value == "PENDING":
            if is_consent_decline(utterance):
                machine.decline_consent()
                return self._close(machine, script.phrase("hard_refusal_close"))
            machine.grant_consent()
            # If fields were carried over (dropped web journey, or a
            # redialled call resuming after a network drop), say so out
            # loud — real CIMET-family calls read back what's already on
            # file rather than silently sitting on it, per the reference
            # transcript's address-confirmation pattern.
            ack_key = "resume_ack_with_prefill" if state.collected_fields else "consent_grant_ack"
            return self._ask_next_question(machine, first_name, acknowledgement=script.phrase(ack_key))

        # --- Guardrail: payment mention always wins, checked on raw text. ---
        if mentions_payment(utterance):
            return self._escalate(
                machine,
                category=EscalationCategory.SENSITIVE_PAYMENT,
                reason="Customer raised payment/card details, which this channel cannot collect.",
                confidence=0.95,
                evidence=f"customer said: '{clean_utterance}'",
                prefix=script.phrase("payment_refusal"),
            )

        intent = self.intent_agent.classify(utterance)

        if intent.intent == "request_human":
            return self._escalate(
                machine,
                category=EscalationCategory.CUSTOMER_REQUEST,
                reason="Customer explicitly asked to speak to a person.",
                confidence=intent.confidence,
                evidence=intent.evidence,
            )

        if intent.intent == "refuse_decline" and is_hard_refusal(utterance):
            machine.mark_ended_by_customer(CallEndReason.HARD_REFUSAL)
            # "Don't call me again" is a standing no-contact request, not just
            # a reason to end this call — the caller (API layer, which has
            # the phone number) is responsible for writing it back to the DNC
            # registry so the *next* recovery attempt respects it too.
            return self._close(machine, script.phrase("hard_refusal_close"), no_contact_requested=True)

        if is_busy_deferral(utterance):
            machine.mark_ended_by_customer(CallEndReason.SOFT_DEFERRAL)
            return self._close(machine, script.phrase("busy_reschedule"))

        if intent.intent == "anger_frustration":
            llm_signal = self.escalation_signal_agent.propose(utterance, self._recent_context(machine))
            decision = evaluate_escalation(
                intent=intent,
                utterance=utterance,
                llm_signal=llm_signal,
                field_retries_exhausted=False,
                safety_critical_value_hit=False,
                off_script_repeat_count=state.off_script_count,
                advice_repeat_count=state.advice_request_count,
            )
            if decision.should_escalate:
                return self._escalate(
                    machine, decision.category, decision.reason, decision.confidence, decision.evidence
                )

        # A pending per-field reconfirmation ("I heard '14-03-1990' — is that
        # correct?") takes priority over everything below — the customer's
        # reply here is a yes/no about THAT value, not a new answer to
        # extract, and not the final read-back summary.
        if state.awaiting_confirmation_for:
            return self._handle_field_reconfirmation(machine, first_name)

        if is_advice_request(utterance):
            state.advice_request_count += 1
            if state.advice_request_count >= 2:
                return self._escalate(
                    machine,
                    category=EscalationCategory.OFF_SCRIPT,
                    reason="Customer repeated a request for product/financial advice after being redirected.",
                    confidence=0.7,
                    evidence=f"customer said: '{clean_utterance}'",
                )
            return self._ask_next_question(machine, first_name, acknowledgement=script.phrase("advice_refusal"))

        if intent.intent == "generic_question":
            # A legitimate meta-question about the call ("who are you", "is
            # this a scam", "how long will this take") gets a brief, honest
            # answer and a return to whatever was already being asked — not
            # a bare repeated question (reads as the bot ignoring them) and
            # not a capture-failure retry (they didn't attempt to answer, so
            # it shouldn't count against them).
            return self._ask_next_question(machine, first_name, acknowledgement=script.phrase("generic_question_ack"))

        if state.current_step.value == "CONFIRMATION":
            return self._handle_confirmation(machine, intent, first_name)

        asked_field = machine.get_next_required_field()

        if intent.intent == "confusion":
            return self._handle_capture_failure(machine, asked_field, first_name, clarification=True)

        # Default path: attempt to extract structured field values from the utterance.
        # Extraction targets = required missing fields + whichever field was just
        # asked, even if that field is optional — otherwise an optional field
        # can never be captured (it isn't in state.missing_fields at all).
        extraction_target_names = set(state.missing_fields)
        if asked_field and asked_field.field not in state.collected_fields:
            extraction_target_names.add(asked_field.field)
        extraction = self.extraction_agent.propose(
            missing_fields=[machine.script.fields[f] for f in extraction_target_names],
            asked_field=asked_field,
            utterance=utterance,
            context=self._recent_context(machine),
        )

        for item in extraction.extractions:
            field_script = machine.script.fields.get(item.field)
            if not field_script or item.value is None:
                continue
            result = machine.apply_field_value(item.field, item.value, item.confidence, item.evidence)
            if result.accepted:
                # A one-shot full-date capture supersedes any partial pieces
                # collected from earlier turns for this field.
                state.partial_date_components.pop(item.field, None)
                if result.escalate_value:
                    return self._escalate(
                        machine,
                        category=EscalationCategory.OTHER_SAFETY_BOUNDARY,
                        reason="A safety-critical field indicates a vulnerable customer.",
                        confidence=1.0,
                        evidence=item.evidence,
                    )
                if item.confidence < 0.5:
                    return self._escalate(
                        machine,
                        category=EscalationCategory.LOW_CONFIDENCE,
                        reason=f"Low-confidence capture of '{item.field}' — safer to confirm with a human.",
                        confidence=1 - item.confidence,
                        evidence=item.evidence,
                    )

        if asked_field and asked_field.field not in state.collected_fields:
            # off_script_count increments INSIDE the handlers below (next to
            # record_retry), not here — a helpful partial date answer ("just
            # the year") is progress, not deviation, and must never count
            # toward it. See _handle_capture_failure.
            if asked_field.validation.type == "date":
                return self._handle_date_field_failure(machine, asked_field, first_name)
            return self._handle_capture_failure(machine, asked_field, first_name, clarification=False)

        state.off_script_count = 0

        # The field just asked about was captured THIS turn — read it back
        # and lock it only once the customer confirms it, rather than
        # silently trusting the first guess. (Fields captured opportunistically
        # ahead of being asked, or carried over from a prior session, are
        # NOT re-confirmed here — re-litigating every incidental detail would
        # undercut the "ask only what's missing" efficiency goal; this is
        # specifically for the field the agent is actively asking about.)
        if (
            asked_field
            and asked_field.field in state.collected_fields
            and not state.collected_fields[asked_field.field].confirmed
        ):
            return self._ask_field_reconfirmation(machine, asked_field)

        # NOTE: deliberately NOT gated on is_ready_for_confirmation() here —
        # that only checks REQUIRED fields, which would skip straight to
        # confirmation past any optional field still waiting to be asked (an
        # optional field ordered after the last required one would otherwise
        # never get asked at all). _ask_next_question() is the single place
        # that decides "any field left (required or optional) -> ask it,
        # otherwise -> confirmation" and must stay the only decision point.
        return self._ask_next_question(machine, first_name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_capture_failure(self, machine, asked_field, first_name, clarification: bool) -> AgentTurn:
        state = machine.state
        if asked_field is None:
            return self._ask_next_question(machine, first_name)

        machine.record_retry(asked_field.field)
        # Cross-field deviation tally, reset the moment any field is
        # successfully captured (see handle_utterance). Scoped to REQUIRED
        # fields only — declining an OPTIONAL field ("no, don't have it") is
        # normal, on-topic behavior (that's the whole point of it being
        # optional), never deviation.
        if asked_field.required:
            state.off_script_count += 1

        if machine.retries_exhausted(asked_field.field):
            if not asked_field.required:
                # Optional field the customer couldn't/wouldn't answer — skip it
                # and keep the call moving rather than escalating over it.
                machine.skip_optional_field(
                    asked_field.field, reason="skipped after max retries — optional field"
                )
                return self._ask_next_question(machine, first_name)

            if asked_field.field not in state.fallback_offered_fields:
                # First exhaustion on a required field: offer a graceful way
                # out — type it in, or connect to a human — rather than an
                # abrupt hard escalate the moment retries run out. Only a
                # SECOND exhaustion (still no good answer after the offer)
                # actually escalates.
                state.fallback_offered_fields.add(asked_field.field)
                text = machine.script.phrase("capture_fallback_offer")
                self._say(machine, "agent", text)
                return AgentTurn(agent_text=text)

            return self._escalate(
                machine,
                category=EscalationCategory.CONFUSION_REPEATED_FAILURE,
                reason=(
                    f"Failed to capture '{asked_field.field}' after {asked_field.max_retries} attempts, "
                    "even after offering to type it in or connect to a human."
                ),
                confidence=0.85,
                evidence=state.last_customer_utterance or "",
            )

        # Date fields: if the utterance clearly has SOME but not all of
        # day/month/year, ask specifically for what's missing instead of a
        # generic "try again" — a direct, evidence-based fix (a real test
        # utterance, "first January 2026" without a recognised year format,
        # surfaced this gap).
        if not clarification and asked_field.validation.type == "date":
            hint = partial_date_hint(state.last_customer_utterance or "")
            if hint:
                self._say(machine, "agent", hint)
                return AgentTurn(agent_text=hint)

        question = asked_field.clarification_question or asked_field.question
        if asked_field.field not in state.soft_redirect_offered_fields:
            # The first miss on any field gets a warm, human transition back
            # to the question instead of a bare repeat — a customer who went
            # off-topic for a moment (or just gave an unrelated aside) reads
            # a flat repeated question as the bot ignoring them; this is the
            # single softening touch that costs nothing (still counts as a
            # normal retry above) but makes the agent feel less robotic.
            state.soft_redirect_offered_fields.add(asked_field.field)
            text = machine.script.phrase("capture_soft_redirect_template", first_name=first_name, question=question)
            self._say(machine, "agent", text)
            return AgentTurn(agent_text=text)
        self._say(machine, "agent", question)
        return AgentTurn(agent_text=question)

    def _handle_date_field_failure(self, machine: JourneyStateMachine, asked_field, first_name: str) -> AgentTurn:
        """A date-of-birth-style answer given piece by piece across turns
        ("20 September" this turn, "2005" the next) must be combined into
        one complete date, not have each half evaluated — and fail — on its
        own. This is the fix for the exact reported gap: a customer who
        answers a follow-up hint with JUST the missing piece (not the whole
        date again) used to get treated as a fresh capture failure, burning
        a retry and reaching the escalation ladder within two exchanges.
        Only a turn with NOTHING date-shaped in it at all falls through to
        the normal retry ladder — a genuinely helpful partial answer never
        costs a retry."""
        state = machine.state
        field = asked_field.field
        utterance = state.last_customer_utterance or ""
        new_components = extract_date_components(utterance)

        if not new_components:
            return self._handle_capture_failure(machine, asked_field, first_name, clarification=False)

        merged = merge_date_components(state.partial_date_components.get(field, {}), new_components)
        complete = components_to_ddmmyyyy(merged)

        if complete is None:
            # Some but not all of day/month/year known so far — bank the
            # progress and ask ONLY for what's still missing. Deliberately
            # does not call machine.record_retry(): the customer answered
            # correctly, just incompletely, which is not a mishear.
            state.partial_date_components[field] = merged
            hint = hint_for_missing_components(merged)
            self._say(machine, "agent", hint)
            return AgentTurn(agent_text=hint)

        state.partial_date_components.pop(field, None)
        result = machine.apply_field_value(field, complete, confidence=0.8, evidence=f"customer said: '{utterance}'")
        if not result.accepted:
            # The combined pieces form a calendar-impossible date (e.g. day
            # 31 + month February) — a genuine failure, not a free pass.
            return self._handle_capture_failure(machine, asked_field, first_name, clarification=False)

        # Still goes through the same reconfirm-before-lock loop as any other
        # capture — merging across turns never bypasses that safety net.
        return self._ask_field_reconfirmation(machine, asked_field)

    def _ask_field_reconfirmation(self, machine: JourneyStateMachine, field_script) -> AgentTurn:
        state = machine.state
        collected = state.collected_fields[field_script.field]
        text = machine.script.phrase("field_reconfirm_template", value=str(collected.value))
        state.awaiting_confirmation_for = field_script.field
        self._say(machine, "agent", text)
        return AgentTurn(agent_text=text)

    def _handle_field_reconfirmation(self, machine: JourneyStateMachine, first_name: str) -> AgentTurn:
        state = machine.state
        field_name = state.awaiting_confirmation_for
        field_script = machine.script.fields[field_name]
        state.awaiting_confirmation_for = None

        if _is_affirmative(state.last_customer_utterance or ""):
            if field_name in state.collected_fields:
                state.collected_fields[field_name].confirmed = True
            return self._ask_next_question(machine, first_name)

        # Declined — discard the unconfirmed guess and ask again, through the
        # SAME retry/fallback-offer/escalate ladder as a normal capture
        # failure, so a customer who keeps correcting a mishear still gets
        # the graceful "type it in or connect to a human" offer rather than
        # looping forever.
        state.collected_fields.pop(field_name, None)
        # A wrong date shouldn't leave stale day/month/year pieces around to
        # silently merge with whatever the customer says next.
        state.partial_date_components.pop(field_name, None)
        return self._handle_capture_failure(machine, field_script, first_name, clarification=True)

    def _ask_next_question(self, machine: JourneyStateMachine, first_name: str, acknowledgement: str = "") -> AgentTurn:
        next_field = machine.get_next_required_field()
        if next_field is None:
            # No field left to ask (required or optional) -> the journey is
            # complete enough to confirm.
            machine.advance_to_confirmation()
            return self._ask_confirmation(machine)

        question = f"{acknowledgement} {next_field.question}".strip()
        self._say(machine, "agent", question)
        return AgentTurn(agent_text=question)

    def _ask_confirmation(self, machine: JourneyStateMachine) -> AgentTurn:
        text = machine.script.phrase("confirmation_question")
        self._say(machine, "agent", text)
        return AgentTurn(agent_text=text)

    def _handle_confirmation(self, machine: JourneyStateMachine, intent, first_name: str) -> AgentTurn:
        state = machine.state
        script = machine.script
        if intent.intent == "refuse_decline":
            machine.mark_ended_by_customer(CallEndReason.SOFT_DEFERRAL)
            return self._close(machine, script.phrase("confirmation_decline"))

        if not _is_affirmative(state.last_customer_utterance or ""):
            return self._escalate(
                machine,
                category=EscalationCategory.OFF_SCRIPT,
                reason="Customer wants to amend collected details at confirmation — routed to a human rather than guessing which field to change.",
                confidence=0.6,
                evidence=state.last_customer_utterance or "",
            )

        # Customer explicitly reconfirmed the read-back summary — this is the
        # signal that gets persisted to the durable call record, distinct
        # from journey_status, so "was this data customer-confirmed" is
        # always answerable later without re-deriving it from the transcript.
        state.customer_reconfirmed = True

        machine.advance_to_submission()
        payload = build_submission_payload(state, machine.script)
        result = journey_sandbox.submit(payload, machine.script)

        if not result.success:
            logger.error("Journey submission failed for lead %s: %s", state.lead_id, result.errors)
            return self._escalate(
                machine,
                category=EscalationCategory.OTHER_SAFETY_BOUNDARY,
                reason=f"Journey submission failed: {'; '.join(result.errors)}",
                confidence=1.0,
                evidence="submission validation error",
            )

        machine.mark_completed(result.submission_id)
        text = script.phrase("submission_success_template", submission_id=result.submission_id, first_name=first_name)
        self._say(machine, "agent", text, event="JOURNEY_SUBMITTED")
        return AgentTurn(agent_text=text, completed=True, submission_id=result.submission_id)

    def _escalate(
        self,
        machine: JourneyStateMachine,
        category: EscalationCategory,
        reason: str,
        confidence: float,
        evidence: str,
        prefix: str = "",
    ) -> AgentTurn:
        state = machine.state
        machine.mark_escalated()
        state.escalation_reason = category
        state.escalation_evidence = evidence

        packet = build_handoff_packet(state, category, reason, confidence, self.summarization_agent)
        text = f"{prefix} {machine.script.handoff_line}".strip()
        self._say(machine, "agent", text, event="ESCALATION_TRIGGERED")

        return AgentTurn(
            agent_text=text,
            escalated=True,
            escalation_category=category,
            handoff_id=packet.handoff_id,
        )

    def _close(self, machine: JourneyStateMachine, text: str, no_contact_requested: bool = False) -> AgentTurn:
        self._say(machine, "agent", text, event="CALL_ENDED")
        return AgentTurn(agent_text=text, ended=True, no_contact_requested=no_contact_requested)

    def _say(self, machine: JourneyStateMachine, speaker: str, text: str, event: Optional[str] = None) -> None:
        machine.state.conversation_history.append(ConversationTurn(speaker=speaker, text=text, event=event))

    def _recent_context(self, machine: JourneyStateMachine, last_n: int = 6) -> str:
        turns = machine.state.conversation_history[-last_n:]
        return "\n".join(f"{t.speaker}: {t.text}" for t in turns)
