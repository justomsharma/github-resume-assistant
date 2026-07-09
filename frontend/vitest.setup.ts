import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL doesn't auto-cleanup under Vitest the way it does under Jest, so each
// `it` block's render() would otherwise pile up in the same jsdom document.
afterEach(() => {
  cleanup();
});

// jsdom has no matchMedia implementation; several components (ContributionGraph,
// ThemeToggle) read prefers-reduced-motion / prefers-color-scheme.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
