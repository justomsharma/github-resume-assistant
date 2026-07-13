import type { ErrorKind } from "@/lib/api";

const KIND_META: Record<ErrorKind, { icon: string; subtext: string | null }> = {
  invalid_input: { icon: "⚠", subtext: "Check the details above and try again." },
  user_not_found: { icon: "⚠", subtext: "Check the details above and try again." },
  too_large: { icon: "⚠", subtext: null },
  rate_limited: { icon: "⏳", subtext: "This is usually temporary — try again in a few minutes." },
  server_error: { icon: "✕", subtext: "Something went wrong on our end — try again shortly." },
  network: { icon: "⚡", subtext: "Check your internet connection and try again." },
};

/** A dismissable-by-navigation alert banner, styled per error kind (LandingForm). */
export default function ErrorBanner({ message, kind }: { message: string; kind: ErrorKind }) {
  const { icon, subtext } = KIND_META[kind];
  return (
    <div className="alert" role="alert">
      <span className="alert-ic" aria-hidden="true">
        {icon}
      </span>
      <div>
        <div className="alert-msg">{message}</div>
        {subtext && <div className="alert-sub">{subtext}</div>}
      </div>
    </div>
  );
}
