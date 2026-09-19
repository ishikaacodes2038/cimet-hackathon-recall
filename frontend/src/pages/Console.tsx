import { FormEvent, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { api, HandoffPacket, JourneyStateView, LanguagesResponse, StartSessionResponse } from "../api";
import { useVoice } from "../useVoice";
import Waveform from "../Waveform";

const KNOWN_LEADS = ["LEAD-1001", "LEAD-1002", "LEAD-1003", "LEAD-1004"];

const STATUS_BADGE: Record<string, string> = {
  COMPLETED: "bg-success/15 text-success border-success/30",
  ESCALATED: "bg-error/15 text-error border-error/30",
  ENDED_BY_CUSTOMER: "bg-surface-container-high text-text-muted border-border-hairline",
  DROPPED_NETWORK: "bg-warning/15 text-warning border-warning/30",
  IN_PROGRESS: "bg-primary-container/15 text-primary-container border-primary-container/30",
};

function Banner({ tone, children }: { tone: "success" | "neutral" | "escalated" | "blocked" | "error"; children: React.ReactNode }) {
  const styles: Record<string, string> = {
    success: "bg-success/10 border-success/30 text-success",
    neutral: "bg-surface-container border-border-hairline text-text-muted",
    escalated: "bg-error/10 border-error/40 text-error font-semibold",
    blocked: "bg-error/10 border-error/30 text-text-primary",
    error: "bg-error/10 border-error/30 text-text-primary",
  };
  return <div className={`px-3.5 py-2.5 rounded-lg border text-sm ${styles[tone]}`}>{children}</div>;
}

export default function Console() {
  const location = useLocation();
  const resumedSession = (location.state as { resumedSession?: StartSessionResponse } | null)?.resumedSession;

  const [leadId, setLeadId] = useState(resumedSession?.state?.lead_id ?? KNOWN_LEADS[0]);
  const [language, setLanguage] = useState(resumedSession?.state?.language ?? "en-AU");
  const [languages, setLanguages] = useState<LanguagesResponse | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(resumedSession?.session_id ?? null);
  const [state, setState] = useState<JourneyStateView | null>(resumedSession?.state ?? null);
  const [inputText, setInputText] = useState("");
  const [blockedReason, setBlockedReason] = useState<string | null>(null);
  const [handoff, setHandoff] = useState<HandoffPacket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [voiceMode, setVoiceMode] = useState(true);
  const [dropped, setDropped] = useState(false);
  const [reconnectDismissed, setReconnectDismissed] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [terminated, setTerminated] = useState(false);
  const [justCut, setJustCut] = useState(false);

  const voice = useVoice(language);

  useEffect(() => {
    api.listLanguages().then(setLanguages).catch(() => undefined);
  }, []);

  useEffect(() => {
    // Speak the resumed call's opener once, on arrival from a redial —
    // guarded so React StrictMode's double-invoke in dev doesn't double-speak.
    if (resumedSession && voiceMode) {
      voice.speak(resumedSession.agent_text);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function sendText(text: string) {
    if (!sessionId || !text.trim()) return;
    setBusy(true);
    setError(null);
    setJustCut(false);
    try {
      const resp = await api.sendMessage(sessionId, text.trim());
      setState(resp.state);
      setInputText("");
      if (resp.turn.escalated && resp.turn.handoff_id) {
        const packet = await api.getHandoff(resp.turn.handoff_id);
        setHandoff(packet);
      }
      if (voiceMode) voice.speak(resp.turn.agent_text);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleStartCall() {
    setError(null);
    setHandoff(null);
    setBlockedReason(null);
    setDropped(false);
    setBusy(true);
    try {
      const resp = await api.startSession(leadId, language);
      if (resp.blocked) {
        setBlockedReason(resp.block_reason);
        setSessionId(null);
        setState(null);
        return;
      }
      setSessionId(resp.session_id);
      setState(resp.state);
      if (voiceMode) voice.speak(resp.agent_text);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSend(e: FormEvent) {
    e.preventDefault();
    await sendText(inputText);
  }

  function handleMicClick() {
    if (voice.isListening) {
      voice.stopListening();
      return;
    }
    voice.startListening((transcript) => {
      sendText(transcript);
    });
  }

  async function handleSimulateDrop() {
    if (!sessionId) return;
    const resp = await api.simulateDrop(sessionId);
    setState(resp.state);
    setDropped(true);
    setReconnectDismissed(false);
  }

  async function handleSimulateSilence() {
    if (!sessionId) return;
    const resp = await api.simulateSilenceTimeout(sessionId);
    setState(resp.state);
    setDropped(true);
    setReconnectDismissed(false);
  }

  function handleResetCall() {
    // The only thing that actually makes "Start recovery call" clickable
    // again — without this, sessionId never clears once a call ends, so the
    // button stays stuck on "Call in progress" forever and there is no way
    // to run a second call without reloading the whole page.
    setSessionId(null);
    setState(null);
    setHandoff(null);
    setError(null);
    setBlockedReason(null);
    setDropped(false);
    setInputText("");
    setReconnectDismissed(false);
    setTerminated(false);
    setJustCut(false);
  }

  async function handleReconnectNow() {
    if (!sessionId) return;
    setReconnecting(true);
    try {
      const resp = await api.reconnect(sessionId);
      setSessionId(resp.session_id);
      setState(resp.state);
      setDropped(false);
      setReconnectDismissed(false);
      if (voiceMode) voice.speak(resp.agent_text);
    } catch (err) {
      setError(String(err));
    } finally {
      setReconnecting(false);
    }
  }

  async function handleTerminateLead() {
    if (!state) return;
    await api.terminateLead(state.lead_id);
    setTerminated(true);
  }

  const isCallOver =
    state !== null && ["COMPLETED", "ESCALATED", "ENDED_BY_CUSTOMER"].includes(state.journey_status);

  const showReconnectPopup =
    !!state &&
    state.journey_status === "DROPPED_NETWORK" &&
    state.end_reason === "abrupt_disconnect" &&
    !reconnectDismissed;

  return (
    <div className="flex flex-col gap-5 max-w-[1400px] mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Live recovery call</h1>
          <p className="text-text-muted text-sm mt-0.5">
            Pick a dropped-off lead, a language, and run the Agent-Driven recovery flow.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-text-muted bg-surface-container/60 px-3 py-1.5 rounded-lg border border-border-hairline">
          <input type="checkbox" checked={voiceMode} onChange={(e) => setVoiceMode(e.target.checked)} className="accent-primary-container" />
          Speak agent replies aloud
        </label>
      </div>

      <p className="text-text-muted text-[11px] font-mono uppercase tracking-wider -mt-2">
        Dev/test harness (browser mic + text) — the judged demo call runs over a real phone via Vapi, see README §13
      </p>

      {!voice.supported && (
        <Banner tone="neutral">
          🎤 Real-time mic input isn't supported in this browser (Chrome or Edge required) — text input still works fully.
        </Banner>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        <section className="lg:col-span-8 flex flex-col gap-4">
          {/* Control toolbar */}
          <div className="bg-surface/90 backdrop-blur-xl rounded-xl p-4 border border-border-hairline shadow-lg">
            <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
              <div className="sm:col-span-5 flex flex-col gap-1">
                <label htmlFor="lead-select" className="text-[10px] font-mono uppercase tracking-wider text-text-muted">
                  Lead
                </label>
                <select
                  id="lead-select"
                  value={leadId}
                  onChange={(e) => setLeadId(e.target.value)}
                  disabled={!!sessionId}
                  className="h-10 px-3 bg-surface-container/90 border border-border-hairline rounded-lg text-sm text-text-primary focus:border-primary-container focus:outline-none disabled:opacity-60"
                >
                  {KNOWN_LEADS.map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))}
                </select>
              </div>
              <div className="sm:col-span-4 flex flex-col gap-1">
                <label htmlFor="lang-select" className="text-[10px] font-mono uppercase tracking-wider text-text-muted">
                  Language
                </label>
                <select
                  id="lang-select"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  disabled={!!sessionId}
                  className="h-10 px-3 bg-surface-container/90 border border-border-hairline rounded-lg text-sm text-text-primary focus:border-primary-container focus:outline-none disabled:opacity-60"
                >
                  {Object.entries(languages?.supported ?? { en: "English (Australian)" }).map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="sm:col-span-3">
                <button
                  onClick={handleStartCall}
                  disabled={busy || !!sessionId}
                  className="w-full h-10 px-4 rounded-lg bg-gradient-to-r from-primary-container to-[#ff7959] text-white font-semibold text-sm flex items-center justify-center gap-1.5 hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md shadow-primary-container/20"
                >
                  <span className="material-symbols-outlined text-[18px]">call</span>
                  {sessionId ? "Call in progress" : "Start recovery call"}
                </button>
              </div>
            </div>
          </div>

          {blockedReason && (
            <Banner tone="blocked">
              🚫 Call blocked before dialling — reason: <strong>{blockedReason}</strong>
            </Banner>
          )}
          {error && <Banner tone="error">{error}</Banner>}

          {state && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`px-2.5 py-1 rounded-full border font-mono text-[11px] font-semibold ${STATUS_BADGE[state.journey_status] ?? "bg-surface-container border-border-hairline text-text-muted"}`}>
                  {state.journey_status}
                </span>
                <span className="text-text-muted text-xs font-mono">LEAD: <strong className="text-text-primary">{state.lead_id}</strong></span>
                <span className="text-text-muted text-xs font-mono">STEP: <strong className="text-text-primary">{state.current_step}</strong></span>
                {state.callback_attempt > 0 && (
                  <span className="text-text-muted text-xs font-mono">CALLBACK ATTEMPT: <strong className="text-text-primary">{state.callback_attempt}</strong></span>
                )}
              </div>

              {/* Transcript panel */}
              <div className="bg-surface/90 backdrop-blur-xl rounded-xl border border-border-hairline shadow-xl flex flex-col overflow-hidden">
                <div className="px-4 py-2.5 border-b border-border-hairline bg-surface-container/60 flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px] text-tertiary">graphic_eq</span>
                  <span className="font-semibold text-sm">Dialogue stream</span>
                </div>
                <div className="p-4 space-y-3 min-h-[280px] max-h-[420px] overflow-y-auto">
                  {state.conversation_history.map((turn, i) => {
                    if (turn.speaker === "system") {
                      return (
                        <div key={i} className="flex justify-center">
                          <span className="text-[10px] font-mono uppercase text-text-muted bg-surface-container/80 px-2.5 py-1 rounded-full border border-border-hairline">
                            {turn.text} {turn.event && `· ${turn.event}`}
                          </span>
                        </div>
                      );
                    }
                    const isAgent = turn.speaker === "agent";
                    return (
                      <div key={i} className={`flex flex-col max-w-[80%] ${isAgent ? "items-start" : "items-end ml-auto"}`}>
                        <span className="text-[10px] font-mono text-text-muted mb-1 px-1">
                          {isAgent ? "AGENT" : "CUSTOMER"}
                        </span>
                        <div
                          className={`px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed border ${
                            isAgent
                              ? "rounded-tl-sm bg-surface-container/90 border-border-hairline text-text-primary"
                              : "rounded-tr-sm bg-secondary/15 border-secondary/25 text-text-primary"
                          }`}
                        >
                          {turn.text}
                        </div>
                        {turn.event && (
                          <span className="text-[9px] font-mono text-primary-container mt-1 px-1">{turn.event}</span>
                        )}
                      </div>
                    );
                  })}
                </div>

                {state.journey_status === "IN_PROGRESS" && (
                  <div className="border-t border-border-hairline bg-surface-container-low/70 p-4 flex flex-col gap-2.5">
                    <Waveform active={voice.isListening || voice.isSpeaking} tone={voice.isSpeaking ? "green" : "accent"} />
                    <form className="flex items-center gap-2" onSubmit={handleSend}>
                      {voice.supported && (
                        <button
                          type="button"
                          onClick={handleMicClick}
                          disabled={busy}
                          title={
                            voice.isListening ? "Stop listening" : voice.isSpeaking ? "Click to interrupt the agent and speak" : "Click and speak"
                          }
                          className={`w-10 h-10 shrink-0 rounded-full flex items-center justify-center transition-all ${
                            voice.isListening
                              ? "bg-error text-white animate-pulse"
                              : "bg-gradient-to-tr from-primary-container to-[#ff7959] text-white hover:brightness-110"
                          } disabled:opacity-50`}
                        >
                          <span className="material-symbols-outlined text-[18px]">{voice.isListening ? "stop" : "mic"}</span>
                        </button>
                      )}
                      <input
                        value={voice.isListening ? voice.interimText : inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        placeholder="Type, or click the mic and speak..."
                        disabled={busy || voice.isListening}
                        className="flex-1 h-10 px-3.5 bg-surface-container border border-border-hairline rounded-lg text-sm text-text-primary placeholder:text-text-muted/60 focus:border-primary-container focus:outline-none disabled:opacity-60"
                      />
                      <button
                        type="submit"
                        disabled={busy || voice.isListening}
                        className="h-10 px-4 rounded-lg border border-border-hairline bg-surface-container/60 hover:bg-surface-container text-text-primary text-sm font-medium disabled:opacity-50 transition-all"
                      >
                        Send
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          voice.cutOff();
                          setJustCut(true);
                        }}
                        disabled={!voice.isSpeaking}
                        title="Stop the agent talking immediately"
                        className="h-10 px-3.5 rounded-lg border border-error/60 bg-error/5 text-error hover:bg-error hover:text-white disabled:opacity-40 disabled:hover:bg-error/5 disabled:hover:text-error font-semibold text-sm flex items-center gap-1.5 transition-all shrink-0"
                      >
                        <span className="material-symbols-outlined text-[16px]">content_cut</span>
                        Cut
                      </button>
                    </form>

                    {justCut && (
                      <div className="text-xs text-text-muted flex items-center gap-2">
                        Agent interrupted.
                        <button type="button" onClick={handleResetCall} className="text-primary-container hover:underline font-medium">
                          🔄 Start a separate call instead
                        </button>
                      </div>
                    )}
                    {(voice.isListening || voice.isSpeaking) && (
                      <div className="text-xs text-text-muted">
                        {voice.isListening && "🎤 Listening..."}
                        {voice.isSpeaking && "🔊 Agent speaking... (click mic or Cut to interrupt)"}
                      </div>
                    )}
                    <div className="flex gap-2 pt-1">
                      <button
                        type="button"
                        onClick={handleSimulateDrop}
                        className="text-[11px] px-2.5 py-1.5 rounded-md border border-dashed border-border-hairline text-text-muted hover:border-warning hover:text-warning transition-all"
                      >
                        ⚠ Simulate network drop (demo)
                      </button>
                      <button
                        type="button"
                        onClick={handleSimulateSilence}
                        className="text-[11px] px-2.5 py-1.5 rounded-md border border-dashed border-border-hairline text-text-muted hover:border-warning hover:text-warning transition-all"
                      >
                        🔇 Simulate customer silence (demo)
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {state.journey_status === "COMPLETED" && (
                <Banner tone="success">
                  ✅ Journey submitted — reference {state.submission_id}
                  {state.customer_reconfirmed && " · customer reconfirmed before submission"}
                </Banner>
              )}
              {state.journey_status === "ENDED_BY_CUSTOMER" && (
                <Banner tone="neutral">Call ended at the customer's request.</Banner>
              )}
              {state.journey_status === "ESCALATED" && (
                <Banner tone="escalated">🔴 Escalated to a human agent — reason: {state.escalation_reason}</Banner>
              )}
              {dropped && state.journey_status === "DROPPED_NETWORK" && (
                <Banner tone="blocked">
                  {state.end_reason === "silence_timeout" ? "🔇 Customer stopped responding." : "📵 Call dropped (simulated network issue)."}{" "}
                  Everything captured so far is saved —{" "}
                  <Link to="/callbacks" className="underline text-text-primary">
                    redial it from Callbacks
                  </Link>
                  .
                </Banner>
              )}

              {isCallOver && (
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 px-3.5 py-2.5 rounded-lg bg-surface-container/70 border border-border-hairline font-mono text-[12px] text-text-muted">
                  <span className="text-text-primary font-semibold">
                    {state.efficiency.fields_captured_first_try}/{state.efficiency.fields_captured} fields first-try
                  </span>
                  <span>{state.efficiency.duration_seconds}s</span>
                  <span>{state.efficiency.fields_needing_retry} retr{state.efficiency.fields_needing_retry === 1 ? "y" : "ies"}</span>
                  <span className={state.efficiency.no_human_touch ? "text-success" : "text-text-muted"}>
                    {state.efficiency.no_human_touch ? "0 manual re-entries — fully autonomous" : "handed to a human"}
                  </span>
                </div>
              )}

              {showReconnectPopup && (
                <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-lg bg-warning/10 border border-warning/40">
                  <div className="text-sm text-warning">
                    <strong>The call dropped unexpectedly.</strong> Reconnect now?
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleReconnectNow}
                      disabled={reconnecting}
                      className="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-primary-container to-[#ff7959] text-white text-sm font-semibold disabled:opacity-60 transition-all"
                    >
                      {reconnecting ? "Reconnecting..." : "📞 Reconnect now"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setReconnectDismissed(true)}
                      className="px-3.5 py-1.5 rounded-lg border border-border-hairline text-text-muted hover:text-text-primary text-sm transition-all"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              )}

              {isCallOver && (
                <div className="flex flex-col gap-3 p-4 rounded-xl bg-surface-container-low/90 border border-border-hairline">
                  <div className="flex items-center gap-2 text-xs text-text-muted">
                    <span><strong className="text-text-primary">{Object.keys(state.collected_fields).length}</strong> field{Object.keys(state.collected_fields).length === 1 ? "" : "s"} collected</span>
                    <span>·</span>
                    <span>{state.conversation_history.length} turns</span>
                    {state.callback_attempt > 0 && (
                      <>
                        <span>·</span>
                        <span>callback attempt {state.callback_attempt}</span>
                      </>
                    )}
                  </div>
                  {terminated ? (
                    <Banner tone="neutral">🛑 Lead closed — no further recovery attempts.</Banner>
                  ) : (
                    <div className="flex flex-wrap items-center gap-3">
                      <Link to="/history" className="text-primary-container text-sm font-semibold hover:underline">
                        📋 View full call trace in History
                      </Link>
                      {state.end_reason !== "hard_refusal" && (
                        <button
                          type="button"
                          onClick={handleResetCall}
                          className="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-primary-container to-[#ff7959] text-white text-sm font-semibold transition-all"
                        >
                          📞 Call again
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={handleTerminateLead}
                        className="px-3.5 py-1.5 rounded-lg border border-error/40 bg-error/5 text-error hover:bg-error/15 text-sm font-medium transition-all"
                      >
                        🛑 Terminate — no more attempts
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </section>

        <section className="lg:col-span-4 flex flex-col gap-4">
          <div className="bg-surface/90 backdrop-blur-xl rounded-xl border border-border-hairline shadow-xl p-5 flex flex-col gap-3">
            <h3 className="font-semibold flex items-center gap-1.5">
              <span className="material-symbols-outlined text-tertiary text-[18px]">assignment_turned_in</span>
              Collected data
            </h3>
            {state ? (
              <ul className="flex flex-col gap-1.5 text-sm">
                {Object.entries(state.collected_fields).map(([name, f]) => (
                  <li
                    key={name}
                    className={`flex items-center justify-between gap-2 px-2.5 py-2 rounded-lg bg-surface-container/60 ${
                      f.value === "(not provided)" ? "text-text-muted" : ""
                    }`}
                  >
                    <span className={f.value === "(not provided)" ? "text-text-muted" : "text-success"}>
                      {f.value === "(not provided)" ? "○" : "✓"} {name}
                    </span>
                    <span className="text-text-muted text-xs truncate max-w-[40%]">{f.value}</span>
                    <span className="text-text-muted text-[11px] font-mono">{Math.round(f.confidence * 100)}%</span>
                  </li>
                ))}
                {state.missing_fields.map((name) => (
                  <li key={name} className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-lg bg-surface-container/60">
                    <span className="text-warning">⚠ {name}</span>
                    <span className="text-text-muted text-xs">pending</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-text-muted text-sm">Start a call to see collected fields.</p>
            )}

            <h3 className="font-semibold mt-2">Escalation</h3>
            {state?.escalation_status ? (
              <Banner tone="escalated">
                🔴 HUMAN HANDOFF
                <div className="font-normal mt-0.5">Reason: {state.escalation_reason}</div>
              </Banner>
            ) : (
              <Banner tone="success">NORMAL</Banner>
            )}
          </div>

          {handoff && (
            <div className="bg-surface/90 rounded-xl border border-error/30 shadow-lg p-4 text-sm flex flex-col gap-2">
              <h4 className="font-semibold text-error mb-1">Warm handoff context</h4>
              <p><strong>Reason:</strong> {handoff.reason} — {handoff.reason_detail}</p>
              <p><strong>Confidence:</strong> {Math.round(handoff.confidence * 100)}%</p>
              <p><strong>Summary:</strong> {handoff.conversation_summary}</p>
              <p><strong>Last message:</strong> "{handoff.last_customer_message}"</p>
              <p><strong>Completed:</strong> {Object.keys(handoff.completed_fields).join(", ") || "none"}</p>
              <p><strong>Missing:</strong> {handoff.missing_fields.join(", ") || "none"}</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
