import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { api, CallRecord, CallRecording } from "../api";

const LANGUAGE_LABELS: Record<string, string> = { en: "English", hi: "Hindi", fil: "Filipino" };

type RecordingStatus = "loading" | "available" | "not_found" | "forbidden" | "unauthorized";

const STATUS_BADGE: Record<string, string> = {
  COMPLETED: "bg-success/15 text-success border-success/30",
  ESCALATED: "bg-error/15 text-error border-error/30",
  ENDED_BY_CUSTOMER: "bg-surface-container-high text-text-muted border-border-hairline",
  DROPPED_NETWORK: "bg-warning/15 text-warning border-warning/30",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-full border font-mono text-[10px] font-semibold ${STATUS_BADGE[status] ?? "bg-surface-container border-border-hairline text-text-muted"}`}>
      {status}
    </span>
  );
}

export default function History() {
  const [records, setRecords] = useState<CallRecord[]>([]);
  const [selected, setSelected] = useState<CallRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState<CallRecording | null>(null);
  const [recordingStatus, setRecordingStatus] = useState<RecordingStatus>("loading");
  const [simulating, setSimulating] = useState(false);

  useEffect(() => {
    api
      .listCallRecords()
      .then((r) => {
        setRecords(r);
        setSelected(r[0] ?? null);
      })
      .catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!selected) {
      setRecording(null);
      return;
    }
    let cancelled = false;
    setRecordingStatus("loading");
    setRecording(null);
    api
      .getRecording(selected.session_id)
      .then((r) => {
        if (cancelled) return;
        setRecording(r);
        setRecordingStatus("available");
      })
      .catch((err) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        if (message.startsWith("401")) setRecordingStatus("unauthorized");
        else if (message.startsWith("403")) setRecordingStatus("forbidden");
        else setRecordingStatus("not_found");
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  async function handleSimulateRecording() {
    if (!selected) return;
    setSimulating(true);
    try {
      const r = await api.simulateRecording(selected.session_id);
      setRecording(r);
      setRecordingStatus("available");
    } catch (err) {
      setError(String(err));
    } finally {
      setSimulating(false);
    }
  }

  return (
    <div className="max-w-6xl">
      <div className="mb-6">
        <span className="inline-block px-2 py-0.5 rounded-full bg-primary-container/15 text-primary border border-primary-container/30 text-[11px] font-mono uppercase tracking-wider mb-1">
          Audit Archive
        </span>
        <h1 className="text-2xl font-bold tracking-tight">Call history</h1>
        <p className="text-text-muted text-sm mt-1 max-w-2xl">
          Every call that reached an outcome — consent, language, collected data, and whether the customer explicitly
          reconfirmed it — durably stored (SQLite), not just held in memory for this session.
        </p>
      </div>

      {error && (
        <div className="mb-4 px-3.5 py-2.5 rounded-lg border border-error/30 bg-error/10 text-text-primary text-sm">
          {error}
        </div>
      )}
      {records.length === 0 && (
        <div className="rounded-2xl border border-dashed border-border-hairline bg-surface-container-low/50 py-14 px-6 text-center">
          <p className="text-text-muted text-sm">No calls recorded yet — complete or escalate a call in the Console.</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        <div className="lg:col-span-4 flex flex-col gap-2">
          {records.map((r) => (
            <motion.button
              key={r.id}
              onClick={() => setSelected(r)}
              whileHover={{ x: 3 }}
              className={`text-left p-3.5 rounded-xl border transition-all flex flex-col gap-1.5 ${
                selected?.id === r.id
                  ? "bg-surface-container-high border-primary-container/50"
                  : "bg-surface/70 border-border-hairline hover:border-border-hairline/80"
              }`}
            >
              <StatusBadge status={r.journey_status} />
              <span className="text-text-primary text-sm font-medium">
                {r.lead_id} · {LANGUAGE_LABELS[r.language] ?? r.language}
              </span>
              <span className="text-text-muted text-[11px] font-mono">{new Date(r.created_at).toLocaleString()}</span>
            </motion.button>
          ))}
        </div>

        {selected && (
          <motion.div
            key={selected.id}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            className="lg:col-span-8 bg-surface/90 backdrop-blur-xl rounded-xl border border-border-hairline shadow-xl p-5 flex flex-col gap-4"
          >
            <h3 className="text-lg font-bold flex items-center gap-2">
              {selected.lead_id} <StatusBadge status={selected.journey_status} />
            </h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <p><strong className="text-text-muted">Language:</strong> {LANGUAGE_LABELS[selected.language] ?? selected.language}</p>
              <p><strong className="text-text-muted">Consent:</strong> {selected.consent_status}</p>
              {selected.end_reason && (
                <p><strong className="text-text-muted">Ended because:</strong> {selected.end_reason.replace(/_/g, " ")}</p>
              )}
              <p><strong className="text-text-muted">Reconfirmed:</strong> {selected.customer_reconfirmed ? "Yes ✓" : "No"}</p>
              {selected.escalation_reason && (
                <p><strong className="text-text-muted">Escalation:</strong> {selected.escalation_reason}</p>
              )}
              {selected.submission_id && (
                <p><strong className="text-text-muted">Submission ref:</strong> {selected.submission_id}</p>
              )}
              {selected.callback_attempt > 0 && (
                <p><strong className="text-text-muted">Callback attempt:</strong> {selected.callback_attempt}</p>
              )}
            </div>

            <h4 className="font-semibold mt-1">Collected data</h4>
            <ul className="flex flex-col gap-1.5 text-sm">
              {Object.entries(selected.collected_fields).map(([name, value]) => (
                <li key={name} className="flex items-center justify-between px-2.5 py-2 rounded-lg bg-surface-container/60">
                  <span className={value ? "text-success" : "text-text-muted"}>{value ? "✓" : "○"} {name}</span>
                  <span className="text-text-muted text-xs">{value ?? "(not provided)"}</span>
                </li>
              ))}
            </ul>

            <h4 className="font-semibold mt-1">Recording</h4>
            {recordingStatus === "loading" && <p className="text-text-muted text-sm">Checking...</p>}
            {recordingStatus === "unauthorized" && (
              <p className="text-text-muted text-sm">Sign-in required to check for a recording.</p>
            )}
            {recordingStatus === "forbidden" && (
              <p className="text-text-muted text-sm">
                🔒 Recording access requires the Team Lead role or above — switch accounts to view it.
              </p>
            )}
            {recordingStatus === "not_found" && (
              <div className="flex flex-col gap-2.5">
                <p className="text-text-muted text-sm">
                  No recording available for this call — this build has no live Vapi telephony account, so nothing
                  ever produces a real one.
                </p>
                {selected.consent_status === "GRANTED" ? (
                  <button
                    type="button"
                    onClick={handleSimulateRecording}
                    disabled={simulating}
                    className="self-start text-[12px] px-3 py-1.5 rounded-md border border-dashed border-border-hairline text-text-muted hover:border-primary-container hover:text-primary-container transition-all disabled:opacity-50"
                  >
                    {simulating ? "Generating..." : "🎙️ Simulate a recording for this call (demo)"}
                  </button>
                ) : (
                  <p className="text-text-muted text-sm">Consent wasn't granted on this call, so a recording can't be simulated either.</p>
                )}
              </div>
            )}
            {recordingStatus === "available" && recording && (
              <div className="p-3.5 rounded-xl bg-surface-container/70 border border-border-hairline flex flex-col gap-2">
                <p className="text-text-muted text-xs">
                  A placeholder demo reference (no live telephony account in this build) — proves storage,
                  RBAC-gated retrieval, and access logging all work end to end; the URL below isn't a real playable
                  file.
                </p>
                <audio controls src={recording.recording_url} className="w-full" />
                <div className="flex items-center gap-2 text-text-muted text-xs">
                  {recording.duration_seconds && <span>{Math.round(recording.duration_seconds)}s</span>}
                  {recording.format && <span>· {recording.format}</span>}
                  <span>· consent confirmed ✓</span>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </div>
    </div>
  );
}
