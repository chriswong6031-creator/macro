/* Theme Rotation Desk ADD-ONS renderer (display-only).
 *
 * Renders three context panels from the JSON the standalone build emits
 * (basketdata/etf_pulse.json, vol_sentiment.json, theme_extension*.json):
 *   - a vol-regime + CBOE put/call chip
 *   - an ETF Pulse strip (style / risk / sector rotation)
 *   - a per-theme ATR "too hot" extension list
 * Bilingual via the site's .l-en/.l-zh spans. Used by both the standalone preview page
 * and (via templates/_theme_addons.html.j2) the baskets page. Pure render; no scoring.
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

  // ---- vol-regime + put/call chip -----------------------------------------
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
        '<em style="color:var(--muted)">' + bi(pc.sentiment_en, pc.sentiment_zh) + "</em>" +
        (pc.young ? ' <span class="ta-young" title="short history">' + bi("young series", "数据较短") + "</span>" : "") +
        "</span>"
      );
    }
    return '<div class="ta-chip-row">' + out.join("") + "</div>";
  }

  // ---- ETF pulse: style / risk / sector ------------------------------------
  function renderPulse(ep) {
    if (!ep) return "";
    var h = [];
    if (ep.style && ep.style.length) {
      h.push('<div class="ta-sub">' + bi("Style rotation", "风格轮动") + ' <span class="ta-dim">' + bi("20d ratio Δ", "20日比值Δ") + "</span></div>");
      h.push('<div class="ta-strip">' + ep.style.map(function (s) {
        return '<span class="ta-pill"><b>' + esc(s.pair) + "</b> " +
          '<span style="color:' + signColor(s.chg_20d) + '">' + pct(s.chg_20d) + "</span> " +
          '<em>' + bi(s.lead_en, s.lead_zh) + "</em></span>";
      }).join("") + "</div>");
    }
    if (ep.risk) {
      var r = ep.risk;
      h.push('<div class="ta-sub">' + bi("Risk pulse", "风险脉搏") +
        ' <span class="ta-badge" style="background:' + (r.tilt > 0.15 ? "var(--up)" : r.tilt < -0.15 ? "var(--down)" : "var(--muted)") + '">' +
        bi(r.label_en, r.label_zh) + "</span></div>");
      h.push('<div class="ta-strip">' + (r.legs || []).map(function (l) {
        return '<span class="ta-pill"><b>' + esc(l.pair) + "</b> " + bi(l.label_en, l.label_zh) +
          ' <span style="color:' + signColor(l.chg_20d) + '">' + pct(l.chg_20d) + "</span></span>";
      }).join("") + "</div>");
    }
    if (ep.sector && ep.sector.rows) {
      h.push('<div class="ta-sub">' + bi("Sector rotation", "行业轮动") + ' <span class="ta-dim">' + bi("RS, 60d mom vs SPY", "相对强度，60日动量") + "</span></div>");
      h.push('<div class="ta-strip">' + ep.sector.rows.map(function (s, i) {
        var lead = i < 3, lag = i >= ep.sector.rows.length - 3;
        return '<span class="ta-pill ' + (lead ? "ta-lead" : lag ? "ta-lag" : "") + '" title="' + esc(s.label_en) + ' · pctile ' + num(s.pctile_252d, 0) + '">' +
          "<b>" + esc(s.ticker) + "</b> " +
          '<span style="color:' + signColor(s.mom_60d) + '">' + pct(s.mom_60d, 1) + "</span></span>";
      }).join("") + "</div>");
    }
    return h.join("");
  }

  // ---- per-theme ATR extension --------------------------------------------
  function renderExt(te) {
    if (!te || !te.themes || !te.themes.length) return "";
    var max = Math.max(5, Math.max.apply(null, te.themes.map(function (t) { return Math.abs(t.atr_ext || 0); })));
    var rows = te.themes.map(function (t) {
      var w = Math.min(100, Math.abs(t.atr_ext || 0) / max * 100);
      var col = toneVar(t.tone);
      return '<div class="ta-ext-row">' +
        '<span class="ta-ext-name">' + bi(t.name, t.name_zh) + "</span>" +
        '<span class="ta-ext-bar"><span style="width:' + w.toFixed(0) + "%;background:" + col + '"></span></span>' +
        '<span class="ta-ext-val" style="color:' + col + '">' + num(t.atr_ext, 1) + "</span>" +
        '<span class="ta-ext-band" style="color:' + col + '">' + bi(t.band_en, t.band_zh) + "</span>" +
        '<span class="ta-dim">' + (t.pct_parabolic ? Math.round(t.pct_parabolic * 100) + "% " + bi("parabolic", "抛物") : "") + "</span>" +
        "</div>";
    }).join("");
    return '<div class="ta-sub">' + bi("Theme extension", "主题延展") +
      ' <span class="ta-dim">' + bi("median member, ATRs above 50d trend (close-based)", "成员中位数，相对50日趋势的ATR倍数（基于收盘）") + "</span></div>" +
      '<div class="ta-ext">' + rows + "</div>";
  }

  function STYLE() {
    return '<style>' +
      "#theme-addons .ta-chip-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:2px 0 12px}" +
      "#theme-addons .ta-badge{color:#fff;font-weight:700;font-size:11px;padding:2px 8px;border-radius:6px;letter-spacing:.3px}" +
      "#theme-addons .ta-kv{font-size:12px;color:var(--muted)}#theme-addons .ta-kv b{color:var(--text)}" +
      "#theme-addons .ta-young{font-size:10px;color:var(--orange);border:1px solid var(--line);border-radius:4px;padding:0 4px}" +
      "#theme-addons .ta-sub{font-size:12px;font-weight:700;margin:12px 0 6px;color:var(--text)}" +
      "#theme-addons .ta-dim{font-weight:400;color:var(--muted);font-size:11px}" +
      "#theme-addons .ta-strip{display:flex;flex-wrap:wrap;gap:6px}" +
      "#theme-addons .ta-pill{font-size:11.5px;border:1px solid var(--line);background:var(--panel2);border-radius:6px;padding:3px 8px;white-space:nowrap}" +
      "#theme-addons .ta-pill b{color:var(--text)}#theme-addons .ta-pill em{color:var(--muted);font-style:normal}" +
      "#theme-addons .ta-pill.ta-lead{border-color:var(--up)}#theme-addons .ta-pill.ta-lag{border-color:var(--down);opacity:.85}" +
      "#theme-addons .ta-ext{display:flex;flex-direction:column;gap:3px}" +
      "#theme-addons .ta-ext-row{display:grid;grid-template-columns:minmax(120px,1.4fr) 2fr 36px 84px auto;gap:8px;align-items:center;font-size:12px}" +
      "#theme-addons .ta-ext-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
      "#theme-addons .ta-ext-bar{height:8px;background:var(--panel2);border-radius:4px;overflow:hidden}" +
      "#theme-addons .ta-ext-bar span{display:block;height:100%}" +
      "#theme-addons .ta-ext-val{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}" +
      "#theme-addons .ta-ext-band{font-size:11px;font-weight:600}" +
      "@media(max-width:640px){#theme-addons .ta-ext-row{grid-template-columns:minmax(90px,1.3fr) 1.4fr 32px 70px}#theme-addons .ta-ext-row .ta-dim{display:none}}" +
      "</style>";
  }

  window.renderThemeAddons = function (opts) {
    opts = opts || {};
    var base = opts.base || "basketdata/";
    var region = opts.region || "us";
    var mount = document.querySelector(opts.mount || "#theme-addons");
    if (!mount) return;
    var extName = "theme_extension" + (region === "us" ? "" : "_" + region) + ".json";
    Promise.all([
      fetchJSON(base + "vol_sentiment.json"),
      fetchJSON(base + "etf_pulse.json"),
      fetchJSON(base + extName),
    ]).then(function (res) {
      var vs = res[0], ep = res[1], te = res[2];
      if (!vs && !ep && !te) { mount.style.display = "none"; return; }
      var asof = (ep && ep.as_of) || (vs && vs.as_of) || (te && te.as_of) || "";
      mount.innerHTML = STYLE() +
        '<h2 style="margin:0 0 4px"><span class="idx">00B</span>' +
        bi("⚡ Rotation context", "⚡ 轮动背景") +
        ' <span class="chip">' + bi("display-only", "仅展示") + "</span>" +
        (asof ? ' <span class="ta-dim" style="font-weight:400">' + esc(asof) + "</span>" : "") + "</h2>" +
        '<p class="ta-dim" style="margin:0 0 6px">' +
        bi("Style/risk/sector rotation, vol regime and per-theme extension — the tape context beside the Theme Rotation Desk. Never scored.",
           "风格/风险/行业轮动、波动率制度与各主题延展 — 主题轮动台旁的市场背景。不计分。") + "</p>" +
        renderVol(vs) + renderPulse(ep) + renderExt(te);
      mount.style.display = "";
    });
  };
})();
