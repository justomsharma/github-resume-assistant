"use client";

interface DashboardSidebarProps {
  profileLogin: string;
  onBackToHome: () => void;
}

const NAV_ITEMS: { label: string; icon: string; active?: boolean }[] = [
  { label: "Home", icon: "⌂", active: true },
  { label: "Analysis History", icon: "◷" },
  { label: "Saved Reports", icon: "▤" },
  { label: "Settings", icon: "⚙" },
];

/**
 * Standalone dashboard sidebar for the results page. Only "Home" is wired to a
 * real action (back to the landing form) — the other nav items have no routes
 * yet, so they render as static/disabled to avoid promising navigation that
 * doesn't exist.
 */
export default function DashboardSidebar({ profileLogin, onBackToHome }: DashboardSidebarProps) {
  return (
    <aside className="dside">
      <div className="dlogo">
        <span className="dlogo-mark">A</span>
        <span className="dlogo-name">AI Analyze</span>
      </div>
      <nav className="dnav">
        {NAV_ITEMS.map((item) =>
          item.active ? (
            <button key={item.label} type="button" className="dnavitem active" onClick={onBackToHome}>
              <span className="dni">{item.icon}</span> {item.label}
            </button>
          ) : (
            <button key={item.label} type="button" className="dnavitem" disabled title="Coming soon">
              <span className="dni">{item.icon}</span> {item.label}
            </button>
          ),
        )}
      </nav>
      <div className="dsidefoot">
        <div className="dpromo">
          <div className="dpromo-t">✨ Upgrade to Pro</div>
          <div className="dpromo-d">Unlock advanced insights, custom reports, and more.</div>
          <button type="button" className="dpromo-btn" disabled title="Coming soon">
            Upgrade Now →
          </button>
        </div>
        <div className="dprofile">
          <span className="dprofile-av">{profileLogin.slice(0, 2).toUpperCase()}</span>
          <span className="dprofile-name">@{profileLogin}</span>
        </div>
      </div>
    </aside>
  );
}
