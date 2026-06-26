import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Catalog from "./pages/Catalog";
import Library from "./pages/Library";
import Launch from "./pages/Launch";
import ActiveSim from "./pages/ActiveSim";
import Builder from "./pages/Builder";
import Leaderboard from "./pages/Leaderboard";
import Reports from "./pages/Reports";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/library" element={<Library />} />
        <Route path="/launch/:scenarioId" element={<Launch />} />
        <Route path="/sim/:runId" element={<ActiveSim />} />
        <Route path="/catalog" element={<Catalog />} />
        <Route path="/builder" element={<Builder />} />
        <Route path="/leaderboard" element={<Leaderboard />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/reports/:runId" element={<Reports />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
