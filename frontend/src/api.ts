const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// Real login identity — see backend/app/auth.py. A session starts logged
// OUT (no silent default persona); Login.tsx calls POST /auth/login and
// stores the token this backend actually issued, not a value the frontend
// invents locally. Persisted in localStorage as a per-viewer convenience
// (not shared state) so a reload keeps the same session logged in.
export interface AuthUser {
  username: string;
  display_name: string;
  role: number; // 1 = Agent, 2 = Team Lead, 3 = Admin
}

const AUTH_TOKEN_KEY = "recall_auth_token";
const AUTH_USER_KEY = "recall_auth_user";

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getAuthUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(AUTH_USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function isLoggedIn(): boolean {
  return !!getAuthToken();
}

export function setAuth(token: string, user: AuthUser): void {
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  } catch {
    // per-viewer convenience only — nothing breaks if this can't persist.
  }
}

export function clearAuth(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
  } catch {
    // ignore
  }
}

export const ROLE_LABELS: Record<number, string> = { 1: "Agent", 2: "Team Lead", 3: "Admin" };

// The three seeded demo accounts (see backend/app/auth.py DEMO_CREDENTIALS)
// — shown on the login page as one-click "log in as ..." shortcuts,
// alongside the real username/password form, purely for demo convenience.
export const QUICK_LOGIN_ACCOUNTS = [
  { username: "alex.kim", password: "agent123", label: "Alex Kim — Agent" },
  { username: "priya.nair", password: "lead123", label: "Priya Nair — Team Lead" },
  { username: "sam.torres", password: "admin123", label: "Sam Torres — Admin" },
];

export interface CollectedFieldView {
  value: string;
  confidence: number;
  evidence: string;
}

export interface ConversationTurn {
  speaker: string;
  text: string;
  timestamp: string;
  event: string | null;
}

export interface JourneyStateView {
  lead_id: string;
  session_id: string;
  language: string;
  current_step: string;
  journey_status: string;
  end_reason: string | null;
  consent_status: string;
  collected_fields: Record<string, CollectedFieldView>;
  missing_fields: string[];
  escalation_status: boolean;
  escalation_reason: string | null;
  submission_status: string;
  submission_id: string | null;
  customer_reconfirmed: boolean;
  callback_attempt: number;
  conversation_history: ConversationTurn[];
  efficiency: CallEfficiency;
}

export interface CallEfficiency {
  fields_captured: number;
  fields_captured_first_try: number;
  fields_needing_retry: number;
  duration_seconds: number;
  no_human_touch: boolean;
}

export interface AgentTurn {
  agent_text: string;
  escalated: boolean;
  escalation_category: string | null;
  handoff_id: string | null;
  ended: boolean;
  completed: boolean;
  submission_id: string | null;
  no_contact_requested?: boolean;
}

export interface StartSessionResponse {
  session_id: string;
  call_id?: string | null;
  blocked: boolean;
  block_reason: string;
  agent_text: string;
  state: JourneyStateView | null;
  call_placement_error?: string | null;
}

export interface MetricsSummary {
  total_sessions: number;
  completed: number;
  escalated: number;
  ended_by_customer: number;
  in_progress: number;
  completion_rate: number;
  escalation_rate: number;
  total_handoffs: number;
  avg_fields_captured: number;
  avg_turns: number;
}

export interface MessageResponse {
  turn: AgentTurn;
  state: JourneyStateView;
}

export interface HandoffPacket {
  handoff_id: string;
  lead_id: string;
  session_id: string;
  reason: string;
  reason_detail: string;
  current_step: string;
  completed_fields: Record<string, string>;
  missing_fields: string[];
  last_customer_message: string;
  conversation_summary: string;
  confidence: number;
  transcript: ConversationTurn[];
  created_at: string;
}

export interface LanguagesResponse {
  default: string;
  supported: Record<string, string>;
}

export interface PendingCallback {
  session_id: string;
  lead_id: string;
  callback_attempt: number;
  fields_captured: number;
  can_retry: boolean;
}

export interface CallRecord {
  id: number;
  session_id: string;
  lead_id: string;
  language: string;
  consent_status: string;
  journey_status: string;
  end_reason: string | null;
  escalation_reason: string | null;
  customer_reconfirmed: boolean;
  collected_fields: Record<string, string>;
  submission_id: string | null;
  callback_attempt: number;
  created_at: string;
}

export interface CallEvent {
  id: number;
  session_id: string;
  lead_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface CallRecording {
  id: number;
  session_id: string;
  lead_id: string;
  recording_url: string;
  duration_seconds: number | null;
  format: string | null;
  consent_confirmed: boolean;
  created_at: string;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Demo-Token": token } : {}),
    },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${body}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; user: AuthUser }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  startSession: (leadId: string, language = "en") =>
    request<StartSessionResponse>("/voice/session", {
      method: "POST",
      body: JSON.stringify({ lead_id: leadId, language }),
    }),
  sendMessage: (sessionId: string, text: string) =>
    request<MessageResponse>("/voice/message", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, text }),
    }),
  simulateDrop: (sessionId: string) =>
    request<MessageResponse>("/voice/simulate-drop", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),
  redial: (sessionId: string) =>
    request<StartSessionResponse>("/voice/redial", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),
  listPendingCallbacks: () => request<PendingCallback[]>("/voice/callbacks/pending"),
  getHandoff: (handoffId: string) => request<HandoffPacket>(`/handoff/${handoffId}`),
  listHandoffs: () => request<HandoffPacket[]>("/handoffs"),
  getMetrics: () => request<MetricsSummary>("/metrics/summary"),
  listLanguages: () => request<LanguagesResponse>("/languages"),
  listCallRecords: () => request<CallRecord[]>("/call-records"),
  listCallRecordsForLead: (leadId: string) => request<CallRecord[]>(`/leads/${leadId}/call-records`),
  listCallEventsForLead: (leadId: string) => request<CallEvent[]>(`/leads/${leadId}/call-events`),
  listCallEventsForSession: (sessionId: string) => request<CallEvent[]>(`/call-records/${sessionId}/events`),
  getRecording: (sessionId: string) => request<CallRecording>(`/call-records/${sessionId}/recording`),
  simulateRecording: (sessionId: string) =>
    request<CallRecording>(`/call-records/${sessionId}/simulate-recording`, { method: "POST" }),
  listRecordingsForLead: (leadId: string) => request<CallRecording[]>(`/leads/${leadId}/recordings`),
  reconnect: (sessionId: string) =>
    request<StartSessionResponse>("/voice/reconnect", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),
  simulateSilenceTimeout: (sessionId: string) =>
    request<MessageResponse>("/voice/simulate-silence-timeout", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),
  terminateLead: (leadId: string) =>
    request<{ lead_id: string; closed: boolean }>(`/leads/${leadId}/terminate`, { method: "POST" }),
};
