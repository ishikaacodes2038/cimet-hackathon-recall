import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { api, MetricsSummary } from "../api";

function StatCard({ label, value, hint, icon }: { label: string; value: string; hint?: string; icon: string }) {
  return (
    <motion.div
      whileHover={{ y: -3 }}
      className="bg-surface/85 backdrop-blur-md p-4 rounded-2xl border border-border-hairline shadow-lg flex flex-col gap-1.5"
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] text-text-muted uppercase tracking-wider">{label}</span>
        <span className="material-symbols-outlined text-[16px] text-primary-container">{icon}</span>
      </div>
      <span className="font-mono text-3xl font-bold text-text-primary tracking-tight">{value}</span>
      {hint && <span className="text-text-muted text-xs">{hint}</span>}
    </motion.div>
  );
}

export default function Analytics() {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getMetrics().then(setMetrics).catch((err) => setError(String(err)));
  }, []);

  return (
    <div className="max-w-6xl">
      <div className="mb-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface-container/80 border border-primary-container/30 text-[11px] font-mono text-primary uppercase tracking-wider mb-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-container opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-container" />
          </span>
          Operational Benchmark · Live
        </div>
        <h1 className="text-2xl font-bold tracking-tight">Efficiency &amp; quality gain</h1>
        <p className="text-text-muted text-sm mt-1">
          Live-computed from this running server's actual sessions — refresh after running calls in the console.
        </p>
      </div>

      {error && (
        <div className="mb-4 px-3.5 py-2.5 rounded-lg border border-error/30 bg-error/10 text-text-primary text-sm">
          {error}
        </div>
      )}

      {metrics && (
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8"
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.06 } } }}
        >
          <StatCard icon="dialpad" label="Sessions this run" value={String(metrics.total_sessions)} />
          <StatCard
            icon="check_circle"
            label="Completed autonomously"
            value={`${Math.round(metrics.completion_rate * 100)}%`}
            hint={`${metrics.completed} of ${metrics.total_sessions}`}
          />
          <StatCard
            icon="support_agent"
            label="Escalated to a human"
            value={`${Math.round(metrics.escalation_rate * 100)}%`}
            hint={`${metrics.escalated} of ${metrics.total_sessions}`}
          />
          <StatCard icon="sync_alt" label="Warm handoffs generated" value={String(metrics.total_handoffs)} />
          <StatCard icon="fact_check" label="Avg. fields captured / session" value={metrics.avg_fields_captured.toFixed(1)} />
          <StatCard icon="forum" label="Avg. turns / session" value={String(metrics.avg_turns)} />
        </motion.div>
      )}

      <div className="bg-surface/85 backdrop-blur-md rounded-2xl border border-border-hairline shadow-lg p-5">
        <h3 className="text-lg font-bold mb-1">Manual baseline (today's Mode A)</h3>
        <p className="text-text-muted text-sm mb-4">
          Per the hackathon brief: a human agent reads a script line for every field and types every answer into
          the journey iframe, one call at a time, for 100% of dropped-off leads — no carry-over from the web
          journey, no autonomous triage.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="text-text-muted font-mono text-[11px] uppercase tracking-wider border-b border-border-hairline">
                <th className="py-2.5 pr-4 font-semibold">Metric</th>
                <th className="py-2.5 pr-4 font-semibold">Manual (today)</th>
                <th className="py-2.5 font-semibold text-primary-container">Recall (this run)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-hairline/60">
              <tr>
                <td className="py-3 pr-4 text-text-primary">Fields typed by a human per completed journey</td>
                <td className="py-3 pr-4 text-text-muted">all fields, every call</td>
                <td className="py-3 text-tertiary font-medium">0 (autonomous completion)</td>
              </tr>
              <tr>
                <td className="py-3 pr-4 text-text-primary">Calls requiring a human agent</td>
                <td className="py-3 pr-4 text-text-muted">100%</td>
                <td className="py-3 text-tertiary font-medium">{metrics ? `${Math.round(metrics.escalation_rate * 100)}%` : "—"}</td>
              </tr>
              <tr>
                <td className="py-3 pr-4 text-text-primary">Fields re-asked that were already on file</td>
                <td className="py-3 pr-4 text-text-muted">all of them (no carry-over)</td>
                <td className="py-3 text-tertiary font-medium">0 — reused from the dropped web journey</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-text-muted text-xs mt-3">
          Full methodology and a labelled scenario-by-scenario breakdown: <code className="text-primary-container">docs/EFFICIENCY_REPORT.md</code>.
        </p>
      </div>
    </div>
  );
}
