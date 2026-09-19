import { motion } from "framer-motion";

const GUARDRAILS = [
  {
    icon: "🎙️",
    title: "Consent first",
    body: "Recording disclosure is delivered before anything is collected. A decline ends the call immediately — zero fields captured.",
    enforced: "Deterministic state-machine gate — the LLM cannot skip it.",
  },
  {
    icon: "💳",
    title: "No card data by voice",
    body: "Payment keywords or a card-number-shaped pattern are intercepted before extraction runs, escalated immediately, and redacted from every transcript.",
    enforced: "Keyword + regex guardrail, checked on every raw utterance.",
  },
  {
    icon: "🚫",
    title: "No product advice",
    body: "A request for advice on which plan to choose is redirected once; a repeated request escalates to a human rather than the AI ever answering it.",
    enforced: "Guardrail refusal template — never LLM-generated advice.",
  },
  {
    icon: "📵",
    title: "DNC-aware",
    body: "Every outbound session is checked against the Do-Not-Call registry before a call is even initiated — not after.",
    enforced: "Gate runs in POST /voice/session, before any session exists.",
  },
  {
    icon: "🙅",
    title: "Respect \"no\" — and remember it",
    body: "A hard refusal ends the call respectfully with no pressure loop, and writes the number back to the DNC registry so the next recovery attempt is blocked too.",
    enforced: "Standing no-contact write-back, not just a one-call decision.",
  },
  {
    icon: "🧯",
    title: "Never fabricate success",
    body: "A journey submission failure is surfaced honestly and escalated — the agent never tells a customer their comparison was submitted when it wasn't.",
    enforced: "Submission validated against the script's required fields.",
  },
  {
    icon: "🔁",
    title: "Reconfirm before locking a value",
    body: "Every field the agent actively asked about is read back (\"I heard 'X' — is that correct?\") before it's treated as final. A decline discards it and re-asks, never silently trusting the first guess.",
    enforced: "State-machine gate — CollectedField.confirmed only flips true after an explicit yes.",
  },
  {
    icon: "🎯",
    title: "Reject vague or off-topic answers",
    body: "A bare \"yes\"/\"ok\" or genuine off-topic chatter is rejected rather than stored as the literal field value — two redirects back to the call's purpose, then escalation, not an endless loop.",
    enforced: "Deterministic filler/chatter check in validation.py — never an LLM judgment call.",
  },
  {
    icon: "🔒",
    title: "Role-gated access to recordings",
    body: "Call transcripts are visible to any signed-in Agent; audio recordings require Team Lead or above. Every recording access is itself logged as an audit event.",
    enforced: "FastAPI dependency on every /call-records endpoint, checked before the handler runs.",
  },
];

const container = { hidden: {}, show: { transition: { staggerChildren: 0.08 } } };
const item = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.4 } } };

export default function Guardrails() {
  return (
    <div className="max-w-6xl">
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wider text-emerald-400 mb-1">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          Runtime verification layer
        </div>
        <h1 className="text-2xl font-bold tracking-tight">Guardrails &amp; judgment</h1>
        <p className="text-text-muted text-sm mt-1 max-w-2xl">
          Every rule below is plain, deterministic code — never left to model judgment alone.
        </p>
      </div>

      <motion.div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" variants={container} initial="hidden" animate="show">
        {GUARDRAILS.map((g) => (
          <motion.div
            key={g.title}
            variants={item}
            whileHover={{ y: -3 }}
            className="glass-card rounded-2xl p-5 flex flex-col justify-between relative overflow-hidden"
          >
            <div className="absolute -top-10 -right-10 w-28 h-28 bg-primary-container/10 rounded-full blur-2xl pointer-events-none" />
            <div className="relative z-10">
              <div className="w-11 h-11 rounded-xl bg-surface-container-high border border-border-hairline flex items-center justify-center text-xl mb-3">
                {g.icon}
              </div>
              <h3 className="font-bold text-text-primary mb-2">{g.title}</h3>
              <p className="text-text-muted text-sm leading-relaxed">{g.body}</p>
            </div>
            <div className="mt-4 pt-3 border-t border-border-hairline/70 flex items-center gap-1.5 relative z-10">
              <span className="material-symbols-outlined text-success text-[15px] shrink-0">check_circle</span>
              <span className="font-mono text-[11px] text-success">{g.enforced}</span>
            </div>
          </motion.div>
        ))}
      </motion.div>
    </div>
  );
}
