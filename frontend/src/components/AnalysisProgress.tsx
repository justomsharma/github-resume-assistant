"use client";

import { useEffect, useRef, useState } from "react";

interface Step {
  title: string;
  description: string;
  icon: string;
}

// The 5 real backend stages (src/resume_assistant/web/service.py _STAGES), in
// order: parsing -> profile -> evidence -> report -> plan. Evenly weighted
// since each stage reports one SSE progress event out of the same total.
const STEPS: Step[] = [
  {
    title: "Parsing Resume",
    description: "Extracting skills, experience, and education",
    icon: "📄",
  },
  {
    title: "Analyzing GitHub Profile",
    description: "Scanning repositories, languages, and contributions",
    icon: "🐙",
  },
  {
    title: "Extracting Skills & Experience",
    description: "Identifying key skills and domain expertise",
    icon: "🔠",
  },
  {
    title: "Evaluating Strengths",
    description: "Assessing technical and soft skills",
    icon: "📊",
  },
  {
    title: "Generating Report",
    description: "Compiling insights and recommendations",
    icon: "📝",
  },
];

/**
 * Analysis-in-progress view rendered inside the violet dashboard shell. ``progress``
 * is a 0..1 fraction sourced from real per-stage SSE events (or a time-based
 * fallback) by the page. The displayed value eases toward ``progress`` each frame
 * so stage jumps animate smoothly; motion is skipped when the user prefers
 * reduced motion.
 */
export default function AnalysisProgress({
  handle,
  progress,
  detail,
  onCancel,
}: {
  handle: string;
  progress: number;
  detail?: string;
  onCancel: () => void;
}) {
  const [display, setDisplay] = useState(0);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      frame.current = requestAnimationFrame(() => setDisplay(progress));
      return () => {
        if (frame.current !== null) cancelAnimationFrame(frame.current);
      };
    }
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

  const scaled = display * STEPS.length;
  // A step is "done" once its full share of progress is covered. Using this
  // (rather than clamping an "active index" to STEPS.length - 1) lets the last
  // step flip to a checkmark once display reaches 1, instead of staying stuck
  // showing a spinner forever.
  const doneCount = Math.min(Math.floor(scaled + 1e-9), STEPS.length);

  return (
    <>
      <div className="dtop">
        <div>
          <h1 className="dtitle">
            Analyzing your <em>profile&hellip;</em>
          </h1>
          <p className="dsub">
            Our AI is reviewing {handle}&rsquo;s resume and GitHub profile to generate
            comprehensive insights.
          </p>
        </div>
        <div className="dtop-actions">
          <button type="button" className="dbtn dbtn-ghost" onClick={onCancel}>
            ✕ Cancel Analysis
          </button>
        </div>
      </div>

      <div className="pstep-list" role="progressbar" aria-valuenow={Math.round(display * 100)} aria-valuemin={0} aria-valuemax={100}>
        {STEPS.map((step, i) => {
          const state = i < doneCount ? "done" : i === doneCount ? "now" : "pending";
          const stepPct =
            state === "done" ? 100 : state === "now" ? Math.round((scaled - doneCount) * 100) : 0;
          return (
            <div className={`pstep pstep-${state}`} key={step.title}>
              <span className="pstep-ic">
                {state === "done" ? "✓" : state === "now" ? <span className="pstep-spin" /> : step.icon}
              </span>
              <div className="pstep-body">
                <div className="pstep-t">{step.title}</div>
                <div className="pstep-d">{step.description}</div>
                {state === "now" && detail && <div className="pstep-detail">{detail}</div>}
              </div>
              <span className="pstep-meta">
                {state === "pending" ? "Pending" : `${stepPct}%`}
              </span>
            </div>
          );
        })}
      </div>

      <div className="dnotice">
        <span>✨</span> This may take a few moments. Please don&rsquo;t close this window.
      </div>
    </>
  );
}
