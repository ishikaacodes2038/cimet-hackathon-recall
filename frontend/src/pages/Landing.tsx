import { motion, Variants } from "framer-motion";
import { Link } from "react-router-dom";

const HIGHLIGHTS = [
  {
    icon: "history_toggle_off",
    title: "Resumes, never repeats",
    body: "Picks up exactly where the web journey dropped off — fields already on file are never re-asked.",
  },
  {
    icon: "gavel",
    title: "Knows its own limits",
    body: "Seven deterministic escalation categories hand off to a human the moment a call needs one — with full context, so nobody repeats themselves.",
  },
  {
    icon: "shield",
    title: "Guardrails, not guesswork",
    body: "Consent-first, no card data ever collected, no product advice given, DNC-aware, and a hard refusal is remembered for next time.",
  },
];

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12, delayChildren: 0.15 } },
};

const item: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] } },
};

export default function Landing() {
  return (
    <motion.div className="max-w-4xl mx-auto" variants={container} initial="hidden" animate="show">
      <motion.div
        variants={item}
        className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-surface-container/90 border border-border-hairline text-[11px] font-mono tracking-widest text-text-muted mb-6"
      >
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-container opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-container" />
        </span>
        CIMET / ECONNEX — 12-HOUR ENGINEERING HACKATHON
      </motion.div>

      <motion.h1 variants={item} className="text-5xl md:text-6xl font-extrabold tracking-tight mb-4">
        Teach the phone <span className="text-primary-container drop-shadow-[0_0_25px_rgba(255,90,54,0.4)]">to listen.</span>
      </motion.h1>

      <motion.p variants={item} className="text-lg text-text-muted max-w-2xl mb-8 leading-relaxed">
        <strong className="text-text-primary">Recall</strong> is an AI voice agent that recovers a dropped-off Energy
        comparison journey over a real phone call — and knows exactly when to hand a customer back to a human.
      </motion.p>

      <motion.div variants={item} className="flex flex-wrap items-center gap-3 mb-10">
        <Link
          to="/console"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gradient-to-r from-primary-container to-[#ff7959] text-white font-semibold text-sm shadow-[0_0_22px_rgba(255,90,54,0.35)] hover:shadow-[0_0_32px_rgba(255,90,54,0.55)] hover:scale-[1.02] active:scale-[0.98] transition-all"
        >
          Open the console
          <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
        </Link>
        <Link
          to="/analytics"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-surface-container/90 border border-border-hairline text-text-primary font-semibold text-sm hover:bg-surface-container-high transition-all"
        >
          <span className="material-symbols-outlined text-[16px] text-secondary">query_stats</span>
          View live metrics
        </Link>
      </motion.div>

      <motion.div
        variants={item}
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
        className="mb-10 rounded-xl bg-surface/95 border border-border-hairline shadow-2xl overflow-hidden"
      >
        <div className="h-10 px-4 bg-surface-container-low/90 border-b border-border-hairline flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-error/90" />
          <span className="w-2.5 h-2.5 rounded-full bg-warning/90" />
          <span className="w-2.5 h-2.5 rounded-full bg-success/90" />
          <span className="font-mono text-[10px] text-text-muted ml-2">live_session_stream.wav · Active</span>
        </div>
        <div className="p-5 space-y-3">
          <div className="flex items-start gap-2 max-w-lg">
            <div className="w-7 h-7 rounded-lg bg-surface-container border border-primary-container/30 flex items-center justify-center shrink-0">
              <span className="material-symbols-outlined text-primary-container text-[16px]">smart_toy</span>
            </div>
            <div className="p-3 rounded-xl rounded-tl-sm bg-surface-container/90 border border-border-hairline text-sm text-text-primary">
              Hi Priya, this is CIMET calling about the energy comparison you started yesterday...
            </div>
          </div>
          <div className="flex items-start justify-end gap-2 max-w-lg ml-auto">
            <div className="p-3 rounded-xl rounded-tr-sm bg-secondary/15 border border-secondary/25 text-sm text-text-primary">
              Yes, go ahead
            </div>
          </div>
          <div className="flex items-center gap-2 pt-2 border-t border-border-hairline/40">
            <span className="px-2.5 py-1 rounded-full bg-success/15 text-success border border-success/30 font-mono text-[11px] font-semibold">
              full_name ✓
            </span>
            <span className="px-2.5 py-1 rounded-full bg-warning/15 text-warning border border-warning/30 font-mono text-[11px] font-semibold">
              date_of_birth…
            </span>
            <span className="px-2.5 py-1 rounded-full bg-surface-container-high text-text-muted border border-border-hairline font-mono text-[11px]">
              address
            </span>
          </div>
        </div>
      </motion.div>

      <motion.div variants={container} className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {HIGHLIGHTS.map((h) => (
          <motion.div
            key={h.title}
            variants={item}
            whileHover={{ y: -4 }}
            className="group relative p-5 rounded-xl bg-surface/90 border border-border-hairline hover:border-primary-container/50 shadow-sm hover:shadow-[0_10px_30px_rgba(255,90,54,0.15)] transition-all overflow-hidden"
          >
            <div className="absolute -right-8 -top-8 w-24 h-24 bg-primary-container/10 rounded-full blur-2xl group-hover:bg-primary-container/20 transition-all" />
            <div className="relative z-10">
              <div className="w-10 h-10 rounded-lg bg-surface-container-high border border-border-hairline flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                <span className="material-symbols-outlined text-primary-container">{h.icon}</span>
              </div>
              <h3 className="font-bold text-text-primary mb-1.5">{h.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed">{h.body}</p>
            </div>
          </motion.div>
        ))}
      </motion.div>
    </motion.div>
  );
}
