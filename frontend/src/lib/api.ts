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

/**
 * Upload a resume file + GitHub username to the backend and return the
 * grounded gap report + 30-day plan. Throws AnalysisRequestError with the
 * backend's friendly message on any 4xx/5xx (bad file, rate limit, etc).
 */
export async function analyze(file: File, username: string): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("resume_file", file);
  formData.append("username", username);

  const response = await fetch(`${API_URL}/api/analyze`, {
    method: "POST",
    body: formData,
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
