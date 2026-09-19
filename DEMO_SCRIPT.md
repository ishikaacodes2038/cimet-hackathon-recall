# Demo Script

Target: 3–5 minutes, live, narrated. Every line below has actually been run through the API during development (see `tests/test_conversation_scenarios.py` for the exact automated versions of scenes 1–4).

**Before judges arrive:** `docker compose up --build` (or run backend + frontend manually per the README), open the console at `http://localhost:5173`, confirm `/health` is green.

## Scene 1 — Show the dropped lead

Open the console. Select `LEAD-1001` from the dropdown. Narrate: "This is a synthetic Energy lead that abandoned the comparison journey yesterday, after already giving us their name."

## Scene 2 — AI initiates recovery, with consent first

Click **Start recovery call**. The opener fires: *"Hi Priya, this is CIMET calling about the energy comparison you started on yesterday. This call is recorded for quality and training purposes. Are you okay for me to continue?"*

Narrate: consent is disclosed **before anything else happens** — this is a deterministic gate in the state machine, not something the LLM can skip.

## Scene 3 — Natural answers, including one that volunteers ahead of being asked

Type: `Yes that's fine` → agent asks for date of birth.
Type: `14th of March 1990` → agent asks for address.
Continue through address / property type / provider / fuel type.

Narrate while typing: "Notice `full_name` was never asked — it was already on file from the dropped web journey."

## Scene 4 — Structured extraction and journey completion

Keep answering (declining the optional meter number is a good beat — narrate that it gets *skipped*, not looped on, and the call keeps moving). At confirmation, type `yes go ahead`.

The right-hand panel shows every collected field with its confidence and the exact customer words it came from. The agent responds with a real submission reference number. Narrate: "That's a real payload, validated against the script's required fields and written to `data/submissions.jsonl` — not a canned success message."

## Scene 5 — Second call: explicit request for a human

Start a new session (`LEAD-1004`). Answer consent, then type: `Actually can I just speak to a real person please`.

The agent stops immediately — no further questions — and shows the 🔴 **HUMAN HANDOFF** banner. Open the handoff card: reason (`CUSTOMER_REQUEST`), everything collected so far, what's still missing, the last thing the customer said, and a generated summary. Narrate: "A human picking this up doesn't need the customer to repeat anything."

## Scene 6 — Guardrail: payment boundary

Start another session. After consent, type: `Can I just give you my card number, it's 4111 1111 1111 1111`.

The agent refuses to collect it and escalates immediately (`SENSITIVE_PAYMENT`). Narrate: check the transcript panel — the card number itself is redacted (`[REDACTED CARD NUMBER]`), never stored in the clear.

## Scene 7 — Guardrail: anger, and refusal handled with no pressure

Two quick beats:
- Type `I've already told you three times, this is ridiculous!!` → escalates as `ANGER_FRUSTRATION`.
- New session, type `not interested, please stop calling me` → call ends respectfully, no handoff needed, no further questions asked — journey status `ENDED_BY_CUSTOMER`.

## Scene 8 — Measurable efficiency

Open `docs/EFFICIENCY_REPORT.md`. Narrate the honest numbers: happy path completes in 13 turns with 11 fields captured and zero human typing; one interruption-style turn captured 3 fields at once; the escalation-heavy scenario set (deliberately adversarial) shows every dangerous case routing correctly to a human.

## Scene 9 — What's deterministic vs. what's the LLM

Close on the architecture diagram in the README: the LLM only ever proposes (a field value, an intent, an escalation signal) — consent, DNC, the payment boundary, retry limits, and submission are all plain Python. This is why the same 25-test suite passes whether or not a live LLM key is configured — the system was built and hardened against the zero-dependency rule-based fallback first.

## If something breaks live

Every scene above works purely through the mock/text voice interface — there is no live-call dependency to fail. If a live Vapi call is being attempted as a stretch goal and it misbehaves, fall back to the console's text input: it is driving the *exact same* orchestrator code, not a simplified demo path.
