import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";
import type { ErrorKind } from "@/lib/api";
import ErrorBanner from "./ErrorBanner";

describe("ErrorBanner", () => {
  const cases: { kind: ErrorKind; expectedSubtext: string | null }[] = [
    { kind: "invalid_input", expectedSubtext: "Check the details above and try again." },
    { kind: "user_not_found", expectedSubtext: "Check the details above and try again." },
    { kind: "too_large", expectedSubtext: null },
    { kind: "rate_limited", expectedSubtext: "This is usually temporary — try again in a few minutes." },
    { kind: "server_error", expectedSubtext: "Something went wrong on our end — try again shortly." },
    { kind: "network", expectedSubtext: "Check your internet connection and try again." },
  ];

  it.each(cases)("renders the right subtext for kind '$kind'", ({ kind, expectedSubtext }) => {
    render(<ErrorBanner message="Something happened." kind={kind} />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Something happened.");
    if (expectedSubtext) {
      expect(alert).toHaveTextContent(expectedSubtext);
    } else {
      expect(alert.textContent).not.toMatch(/try again/i);
    }
  });

  it("has no axe violations", async () => {
    const { container } = render(<ErrorBanner message="Something happened." kind="server_error" />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
