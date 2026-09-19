import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, QUICK_LOGIN_ACCOUNTS, setAuth } from "../api";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function doLogin(u: string, p: string) {
    setBusy(true);
    setError(null);
    try {
      const resp = await api.login(u, p);
      setAuth(resp.token, resp.user);
      navigate("/");
    } catch {
      setError("Incorrect username or password.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    await doLogin(username, password);
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-background text-text-primary font-sans relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[550px] h-[550px] bg-primary-container/14 rounded-full blur-[130px] animate-orb-1" />
        <div className="absolute bottom-1/4 left-1/4 w-[450px] h-[450px] bg-[#3842c7]/18 rounded-full blur-[140px] animate-orb-2" />
      </div>

      <form
        onSubmit={handleSubmit}
        className="relative z-10 w-full max-w-[340px] flex flex-col gap-2.5 p-7 rounded-2xl bg-surface/90 backdrop-blur-xl border border-border-hairline shadow-2xl"
      >
        <div className="flex items-center gap-2 text-xl font-bold mb-1">
          <span className="text-primary-container text-2xl">↻</span>
          <span>Recall</span>
        </div>
        <p className="text-text-muted text-sm mb-2">Sign in to the CIMET energy recovery console.</p>

        {error && (
          <div className="px-3 py-2 rounded-lg bg-error/10 border border-error/30 text-error text-sm">{error}</div>
        )}

        <label className="text-[11px] text-text-muted mt-1" htmlFor="login-username">
          Username
        </label>
        <input
          id="login-username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="e.g. alex.kim"
          autoComplete="username"
          className="h-10 px-3 rounded-lg bg-surface-container border border-border-hairline text-text-primary placeholder:text-text-muted/60 focus:border-primary-container focus:outline-none focus:ring-1 focus:ring-primary-container transition-all text-sm"
        />

        <label className="text-[11px] text-text-muted mt-1" htmlFor="login-password">
          Password
        </label>
        <input
          id="login-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          autoComplete="current-password"
          className="h-10 px-3 rounded-lg bg-surface-container border border-border-hairline text-text-primary placeholder:text-text-muted/60 focus:border-primary-container focus:outline-none focus:ring-1 focus:ring-primary-container transition-all text-sm"
        />

        <button
          type="submit"
          disabled={busy || !username || !password}
          className="mt-2 h-10 rounded-lg bg-gradient-to-r from-primary-container to-[#ff7959] text-white font-semibold text-sm hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-[0_0_20px_rgba(255,90,54,0.3)]"
        >
          {busy ? "Signing in..." : "Log in"}
        </button>

        <div className="text-center text-[11px] text-text-muted my-1.5">or use a demo account</div>

        <div className="flex flex-col gap-1.5">
          {QUICK_LOGIN_ACCOUNTS.map((acct) => (
            <button
              key={acct.username}
              type="button"
              disabled={busy}
              onClick={() => doLogin(acct.username, acct.password)}
              className="h-9 rounded-lg border border-border-hairline bg-surface-container/60 hover:bg-surface-container hover:border-primary-container/40 text-text-muted hover:text-text-primary text-[12px] font-medium transition-all disabled:opacity-50"
            >
              {acct.label}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
