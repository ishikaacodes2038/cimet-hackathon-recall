import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { isLoggedIn } from "./api";
import Intro from "./Intro";
import Layout from "./Layout";
import Analytics from "./pages/Analytics";
import Callbacks from "./pages/Callbacks";
import Console from "./pages/Console";
import Guardrails from "./pages/Guardrails";
import Handoffs from "./pages/Handoffs";
import History from "./pages/History";
import Landing from "./pages/Landing";
import Login from "./pages/Login";

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!isLoggedIn()) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const [showIntro, setShowIntro] = useState(true);

  if (showIntro) {
    return <Intro onFinish={() => setShowIntro(false)} />;
  }

  return (
    <Routes>
      <Route path="login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Landing />} />
        <Route path="console" element={<Console />} />
        <Route path="callbacks" element={<Callbacks />} />
        <Route path="handoffs" element={<Handoffs />} />
        <Route path="history" element={<History />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="guardrails" element={<Guardrails />} />
      </Route>
    </Routes>
  );
}
