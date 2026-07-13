"use client";

import { useRef, useState } from "react";
import { analyzeWithProgress, AnalysisRequestError } from "@/lib/api";
import type { AnalysisResponse } from "@/lib/types";
import Sidebar from "@/components/Sidebar";
import DashboardSidebar from "@/components/DashboardSidebar";
import LandingForm from "@/components/LandingForm";
import AnalysisProgress from "@/components/AnalysisProgress";
import AnalysisDashboard from "@/components/AnalysisDashboard";
import ThemeToggle from "@/components/ThemeToggle";

type Screen = "landing" | "loading" | "results";

export default function Home() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [handle, setHandle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [progress, setProgress] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);

  async function handleSubmit(file: File, username: string) {
    setError(null);
    setHandle(username);
    setProgress(0);
    setScreen("loading");
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const response = await analyzeWithProgress(file, username, setProgress, controller.signal);
      setProgress(1);
      setResult(response);
      setScreen("results");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // User-initiated cancel: just go back to landing, no error to show.
        setScreen("landing");
        return;
      }
      const message =
        err instanceof AnalysisRequestError ? err.message : "Something went wrong. Try again.";
      setError(message);
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
