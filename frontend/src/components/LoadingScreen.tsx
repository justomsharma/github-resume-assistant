"use client";

import { useEffect, useState } from "react";

const STEPS = [
  "Fetching your public repos",
  "Extracting claims from your resume",
  "Matching claims against your repos",
  "Writing your 30-day prescription",
];

/** Port of index.html's loading screen + app.js's playLoading. */
export default function LoadingScreen({ handle }: { handle: string }) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;
    const interval = setInterval(() => {
      setActive((step) => (step < STEPS.length - 1 ? step + 1 : step));
    }, 700);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="load">
      <div className="head">
        <span className="spin" aria-hidden="true" />
        <h2>Reading your work</h2>
      </div>
      <p className="sub">
        This takes a few seconds. We&rsquo;re grounding everything in {handle}&rsquo;s real
        GitHub.
      </p>
      <div className="steps">
        {STEPS.map((label, i) => {
          const cls = i < active ? "done" : i === active ? "now" : "wait";
          const icon = i < active ? "✓" : i === active ? "●" : String(i + 1);
          return (
            <div className={`ls ${cls}`} key={label}>
              <span className="ic">{icon}</span>
              <span className="lb">{label}</span>
              <span className="meta">{i === active ? "working…" : ""}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
