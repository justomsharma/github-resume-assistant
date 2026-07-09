"use client";

import { useEffect, useRef } from "react";

/**
 * Port of app.js's buildGraph. Decorative only (aria-hidden) — the GitHub API
 * surface this app uses has no contribution calendar, so this is a
 * deterministic texture, never presented as real data.
 */
export default function ContributionGraph({ empty }: { empty: boolean }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const mode = empty ? "tail" : "full";
    const cols = window.matchMedia("(max-width:560px)").matches ? 20 : 30;
    const vars = ["--g0", "--g1", "--g2", "--g3", "--g4"];
    const total = cols * 7;
    const tail = total - Math.round(cols * 0.8);

    el.innerHTML = "";
    for (let i = 0; i < total; i++) {
      const cell = document.createElement("i");
      let level = 0;
      // Deterministic pseudo-pattern so the texture is stable across renders.
      let seeded = (Math.sin(i * 12.9898) * 43758.5453) % 1;
      seeded = seeded < 0 ? seeded + 1 : seeded;
      if (mode === "full") {
        level = seeded > 0.86 ? 4 : seeded > 0.68 ? 3 : seeded > 0.45 ? 2 : seeded > 0.22 ? 1 : 0;
      } else if (i >= tail && seeded > 0.32) {
        level = 3 + (seeded > 0.66 ? 1 : 0);
      }
      cell.style.background = `var(${vars[level]})`;
      cell.style.opacity = reduceMotion ? "1" : "0";
      cell.style.transform = reduceMotion ? "none" : "scale(.4)";
      cell.style.animation = reduceMotion ? "none" : `pop .45s ease forwards`;
      cell.style.animationDelay = reduceMotion ? "0ms" : `${i * (mode === "full" ? 3 : 5)}ms`;
      el.appendChild(cell);
    }
  }, [empty]);

  return <div className="graph" ref={ref} data-graph-mode={empty ? "tail" : "full"} aria-hidden="true" />;
}
