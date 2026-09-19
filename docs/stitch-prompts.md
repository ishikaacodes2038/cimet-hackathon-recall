# Google Stitch prompts — Recall

Run the **Design System** prompt first in a Stitch project, then each screen prompt in the same project so Stitch keeps visual continuity. Stitch produces static frames/HTML — treat its output as the *visual spec* to implement with real motion (framer-motion, as already done), not literal final animated code.

---

## 0. Design System (run first)

```
Design system for "Recall", a dark-themed AI voice agent product for an energy-plan
comparison company (CIMET). Mood: Linear.app x Arc Browser x OpenAI voice UI — premium,
minimal, confident, slightly futuristic, NOT corporate-generic.

Colors: near-black background (#0f1222), elevated panel surface (#161a30), border
(#2a2f4d), primary text off-white (#e8e9f3), muted text (#9095b8), single accent
color burnt-orange (#ff5a36), success green (#35d07f), warning amber (#f5b942),
error red (#ff5a5a). Accent used sparingly — CTAs, active states, key numbers only.

Typography: bold geometric sans-serif for headlines (weight 800, tight -0.02em
letter-spacing, large scale), regular weight for body at smaller size with generous
line-height. Numbers/stats in a slightly heavier weight than body text.

Shape language: 8-10px border radius on cards and buttons, 1px hairline borders in
the border color (not shadows) to separate surfaces, soft 20-30% opacity glow blurs
in the accent color used as ambient background decoration (never full-strength
color fills).

Iconography: minimal line icons or single Unicode-style glyphs, no skeuomorphism.

Component library to establish: primary button (filled accent, dark text), ghost
button (outline, transparent fill), stat card (large number + small label),
badge/pill (rounded-full, small caps label, tinted background matching status
color), sidebar navigation item with an animated active-state background pill.
```

---

## 1. Intro / Splash screen

```
Full-bleed splash screen for "Recall", center-aligned. A circular arrow/refresh
glyph mark (↻) in accent orange next to the wordmark "Recall" in bold white,
both scaled very large as if captured mid-zoom toward the viewer — motion-blur-free
but composed to suggest it is rushing forward out of the screen. Small tagline
below in muted gray: "Teach the phone to listen." Tiny "click to skip" label
pinned bottom-center in low-opacity muted text. Pure near-black background, no
other UI chrome visible — this is a pre-app moment, not a page.
```

---

## 2. Home / Landing page

```
SaaS marketing-style landing page for "Recall" using the established design system.
Two soft ambient glow blobs bleed in from top-left (orange) and bottom-right (blue,
#4d6fff) behind the content, both very blurred/diffused. Left-aligned hero: small
uppercase pill badge reading "CIMET / ECONNEX — 12-HOUR ENGINEERING HACKATHON",
below it a huge bold two-line headline "Teach the phone / to listen." with the
second line's last word "listen." in accent orange, below that a muted-gray
paragraph two sentences long, below that two buttons side by side — a filled
accent primary button "Open the console →" and an outline ghost button "View live
metrics". Below the buttons, a floating "product shot" card: a browser-chrome-style
panel (three small dots top-left) containing a mock chat transcript — one agent
message bubble left-aligned, one customer reply bubble right-aligned, and a row of
three small status pill badges below in green/amber/gray. This card should look
like it is floating with a soft drop shadow, at a very slight forward tilt as if
photographed at an angle. Below that, a row of three feature cards in a grid, each
with a bold short title and one sentence of muted body text.
```

---

## 3. Console — live call page

```
App interior page (persistent left sidebar with nav icons for Home, Console,
Callbacks, Handoffs, History, Analytics, Guardrails — Console item highlighted
active with a soft accent-tinted rounded background). Main content: page title
"Live recovery call" with a muted subtitle sentence, a toggle switch top-right
labeled "Speak agent replies aloud". Below: a two-column layout. Left column
(wider): a control row with a lead-selector dropdown, a language dropdown, and a
filled "Start recovery call" button; below that a chat transcript panel showing
alternating agent (left, dark-blue bubble) and customer (right, slightly lighter
bubble) messages, with a small italic system note bubble centered between some
of them; below the transcript, a horizontal audio waveform made of ~24 thin
vertical bars of varying heights in accent orange, implying live audio activity;
below that an input row with a circular microphone icon button (accent-filled),
a text input, a "Send" button, and — shown only conditionally — an outlined red
"✂ Cut" button. Right column (narrower): a "Collected data" panel listing field
rows each with a checkmark or hollow circle, a field name, a value, and a
percentage confidence badge; below it an "Escalation" status panel showing a
green "NORMAL" pill or, alternately, a red "HUMAN HANDOFF" banner state.
```

---

## 4. Callbacks page

```
Same app shell/sidebar (Callbacks item active). Page title "Pending callbacks"
with a muted explanatory subtitle about network-dropped calls being resumable.
Below: a vertical list of horizontal callback cards, each showing a lead ID in
bold, a muted meta line ("2 fields already captured · attempt 1 of 3"), and a
right-aligned filled button "↻ Redial now" with a subtle circular-arrow icon
suggesting rotation/retry. One card in the list shown in a disabled/grayed state
with its button reading "Escalate only" to represent the max-attempts-reached case.
Empty state variant: centered muted-gray text with a dashed-border illustration
placeholder suggesting "nothing here yet".
```

---

## 5. Handoffs page

```
Same app shell (Handoffs active). Page title "Warm handoffs" with subtitle about
escalated calls keeping full context. Below: a two-column layout — left column a
narrow vertical list of compact handoff row buttons (each showing a red-accented
escalation-reason label, a lead ID, and a timestamp, one row visually highlighted
as selected with an accent left-border), right column a larger detail panel
showing: a heading combining a red circle emoji-style dot with the escalation
reason and lead ID, a reason-detail sentence, a confidence percentage, a
multi-sentence AI-generated summary block, a quoted "last customer message" line,
completed/missing field lists, and below all of that a full scrollable transcript
in the same chat-bubble style as the Console page, slightly condensed.
```

---

## 6. History page

```
Same app shell (History active). Page title "Call history" with subtitle
mentioning durable storage. Layout mirrors the Handoffs page: left a scrollable
list of compact rows, each showing a status badge (colored pill: green
"COMPLETED", red "ESCALATED", gray "ENDED_BY_CUSTOMER", amber "DROPPED_NETWORK"),
a lead ID + language label, and a timestamp; right a detail panel showing the
selected call's status badge, language, consent status, a highlighted
"customer reconfirmed ✓" line, escalation reason if any, submission reference if
any, and a "Collected data" checklist matching the Console page's field-list style.
```

---

## 7. Analytics page

```
Same app shell (Analytics active). Page title "Efficiency & quality gain" with a
subtitle noting the numbers are live-computed. Below: a responsive grid of 5-6
stat cards, each a compact panel with one large bold accent-colored number at the
top, a small muted label underneath, and an even smaller muted hint line (e.g.
"14 of 20"). Below the stat grid, a wider panel titled "Manual baseline (today's
Mode A)" containing a simple two/three-column comparison table with a header row
in muted uppercase small text and clean horizontal divider lines between data
rows — no heavy borders or zebra striping, just whitespace and hairlines.
```

---

## 8. Guardrails page

```
Same app shell (Guardrails active). Page title "Guardrails & judgment" with
subtitle "Every rule below is plain, deterministic code — never left to model
judgment alone." Below: a responsive grid of 6 equal cards, each containing a
large single emoji/glyph icon at the top (🎙️ 💳 🚫 📵 🙅 🧯), a bold short title,
a 1-2 sentence muted description, and a thin-divider-separated footer line in
small green monospace-ish text describing how it's technically enforced (e.g.
"Deterministic state-machine gate — the LLM cannot skip it."). Cards lift
slightly with a soft shadow on hover state.
```
