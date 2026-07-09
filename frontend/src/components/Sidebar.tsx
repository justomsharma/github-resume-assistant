import Link from "next/link";

export default function Sidebar() {
  return (
    <aside className="side">
      <Link className="logo" href="/">
        <span className="mark">℞</span>
        <span className="name">Resume&nbsp;&times;&nbsp;GitHub</span>
      </Link>
      <nav className="nav">
        <Link className="navitem active" href="/">
          <span className="ni">⌂</span> Analyze
        </Link>
        <a
          className="navitem"
          href="https://github.com/justomsharma/github-resume-assistant"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span className="ni">★</span> Source on GitHub
        </a>
      </nav>
      <div className="sidefoot">
        <div className="promo">
          <div className="promo-t">Grounded, not generic</div>
          <div className="promo-d">
            Every verdict is checked against your real public repos — dependencies, file tree,
            and README.
          </div>
        </div>
      </div>
    </aside>
  );
}
