# Recall — Architecture & Wiring Guide

This document explains, in plain language, what "Recall" (the CIMET Energy
dropout-recovery voice agent) is built from, how every piece is wired
together, and — as a concrete worked example — exactly why the "first
January 2026" date-of-birth bug happened and what fixed it.

---

## 1. What the app actually does

A customer started an energy-plan switch on CIMET's website, got partway
through the form, and dropped off. Recall places (or simulates) an outbound
call, picks the conversation back up in whatever language the customer
prefers, asks only for whatever is still missing, and submits the completed
journey — or hands off to a human the moment something needs a person
(payment info, anger, a direct request, repeated confusion, a safety flag
like life support).

It is **not** a raw LLM chatbot. The LLM (or a deterministic rule-based
stand-in, see §4) is only ever allowed to *propose* a value or a
classification. A plain-Python state machine is the only thing that can
actually change what's stored, what question comes next, or whether the call
ends/escalates/submits. This split is the single most important design
decision in the whole app, and it's why the doc keeps coming back to it.

---

## 2. Tech stack — what's actually being used

| Layer | Technology | Why |
|---|---|---|
| Backend framework | **FastAPI** (Python 3.9) | async-friendly, typed request/response models, auto docs |
| Data validation | **Pydantic v2** | every request, response, and internal state object is a typed model — no loose dicts flowing through the system |
| Conversation state | In-memory `session_store` (dict keyed by session_id) | fine for a hackathon/demo; would become Redis/DB-backed for production |
| Durable call records | **SQLite** (`backend/app/services/call_records.py`) | one row per call, written the moment a call reaches a terminal state (completed/escalated/ended) |
| LLM | **Anthropic Claude** via the `anthropic` Python SDK, tool-calling / structured output — used *only if* `LLM_API_KEY` is set | see §4 for the fallback that runs without it |
| Voice (telephony) | **Vapi** (`app/providers/voice/vapi.py`) — used *only if* `VOICE_PROVIDER=vapi` | real outbound calls, transfer-to-human, end-call control |
| Voice (default/demo) | **Mock provider** (`app/providers/voice/mock.py`) | no external account needed; generates fake call IDs, everything else runs identically |
| Browser speech-to-text | **Web Speech API** — `SpeechRecognition` / `webkitSpeechRecognition` (built into Chrome/Edge) | zero cost, zero vendor account, degrades to text input where unsupported (Firefox/Safari) |
| Browser text-to-speech | **Web Speech API** — `SpeechSynthesis` | same as above — this is what actually *speaks* the agent's lines in the browser demo |
| Frontend | **React + TypeScript + Vite** | `frontend/src/pages/Console.tsx` is the live-call UI |
| Scripts / prompts | Plain **YAML** files, one per language (`scripts/energy/recovery.{en,hi,fil}.yaml`) | every user-facing sentence — including guardrail refusals — is data, not a hardcoded Python string |

**Nothing here is a hidden or "magic" AI service** — the two swappable
external dependencies (Claude for language understanding, Vapi for actual
phone calls) both have deterministic, fully-functional fallbacks so the app
never needs live credentials to run or be demoed end-to-end.

---

## 3. Request lifecycle — how a call actually flows

```
Browser (Console.tsx)
   |
   |  POST /voice/session {lead_id, language}
   v
FastAPI app/api/voice.py
   |  - DNC check (blocks before any call is even placed)
   |  - load_energy_script(language)         <- YAML for that language
   |  - JourneyStateMachine.start(...)        <- prefill from the dropped web journey
   |  - voice_provider.start_call(...)        <- mock, or real Vapi call
   |  - orchestrator.opening_message(...)     <- consent disclosure, from the script
   v
Response: {session_id, agent_text, state}
   |
   |  (customer speaks -> browser STT -> text)
   |
   |  POST /voice/message {session_id, text}
   v
ConversationOrchestrator.handle_utterance()   <- see §5, the supervisor
   |
   |  turn-by-turn: guardrails -> intent -> extraction -> validation -> next question
   v
Response: {turn: {agent_text, escalated, completed, ...}, state}
   |
   |  (browser speaks agent_text via TTS)
```

Every single turn goes through the same `/voice/message` endpoint whether
the customer typed or spoke — the browser's Speech-to-Text just turns audio
into the same `text` field a typed message would use. That's deliberate: it
means the entire backend is testable (and was tested — 74 tests) without a
microphone, and the voice layer is a thin, swappable adapter.

---

## 4. The LLM layer — and why the app doesn't fall over without one

`backend/app/services/llm_client.py` defines one interface, `LLMClient`,
with three implementations, selected by `LLM_PROVIDER`:

- **`RuleBasedLLMClient`** — deterministic keyword/regex matching, no
  network call, no API key. This is the *default* when `LLM_API_KEY` isn't
  set, and it's also what every automated test runs against (tests must
  never depend on a live API call or be flaky because of one).
- **`AnthropicLLMClient`** (`LLM_PROVIDER=anthropic`) — real Claude calls
  using **tool-calling / structured output** (the `tools` + `tool_choice`
  parameters on the Messages API), so the model's response is always a
  validated JSON object, never free text that has to be parsed hopefully.
  If a live call throws for any reason (network, rate limit, bad key), it
  **catches the exception and falls back to the rule-based client** rather
  than breaking the call.
- **`SarvamLLMClient`** (`LLM_PROVIDER=sarvam`) — real calls to Sarvam AI's
  OpenAI-compatible chat-completions endpoint (`LLM_BASE_URL`), prompted for
  a strict JSON object instead of using tool-calling (Sarvam's tool-calling
  support wasn't confirmed at build time). Same fallback-on-any-exception
  wrapping as the Anthropic client. **Unverified against a live account** —
  built against Sarvam's documented API shape (Bearer auth, `/chat/completions`,
  `response_format: json_object`) but never exercised against a real key in
  this build environment, the same status Vapi's voice provider was in
  before §12's live-key check. Confirm the exact envelope (auth header name,
  whether `json_object` mode is actually honored, the real model name) once
  a key is pasted into `.env`, and fix only inside `SarvamLLMClient` if it
  differs — nothing else should need to change.

Both implementations answer exactly four questions, and nothing else:
1. `extract_fields` — does this utterance contain a value for any of the
   fields we're still missing?
2. `classify_intent` — is the customer answering, asking for a human,
   refusing, angry, asking for advice, confused, or something else?
3. `detect_escalation_signal` — a fuzzy read on tone (used only for the
   anger/frustration case, and always combined with hard keyword rules).
4. `summarize` — a 2-3 sentence handoff summary for the human agent, with a
   deterministic fallback if this fails.

### Multi-agent orchestration, concretely

The "multi-agent" part isn't separate processes or separate models — it's an
architectural split of responsibility, all wrapping the same `LLMClient`:

```
ConversationOrchestrator (supervisor)
   |
   +-- ExtractionAgent          -> proposes field values (never applies them)
   +-- IntentAgent               -> proposes an intent label
   +-- EscalationSignalAgent     -> proposes an escalation signal (anger, etc.)
   +-- SummarizationAgent        -> proposes a handoff summary
```

Every one of these returns a typed **proposal**. The orchestrator is the
*only* place a proposal can become a real state change, and it always runs
the proposal through deterministic code first:
- `app/services/validation.py` — is this actually a valid value for this
  field's type (date, email, enum, postcode, yes/no)?
- `app/services/escalation.py` — hard rules (explicit human request, payment
  mention, safety-critical value, retry exhaustion) always win over model
  judgment; the LLM's opinion is only consulted for the ambiguous
  anger/frustration case, and only as one input among several.

This is why the LLM being wrong, offline, or replaced by the rule-based
fallback can never cause the agent to submit a bad value or skip a guardrail
— it can only ever cause a *missed* extraction (which just means the
customer gets asked again), never an *incorrect* one being trusted.

---

## 5. The conversation supervisor — `ConversationOrchestrator.handle_utterance()`

This is the single function that decides what happens on every turn. It
runs as a strict, ordered gate list — read top to bottom, each check either
returns immediately or falls through to the next:

1. **Consent gate** — nothing else happens until consent is granted or
   declined. This is checked before literally anything else, every call.
2. **Payment mention** — always escalates immediately, regardless of what
   else is happening, checked on the raw (un-redacted) text so it can never
   be missed by a text-cleaning step.
3. **Explicit "speak to a human"** — always wins, no confidence threshold.
4. **Hard refusal / "don't call me again"** — ends the call and (at the API
   layer) writes the phone number back into the Do-Not-Call registry.
5. **"I'm busy" deferral** — ends the call politely, no escalation.
6. **Anger/frustration** — escalates if the deterministic + LLM signal
   agree it's real anger, not just checked by itself.
7. **A pending field reconfirmation** ("I heard 'Jordan Lee' — is that
   correct?") — if one is pending, the customer's reply is *always*
   interpreted as answering that yes/no, never as a new field value. See §7.
8. **Off-topic advice request** ("which plan should I pick?") — redirected
   once, escalated if repeated.
9. **Confirmation step** — if the whole journey is fully collected and
   we're reading back the final summary, handle that separately.
10. **Default: extraction** — try to pull structured field values out of
    what the customer said, validate each one, and either lock it in,
    reject it, or (if confidence is low) escalate it for a human to check.

Guardrails 1–6 are checked **before** the reconfirmation gate (step 7) very
deliberately — a customer who's mid-reconfirmation but suddenly says "just
connect me to a person" must still escalate immediately, not get stuck
answering a yes/no about a field value they no longer care about. There's a
dedicated test for exactly this (`test_asking_for_human_during_a_reconfirmation_still_escalates_immediately`).

---

## 6. Multi-language design — and the en / en-AU fix

Every user-facing sentence the agent ever says — field questions,
confirmations, guardrail refusals, the reconfirmation prompt, the closing
line — comes from `machine.script.phrase(...)`, which reads from a
per-language YAML file (`scripts/energy/recovery.en.yaml`,
`recovery.hi.yaml`, `recovery.fil.yaml`). **There is no hardcoded English
string anywhere in the orchestrator.** That's what makes a full Hindi or
Filipino call actually stay in that language for the whole conversation
rather than switching mid-sentence.

### The "bot switches to English mid-Hindi-call" bug

This turned out **not** to be a language-detection bug at all — the backend
never listens to what language the customer replies in; it always speaks
whatever language the session was started with. The actual cause was found
by grepping the Hindi script file for `(` followed by a Latin letter:
four of the Hindi questions had **English words left in parentheses as
translation aids**, e.g.:

```
क्या यह आवासीय (residential) है या व्यावसायिक (business) प्रॉपर्टी?
```

The browser's text-to-speech reads *everything* on the line — including
"(residential)" and "(business)" — literally, in an English-accented voice,
which is what sounded like the bot switching languages mid-sentence. Fixed
by removing the four parenthetical glosses, while deliberately **keeping**
genuinely untranslatable terms (NMI/MIRN, the official "Pensioner Concession
Card / Health Care Card" names, and "CIMET" itself) — those are correct to
say in English even in an otherwise-Hindi sentence, the same way a Hindi
speaker would.

A second, related fix in the same pass: the Hindi script had inconsistent
verb gender (`कर रहा/रही हूं`, `जा रहा/रही हूं` — the masculine/feminine slash
forms Hindi uses for first-person verbs). A voice agent has one persona, one
voice — so every line was normalized to a single consistent grammatical
gender (feminine), matching the female voice preference in the frontend's
voice-picker.

### English vs. English (Australian)

There is no wording difference between "English" and "English (Australian)"
— CIMET is an Australian company and the script was already written in
Australian English. What differs is purely which **BCP-47 voice/recognition
tag** the browser uses:

```python
# backend/app/services/script_loader.py
SUPPORTED_LANGUAGES = {"en": "English", "en-AU": "English (Australian)", "hi": "Hindi", "fil": "Filipino (Tagalog)"}
SCRIPT_FILE_FOR = {"en": "en", "en-AU": "en", "hi": "hi", "fil": "fil"}  # both map to the SAME script file
DEFAULT_LANGUAGE = "en-AU"
```

```ts
// frontend/src/useVoice.ts
export const VOICE_LANG_MAP = { en: "en-US", "en-AU": "en-AU", hi: "hi-IN", fil: "tl-PH" };
```

They're genuinely independent, selectable dropdown options — not one hidden
behind the other — but backed by one shared script file, so there's no
content to keep in sync between them.

---

## 7. Reconfirm-before-lock — the new safety net for STT mishears

This is the direct fix for the reported failure mode: the agent used to
trust the **first** thing it extracted from an utterance and lock it in
immediately. Now, every field the agent is *actively asking about* goes
through a read-back loop before it's treated as final:

```
customer: "Jordan Lee"
agent:    "I heard 'Jordan Lee' — is that correct?"   <- awaiting_confirmation_for = "full_name"
customer: "yes"                                        <- confirmed = True, move to next question
   -- or --
customer: "no, that's not right"                        <- value discarded, field re-asked
```

Implementation:
- `JourneyState.awaiting_confirmation_for: Optional[str]` — which field, if
  any, is currently pending a yes/no.
- `_ask_field_reconfirmation()` — builds the "I heard 'X' — is that
  correct?" line from the script's `field_reconfirm_template` phrase, and
  sets `awaiting_confirmation_for`.
- `_handle_field_reconfirmation()` — the very next thing checked in
  `handle_utterance()` (after guardrails) once a reconfirmation is pending.
  Affirmative → `CollectedField.confirmed = True`, move on. Negative → the
  guessed value is discarded and re-asked through the *same* retry/fallback
  ladder as a normal capture failure (so repeated corrections still get a
  graceful "type it in or connect to a human" offer instead of looping
  forever).

Scope decision, worth being explicit about: **only the field actively being
asked about is reconfirmed.** Fields volunteered ahead of being asked (e.g.
the customer mentions "residential, electricity" while answering the name
question) or carried over from the dropped web journey are captured/kept
directly, without an individual reconfirmation — re-litigating every
incidental detail would undercut the "only ask what's missing" efficiency
goal that resuming a dropped journey is supposed to deliver.

---

## 8. Date-of-birth: the exact bug, and the exact fix

This is the specific example from live testing: the customer said "first
January 2026", the STT engine (a real, external transcription accuracy
issue, not something this codebase controls) heard "first january 2006",
and the form ended up storing **"january 20"** — a truncated fragment, not
even the mis-heard year.

### Root cause #1 — first-match instead of best-match

The date parser (`find_date_span()`) tried a list of regex patterns in
order and returned as soon as *any one* of them matched:

```python
DATE_PATTERNS = [
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
    r"\d{4}-\d{1,2}-\d{1,2}",
    r"(month)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}",      # "March 14th, 1990"
    ...
]
```

A generic earlier pattern like "month name + a short 1-2 digit number"
would match against `"first january 2006"` by grabbing just **`"20"`** — the
first two digits of the four-digit year `2006` — because the day-number part
of the regex (`\d{1,2}`) had no requirement that it stop at a digit
boundary. It matched, so the function returned immediately with a two-digit
fragment, and the much more specific/correct pattern for spelled-out
ordinals ("first of January 2026") never even got a chance to run.

### Root cause #2 — unbounded digit matching

The `\d{1,2}` used for "day" wasn't anchored, so it was happy to match a
**prefix** of a longer digit run instead of a standalone 1-2 digit number.

### The fix — `backend/app/services/date_parsing.py`

Two changes, both necessary:

1. **`find_date_span()` now evaluates every pattern and keeps the longest
   match**, not the first one:
   ```python
   def find_date_span(text: str) -> Optional[str]:
       best = None
       for pattern in DATE_PATTERNS:
           match = re.search(pattern, text.lower())
           if match and (best is None or len(match.group(0)) > len(best)):
               best = match.group(0)
       return best
   ```
   Now the full-span ordinal-date pattern ("first january 2006", 19
   characters) always beats the accidental 2-character prefix match.

2. **Every day/year digit group is boundary-anchored with a lookaround**,
   not `\b`:
   ```python
   _DAY_DIGIT = r"(?<!\d)\d{1,2}(?!\d)"          # not "\b\d{1,2}\b"
   _YEAR = r"(?<!\d)(?:19|20)\d{2}(?!\d)"
   ```
   `\b` was tried first and made things *worse* — it broke ordinal suffixes
   like "14th", because `\b` requires a transition between a "word" and
   "non-word" character, and both `4` and `t` count as word characters in
   regex, so there's no boundary between them at all. The lookaround form
   (`(?<!\d)...(?!\d)`) means "not immediately preceded or followed by
   *another digit*", which correctly rejects "20" as a prefix of "2006"
   while still allowing "14th" to match.

3. As a related fix (bug, not the reported one, but found while fixing
   this): **every date pattern now requires a year.** "March 14" alone used
   to be accepted as a complete date-of-birth capture, which is wrong — a
   DOB missing its year is incomplete, not valid.

### Storing it as canonical DD-MM-YYYY, regardless of input format

Separately from the truncation bug, `normalize_to_ddmmyyyy()` is the single
place that turns whatever format/language the customer said the date in
into one consistent stored format:

```python
normalize_to_ddmmyyyy("14/03/1990")          -> "14-03-1990"
normalize_to_ddmmyyyy("1990-03-14")          -> "14-03-1990"
normalize_to_ddmmyyyy("14th of March 1990")  -> "14-03-1990"
normalize_to_ddmmyyyy("first january 2006")  -> "01-01-2006"
normalize_to_ddmmyyyy("31st of February 1990") -> None   # impossible date, fails closed
```

It validates the result through `datetime.date(year, month, day)`, so an
impossible date (31 Feb) is rejected rather than silently stored as
garbage. `validation.py`'s `date` field type calls this and *only* this —
there used to be a second, separate copy of the date-pattern list inside
`llm_client.py`'s extractor, which is exactly the kind of duplication that
lets extraction accept a value validation then rejects; that duplicate is
gone now, `date_parsing.py` is the one source of truth both sides call.

**What this fix does *not* claim to solve:** if the STT engine itself
mis-hears "2026" as "2006" — a genuine audio transcription error — nothing
in this codebase can correct that; the fix guarantees that *whatever* the
STT engine hears gets stored completely and correctly, not truncated into
an even-more-wrong fragment. The reconfirm-before-lock flow from §7 is the
actual safety net for the mishearing itself — the customer now gets to
catch and correct "I heard '01-01-2006' — is that correct?" before it's
ever submitted.

---

## 9. Guardrails — deterministic, not model-dependent

`backend/app/guardrails/` — each one is a plain-Python function, not an LLM
call, precisely because these must never depend on model judgment:

- `consent.py` — builds the opening disclosure line, detects a consent
  decline.
- `payment.py` — regex for card numbers / payment-detail phrases; checked
  on the **raw** utterance before redaction, so it can't be missed.
- `refusal.py` — hard refusal ("don't call me again") vs. a soft "busy,
  call back later" deferral.
- `advice.py` — detects a request for personalized financial/plan advice
  (must be redirected, never answered — the agent isn't a licensed
  advisor).
- `dnc.py` — Do-Not-Call registry check, gates call placement itself (no
  session or call is even created for a DNC-listed number), and gets
  written to on a hard refusal so the *next* recovery attempt also respects
  it.

`app/utils/redaction.py` strips anything that looks like a card number out
of the stored transcript (`REDACTED`) — the raw digits are never persisted,
even though the guardrail already escalated on seeing them.

---

## 10. Frontend voice pipeline

`frontend/src/useVoice.ts` wraps the browser's native Speech API:

- **STT**: `SpeechRecognition`/`webkitSpeechRecognition`, language set via
  `recognition.lang = bcp47` from the selected language. Interim results are
  shown live in the input box; only the final transcript is sent to
  `/voice/message`.
- **TTS**: `SpeechSynthesisUtterance`, with a **cached voice per language**
  (`voiceCacheRef`) — the same `SpeechSynthesisVoice` object is picked once
  and reused for the whole session, rather than re-resolved (and potentially
  drifting to a different voice) on every single line. A best-effort
  name-based preference list (`VOICE_NAME_PREFERENCE`) picks a female voice
  per language to match the scripts' consistent grammatical gender, falling
  back deterministically to the first available voice for that language if
  no name match is found.
- **Cut (barge-in)**: `cutOff()` calls `window.speechSynthesis.cancel()`
  immediately. The button (`Console.tsx`) is now rendered for the entire
  duration of the call, not only while the agent happens to be mid-sentence
  — it's simply disabled (greyed out) when there's nothing playing, rather
  than disappearing from the layout. Clicking the mic to speak also
  implicitly barges in and cancels any in-progress TTS.
- Degrades to text-only input automatically in browsers without
  `SpeechRecognition` support (Firefox, Safari) — `voice.supported` gates
  whether the mic button even renders.

---

## 11. Everything else that's wired in

- **Escalation → handoff packet** (`app/services/handoff.py`): every
  escalation builds a structured packet (category, reason, confidence,
  evidence, everything collected so far, an LLM-or-fallback summary) with a
  `handoff_id`, retrievable via `GET /handoff/{id}` — what a human agent
  would actually see when the call is transferred to them.
- **Network-drop callback** (`/voice/simulate-drop`, `/voice/redial`):
  models what a Vapi "call ended, reason=network" webhook would trigger in
  production. A dropped call's collected fields are carried into the redial
  exactly like a resumed web-journey prefill; after `MAX_CALLBACK_ATTEMPTS`
  (3) it escalates straight to a human instead of auto-redialling forever.
- **Call records** (`app/services/call_records.py`, SQLite): written once a
  call reaches any terminal state, including whether the customer
  explicitly reconfirmed the final read-back (`customer_reconfirmed`,
  distinct from just reaching COMPLETED) — queryable via `/call-records`.
- **Metrics / efficiency report** (`app/evaluation/`): scriptable offline
  report over recorded calls, runs against the rule-based LLM client so it
  never needs a live API key either.

---

## 12. Follow-up spec additions (call-end taxonomy, RBAC, recordings, multi-call-per-lead)

A later round of work added a formal taxonomy for how a call ends, durable
event logging, minimal role-based access control, call-recording storage,
and per-lead call history. Summarized here; see the code comments in each
file for the reasoning behind specific choices.

**`CallEndReason`** (`app/models/journey.py`) — an exhaustive enum
(`completed`, `escalated`, `hard_refusal`, `soft_deferral`,
`abrupt_disconnect`, `silence_timeout`, `provider_error`) set on every
`JourneyState` the moment a call reaches a terminal status, so "why did
this call end" never has to be re-derived by guessing from
`journey_status` + transcript. A consent decline and a "confirmation
declined" both map to `soft_deferral` (no DNC write-back either way,
matching a busy deferral); `abrupt_disconnect` and `silence_timeout` both
reuse `JourneyStatus.DROPPED_NETWORK`'s existing redial machinery — only
`end_reason` distinguishes them, since both are "the call didn't end
because the customer chose to end it."

**`call_events`** (SQLite, `app/services/call_records.py`) — an
append-only trail, one row per significant moment (call started, escalation
triggered, disconnect detected, reconnect attempted, call ended, recording
accessed), queryable by `lead_id` as well as `session_id`. Written via
FastAPI `BackgroundTasks` so a log write never adds latency to a live turn.
This is what survives a mid-call crash that the single terminal
`call_records` row doesn't — the in-memory `session_store` itself is still
not crash-durable (a live mid-call turn is lost on a restart either way);
`call_events` gives a partial trail of what happened up to the crash, not a
way to resume from it.

**Reconnect vs. redial** — `/voice/reconnect` and `/voice/redial` share one
implementation (`_resume_dropped_session` in `app/api/voice.py`): same
prefill-from-prior-call logic, same `MAX_CALLBACK_ATTEMPTS` cap either way.
`/voice/reconnect` is the immediate, human-in-the-loop path — Console shows
a "The call dropped unexpectedly — reconnect now?" popup the instant
`end_reason == abrupt_disconnect`, never for any other end reason (a hard
refusal must never prompt a reconnect). `/voice/redial` is the same action
triggered later from the Callbacks page. Neither can bypass the attempt cap.

**RBAC** (`app/auth.py`) — a hardcoded set of demo users with a role each
(`Agent` / `Team Lead` / `Admin`), read from an `X-Demo-Token` header via a
FastAPI dependency; no identity provider integration, by design, for
hackathon scope. Scoped by **resource type**, not per-call ownership: this
build's calls are all placed autonomously by the AI orchestrator, so there
is no per-agent call assignment anywhere in the data model to scope
against. Any authenticated user can view transcripts (`call_records`);
Team Lead and above can also view recordings (`call_recordings`); every
recording access is itself logged as a `call_events` row. The frontend's
sidebar has a "Viewing as" role switcher (persisted in `localStorage`,
purely a per-viewer demo convenience) that sets this header on every
request.

**`call_recordings`** — a reference-URL table (never a downloaded/re-hosted
audio file), written best-effort from the Vapi webhook when an
`artifactPlan.recordingEnabled` call's end-of-call report includes a
recording URL, and only when `consent_status == GRANTED`. The exact field
path (`call.artifact.recording` per Vapi's docs as of this build) is
UNVERIFIED against a live payload — different Vapi doc pages describe this
slightly differently, and a Custom-LLM chat-completion turn (what
`/vapi/webhook` mainly handles) isn't necessarily the same webhook message
as an end-of-call report. The capture is wrapped so a shape mismatch can
only mean a recording silently isn't captured, never that the call breaks.

**Multi-call-per-lead** — `call_records` was never `UNIQUE` on `lead_id`
(only `session_id`), so a lead having multiple call attempts was already
structurally supported; what was missing was a way to query and see them
together (`GET /leads/{lead_id}/call-records`, `GET
/leads/{lead_id}/call-events`) and a way to explicitly close a lead out
(`POST /leads/{lead_id}/terminate`, backed by a `closed_leads` table,
gating `/voice/session` the same way the DNC registry does). Console's
post-call outcome card offers "📞 Call again" (hidden after a hard refusal)
and "🛑 Terminate — no more attempts" side by side.

**Audit of other regex extractors (§0.3 of the follow-up spec)** — the
date parser's "first-match instead of best-match" bug class was checked
against the other two regex-based extractors: `postcode_au` (`.search()`
→ `.findall()`, keep the LAST match — an AU address's postcode is always
the last 4-digit run, not the first one that happens to appear) and `enum`
(pick whichever valid option was mentioned LAST in the raw utterance, not
the first one listed in the script — "not really residential, more like
business" must resolve to `business`). `email` was checked and found not
vulnerable (a single greedy pattern, no multi-pattern list to pick the
wrong one from).

**Confidence semantics parity (§0.4)** — `FieldExtraction.confidence`,
`Intent.confidence`, and `EscalationDecision.confidence` are now bounded to
`[0, 1]` at the Pydantic schema level (`app/schemas/extraction.py`), so an
out-of-range value from either `LLMClient` implementation can't silently
break the `< 0.5` escalation threshold. What this does NOT confirm: whether
`RuleBasedLLMClient`'s hand-picked constants (0.4–0.9) and a live Claude
call's self-reported confidence behave comparably in *distribution* for
equivalent inputs — that needs an empirical check against a live API key
(run both clients over the same evaluation transcripts and compare), which
this offline-only build environment cannot do.

## 13. Generic-question handling and the vague-answer guardrail

Two related, adversarial-testing-driven additions:

**Generic questions** ("who are you", "is this a scam", "how long will
this take") get their own intent category (`generic_question` in
`INTENT_KEYWORDS`, `app/services/llm_client.py`) — a brief, honest
acknowledgement (`generic_question_ack` phrase) followed by a return to
whatever was already being asked, costing no retry. Previously these fell
through to the normal capture-failure ladder, which either wasted a retry
or (worse) got misread as an attempt to answer the pending field. "Trained"
against a synthetic corpus (`data/synthetic/generic_questions.json`,
verified in `backend/tests/test_generic_question_handling.py`) — for a
deterministic, substring-matching classifier, "training" honestly means
exactly this: a labeled corpus the keyword list is checked and expanded
against, not gradient descent. Coverage is a regression-tested fact, not a
vibe, and the corpus/keyword-list pair is meant to grow together whenever a
new real-world phrasing is found to be missed.

**Vague-answer guardrail** — a free-text (`non_empty`) field used to accept
*any* non-blank string, including a bare "yes"/"ok"/"sure" said in
response to "what's your address?" — which got stored as the literal
address. `FieldValidation` gained `min_length` (default 3) and
`reject_generic_filler` (default `True`); `validate_field_value`
(`app/services/validation.py`) now rejects an answer that's an exact match
(never a substring — "123 Yes Street" is untouched) against a
multi-language `GENERIC_FILLER_PHRASES` set. A rejected answer flows
through the same capture-failure/retry ladder as any other invalid value,
not a special case.

## 14. Real login, off-topic deviation handling, and simulated recordings

Three more fixes/additions from live testing after §12–13 shipped:

**Real login, not just a role switcher** — `app/api/auth.py` adds
`POST /auth/login` (username + password against `DEMO_CREDENTIALS`, returns
the matching demo token) and `GET /auth/me`. The frontend gates every route
behind `RequireAuth` (`App.tsx`) — a session starts logged OUT, no silent
default persona — and `Login.tsx` offers both a real-feeling username/
password form and one-click demo shortcuts for the three seeded accounts
(Alex Kim/Agent, Priya Nair/Team Lead, Sam Torres/Admin — a genuine, named
Agent login was the specific gap flagged). The old sidebar "Viewing as"
dropdown is gone; the sidebar now shows who's actually logged in plus a
Log out action.

**Off-topic chatter was being silently accepted as the answer.** The
vague-filler guardrail from §13 only rejected an exact short phrase ("yes",
"ok") — a longer rambling sentence ("I saw a really cute dog outside
today") sailed straight through and got stored as the literal `full_name`,
which meant the capture-failure retry ladder never even engaged for
genuine off-topic chatter. Fixed with `OFF_TOPIC_CHATTER_MARKERS` in
`app/services/validation.py` — substring markers (unlike the exact-match
filler check) for phrasing that's essentially never part of a genuine
name/address/date/provider answer. Deliberately conservative: an earlier,
broader version of this list (matching on things like "I think" and "by
the way") was tried and reverted after it broke two genuine scenarios — a
hedged real answer ("I think it's AGL, not totally sure") and a legitimate
multi-field aside ("Jordan Lee, and by the way this is a residential
place"). A false positive here (wrongly rejecting a real answer) is worse
than a false negative (an occasional off-topic remark getting through,
which the existing retry ladder still catches on repetition) — see
`docs/ARCHITECTURE.md`'s own §7 reconfirm-before-lock reasoning for the
same asymmetry applied elsewhere.

Once off-topic content is correctly rejected, "give it two tries, then
escalate" falls out of the **existing**, already-tested per-field retry
ladder for free: attempt 1 gets the warm soft-redirect
(`capture_soft_redirect_template`), attempt 2 gets the fallback offer
(`capture_fallback_offer`, now explicitly naming the call's purpose — "this
call is specifically to finish your energy comparison"), attempt 3
escalates as `CONFUSION_REPEATED_FAILURE`. A parallel cross-field
`off_script_count` escalation path was prototyped and then removed — for
this script's field configuration (every required field's own
`max_retries` is 2), it turned out to be mathematically unreachable, since
a single field's own exhaustion always resolves at the same or an earlier
turn. Kept simple rather than shipping dead code.

**Recordings weren't appearing** because nothing in this offline build ever
produces one — there's no live Vapi telephony account, so the webhook path
that would capture a real recording URL is simply never exercised (this
was already flagged as unverified in §12, but the practical effect —
"recording UI always empty" — wasn't obvious until tested live). Added
`POST /call-records/{session_id}/simulate-recording` (Team Lead+, requires
granted consent, same as the real path) generating a placeholder
`https://demo-recordings.invalid/...` reference — the same "demo
affordance for an otherwise-unreachable path" pattern as
`/voice/simulate-drop`. This proves storage, RBAC-gated retrieval, and
access-logging all work end to end without needing a real phone call;
History's Recording panel makes clear the URL isn't a real playable file.

## 15. What's mocked vs. real, and how to flip it

| Component | Default (demo) | Real |
|---|---|---|
| LLM | `RuleBasedLLMClient` (no key needed) | Set `LLM_API_KEY` → `AnthropicLLMClient`, model from `LLM_MODEL` (`claude-sonnet-5` by default) |
| Phone calls | `MockVoiceProvider` (fake call IDs, all endpoints no-op) | Set `VOICE_PROVIDER=vapi` + `VAPI_API_KEY`/`VAPI_PHONE_NUMBER_ID`/`VAPI_ASSISTANT_ID` |
| Human transfer target | not configured — transfer is skipped | `HUMAN_TRANSFER_DESTINATION` (phone number or SIP URI) |

Every test in `backend/tests/` (152 tests, all currently passing) runs
entirely against the mock/rule-based path — no network calls, no API keys
required to verify the whole system end-to-end.

## 16. UI re-skin — "Kinetic Obsidian"

The console was fully re-skinned to a dark, glass-card visual language
(provided as a set of static Tailwind-CDN HTML mockups covering every page:
intro, landing, console, callbacks, handoffs, history, analytics,
guardrails). The re-skin is visual only — every page keeps the exact
state/data logic it had before; no fabricated metrics or features from the
mockups (e.g. invented checksum/audit-hash language, made-up cost-per-lead
figures) were carried in, since none of it corresponds to anything the
backend actually computes.

**Infrastructure** — Tailwind CSS v3 installed as a real dependency
(`tailwindcss`, `postcss`, `autoprefixer`; NOT the CDN `<script>` tag the
mockups used, which isn't appropriate for a production build).
`tailwind.config.js` defines the mockups' color tokens (`primary-container`,
`background`, `surface`, `tertiary`, etc.) and custom keyframe animations
(`orb-1`/`orb-2` ambient glows, `eq-bounce` waveform, `sonar` pulse).
`frontend/src/kinetic.css` replaces the old `frontend/src/styles.css`
(deleted — no longer referenced anywhere) and pulls in Google Fonts (Inter,
Space Mono) and the Material Symbols Outlined icon font, replacing the
emoji/unicode glyphs used previously.

**Pages rewritten:** `Layout.tsx`, `Login.tsx`, `Waveform.tsx`,
`Intro.tsx`, and every route page (`Console.tsx`, `Landing.tsx`,
`Callbacks.tsx`, `Handoffs.tsx`, `History.tsx`, `Analytics.tsx`,
`Guardrails.tsx`). All state, handlers, API calls, and the two
previously-fixed bugs (`History.tsx`'s `err instanceof Error` message
pattern and its stale-request `cancelled` guard) were preserved verbatim —
only JSX/markup and class names changed. `Guardrails.tsx`'s card list grew
from 6 to 9 entries to also document the reconfirm-before-lock loop (§7),
the off-topic/vague-answer rejection (§13–14), and recording RBAC (§12) —
all real, already-shipped behavior, not new claims.

Verified via a full live click-through in the browser (login, a real
Console call, History with a real simulated recording, live Analytics
numbers, all 9 Guardrails cards) with zero console errors, and a clean
production build (`npm run build`: `tsc -b && vite build`, 458 modules,
0 TypeScript errors).
