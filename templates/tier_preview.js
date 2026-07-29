/* Anonymous/Free preview controller for public dashboard shells.
   The server still owns every protected detail page and data payload. This
   layer only determines how many already-public summary rows each visitor sees:
   anonymous = 1, registered Free = 3, Insider/Pro = the full book. */
(function () {
  "use strict";

  var state = { tier: "anon", cap: 1 };
  var GATE_ATTR = "data-mx-tier-gate";
  var observer = null;
  var applying = false;

  function isPaid(tier) { return tier === "insider" || tier === "pro" || tier === "unlimited"; }
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
      window.MMOnboard.open("upgrade", { plan: "insider", period: "annual" });
      return;
    }
    location.href = "/plans.html";
  }

  function directRows(root) {
    var rows = Array.prototype.slice.call(root.children || []);
    return rows.filter(function (row) {
      if (row.matches && row.matches("tr")) return !!row.querySelector("td");
      return !!(row.matches && row.matches(".actitem,[data-theme-id],.pvcard,.nbcard,.nb-card,.ts-row,.sbx-tile,.dash-tw-row"));
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
  function gateCopy() {
    if (state.tier === "free") {
      return {
        title: "Free includes 3 signals per list",
        zh: "免费方案每个列表可查看 3 条信号",
        body: "Upgrade to Insider or Pro for the full book.",
        bodyZh: "升级 Insider 或 Pro 查看完整名单。",
        action: "See paid plans",
        actionZh: "查看付费方案",
        mode: "upgrade"
      };
    }
    return {
      title: "Preview 1 signal before signup",
      zh: "注册前可预览 1 条信号",
      body: "Create a free account to see 3 signals per list each day.",
      bodyZh: "创建免费账户，每天每个列表可查看 3 条信号。",
      action: "Create free account",
      actionZh: "创建免费账户",
      mode: "signup"
    };
  }
  function makeGate() {
    var copy = gateCopy();
    var gate = document.createElement("div");
    gate.className = "mx-tier-gate";
    gate.setAttribute(GATE_ATTR, "");
    gate.innerHTML =
      '<span class="mx-tier-lock" aria-hidden="true">⌁</span>' +
      '<span class="mx-tier-copy"><b><span class="l-en">' + copy.title + '</span><span class="l-zh">' + copy.zh + '</span></b>' +
      '<small><span class="l-en">' + copy.body + '</span><span class="l-zh">' + copy.bodyZh + '</span></small></span>' +
      '<button type="button"><span class="l-en">' + copy.action + '</span><span class="l-zh">' + copy.actionZh + '</span></button>';
    gate.querySelector("button").addEventListener("click", function () {
      if (copy.mode === "upgrade") openUpgrade(); else openOnboard("signup");
    });
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
    var next = group.root.nextElementSibling;
    if (next && next.hasAttribute(GATE_ATTR)) next.remove();
  }
  function applyGroup(group) {
    clearGroup(group);
    if (!isFinite(state.cap) || group.items.length <= state.cap) return;
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
    group.root.insertAdjacentElement("afterend", makeGate());
  }
  function apply() {
    if (applying) return;
    applying = true;
    if (observer) observer.disconnect();
    try { groups().forEach(applyGroup); } finally {
      applying = false;
      if (observer && document.body) observer.observe(document.body, { childList: true, subtree: true });
    }
  }
  function setTier(tier) {
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
