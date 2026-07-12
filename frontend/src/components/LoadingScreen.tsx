"use client";

import { useEffect, useRef, useState } from "react";

const STEPS = [
  "Fetching your GitHub profile",
  "Reading your public repos",
  "Matching your resume claims against your repos",
  "Writing your 30-day prescription",
];

// SVG ring geometry. The stroke is drawn as one dash of the full circumference,
// offset by the remaining fraction so the arc grows with progress.
const RADIUS = 78;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * Full-screen processing view: a circular progress ring with the real percentage
 * in its center, title + subtitle above, and the step list below. ``progress`` is
 * a 0..1 fraction sourced from real stage events (or a time-based fallback) by the
 * page. The displayed value eases toward ``progress`` so stage jumps animate
 * smoothly; motion is skipped when the user prefers reduced motion.
 */
export default function LoadingScreen({
  handle,
  progress,
}: {
  handle: string;
  progress: number;
}) {
  const [display, setDisplay] = useState(0);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      // Snap straight to the target (deferred a frame to avoid a sync setState).
      frame.current = requestAnimationFrame(() => setDisplay(progress));
      return () => {
        if (frame.current !== null) cancelAnimationFrame(frame.current);
      };
    }
    // Ease the displayed value toward the real target each frame.
    const tick = () => {
      setDisplay((current) => {
        const next = current + (progress - current) * 0.12;
        return Math.abs(progress - next) < 0.001 ? progress : next;
      });
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, [progress]);

  const percent = Math.round(display * 100);
  const activeStep = Math.min(Math.floor(display * STEPS.length), STEPS.length - 1);
  const offset = CIRCUMFERENCE * (1 - display);

  return (
    <div className="load">
      <div className="ring-wrap">
        <svg className="ring" viewBox="0 0 180 180" aria-hidden="true">
          <circle className="ring-track" cx="90" cy="90" r={RADIUS} />
          <circle
            className="ring-arc"
            cx="90"
            cy="90"
            r={RADIUS}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="ring-center">
          <span className="ring-pct">{percent}%</span>
          <span className="ring-lbl">Analyzing</span>
        </div>
      </div>

      <h2 className="load-title">Reading your work</h2>
      <p className="load-sub">
        This takes a few seconds. We&rsquo;re grounding everything in {handle}&rsquo;s real
        GitHub.
      </p>

      <div
        className="steps"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        {STEPS.map((label, i) => {
          const cls = i < activeStep ? "done" : i === activeStep ? "now" : "wait";
          const icon = i < activeStep ? "✓" : i === activeStep ? "●" : String(i + 1);
          return (
            <div className={`ls ${cls}`} key={label}>
              <span className="ic">{icon}</span>
              <span className="lb">{label}</span>
              <span className="meta">{i === activeStep ? "working…" : ""}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
