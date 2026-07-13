"use client";

import { useRef, useState } from "react";
import { analyzeWithProgress, AnalysisRequestError } from "@/lib/api";
import type { AppError } from "@/lib/api";
import type { AnalysisResponse, GapReport } from "@/lib/types";
import Sidebar from "@/components/Sidebar";
import DashboardSidebar from "@/components/DashboardSidebar";
import LandingForm from "@/components/LandingForm";
import AnalysisProgress from "@/components/AnalysisProgress";
import AnalysisDashboard from "@/components/AnalysisDashboard";
import ThemeToggle from "@/components/ThemeToggle";

type Screen = "landing" | "loading" | "results";

/** While the plan is still generating, the dashboard renders with `plan: null`. */
interface PartialResult {
  report: GapReport;
  plan: AnalysisResponse["plan"] | null;
}

export default function Home() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [handle, setHandle] = useState("");
  const [error, setError] = useState<AppError | null>(null);
  const [result, setResult] = useState<PartialResult | null>(null);
  const [progress, setProgress] = useState(0);
  const [detail, setDetail] = useState<string | undefined>(undefined);
  const controllerRef = useRef<AbortController | null>(null);

  async function handleSubmit(file: File, username: string) {
    setError(null);
    setHandle(username);
    setProgress(0);
    setDetail(undefined);
    setResult(null);
    setScreen("loading");
    const controller = new AbortController();
    controllerRef.current = controller;
    // Guards against a stale run's callbacks firing after the user has already
    // cancelled or started a new analysis (the fetch/stream keeps running in the
    // background until the promise settles, even once we've moved on from it).
    const isStale = () => controllerRef.current !== controller;

    try {
      const response = await analyzeWithProgress(
        file,
        username,
        {
          onProgress: (fraction) => {
            if (!isStale()) setProgress(fraction);
          },
          onSubProgress: (text) => {
            if (!isStale()) setDetail(text);
          },
          onReportReady: (report) => {
            if (isStale()) return;
            setResult({ report, plan: null });
            setScreen("results");
          },
        },
        controller.signal,
      );
      if (isStale()) return;
      setProgress(1);
      setResult(response);
      setScreen("results");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // User-initiated cancel: just go back to landing, no error to show.
        setScreen("landing");
        return;
      }
      if (isStale()) return;
      setError(
        err instanceof AnalysisRequestError
          ? { message: err.message, kind: err.kind }
          : { message: "Something went wrong. Try again.", kind: "network" },
      );
      setScreen("landing");
    }
  }

  function cancelAnalysis() {
    controllerRef.current?.abort();
  }

  function reset() {
    setResult(null);
    setError(null);
    setScreen("landing");
  }

  if (screen === "results" && result) {
    return (
      <>
        <AnalysisDashboard result={result} onBackToHome={reset} />
        <ThemeToggle />
      </>
    );
  }

  if (screen === "loading") {
    return (
      <div className="dash">
        <div className="dshell">
          <DashboardSidebar profileLogin={handle || "you"} onBackToHome={cancelAnalysis} />
          <main className="dmain">
            <AnalysisProgress
              handle={handle ? `@${handle}` : "your"}
              progress={progress}
              detail={detail}
              onCancel={cancelAnalysis}
            />
          </main>
        </div>
        <ThemeToggle />
      </div>
    );
  }

  return (
    <div className="v-ai">
      <div className="app">
        <div className="shell">
          <Sidebar />
          <main className="main">
            <section className="screen active">
                <div className="hgroup">
                  <span className="pill">Grounded in your real GitHub ⚡</span>
                  <h1>
                    Let&rsquo;s make your resume <span className="grad">credible</span>
                  </h1>
                  <p className="sub">
                    Upload your resume and share your GitHub username to get a grounded gap
                    report and a personalized 30-day build plan.
                  </p>
                </div>
                <LandingForm error={error} submitting={false} onSubmit={handleSubmit} />
                <div className="features">
                  <div className="feat">
                    <span className="feat-ic">🛡</span>
                    <div>
                      <div className="feat-t">Secure &amp; Private</div>
                      <div className="feat-d">Public repos only; nothing is stored</div>
                    </div>
                  </div>
                  <div className="feat">
                    <span className="feat-ic">⚡</span>
                    <div>
                      <div className="feat-t">Grounded Verdicts</div>
                      <div className="feat-d">Checked against your real repo code</div>
                    </div>
                  </div>
                  <div className="feat">
                    <span className="feat-ic">📈</span>
                    <div>
                      <div className="feat-t">Actionable Plan</div>
                      <div className="feat-d">A ranked 30-day plan to close gaps</div>
                    </div>
                  </div>
                </div>
              </section>
          </main>
        </div>
      </div>
      <ThemeToggle />
    </div>
  );
}
