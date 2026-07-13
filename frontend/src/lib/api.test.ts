import { afterEach, describe, expect, it, vi } from "vitest";
import { analyzeWithProgress } from "./api";
import type { AnalysisResponse } from "./types";

/**
 * A duck-typed fetch Response carrying one SSE chunk with every `events` line
 * pre-joined — good enough for `analyzeStream`'s reader.read()/headers.get()
 * usage without depending on jsdom having real ReadableStream/Response globals.
 */
function fakeStreamResponse(events: object[]): Response {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const chunk = new TextEncoder().encode(text);
  let done = false;
  return {
    status: 200,
    ok: true,
    headers: { get: (name: string) => (name === "content-type" ? "text/event-stream" : null) },
    body: {
      getReader: () => ({
        read: async () => {
          if (done) return { done: true, value: undefined };
          done = true;
          return { done: false, value: chunk };
        },
      }),
    },
  } as unknown as Response;
}

describe("analyzeWithProgress (SSE)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("dispatches subprogress and report-ready callbacks, then resolves with the final result", async () => {
    const report: AnalysisResponse["report"] = {
      profile_login: "octocat",
      backed: [],
      not_shown: [],
      not_verifiable: [],
      github_is_empty: false,
    };
    const plan: AnalysisResponse["plan"] = {
      profile_login: "octocat",
      suggestions: [],
      github_is_empty: false,
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        fakeStreamResponse([
          { type: "progress", stage: "parsing", index: 1, total: 5, label: "Parsing your resume" },
          { type: "subprogress", stage: "evidence", detail: "Reading repo 1 of 2" },
          { type: "report", report },
          { type: "result", report, plan },
        ]),
      ),
    );

    const onProgress = vi.fn();
    const onSubProgress = vi.fn();
    const onReportReady = vi.fn();

    const result = await analyzeWithProgress(new File(["resume"], "resume.pdf"), "octocat", {
      onProgress,
      onSubProgress,
      onReportReady,
    });

    expect(onProgress).toHaveBeenCalledWith(1 / 5);
    expect(onSubProgress).toHaveBeenCalledWith("Reading repo 1 of 2");
    expect(onReportReady).toHaveBeenCalledWith(report);
    expect(result).toEqual({ report, plan });
  });

  it("works without onSubProgress/onReportReady (both optional)", async () => {
    const report: AnalysisResponse["report"] = {
      profile_login: "octocat",
      backed: [],
      not_shown: [],
      not_verifiable: [],
      github_is_empty: true,
    };
    const plan: AnalysisResponse["plan"] = { profile_login: "octocat", suggestions: [], github_is_empty: true };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        fakeStreamResponse([
          { type: "subprogress", stage: "evidence", detail: "Reading repo 1 of 1" },
          { type: "report", report },
          { type: "result", report, plan },
        ]),
      ),
    );

    const result = await analyzeWithProgress(new File(["resume"], "resume.pdf"), "newgrad", {
      onProgress: vi.fn(),
    });

    expect(result).toEqual({ report, plan });
  });
});
