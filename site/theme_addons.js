/* Theme Rotation Desk ADD-ONS renderer — "Rotation context" (display-only).
 *
 * Three plain-language context panels that sit beside the Theme Rotation Desk, each built
 * from the JSON the standalone build emits (basketdata/vol_sentiment.json, etf_pulse.json,
 * theme_extension*.json):
 *   - Volatility & sentiment  : vol-regime + CBOE put/call chip
 *   - ETF rotation            : style / risk-on-off / sector leadership strips
 *   - Theme stretch           : per-theme ATR extension above the 50-day trend (overbought read)
 * Bilingual via the site's .l-en/.l-zh spans. Pure render; nothing here is scored.
 *
 *   renderThemeAddons({ base:'basketdata/', region:'us', mount:'#theme-addons' })
 */
(function () {
  "use strict";

  function bi(en, zh) {
    var z = (zh == null || zh === "") ? en : zh;
    return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(z) + "</span>";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function pct(x, d) { return x == null ? "—" : (x > 0 ? "+" : "") + Number(x).toFixed(d == null ? 2 : d) + "%"; }
  function num(x, d) { return x == null ? "—" : Number(x).toFixed(d == null ? 2 : d); }
  function toneVar(t) {
    return { pos: "var(--up)", neg: "var(--down)", warn: "var(--warn)", neu: "var(--muted)" }[t] || "var(--muted)";
  }
  function signColor(x) { return x == null ? "var(--muted)" : x > 0 ? "var(--up)" : x < 0 ? "var(--down)" : "var(--muted)"; }

  function fetchJSON(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  // a titled section wrapper so each context block reads as its own card (not a wall of text)
  function sect(icon, titleEn, titleZh, hintEn, hintZh, body) {
    if (!body) return "";
    return '<section class="ta-sect">' +
      '<div class="ta-h"><span class="ta-ico">' + icon + "</span>" + bi(titleEn, titleZh) +
      (hintEn ? '<span class="ta-hint">' + bi(hintEn, hintZh) + "</span>" : "") + "</div>" +
      body + "</section>";
  }

  // ---- Volatility & sentiment : vol-regime + put/call chip -----------------
  function renderVol(vs) {
    if (!vs || (!vs.vol_regime && !vs.put_call)) return "";
    var v = vs.vol_regime, pc = vs.put_call, out = [];
    if (v) {
      out.push(
        '<span class="ta-badge" style="background:' + toneVar(v.tone) + '">' + bi(v.label_en, v.label_zh) + "</span>" +
        '<span class="ta-kv">VIX <b>' + num(v.vix, 1) + "</b> · " + bi("pctile", "百分位") + " <b>" +
        (v.vix_pctile == null ? "—" : Math.round(v.vix_pctile * 100) + "%") + "</b></span>" +
        '<span class="ta-kv">' + bi("term", "期限") + " <b>" + esc(v.term_state || "—") + "</b></span>" +
        (v.vrp_state ? '<span class="ta-kv">VRP <b>' + esc(v.vrp_state) + "</b></span>" : "")
      );
    }
    if (pc) {
      out.push(
        '<span class="ta-kv">' + bi("put/call", "看跌/看涨") + " <b>" + num(pc.equity_pc, 2) + "</b> " +
        '<em>' + bi(pc.sentiment_en, pc.sentiment_zh) + "</em>" +
        (pc.young ? ' <span class="ta-young" title="short history">' + bi("young series", "数据较短") + "</span>" : "") +
        "</span>"
      );
    }
    return sect("🌡️", "Volatility & sentiment", "波动率与情绪",
      "how nervous the tape is right now", "当前市场紧张程度",
      '<div class="ta-chip-row">' + out.join("") + "</div>");
  }

  // ---- ETF rotation : style / risk / sector --------------------------------
  function renderPulse(ep) {
    if (!ep) return "";
    var h = [];
    if (ep.style && ep.style.length) {
      h.push('<div class="ta-lead">' + bi("Style", "风格") + ' <span class="ta-dim">' + bi("20d ratio Δ", "20日比值Δ") + "</span></div>");
      h.push('<div class="ta-strip">' + ep.style.map(function (s) {
        return '<span class="ta-pill"><b>' + esc(s.pair) + "</b> " +
          '<span style="color:' + signColor(s.chg_20d) + '">' + pct(s.chg_20d) + "</span> " +
          '<em>' + bi(s.lead_en, s.lead_zh) + "</em></span>";
      }).join("") + "</div>");
    }
    if (ep.risk) {
      var r = ep.risk;
      h.push('<div class="ta-lead">' + bi("Risk-on / off", "风险偏好") +
        ' <span class="ta-badge sm" style="background:' + (r.tilt > 0.15 ? "var(--up)" : r.tilt < -0.15 ? "var(--down)" : "var(--muted)") + '">' +
        bi(r.label_en, r.label_zh) + "</span></div>");
      h.push('<div class="ta-strip">' + (r.legs || []).map(function (l) {
        return '<span class="ta-pill"><b>' + esc(l.pair) + "</b> " + bi(l.label_en, l.label_zh) +
          ' <span style="color:' + signColor(l.chg_20d) + '">' + pct(l.chg_20d) + "</span></span>";
      }).join("") + "</div>");
    }
    if (ep.sector && ep.sector.rows) {
      h.push('<div class="ta-lead">' + bi("Sector leadership", "行业领先") + ' <span class="ta-dim">' + bi("60d momentum vs SPY", "相对SPY的60日动量") + "</span></div>");
      h.push('<div class="ta-strip">' + ep.sector.rows.map(function (s, i) {
        var lead = i < 3, lag = i >= ep.sector.rows.length - 3;
        return '<span class="ta-pill ' + (lead ? "ta-lead-p" : lag ? "ta-lag" : "") + '" title="' + esc(s.label_en) + ' · pctile ' + num(s.pctile_252d, 0) + '">' +
          "<b>" + esc(s.ticker) + "</b> " +
          '<span style="color:' + signColor(s.mom_60d) + '">' + pct(s.mom_60d, 1) + "</span></span>";
      }).join("") + "</div>");
    }
    return sect("🔁", "ETF rotation", "ETF 轮动",
      "which styles, risk legs and sectors money is favouring", "资金正在偏好的风格、风险与行业",
      h.join(""));
  }

  // ---- Theme stretch : per-theme ATR extension above the 50-day trend ------
  function renderExt(te) {
    if (!te || !te.themes || !te.themes.length) return "";
    var maxAbs = Math.max(2, Math.max.apply(null, te.themes.map(function (t) { return Math.abs(t.atr_ext || 0); })));
    // sort most-stretched first so the overbought themes read at the top
    var rows = te.themes.slice().sort(function (a, b) { return (b.atr_ext || 0) - (a.atr_ext || 0); }).map(function (t) {
      var v = t.atr_ext || 0;
      var w = Math.min(50, Math.abs(v) / maxAbs * 50);   // half-track %, diverging from the centre
      var col = toneVar(t.tone);
      var left = v >= 0 ? 50 : (50 - w);
      var bar = '<span class="ta-dbar"><i class="ta-zero"></i>' +
        '<i class="ta-fill" style="left:' + left.toFixed(1) + "%;width:" + w.toFixed(1) + "%;background:" + col + '"></i></span>';
      return '<div class="ta-ext-row">' +
        '<span class="ta-ext-name">' + bi(t.name, t.name_zh) + "</span>" +
        bar +
        '<span class="ta-ext-val" style="color:' + col + '">' + (v >= 0 ? "+" : "") + num(v, 1) + "σ</span>" +
        '<span class="ta-ext-band" style="color:' + col + '">' + bi(t.band_en, t.band_zh) + "</span>" +
        '<span class="ta-dim ta-ext-par">' + (t.pct_parabolic ? Math.round(t.pct_parabolic * 100) + "% " + bi("parabolic", "抛物") : "") + "</span>" +
        "</div>";
    }).join("");
    var explain = bi(
      "Median stock's stretch above (or below) its 50-day trend, in ATR — higher = more overbought and pullback-prone. A heat gauge, not a buy/sell signal.",
      "各主题中位数个股相对 50 日趋势的延展幅度（以 ATR 计）。数值越高越超买、越易回调。这是过热温度计，并非买卖信号。");
    return sect("📏", "Theme stretch", "主题延展", null, null,
      '<p class="ta-explain">' + explain + "</p>" +
      '<div class="ta-scale"><span>' + bi("below trend", "趋势下方") + "</span><span>" + bi("on trend", "趋于趋势") +
      "</span><span>" + bi("overbought →", "超买 →") + "</span></div>" +
      '<div class="ta-ext">' + rows + "</div>");
  }

  // ---- Within-theme leaders : leader (extended WITH theme) vs chase (beyond it) -----
  function renderMembers(mc) {
    if (!mc || !mc.themes || !mc.themes.length) return "";
    // lead with the themes that have actually run hot AND carry something actionable to show
    var hot = mc.themes.filter(function (t) {
      return t.hot && (t.n_leaders || t.n_beyond || t.n_catchup);
    }).slice(0, 8);
    if (!hot.length) return "";
    function pill(m) {
      var col = toneVar(m.tone);
      var rel = m.ext_rel == null ? "" : (m.ext_rel >= 0 ? "+" : "") + num(m.ext_rel, 1) + "pp vs theme median";
      var rs = m.rs_rank == null ? "" : " · 20d RS " + Math.round(m.rs_rank * 100) + "%ile in theme";
      var rsf = m.rs_fast_rank == null ? "" : " · 10d RS " + Math.round(m.rs_fast_rank * 100) + "%ile";
      var cls = m.band === "leader" ? "ta-mc-lead" : m.band === "catch_up" ? "ta-mc-catch"
        : m.band === "beyond" ? "ta-mc-chase" : "";
      return '<span class="ta-pill ' + cls + '" title="' + esc(rel + rs + rsf) + '">' +
        "<b>" + esc(m.ticker) + "</b> " +
        '<span style="color:' + col + '">' + (m.ext == null ? "—" : (m.ext >= 0 ? "+" : "") + num(m.ext, 0) + "%") + "</span> " +
        '<em>' + bi(m.band_en, m.band_zh) + "</em></span>";
    }
    var blocks = hot.map(function (t) {
      var mem = t.members || [];
      // actionable first: leaders you can time + laggards turning up (the rotation entry when the
      // leaders are gone); then the capped chase list; then a few mid-pack extended names.
      var leaders = mem.filter(function (m) { return m.band === "leader"; });
      var catchup = mem.filter(function (m) { return m.band === "catch_up"; });
      var beyond = mem.filter(function (m) { return m.band === "beyond"; });
      var ext = mem.filter(function (m) { return m.band === "extended"; });
      var BC = 6, shownBeyond = beyond.slice(0, BC);
      var pills = leaders.map(pill).join("") + catchup.map(pill).join("") + shownBeyond.map(pill).join("") +
        (beyond.length > BC ? '<span class="ta-pill ta-mc-more">+' + (beyond.length - BC) + " " + bi("more chasing", "更多追高") + "</span>" : "") +
        ext.slice(0, 3).map(pill).join("");
      var sub = [];
      if (t.n_leaders) sub.push(t.n_leaders + " " + bi("lead", "领涨"));
      if (t.n_catchup) sub.push(t.n_catchup + " " + bi("turning up", "转强"));
      if (t.n_beyond) sub.push(t.n_beyond + " " + bi("chasing", "追高"));
      return '<div class="ta-mc-theme"><div class="ta-mc-h"><b>' + bi(t.name, t.name_zh) + "</b>" +
        '<span class="ta-dim"> · ' + bi("typical", "典型") + " " + (t.median_ext >= 0 ? "+" : "") + num(t.median_ext, 0) + "% " +
        bi("over 200d", "高于200日") + (sub.length ? " · " + sub.join(" · ") : "") + "</span></div>" +
        '<div class="ta-strip">' + pills + "</div></div>";
    }).join("");
    var explain = bi(
      "When a theme runs hot the whole basket is extended. This splits the names: a LEADER is extended in line with its theme and leads it on relative strength — wait for a pullback, don't veto it; a name flagged CHASING is stretched far beyond its cohort; a TURNING-UP laggard lagged the theme but its relative strength has turned up over 10 days, with room left. Cohort context only — never scored.",
      "主题走热时整个篮子都在延展。本面板区分个股：领涨股与主题同步延展、相对强度领先 —— 等回调、勿否决；被标记为追高的个股远超同侪；转强的落后股此前跑输、但近10日相对强度已转升且仍有空间。仅为同侪背景，从不计分。");
    return sect("🏁", "Within-theme leaders", "主题内领涨", null, null,
      '<p class="ta-explain">' + explain + "</p>" +
      '<div class="ta-mc-legend"><span class="ta-mc-key ta-mc-lead">' + bi("leader · wait for pullback", "领涨 · 等回调") +
      '</span><span class="ta-mc-key ta-mc-catch">' + bi("turning up · catch-up laggard", "转强 · 补涨落后股") +
      '</span><span class="ta-mc-key ta-mc-chase">' + bi("chasing · extended beyond theme", "追高 · 超出主题") + "</span></div>" +
      '<div class="ta-mc">' + blocks + "</div>");
  }

  function STYLE() {
    return '<style>' +
      "#theme-addons .ta-sect{border-top:1px solid var(--line);padding:13px 0 4px;margin-top:4px}" +
      "#theme-addons .ta-sect:first-of-type{border-top:0}" +
      "#theme-addons .ta-h{display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:13.5px;font-weight:700;margin:0 0 9px}" +
      "#theme-addons .ta-ico{font-size:14px}" +
      "#theme-addons .ta-hint{font-weight:400;color:var(--muted);font-size:11.5px}" +
      "#theme-addons .ta-chip-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:2px 0}" +
      "#theme-addons .ta-badge{color:#fff;font-weight:700;font-size:11px;padding:2px 8px;border-radius:6px;letter-spacing:.3px}" +
      "#theme-addons .ta-badge.sm{font-size:10px;padding:1px 6px}" +
      "#theme-addons .ta-kv{font-size:12px;color:var(--muted)}#theme-addons .ta-kv b{color:var(--text)}" +
      "#theme-addons .ta-kv em{color:var(--muted);font-style:normal}" +
      "#theme-addons .ta-young{font-size:10px;color:var(--orange);border:1px solid var(--line);border-radius:4px;padding:0 4px}" +
      "#theme-addons .ta-lead{font-size:11.5px;font-weight:650;margin:10px 0 5px;color:var(--text);display:flex;align-items:center;gap:7px}" +
      "#theme-addons .ta-lead:first-child{margin-top:0}" +
      "#theme-addons .ta-dim{font-weight:400;color:var(--muted);font-size:11px}" +
      "#theme-addons .ta-strip{display:flex;flex-wrap:wrap;gap:6px}" +
      "#theme-addons .ta-pill{font-size:11.5px;border:1px solid var(--line);background:var(--panel2);border-radius:6px;padding:3px 8px;white-space:nowrap}" +
      "#theme-addons .ta-pill b{color:var(--text)}#theme-addons .ta-pill em{color:var(--muted);font-style:normal}" +
      "#theme-addons .ta-pill.ta-lead-p{border-color:var(--up)}#theme-addons .ta-pill.ta-lag{border-color:var(--down);opacity:.85}" +
      "#theme-addons .ta-explain{font-size:11.5px;color:var(--muted);line-height:1.55;margin:0 0 9px;max-width:95ch}" +
      "#theme-addons .ta-scale{display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin:0 0 4px;padding:0 2px}" +
      "#theme-addons .ta-ext{display:flex;flex-direction:column;gap:4px}" +
      "#theme-addons .ta-ext-row{display:grid;grid-template-columns:minmax(110px,1.3fr) 2fr 52px 92px auto;gap:9px;align-items:center;font-size:12px}" +
      "#theme-addons .ta-ext-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
      "#theme-addons .ta-dbar{position:relative;display:block;height:9px;background:var(--panel2);border-radius:4px;overflow:hidden}" +
      "#theme-addons .ta-zero{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line)}" +
      "#theme-addons .ta-fill{position:absolute;top:0;bottom:0;border-radius:3px}" +
      "#theme-addons .ta-ext-val{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}" +
      "#theme-addons .ta-ext-band{font-size:11px;font-weight:600}" +
      "#theme-addons .ta-mc{display:flex;flex-direction:column;gap:11px}" +
      "#theme-addons .ta-mc-h{font-size:12px;margin:0 0 5px}#theme-addons .ta-mc-h b{color:var(--text)}" +
      "#theme-addons .ta-pill.ta-mc-more{color:var(--muted);border-style:dashed}" +
      "#theme-addons .ta-mc-legend{display:flex;flex-wrap:wrap;gap:14px;margin:0 0 9px;font-size:11px;color:var(--muted)}" +
      "#theme-addons .ta-mc-key{display:inline-flex;align-items:center;gap:5px}" +
      "#theme-addons .ta-mc-key::before{content:'';width:9px;height:9px;border-radius:2px;border:1.5px solid var(--line)}" +
      "#theme-addons .ta-mc-key.ta-mc-lead::before{border-color:var(--up)}" +
      "#theme-addons .ta-mc-key.ta-mc-catch::before{border-color:var(--link)}" +
      "#theme-addons .ta-mc-key.ta-mc-chase::before{border-color:var(--down)}" +
      "#theme-addons .ta-pill.ta-mc-lead{border-color:var(--up)}" +
      "#theme-addons .ta-pill.ta-mc-catch{border-color:var(--link)}" +
      "#theme-addons .ta-pill.ta-mc-chase{border-color:var(--down)}" +
      "@media(max-width:640px){#theme-addons .ta-ext-row{grid-template-columns:minmax(84px,1.2fr) 1.5fr 44px 70px}#theme-addons .ta-ext-par{display:none}}" +
      "</style>";
  }

  window.renderThemeAddons = function (opts) {
    opts = opts || {};
    var base = opts.base || "basketdata/";
    var region = opts.region || "us";
    var mount = document.querySelector(opts.mount || "#theme-addons");
    if (!mount) return;
    var suffix = (region === "us" ? "" : "_" + region) + ".json";
    Promise.all([
      fetchJSON(base + "vol_sentiment.json"),
      fetchJSON(base + "etf_pulse.json"),
      fetchJSON(base + "theme_extension" + suffix),
      fetchJSON(base + "member_context" + suffix),
    ]).then(function (res) {
      var vs = res[0], ep = res[1], te = res[2], mc = res[3];
      if (!vs && !ep && !te && !mc) { mount.style.display = "none"; return; }
      var asof = (ep && ep.as_of) || (vs && vs.as_of) || (te && te.as_of) || (mc && mc.as_of) || "";
      mount.innerHTML = STYLE() +
        '<h2 style="margin:0 0 4px"><span class="idx">00B</span>' +
        bi("⚡ Rotation context", "⚡ 轮动背景") +
        ' <span class="chip">' + bi("display-only", "仅展示") + "</span>" +
        (asof ? ' <span class="ta-dim" style="font-weight:400">' + esc(asof) + "</span>" : "") + "</h2>" +
        '<p class="ta-dim" style="margin:0 0 4px;max-width:95ch">' +
        bi("The tape context beside the Theme Rotation Desk — how jumpy volatility is, where ETF money is rotating, and how stretched each theme has become. Background only, never scored.",
           "主题轮动台旁的市场背景 — 波动率是否紧张、ETF 资金在向何处轮动、各主题延展到何种程度。仅作背景，从不计分。") + "</p>" +
        renderVol(vs) + renderPulse(ep) + renderMembers(mc) + renderExt(te);
      mount.style.display = "";
    });
  };
})();
