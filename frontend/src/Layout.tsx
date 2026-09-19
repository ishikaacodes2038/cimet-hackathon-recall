import { AnimatePresence, motion } from "framer-motion";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { clearAuth, getAuthUser, ROLE_LABELS } from "./api";

const ROLE_HINTS: Record<number, string> = {
  1: "No access to recordings",
  2: "Transcripts + recordings",
  3: "Full access",
};

const NAV_ITEMS = [
  { to: "/", label: "Home", icon: "home", end: true },
  { to: "/console", label: "Console", icon: "keyboard_voice" },
  { to: "/callbacks", label: "Callbacks", icon: "phone_callback" },
  { to: "/handoffs", label: "Handoffs", icon: "support_agent" },
  { to: "/history", label: "History", icon: "history" },
  { to: "/analytics", label: "Analytics", icon: "monitoring" },
  { to: "/guardrails", label: "Guardrails", icon: "shield" },
];

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = getAuthUser();

  function handleLogout() {
    clearAuth();
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-background text-text-primary font-sans relative overflow-x-hidden selection:bg-primary-container selection:text-white">
      {/* Ambient kinetic mesh background */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-40 -left-32 w-[600px] h-[600px] rounded-full bg-primary-container/15 blur-[130px] animate-orb-1" />
        <div className="absolute top-1/3 -right-40 w-[650px] h-[650px] rounded-full bg-[#3842c7]/15 blur-[140px] animate-orb-2" />
        <div className="absolute bottom-0 left-1/3 w-[500px] h-[500px] rounded-full bg-tertiary/8 blur-[140px]" />
        <div className="absolute inset-0 bg-[radial-gradient(#1f253d_1px,transparent_1px)] [background-size:28px_28px] opacity-20" />
      </div>

      <aside className="fixed left-0 top-0 h-full w-64 bg-surface/95 backdrop-blur-2xl border-r border-border-hairline z-50 flex flex-col justify-between">
        <div className="flex flex-col flex-1 min-h-0">
          <div className="h-16 px-5 flex items-center gap-2.5 border-b border-border-hairline">
            <span className="text-2xl text-primary-container">↻</span>
            <div className="flex flex-col leading-tight">
              <span className="text-[17px] font-bold tracking-tight">Recall</span>
              <span className="font-mono text-[9px] text-text-muted uppercase tracking-widest">Voice Agent · CIMET</span>
            </div>
          </div>

          <div className="px-3 py-2.5">
            <div className="flex items-center gap-2 px-2.5 py-1.5 bg-surface-container/70 rounded-lg border border-border-hairline">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-container opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-container" />
              </span>
              <span className="font-mono text-[10px] text-text-muted truncate">CIMET Energy Hackathon</span>
            </div>
          </div>

          <nav className="flex-1 px-2.5 py-1 space-y-1 overflow-y-auto">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all relative ${
                    isActive
                      ? "bg-surface-container-high text-primary border-l-2 border-primary-container font-semibold"
                      : "text-text-muted hover:bg-surface-container hover:text-text-primary"
                  }`
                }
              >
                <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>

        {user && (
          <div className="p-3 border-t border-border-hairline bg-surface-container-low/70 flex flex-col gap-1.5">
            <span className="font-mono text-[9px] text-text-muted uppercase tracking-wider">Signed in as</span>
            <div className="flex flex-col leading-tight text-[13px]">
              <strong className="text-text-primary">{user.display_name}</strong>
              <span className="text-[11px] text-primary-container font-medium">{ROLE_LABELS[user.role]}</span>
            </div>
            <span className="font-mono text-[10px] text-text-muted opacity-80">{ROLE_HINTS[user.role]}</span>
            <button
              type="button"
              onClick={handleLogout}
              className="mt-1 w-full text-[11px] font-mono px-2.5 py-1.5 rounded-md border border-border-hairline bg-surface hover:bg-surface-container text-text-muted hover:text-text-primary transition-all"
            >
              Log out
            </button>
          </div>
        )}
        <div className="px-3 py-2 border-t border-border-hairline/60 font-mono text-[10px] text-text-muted/70">
          CIMET / econnex hackathon
        </div>
      </aside>

      <div className="pl-64 relative z-10">
        <header className="fixed top-0 left-64 right-0 h-14 bg-surface/85 backdrop-blur-2xl border-b border-border-hairline z-40 px-6 flex items-center justify-between">
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-surface-container/90 border border-border-hairline text-text-muted font-mono text-[10px]">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-tertiary opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-tertiary" />
            </span>
            <span className="text-text-primary font-semibold tracking-wide">SESSION ENGINE ONLINE</span>
          </div>
          <div className="flex items-center gap-3 text-text-muted font-mono text-[11px]">
            <span className="hidden lg:flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[16px] text-tertiary">dns</span>
              CIMET_AU_EAST_1
            </span>
            <span className="h-4 w-px bg-border-hairline hidden lg:block" />
            <span className="flex items-center gap-1.5 text-success">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
              142ms
            </span>
          </div>
        </header>

        <main className="relative pt-14 min-h-screen w-full px-6 py-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
