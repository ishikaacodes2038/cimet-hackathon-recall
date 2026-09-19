import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { api, HandoffPacket } from "../api";

export default function Handoffs() {
  const [handoffs, setHandoffs] = useState<HandoffPacket[]>([]);
  const [selected, setSelected] = useState<HandoffPacket | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listHandoffs()
      .then((list) => {
        setHandoffs(list);
        setSelected(list[0] ?? null);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-6xl">
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wider text-primary-container mb-1">
          <span className="w-1.5 h-1.5 rounded-full bg-primary-container animate-pulse" />
          Escalated Sessions
        </div>
        <h1 className="text-2xl font-bold tracking-tight">Warm handoffs</h1>
        <p className="text-text-muted text-sm mt-1">
          Every call the agent escalated, with full context — nobody repeats themselves.
        </p>
      </div>

      {error && (
        <div className="mb-4 px-3.5 py-2.5 rounded-lg border border-error/30 bg-error/10 text-text-primary text-sm">
          {error}
        </div>
      )}

      {!loading && handoffs.length === 0 && (
        <div className="rounded-2xl border border-dashed border-border-hairline bg-surface-container-low/50 py-14 px-6 text-center">
          <p className="text-text-muted text-sm max-w-md mx-auto">
            No escalations yet this session — run a call in the console and trigger one (try asking for a human, or
            mentioning payment).
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        <div className="lg:col-span-4 flex flex-col gap-2">
          {handoffs.map((h) => (
            <motion.button
              key={h.handoff_id}
              onClick={() => setSelected(h)}
              whileHover={{ x: 3 }}
              className={`text-left p-3.5 rounded-xl border transition-all ${
                selected?.handoff_id === h.handoff_id
                  ? "bg-surface-container-high border-primary-container/50"
                  : "bg-surface/70 border-border-hairline hover:border-border-hairline/80"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-error text-xs font-mono font-bold">{h.reason}</span>
                <span className="text-text-muted text-[11px] font-mono">{new Date(h.created_at).toLocaleTimeString()}</span>
              </div>
              <div className="text-text-primary text-sm font-semibold mt-1">{h.lead_id}</div>
            </motion.button>
          ))}
        </div>

        {selected && (
          <motion.div
            key={selected.handoff_id}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            className="lg:col-span-8 bg-surface/90 backdrop-blur-xl rounded-xl border border-border-hairline shadow-xl p-5 flex flex-col gap-3"
          >
            <h3 className="text-lg font-bold flex items-center gap-2">
              <span className="text-error">🔴 {selected.reason}</span>
              <span className="text-text-muted font-normal">— {selected.lead_id}</span>
            </h3>
            <p className="text-text-muted text-sm">{selected.reason_detail}</p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <p><strong className="text-text-muted">Confidence:</strong> {Math.round(selected.confidence * 100)}%</p>
              <p><strong className="text-text-muted">Last message:</strong> "{selected.last_customer_message}"</p>
              <p className="col-span-2"><strong className="text-text-muted">Summary:</strong> {selected.conversation_summary}</p>
              <p><strong className="text-text-muted">Completed:</strong> {Object.keys(selected.completed_fields).join(", ") || "none"}</p>
              <p><strong className="text-text-muted">Missing:</strong> {selected.missing_fields.join(", ") || "none"}</p>
            </div>

            <h4 className="font-semibold mt-2">Full transcript</h4>
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {selected.transcript.map((turn, i) => (
                <div key={i} className={`flex flex-col max-w-[80%] ${turn.speaker === "agent" ? "items-start" : turn.speaker === "customer" ? "items-end ml-auto" : "items-center mx-auto"}`}>
                  {turn.speaker !== "system" && (
                    <span className="text-[10px] font-mono text-text-muted mb-0.5 px-1">{turn.speaker.toUpperCase()}</span>
                  )}
                  <div
                    className={`px-3 py-2 rounded-xl text-sm ${
                      turn.speaker === "system"
                        ? "bg-surface-container/70 text-text-muted text-xs"
                        : turn.speaker === "agent"
                          ? "bg-surface-container border border-border-hairline"
                          : "bg-secondary/15 border border-secondary/25"
                    }`}
                  >
                    {turn.text}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
