from typing import Optional

from pydantic import BaseModel

# English safety net — used only if a script file is missing a phrase key,
# so a malformed/incomplete translation degrades gracefully instead of
# raising, while every shipped script (en/hi/fil) defines its own.
PHRASE_DEFAULTS = {
    "consent_grant_ack": "Great, thank you.",
    "resume_ack_with_prefill": "Great, thank you — I can see we already have some of your details on file, so I'll only ask what's still missing.",
    "advice_refusal": (
        "I can't recommend a specific plan for you — I'm only able to collect your details so our "
        "system can generate a comparison. Someone can talk through the options with you afterwards. "
        "Shall we keep going with a few more details?"
    ),
    "payment_refusal": (
        "I'm not able to take payment or card details over this call — that's not something this line "
        "handles for your security. I'll send you a secure link to enter your payment details yourself, "
        "and connect you with someone who can help with anything else."
    ),
    "hard_refusal_close": (
        "Understood — thank you for letting me know. I've noted your preference and I won't call again "
        "about this. Have a good day."
    ),
    "busy_reschedule": "No worries at all — I'll let you go. We can try again another time if that suits better.",
    "confirmation_question": "Just to confirm — I've got everything I need now. Shall I go ahead and submit this comparison for you?",
    "confirmation_decline": "No problem — I won't submit anything. Thanks for your time.",
    "capture_fallback_offer": (
        "I'm having a bit of trouble catching that correctly — remember, this call is specifically to "
        "finish your energy comparison, so I do need this to keep going. You're welcome to type it in "
        "instead, or I can connect you with someone who can help."
    ),
    "field_reconfirm_template": "I heard '{value}' — is that correct?",
    "capture_soft_redirect_template": "No worries, {first_name} — let's get that sorted. {question}",
    "generic_question_ack": (
        "Good question — I'm an automated assistant calling on behalf of CIMET about the energy "
        "comparison you started, and this call is recorded for quality and training purposes."
    ),
    "submission_success_template": (
        "All done — I've submitted your energy comparison (reference {submission_id}). "
        "You'll hear back with your options shortly. Thanks for your time, {first_name}!"
    ),
}

# The consent opener names WHEN the customer last engaged (e.g. "earlier
# today", "yesterday"). That's spoken data, not a fixed sentence, so callers
# pass one of these canonical tokens (never freeform English prose) and each
# script translates it — otherwise an English phrase like "earlier today"
# gets interpolated straight into an otherwise fully-Hindi/Filipino sentence,
# which is exactly the "bot switches language mid-call" bug this closes.
RELATIVE_DATE_DEFAULTS = {
    "TODAY": "earlier today",
    "YESTERDAY": "yesterday",
    "TWO_DAYS_AGO": "two days ago",
    "MONDAY": "Monday",
    "LAST_CALLBACK_ATTEMPT": "our last attempt to reach you",
}


class FieldValidation(BaseModel):
    type: str  # "non_empty" | "email" | "date" | "postcode_au" | "enum" | "yes_no"
    options: Optional[list[str]] = None
    # Guardrail against vague/irrelevant answers on free-text ("non_empty")
    # fields — without this, a bare "yes"/"ok"/"sure" given in response to
    # "what's your address?" used to be stored as a literal address. A
    # script can raise min_length or set reject_generic_filler=False for a
    # field where short generic-sounding answers are actually legitimate.
    min_length: int = 3
    reject_generic_filler: bool = True


class FieldScript(BaseModel):
    field: str
    section: str
    purpose: str
    question: str
    clarification_question: Optional[str] = None
    validation: FieldValidation
    extraction_hints: list[str] = []
    max_retries: int = 2
    required: bool = True
    safety_critical: bool = False
    # values (as lowercase strings) that, if collected for this field, trigger an immediate escalation
    escalate_on_values: list[str] = []


class SectionScript(BaseModel):
    name: str
    opening_line: Optional[str] = None
    fields: list[str]


class JourneyScript(BaseModel):
    vertical: str
    consent_line: str
    handoff_line: str
    sections: list[SectionScript]
    fields: dict[str, FieldScript]
    # Every other user-facing line the orchestrator can say (confirmation
    # question, refusals, submission outcome, etc.) — keyed so the script is
    # the ONE place all customer-facing text lives, in whatever language this
    # file is in. See PHRASE_DEFAULTS for the fallback if a script omits one.
    phrases: dict[str, str] = {}
    # Translations for the RELATIVE_DATE_DEFAULTS tokens above, in this
    # script's language. Falls back to English if a script omits one.
    relative_date_labels: dict[str, str] = {}

    def phrase(self, key: str, **kwargs: str) -> str:
        template = self.phrases.get(key) or PHRASE_DEFAULTS.get(key, "")
        return template.format(**kwargs) if kwargs else template

    def relative_date(self, token: str) -> str:
        return self.relative_date_labels.get(token) or RELATIVE_DATE_DEFAULTS.get(token, token)

    def field_order(self) -> list[str]:
        order: list[str] = []
        for section in self.sections:
            order.extend(section.fields)
        return order

    def required_field_names(self) -> list[str]:
        return [name for name in self.field_order() if self.fields[name].required]
