import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { fetchMe } from "./role";
import LoginPage from "./pages/LoginPage";
import WellsPage from "./pages/WellsPage";
import DashboardPage from "./pages/DashboardPage";
import ModelsPage from "./pages/ModelsPage";
import QualityPage from "./pages/QualityPage";
import EvaluationsPage from "./pages/EvaluationsPage";
import HelpPage from "./pages/HelpPage";

export default function App() {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
  });
  const [, force] = useState(0);

  useEffect(() => {
    const onUnauth = () => {
      qc.setQueryData(["me"], null);
      force((x) => x + 1);
    };
    window.addEventListener("tdml:unauthorized", onUnauth);
    return () => window.removeEventListener("tdml:unauthorized", onUnauth);
  }, [qc]);

  if (me.isLoading) return <div className="center muted">Loading…</div>;
  if (!me.data) return <LoginPage onLogin={() => me.refetch()} />;

  const logout = async () => {
    await api.post("/api/auth/logout").catch(() => undefined);
    qc.clear();
    qc.setQueryData(["me"], null);
    force((x) => x + 1);
  };

  if (me.data.role === "guest") {
    // guest: Monitoring + Dashboard only
    return (
      <div className="app">
        <header className="topbar">
          <div className="brand">Torque &amp; Drag ML Calibration</div>
          <nav>
            <NavLink to="/monitoring">Monitoring</NavLink>
            <NavLink to="/dashboard">Dashboard</NavLink>
          </nav>
          <div className="user">
            <span className="muted">{me.data.username} (guest)</span>
            <button className="btn ghost" onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
        <main>
          <Routes>
            <Route path="/monitoring" element={<WellsPage key="monitoring" purpose="monitoring" />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/dashboard/:wellId" element={<DashboardPage />} />
            <Route path="*" element={<Navigate to="/monitoring" replace />} />
          </Routes>
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Torque &amp; Drag ML Calibration</div>
        <nav>
          <NavLink to="/training">Training Data</NavLink>
          <NavLink to="/monitoring">Monitoring</NavLink>
          <NavLink to="/quality">Data Quality</NavLink>
          <NavLink to="/models">Models</NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/evaluations">Evaluations</NavLink>
          <NavLink to="/help">How-to Guide</NavLink>
        </nav>
        <div className="user">
          <span className="muted">{me.data.username}</span>
          <button className="btn ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/training" replace />} />
          <Route path="/training" element={<WellsPage key="training" purpose="training" />} />
          <Route path="/monitoring" element={<WellsPage key="monitoring" purpose="monitoring" />} />
          <Route path="/quality" element={<QualityPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/evaluations" element={<EvaluationsPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/help/:topic" element={<HelpPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/dashboard/:wellId" element={<DashboardPage />} />
          {/* old links */}
          <Route path="/sumur" element={<Navigate to="/training" replace />} />
          <Route path="/kualitas" element={<Navigate to="/quality" replace />} />
          <Route path="/model" element={<Navigate to="/models" replace />} />
          <Route path="/evaluasi" element={<Navigate to="/evaluations" replace />} />
          <Route path="/panduan/*" element={<Navigate to="/help" replace />} />
          <Route path="*" element={<Navigate to="/training" replace />} />
        </Routes>
      </main>
    </div>
  );
}
