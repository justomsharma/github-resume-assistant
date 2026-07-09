"use client";

/** Port of app.js's toggleTheme: flips documentElement[data-theme] between light/dark. */
export default function ThemeToggle() {
  function handleClick() {
    const root = document.documentElement;
    let current = root.getAttribute("data-theme");
    if (!current) {
      current = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    root.setAttribute("data-theme", current === "dark" ? "light" : "dark");
  }

  return (
    <button className="themetoggle" type="button" onClick={handleClick}>
      Toggle theme
    </button>
  );
}
