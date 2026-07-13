"use client";

interface DashboardSidebarProps {
  profileLogin: string;
  onBackToHome: () => void;
}

/**
 * Standalone dashboard sidebar shared by the loading and results screens.
 * "Home" is the only nav item and is wired to a real action (back to the
 * landing form).
 */
export default function DashboardSidebar({ profileLogin, onBackToHome }: DashboardSidebarProps) {
  return (
    <aside className="dside">
      <div className="dlogo">
        <span className="dlogo-mark">A</span>
        <span className="dlogo-name">AI Analyze</span>
      </div>
      <nav className="dnav">
        <button type="button" className="dnavitem active" onClick={onBackToHome}>
          <span className="dni">⌂</span> Home
        </button>
      </nav>
      <div className="dsidefoot">
        <div className="dprofile">
          <span className="dprofile-av">{profileLogin.slice(0, 2).toUpperCase()}</span>
          <span className="dprofile-name">@{profileLogin}</span>
        </div>
      </div>
    </aside>
  );
}
