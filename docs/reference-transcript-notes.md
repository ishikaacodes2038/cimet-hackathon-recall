# Reference transcript — analysis notes

Source: `call-transcript-redacted.pdf`, the only test data provided by the hackathon organiser ahead of the event. A de-identified transcript of a real outbound **Internet/NBN plan sales call**, run by a CIMET-family agent (the agent names both "Internet's comparison" and "Econnex Comparison" — confirming this is the same company/platform family referenced in the hackathon brief, `econnex`).

**Important caveat, read first:** this is an Internet **sales** call (a new signup), not an Energy **dropout-recovery** call (resuming an abandoned comparison journey). Some patterns transfer directly; some don't. Each item below says which.

## Patterns that transfer directly (and are now reflected in the build)

1. **Recording disclosure wording.** The real agent says: *"please be advised that this call will be recorded for quality assurance and training purposes."* Our `consent_line` already matched this closely — good independent validation of the original phrasing.

2. **NMI/MIRN as optional, gracefully skippable.** The real agent asks the customer to find an "ABC ID" on their existing bill and explicitly says *"it's okay if you don't see it, that means it's not visible on the bill"* — i.e., treated as optional, not blocking. This directly validates a design decision already made independently: `nmi_or_mirn` is `required: false` with a 1-retry cap in our script.

3. **Read-back confirmation of known data.** The real agent reads back the address before proceeding: *"your address is [SERVICE_ADDRESS], correct?"* Our system did **not** do this — prefilled/carried-over fields were loaded silently with zero verbal mention to the customer. **Fixed**: added a `resume_ack_with_prefill` phrase spoken once after consent, acknowledging that some details are already on file, without re-confirming each one individually (which would undercut the brief's "ask only for missing information" instruction).

4. **Payment handled by redirecting to self-service, not just "get a human."** The redaction notes state plainly: *"The agent muted the recording before collecting payment information, and the customer entered card details directly into a web form."* An AI voice agent has no "mute" — escalation is still the right call per the brief ("hand off instead"). But the phrasing was updated to reflect the same self-service pattern: the `payment_refusal` line now says *"I'll send you a secure link to enter your payment details yourself"* rather than only offering a live transfer.

## Patterns noted but deliberately NOT copied

- **Promotional/tiered pricing negotiation** ("$42.90 for six months, then $72.90") — this is sales-specific bargaining. Dropout recovery is completing an already-in-progress comparison, not negotiating a deal; the brief itself notes recovery calls are lower-stakes than a retention call. Not applicable.
- **Cross-sell into other verticals at the end of the call** ("since we helped with Internet, how about electricity and gas?") — explicitly out of scope; the brief scopes this build to Energy only.
- **Agent guiding the customer through their own web checkout live** ("click apply now", "select yes") — this transcript's call has the *customer* clicking through a self-service form with the agent narrating, which is neither of the two modes described in the brief (Mode A: human fills the console; Mode B: AI runs the journey). Worth flagging to the organiser — see the open questions in the main chat response.

## Patterns worth noting for authenticity, not changed

- Heavy use of "K?" as a checking-in tic, disfluency, and repetition throughout. Not incorporated into the scripts — a *dummy* script should read as a clean, intentional design, not a literal transcription of one real (imperfect) call. Noted here so the choice is visible, not accidental.
