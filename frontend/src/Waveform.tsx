import { motion } from "framer-motion";

const BAR_COUNT = 32;

/** Purely CSS/motion-driven — no Web Audio amplitude analysis, so no extra
 * mic-stream permissions beyond what SpeechRecognition already needs. Active
 * (listening/speaking) bars bounce through a keyframe loop with a per-bar
 * stagger; idle bars sit flat. */
export default function Waveform({ active, tone = "accent" }: { active: boolean; tone?: "accent" | "green" }) {
  const barColor = tone === "green" ? "bg-tertiary shadow-[0_0_6px_rgba(74,224,141,0.5)]" : "bg-primary-container shadow-[0_0_6px_rgba(255,90,54,0.5)]";
  return (
    <div className="h-11 flex items-center justify-between gap-[3px] px-3 py-1 bg-surface-container-low/60 rounded-lg border border-border-hairline/60">
      {Array.from({ length: BAR_COUNT }).map((_, i) => (
        <motion.span
          key={i}
          className={`w-1 rounded-full ${barColor} origin-center`}
          style={{ height: 24 }}
          animate={
            active
              ? { scaleY: [0.25, 1, 0.4, 0.85, 0.3, 0.9, 0.25] }
              : { scaleY: 0.15 }
          }
          transition={
            active
              ? { duration: 1.1 + (i % 5) * 0.08, repeat: Infinity, ease: "easeInOut", delay: (i % 8) * 0.06 }
              : { duration: 0.3 }
          }
        />
      ))}
    </div>
  );
}
