/* Anonymous/Free preview controller for public dashboard shells.
   The server still owns every protected detail page and data payload. This
   layer only determines how many already-public summary rows each visitor sees:
   anonymous = 1, registered Free = 3, Essential/Pro = the full book. */
(function () {
  "use strict";

  var state = { tier: "anon", cap: 1 };
  var GATE_ATTR = "data-mx-tier-gate";
  var observer = null;
  var applying = false;

  // `essential` is the WIRE value; `insider` is what the estate shipped before the
  // rename (lib/tiers.py is the server's copy of the same table). Named here, not just
  // resolved in setTier(), because a far-future-cached copy of this file must keep a
  // paying visitor OUT of the 3-row free cap when /api/me answers with either value —
  // rows written before the flip still say `insider` and are never back-filled.
  var TIER_ALIAS = { insider: "essential" };
  function normTier(tier) {
    var t = String(tier == null ? "" : tier).trim().toLowerCase();
    return TIER_ALIAS[t] || t;
  }
  function isPaid(tier) {
    var t = normTier(tier);
    return t === "essential" || t === "pro" || t === "unlimited";
  }
  function capFor(tier) { return isPaid(tier) ? Infinity : (tier === "free" ? 3 : 1); }
  function hasSessionCookie() {
    try {
      return String(document.cookie || "").split(";").some(function (part) {
        return /^sb-.*-auth-token(\.\d+)?$/.test(part.split("=")[0].trim());
      });
    } catch (e) { return false; }
  }
  function cachedMe() {
    try {
      var raw = sessionStorage.getItem("mm.me");
      var parsed = raw ? JSON.parse(raw) : null;
      if (parsed && parsed.me && parsed.t && Date.now() - parsed.t < 60000) return parsed.me;
    } catch (e) {}
    return null;
  }
  function meHint() {
    try {
      var parsed = JSON.parse(localStorage.getItem("mm.me.hint") || "null");
      return parsed && parsed.tier ? parsed : null;
    } catch (e) { return null; }
  }
  function openOnboard(mode) {
    if (window.MMOnboard && typeof window.MMOnboard.open === "function") {
      window.MMOnboard.open(mode || "signup", {});
      return;
    }
    if (window.MDXAuth && typeof window.MDXAuth.open === "function") {
      window.MDXAuth.open(mode === "signup" ? "signup" : "signin");
      return;
    }
    location.href = "/?signup=1";
  }
  function openUpgrade() {
    if (window.MMOnboard && typeof window.MMOnboard.open === "function") {
      window.MMOnboard.open("upgrade", { plan: "essential", period: "annual" });
      return;
    }
    location.href = "/plans.html";
  }

  function directRows(root) {
    var rows = Array.prototype.slice.call(root.children || []);
    return rows.filter(function (row) {
      if (row.matches && row.matches("tr")) return !!row.querySelector("td");
      return !!(row.matches && row.matches(".actitem,[data-theme-id],.pvcard,.nbcard,.nb-card,.ts-row,.sbx-tile,.dash-tw-row,.pbr-r"));
    });
  }
  function groups() {
    var out = [];
    function add(selector) {
      document.querySelectorAll(selector).forEach(function (root) {
        var items = directRows(root);
        if (items.length) out.push({ root: root, items: items });
      });
    }
    add("#action-board .actbody");
    add("#us-standouts .nbgrid");
    add("#us-standouts .topsetups tbody");
    // The `ran` list is quieter markup than the cards, but it is the SAME board:
    // ticker, name and move, one row per name. It sat inside #us-standouts ungated,
    // so an anonymous visitor read the full roster in plain text directly under a
    // blurred grid. Same group idiom, same cap, same gate.
    add("#us-standouts .pbr-l");
    add("#us-stocktable-wrap tbody");
    add("#dash-tw-rows");
    add("#dash-mtf-body tbody");
    add("body.page-stocks .panel table tbody");

    var seen = [];
    return out.filter(function (group) {
      if (seen.indexOf(group.root) !== -1) return false;
      seen.push(group.root);
      return true;
    });
  }
  function surfaceFor(root) {
    if (root.closest && root.closest("#action-board")) return "action";
    if (root.closest && root.closest("#us-standouts")) return "prophet";
    return "";
  }
  function gateCopy(surface) {
    if (state.tier === "free") {
      if (surface === "prophet") {
        return {
          eyebrow: "Prophet",
          eyebrowZh: "Prophet",
          mark: "P",
          title: "See the complete Prophet ranking",
          zh: "查看完整 Prophet 排名",
          body: "Every model-ranked setup, in one signal book.",
          bodyZh: "所有模型排名机会，集中于一份信号名单。",
          action: "Unlock full Prophet",
          actionZh: "解锁完整 Prophet",
          mode: "upgrade"
        };
      }
      return {
        eyebrow: "Essential access",
        eyebrowZh: "Essential 权限",
        mark: "↗",
        title: "Unlock the complete action board",
        zh: "解锁完整行动面板",
        body: "See every current setup, without limits.",
        bodyZh: "无限制查看所有当前机会。",
        action: "View Essential plans",
        actionZh: "查看 Essential 方案",
        mode: "upgrade"
      };
    }
    if (surface === "prophet") {
      return {
        eyebrow: "Prophet",
        eyebrowZh: "Prophet",
        mark: "P",
        title: "Expand the Prophet shortlist",
        zh: "展开 Prophet 精选名单",
        body: "More model-ranked setups, with the same signal detail and discipline.",
        bodyZh: "查看更多模型排名机会，同时保留完整信号细节与纪律。",
        action: "See more Prophet picks",
        actionZh: "查看更多 Prophet 精选",
        mode: "signup"
      };
    }
    return {
      eyebrow: "Daily action board",
      eyebrowZh: "每日行动面板",
      mark: "↗",
      title: "Open more of today’s action board",
      zh: "展开今日行动面板",
      body: "More actionable signals, presented in one clean daily workflow.",
      bodyZh: "更多可执行信号，集中于清晰的每日流程。",
      action: "Create free account",
      actionZh: "创建免费账户",
      secondary: "Already a member? Sign in",
      secondaryZh: "已有账户？登录",
      mode: "signup"
    };
  }
  function makeGate(surface) {
    var copy = gateCopy(surface);
    var gate = document.createElement("div");
    gate.className = "mx-tier-gate mx-tier-gate--" + surface;
    gate.setAttribute(GATE_ATTR, surface);
    gate.innerHTML =
      '<span class="mx-tier-copy">' +
      '<span class="mx-tier-eyebrow"><span class="mx-tier-mark" aria-hidden="true">' + copy.mark + '</span>' +
      '<span class="l-en">' + copy.eyebrow + '</span><span class="l-zh">' + copy.eyebrowZh + '</span></span>' +
      '<b><span class="l-en">' + copy.title + '</span><span class="l-zh">' + copy.zh + '</span></b>' +
      '<small><span class="l-en">' + copy.body + '</span><span class="l-zh">' + copy.bodyZh + '</span></small></span>' +
      '<span class="mx-tier-actions"><button class="mx-tier-primary" type="button"><span class="l-en">' + copy.action + '</span><span class="l-zh">' + copy.actionZh + '</span></button>' +
      (copy.secondary ? '<button class="mx-tier-signin" type="button"><span class="l-en">' + copy.secondary + '</span><span class="l-zh">' + copy.secondaryZh + '</span></button>' : '') +
      '</span>';
    gate.querySelector(".mx-tier-primary").addEventListener("click", function () {
      if (copy.mode === "upgrade") openUpgrade(); else openOnboard("signup");
    });
    var signin = gate.querySelector(".mx-tier-signin");
    if (signin) signin.addEventListener("click", function () { openOnboard("signin"); });
    return gate;
  }
  function clearGroup(group) {
    group.items.forEach(function (item) {
      item.classList.remove("mx-tier-blurred", "mx-tier-hidden");
      item.removeAttribute("aria-hidden");
      if (item.hasAttribute("data-mx-old-tabindex")) {
        var old = item.getAttribute("data-mx-old-tabindex");
        if (old === "") item.removeAttribute("tabindex"); else item.setAttribute("tabindex", old);
        item.removeAttribute("data-mx-old-tabindex");
      }
    });
  }
  function applyGroup(group) {
    clearGroup(group);
    if (!isFinite(state.cap) || group.items.length <= state.cap) return false;
    group.items.forEach(function (item, index) {
      if (index < state.cap) return;
      item.setAttribute("aria-hidden", "true");
      if (index < state.cap + 2) {
        item.classList.add("mx-tier-blurred");
        if (item.hasAttribute("tabindex")) item.setAttribute("data-mx-old-tabindex", item.getAttribute("tabindex") || "");
        item.setAttribute("tabindex", "-1");
      } else {
        item.classList.add("mx-tier-hidden");
      }
    });
    return true;
  }
  // ── themes-in-favour strip ────────────────────────────────────────────────
  // The strip lives inside #us-standouts and lists, per theme, which of today's board
  // names sit in it — i.e. the very tickers the gated cards carry, printed in plain
  // text above the blur. The theme NAME is context worth leaving visible; the ticker
  // LIST is the product, so it collapses to a count for anon/free. Reversible through
  // the same data-mx-old-* stash clearGroup uses for tabindex, because a visitor who
  // upgrades in-page must get the names back without a reload.
  function themeNameCount(list) {
    var n = 0;
    Array.prototype.slice.call(list.children || []).forEach(function (el) {
      if (el.classList && el.classList.contains("pbt-more")) {
        // the "+N" tail: names the strip already truncated, still real membership.
        var extra = parseInt(String(el.textContent || "").replace(/[^0-9]/g, ""), 10);
        if (extra > 0) n += extra;
      } else if (el.tagName === "SPAN") {
        n += 1;
      }
    });
    return n;
  }
  function applyThemeTickers() {
    var gated = isFinite(state.cap);
    document.querySelectorAll("#us-standouts .pbt-tk").forEach(function (list) {
      var stashed = list.getAttribute("data-mx-old-html");
      if (!gated) {
        if (stashed !== null) {
          list.innerHTML = stashed;
          list.removeAttribute("data-mx-old-html");
        }
        return;
      }
      if (stashed !== null) return;
      var n = themeNameCount(list);
      list.setAttribute("data-mx-old-html", list.innerHTML);
      list.innerHTML =
        '<span class="l-en">' + n + (n === 1 ? " name" : " names") + ' on the board</span>' +
        '<span class="l-zh">榜上 ' + n + ' 只股票</span>';
    });
  }
  function placeSurfaceGates(surfaces) {
    [
      { key: "action", selector: "#action-board" },
      { key: "prophet", selector: "#us-standouts" }
    ].forEach(function (surface) {
      var panel = document.querySelector(surface.selector);
      if (panel && surfaces[surface.key]) panel.appendChild(makeGate(surface.key));
    });
  }
  function apply() {
    if (applying) return;
    applying = true;
    if (observer) observer.disconnect();
    try {
      document.querySelectorAll("[" + GATE_ATTR + "]").forEach(function (gate) { gate.remove(); });
      var surfaces = { action: false, prophet: false };
      groups().forEach(function (group) {
        if (!applyGroup(group)) return;
        var surface = surfaceFor(group.root);
        if (surface) surfaces[surface] = true;
      });
      placeSurfaceGates(surfaces);
      // Unconditional: the strip leaks even when the grid itself is short enough that
      // no group tripped the cap.
      applyThemeTickers();
    } finally {
      applying = false;
      if (observer && document.body) observer.observe(document.body, { childList: true, subtree: true });
    }
  }
  function setTier(tier) {
    tier = normTier(tier);
    tier = isPaid(tier) ? tier : (tier === "free" ? "free" : "anon");
    state.tier = tier;
    state.cap = capFor(tier);
    document.documentElement.setAttribute("data-access-tier", tier);
    apply();
    try { window.dispatchEvent(new CustomEvent("mmx-access-tier", { detail: { tier: tier, cap: state.cap } })); } catch (e) {}
  }
  function fetchMe() {
    if (!window.MDXAuth || typeof window.MDXAuth.client !== "function") return Promise.resolve(null);
    return window.MDXAuth.client().then(function (sb) {
      return sb.auth.getSession();
    }).then(function (result) {
      var session = result && result.data && result.data.session;
      if (!session) return null;
      return fetch("/api/me", {
        cache: "no-store",
        headers: { Authorization: "Bearer " + session.access_token }
      }).then(function (response) {
        if (!response.ok) return null;
        return response.json();
      });
    }).catch(function () { return null; });
  }
  function resolveTier() {
    if (!hasSessionCookie()) { setTier("anon"); return; }
    var cached = cachedMe() || meHint();
    setTier((cached && cached.tier) || "free");
    fetchMe().then(function (me) { setTier((me && me.tier) || "free"); });
  }

  window.MMXAccessPreview = {
    tier: function () { return state.tier; },
    cap: function () { return state.cap; },
    isAnon: function () { return state.tier === "anon"; },
    openSignin: function () { openOnboard("signin"); },
    openSignup: function () { openOnboard("signup"); },
    refresh: resolveTier
  };

  function boot() {
    resolveTier();
    if (window.MDXAuth && typeof window.MDXAuth.onChange === "function") {
      window.MDXAuth.onChange(function (user, event) {
        if (!user || event === "SIGNED_OUT") setTier("anon");
        else resolveTier();
      });
    }
    if (window.MutationObserver) {
      observer = new MutationObserver(function () {
        if (applying) return;
        clearTimeout(observer._timer);
        observer._timer = setTimeout(apply, 40);
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
