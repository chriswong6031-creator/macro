/* AI Desk renderer — fetches ai_desk.json (written by engine/ai_desk.py) and builds
   the desk note client-side: track-record badge, falsifiable theses, the analyst
   panel, and recent graded outcomes. Labels are bilingual (l-en/l-zh; theme.js
   toggles); the AI-authored content is shown as-is. Resilient: any missing field
   degrades to a muted note, never throws. */
(function () {
  "use strict";
  var root = document.getElementById("desk-root");
  if (!root) return;
  var src = root.getAttribute("data-src") || "ai_desk.json";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function bi(en, zh) {  // bilingual label
    return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' +
      esc(zh || en) + "</span>";
  }
  function pct(x) { return (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%"; }

  var LEAN = {
    overweight: { cls: "ow", en: "overweight", zh: "超配" },
    underweight: { cls: "uw", en: "underweight", zh: "低配" },
    avoid: { cls: "avoid", en: "avoid", zh: "回避" },
    "fade-fear": { cls: "fade", en: "fade fear", zh: "淡化恐慌" }
  };

  function checkText(c) {
    if (!c) return bi("not machine-scorable", "无法机械打分");
    if (c.kind === "rel_return") {
      var thr = (c.threshold * 100).toFixed(0) + "%";
      return esc(c.subject_ticker) + " vs " + esc(c.vs) + " · " +
        bi("read changes if relative return " + c.op + " " + thr + " over " + c.horizon_d + "d",
           "若 " + c.horizon_d + "日相对收益 " + c.op + " " + thr + " 则改判");
    }
    if (c.kind === "level") {
      return esc(c.subject_ticker) + " · " +
        bi("read changes on a new high above entry within " + c.horizon_d + "d",
           "若 " + c.horizon_d + "日内创出高于入场的新高则改判");
    }
    return bi("not machine-scorable (soft)", "无法机械打分（软）");
  }

  function thesisCard(t) {
    var L = LEAN[t.lean] || { cls: "conv", en: t.lean, zh: t.lean };
    var h = '<div class="thesis">';
    h += '<div class="thesis-head"><span class="thesis-subj">' + esc(t.subject) + "</span>";
    h += '<span class="chip ' + L.cls + '">' + bi(L.en, L.zh) + "</span>";
    h += '<span class="chip conv">' + bi("conviction " + esc(t.conviction), "信心 " + esc(t.conviction)) + "</span>";
    h += '<span class="chip conv">' + esc(t.horizon_d) + "d</span></div>";
    if (t.thesis) h += '<div class="body">' + esc(t.thesis) + "</div>";
    if (t.evidence && t.evidence.length) {
      h += '<div class="row"><span class="k">' + bi("Evidence", "依据") + "</span><ul class=\"ev\">";
      t.evidence.forEach(function (e) { h += "<li>" + esc(e) + "</li>"; });
      h += "</ul></div>";
    }
    if (t.dissent) h += '<div class="dissent"><span class="k">' + bi("Dissent", "异议") + "</span> " + esc(t.dissent) + "</div>";
    var f = t.falsifier || {};
    h += '<div class="fals"><span class="k">' + bi("Changes this read", "改判条件") + "</span> " +
      esc(f.text || "") + '<div class="mono" style="margin-top:4px">' + checkText(f.check) +
      (t.check_by ? " · " + bi("check by ", "检验日 ") + esc(t.check_by) : "") + "</div></div>";
    h += "</div>";
    return h;
  }

  function trackBadge(tr) {
    var h = '<div class="panel"><h2>📊 ' + bi("Desk track record", "交易台战绩") + "</h2>";
    if (!tr || !tr.overall || tr.scored_total === 0 || tr.overall.n === 0) {
      h += '<p class="muted sm" style="margin:4px 0 0">' +
        esc((tr && tr.calibration_note) ||
          "No theses scored yet — the track record begins once the first check-by dates pass.") +
        "</p>";
      if (tr) h += '<p class="muted sm" style="margin:6px 0 0">' +
        bi("open: ", "进行中：") + esc(tr.open || 0) + " · " +
        bi("unscored: ", "未打分：") + esc(tr.unscored_soft || 0) + "</p>";
      return h + "</div>";
    }
    var ov = tr.overall;
    h += '<div class="tr-grid">';
    h += '<div class="tr-cell"><div class="v">' + (ov.hit_rate != null ? (ov.hit_rate * 100).toFixed(0) + "%" : "—") +
      '</div><div class="l">' + bi("holding", "成立率") + " (" + ov.hits + "/" + ov.n + ")</div></div>";
    h += '<div class="tr-cell"><div class="v">' + (ov.dir_accuracy != null ? (ov.dir_accuracy * 100).toFixed(0) + "%" : "—") +
      '</div><div class="l">' + bi("directional", "方向正确率") + "</div></div>";
    ["high", "medium", "low"].forEach(function (c) {
      var b = (tr.by_conviction || {})[c];
      if (b && b.n) h += '<div class="tr-cell"><div class="v">' + (b.hit_rate * 100).toFixed(0) +
        '%</div><div class="l">' + esc(c) + " (" + b.hits + "/" + b.n + ")</div></div>";
    });
    h += "</div>";
    if (tr.calibration_note) h += '<p class="muted sm" style="margin:8px 0 0">' + esc(tr.calibration_note) + "</p>";
    if (tr.recent && tr.recent.length) {
      h += '<details class="panel-acc" style="margin-top:10px"><summary>' +
        bi("Recent graded calls", "近期已打分") + "</summary><table class=\"rec\"><tr><th>" +
        bi("Subject", "标的") + "</th><th>" + bi("Lean", "倾向") + "</th><th>" +
        bi("Conviction", "信心") + "</th><th>" + bi("Outcome", "结果") + "</th><th>" +
        bi("Realized", "实际") + "</th></tr>";
      tr.recent.forEach(function (r) {
        var oc = r.outcome === "hit" ? "out-hit" : (r.outcome === "miss" ? "out-miss" : "out-open");
        h += "<tr><td>" + esc(r.subject) + "</td><td>" + esc(r.lean) + "</td><td>" +
          esc(r.conviction) + '</td><td class="' + oc + '">' + esc(r.outcome) + "</td><td>" +
          (r.realized != null ? pct(r.realized) : "—") + "</td></tr>";
      });
      h += "</table></details>";
    }
    return h + "</div>";
  }

  function panelAccordion(panel) {
    var keys = ["opportunity", "skeptic", "base_rate", "structural"];
    var labels = { opportunity: ["Opportunity", "机会派"], skeptic: ["Skeptic", "怀疑派"],
      base_rate: ["Base-rate", "基率派"], structural: ["Structural", "结构派"] };
    var present = keys.filter(function (k) { return panel && panel[k]; });
    if (!present.length) return "";
    var h = '<div class="panel"><details class="panel-acc"><summary>🧑‍⚖️ ' +
      bi("What the analyst panel argued", "分析师小组的论点") + " (" + present.length + ")</summary>";
    present.forEach(function (k) {
      var s = panel[k] || {};
      h += '<div class="stance"><div class="role">' + bi(labels[k][0], labels[k][1]) + "</div>";
      if (s.stance) h += "<div>" + esc(s.stance) + "</div>";
      if (s.candidates && s.candidates.length) {
        h += '<div class="sm" style="margin-top:4px">';
        s.candidates.forEach(function (c) {
          if (!c || c.lean === "none" || !c.subject) return;
          h += "• " + esc(c.subject) + " " + esc(c.lean) +
            (c.strength ? " (" + esc(c.strength) + ")" : "") + "<br>";
        });
        h += "</div>";
      }
      if (s.key_risk) h += '<div class="risk">' + bi("Key risk: ", "主要风险：") + esc(s.key_risk) + "</div>";
      h += "</div>";
    });
    return h + "</details></div>";
  }

  function render(d) {
    var html = "";
    html += trackBadge(d.track_record);
    if (d.regime_context) {
      html += '<div class="panel"><h2>🧭 ' + bi("Regime context", "周期背景") + "</h2><div>" +
        esc(d.regime_context) + "</div>";
      var sv = d.source_verdicts || {};
      var bits = [];
      if (sv.flow) bits.push("flow: " + esc(sv.flow));
      if (sv.regime_snap) bits.push("regime-snap: " + esc(sv.regime_snap));
      html += '<p class="muted sm mono" style="margin:8px 0 0">' +
        bi("confidence ", "信心 ") + esc(d.confidence || "low") +
        (bits.length ? " · " + bits.join(" · ") : "") + "</p></div>";
    }
    var theses = d.theses || [];
    html += '<div class="panel"><h2>🎯 ' + bi("Conditional leans", "条件性倾向") + " (" + theses.length + ")</h2>";
    if (!theses.length) {
      html += '<p class="muted sm">' + bi("No actionable leans today — honesty over content.",
        "今日无可执行倾向 — 诚实优先于内容。") + "</p>";
    } else {
      theses.forEach(function (t) { html += thesisCard(t); });
    }
    html += "</div>";
    html += panelAccordion(d.panel);
    root.innerHTML = html;
  }

  function degraded(msg) {
    root.innerHTML = '<div class="panel muted sm">' +
      bi("AI desk note unavailable right now — it regenerates daily after the close.",
        "AI 交易台笔记暂不可用 — 每个交易日收盘后更新。") +
      (msg ? ' <span class="mono">(' + esc(msg) + ")</span>" : "") + "</div>";
  }

  fetch(src, { cache: "no-store" }).then(function (r) {
    if (!r.ok) throw new Error("http " + r.status);
    return r.json();
  }).then(function (d) {
    if (!d || (d.degraded_reason && !(d.theses && d.theses.length) && !d.regime_context)) {
      degraded(d && d.degraded_reason);
    } else {
      render(d);
    }
  }).catch(function (e) { degraded(e && e.message); });
})();
