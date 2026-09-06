/* F08 reference sheets — theme + language toggle ONLY.
   Mockup tier. No product behaviour lives here: these sheets fix composition,
   hierarchy and state vocabulary, not interaction.

   Both attributes are also readable from the query string (?theme=light&lang=zh)
   so the four evidence quadrants (dark/light x EN/ZH) can be captured headless
   without scripting a click. Nothing else in this file touches the DOM. */
(function () {
  var d = document.documentElement;
  var q = new URLSearchParams(location.search);
  var theme = q.get("theme") === "light" ? "light" : "dark";
  var lang = q.get("lang") === "zh" ? "zh" : "en";
  d.setAttribute("data-theme", theme);
  d.setAttribute("data-lang", lang);

  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-toggle]");
    if (!t) return;
    if (t.getAttribute("data-toggle") === "theme") {
      d.setAttribute("data-theme", d.getAttribute("data-theme") === "light" ? "dark" : "light");
    } else {
      d.setAttribute("data-lang", d.getAttribute("data-lang") === "zh" ? "en" : "zh");
    }
  });
})();
