import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import LandingForm from "./LandingForm";

describe("LandingForm", () => {
  it("renders the upload and username steps", () => {
    render(<LandingForm error={null} submitting={false} onSubmit={vi.fn()} />);

    expect(screen.getByText("Upload Resume")).toBeInTheDocument();
    expect(screen.getByText("GitHub Username")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start analysis/i })).toBeDisabled();
  });

  it("enables submit only once a file and username are both present", async () => {
    const user = userEvent.setup();
    render(<LandingForm error={null} submitting={false} onSubmit={vi.fn()} />);

    const submit = screen.getByRole("button", { name: /start analysis/i });
    expect(submit).toBeDisabled();

    await user.type(screen.getByPlaceholderText("e.g., octocat"), "octocat");
    expect(submit).toBeDisabled(); // username alone isn't enough — still no file

    const file = new File(["resume text"], "resume.pdf", { type: "application/pdf" });
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await user.upload(input, file);

    expect(submit).toBeEnabled();
  });

  it("shows the error alert when one is provided", () => {
    render(<LandingForm error="Something went wrong." submitting={false} onSubmit={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
  });
});
