# Recall — CIMET Energy Voice Agent

AI voice agent ("**Recall**") that recovers a dropped-off Energy comparison journey over a phone call — resumes from the customer's last completed step, asks only for what's missing, extracts and validates structured data as the conversation happens, completes and submits the journey, and hands off to a human the moment it should, with full context.

Built for the CIMET / econnex 12-hour solo engineering hackathon (Jaipur). See `REQUIREMENTS_MATRIX.md` for the requirement-by-requirement traceability and `docs/EFFICIENCY_REPORT.md` for measured efficiency numbers.

## 1. Problem

CIMET's Energy comparison journey is a multi-step form. Customers who abandon it mid-way become dropped-off leads, currently recovered by a human agent who reads a script and manually types every answer into the journey, one call at a time. This project builds the **Agent-Driven** alternative: an AI that runs that call itself, and knows precisely when it shouldn't.

## 2. Why it matters

Recovery calls are the difference between a dropped lead and completed revenue. A human-only process caps how many can be attempted; an autonomous agent that reliably knows its own limits — consent, payment boundaries, anger, confusion, explicit requests for a human — can scale recovery without scaling risk.

## 3. Solution

A conversation orchestrator drives a deterministic state machine through a script-defined set of Energy fields, using an LLM only for narrow, structured tasks (intent classification, field extraction, escalation signal), never for control flow. The LLM cannot mutate journey state directly — every proposal it makes is validated and applied by plain Python before it affects anything.

## 4. Architecture

```
Voice layer (Vapi adapter, or the mock text-loop everything below was built and tested against)
        -> Conversation Orchestrator (FastAPI, app/agents/orchestrator.py)
        -> Journey State Machine (deterministic, Pydantic — app/state/machine.py)
        -> LLM (Claude tool-calling, or a zero-dependency rule-based fallback — app/services/llm_client.py)
              - field extraction   - intent classification   - escalation signal   - summarisation
        -> Validation Layer (deterministic — app/services/validation.py)
        -> Journey Sandbox (submit, app/services/journey_sandbox.py)
        -> Escalation Engine (deterministic-first — app/services/escalation.py) -> Warm Handoff -> Ops Console
```

**Key principle:** the LLM never mutates application state directly. It returns typed, evidence-backed proposals (a field value + confidence + the exact customer words it came from, an intent label, an escalation signal); deterministic code decides what happens next. Consent, DNC, the payment boundary, and escalation routing are all plain Python — not model judgment.

## 5. Technology choices

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + Pydantic v2 | Typed, fast to build, matches the state-machine-first architecture |
| LLM | Claude (Anthropic), tool-calling for structured output | Typed extraction/intent/escalation schemas instead of parsing free text |
| LLM fallback | A deterministic rule-based client (regex/keyword) | The system must be demoable and testable with zero external dependency — see §6 |
| Voice | Vapi adapter behind a `VoiceProvider` interface, swappable | Bundles telephony + STT + TTS + turn-taking + call transfer, which de-risks a solo 12-hour build versus hand-rolling Twilio + STT + TTS separately |
| Frontend | React + TypeScript + Vite | Minimal ops console — transcript, collected fields, escalation, handoff |
| Storage | In-memory session store + a local JSONL submission log | A 12-hour build has no business standing up Postgres for ephemeral call sessions |

## 6. AI/LLM architecture

Two interchangeable `LLMClient` implementations (`app/services/llm_client.py`):

- **`AnthropicLLMClient`** — real Claude tool-calls for extraction, intent, and summarisation, with every call wrapped so a timeout or malformed response falls back to the rule-based client rather than breaking the call.
- **`RuleBasedLLMClient`** — a zero-dependency fallback (regex/keyword-driven) used automatically whenever no `LLM_API_KEY` is configured. **This is what the entire test suite and the adversarial testing below run against** — the core orchestration logic was built and hardened against this before any live LLM call was ever needed, per the brief's own rule: "If an external dependency isn't available, create a clean mock interface so development can continue."

Five narrow, separated concerns — never one giant prompt:
1. Field extraction (`extract_fields`) — evidence-backed, per-field confidence
2. Intent classification (`classify_intent`)
3. Escalation signal (`detect_escalation_signal`) — a *signal*, not the decision; see §8
4. Response generation — the script's own question/clarification text is always the source of truth; nothing is invented outside it
5. Conversation summarisation (`summarize`) — used to build the warm-handoff packet

## 7. State machine

`app/state/machine.py` (`JourneyStateMachine`) owns: current step, completed steps, required vs. collected fields, retry counts, consent status, DNC status, journey status, submission status. Fields already present from the dropped-off web journey (e.g. name, address) are loaded at `LOAD_EXISTING_DATA` and never re-asked. Steps: `START → CONSENT → LOAD_EXISTING_DATA → IDENTITY → PROPERTY → ENERGY_USAGE → SAFETY_CONCESSION → PREFERENCES → CONFIRMATION → SUBMISSION → COMPLETED` (or `ESCALATED` / `ENDED` at any point). The Energy field list itself lives in `scripts/energy/recovery.yaml` — swapping in the real on-site field list is a data change, not a code change.

## 8. Escalation design

`app/services/escalation.py` combines hard deterministic rules (explicit human request, payment mention, a safety-critical field value like life-support, retry exhaustion) with one LLM-assisted signal (anger/frustration sentiment) — and the hard rules always take precedence. Seven categories: `CUSTOMER_REQUEST`, `ANGER_FRUSTRATION`, `CONFUSION_REPEATED_FAILURE`, `OFF_SCRIPT`, `SENSITIVE_PAYMENT`, `LOW_CONFIDENCE`, `OTHER_SAFETY_BOUNDARY`. Every escalation produces a `HandoffPacket` (`app/services/handoff.py`) with the full transcript, completed/missing fields, last customer message, a summary, and a confidence score — a human never needs to make the customer repeat anything.

## 9. Guardrails

- **Consent first** — recording disclosure is delivered before any data is collected; a decline ends the call immediately, nothing is asked.
- **No card data by voice** — payment mentions (keywords or a card-number-shaped pattern) are intercepted before extraction even runs, escalated immediately, and redacted from every transcript/log (`app/utils/redaction.py`).
- **No advice** — product/financial-advice requests get a guardrail refusal and a redirect back to the script; a second request escalates.
- **DNC-aware** — `app/guardrails/dnc.py` gates `/voice/session` before any session/call is created at all for a listed number.
- **Respect "no"** — a hard refusal or a "busy" deferral ends the call respectfully, logs the outcome, and never loops or re-asks.

## 10. API

`GET /health` · `GET /leads/{lead_id}` · `GET /journeys/{lead_id}` · `POST /voice/session` · `POST /voice/message` · `POST /journey/validate` · `POST /journey/submit` · `POST /escalation/evaluate` · `POST /handoff` · `GET /handoff/{id}` · `POST /vapi/webhook` (Custom-LLM adapter for live Vapi calls).

## 11. Setup

### Prerequisites
- Python 3.9+ (tested on 3.9.7)
- Node 18+ for the frontend (Node was installed and `npm install && npm run build` verified clean — zero TypeScript errors, 458 modules — plus a live click-through of the running dev server)
- Docker + Docker Compose (optional)

### Environment variables

```bash
cp .env.example .env
```

An empty `.env` is fine — the system runs on the rule-based LLM fallback and the mock voice provider with zero external dependencies.

### Backend — run locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/health`.

> **Windows note:** on some machines, `venv`/`virtualenv` fails with `Unable to create process using '...python.exe ...'` (a launcher-stub bug unrelated to this project). Workaround — skip the venv:
> ```bash
> python -m pip install --user -r requirements.txt
> python -m uvicorn app.main:app --reload
> ```

### Frontend — run locally

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Visit `http://localhost:5173`. Requires the backend running on `http://localhost:8000` (or set `VITE_API_BASE`).

### Run with Docker (backend)

```bash
docker compose up --build
```

## 12. Running tests

```bash
cd backend
pytest -v
```

152 tests: state-machine unit tests + a full end-to-end scenario suite (`tests/test_conversation_scenarios.py`) driven through the real HTTP API, covering the happy path plus messy-conversation and guardrail scenarios, auth, off-topic deviation handling, reconfirmation, date parsing, and more — including permanent regressions for every bug found during adversarial testing (see §17).

## 13. Demo instructions

See `DEMO_SCRIPT.md`.

**Vapi is the real demo path, not the browser console.** The Console page's
text/mic UI (Web Speech API) is a dev/test harness only — it never places an
actual phone call. The judged call must go through `VOICE_PROVIDER=vapi`
(README §16), which dials a real number and drives the conversation via
`POST /vapi/webhook`.

**Fallback if Vapi fails on demo day:** if the live call can't be placed or
drops mid-demo (network at venue, Vapi outage, a misconfigured webhook URL),
fall back immediately to the Console's browser-mic path with `voiceMode` on
(the "Speak agent replies aloud" checkbox) — it exercises the exact same
orchestrator/state-machine/escalation logic the phone call does, just with
the browser as the mic/speaker instead of a real phone line, so nothing
about the actual agent behavior being judged is different. Say this
explicitly to the judges rather than silently switching: "the phone
network's not cooperating, so I'll drive the same agent through the browser
mic instead — same code path end to end." Do not attempt to debug Vapi
live in front of judges; switch immediately and debug afterward.

## 14. Business impact

See `docs/EFFICIENCY_REPORT.md` — generated by actually running scenarios through the live app, not hand-typed. Headline, measured figures: the happy-path journey completes autonomously in 13 customer turns with 11/12 fields captured and zero human typing; a single volunteered utterance ("Jordan Lee, and by the way this is residential, mostly electricity") captures 3 fields in one turn instead of three separate round-trips; one field (`full_name`) is never asked at all because it's reused from the dropped web journey.

## 15. Environment variables reference

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` / `production` |
| `LOG_LEVEL` | Python logging level |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | LLM configuration — no key is hardcoded anywhere; empty key = rule-based fallback |
| `VOICE_PROVIDER` | `mock` (local text-loop, no vendor) or `vapi` (real calls) |
| `VAPI_API_KEY`, `VAPI_PHONE_NUMBER_ID`, `VAPI_ASSISTANT_ID` | Only required when `VOICE_PROVIDER=vapi` |
| `PUBLIC_BASE_URL` | Publicly reachable URL for this backend (ngrok in dev) so Vapi can call back into it |
| `VITE_API_BASE` (frontend) | Backend URL the console talks to |

## 16. Limitations

- **Vapi integration: wired end-to-end, but not against a live account.** An earlier version of this code had the provider class and webhook built but never actually connected — `POST /voice/session` never called `start_call()`, so no real call could ever have been placed even with valid credentials. That gap is now fixed: `/voice/session` places the call via `VapiVoiceProvider.start_call()` when `VOICE_PROVIDER=vapi`, surfaces a placement failure instead of pretending the call succeeded, and `/voice/message` drives `end_call`/`transfer_call` on escalation or completion. `tests/test_vapi_provider.py` verifies all of this against a mocked HTTP transport (request shape, response parsing, failure handling, the webhook→session→orchestrator path) — 7 passing tests. What that *can't* prove: whether Vapi's real API actually matches the request/response envelope assumed here. That needs 10 minutes against a live account before the demo — see the on-site checklist below.

  **On-site verification checklist (needs a real Vapi account):**
  1. Set `VAPI_API_KEY`, `VAPI_ASSISTANT_ID`, `VAPI_PHONE_NUMBER_ID` in `.env`, set `VOICE_PROVIDER=vapi`.
  2. Configure the Vapi Assistant's Custom LLM server URL to `<your ngrok URL>/vapi/webhook`.
  3. `POST /voice/session` with a real test number and confirm a call actually rings and `call_id` comes back non-null.
  4. Confirm Vapi's webhook POST body actually matches `VapiWebhookRequest` (`messages: [{role, content}]`, `call.metadata.session_id`) — adjust `app/api/vapi_webhook.py` if the real shape differs; that's the only file that should need to change.
  5. Trigger an escalation live and confirm `transfer_call` actually moves the call (needs `HUMAN_TRANSFER_DESTINATION` set).
- **Real voice input is browser mic only, not telephony.** The console can now listen (Web Speech API `SpeechRecognition`) and speak (`speechSynthesis`) for a genuine spoken conversation with the agent — zero vendor account needed — but this is a browser microphone, not an actual phone call. Chrome/Edge only; the console degrades to text input automatically elsewhere. A real inbound/outbound phone call still requires the Vapi path (§16 above).
- **Rule-based LLM fallback is intentionally simple** — free-text fields (name, address) are captured near-verbatim rather than parsed into structured sub-fields; a real Claude call would do meaningfully better extraction. The fallback exists so the system is fully testable/demoable with zero external dependency, not as the primary intended runtime.
- **Confirmation-step corrections are routed to a human**, not resolved automatically — if a customer wants to change a previously given answer at the confirmation step, the system escalates rather than guessing which field to amend. A deliberate scope cut, not an oversight.
- **Energy field list is a dummy** (cross-referenced against the field names used in CIMET's own companion QA-Automation brief) — the real on-site field list needs to replace `scripts/energy/recovery.yaml`.

## 17. Bugs found and fixed during adversarial (hostile-judge) testing

1. **Infinite loop on optional fields.** Optional fields (e.g. the NMI/MIRN meter number) were asked but structurally excluded from extraction, so they could never be captured *or* escalated — the call got stuck repeating the same clarification forever. Fixed by including the currently-asked field in the extraction target list regardless of required status, and by adding a distinct "skip after max retries" path for optional fields (escalation is reserved for *required* fields).
2. **Optional fields after the last required field were silently skipped.** The "ready for confirmation" check only looked at required fields, so the moment the last required field was collected, the agent jumped straight to confirmation — permanently skipping any optional field ordered after it in the script, and then misinterpreting the customer's answer to a question that was never asked as a confused response to the confirmation prompt, triggering a wrong escalation. Fixed by making a single function the sole decision point for "ask next field vs. confirm."
3. **LOW_CONFIDENCE escalation was unreachable offline.** The rule-based extractor only ever emitted confident matches or nothing, so the LOW_CONFIDENCE escalation category — one of the six required by the brief — could never actually fire in offline/fallback mode (exactly the mode a live-API outage would fall back to mid-demo). Fixed by detecting hedging language ("I think," "not totally sure") and emitting a deliberately low-confidence capture that routes to a human for confirmation.

4a. **Every orchestrator-owned line was hardcoded English, leaking into non-English calls.** Multi-language support only covered script-sourced text (consent line, field questions) — the confirmation question, submission success message, and every guardrail refusal (advice/payment/refusal/busy) were Python string literals, so a Hindi or Filipino call would say things like "Great, thank you. <Hindi question>" — English glued onto a translated sentence. Found by re-reading the orchestrator code against the real reference transcript (see `docs/reference-transcript-notes.md`), not by a test — prior tests only checked a substring was present in the target language, never that the *whole* line was. Fixed: every such line now lives in `scripts/energy/recovery.*.yaml` under a `phrases` block, one per language, with an English fallback (`PHRASE_DEFAULTS`) only for missing keys. Covered by two new regression tests asserting zero English leak.

4b. **Silent field carry-over gave the customer no audible confirmation.** The real reference transcript's agent explicitly reads back what's on file ("your address is X, correct?") before proceeding — our system silently loaded prefilled fields into state with zero verbal mention. Added a `resume_ack_with_prefill` phrase, spoken once after consent is granted, when there's anything to acknowledge — without adding an extra turn or asking to re-confirm each field individually (which would contradict the brief's own "ask only for missing information" instruction).

4c. **"Don't call me again" wasn't actually remembered.** A hard refusal correctly ended the current call, but never wrote back to the DNC registry — so a later recovery attempt for the same lead could dial them again, contradicting the brief's own guardrail. Found by cross-checking against an independently-designed sibling architecture that explicitly called this out. Fixed: `app/guardrails/dnc.py` is now a writable registry, and a hard refusal (not a "busy" deferral, not a consent decline — those are different signals) adds the lead's number to it via the API layer, which is what has the phone number.

All four are covered by permanent regression tests in `tests/test_conversation_scenarios.py`.

5. **A mis-heard field was trusted and stored on the first guess.** Reported live: the customer said "first January 2026," STT heard "first january 2006," and — separately — the truncation bug below turned that into "january 20." Even setting the truncation aside, nothing ever gave the customer a chance to catch and correct a mishear before it was submitted. Fixed with a reconfirm-before-lock loop: every field the agent is actively asking about is read back ("I heard 'X' — is that correct?") before `CollectedField.confirmed` is set; declining discards the value and re-asks through the same retry/fallback ladder as a normal capture failure. Deliberately scoped to only the actively-asked field — fields volunteered ahead of being asked, or carried over from a resumed journey, are not individually re-litigated. Covered by `tests/test_reconfirmation.py` (7 tests); see `docs/ARCHITECTURE.md` §7.

6. **A date missing its year, or a truncated fragment of one, could be stored as a "complete" date of birth.** Root cause and fix are detailed in full in `docs/ARCHITECTURE.md` §8 (this was the single most important bug fixed this phase, reported directly by live testing) — in short, `find_date_span()` used to return the *first* matching pattern instead of the *longest*, and an unbounded `\d{1,2}` happily matched a two-digit prefix of a four-digit year. Fixed by longest-match selection plus lookaround-bounded digit patterns, with every date now normalized to a canonical `DD-MM-YYYY` string regardless of the language/format spoken. Covered by `tests/test_date_parsing_and_fallback.py`, including a regression test that reproduces the exact reported utterance.

7. **`last_activity_date` was raw English prose, interpolated straight into a translated sentence.** The four seeded leads' `last_activity_date` values ("earlier today", "yesterday", etc.) were plain English strings formatted directly into the consent opener — so a Hindi call would say "...आपने **earlier today** को जो..." — English mid-sentence, the same bug class as 4a above but from lead data instead of script text, and the direct cause of what looked like the bot "switching languages" mid-Hindi-call. Fixed by treating `last_activity_date` as a canonical token (`TODAY`, `YESTERDAY`, `TWO_DAYS_AGO`, `MONDAY`, `LAST_CALLBACK_ATTEMPT`) resolved through each script's own `relative_date_labels`, never raw prose. Covered by two new regression tests in `tests/test_multilingual_and_callback.py`.

All seven are covered by permanent regression tests.

8. **A date answered piece by piece across turns was evaluated one piece at a time — and failed each time.** Reported live: "20 September 2005" spoken as one phrase only registered as "20 September," the agent correctly asked for the year, but answering with just "2005" (the missing piece, not the whole date again — the natural way anyone answers a follow-up question) was evaluated in isolation, found no day/month in that utterance, and counted as a second capture failure — landing on the fallback-offer/escalate ladder after only two perfectly reasonable answers. Root cause: `_handle_capture_failure` called `machine.record_retry()` unconditionally, even for a helpful partial answer, and nothing carried day/month/year pieces across turns. Fixed with `extract_date_components()`/`merge_date_components()` (`app/services/date_parsing.py`) plus a dedicated `_handle_date_field_failure` path that accumulates pieces per field and only reaches the retry ladder when a turn has nothing date-shaped in it at all. Covered by `tests/test_date_parsing_and_fallback.py` (6 new tests, including the exact reported case, spoken across up to three separate turns).

9. **There was no way to start a second call without reloading the page.** `sessionId` never reset once a call reached a terminal state, so the "Start recovery call" button stayed permanently stuck on "Call in progress." Fixed: a "🔄 Start another call" action now appears alongside every call outcome (completed/escalated/ended), resetting the console to a clean slate. Escalated calls also previously had no banner in the main transcript panel at all (only the side "Escalation" card) — added one for consistency with the other two terminal outcomes.

10. **A free-text field accepted anything, including "yes"/"ok"/"sure" as a literal answer.** Answering "what's your address?" with "yes" used to be stored as the address. Fixed with a guardrail on `non_empty` fields: exact-phrase (never substring) matching against a multi-language generic-filler set, plus a minimum length. See `docs/ARCHITECTURE.md` §13.

11. **Generic meta-questions about the call ("who are you", "is this a scam") had no home.** They either burned a retry as a failed capture attempt or got misread as an attempted answer. Fixed with a dedicated `generic_question` intent — a brief honest acknowledgement, then back to the pending question, no retry cost. "Trained" (in the only sense that means anything for a deterministic keyword classifier) against a synthetic labeled corpus — see `docs/ARCHITECTURE.md` §13.

12. **Follow-up spec: call-end taxonomy, RBAC, recordings, multi-call-per-lead, reconnect.** A separate, larger round of work — full detail in `docs/ARCHITECTURE.md` §12, including what's implemented vs. explicitly flagged as unverified (live Vapi recording payload shape, empirical confidence-distribution parity between the rule-based and Claude clients).

## 18. UI re-skin

The console was re-skinned to a dark "Kinetic Obsidian" glass-card visual
language (Tailwind CSS v3, Inter + Space Mono fonts, Material Symbols
icons) across every page — intro, landing, console, callbacks, handoffs,
history, analytics, guardrails. Visual only: every page kept its exact
existing state/data logic, and no fabricated metrics/features were carried
in from the source mockups. See `docs/ARCHITECTURE.md` §16.

## 19. Future improvements

- Swap the rule-based LLM client for live Claude calls once an API key is configured, and re-run the full scenario suite against it.
- Verify and harden the Vapi integration against a real account (call transfer semantics in particular need on-dashboard confirmation).
- Replace the in-memory session store with something durable if calls need to survive a backend restart.
- Console: live-poll or WebSocket the transcript instead of only updating on each `/voice/message` response, for a true "watch it happen live" demo feel.
