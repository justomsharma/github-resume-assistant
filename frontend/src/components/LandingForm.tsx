"use client";

import { useRef, useState, type DragEvent, type FormEvent } from "react";
import type { AppError } from "@/lib/api";
import ErrorBanner from "./ErrorBanner";

interface LandingFormProps {
  error: AppError | null;
  submitting: boolean;
  onSubmit: (file: File, username: string) => void;
}

/** Port of index.html's upload board + app.js's wireUpload (drag-and-drop). */
export default function LandingForm({ error, submitting, onSubmit }: LandingFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [username, setUsername] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || !username.trim()) return;
    onSubmit(file, username.trim());
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragOver(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }

  return (
    <>
      {error && <ErrorBanner message={error.message} kind={error.kind} />}

      <form className="board" onSubmit={handleSubmit} encType="multipart/form-data">
        <div className="cards">
          <div className="step-card">
            <div className="step-head">
              <span className="step-n">1</span>
              <div>
                <div className="step-t">Upload Resume</div>
                <div className="step-d">Upload your latest resume (PDF or DOCX)</div>
              </div>
            </div>
            <label
              className={`drop${dragOver ? " dragover" : ""}${file ? " hasfile" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <span className="drop-ic" aria-hidden="true">
                ↑
              </span>
              <span className="drop-t">{file ? file.name : "Drag & drop your file here"}</span>
              <span className="drop-or">or</span>
              <span className="btn btn-ghost">Choose File</span>
              <input
                ref={inputRef}
                className="visually-hidden"
                type="file"
                accept=".pdf,.docx"
                required
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <div className="drop-note">Supports PDF, DOCX (Max 10MB)</div>
          </div>

          <div className="step-card">
            <div className="step-head">
              <span className="step-n">2</span>
              <div>
                <div className="step-t">GitHub Username</div>
                <div className="step-d">Enter your GitHub username</div>
              </div>
            </div>
            <div className="gh">
              <span className="pre" aria-hidden="true">
                ◆
              </span>
              <input
                className="field"
                autoComplete="off"
                spellCheck={false}
                placeholder="e.g., octocat"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="privacy">
              <span className="privacy-ic" aria-hidden="true">
                🛡
              </span>
              <div>
                <div className="privacy-t">We value your privacy</div>
                <div className="privacy-d">
                  We&rsquo;ll only analyze public repositories and contributions. No private data
                  is accessed.
                </div>
              </div>
            </div>
          </div>
        </div>

        <button className="btn btn-cta" type="submit" disabled={submitting || !file || !username.trim()}>
          {submitting ? "Analyzing…" : "Start Analysis →"}
        </button>
        <p className="reassure">
          <span aria-hidden="true">🔒</span> Your data is analyzed and discarded — never stored or
          shared.
        </p>
      </form>
    </>
  );
}
