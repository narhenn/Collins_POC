import { ReactNode, useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

const NAV = [
  { to: "/", icon: "fa-th-large", label: "Dashboard" },
  { to: "/library", icon: "fa-database", label: "Scenario Library" },
  { to: "/catalog", icon: "fa-cubes", label: "Asset Catalog" },
  { to: "/builder", icon: "fa-magic", label: "Scenario Builder" },
  { to: "/leaderboard", icon: "fa-trophy", label: "Leaderboard" },
  { to: "/reports", icon: "fa-file-alt", label: "Reports & AAR" },
];

function Clock() {
  const [t, setT] = useState("--:--:--");
  useEffect(() => {
    const tick = () => {
      const n = new Date();
      setT([n.getHours(), n.getMinutes(), n.getSeconds()].map((x) => String(x).padStart(2, "0")).join(":"));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return <div className="topbar-clock">{t}</div>;
}

export default function Layout({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const title =
    NAV.find((n) => n.to !== "/" && loc.pathname.startsWith(n.to))?.label ??
    (loc.pathname.startsWith("/sim") ? "Active Simulation" :
     loc.pathname.startsWith("/launch") ? "Configure & Launch" : "Dashboard");

  return (
    <>
      <nav id="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">GC</div>
          <div>
            <div className="logo-text"><span>Goal</span>Cert</div>
            <div style={{ fontSize: 10, color: "var(--gc-muted)", marginTop: 1 }}>Simulation Engine v2.0</div>
          </div>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          <div className="sidebar-section">
            <div className="sidebar-section-label">Navigation</div>
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}
                className={({ isActive }) => "nav-item" + (isActive ? " active" : "")}>
                <i className={`fa ${n.icon}`} /> {n.label}
              </NavLink>
            ))}
          </div>
        </div>
        <div className="sidebar-bottom">
          <div style={{ fontSize: 12, color: "var(--gc-muted)" }}>
            <span className="status-dot" /> Engine Online
          </div>
          <div style={{ fontSize: 11, color: "var(--gc-muted)", marginTop: 6 }}>
            Deterministic · model-driven
          </div>
        </div>
      </nav>

      <div id="main">
        <div id="topbar">
          <div className="topbar-title">{title}</div>
          <div className="topbar-right">
            <Clock />
            <NavLink to="/library" className="btn btn-primary"><i className="fa fa-plus" /> New Simulation</NavLink>
          </div>
        </div>
        <div className="page">{children}</div>
      </div>
    </>
  );
}
