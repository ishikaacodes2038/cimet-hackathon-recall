import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function Intro({ onFinish }: { onFinish: () => void }) {
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      onFinish();
      return;
    }
    const timer = setTimeout(() => setExiting(true), 1900);
    const finishTimer = setTimeout(onFinish, 2300);
    return () => {
      clearTimeout(timer);
      clearTimeout(finishTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AnimatePresence>
      {!exiting && (
        <motion.div
          exit={{ opacity: 0, filter: "blur(6px)" }}
          transition={{ duration: 0.4 }}
          onClick={onFinish}
          role="presentation"
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-background cursor-pointer overflow-hidden"
        >
          <div className="absolute inset-0 pointer-events-none overflow-hidden z-0">
            <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[550px] h-[550px] bg-primary-container/14 rounded-full blur-[130px] animate-orb-1" />
            <div className="absolute bottom-1/4 left-1/4 w-[450px] h-[450px] bg-[#3842c7]/18 rounded-full blur-[140px] animate-orb-2" />
          </div>

          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 flex items-center gap-4"
          >
            <span className="text-6xl md:text-7xl text-primary-container drop-shadow-[0_0_24px_rgba(255,90,54,0.6)]">↻</span>
            <span className="text-6xl md:text-8xl font-black text-white tracking-tight">Recall</span>
          </motion.div>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="relative z-10 text-lg md:text-xl text-text-muted mt-4"
          >
            Teach the phone to listen.
          </motion.p>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="relative z-10 text-xs text-text-muted/60 uppercase tracking-widest mt-8"
          >
            click to skip
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
