// Progressive enhancement for the GitHub Resume Assistant web app.
// Rendering + formatting live in the server-side Jinja templates; this script
// only adds the loading animation on submit (index) and the decorative
// contribution graph (results). Everything still works with JS disabled: the
// form does a plain POST and the server renders the results page.

(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function toggleTheme() {
    var root = document.documentElement;
    var current = root.getAttribute("data-theme");
    if (!current) {
      current = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    root.setAttribute("data-theme", current === "dark" ? "light" : "dark");
  }

  // --- Landing: swap to the loading screen while the POST is in flight -------
  function wireForm() {
    var form = document.getElementById("analyzeForm");
    if (!form) return;

    form.addEventListener("submit", function () {
      // Do NOT preventDefault: let the browser POST and navigate to /analyze.
      // Showing the loading screen here keeps it visible until the results
      // page finishes loading.
      var landing = document.getElementById("s-landing");
      var loading = document.getElementById("s-loading");
      if (!landing || !loading) return;

      var userField = document.getElementById("username");
      var handle = userField && userField.value.trim() ? "@" + userField.value.trim() : "your";
      var loadHandle = document.getElementById("loadHandle");
      if (loadHandle) loadHandle.textContent = handle;

      landing.classList.remove("active");
      loading.classList.add("active");
      playLoading(handle);
    });
  }

  function playLoading(handle) {
    var box = document.getElementById("loadSteps");
    if (!box) return;
    var steps = [
      "Fetching " + handle + "'s public repos",
      "Extracting claims from your resume",
      "Matching claims against your repos",
      "Writing your 30-day prescription",
    ];

    function paint(active) {
      box.innerHTML = "";
      steps.forEach(function (label, i) {
        var cls = i < active ? "done" : i === active ? "now" : "wait";
        var icon = i < active ? "✓" : i === active ? "●" : String(i + 1);
        var meta = i === active ? "working…" : "";
        box.insertAdjacentHTML(
          "beforeend",
          '<div class="ls ' + cls + '"><span class="ic">' + icon +
            '</span><span class="lb">' + label + '</span><span class="meta">' + meta + "</span></div>"
        );
      });
    }

    if (reduceMotion) {
      paint(0);
      return;
    }
    var step = 0;
    paint(0);
    setInterval(function () {
      step = step < steps.length - 1 ? step + 1 : step;
      paint(step);
    }, 700);
  }

  // --- Results: decorative contribution graph --------------------------------
  // The GitHub API surface we use has no contribution calendar, so this graph
  // is intentionally decorative — a deterministic texture, never presented as
  // real data (aria-hidden in the template).
  function buildGraph() {
    var el = document.getElementById("h-graph");
    if (!el) return;
    var mode = el.getAttribute("data-graph-mode") || "tail";
    var cols = window.matchMedia("(max-width:560px)").matches ? 20 : 30;
    var vars = ["--g0", "--g1", "--g2", "--g3", "--g4"];
    var total = cols * 7;
    var tail = total - Math.round(cols * 0.8);

    el.innerHTML = "";
    for (var i = 0; i < total; i++) {
      var cell = document.createElement("i");
      var level = 0;
      // Deterministic pseudo-pattern so the texture is stable across renders.
      var seeded = (Math.sin(i * 12.9898) * 43758.5453) % 1;
      seeded = seeded < 0 ? seeded + 1 : seeded;
      if (mode === "full") {
        level = seeded > 0.86 ? 4 : seeded > 0.68 ? 3 : seeded > 0.45 ? 2 : seeded > 0.22 ? 1 : 0;
      } else if (i >= tail && seeded > 0.32) {
        level = 3 + (seeded > 0.66 ? 1 : 0);
      }
      cell.style.background = "var(" + vars[level] + ")";
      cell.style.animationDelay = reduceMotion ? "0ms" : i * (mode === "full" ? 3 : 5) + "ms";
      el.appendChild(cell);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("themeToggle");
    if (toggle) toggle.addEventListener("click", toggleTheme);
    wireForm();
    buildGraph();
  });
})();
