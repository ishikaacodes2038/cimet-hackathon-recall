import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";

import { api, PendingCallback } from "../api";

export default function Callbacks() {
  const [pending, setPending] = useState<PendingCallback[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [redialing, setRedialing] = useState<string | null>(null);
  const navigate = useNavigate();

  function refresh() {
    api.listPendingCallbacks().then(setPending).catch((err) => setError(String(err)));
  }

  useEffect(refresh, []);

  async function handleRedial(sessionId: string) {
    setRedialing(sessionId);
    try {
      const resp = await api.redial(sessionId);
      if (resp.state) {
        refresh();
        navigate("/console", { state: { resumedSession: resp } });
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setRedialing(null);
    }
  }

  return (
    <div className="max-w-5xl">
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wider text-text-muted mb-1">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-container opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-container" />
          </span>
          Resumption Pipeline
        </div>
        <h1 className="text-2xl font-bold tracking-tight">Pending callbacks</h1>
        <p className="text-text-muted text-sm mt-1 max-w-2xl">
          Calls dropped by a network issue — not a customer choice — keep everything captured so far and can be
          redialled picking up exactly where they left off. Capped at 3 attempts before handing to a human.
        </p>
      </div>

      {error && (
        <div className="mb-4 px-3.5 py-2.5 rounded-lg border border-error/30 bg-error/10 text-text-primary text-sm">
          {error}
        </div>
      )}

      {pending.length === 0 ? (
        <div className="relative overflow-hidden w-full rounded-2xl border border-dashed border-border-hairline bg-surface-container-low/50 py-14 px-6 flex flex-col items-center text-center">
          <div className="w-14 h-14 rounded-full bg-tertiary/10 border border-tertiary/30 flex items-center justify-center mb-3">
            <span className="material-symbols-outlined text-tertiary text-[26px]">verified</span>
          </div>
          <h3 className="font-semibold text-text-primary">No dropped calls right now</h3>
          <p className="text-text-muted text-sm mt-1.5 max-w-md">
            Start a call in the Console and click "Simulate network drop" to see this in action.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {pending.map((p) => (
            <motion.div
              key={p.session_id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="relative overflow-hidden rounded-xl bg-surface/85 border border-border-hairline hover:border-primary-container/40 transition-all p-4 pl-5 flex items-center justify-between gap-4 shadow-sm"
            >
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary-container/70" />
              <div>
                <strong className="text-text-primary">{p.lead_id}</strong>
                <div className="text-text-muted text-xs mt-1">
                  {p.fields_captured} field(s) already captured · attempt {p.callback_attempt} of 3
                </div>
              </div>
              <button
                onClick={() => handleRedial(p.session_id)}
                disabled={!p.can_retry || redialing === p.session_id}
                title={p.can_retry ? "Redial, resuming from what's already captured" : "Max attempts reached"}
                className="shrink-0 px-4 py-2 rounded-lg bg-gradient-to-r from-primary-container to-[#ff7959] text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed hover:brightness-110 transition-all"
              >
                {redialing === p.session_id ? "Redialling..." : p.can_retry ? "↻ Redial now" : "Escalate only"}
              </button>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
