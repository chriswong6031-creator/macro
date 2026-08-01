/* Accountable AI-JUDGMENT panel — fetches site/stockdata/ai_desk_notes.json (the top-pick
   leans written by engine/stock_desk.py) + ai_desk_track.json (the graded track record).
   Shows the CHECKABLE lean for a name ONLY if it's a covered top pick (panel stays hidden
   otherwise). HONEST: the cross-sectional rank has no validated forward edge — the lean is a
   fallible, scored conditional, never a size, never alpha. All model output is escaped before
   insertion. Bilingual chrome (model prose stays English); re-renders on 'langchange'.
   Exposes window.loadAiLean(ticker), called by stock.html's load(). */
(function () {
  var NOTES = null, TRACK = null, CUR = null, FETCHED = false;
  var LBL = {
    en: { head: "AI judgment", why: "Why", bear: "Bear case", fals: "Changes this read",
          by: "check by", track: "AI track record", scored: "scored", hit: "hit-rate",
          none: "no leans scored yet — provisional",
          foot: "Accountable, checkable lean vs SPY — graded against reality. The board's "
              + "rank has no validated forward edge; this is accountability, not alpha. Never a size.",
          leans: { constructive: "Constructive", neutral: "Neutral", cautious: "Cautious", avoid: "Avoid" },
          conv: { low: "low", medium: "medium", high: "high" } },
    zh: { head: "AI 研判", why: "理由", bear: "看空理由", fals: "改判条件",
          by: "复核日期", track: "AI 战绩", scored: "已评", hit: "命中率",
          none: "暂无已评判断 — 暂定",
          foot: "相对标普500的可问责、可检验判断 — 接受现实检验。榜单排名无经验证的前瞻优势；"
              + "这是问责机制，而非阿尔法。从不给出仓位。",
          leans: { constructive: "建设性", neutral: "中性", cautious: "谨慎", avoid: "回避" },
          conv: { low: "低", medium: "中", high: "高" } },
  };
  function esc(s) { var d = document.createElement("div"); d.textContent = (s == null ? "" : String(s)); return d.innerHTML; }
  function escAttr(s) { return esc(s).replace(/"/g, "&quot;"); }   // quote-safe for HTML attributes
  function curLang() { return document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"; }

  function render() {
    var panel = document.getElementById("ai-lean");
    var body = document.getElementById("ai-lean-body");
    if (!panel || !body) return;
    var n = (NOTES && CUR && NOTES.by_ticker) ? NOTES.by_ticker[CUR] : null;
    if (!n || !n.lean) { panel.style.display = "none"; return; }   // not a covered pick -> hidden
    var lang = curLang(), t = LBL[lang];
    var lean = String(n.lean).toLowerCase();
    var leanLabel = (t.leans[lean] || n.lean);
    var conv = t.conv[String(n.conviction).toLowerCase()] || n.conviction;
    var h = '<div class="aj-top">'
      + '<span class="aj-chip ' + escAttr(lean) + '">' + esc(leanLabel) + "</span>"
      + '<span class="aj-meta">' + esc(conv) + " · " + esc(n.horizon_d || "?") + "d";
    if (n.check_by) h += " · " + esc(t.by) + " " + esc(n.check_by);
    h += "</span></div>";
    if (n.thesis) h += '<div class="aj-sec"><span class="aj-h">' + esc(t.why) + ":</span> " + esc(n.thesis) + "</div>";
    if (n.dissent) h += '<div class="aj-sec aj-bear"><span class="aj-h">' + esc(t.bear) + ":</span> " + esc(n.dissent) + "</div>";
    var fals = n.falsifier && n.falsifier.text;
    if (fals) h += '<div class="aj-sec"><span class="aj-h">' + esc(t.fals) + ":</span> " + esc(fals) + "</div>";
    // track-record footer (accountability)
    var tr = TRACK && TRACK.overall;
    var trLine;
    if (tr && tr.n) {
      trLine = esc(t.track) + ": " + esc(tr.n) + " " + esc(t.scored) + " · " + esc(t.hit) + " " + esc(tr.hit_rate);
    } else { trLine = esc(t.track) + ": " + esc(t.none); }
    h += '<p class="aj-foot">📊 ' + trLine + " · " + esc(t.foot) + "</p>";
    body.innerHTML = h;
    panel.style.display = "";
  }

  function ensure(cb) {
    if (FETCHED) { cb(); return; }
    FETCHED = true;
    var a = fetch("stockdata/ai_desk_notes.json?_=" + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    var b = fetch("stockdata/ai_desk_track.json?_=" + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    Promise.all([a, b]).then(function (res) { NOTES = res[0]; TRACK = res[1]; cb(); });
  }

  // Called with the RAW ticker (e.g. CASY) — the key stock_desk uses in by_ticker.
  window.loadAiLean = function (ticker) {
    var panel = document.getElementById("ai-lean");
    if (panel) panel.style.display = "none";
    CUR = ticker;
    ensure(render);
  };
  document.addEventListener("langchange", render);
})();
