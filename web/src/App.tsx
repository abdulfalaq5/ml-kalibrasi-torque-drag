import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import LoginPage from "./pages/LoginPage";
import WellsPage from "./pages/WellsPage";
import DashboardPage from "./pages/DashboardPage";
import ModelsPage from "./pages/ModelsPage";
import QualityPage from "./pages/QualityPage";
import EvaluationsPage from "./pages/EvaluationsPage";

export default function App() {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<{ username: string }>("/api/auth/me"),
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

  if (me.isLoading) return <div className="center muted">Memuat…</div>;
  if (!me.data) return <LoginPage onLogin={() => me.refetch()} />;

  const logout = async () => {
    await api.post("/api/auth/logout").catch(() => undefined);
    qc.clear();
    qc.setQueryData(["me"], null);
    force((x) => x + 1);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Kalibrasi Torque &amp; Drag ML</div>
        <nav>
          <NavLink to="/sumur">Data sumur</NavLink>
          <NavLink to="/kualitas">Kualitas data</NavLink>
          <NavLink to="/model">Model</NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/evaluasi">Evaluasi</NavLink>
        </nav>
        <div className="user">
          <span className="muted">{me.data.username}</span>
          <button className="btn ghost" onClick={logout}>
            Keluar
          </button>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/sumur" replace />} />
          <Route path="/sumur" element={<WellsPage />} />
          <Route path="/kualitas" element={<QualityPage />} />
          <Route path="/model" element={<ModelsPage />} />
          <Route path="/evaluasi" element={<EvaluationsPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/dashboard/:wellId" element={<DashboardPage />} />
          <Route path="*" element={<Navigate to="/sumur" replace />} />
        </Routes>
      </main>
    </div>
  );
}
