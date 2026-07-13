import type { AnalysisResponse, ApiErrorResponse } from "./types";

/**
 * NEXT_PUBLIC_API_URL must be set at build time (Vercel env var) — it's
 * inlined into the client bundle since the browser calls the Flask API
 * directly (no Next.js server proxy in between).
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:5000";

export class AnalysisRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "AnalysisRequestError";
  }
}

/** Signals the SSE stream couldn't be used, so the caller should fall back. */
class StreamUnavailableError extends Error {
  constructor() {
    super("streaming unavailable");
    this.name = "StreamUnavailableError";
  }
}

/**
 * Upload a resume file + GitHub username to the backend and return the
 * grounded gap report + 30-day plan. Throws AnalysisRequestError with the
 * backend's friendly message on any 4xx/5xx (bad file, rate limit, etc).
 */
export async function analyze(
  file: File,
  username: string,
  signal?: AbortSignal,
): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("resume_file", file);
  formData.append("username", username);

  const response = await fetch(`${API_URL}/api/analyze`, {
    method: "POST",
    body: formData,
    signal,
  });

  if (response.status === 413) {
    throw new AnalysisRequestError(
      "That file is larger than the 10 MB limit. Upload a smaller file.",
      413,
    );
  }

  const body = (await response.json()) as AnalysisResponse | ApiErrorResponse;
  if (!response.ok) {
    const message = "error" in body ? body.error : "Something went wrong. Try again.";
    throw new AnalysisRequestError(message, response.status);
  }
  return body as AnalysisResponse;
}

/**
 * Run the analysis with real progress. Prefers the SSE stream endpoint (which
 * reports each real pipeline stage); if streaming is unavailable on the host it
 * transparently falls back to the single-shot analyze() with a time-based
 * estimate. onProgress receives a 0..1 fraction. The caller should set the
 * fraction to 1 once this resolves so the ring snaps to 100%.
 */
export async function analyzeWithProgress(
  file: File,
  username: string,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<AnalysisResponse> {
  try {
    return await analyzeStream(file, username, onProgress, signal);
  } catch (err) {
    if (!(err instanceof StreamUnavailableError)) throw err;
    // Streaming blocked/buffered by the host — fall back without failing the page.
  }
  return analyzeWithTimeFill(file, username, onProgress, signal);
}

/** POST to the SSE endpoint and parse real per-stage progress events. */
async function analyzeStream(
  file: File,
  username: string,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("resume_file", file);
  formData.append("username", username);

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/analyze/stream`, {
      method: "POST",
      body: formData,
      signal,
    });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new StreamUnavailableError();
  }

  if (response.status === 413) {
    throw new AnalysisRequestError(
      "That file is larger than the 10 MB limit. Upload a smaller file.",
      413,
    );
  }

  const contentType = response.headers.get("content-type") ?? "";
  // Bad input fails fast as a normal JSON 4xx, not a stream — surface it.
  if (!response.ok && contentType.includes("application/json")) {
    const body = (await response.json()) as ApiErrorResponse;
    throw new AnalysisRequestError(body.error ?? "Something went wrong. Try again.", response.status);
  }
  if (!response.body || !contentType.includes("text/event-stream")) {
    throw new StreamUnavailableError();
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AnalysisResponse | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    // SSE events are separated by a blank line.
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine.slice(5).trim()) as StreamPayload;
      if (payload.type === "progress") {
        onProgress(payload.index / payload.total);
      } else if (payload.type === "result") {
        result = { report: payload.report, plan: payload.plan };
      } else if (payload.type === "error") {
        throw new AnalysisRequestError(payload.error, 502);
      }
    }
  }

  if (result === null) {
    throw new AnalysisRequestError("Something went wrong. Try again.", 500);
  }
  return result;
}

/** Fallback: drive a time-based estimate while the single-shot analyze() runs. */
async function analyzeWithTimeFill(
  file: File,
  username: string,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<AnalysisResponse> {
  const EXPECTED_MS = 20_000;
  const start = Date.now();
  let finished = false;
  const timer = setInterval(() => {
    if (finished) return;
    const elapsed = Date.now() - start;
    // Ease toward 0.95, approaching but never reaching it until the real finish.
    onProgress(0.95 * (1 - Math.exp(-elapsed / (EXPECTED_MS / 3))));
  }, 200);
  try {
    return await analyze(file, username, signal);
  } finally {
    finished = true;
    clearInterval(timer);
  }
}

/** The shape of each SSE `data:` payload from /api/analyze/stream. */
type StreamPayload =
  | { type: "progress"; stage: string; index: number; total: number; label: string }
  | { type: "result"; report: AnalysisResponse["report"]; plan: AnalysisResponse["plan"] }
  | { type: "error"; error: string };
