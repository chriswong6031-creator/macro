"use strict";
/* Mastermind Admin — single-page console. Vanilla JS, no external deps. */

const $ = (sel, el = document) => el.querySelector(sel);
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtAge = (hrs) => hrs == null ? "—" : hrs < 1 ? `${Math.round(hrs * 60)}m` : hrs < 48 ? `${hrs.toFixed(0)}h` : `${(hrs / 24).toFixed(0)}d`;
const fmtUSD = (n) => n == null ? "—" : "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
const fmtTokens = (n) => n == null ? "—" : Number(n) >= 1e6 ? `${(Number(n)/1e6).toFixed(2)}M` : Number(n) >= 1000 ? `${(Number(n)/1000).toFixed(1)}k` : String(Math.round(Number(n)));
const fmtBytes = (b) => { if (b == null) return "—"; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0, n = Number(b); while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; } return n.toFixed(n < 10 && i > 0 ? 1 : 0) + " " + u[i]; };
const fmtNum = (n) => n == null ? "—" : Number(n).toLocaleString();
const getCookie = (name) => { const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)")); return m ? decodeURIComponent(m[1]) : null; };

let SESSION = { auth_enabled: false, authenticated: true, deployed: false, integrations: {} };

/* ---- lobe popup (system map hover) -------------------------------------- */
let NW_LOBE_BY_ID = {};
let _lobeTip = null;
function getLobeTip() {
  if (!_lobeTip) {
    _lobeTip = document.createElement("div");
    _lobeTip.className = "lobe-tip";
    _lobeTip.setAttribute("role", "tooltip");
    _lobeTip.setAttribute("aria-hidden", "true");
    document.body.appendChild(_lobeTip);
  }
  return _lobeTip;
}
function showLobeTip(el) {
  const id = el.dataset.lobe;
  const l = NW_LOBE_BY_ID[id];
  if (!l) return;
  const tip = getLobeTip();
  const age = l.age_hours, sla = l.freshness_sla_hours;
  const ageTxt = age == null ? "—" : fmtAge(age);
  const slaTxt = sla ? ` / ${fmtAge(sla)}` : "";
  const stt = l.status === "fresh" ? "fresh" : l.status === "stale" ? "stale" : (l.status === "missing" || l.status === "degraded") ? "missing" : "stale";
  tip.innerHTML =
    `<div class="lobe-tip-header">` +
      `<span class="status-dot" data-status="${esc(stt)}" style="width:8px;height:8px"></span>` +
      `<span class="lobe-tip-name">${esc(l.label)}</span>` +
      `<span class="group-chip" data-group="${esc(l.group)}">${esc(l.group_label || l.group)}</span>` +
    `</div>` +
    `<div class="lobe-tip-desc">${esc(l.short_desc || "No description registered.")}</div>` +
    `<div class="lobe-tip-metrics">` +
      `<span>${ageTxt}${slaTxt}</span>` +
      `<span class="metric-sep">·</span>` +
      `<span>${l.n_consumers} consumer${l.n_consumers === 1 ? "" : "s"}</span>` +
      `<span class="metric-sep">·</span>` +
      `<span>${esc(l.tier || "—")}</span>` +
    `</div>`;
  positionLobeTip(tip, el);
  tip.classList.add("show");
}
function hideLobeTip() {
  if (_lobeTip) _lobeTip.classList.remove("show");
}
function positionLobeTip(tip, el) {
  /* Position next to the node, clamped to viewport. position:fixed. */
  const r = el.getBoundingClientRect();
  const tw = 248, th = 110; /* conservative max tip size */
  const vw = window.innerWidth, vh = window.innerHeight;
  const PAD = 8;
  /* prefer right of node; fall left if no room */
  let left = r.right + PAD;
  if (left + tw > vw - PAD) left = r.left - tw - PAD;
  left = Math.max(PAD, Math.min(left, vw - tw - PAD));
  /* prefer top-aligned with node center; shift up if clips bottom */
  let top = r.top + r.height / 2 - 40;
  if (top + th > vh - PAD) top = vh - th - PAD;
  top = Math.max(PAD, top);
  tip.style.left = left + "px";
  tip.style.top  = top  + "px";
}
function wireLobeTipNode(el) {
  el.addEventListener("mouseenter", () => showLobeTip(el));
  el.addEventListener("mouseleave", hideLobeTip);
  el.addEventListener("focus",      () => showLobeTip(el));
  el.addEventListener("blur",       hideLobeTip);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { showLogin(); throw new Error("auth required"); }
  return r.json().catch(() => ({ error: "bad json" }));
}
function post(path, body) {
  const headers = { "Content-Type": "application/json" };
  const csrf = getCookie("admin_csrf");
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return api(path, { method: "POST", headers, body: JSON.stringify(body || {}) });
}

let TOAST_T;
function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast show" + (err ? " err" : "");
  clearTimeout(TOAST_T); TOAST_T = setTimeout(() => t.className = "toast", 3000);
}

/* ---- login -------------------------------------------------------------- */
function showLogin() { $("#login").classList.add("show"); $("#app").style.display = "none"; }
function hideLogin() { $("#login").classList.remove("show"); $("#app").style.display = ""; }

$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#loginErr").textContent = "";
  const r = await fetch("/api/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: $("#pw").value }),
  }).then(x => x.json()).catch(() => ({ ok: false, error: "network error" }));
  if (r.ok) { $("#pw").value = ""; hideLogin(); boot(); }
  else $("#loginErr").textContent = r.error || "login failed";
});

async function logout() {
  await post("/api/logout", {});
  showLogin();
}

/* ---- sidebar nav + router ----------------------------------------------- */
const NAV_ICO = (inner) => `<svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
const ICONS = {
  overview:    NAV_ICO('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
  neural_web:  NAV_ICO('<circle cx="12" cy="12" r="2.4"/><circle cx="5" cy="6" r="1.7"/><circle cx="19" cy="6" r="1.7"/><circle cx="5" cy="18" r="1.7"/><circle cx="19" cy="18" r="1.7"/><path d="M10 11 6.4 7.2M14 11l3.6-3.8M10 13l-3.6 3.8M14 13l3.6 3.8"/>'),
  alerts:      NAV_ICO('<path d="M12 3a6 6 0 0 0-6 6c0 4-1.5 5.5-2 6.5h16c-.5-1-2-2.5-2-6.5a6 6 0 0 0-6-6Z"/><path d="M10 19a2 2 0 0 0 4 0"/>'),
  analytics:   NAV_ICO('<path d="M4 20V11M9.5 20V5M15 20v-8M20.5 20V8"/><path d="M2.5 20h19"/>'),
  users:       NAV_ICO('<circle cx="9" cy="8" r="3"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><path d="M16 5.3a3 3 0 0 1 0 5.4M21 20a5.5 5.5 0 0 0-4-5.3"/>'),
  experiments: NAV_ICO('<path d="M9 3h6M10 3v5.5L5.4 17.6A2 2 0 0 0 7.2 20.5h9.6a2 2 0 0 0 1.8-2.9L14 8.5V3"/><path d="M8 14h8"/>'),
  system:      NAV_ICO('<rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/><path d="M7 7.5h.01M7 16.5h.01"/>'),
  health:      NAV_ICO('<path d="M3 12h3.5l2 5 3.5-11 2.5 7 1.5-3H21"/>'),
  deploy:      NAV_ICO('<path d="M12 2.5s4.5 2.8 4.5 8.5c0 2.8-1.8 4.5-1.8 4.5H9.3S7.5 13.8 7.5 11C7.5 5.3 12 2.5 12 2.5Z"/><circle cx="12" cy="9.5" r="1.5"/><path d="M8.5 17l-2 4M15.5 17l2 4"/>'),
  cost:        NAV_ICO('<circle cx="12" cy="12" r="9"/><path d="M12 6.5v11M14.6 9a2.6 2 0 0 0-2.6-1.5c-1.6 0-2.7.9-2.7 2.1 0 2.6 5.4 1.3 5.4 4 0 1.3-1.2 2.2-2.7 2.2A2.7 2 0 0 1 9.2 16"/>'),
  content:     NAV_ICO('<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>'),
  features:    NAV_ICO('<circle cx="8" cy="8" r="3"/><circle cx="16" cy="16" r="3"/><path d="M11 8h9M4 16h9"/>'),
  brief:       NAV_ICO('<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M18.5 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>'),
  vector:      NAV_ICO('<circle cx="12" cy="12" r="9"/><path d="M9.5 7.5h4.2a2.2 2 0 0 1 0 4H9.5m0 0h4.6a2.2 2 0 0 1 0 4.4H9.5m0-8.4V5.5m0 13v-2m2.4-11v2m0 7.4v2"/>'),
  long_hold:     NAV_ICO('<polyline points="3 18 8 10 13 14 18 6"/><line x1="3" y1="21" x2="21" y2="21"/>'),
  context_lobe:  NAV_ICO('<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>'),
  causal_lab:    NAV_ICO('<path d="M9 3h6M10 3v5.5L5.4 17.6A2 2 0 0 0 7.2 20.5h9.6a2 2 0 0 0 1.8-2.9L14 8.5V3"/><path d="M8 14h8"/><circle cx="17" cy="7" r="3"/><path d="M15.5 5.5l3 3"/>'),
  metabolism:    NAV_ICO('<circle cx="12" cy="12" r="9"/><path d="M8 12h8M12 8v8"/><circle cx="12" cy="12" r="3"/>'),
  codex:         NAV_ICO('<path d="M12 3l2 6h6l-5 4 2 6-5-4-5 4 2-6-5-4h6z"/>'),
  orchestrator:  NAV_ICO('<circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v2.6M12 17.9v2.6M3.5 12h2.6M17.9 12h2.6"/>'),
  mastermind_ai: NAV_ICO('<rect x="5" y="7" width="14" height="12" rx="2.5"/><circle cx="9.5" cy="12.5" r="1.2"/><circle cx="14.5" cy="12.5" r="1.2"/><path d="M12 7V4M12 4h.01M9 16h6"/>'),
  site_gate:     NAV_ICO('<rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/><circle cx="12" cy="16" r="1.5"/>'),
};
const NAV_GROUPS = [
  { label: "", items: [["overview", "Overview"]] },
  { label: "Neural Web", items: [["neural_web", "Observatory"], ["orchestrator", "Master Brain"], ["mastermind_ai", "Mastermind AI"], ["alerts", "Alerts"], ["long_hold", "Long-Hold Lobe"], ["context_lobe", "Context Lobe"], ["causal_lab", "Causal Lab"]] },
  { label: "Growth", items: [["analytics", "Analytics"], ["users", "Users"], ["experiments", "Experiments"], ["site_gate", "Site Access"]] },
  { label: "System", items: [["system", "System"], ["health", "Health"], ["deploy", "Build & Deploy"], ["metabolism", "Metabolism"], ["codex", "Codex Research"], ["cost", "AI Cost"], ["content", "Content"]] },
  { label: "Config", items: [["features", "Features"], ["brief", "AI Brief"], ["vector", "BTC Override"]] },
];
const TAB_LABELS = Object.fromEntries(NAV_GROUPS.flatMap(g => g.items));
let CURRENT = "overview";
let SUMMARY = null;
let RT_TIMER = null;
let LOOP_TIMER = null;   /* live-runs poll interval (metabolism + mastermind_ai tabs) */
let LOOP_TICK  = null;   /* 1-second elapsed-counter tick for the loop strip */

/* ---- live-runs helpers --------------------------------------------------- */
/* Map workflow names (no .yml suffix) to plain-word stage labels. */
const LOOP_STAGE_WORD_NAME = {
  "metabolism-agenda":     "scanning & ranking",
  "metabolism-propose":    "drafting proposals",
  "metabolism-adjudicate": "judging proposals",
  "metabolism-build":      "building approved work",
  "metabolism-cycle":      "full loop (chain runner)",
};

function loopStageWord(run) {
  const wf = (run && (run.workflow || "")).replace(/\.yml$/, "");
  return LOOP_STAGE_WORD_NAME[wf] || wf || "unknown stage";
}

function fmtElapsedSec(totalSec) {
  if (totalSec == null || totalSec < 0) return "0s";
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = Math.floor(totalSec % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function fmtLoopDurationMin(startStr, endStr) {
  try {
    const dur = (new Date(endStr) - new Date(startStr)) / 60000;
    return dur > 0 ? dur.toFixed(0) : "0";
  } catch (e) { return "?"; }
}

/* Render the live-loop status strip HTML from /api/live_runs response.
   metabolism = runs.metabolism  ({active, queued, last_completed, heartbeat})
   codex      = runs.codex       ({active, queued, last_completed})
   Returns an HTML string. Called from metabolism, mastermind_ai, and orchestrator tabs. */
function liveLoopStripHtml(metabolism, codex) {
  /* metabolism.active is an array; prefer the first (most recent) entry. */
  const metab = (metabolism && typeof metabolism === "object") ? metabolism : {};
  const active  = (Array.isArray(metab.active)  && metab.active.length)  ? metab.active[0]  : null;
  const queued  = (Array.isArray(metab.queued)  && metab.queued.length)  ? metab.queued[0]  : null;
  const last    = metab.last_completed || null;

  let html = "";

  /* ---- main loop strip line ---- */
  if (active) {
    const stage = loopStageWord(active);
    const startTs = active.run_started_at || active.created_at || "";
    const elSec = startTs ? Math.max(0, Math.floor((Date.now() - new Date(startTs).getTime()) / 1000)) : 0;
    const elTxt = fmtElapsedSec(elSec);
    const ghLink = active.html_url ? ` &mdash; <a href="${esc(active.html_url)}" target="_blank" rel="noopener">watch on GitHub</a>` : "";
    const currentStep = (Array.isArray(active.jobs) && active.jobs.length) ? active.jobs[0].current_step : null;
    const stepLine = currentStep ? `<div class="loop-strip-step sub">building: ${esc(currentStep)}</div>` : "";
    html += `<div class="loop-strip loop-strip-active">
      <span class="loop-dot">&#9679;</span>
      <div>
        <div>Loop running &mdash; <span class="loop-stage">${esc(stage)}</span> &middot; started <span class="loop-elapsed" data-loop-start="${esc(startTs)}">${esc(elTxt)}</span> ago${ghLink}</div>
        ${stepLine}
      </div>
    </div>`;
  } else if (queued) {
    const startTs = queued.created_at || "";
    const elSec = startTs ? Math.max(0, Math.floor((Date.now() - new Date(startTs).getTime()) / 1000)) : 0;
    const elTxt = fmtElapsedSec(elSec);
    html += `<div class="loop-strip loop-strip-queued">
      <span class="loop-dot loop-dot-queued">&#9684;</span>
      Loop queued behind other runner work &mdash; waiting <span class="loop-elapsed" data-loop-start="${esc(startTs)}">${esc(elTxt)}</span>
    </div>`;
  } else if (last) {
    const outcome = last.conclusion || last.status || "done";
    const outcomeWord = outcome === "success" ? "completed" : outcome === "failure" ? "failed" : outcome === "cancelled" ? "cancelled" : outcome;
    const endTs = last.updated_at || last.run_started_at || "";
    const startTs = last.created_at || last.run_started_at || "";
    const agoSec = endTs ? Math.max(0, Math.floor((Date.now() - new Date(endTs).getTime()) / 1000)) : null;
    const agoTxt = agoSec != null ? fmtElapsedSec(agoSec) : "—";
    const durTxt = last.duration_s != null ? (last.duration_s / 60).toFixed(0) : "?";
    html += `<div class="loop-strip loop-strip-idle">
      <span class="loop-dot loop-dot-idle">&#9675;</span>
      No loop running &mdash; last loop ${esc(outcomeWord)} ${esc(agoTxt)} ago, took ${esc(durTxt)}m
    </div>`;
  } else {
    html += `<div class="loop-strip loop-strip-idle">
      <span class="loop-dot loop-dot-idle">&#9675;</span>
      No loop running
    </div>`;
  }

  /* ---- codex lane line (only when active/queued) ---- */
  const cdx = (codex && typeof codex === "object") ? codex : {};
  const cdxActive = (Array.isArray(cdx.active) && cdx.active.length) ? cdx.active[0] : null;
  const cdxQueued = (Array.isArray(cdx.queued) && cdx.queued.length) ? cdx.queued[0] : null;
  if (cdxActive) {
    const startTs = cdxActive.run_started_at || cdxActive.created_at || "";
    const elSec = startTs ? Math.max(0, Math.floor((Date.now() - new Date(startTs).getTime()) / 1000)) : 0;
    const ghLink = cdxActive.html_url ? ` &mdash; <a href="${esc(cdxActive.html_url)}" target="_blank" rel="noopener">watch ↗</a>` : "";
    html += `<div class="loop-strip loop-strip-active loop-strip-secondary">
      <span class="loop-dot">&#9679;</span>
      Codex research: running &mdash; ${esc(fmtElapsedSec(elSec))} ago${ghLink}
    </div>`;
  } else if (cdxQueued) {
    const startTs = cdxQueued.created_at || "";
    const elSec = startTs ? Math.max(0, Math.floor((Date.now() - new Date(startTs).getTime()) / 1000)) : 0;
    html += `<div class="loop-strip loop-strip-queued loop-strip-secondary">
      <span class="loop-dot loop-dot-queued">&#9684;</span>
      Codex research: queued &mdash; waiting ${esc(fmtElapsedSec(elSec))}
    </div>`;
  }

  return html;
}

/* Render the daily-pipeline strip line (used in orchestrator hero).
   nightly is runs.nightly ({active, queued, last_completed}) from /api/live_runs.
   Returns HTML string or "". */
function dailyPipelineStripLine(nightly) {
  if (!nightly || typeof nightly !== "object") return "";
  const activeRun = (Array.isArray(nightly.active) && nightly.active.length) ? nightly.active[0] : null;
  const queuedRun = (Array.isArray(nightly.queued) && nightly.queued.length) ? nightly.queued[0] : null;
  if (activeRun) {
    const startTs = activeRun.run_started_at || activeRun.created_at || "";
    const elSec = startTs ? Math.max(0, Math.floor((Date.now() - new Date(startTs).getTime()) / 1000)) : 0;
    return `<div class="loop-strip loop-strip-active" style="margin-top:8px">
      <span class="loop-dot">&#9679;</span>
      Nightly pipeline running &mdash; <span class="loop-elapsed" data-loop-start="${esc(startTs)}">${esc(fmtElapsedSec(elSec))}</span>
    </div>`;
  }
  if (queuedRun) {
    return `<div class="loop-strip loop-strip-queued" style="margin-top:8px">
      <span class="loop-dot loop-dot-queued">&#9684;</span>
      Nightly pipeline queued
    </div>`;
  }
  return "";
}

/* Start the live-runs poll for a tab.
   tabId: the CURRENT tab id, used to auto-cancel when tab changes.
   wrapId: id of the container element where the strip HTML will be injected.
   dailyMode: when true, also renders the daily-pipeline strip line inside the strip. */
function startLoopPoll(tabId, wrapId, dailyMode) {
  /* Clear any previous loop timers. */
  if (LOOP_TIMER) { clearInterval(LOOP_TIMER); LOOP_TIMER = null; }
  if (LOOP_TICK)  { clearInterval(LOOP_TICK);  LOOP_TICK  = null; }

  const doFetch = async () => {
    if (CURRENT !== tabId) {
      if (LOOP_TIMER) { clearInterval(LOOP_TIMER); LOOP_TIMER = null; }
      if (LOOP_TICK)  { clearInterval(LOOP_TICK);  LOOP_TICK  = null; }
      return;
    }
    let runs;
    try { runs = await api("/api/live_runs"); } catch (e) { return; }
    if (CURRENT !== tabId) return;
    const wrap = $("#" + (wrapId || "loopStripWrap"));
    if (!wrap) return;
    let stripHtml = liveLoopStripHtml(
      (runs && runs.metabolism) || {},
      (runs && runs.codex) || {},
    );
    if (dailyMode && runs && runs.nightly) {
      stripHtml += dailyPipelineStripLine(runs.nightly);
    }
    wrap.innerHTML = stripHtml;
    /* Restart the tick timer to count elapsed time. */
    if (LOOP_TICK) { clearInterval(LOOP_TICK); LOOP_TICK = null; }
    LOOP_TICK = setInterval(() => tickLoopElapsed(), 1000);
  };

  /* Initial fetch immediately, then every 20 seconds. */
  doFetch();
  LOOP_TIMER = setInterval(doFetch, 20000);
  /* Also start the client-side tick immediately. */
  LOOP_TICK = setInterval(() => tickLoopElapsed(), 1000);
}

/* Update the elapsed timer display(s) without a network fetch. */
function tickLoopElapsed() {
  document.querySelectorAll(".loop-elapsed[data-loop-start]").forEach(el => {
    const startStr = el.dataset.loopStart;
    if (!startStr) return;
    try {
      const elSec = Math.max(0, Math.floor((Date.now() - new Date(startStr).getTime()) / 1000));
      el.textContent = fmtElapsedSec(elSec);
    } catch (e) { /* ignore bad dates */ }
  });
}

function renderSidebar() {
  const nav = $("#sidenav"); if (!nav) return; nav.innerHTML = "";
  NAV_GROUPS.forEach(g => {
    const grp = h(`<div class="nav-group"></div>`);
    if (g.label) grp.appendChild(h(`<div class="eyebrow">${esc(g.label)}</div>`));
    g.items.forEach(([id, label]) => {
      const it = h(`<div class="nav-item" data-tab="${id}">${ICONS[id] || ""}<span>${esc(label)}</span></div>`);
      if (id === CURRENT) it.classList.add("active");
      it.onclick = () => go(id);
      grp.appendChild(it);
    });
    nav.appendChild(grp);
  });
}
function setActiveNav(id) {
  const nav = $("#sidenav"); if (!nav) return;
  nav.querySelectorAll(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.tab === id));
}
function setTopbarTitle(t) { const el = $("#topbar-title"); if (el) el.textContent = t; }

function go(id) {
  if (currentLobeId() || currentAnalyticsDetail()) history.replaceState(null, "", location.pathname + location.search);
  CURRENT = id;
  if (RT_TIMER)   { clearInterval(RT_TIMER);   RT_TIMER   = null; }
  if (LOOP_TIMER) { clearInterval(LOOP_TIMER); LOOP_TIMER = null; }
  if (LOOP_TICK)  { clearInterval(LOOP_TICK);  LOOP_TICK  = null; }
  hideLobeTip();
  setActiveNav(id);
  setTopbarTitle(TAB_LABELS[id] || id);
  RENDER[id]();
}

/* hash router — lobe detail "pages" live at #/lobe/<id> */
function currentLobeId() {
  const m = location.hash.match(/^#\/lobe\/(.+)$/);
  return m ? decodeURIComponent(m[1]) : null;
}
function gotoLobe(id) { location.hash = "#/lobe/" + encodeURIComponent(id); }
function backToObservatory() {
  if (currentLobeId()) history.replaceState(null, "", location.pathname + location.search);
  go("neural_web");
}
function route() {
  const id = currentLobeId();
  if (id) { renderLobeDetail(id); return; }
  const det = currentAnalyticsDetail();
  if (det) { (det.kind === "session" ? renderSessionDetail : renderVisitorDetail)(det.id); return; }
  go(CURRENT || "overview");
}
window.addEventListener("hashchange", route);

/* ---- header + banner ---------------------------------------------------- */
function renderHeader() {
  const m = SUMMARY.meta || {};
  const hh = SUMMARY.health || {};
  const sv = SUMMARY.services || {};
  const allOk = hh.healthy && (!sv.available || sv.healthy);
  const led = allOk ? "ok" : ((hh.broad_outage || (hh.sources && hh.sources.dead) || (sv.available && !sv.healthy)) ? "bad" : "warn");
  const el = $("#hmeta"); el.innerHTML = "";
  el.appendChild(h(`<span class="pill"><span class="led ${led}"></span>${allOk ? "Healthy" : "Attention"}</span>`));
  const ex = SUMMARY.experiments || {};
  if (ex.available && ex.ready_count > 0) {
    const p = h(`<span class="pill ready" title="experiment results are ready — open the Experiments tab">🔔 ${ex.ready_count} result${ex.ready_count > 1 ? "s" : ""} ready</span>`);
    p.style.cursor = "pointer"; p.onclick = () => go("experiments");
    el.appendChild(p);
  }
  if (m.deployed) el.appendChild(h(`<span class="pill" title="running on the VPS behind Caddy">deployed</span>`));
  el.appendChild(h(`<span>repo <code>${esc(m.repo || "?")}</code></span>`));
  el.appendChild(h(`<span>GH ${m.has_token ? "✓ token" : "read-only"}</span>`));
  if (m.site_url) el.appendChild(h(`<a href="${esc(m.site_url)}" target="_blank" rel="noopener">live site ↗</a>`));
  if (SESSION.auth_enabled) { const lo = h(`<span class="logout">log out</span>`); lo.onclick = logout; el.appendChild(lo); }
}

function renderBanner() {
  const g = SUMMARY.git || {}, m = SUMMARY.meta || {};
  const b = $("#banner");
  // In deployed mode, flag edits commit straight to main via GitHub — no local banner.
  if (m.deployed || !g.config_dirty) { b.className = "banner"; b.innerHTML = ""; return; }
  b.className = "banner show";
  b.innerHTML = `<span>⚠︎ <b>You have unsaved feature changes</b> — they won't affect the live site until you commit and rebuild.</span>`;
  const sp = h(`<span class="spacer"></span>`); b.appendChild(sp);
  const commit = h(`<button class="btn">Commit locally</button>`); commit.onclick = () => doCommit(false); b.appendChild(commit);
  if (g.can_push_live) { const cp = h(`<button class="btn primary">Commit &amp; push to main</button>`); cp.onclick = () => doCommit(true); b.appendChild(cp); }
  else b.appendChild(h(`<span class="sub">on <code>${esc(g.branch || "?")}</code> — push from a main checkout to go live</span>`));
}
async function doCommit(push) {
  if (push && !confirm("Commit config.yml and PUSH to the live branch?")) return;
  const r = await post("/api/git/commit", { push, confirm: true });
  if (r.ok) { toast(r.pushed ? "Committed & pushed" : "Committed locally"); await refresh(); renderBanner(); }
  else toast(r.error || "commit failed", true);
}

async function refresh() {
  SUMMARY = await api("/api/summary");
  if (SUMMARY.error) { toast(SUMMARY.error, true); return; }
  renderHeader(); renderBanner();
}

/* ---- helpers ------------------------------------------------------------ */
function card(title, bodyHtml) { return `<div class="card"><h3>${title}</h3>${bodyHtml}</div>`; }
function meter(label, pct, valText, cls) {
  const c = cls || (pct >= 90 ? "bad" : pct >= 75 ? "warn" : "");
  return `<div class="meter"><div class="top"><span>${esc(label)}</span><b>${valText}</b></div>
    <div class="bar"><i class="${c}" style="width:${Math.max(0, Math.min(100, pct || 0))}%"></i></div></div>`;
}

const RENDER = {};

/* ---- OVERVIEW ----------------------------------------------------------- */
RENDER.overview = async () => {
  const v = $("#view"), s = SUMMARY;
  const hh = s.health || {}, c = s.cost || {}, sys = s.system || {}, sv = s.services || {}, m = s.meta || {};
  const flagsOn = Object.values((s.flags && s.flags.groups) || {}).flat().filter(f => f.value === true).length;
  const mem = sys.memory || {}, disk = sys.disk || {};
  v.innerHTML = `
    <div class="grid">
      ${card("Pipeline", `<div class="big" style="color:${hh.healthy ? "var(--ok)" : "var(--warn)"}">${hh.healthy ? "Healthy" : "Attention"}</div>
        <div class="sub">last run ${fmtAge(hh.age_hours)} ago · ${(hh.sources || {}).ok || 0}/${(hh.sources || {}).total || 0} sources</div>`)}
      ${card("Services", sv.available ? `<div class="big" style="color:${sv.healthy ? "var(--ok)" : "var(--bad)"}">${sv.ok_count}/${sv.total}</div><div class="sub">background services running</div>` : `<div class="big">—</div><div class="sub">server only</div>`)}
      ${card("Server", sys.available ? `<div class="big">${mem.used_pct != null ? mem.used_pct + "%" : "—"}<span class="sub"> memory</span></div><div class="sub">disk ${disk.used_pct != null ? disk.used_pct + "%" : "—"} · load ${sys.cpu && sys.cpu.load1 != null ? sys.cpu.load1.toFixed(2) : "—"}</div>` : `<div class="big">—</div><div class="sub">server only</div>`)}
      ${card("Est. AI cost", `<div class="big">${fmtUSD(c.monthly_usd)}<span class="sub"> /mo</span></div><div class="sub">${fmtUSD(c.effective_daily_usd)}/day</div>`)}
      ${card("Features on", `<div class="big">${flagsOn}</div><div class="sub">of your feature switches</div>`)}
      ${card("Analytics", `<div class="big" style="color:var(--ok);font-size:18px">Umami live</div><div class="sub">${m.integrations && m.integrations.umami ? "API connected" : "tag on every page"}</div>`)}
      ${card("Experiments", `<div class="big" style="color:${(s.experiments && s.experiments.ready_count) ? "var(--ok)" : "var(--text)"}">${(s.experiments && s.experiments.ready_count) || 0}<span class="sub"> ready</span></div><div class="sub">${s.experiments && s.experiments.soonest ? "next in " + s.experiments.soonest.days_until + "d" : (s.experiments && s.experiments.n ? s.experiments.n + " tracked" : "—")}</div>`)}
    </div>
    <div class="section">Quick actions</div>
    <div id="qa"></div>`;
  const qa = $("#qa");
  const rebuild = h(`<button class="btn primary">▶ Rebuild &amp; deploy now</button>`);
  rebuild.onclick = () => dispatch("daily.yml"); rebuild.disabled = !m.has_token; qa.appendChild(rebuild);
  const redeploy = h(`<button class="btn" style="margin-left:8px">⟳ Redeploy site only</button>`);
  redeploy.onclick = () => dispatch("pages.yml"); redeploy.disabled = !m.has_token; qa.appendChild(redeploy);
  const probe = h(`<button class="btn" style="margin-left:8px">◎ Check all sites are up</button>`);
  probe.onclick = () => go("system"); qa.appendChild(probe);
  if (!m.has_token) qa.appendChild(h(`<div class="sub" style="margin-top:8px">The rebuild/deploy buttons need a GitHub access token (<code>GH_TOKEN</code>, with Actions-write permission) set on the server.</div>`));
};

/* ---- EXPERIMENTS & DATA COLLECTION -------------------------------------- */
const EXP_STATUS_PILL = (s) => {
  const cls = s === "validated" ? "s-ok" : (s === "measuring" || s === "proven") ? "s-warn" : s === "blocked" ? "s-bad" : "s-mut";
  return `<span class="statpill ${cls}">${esc(s || "?")}</span>`;
};
const EXP_DUE = (e) => {
  if (e.ready) return `<b style="color:var(--ok)">ready ✓</b>`;
  if (e.days_until == null) return `<span class="sub">${esc(e.come_back_on || "—")}</span>`;
  if (e.days_until <= 0) return `<b style="color:var(--ok)">due now</b>`;
  const soon = e.days_until <= 7;
  return `<span style="color:${soon ? "var(--warn)" : "var(--text)"}">${e.days_until}d</span> <span class="sub mono">${esc((e.come_back_on || "").slice(0, 10))}</span>`;
};
RENDER.experiments = async () => {
  const v = $("#view");
  const d = await api("/api/experiments");
  if (!d.ok) {
    v.innerHTML = card("Experiments & data collection", `<div class="sub">${esc(d.reason || "not available")}</div>`);
    return;
  }
  const exps = d.experiments || [];
  const ready = exps.filter(e => e.ready);
  let html = `<div class="sub" style="margin-bottom:10px">Ongoing experiments and long-running data collections. Each one shows the exact date to come back and take the next step. This list is refreshed automatically every night.</div>
    <div class="grid">
      ${card("Tracked", `<div class="big">${d.n}</div><div class="sub">experiments running</div>`)}
      ${card("Results ready", `<div class="big" style="color:${d.ready_count ? "var(--ok)" : "var(--text)"}">${d.ready_count}</div><div class="sub">come back for the next step</div>`)}
      ${card("Last updated", `<div class="big" style="font-size:18px" class="mono">${esc(d.as_of || "—")}</div><div class="sub">today ${esc(d.today || "")}</div>`)}
    </div>`;
  if (ready.length) {
    html += `<div class="section">🔔 Ready for review <span class="cnt">${ready.length}</span></div>
      <div class="grid">${ready.map(e => `<div class="card ready"><h3>${esc(e.name)}</h3>
        <div class="sub">${esc(e.what || "")}</div>
        <div class="kv" style="margin-top:8px"><span>Status</span>${EXP_STATUS_PILL(e.status)}</div>
        ${e.phase_hint ? `<div class="kv"><span>Next</span><b>${esc(e.phase_hint)}</b></div>` : ""}
        <div class="note" style="margin-top:6px">${esc(e.next_step || "")}</div>
        ${e.state ? `<div class="note mono muted">${esc(e.state)}</div>` : ""}
        ${e.surfaced ? `<div class="note mono muted">↳ ${esc(e.surfaced)}</div>` : ""}</div>`).join("")}</div>`;
  }
  html += `<div class="section">All experiments <span class="cnt">${exps.length}</span></div>
    <table class="exp-table"><thead><tr><th>Experiment</th><th>Type</th><th>Status</th><th>How often</th><th class="r">Come back</th><th>Next step</th><th>Your action</th></tr></thead><tbody>
    ${exps.map(e => `<tr${e.ready ? ' class="hl"' : ""}>
      <td><b>${esc(e.name)}</b><div class="sub">${esc(e.what || "")}</div><div class="note mono muted">${esc(e.source || "")}</div></td>
      <td class="sub">${esc(e.kind || "")}</td>
      <td>${EXP_STATUS_PILL(e.status)}</td>
      <td class="sub">${esc(e.cadence || "")}</td>
      <td class="r">${EXP_DUE(e)}</td>
      <td class="sub" style="max-width:340px">${esc(e.next_step || "")}${e.state ? `<div class="note mono muted">${esc(e.state)}</div>` : ""}</td>
      <td class="exp-actions">
        <button class="btn exp-act-btn" data-exp-id="${esc(e.id || "")}" data-action="acted">Acted</button>
        <button class="btn exp-act-btn" data-exp-id="${esc(e.id || "")}" data-action="dismissed">Dismiss</button>
        <button class="btn exp-act-btn" data-exp-id="${esc(e.id || "")}" data-action="snoozed">Snooze</button>
        <button class="btn exp-act-btn" data-exp-id="${esc(e.id || "")}" data-action="overrode">Override</button>
      </td></tr>`).join("")}
    </tbody></table>
    ${d.note ? `<div class="sub" style="margin-top:10px">${esc(d.note)}</div>` : ""}`;
  v.innerHTML = html;
  // L4 action capture: wire up Acted/Dismiss/Snooze buttons (NW Rails PR-8)
  v.querySelectorAll(".exp-act-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const expId = btn.dataset.expId;
      const action = btn.dataset.action;
      const note = window.prompt(`Direction note (optional, ≤280 chars) for "${action}" on ${expId}:`);
      if (note === null) return; // user cancelled
      const r = await post("/api/actions", { surface: expId, action, direction_note: note });
      if (r.ok) toast(`Logged: ${action} — ${expId}`);
      else toast(r.error || "action log failed", true);
    });
  });
};

/* ---- SITE ACCESS GATE ----------------------------------------------------- */
/* Admin panel for the IP/country blocklist gate (app/gate.py).
   The gate is OFF by default (enabled=false => allow everyone, fail-open).
   Operator can block IPs/CIDRs and countries; own IP is always in allow_ips. */

// ISO-3166-1 alpha-2 — one static array; names via Intl.DisplayNames (no hardcoded CJK).
const SG_COUNTRY_CODES = [
  "AF","AX","AL","DZ","AS","AD","AO","AI","AQ","AG","AR","AM","AW","AU","AT","AZ",
  "BS","BH","BD","BB","BY","BE","BZ","BJ","BM","BT","BO","BQ","BA","BW","BV","BR",
  "IO","BN","BG","BF","BI","CV","KH","CM","CA","KY","CF","TD","CL","CN","CX","CC",
  "CO","KM","CG","CD","CK","CR","CI","HR","CU","CW","CY","CZ","DK","DJ","DM","DO",
  "EC","EG","SV","GQ","ER","EE","SZ","ET","FK","FO","FJ","FI","FR","GF","PF","TF",
  "GA","GM","GE","DE","GH","GI","GR","GL","GD","GP","GU","GT","GG","GN","GW","GY",
  "HT","HM","VA","HN","HK","HU","IS","IN","ID","IR","IQ","IE","IM","IL","IT","JM",
  "JP","JE","JO","KZ","KE","KI","KP","KR","KW","KG","LA","LV","LB","LS","LR","LY",
  "LI","LT","LU","MO","MG","MW","MY","MV","ML","MT","MH","MQ","MR","MU","YT","MX",
  "FM","MD","MC","MN","ME","MS","MA","MZ","MM","NA","NR","NP","NL","NC","NZ","NI",
  "NE","NG","NU","NF","MK","MP","NO","OM","PK","PW","PS","PA","PG","PY","PE","PH",
  "PN","PL","PT","PR","QA","RE","RO","RU","RW","BL","SH","KN","LC","MF","PM","VC",
  "WS","SM","ST","SA","SN","RS","SC","SL","SG","SX","SK","SI","SB","SO","ZA","GS",
  "SS","ES","LK","SD","SR","SJ","SE","CH","SY","TW","TJ","TZ","TH","TL","TG","TK",
  "TO","TT","TN","TR","TM","TC","TV","UG","UA","AE","GB","US","UM","UY","UZ","VU",
  "VE","VN","VG","VI","WF","EH","YE","ZM","ZW"
];

/* Pure-JS IPv4 CIDR membership check. Returns true if ip (dotted-decimal) is
   inside the CIDR entry. Falls back to string equality for IPv6 / anything else.
   Never uses eval or new Function. */
function ipInList(ip, entries) {
  if (!entries || !entries.length) return false;
  function ip4ToUint32(s) {
    const p = s.split(".").map(Number);
    if (p.length !== 4 || p.some(x => isNaN(x) || x < 0 || x > 255)) return null;
    return ((p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]) >>> 0;
  }
  const ipU32 = ip4ToUint32(ip);
  for (const entry of entries) {
    if (entry === ip) return true;
    if (ipU32 !== null && entry.includes("/")) {
      try {
        const [base, bits] = entry.split("/");
        const prefix = parseInt(bits, 10);
        if (isNaN(prefix) || prefix < 0 || prefix > 32) continue;
        const baseU32 = ip4ToUint32(base);
        if (baseU32 === null) continue;
        const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
        if ((ipU32 & mask) === (baseU32 & mask)) return true;
      } catch (_) { /* ignore malformed */ }
    }
  }
  return false;
}

RENDER.site_gate = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="sub">Loading gate status…</div>`;

  let d;
  try { d = await api("/api/site_gate"); } catch (e) {
    v.innerHTML = card("Site Access", `<div class="sub">Load error: ${esc(String(e))}</div>`);
    return;
  }
  if (!d.ok) {
    v.innerHTML = card("Site Access Gate", `<div class="sub s-bad">${esc(d.error || "unavailable")}</div>`);
    return;
  }

  const rules      = d.rules       || {};
  const gs         = d.gate_status || {};
  const cd         = gs.country_detection || {};
  const yourIP     = d.your_ip  || "—";
  const siteUrl    = d.site_url || "https://mastermind-x.com";
  const blockedIps = rules.blocked_ips       || [];
  const blockedCC  = rules.blocked_countries || [];
  const allowIps   = rules.allow_ips         || [];

  // ── Country detection badge ──────────────────────────────────────────────
  let cdBadge = "";
  if (!gs.ok) {
    cdBadge = `<span class="statpill s-mut">gate status unavailable — macro-api not reachable</span>`;
  } else {
    const src = cd.source || "unavailable";
    if (src.startsWith("header:")) {
      const hdr = src.slice(7);
      cdBadge = `<span class="statpill s-ok">Country detection active (via ${esc(hdr)})</span>`;
    } else if (src === "geoip") {
      cdBadge = `<span class="statpill s-ok">Active (GeoIP database)</span>`;
    } else {
      cdBadge = `<span class="statpill s-warn">Not detecting yet — add the EdgeOne country header (see setup)</span>`;
    }
  }
  const geoDbBadge = cd.geoip_db
    ? `<span class="statpill s-ok" style="font-size:11px">GeoIP db: present</span>`
    : `<span class="statpill s-mut" style="font-size:11px">GeoIP db: absent</span>`;
  const lastSeen = cd.last_seen_country
    ? `<span class="sub" style="margin-left:8px">last seen: <b>${esc(cd.last_seen_country)}</b></span>` : "";

  // ── Self-lockout check (real CIDR for IPv4, string-eq fallback for IPv6) ─
  const selfLocked = ipInList(yourIP, blockedIps);
  const selfWarn = selfLocked
    ? `<div class="sg-warn">⚠ Your current IP is in the block list. You'd still reach this admin console (it's never gated), but you would be blocked from the public site — it stays in the allow-list to protect you.</div>`
    : "";

  // ── Build country grid ───────────────────────────────────────────────────
  let dnEn, dnZh;
  try { dnEn = new Intl.DisplayNames(["en"], { type: "region" }); } catch (_) { dnEn = null; }
  try { dnZh = new Intl.DisplayNames(["zh"], { type: "region" }); } catch (_) { dnZh = null; }
  function sgCountryNames(code) {
    const en = dnEn ? (dnEn.of(code) || code) : code;
    let zh = code;
    try { zh = dnZh ? (dnZh.of(code) || code) : code; } catch (_) {}
    return { en, zh };
  }

  const blockedCCSet = new Set(blockedCC);
  const countryItems = SG_COUNTRY_CODES.map(cc => {
    const { en, zh } = sgCountryNames(cc);
    const on = blockedCCSet.has(cc);
    return `<button class="sg-cc-btn${on ? " sg-cc-on" : ""}" data-cc="${esc(cc)}" title="${esc(en)} / ${esc(zh)}">
      <span class="sg-cc-code">${esc(cc)}</span>
      <span class="sg-cc-en">${esc(en)}</span>
      ${en !== zh ? `<span class="sg-cc-zh">${esc(zh)}</span>` : ""}
    </button>`;
  }).join("");

  // ── Allow-IP chips ───────────────────────────────────────────────────────
  let currentAllowIps = [...allowIps];
  function allowChipHtml(ip) {
    return `<span class="sg-ip-chip" data-aip="${esc(ip)}">${esc(ip)}<button class="sg-ip-rm" data-aip="${esc(ip)}" title="Remove">✕</button></span>`;
  }

  // ── Blocked-IP chips ─────────────────────────────────────────────────────
  let currentBlockedIps = [...blockedIps];
  function blockedChipHtml(ip) {
    return `<span class="sg-ip-chip" data-bip="${esc(ip)}">${esc(ip)}<button class="sg-ip-rm" data-bip="${esc(ip)}" title="Remove">✕</button></span>`;
  }

  v.innerHTML = `
    <div class="grid">
      ${card("Master switch", `
        <div class="sg-toggle-row">
          <label class="switch"><input type="checkbox" id="sgEnabled"${rules.enabled ? " checked" : ""}><span class="slider"></span></label>
          <div>
            <b id="sgEnabledLabel">${rules.enabled ? "On — visitors matching a rule below see the coming-soon page." : "Off — everyone can access the site."}</b>
            <div class="sub" style="margin-top:4px">Off = fail-open. Disabling never exposes admin; it only bypasses the public-site gate.</div>
          </div>
        </div>
      `)}
      ${card("Country detection", `
        <div style="display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:6px">
          ${cdBadge}${lastSeen}${geoDbBadge}
        </div>
        <div class="sub">Source resolved on the last /api/gate/check call. Configure via EdgeOne: add <b>EO-Client-IPCountry</b> header.</div>
      `)}
      ${card("Your IP", `
        <div class="big mono" style="font-size:16px">${esc(yourIP)}</div>
        ${selfWarn}
        <div class="sub" style="margin-top:6px">Your IP is auto-added to the allow-list on every save so you can never lock yourself out.</div>
      `)}
    </div>

    <div class="section">IP Blocklist <span class="cnt" id="sgBlockCount">${blockedIps.length}</span></div>
    <div class="card">
      <div class="sg-ip-add" style="margin-bottom:8px">
        <input id="sgBlockIPInput" class="inp" style="flex:1;font-family:var(--mono);font-size:13px" placeholder="1.2.3.4 or 203.0.113.0/24 (IPv4 CIDR or IPv6)">
        <button class="btn" id="sgBlockIPAdd">Add</button>
      </div>
      <div id="sgBlockIPList" style="display:flex;flex-wrap:wrap;gap:6px">
        ${blockedIps.map(ip => blockedChipHtml(ip)).join("")}
        ${blockedIps.length === 0 ? `<span class="sub muted">No IPs blocked</span>` : ""}
      </div>
    </div>

    <div class="section">Allow-list (bypass) <span class="cnt" id="sgAllowCount">${allowIps.length}</span></div>
    <div class="card">
      <div class="sub" style="margin-bottom:8px">Always allowed (bypass every block). Your current IP is auto-added. Remove stale entries here.</div>
      <div id="sgAllowIPList" style="display:flex;flex-wrap:wrap;gap:6px">
        ${allowIps.map(ip => allowChipHtml(ip)).join("")}
        ${allowIps.length === 0 ? `<span class="sub muted">None</span>` : ""}
      </div>
    </div>

    <div class="section">Country Blocklist <span class="cnt" id="sgCCCount">${blockedCCSet.size}</span></div>
    <div class="card">
      <div class="sub" style="margin-bottom:8px">Click to toggle. Names via browser Intl.DisplayNames — no hardcoded CJK.</div>
      <input id="sgCCFilter" class="inp" style="width:100%;margin-bottom:10px;font-size:13px" placeholder="Filter countries…">
      <div id="sgCCGrid" class="sg-cc-grid">${countryItems}</div>
    </div>

    <div style="margin-top:18px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <button class="btn btn-primary" id="sgSave">Save</button>
      <a class="btn" href="${esc(siteUrl)}/coming-soon.html" target="_blank" rel="noopener">Preview coming-soon page</a>
      <span class="sub" id="sgSaveStatus"></span>
    </div>
    ${rules.updated_at ? `<div class="sub" style="margin-top:8px">Last saved: <b>${esc(rules.updated_at)}</b></div>` : ""}
  `;

  // ── Enable toggle label ──────────────────────────────────────────────────
  const enabledCb = $("#sgEnabled");
  const enabledLbl = $("#sgEnabledLabel");
  enabledCb.addEventListener("change", () => {
    enabledLbl.textContent = enabledCb.checked
      ? "On — visitors matching a rule below see the coming-soon page."
      : "Off — everyone can access the site.";
  });

  // ── Blocked IP management ────────────────────────────────────────────────
  function refreshBlockCount() {
    const el = $("#sgBlockCount");
    if (el) el.textContent = currentBlockedIps.length;
  }
  function rebuildBlockedList() {
    const el = $("#sgBlockIPList");
    if (!el) return;
    if (currentBlockedIps.length === 0) {
      el.innerHTML = `<span class="sub muted">No IPs blocked</span>`;
    } else {
      el.innerHTML = currentBlockedIps.map(ip => blockedChipHtml(ip)).join("");
      el.querySelectorAll(".sg-ip-rm[data-bip]").forEach(btn => {
        btn.addEventListener("click", () => {
          currentBlockedIps = currentBlockedIps.filter(x => x !== btn.dataset.bip);
          rebuildBlockedList(); refreshBlockCount();
        });
      });
    }
    refreshBlockCount();
  }
  // wire initial remove buttons
  v.querySelectorAll(".sg-ip-rm[data-bip]").forEach(btn => {
    btn.addEventListener("click", () => {
      currentBlockedIps = currentBlockedIps.filter(x => x !== btn.dataset.bip);
      rebuildBlockedList(); refreshBlockCount();
    });
  });
  const blockIPInput = $("#sgBlockIPInput");
  $("#sgBlockIPAdd").addEventListener("click", () => {
    const val = (blockIPInput.value || "").trim();
    if (!val || currentBlockedIps.includes(val)) { blockIPInput.value = ""; return; }
    currentBlockedIps.push(val);
    blockIPInput.value = "";
    rebuildBlockedList();
  });
  blockIPInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); $("#sgBlockIPAdd").click(); } });

  // ── Allow-IP management ──────────────────────────────────────────────────
  function refreshAllowCount() {
    const el = $("#sgAllowCount");
    if (el) el.textContent = currentAllowIps.length;
  }
  function rebuildAllowList() {
    const el = $("#sgAllowIPList");
    if (!el) return;
    if (currentAllowIps.length === 0) {
      el.innerHTML = `<span class="sub muted">None</span>`;
    } else {
      el.innerHTML = currentAllowIps.map(ip => allowChipHtml(ip)).join("");
      el.querySelectorAll(".sg-ip-rm[data-aip]").forEach(btn => {
        btn.addEventListener("click", () => {
          currentAllowIps = currentAllowIps.filter(x => x !== btn.dataset.aip);
          rebuildAllowList(); refreshAllowCount();
        });
      });
    }
    refreshAllowCount();
  }
  v.querySelectorAll(".sg-ip-rm[data-aip]").forEach(btn => {
    btn.addEventListener("click", () => {
      currentAllowIps = currentAllowIps.filter(x => x !== btn.dataset.aip);
      rebuildAllowList(); refreshAllowCount();
    });
  });

  // ── Country toggle ───────────────────────────────────────────────────────
  v.querySelectorAll(".sg-cc-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const cc = btn.dataset.cc;
      if (blockedCCSet.has(cc)) { blockedCCSet.delete(cc); btn.classList.remove("sg-cc-on"); }
      else                       { blockedCCSet.add(cc);    btn.classList.add("sg-cc-on"); }
      const el = $("#sgCCCount"); if (el) el.textContent = blockedCCSet.size;
    });
  });

  // Country filter
  $("#sgCCFilter").addEventListener("input", function() {
    const q = this.value.toLowerCase();
    v.querySelectorAll(".sg-cc-btn").forEach(btn => {
      const match = !q || btn.textContent.toLowerCase().includes(q) || btn.dataset.cc.toLowerCase().includes(q);
      btn.style.display = match ? "" : "none";
    });
  });

  // ── Save ─────────────────────────────────────────────────────────────────
  const saveBtn = $("#sgSave");
  const saveStatus = $("#sgSaveStatus");
  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    if (saveStatus) saveStatus.textContent = "Saving…";

    const r = await post("/api/site_gate/save", {
      enabled:            enabledCb.checked,
      blocked_ips:        [...currentBlockedIps],
      blocked_countries:  [...blockedCCSet],
      allow_ips:          [...currentAllowIps],
    });

    saveBtn.disabled = false;
    if (r.ok) {
      if (saveStatus) saveStatus.textContent = "";
      const warnSuffix = r.warnings && r.warnings.length
        ? ` (${r.warnings.length} warning${r.warnings.length > 1 ? "s" : ""})`
        : "";
      toast("Gate rules saved" + warnSuffix);
      if (r.warnings && r.warnings.length) r.warnings.forEach(w => toast(w, true));
      await RENDER.site_gate();
    } else {
      if (saveStatus) saveStatus.textContent = r.error || "save failed";
      toast(r.error || "save failed", true);
    }
  });
};

/* ---- BTC OVERRIDE (owner view — Override-Registry W3, D2/D3) ------------- */
/* The full honesty payload the subscriber "Proprietary cycle timer" scrub hides.
   OWNER-ONLY (D2). Both-sides framing, numbers only, NO action affordances (D3). */
const EVAL_PILL = (s) => {
  const cls = s === "evaluable" ? "s-ok" : s === "in_window" ? "s-warn" : "s-bad";
  const lbl = s === "evaluable" ? "can trigger" : s === "in_window" ? "can trigger (in window)" : "can't trigger yet";
  return `<span class="statpill ${cls}">${esc(lbl)}</span>`;
};
const LEVEL_PILL = (l) => `<span class="statpill ${l === "ok" ? "s-ok" : l === "watch" ? "s-warn" : "s-bad"}">${esc(l || "?")}</span>`;
function shadowSvg(series) {
  if (!series || series.length < 2) return "";
  const w = 640, hh = 90, pad = 4;
  const vals = series.flatMap(p => [p.gated, p.raw]);
  const lo = Math.min(...vals), hi = Math.max(...vals), span = (hi - lo) || 1;
  const x = (i) => pad + i * (w - 2 * pad) / (series.length - 1);
  const y = (v) => hh - pad - (v - lo) * (hh - 2 * pad) / span;
  const line = (k) => series.map((p, i) => `${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${w} ${hh}" style="width:100%;height:90px;display:block" preserveAspectRatio="none" role="img" aria-label="gated vs ungated equity">
    <polyline points="${line("raw")}" fill="none" stroke="var(--warn)" stroke-width="1.8"/>
    <polyline points="${line("gated")}" fill="none" stroke="var(--ok)" stroke-width="1.8"/>
  </svg>
  <div class="sub" style="display:flex;gap:14px"><span><i style="display:inline-block;width:10px;height:3px;background:var(--ok);vertical-align:middle"></i> our actual position</span>
  <span><i style="display:inline-block;width:10px;height:3px;background:var(--warn);vertical-align:middle"></i> what the model wanted</span></div>`;
}
RENDER.vector = async () => {
  const v = $("#view");
  const d = await api("/api/vector_override");
  if (!d.ok) { v.innerHTML = card("BTC Override — owner view", `<div class="sub">${esc(d.reason || "not available")}</div>`); return; }
  const o = d.override || {}, cf = d.counterfactual || {}, pv = d.provenance || {}, fl = d.falsifiers || {}, sh = d.shadow || {};
  const re = d.reentry || null;
  const rawOpt = cf.raw_pct && cf.raw_pct.optimal, gatedOpt = cf.gated_pct && cf.gated_pct.optimal;
  const damp = (pv.dampening_path_pct || []).map(x => `${x}%`).join(" → ");
  // D5 (owner decision 2026-07-02): a PRE-WINDOW fresh MVRV-Z<0 print is an owner
  // ALERT only — never a sleeve, never sizing. Banner + numbers, no buttons (D3).
  const d5Banner = re && re.pre_window_mvrv_fire ? `
    <div class="card" style="border-color:var(--warn);margin-bottom:10px">
      <div class="big" style="color:var(--warn)">ALERT — an early "cheap Bitcoin" signal fired ${esc(re.pre_window_mvrv_fire)}</div>
      <div class="sub">This happened before the planned buy-back window opens (${esc(re.window_start || "?")}). It's a heads-up only — nothing is bought early; the position stays 100% in cash until the scheduled dates. This early signal is still only being tracked, not acted on.</div>
    </div>` : "";
  const reSection = re ? `
    <div class="section">Planned buy-back schedule</div>
    <div class="card">
      <div class="kv"><span>Status</span><b><span class="statpill ${re.state === "fully_released" ? "s-ok" : re.state === "window_open_filling" ? "s-warn" : re.state === "armed_pending_window" ? "s-ok" : "s-bad"}">${esc(re.state || "?")}</span></b></div>
      <div class="kv"><span>Buy-back window</span><b>${esc(re.window_start || "—")} → ${esc(re.window_end || "—")}</b></div>
      <div class="kv"><span>Amount released so far</span><b>${re.release_frac == null ? "—" : Math.round(100 * re.release_frac) + "%"}</b></div>
      ${re.halt_from ? `<div class="kv"><span>MANUALLY PAUSED</span><b style="color:var(--bad)">paused since ${esc(re.halt_from)}</b></div>` : ""}
      <table style="margin-top:8px"><thead><tr><th>Step</th><th>Size</th><th>Planned date</th><th>Done?</th><th>Trigger</th></tr></thead><tbody>
        ${(re.schedule || []).map(t => `<tr><td>${t.tranche}</td><td>${Math.round(100 * t.weight)}%</td><td class="mono">${esc(t.scheduled || "—")}</td>
          <td>${t.filled ? `<span class="statpill s-ok">${esc(t.fill_date || "done")}</span>` : `<span class="statpill s-warn">pending</span>`}</td>
          <td class="sub">${esc(t.cause || "")}</td></tr>`).join("")}
      </tbody></table>
      <div class="sub" style="margin-top:8px">Early buy-back speed-up: ${re.accelerator && re.accelerator.enabled ? "on" : "off"} · valuation score (MVRV-Z) ${re.accelerator ? re.accelerator.mvrv_z_last ?? "—" : "—"} · bottoming pressure ${re.accelerator ? re.accelerator.bottom_pressure_last ?? "—" : "—"}</div>
      ${re.dat_advisory ? `<div class="sub">Distance to forced selling by Bitcoin-treasury companies: ${re.dat_advisory.forced_sell_distance_pct ?? "—"}% · info only${re.dat_advisory.stale ? ` · <b style="color:var(--warn)">data is stale (${re.dat_advisory.age_days ?? "?"}d old)</b>` : ""}</div>` : ""}
      <div class="note" style="margin-top:6px">${esc(re.owner_note || "")}</div>
      <div class="note mono muted">as of ${esc(re.asof || "?")} · to pause buy-backs, edit the halt switch in config (this page only shows numbers)</div>
    </div>` : "";
  v.innerHTML = `
    <div class="sub" style="margin-bottom:10px">Your private view of the Bitcoin allocation override. Subscribers only see a "Proprietary cycle timer" label — this page shows the full honest picture behind it: the numbers both for and against the call. Read-only (no buttons to act on here).${d.stub ? ` <span class="statpill s-warn">placeholder data — will be replaced with measured results</span>` : ""}</div>
    ${d5Banner}
    <div class="grid">
      ${card("Override status", `<div class="big" style="color:${o.active ? "var(--warn)" : "var(--ok)"}">${o.active ? "ACTIVE" : "off"}</div>
        <div class="sub">${esc(o.id || "?")} · ${o.active ? `unlocks ${esc(o.release || "?")}` : "not engaged"} · <b>${o.graded ? "scored" : "never scored yet"}</b></div>
        <div class="note">${esc(o.status || "")}</div>`)}
      ${card("Model vs. what we allow", `<div class="big">${rawOpt == null ? "—" : rawOpt + "%"}<span class="sub"> vs ${gatedOpt == null ? "—" : gatedOpt + "%"}</span></div>
        <div class="sub">what the model would hold vs what we actually allow · this year the model averaged ${cf.ytd_raw_mean_pct == null ? "—" : cf.ytd_raw_mean_pct + "%"} · it wanted more than 0% on ${cf.ytd_raw_days_gt0 ?? "—"} of ${cf.ytd_days ?? "—"} days</div>
        <div class="note">${esc(cf.raw_source || "")}${cf.parity_ok === false ? ' · <b style="color:var(--bad)">MISMATCH — this recalculation no longer matches the live model</b>' : ""}</div>`)}
      ${card("Warning signs", `<div class="big" style="color:${fl.evaluable === fl.total ? "var(--ok)" : "var(--warn)"}">${esc(fl.headline || "—")}</div>
        <div class="sub">${(fl.items || []).filter(i => i.level !== "ok").length ? (fl.items || []).filter(i => i.level !== "ok").length + " warning(s) active" : "all clear"} — but a warning sign that can't actually trigger tells you nothing</div>`)}
      ${card("Evidence behind the call", `<div class="big">${pv.basis_n ?? "?"} cases</div>
        <div class="sub">confidence trimmed by ${esc(damp || "—")} · timing fit ±${pv.pivot_fit_mae_days ?? "—"} days <b>(fitted on past data)</b></div>`)}
    </div>
    <div class="section">Live tracking — what we hold vs what the model wanted ${sh.since ? `since ${esc(sh.since)}` : ""}</div>
    <div class="card">
      ${sh.ok ? `
        ${shadowSvg(sh.series)}
        <div class="kv"><span>Our actual return</span><b>${sh.gated_return_pct}%</b></div>
        <div class="kv"><span>Model's return (if we'd followed it)</span><b>${sh.raw_return_pct}%</b></div>
        <div class="kv"><span>Cost of the override (what we gave up)</span><b style="color:${(sh.regret_pp || 0) > 0 ? "var(--warn)" : "var(--ok)"}">${sh.regret_pp > 0 ? "+" : ""}${sh.regret_pp}pp</b></div>
        ${(sh.prior_cycles || []).map(p => `<div class="kv"><span>${p.year} at this point / by unlock date</span><b>${p.raw_at_same_elapsed_pct > 0 ? "+" : ""}${p.raw_at_same_elapsed_pct}% / ${p.raw_by_release_pct > 0 ? "+" : ""}${p.raw_by_release_pct}%</b></div>`).join("")}
        <div class="note" style="margin-top:8px">${esc(sh.framing || "")}</div>
      ` : `<div class="sub">${esc(sh.reason || "no shadow data")}</div>`}
    </div>
    ${reSection}
    <div class="section">Warning signs — status, and whether they can even trigger</div>
    <table><thead><tr><th>Warning sign</th><th>Status</th><th>Can it trigger?</th><th>What it says</th></tr></thead><tbody>
      ${(fl.items || []).map(i => `<tr><td><b>${esc(i.key)}</b></td><td>${LEVEL_PILL(i.level)}</td><td>${EVAL_PILL(i.evaluability)}<div class="note" style="max-width:340px">${esc(i.why || "")}</div></td>
        <td class="sub" style="max-width:380px">${esc(i.text || "")}</td></tr>`).join("")}
    </tbody></table>
    <div class="sub" style="margin-top:8px">${esc(fl.note || "")}</div>
    <div class="section">Where these numbers come from</div>
    <div class="grid">
      ${card("Past midterm-election-year selloffs", `${(pv.prior_bears || []).map(b => `<div class="kv"><span class="mono">${esc(b.top)} → ${esc(b.bottom)}</span><b>${Math.round(100 * b.depth)}% drop · ${b.down_days} days</b></div>`).join("") || "<span class='muted'>—</span>"}
        <div class="note" style="margin-top:6px">${esc(pv.basis || "")}</div>`)}
      ${card("Caveats", `<div class="note">${esc(pv.dampening_note || "")}</div><div class="note" style="margin-top:6px">${esc(pv.pivot_fit_note || "")}</div>
        <div class="note" style="margin-top:6px">${esc(d.stub_note || "")}</div>
        <div class="note mono muted" style="margin-top:6px">generated ${esc(d.generated_at || "?")} · ${fmtAge(d.age_hours)} old · defined in ${esc(o.declared_in || "")}</div>`)}
    </div>`;
};

/* ---- ANALYTICS (first-party, self-hosted) ------------------------------------
   Reads our own analytics_events / search_events / ip_geo via /api/analytics/fp/*.
   Sub-tabs lazy-load each panel; Umami/GA4 remain as a third-party cross-check.
   Session replay + visitor identity are hash sub-pages (#/session/… , #/visitor/…). */
let AN = { tab: "overview", days: 7 };
const AN_TABS = [["overview", "Overview"], ["visitors", "Visitors"], ["sessions", "Sessions"], ["pages", "Pages"], ["geo", "Map"], ["flow", "Flow"], ["terminal", "Terminal"]];
const AN_RENDER = {};

function anNotReady(d) {
  return `<div class="card"><h3>First-party analytics — not connected</h3>
    <div class="sub">${esc(d.reason || d.error || "no data yet — the tracker + tables may not be live")}</div>
    <ol class="steps" style="margin-top:10px">${(d.setup_steps || []).map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>`;
}
/* horizontal ranked bars. labelFn(row)->html, valKey numeric; opt.fmt, opt.sub(row)->html */
function anBars(rows, labelFn, valKey, opt) {
  opt = opt || {};
  const fmt = opt.fmt || fmtNum;
  const max = Math.max(1, ...rows.map(r => Number(r[valKey]) || 0));
  return rows.map(r => {
    const val = Number(r[valKey]) || 0;
    const sub = opt.sub ? `<span class="an-bsub">${opt.sub(r)}</span>` : "";
    return `<div class="an-brow"><div class="an-blabel">${labelFn(r)}${sub}</div>
      <div class="an-btrack"><i style="width:${Math.round(val / max * 100)}%"></i></div><b class="an-bval">${fmt(val)}</b></div>`;
  }).join("") || `<div class="muted sub">no data yet</div>`;
}
/* equirectangular dot map (no world GeoJSON dependency): dot per city by lat/lon, sized by visitors */
const AN_WORLD_LAND = "M241,302L240,303L240,304L235,304L231,304L229,303L229,303L227,303L232,303L236,303L238,302L239,302L241,302Z M42,301L38,302L35,301L34,300L34,300L33,300L34,299L38,299L40,300L41,301L42,301Z M270,299L272,300L273,301L273,301L273,302L270,303L267,303L263,304L259,304L254,304L252,303L252,303L256,302L258,302L259,301L260,300L261,299L263,299L264,299L267,298L270,299Z M118,291L120,291L123,291L121,291L120,292L117,292L115,291L115,290L118,291Z M109,291L112,291L111,291L108,291L105,291L107,290L109,291Z M162,288L164,288L166,288L168,289L166,289L164,289L161,289L158,289L156,289L155,288L157,287L159,288L162,288Z M223,286L223,287L223,288L222,288L220,289L218,289L215,289L216,288L214,288L212,289L210,288L210,287L212,287L214,286L216,287L216,286L217,285L217,284L218,283L219,282L221,283L221,284L222,285L223,285L223,286Z M0,311L0,311L2,310L5,310L6,310L6,310L7,310L8,310L8,310L8,310L8,310L11,310L14,310L14,309L20,309L22,310L23,310L26,310L32,311L36,311L44,312L50,311L58,312L63,312L68,312L74,311L74,310L66,310L60,310L58,309L53,309L53,308L54,307L55,307L54,306L51,305L49,305L46,304L51,304L56,304L59,305L62,304L66,303L67,303L66,302L64,302L61,301L57,301L53,301L49,301L48,300L45,299L44,299L43,297L44,297L46,297L49,297L53,297L54,298L57,298L60,297L63,297L65,296L68,296L68,295L67,295L68,294L70,294L71,294L74,294L77,293L80,293L82,293L85,293L87,292L90,292L91,292L93,292L95,292L98,292L101,292L104,292L106,292L109,292L112,292L115,292L118,292L121,292L123,292L125,292L128,292L130,292L132,291L133,292L134,292L135,293L137,292L140,293L143,293L145,294L148,294L150,293L153,293L156,294L159,294L160,293L158,293L157,292L155,292L154,291L153,290L153,289L154,289L157,289L159,289L162,290L164,290L165,291L167,291L170,291L173,290L175,290L177,290L180,290L182,289L183,290L185,290L188,290L190,291L192,291L195,291L197,291L199,291L199,290L201,291L204,291L206,291L208,292L210,291L212,291L214,290L217,290L220,290L222,290L224,289L225,289L226,288L225,287L225,287L224,286L224,285L223,285L223,284L223,283L224,283L225,282L225,281L225,280L225,280L225,279L227,278L228,278L229,277L231,277L232,276L233,275L234,275L236,275L237,274L239,274L240,274L242,273L243,273L244,272L246,273L245,274L243,274L242,274L240,274L239,274L237,275L236,275L235,276L235,276L235,277L236,278L234,278L233,278L231,279L230,279L229,280L229,281L229,282L230,282L232,283L234,283L234,284L235,284L235,285L236,286L237,286L237,288L238,289L238,289L239,290L238,291L237,292L236,292L233,293L233,293L231,294L228,294L226,295L223,295L220,296L219,296L216,296L212,296L209,296L206,296L206,297L209,297L211,298L213,299L210,299L207,299L204,299L204,300L204,301L206,301L207,302L209,303L214,303L217,303L220,304L224,305L229,305L233,305L237,306L241,306L243,307L244,308L246,307L249,307L253,306L257,306L260,305L265,305L270,306L274,306L276,305L278,305L284,305L287,304L291,304L295,304L300,303L303,303L301,302L301,302L301,301L297,301L293,301L289,301L288,301L288,299L289,299L292,298L296,298L298,298L300,297L302,296L305,296L308,296L309,296L312,296L315,295L318,295L320,295L322,294L325,294L327,293L329,292L329,292L327,291L328,291L329,290L331,290L333,289L335,289L337,288L338,287L339,287L342,287L343,287L345,287L345,287L346,286L348,286L349,287L351,287L354,287L356,287L359,287L360,287L362,287L364,286L366,286L368,286L370,286L373,285L374,285L375,284L377,285L379,284L381,285L382,286L384,286L385,285L387,284L389,284L390,285L392,284L394,284L396,284L399,284L401,284L403,285L404,285L405,286L407,285L410,285L412,285L414,285L416,285L418,285L420,284L422,284L424,284L426,283L427,282L428,282L430,282L431,283L432,283L434,283L436,284L437,284L439,284L440,283L442,283L444,282L446,282L448,281L450,281L451,281L453,280L455,280L457,280L458,279L460,279L462,279L462,278L464,278L465,277L467,277L469,277L471,277L473,277L474,278L475,279L476,279L477,280L480,280L481,280L483,281L485,281L486,281L488,280L490,280L492,280L494,281L496,281L498,281L499,283L499,283L499,284L497,284L496,285L496,286L498,286L498,286L497,287L496,288L497,288L500,288L502,288L503,287L504,287L505,286L506,286L507,285L508,284L509,284L511,284L513,284L515,283L516,283L517,282L518,281L520,281L522,281L523,280L524,280L526,279L528,280L529,279L531,279L534,279L535,279L536,278L537,278L538,279L539,279L541,280L543,279L545,279L547,279L548,279L550,279L552,280L553,280L556,280L557,279L559,280L561,279L562,278L563,278L566,277L567,277L568,277L570,278L572,279L574,279L576,279L578,279L580,279L582,278L583,278L586,277L587,277L589,277L590,278L591,279L593,279L595,279L597,279L600,280L602,279L603,279L605,278L606,278L608,278L610,279L612,278L614,278L616,279L618,279L619,278L622,278L624,278L626,278L628,278L630,278L630,277L630,276L631,277L632,277L632,278L633,279L635,279L637,279L640,279L642,279L644,279L646,279L649,279L651,279L652,280L652,280L653,281L655,281L658,282L660,282L663,282L665,282L667,282L669,282L670,282L672,283L674,283L676,284L678,284L679,284L682,285L683,285L685,286L688,286L690,286L692,286L695,286L697,286L699,287L701,287L702,287L702,288L701,289L700,290L700,290L699,291L696,291L695,292L692,292L691,293L690,294L688,294L688,295L687,296L687,296L687,297L688,298L689,298L689,299L693,299L694,300L690,300L687,301L684,301L682,302L681,303L681,303L680,304L682,304L683,305L685,306L687,306L690,307L693,308L698,308L699,309L705,309L705,310L706,310L712,310L717,310L0,311Z M224,256L227,257L230,257L229,258L227,258L226,258L225,258L224,259L222,259L220,258L218,258L215,257L213,256L211,254L212,254L215,255L218,256L219,255L219,254L221,253L223,254L223,254L224,256Z M243,251L245,252L244,252L241,253L240,252L239,253L238,252L240,251L242,252L243,251Z M501,248L497,248L497,248L498,247L498,246L499,247L501,247L501,248L501,248Z M651,233L653,233L654,233L655,233L657,233L657,235L656,235L656,237L655,236L654,238L653,237L652,237L651,236L651,235L649,233L649,232L651,233Z M706,233L706,233L708,233L708,234L708,234L708,235L706,236L705,237L706,238L705,238L703,239L702,240L701,242L700,242L699,243L697,243L696,242L693,242L693,242L694,240L697,238L698,238L699,237L701,236L702,236L703,234L704,234L704,233L706,232L706,233Z M709,224L711,226L711,225L712,225L712,227L714,227L715,227L716,227L717,227L717,229L716,230L714,230L714,230L714,231L714,231L713,232L712,233L710,234L710,234L709,233L710,232L710,231L708,230L708,230L709,229L709,228L709,226L709,225L709,225L708,224L706,223L705,221L706,221L707,222L709,223L709,224Z M694,199L693,200L692,199L691,199L690,198L688,196L688,196L689,196L690,196L691,197L692,197L693,199L694,199Z M717,191L717,191L717,192L716,193L715,192L715,192L715,191L716,191L717,191Z M0,189L719,190L717,190L717,190L718,189L719,189L0,189L0,189L0,188L0,189L0,189Z M696,189L695,190L694,189L694,188L696,189Z M694,187L695,188L694,188L694,188L693,187L693,186L694,187Z M460,184L460,186L461,187L461,188L460,188L460,187L459,188L460,189L460,190L459,190L459,192L458,194L457,196L456,200L455,202L454,204L453,205L451,206L450,205L448,204L448,203L447,202L447,200L447,199L447,198L448,198L448,197L449,196L449,195L448,194L448,193L448,191L449,190L449,189L450,189L451,188L452,188L453,188L454,187L455,186L456,185L456,184L457,185L458,183L458,182L458,181L459,182L460,183L460,184Z M647,184L648,186L649,185L650,186L651,187L651,187L651,189L651,190L652,190L652,192L652,192L653,194L655,195L656,195L658,196L657,197L659,198L659,200L660,199L661,200L661,200L662,202L663,203L664,203L666,205L666,206L666,207L666,208L667,210L667,212L667,212L666,214L666,215L666,216L665,218L663,219L663,220L662,221L661,223L661,223L660,225L660,226L660,227L659,227L657,227L655,228L654,229L653,229L651,229L650,228L650,227L649,228L647,229L645,229L644,228L643,228L641,228L640,226L640,225L639,224L638,224L636,223L637,222L636,221L635,222L634,223L635,222L635,221L636,220L636,218L634,220L633,221L632,222L630,221L630,220L629,219L628,218L629,218L626,217L625,217L623,216L619,216L616,217L614,217L612,217L610,218L608,219L608,220L607,220L606,220L604,220L603,220L601,220L600,220L599,221L598,221L597,222L596,222L595,222L593,222L591,221L590,221L590,220L591,220L591,219L591,218L592,217L591,216L590,214L590,213L590,212L589,211L589,211L588,210L588,209L587,207L587,206L588,207L587,206L588,206L588,207L588,206L587,204L587,204L587,203L587,202L587,202L588,201L587,200L588,199L588,200L589,199L591,198L592,197L593,197L594,197L595,197L596,196L598,196L598,196L599,195L600,196L602,195L603,194L603,193L604,192L605,192L605,191L606,189L607,191L608,190L607,190L608,189L609,189L609,188L610,187L610,186L611,186L611,185L612,186L612,185L613,185L614,185L616,185L617,186L618,186L619,187L619,186L620,184L621,184L620,183L621,182L622,182L623,182L625,182L625,181L624,180L625,180L626,180L627,181L629,181L629,181L631,182L632,181L633,181L633,181L634,182L633,183L633,184L632,184L632,184L632,185L631,186L631,187L633,188L634,188L635,189L637,190L637,190L638,190L639,191L640,191L642,191L642,190L643,189L643,188L643,187L643,186L643,185L643,184L643,183L644,183L643,182L644,181L644,180L644,180L645,179L646,180L646,181L646,181L646,182L647,183L647,184L647,184Z M684,179L685,179L683,179L683,178L684,179L684,179Z M601,178L601,178L598,177L600,177L601,177L602,178L601,178Z M682,178L681,178L680,177L679,177L679,176L681,177L681,177L682,178Z M683,177L683,177L682,176L681,175L682,175L683,176L683,177Z M609,178L607,178L607,178L607,178L608,177L610,176L610,175L612,175L613,175L614,175L615,175L614,175L612,176L610,177L609,178Z M596,174L597,175L598,175L598,175L596,176L595,176L593,176L594,175L595,175L596,174Z M606,174L606,175L603,176L600,176L600,175L601,175L603,175L604,175L606,174Z M680,175L680,175L678,174L677,174L676,173L677,173L678,173L679,174L680,175Z M675,173L675,173L674,173L673,172L673,172L674,172L675,173Z M577,172L581,172L582,171L585,172L586,174L589,174L591,175L589,176L587,175L585,175L583,175L581,174L579,174L577,174L577,174L573,173L573,172L571,172L572,170L575,171L576,171L577,171L577,172Z M629,171L628,172L628,171L629,170L629,170L629,170L629,171Z M672,172L671,172L670,172L669,170L669,169L669,169L670,169L670,170L671,171L672,172L672,172Z M664,170L663,170L663,170L662,171L660,171L659,171L658,171L657,170L657,170L659,170L660,170L660,169L660,169L660,170L662,170L662,169L663,168L663,167L664,167L665,168L665,169L664,170Z M614,166L614,167L612,166L612,166L614,166L614,166Z M621,165L622,167L620,166L618,166L617,166L616,166L616,165L619,165L621,165Z M666,168L666,168L665,167L665,167L664,166L663,165L661,165L662,164L663,165L664,165L664,166L665,167L666,167L666,168Z M628,162L629,165L631,166L633,164L635,163L637,163L638,164L640,164L642,165L645,166L649,167L651,168L652,169L652,170L655,171L656,172L654,172L654,173L656,174L657,176L659,176L659,177L660,177L659,178L662,178L661,179L660,179L660,178L658,178L656,178L654,177L653,176L652,174L649,174L648,174L647,175L647,176L645,177L644,176L642,176L640,175L638,174L638,175L635,175L636,174L637,173L637,171L636,170L632,168L630,168L627,166L627,167L626,167L626,167L626,166L624,165L626,164L628,164L627,164L624,164L624,163L622,163L621,162L624,161L625,161L628,161L628,162Z M610,157L609,159L607,160L605,159L602,159L600,160L600,161L602,163L603,162L607,161L607,162L606,162L605,163L603,163L605,166L605,166L606,168L606,169L605,170L604,169L605,168L603,169L603,168L603,167L602,166L602,165L601,165L601,167L601,170L600,170L599,170L599,168L599,166L598,166L598,165L598,164L599,162L600,160L600,159L602,158L603,158L606,158L608,158L610,157L610,157Z M617,158L617,160L616,159L616,160L617,161L616,162L615,160L615,158L615,157L616,156L616,157L617,157L617,158Z M572,170L569,170L568,169L565,168L564,166L563,165L562,164L560,161L559,160L558,158L557,157L555,156L554,154L553,153L551,151L551,150L552,150L555,151L557,152L558,154L559,154L561,156L563,156L565,158L566,159L568,160L567,161L568,162L569,162L569,163L570,164L571,164L572,165L572,168L572,170Z M596,157L598,158L596,159L595,160L595,161L593,163L593,164L592,167L592,167L590,167L589,166L588,166L587,166L584,166L583,165L582,165L580,165L580,163L579,162L578,161L578,159L578,158L579,156L581,157L582,157L583,155L584,155L586,154L587,153L588,152L589,151L591,150L592,149L593,148L594,148L595,149L595,149L597,150L598,150L598,151L597,151L597,152L596,153L595,154L596,156L596,157Z M613,145L613,146L613,147L612,149L612,147L611,148L611,149L611,150L608,149L608,148L608,147L607,146L607,147L606,147L604,148L604,147L605,146L606,145L607,145L608,145L609,145L610,144L611,144L611,143L612,143L613,144L613,145Z M522,149L521,149L520,148L519,145L520,143L522,144L523,145L524,147L523,148L522,149Z M238,142L236,142L236,142L237,142L237,141L238,141L238,141L238,142Z M608,142L607,142L607,143L606,144L605,143L605,142L606,142L606,141L607,141L607,142L608,140L608,142Z M597,143L594,145L595,144L597,143L598,142L599,140L599,141L598,142L597,143Z M604,139L605,139L606,139L606,140L605,141L604,141L604,141L604,140L604,139Z M611,138L612,140L610,140L610,140L611,142L610,142L610,141L609,141L609,140L610,140L610,139L609,138L610,138L611,138Z M603,137L603,138L602,137L601,136L602,136L603,137Z M603,127L604,128L604,127L605,128L604,128L605,130L605,131L603,132L603,133L603,135L605,135L605,135L608,135L608,136L608,137L608,138L607,137L606,136L605,137L604,135L602,136L601,135L601,135L602,134L601,134L601,134L600,133L600,133L600,131L601,131L601,129L601,127L603,127Z M229,128L228,128L227,128L226,128L226,127L226,127L227,127L228,127L229,128Z M206,128L206,129L204,128L203,128L204,127L204,127L205,127L206,127L207,128L208,128L206,128Z M215,125L217,125L217,125L218,125L220,125L220,125L220,126L222,126L221,126L222,126L223,127L223,128L222,127L221,127L220,127L220,128L219,128L219,127L218,127L217,129L217,128L217,128L215,128L214,128L213,128L212,128L211,127L211,127L213,127L215,127L215,127L214,126L214,125L213,125L214,125L215,125Z M581,127L579,128L577,127L577,126L578,125L580,124L582,124L582,125L581,126L581,127Z M49,126L49,126L48,126L48,126L48,125L48,125L48,124L48,124L48,124L48,124L49,124L50,124L50,125L50,125L50,125L50,126L49,126Z M48,123L47,123L47,123L47,123L47,123L47,123L47,123L48,123L48,123Z M46,122L46,123L45,122L45,122L46,122Z M45,122L45,122L44,122L44,122L43,122L43,122L44,121L44,122L45,122Z M41,121L41,121L40,121L41,121L41,120L41,121L41,121Z M201,120L201,120L203,120L204,120L206,121L207,122L208,122L209,123L209,123L210,123L212,124L211,124L210,125L209,125L207,125L204,125L206,124L205,123L204,123L203,123L203,122L201,122L200,121L199,121L196,121L196,120L196,120L194,120L193,121L192,121L192,121L191,121L190,121L191,121L192,120L192,119L193,119L195,119L195,119L197,119L199,119L201,120Z M205,118L204,118L204,117L203,116L204,115L204,115L205,117L205,118Z M602,119L601,121L600,119L600,118L601,116L603,115L604,116L604,117L602,119Z M204,113L202,113L202,112L203,112L204,112L204,113Z M206,113L206,114L205,114L205,113L204,112L204,112L206,113Z M629,99L630,100L628,101L628,100L627,101L626,102L625,101L625,101L626,99L627,100L628,99L629,99Z M429,97L428,97L428,98L428,98L426,99L425,98L425,98L425,98L426,98L426,97L427,97L429,97Z M407,97L408,97L410,97L412,97L411,97L413,97L412,98L409,98L409,98L407,97L407,97Z M391,92L390,93L391,94L390,95L389,94L388,94L385,93L385,92L387,92L390,92L391,92Z M378,87L380,88L379,90L378,90L378,91L377,90L377,88L376,87L377,87L378,87Z M642,94L641,95L642,96L641,98L638,98L634,98L632,101L630,100L630,98L627,99L624,100L622,100L624,101L623,104L621,105L620,104L621,103L620,102L619,101L621,100L622,99L624,98L625,97L629,96L631,97L633,94L635,95L638,93L639,92L640,90L640,88L641,87L643,86L644,89L644,90L642,92L642,94Z M379,85L378,86L378,86L377,85L377,84L379,84L379,85Z M648,81L649,82L651,81L651,83L648,84L646,85L643,84L642,86L640,86L640,84L641,83L643,83L643,80L644,79L646,81L648,81Z M233,77L234,77L236,77L235,78L234,78L232,78L231,77L232,76L233,77Z M236,73L235,73L233,72L231,71L232,71L234,72L236,72L236,73Z M113,74L112,74L109,73L108,73L106,72L106,71L104,71L103,70L103,70L105,70L107,70L108,71L109,71L110,72L112,73L113,74Z M248,70L246,71L248,71L249,71L248,72L250,72L251,72L253,72L252,74L254,73L254,74L255,75L254,77L253,77L252,77L252,75L252,75L249,77L248,77L249,76L247,75L245,75L241,75L241,75L242,74L242,74L243,73L245,70L247,69L248,68L249,68L249,69L248,70Z M95,64L97,64L96,66L98,67L97,67L96,66L95,66L94,65L94,64L94,64L95,64Z M647,70L649,73L646,72L645,75L647,77L647,78L645,77L644,78L644,77L644,75L644,73L644,72L644,69L643,68L643,65L645,64L644,64L645,63L646,65L647,66L646,68L647,70Z M346,67L343,68L340,68L342,66L341,64L343,63L345,62L347,62L349,63L348,64L348,66L346,67Z M385,61L384,63L382,62L382,61L385,60L385,61Z M54,58L52,59L51,59L51,58L52,57L54,57L55,57L56,58L54,58Z M354,56L352,58L354,57L356,57L356,59L354,60L356,61L358,63L359,63L360,65L361,66L363,66L363,67L362,68L363,69L361,70L358,70L355,70L354,70L353,71L351,71L350,71L348,71L351,69L353,69L350,68L349,68L352,67L350,66L351,65L354,65L354,64L353,63L350,63L350,62L351,61L350,61L349,62L349,60L348,59L348,57L350,56L352,56L354,56Z M29,53L28,54L26,53L25,53L27,53L29,53L29,53Z M201,49L201,50L200,50L199,50L199,50L200,49L201,49L201,49Z M196,49L194,49L192,49L192,49L194,48L196,48L196,49Z M17,47L18,47L19,47L21,47L23,47L22,48L21,48L19,48L19,47L17,47L16,47L17,47Z M190,43L190,44L191,44L192,44L194,45L197,45L197,46L198,46L200,47L198,47L195,47L194,46L192,47L189,48L188,47L186,47L187,46L188,45L188,43L190,43Z M331,42L331,43L333,44L330,46L324,47L323,47L320,47L314,46L316,46L312,45L316,44L316,44L311,43L313,42L316,42L319,43L322,42L324,43L328,42L331,42Z M208,41L206,41L206,40L206,39L208,39L210,39L210,40L210,40L208,41Z M0,37L5,39L10,41L10,42L11,42L11,41L16,41L20,43L18,43L15,44L15,45L14,46L12,46L11,45L8,45L8,44L6,44L3,44L2,43L3,42L0,43L1,44L0,44L0,44L720,44L717,45L715,45L717,46L718,48L719,48L719,49L718,49L715,49L709,50L707,50L704,52L701,53L701,54L698,52L693,54L692,53L690,54L687,54L686,55L684,56L684,57L686,58L686,60L684,60L683,62L684,62L681,63L680,65L677,66L676,68L674,69L673,68L672,65L671,62L672,59L674,58L674,57L677,57L680,55L684,53L687,51L689,49L687,49L685,50L680,52L679,50L673,51L668,54L670,55L666,55L663,55L663,54L660,54L657,55L651,55L644,55L638,59L630,63L633,63L634,64L636,64L638,64L640,64L643,66L643,67L641,69L641,71L640,74L637,76L636,78L634,80L631,82L630,83L627,84L626,84L625,83L622,84L622,85L621,85L620,85L619,86L619,87L618,88L618,88L617,89L616,89L615,89L615,90L615,90L616,91L617,91L618,93L619,95L619,97L618,98L616,98L615,99L613,99L613,98L613,97L612,95L614,94L612,93L611,93L611,93L611,93L610,93L610,93L609,92L610,91L610,91L610,91L611,90L611,90L609,89L609,89L606,90L604,90L602,91L603,90L603,89L604,88L603,87L602,88L599,89L598,90L596,90L595,91L596,92L598,93L598,93L599,94L602,93L603,93L605,93L605,94L602,95L601,96L599,97L598,98L600,99L601,101L602,102L604,104L604,105L603,105L603,106L604,107L604,108L603,110L602,110L601,112L599,114L597,116L595,118L592,119L590,120L588,120L588,120L586,121L584,122L582,122L581,124L580,124L579,123L580,122L577,121L576,122L573,123L572,125L571,126L573,128L575,130L577,131L578,133L579,136L578,139L577,140L574,142L573,143L570,145L570,144L570,142L569,141L567,141L566,140L565,138L563,138L562,138L562,136L560,136L560,138L559,141L558,142L558,144L560,144L561,145L561,147L562,148L563,148L564,149L565,149L566,150L567,151L567,153L567,153L567,154L567,155L568,156L568,157L568,158L567,158L565,157L563,155L563,154L561,153L561,152L560,151L561,149L560,149L559,148L559,147L558,146L557,145L557,146L556,145L557,144L557,142L557,141L558,140L557,139L557,137L556,136L556,134L555,131L554,130L553,131L551,132L550,132L548,131L549,129L549,128L547,126L547,125L546,125L545,123L544,122L544,121L544,121L543,120L541,119L541,120L541,121L540,121L539,121L539,121L538,121L538,121L536,121L534,122L534,123L533,124L530,125L528,127L526,129L524,130L524,131L523,131L522,132L521,132L520,133L520,135L521,137L520,139L520,142L519,142L518,143L518,144L517,144L516,145L515,146L513,144L512,142L511,140L511,139L510,137L509,135L509,134L507,132L506,128L506,126L506,124L505,122L502,123L501,123L498,121L499,120L499,119L496,118L495,117L494,116L493,115L489,115L486,115L483,115L479,115L477,114L475,114L474,112L473,112L471,112L469,113L467,112L465,111L463,110L462,109L460,106L459,107L458,106L457,107L456,107L456,107L456,108L457,109L458,111L459,111L459,112L460,113L460,113L460,114L460,114L461,115L461,116L462,116L461,115L462,114L463,114L463,114L463,115L463,116L463,117L464,117L464,117L465,117L467,117L468,117L469,116L471,115L472,114L473,113L473,113L473,114L473,114L473,116L474,117L475,118L476,118L477,118L478,119L479,120L480,120L480,120L479,121L479,122L478,122L477,124L476,124L476,124L475,125L476,126L475,126L474,126L473,127L473,128L473,128L471,128L471,129L471,129L470,130L468,130L467,130L466,130L465,131L464,132L464,132L462,133L459,134L457,135L456,135L456,135L455,136L453,136L452,136L451,136L451,137L450,137L450,137L449,137L448,138L447,138L446,136L447,136L446,135L446,134L445,133L446,133L445,132L446,132L446,131L445,130L445,130L445,129L444,128L442,127L442,125L440,124L440,124L438,122L438,121L438,120L437,118L436,117L435,117L434,116L434,115L434,114L433,114L433,113L431,111L430,110L429,110L430,109L430,109L430,108L430,108L429,108L429,110L428,111L428,111L427,110L426,109L425,107L425,107L425,109L427,111L428,114L429,114L430,115L431,117L431,118L431,119L433,121L434,121L434,123L434,123L434,125L435,127L436,127L437,128L438,130L439,132L440,133L442,134L443,135L445,136L445,137L446,137L447,138L447,139L445,139L446,140L447,140L447,141L448,141L449,141L451,141L453,141L455,140L456,140L457,140L458,140L459,140L459,139L461,139L461,139L462,139L462,139L462,140L462,141L462,142L461,144L460,146L459,148L457,151L455,152L453,155L451,156L448,158L446,159L444,162L444,163L443,163L442,164L441,164L441,165L440,166L440,167L439,168L438,168L437,171L438,172L439,172L439,173L438,174L439,174L438,175L439,176L440,178L441,178L441,179L441,181L441,182L441,185L442,186L441,187L440,189L439,190L437,190L435,191L433,193L432,193L430,195L430,195L429,196L430,198L431,199L431,199L431,199L431,201L431,202L431,202L431,203L430,204L428,204L426,205L425,206L425,206L426,207L426,208L425,209L425,210L424,211L423,212L423,212L422,213L421,214L420,215L418,217L416,218L415,219L413,220L412,220L412,220L410,220L409,220L407,220L406,220L405,220L403,221L401,221L400,222L399,222L398,221L398,221L397,220L397,221L396,220L397,219L396,218L396,218L396,216L395,215L394,213L394,213L393,211L391,209L390,208L390,206L389,205L389,202L389,200L389,199L388,199L387,197L386,195L385,194L384,192L383,191L383,190L384,188L384,186L384,186L385,184L385,183L387,182L387,181L387,180L387,179L387,178L386,177L386,176L386,176L386,175L386,174L385,172L384,171L385,171L384,170L384,169L382,167L380,165L379,164L378,162L378,161L378,161L379,160L379,158L379,158L379,156L380,155L379,153L378,153L377,152L377,152L377,152L375,152L374,152L373,152L372,152L371,151L370,150L369,149L367,149L365,149L364,149L362,149L359,150L358,151L356,152L354,151L353,151L352,151L351,151L348,151L347,152L345,152L345,152L344,152L342,151L340,150L338,149L337,148L337,148L335,147L334,146L334,145L334,144L333,143L332,142L331,142L331,142L331,141L330,141L330,140L329,140L328,140L327,139L327,139L327,138L327,138L326,137L327,136L326,134L325,134L326,133L327,132L327,131L327,130L327,129L328,128L327,126L327,125L327,124L327,123L326,123L326,122L326,121L327,121L327,120L327,119L328,118L329,117L330,116L330,115L330,114L331,113L332,113L334,111L335,110L337,110L338,109L339,108L341,107L340,105L341,103L341,102L343,101L345,100L346,99L348,98L348,96L350,96L351,97L353,97L355,97L356,97L358,97L360,96L361,95L363,95L366,95L370,94L371,95L373,94L375,94L375,94L377,94L379,94L380,94L380,95L382,94L382,94L381,95L381,96L382,97L382,98L380,99L381,100L382,100L382,101L383,101L385,102L386,102L388,102L390,103L391,104L393,105L396,105L398,106L399,106L400,105L400,104L400,103L402,102L403,102L406,102L406,103L407,103L408,103L410,103L410,104L413,104L415,104L417,105L418,105L419,105L420,104L422,104L423,104L424,105L424,104L426,105L428,105L429,104L429,104L429,104L430,103L430,102L430,101L430,101L431,100L432,98L432,98L432,97L432,96L432,96L432,95L431,95L429,95L428,96L425,96L423,95L421,95L421,96L419,96L417,95L415,95L414,93L413,92L414,91L412,90L415,88L418,88L418,87L422,87L425,86L427,85L430,85L434,87L437,87L439,87L441,87L443,86L443,85L443,84L442,84L441,83L440,83L437,81L435,81L433,80L435,79L436,78L435,77L438,76L438,76L436,76L435,76L434,77L432,77L430,78L430,79L431,79L433,79L433,80L430,80L428,81L427,81L427,80L425,79L425,79L427,78L427,78L423,78L423,77L421,77L421,78L419,79L419,80L418,80L418,80L417,82L416,83L415,84L416,85L416,86L418,87L418,87L415,87L414,88L413,89L412,88L412,87L411,87L410,87L407,88L409,89L408,89L407,89L406,88L405,88L406,89L407,90L406,91L407,92L408,92L408,93L406,93L407,93L406,94L406,95L405,95L403,94L403,93L402,92L401,91L400,90L400,90L400,89L400,89L399,88L399,88L399,86L399,86L399,86L398,85L398,85L397,84L395,84L394,83L392,83L390,81L391,81L390,80L390,80L389,80L388,80L387,80L387,79L387,79L388,79L386,79L385,79L385,80L385,81L385,82L387,83L388,84L390,85L392,85L392,86L392,86L394,87L395,87L397,88L397,89L397,89L395,88L394,88L393,89L394,90L394,91L393,91L392,92L391,93L391,92L392,91L392,91L391,90L391,89L390,89L389,88L388,87L387,87L386,87L384,86L382,85L381,84L380,82L379,82L378,81L377,81L376,82L375,82L373,83L369,83L366,83L366,84L366,86L364,87L362,87L361,88L360,89L359,90L360,91L359,92L359,93L357,93L356,95L353,95L351,95L350,95L349,96L348,96L348,95L347,94L345,94L344,95L343,94L342,94L343,93L342,92L341,92L341,91L341,90L342,89L342,89L342,88L342,87L342,86L342,86L342,84L341,84L344,82L346,83L349,83L351,83L353,83L356,83L357,82L358,78L356,76L354,75L351,75L351,73L353,73L357,74L356,72L358,72L363,71L363,69L365,69L367,69L368,68L369,66L372,65L374,65L374,65L376,64L376,65L378,64L377,63L377,62L376,61L376,59L377,59L377,58L379,58L380,58L381,57L381,58L381,59L381,59L382,60L381,60L381,60L379,61L380,62L380,63L382,63L382,64L384,64L385,63L387,64L388,64L390,64L393,63L395,62L397,63L397,63L399,63L400,62L403,62L402,60L402,59L403,58L405,57L407,59L408,59L409,57L409,56L408,56L407,56L407,55L409,54L412,54L414,54L416,54L418,53L416,52L413,53L409,53L406,54L405,53L403,52L403,50L402,49L403,48L405,47L409,45L411,44L411,43L408,43L404,43L402,44L403,45L400,47L396,48L394,51L396,52L398,53L396,55L394,56L393,59L392,60L389,60L388,61L386,62L385,60L384,58L382,55L381,54L377,56L374,57L371,56L371,54L370,50L372,49L377,47L381,45L385,43L390,39L393,38L398,36L403,35L406,35L409,34L413,34L416,33L423,35L420,35L422,36L424,36L428,37L433,37L441,39L442,40L442,41L440,42L437,43L428,41L426,42L430,43L430,45L432,46L434,46L434,46L433,45L434,44L439,45L441,45L440,44L444,42L446,42L448,43L449,41L447,40L448,39L447,38L453,39L454,40L451,40L451,41L453,41L456,41L456,40L460,39L467,38L469,38L467,39L469,39L471,38L475,38L478,38L480,39L482,37L480,36L481,36L487,36L490,37L497,39L498,38L496,37L496,37L494,37L495,36L493,34L493,34L497,32L498,31L500,30L505,31L506,32L504,33L505,34L506,35L505,37L507,38L506,40L503,42L505,42L506,42L508,41L508,40L510,40L509,39L510,37L508,37L507,36L509,34L506,33L510,32L509,31L510,30L511,31L511,33L513,34L512,32L515,32L519,31L523,32L521,31L521,29L525,29L529,29L534,29L532,28L534,26L537,26L541,26L546,25L546,25L552,25L553,25L558,24L562,24L562,23L564,23L569,22L572,22L569,23L574,23L574,24L576,24L582,24L587,24L588,25L588,26L586,27L580,28L579,28L581,28L584,29L586,28L587,30L588,29L591,29L598,29L598,30L606,30L607,29L611,29L614,29L617,30L618,31L617,32L619,33L623,34L625,32L628,33L631,33L635,33L636,33L640,33L638,31L641,30L659,32L661,33L666,34L674,34L678,34L680,35L679,36L682,37L685,36L688,36L692,36L696,36L699,38L702,37L700,36L701,35L707,36L711,36L717,37L0,37ZM458,87L459,88L460,88L461,88L459,89L459,90L458,91L458,91L458,92L458,93L460,94L462,94L465,95L468,94L468,94L467,93L468,91L466,90L467,89L465,89L466,87L468,88L469,87L468,86L467,85L466,86L466,87L465,86L465,85L465,85L465,84L463,83L462,82L461,81L461,81L463,81L463,80L464,79L466,80L466,78L466,77L464,77L462,76L460,77L458,78L457,79L455,79L453,81L455,82L455,84L457,86L458,87Z M169,37L167,38L165,37L163,37L160,37L162,36L164,35L166,36L167,36L167,36L169,37Z M0,33L720,34L718,34L717,34L0,33Z M0,33L0,33L2,33L5,33L5,34L3,34L0,34L0,33Z M179,36L179,38L182,37L184,38L183,39L185,41L187,39L189,38L189,36L192,36L195,36L197,37L198,38L196,39L197,40L197,41L193,42L191,42L188,42L188,43L186,44L185,45L183,46L180,46L179,47L178,48L176,48L174,50L172,52L171,53L171,55L174,55L174,57L175,59L178,58L182,59L184,60L185,60L188,61L190,62L193,62L195,62L195,63L196,65L197,67L200,69L202,68L203,67L202,64L200,63L204,62L206,61L207,59L207,58L205,57L203,55L205,54L204,52L204,49L205,49L209,49L211,49L212,49L214,50L217,51L217,51L221,51L221,53L221,55L223,55L225,57L228,56L230,54L231,53L232,54L235,57L237,59L236,60L239,61L241,62L244,62L245,63L246,64L248,65L248,65L249,67L247,68L246,69L242,69L240,71L237,71L232,71L229,71L227,71L226,72L223,73L220,75L218,77L219,76L223,74L227,73L230,72L232,73L230,75L230,76L231,78L234,79L237,78L239,76L239,78L240,78L238,80L233,81L232,81L229,83L228,82L228,81L231,79L228,80L226,80L226,80L224,81L222,82L220,82L219,84L218,84L218,85L219,86L220,86L220,85L220,85L220,86L219,86L218,86L216,87L215,87L214,87L213,87L216,87L216,87L213,88L212,88L212,88L211,88L212,88L212,89L210,91L210,90L210,90L209,90L209,91L210,91L210,92L209,92L208,94L208,94L209,93L208,92L207,90L207,91L207,92L206,92L207,93L207,94L208,94L208,95L209,97L207,98L205,99L204,100L203,100L202,100L202,101L199,102L198,103L197,104L197,105L197,107L198,108L199,109L199,110L200,112L200,113L200,114L199,115L199,115L198,115L197,114L197,114L196,112L195,111L194,110L195,109L194,108L193,107L192,107L190,107L189,107L188,106L187,106L185,106L183,106L182,106L181,106L181,107L181,108L182,108L181,108L180,108L180,108L178,108L177,107L175,107L174,107L172,107L171,108L169,109L167,110L166,111L165,111L165,113L165,113L166,114L166,114L166,114L165,116L165,117L164,119L164,120L165,121L165,122L166,123L167,125L167,126L168,127L170,127L171,128L173,127L174,127L176,127L177,126L178,126L179,125L179,123L179,123L181,122L183,122L185,122L186,122L186,122L186,123L185,124L185,125L185,125L185,126L184,128L184,127L183,127L183,127L184,127L184,128L183,129L184,129L183,130L184,130L183,131L183,131L183,131L182,132L183,132L183,132L184,132L184,132L184,132L185,132L185,132L185,132L186,132L187,132L188,132L188,132L189,132L189,132L190,132L190,132L191,132L191,132L192,132L192,133L193,133L194,133L194,134L193,134L194,135L193,135L193,136L193,137L193,137L193,138L193,138L193,139L193,139L192,140L192,140L193,141L193,142L194,142L195,143L196,144L196,144L196,144L197,144L197,144L198,144L199,144L200,143L201,143L202,143L202,143L203,143L204,144L205,144L205,145L206,145L208,143L209,143L209,143L209,141L210,140L211,140L212,140L213,140L215,139L216,139L216,138L217,138L218,138L217,139L217,139L216,140L217,140L217,141L216,142L217,144L217,144L218,142L217,142L217,141L220,140L219,139L220,138L221,140L222,140L224,141L224,141L225,141L228,141L229,142L230,142L231,142L231,141L234,141L236,141L235,141L235,142L237,142L238,143L239,145L240,145L240,145L242,146L243,147L243,148L244,148L245,149L246,149L248,150L248,149L250,149L252,150L253,150L254,150L256,152L257,153L257,153L258,154L259,157L260,157L260,158L259,160L259,160L263,160L263,162L264,161L267,162L270,163L271,164L271,165L273,164L277,165L280,165L283,167L286,169L287,169L289,169L290,170L290,172L291,173L290,176L289,177L286,180L285,182L283,183L283,183L282,185L282,188L282,191L281,192L281,192L280,195L278,197L278,199L276,200L276,201L274,201L271,202L269,202L267,203L265,204L263,206L263,207L263,208L263,210L262,211L261,212L259,215L257,216L255,217L255,219L253,220L252,221L250,222L249,222L248,222L246,221L244,221L243,220L243,221L246,223L245,224L247,225L246,226L245,228L242,229L238,229L235,229L236,230L235,231L236,232L235,233L232,233L231,233L230,233L230,235L231,235L232,235L233,236L231,236L230,237L229,239L229,240L227,240L225,241L225,242L227,244L229,244L228,246L226,247L224,249L223,249L222,250L222,252L224,253L223,253L221,253L220,253L218,254L218,256L217,256L215,255L213,254L210,253L209,252L210,251L209,250L209,247L210,245L212,243L209,243L211,241L211,238L214,239L215,235L213,235L213,237L211,237L212,234L213,231L214,230L213,228L213,226L214,226L215,223L216,220L217,218L217,215L217,214L217,211L218,209L219,206L219,202L220,198L220,195L219,193L217,192L217,191L213,189L210,187L208,186L207,185L207,184L206,182L204,178L202,175L201,174L200,173L199,172L197,171L198,170L197,168L198,167L199,166L200,165L200,164L199,165L198,164L198,163L198,162L199,162L199,161L200,159L200,159L201,158L202,158L202,157L203,157L203,156L203,155L204,155L205,154L206,153L205,153L205,152L205,150L205,150L205,148L204,147L204,147L203,146L204,145L203,145L203,145L202,144L201,144L200,145L200,145L199,145L199,146L200,147L199,147L199,147L198,147L198,146L198,146L197,146L197,146L196,145L195,145L194,145L194,146L194,145L193,145L193,145L193,144L193,144L192,143L191,143L191,143L191,142L190,142L190,143L190,143L189,143L189,142L188,142L188,141L189,141L188,141L189,140L188,140L187,139L187,138L186,138L185,137L185,137L185,137L185,137L185,136L184,136L184,137L183,137L182,136L181,136L180,136L180,136L179,135L178,135L177,135L176,134L173,132L172,132L171,131L169,131L168,132L167,132L165,132L164,131L162,131L161,130L158,129L157,129L156,128L155,128L153,127L152,127L150,126L149,125L149,124L149,123L149,123L149,123L149,122L149,121L149,120L148,120L146,118L144,116L143,115L141,115L141,114L141,113L140,113L139,112L139,110L138,110L136,109L136,109L135,108L134,107L134,105L134,105L132,104L132,104L130,103L130,104L130,105L131,106L131,107L133,108L133,109L133,109L134,109L134,109L134,111L135,111L136,112L137,113L137,114L138,115L139,116L139,117L140,117L140,118L141,118L141,119L140,119L140,119L139,118L138,117L137,116L136,116L136,115L135,114L134,113L133,112L133,113L132,112L131,112L130,111L130,111L131,111L132,110L132,109L130,108L129,107L128,106L127,105L127,104L126,102L125,101L124,100L123,100L123,100L122,99L121,99L119,99L119,98L119,97L117,96L115,93L115,93L114,92L113,91L112,89L111,88L112,87L112,85L111,84L112,82L112,79L112,77L111,75L111,74L111,74L114,75L115,76L115,76L115,74L114,73L114,73L110,71L109,70L105,70L104,68L104,67L102,66L101,65L99,63L99,63L98,62L96,61L96,60L93,58L92,57L90,57L87,57L84,56L80,54L78,54L75,53L72,53L68,53L66,52L64,52L64,53L63,53L61,54L59,54L57,55L56,54L57,52L59,51L59,51L56,52L55,53L52,54L53,55L52,57L49,57L47,58L47,59L44,60L43,60L41,61L39,61L38,62L36,62L34,63L30,63L30,63L32,62L34,62L36,61L39,60L40,60L43,59L43,58L45,58L45,56L46,55L44,56L43,55L42,56L41,55L40,56L39,55L37,56L36,56L36,55L36,54L35,53L32,54L31,53L29,52L29,51L28,51L29,50L30,49L31,48L32,48L34,48L35,47L37,47L38,47L38,46L37,46L38,45L37,45L35,45L34,46L33,45L30,45L27,45L26,44L24,43L27,43L31,42L33,42L32,43L37,42L35,41L33,41L31,40L29,39L26,38L28,38L31,37L34,37L34,36L36,35L38,35L42,34L44,34L47,33L50,34L51,34L52,34L56,34L55,34L59,35L61,35L65,35L69,35L70,36L73,35L76,36L78,36L82,36L85,37L87,38L89,37L91,36L94,36L97,36L100,35L102,36L103,36L104,35L105,35L108,36L111,35L111,37L114,36L115,36L117,36L120,37L125,37L128,38L130,37L132,38L129,39L133,40L138,39L140,39L142,40L144,39L142,39L144,38L146,38L148,38L149,38L151,39L154,39L157,40L160,39L163,39L163,38L165,38L168,39L168,40L169,39L171,39L172,37L169,36L167,35L167,33L170,32L172,32L174,33L177,35L175,36L179,36Z M132,30L131,31L135,30L138,31L140,30L142,31L144,33L145,32L143,30L145,30L147,30L149,31L150,33L151,34L154,35L158,36L158,36L155,36L156,37L155,38L152,37L148,37L146,37L142,38L136,38L133,38L132,37L130,37L128,37L125,36L127,35L130,35L133,35L135,35L131,34L127,35L124,35L123,34L128,33L125,33L121,33L123,31L124,31L130,30L132,30Z M151,29L149,31L146,29L147,29L149,29L151,29Z M207,30L207,31L205,30L203,30L201,31L200,31L198,30L198,29L199,29L204,29L207,30Z M187,30L188,31L190,30L195,29L199,31L198,32L202,31L204,31L209,32L212,32L212,33L216,33L218,34L222,35L224,35L226,37L222,38L227,39L230,39L233,41L236,41L236,42L232,44L230,44L227,42L224,42L224,43L226,44L229,45L229,46L231,47L230,49L227,48L222,47L225,48L227,49L228,50L222,49L218,48L216,47L216,47L213,46L210,45L210,46L205,46L203,45L204,44L208,44L212,44L211,43L212,42L215,40L214,40L213,39L210,38L206,38L208,37L205,36L204,36L202,35L201,36L197,36L190,36L186,35L183,35L181,34L183,33L180,33L180,32L181,30L183,29L188,29L187,30Z M159,29L162,29L165,29L166,29L164,30L167,31L167,33L163,33L161,33L160,32L155,31L155,31L159,31L157,30L159,29Z M647,30L644,30L640,30L640,30L642,29L644,29L647,29L647,30Z M174,31L171,32L169,32L168,30L168,29L169,29L171,28L175,28L179,29L176,30L174,31Z M119,33L114,34L113,33L108,32L109,32L110,30L112,29L110,28L117,28L120,28L125,28L127,29L129,29L126,30L122,31L119,32L119,33Z M661,27L659,27L656,27L652,26L653,26L656,26L661,27Z M173,27L172,27L169,27L166,27L167,26L170,26L172,26L173,27Z M650,26L649,27L641,27L638,27L634,26L635,25L638,25L643,25L650,26Z M163,24L165,24L165,25L164,27L160,27L158,27L158,26L155,26L155,24L157,24L160,24L163,24L163,24Z M144,25L144,25L146,25L148,25L149,26L147,27L141,27L136,28L133,28L132,27L136,26L127,27L125,26L127,25L129,24L135,25L138,26L142,26L139,24L141,23L143,24L144,25Z M475,34L474,34L467,34L467,33L463,33L463,32L465,32L465,31L469,29L467,29L472,27L471,27L476,26L482,24L489,24L492,23L496,23L498,24L496,24L489,25L483,26L477,28L474,30L471,31L471,33L475,34Z M171,23L173,24L177,24L179,24L178,25L180,25L182,26L184,26L187,26L190,25L194,25L198,25L200,26L200,27L199,27L196,28L194,27L188,28L184,28L180,28L175,27L174,26L174,25L172,24L168,24L166,24L167,23L171,23Z M128,22L127,23L126,24L124,24L120,25L117,25L114,25L118,23L122,22L125,22L128,22Z M172,22L171,22L168,22L167,22L171,22L173,22L172,22Z M140,22L136,22L133,22L135,21L137,21L140,21L140,22Z M409,22L405,22L401,22L403,21L402,21L406,21L407,21L409,22Z M141,20L138,21L135,21L135,20L137,20L138,20L141,20Z M168,21L165,22L164,21L163,21L163,20L165,20L166,20L169,21L168,21Z M160,21L161,21L157,21L154,21L150,21L152,20L149,20L149,19L153,19L158,20L160,21Z M570,21L559,21L563,19L564,19L566,19L571,20L570,21Z M397,18L403,20L398,20L397,22L395,22L394,23L392,24L388,22L389,22L386,21L382,20L381,18L386,18L387,18L390,18L391,18L394,18L397,18Z M411,17L415,18L412,19L406,19L400,19L400,18L397,18L395,17L401,17L404,17L406,17L411,17Z M462,17L460,17L458,17L458,17L455,18L453,17L454,17L450,17L454,16L457,16L457,17L458,16L460,16L463,17L462,17Z M560,20L556,20L550,19L547,19L545,18L542,17L548,16L552,16L556,16L560,18L560,20Z M186,18L188,19L186,19L182,21L178,21L174,21L172,20L172,19L174,19L170,19L168,18L167,17L168,17L169,16L171,16L171,16L175,16L178,16L181,17L184,17L186,18Z M223,12L228,12L233,13L236,13L236,14L231,14L226,15L225,15L229,15L224,16L221,17L218,18L214,18L212,19L206,19L209,19L208,20L209,20L207,21L204,22L203,22L200,23L201,23L204,23L204,24L199,25L194,24L188,24L185,24L181,24L181,23L184,23L183,22L185,21L190,22L187,21L184,21L186,20L189,20L190,19L187,18L186,17L192,17L193,18L196,17L192,17L185,17L181,16L180,16L177,15L177,14L180,14L182,14L186,14L189,13L191,13L194,14L195,13L198,12L201,12L207,12L209,12L214,12L219,12L223,12Z M306,12L318,13L315,14L307,14L296,14L297,14L304,14L310,15L314,14L316,15L314,16L319,15L328,14L334,15L336,15L327,17L326,17L320,17L325,18L322,19L321,20L321,22L323,23L320,23L317,24L320,25L321,26L319,26L321,28L317,28L319,29L318,29L316,30L313,30L315,31L315,32L311,31L310,31L313,32L316,33L316,34L313,35L311,34L309,33L310,34L307,35L313,35L315,35L310,37L305,38L299,39L296,39L294,40L292,41L287,43L286,43L283,43L280,44L279,45L279,46L278,47L274,49L275,50L274,51L273,53L270,53L267,52L263,52L262,51L260,49L257,47L256,46L255,44L253,42L253,41L252,41L254,38L257,38L258,37L258,36L256,36L255,37L253,37L251,36L250,35L251,34L253,34L257,35L254,33L252,33L250,33L248,33L251,31L249,30L248,29L245,27L243,26L243,26L237,25L233,25L228,25L223,25L221,24L217,23L222,23L226,22L218,22L213,21L214,21L221,20L229,19L229,18L224,18L226,17L233,16L236,15L235,15L239,14L246,14L252,14L254,14L259,13L264,14L267,14L271,15L266,14L266,13L273,12L280,12L283,11L290,11L306,12Z";
function anDotMap(cities) {
  const W = 720, H = 320;
  const proj = (lat, lon) => [(Number(lon) + 180) / 360 * W, (90 - Number(lat)) / 180 * H];
  const pts = cities.filter(c => c.lat != null && c.lon != null);
  const max = Math.max(1, ...pts.map(c => c.visitors || 0));
  const land = `<path d="${AN_WORLD_LAND}" fill="var(--surface3,#222b3a)" stroke="var(--border,#2e3a50)" stroke-width="0.6" fill-opacity="1"/>`;
  let grid = "";
  for (let lon = -180; lon <= 180; lon += 30) { const x = (lon + 180) / 360 * W; grid += `<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="var(--border)" stroke-width="0.3" stroke-opacity="0.4"/>`; }
  for (let lat = -60; lat <= 60; lat += 30) { const y = (90 - lat) / 180 * H; grid += `<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="var(--border)" stroke-width="0.3" stroke-opacity="0.4"/>`; }
  const dots = pts.map(c => {
    const [x, y] = proj(c.lat, c.lon), r = 2 + Math.sqrt((c.visitors || 1) / max) * 11;
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}" fill="var(--accent)" fill-opacity="0.4" stroke="var(--accent)" stroke-width="0.8"><title>${esc((c.city || "?") + (c.country_code ? ", " + c.country_code : ""))}: ${fmtNum(c.visitors)} visitors</title></circle>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;background:var(--surface2);border-radius:var(--r-md)" role="img" aria-label="visitor city map">${land}${grid}${dots}</svg>
    <div class="sub" style="margin-top:6px">Equirectangular dot map · dot size = visitors · hover a dot for the city</div>`;
}
function anFlags(r) {
  const f = [];
  if (r.is_vpn) f.push('<span class="statpill s-warn">VPN</span>');
  if (r.is_proxy) f.push('<span class="statpill s-warn">proxy</span>');
  if (r.is_hosting) f.push('<span class="statpill s-mut">host</span>');
  return f.join(" ") || '<span class="sub">—</span>';
}
function anTimelineRow(ev) {
  const icon = { pageview: "◉", route: "→", ticker_view: "📈", search: "🔎", terminal_jump: "⤢", click: "·", scroll: "↕", session_start: "●", exit: "⏻", heartbeat: "·" }[ev.type] || "·";
  const detail = ev.ticker ? `<b class="mono">${esc(ev.ticker)}</b>` : `<span class="mono">${esc(ev.path || "")}</span>`;
  const dwell = ev.dwell_ms ? `<span class="an-tw">${(ev.dwell_ms / 1000).toFixed(1)}s</span>` : "";
  const scr = (ev.scroll != null && ev.scroll !== "") ? `<span class="an-tw">${ev.scroll}%↕</span>` : "";
  return `<div class="an-trow"><span class="an-tt mono">${esc(ev.t || "")}</span><span class="an-ti">${icon}</span><span class="an-ty">${esc(ev.type)}</span><span class="an-td">${detail}</span>${dwell}${scr}</div>`;
}
async function anLoad(sub) {
  const body = $("#anBody"); if (!body) return;
  body.innerHTML = `<div class="spin">loading…</div>`;
  try { await (AN_RENDER[sub] || AN_RENDER.overview)(); }
  catch (e) { body.innerHTML = card("Error", `<div class="sub">${esc(String((e && e.message) || e))}</div>`); }
}
async function anUmamiStrip() {
  const c = $("#anUmamiCard"); if (!c) return;
  try {
    const st = await api("/api/analytics");
    const dash = (st && st.dashboard_url) || "https://cloud.umami.is";
    if (!st.configured) { c.innerHTML = `<div class="sub">Umami tag live on every page; the granular API needs a paid plan. GA4 is GFW-blocked for China. <a href="${esc(dash)}" target="_blank" rel="noopener">Open Umami ↗</a></div>`; return; }
    const rep = await api("/api/analytics/report?days=7");
    c.innerHTML = rep.ok
      ? `<div class="sub">Umami (7d): <b>${fmtNum(rep.summary.visitors)}</b> visitors · <b>${fmtNum(rep.summary.pageviews)}</b> pageviews · <a href="${esc(dash)}" target="_blank" rel="noopener">dashboard ↗</a></div>`
      : `<div class="sub">${esc(rep.error || "Umami not available")}</div>`;
  } catch (e) { c.innerHTML = `<div class="sub muted">cross-check unavailable</div>`; }
}

AN_RENDER.overview = async () => {
  const d = await api(`/api/analytics/fp/overview?days=${AN.days}`);
  const b = $("#anBody"); if (!d.ok) { b.innerHTML = anNotReady(d); return; }
  const w = d.window || {}, at = d.alltime || {}, daily = d.daily || [];
  const maxV = Math.max(1, ...daily.map(x => x.visitors));
  b.innerHTML = `
    <div class="grid">
      ${card(`Visitors (${d.days}d)`, `<div class="big">${fmtNum(w.visitors)}</div><div class="sub">${fmtNum(at.visitors)} all-time</div>`)}
      ${card(`Sessions (${d.days}d)`, `<div class="big">${fmtNum(w.sessions)}</div><div class="sub">${fmtNum(w.events)} events</div>`)}
      ${card(`Pageviews (${d.days}d)`, `<div class="big">${fmtNum(w.pageviews)}</div><div class="sub">${fmtNum(w.ticker_views)} ticker views</div>`)}
      ${card(`Searches (${d.days}d)`, `<div class="big">${fmtNum(w.searches)}</div><div class="sub">tickers searched</div>`)}
    </div>
    <div class="section">Visitors per day</div>
    <div class="card"><div class="spark tall">${daily.map(x => `<i style="height:${Math.round(x.visitors / maxV * 100)}%" title="${esc(x.day)}: ${x.visitors} visitors · ${x.events} events"></i>`).join("") || "<span class='muted'>no data yet</span>"}</div></div>
    <div class="section">By site</div>
    <div class="card">${anBars(d.by_site || [], r => `<b>${esc(r.site || "—")}</b>`, "visitors", { sub: r => `${fmtNum(r.events)} events` })}</div>
    <div class="section">Third-party cross-check</div>
    <div class="card" id="anUmamiCard"><div class="sub">loading…</div></div>`;
  anUmamiStrip();
};
AN_RENDER.pages = async () => {
  const d = await api(`/api/analytics/fp/pages?days=${AN.days}&limit=40`);
  const b = $("#anBody"); if (!d.ok) { b.innerHTML = anNotReady(d); return; }
  const rows = d.pages || [];
  b.innerHTML = `<div class="section">Top pages (${d.days}d) <span class="cnt">${rows.length}</span></div>
    <table><thead><tr><th>Site</th><th>Path</th><th class="r">Views</th><th class="r">Visitors</th><th class="r">Avg dwell</th></tr></thead><tbody>
    ${rows.map(r => `<tr><td class="sub">${esc(r.site || "")}</td><td class="mono">${esc(r.path || "")}</td><td class="r">${fmtNum(r.views)}</td><td class="r">${fmtNum(r.visitors)}</td><td class="r sub">${r.avg_dwell_ms ? (r.avg_dwell_ms / 1000).toFixed(1) + "s" : "—"}</td></tr>`).join("") || "<tr><td colspan='5' class='muted'>no data yet</td></tr>"}
    </tbody></table>`;
};
AN_RENDER.geo = async () => {
  const d = await api(`/api/analytics/fp/geo?days=${AN.days}&limit=250`);
  const b = $("#anBody"); if (!d.ok) { b.innerHTML = anNotReady(d); return; }
  const countries = d.countries || [], cities = d.cities || [];
  const unresolved = countries.some(c => !c.country_code);
  b.innerHTML = `<div class="card">${anDotMap(cities)}</div>
    <div class="grid" style="margin-top:14px">
      <div class="card"><h3>Countries (${d.days}d)</h3>${anBars(countries.slice(0, 15), r => `${esc(r.country || "—")}${r.country_code ? ` <span class="an-cc">${esc(r.country_code)}</span>` : ""}`, "visitors")}</div>
      <div class="card"><h3>Cities</h3>${anBars(cities.slice(0, 15), r => `${esc(r.city || "—")}`, "visitors", { sub: r => esc(r.country_code || "") })}</div>
    </div>
    ${unresolved ? `<div class="sub" style="margin-top:10px">Some IPs aren't geolocated yet — the geo-enrich job backfills them every 30 min. <button class="btn" id="anGeoNow">Enrich now</button></div>` : ""}`;
  const g = $("#anGeoNow");
  if (g) g.onclick = async () => { g.disabled = true; g.textContent = "enriching…"; const r = await post("/api/analytics/fp/geo_enrich", { budget: 300 }); toast(r.ok ? "geo enriched" : (r.reason || "failed"), !r.ok); anLoad("geo"); };
};
AN_RENDER.sessions = async () => {
  const d = await api(`/api/analytics/fp/sessions?limit=60`);
  const b = $("#anBody"); if (!d.ok) { b.innerHTML = anNotReady(d); return; }
  const rows = d.sessions || [];
  b.innerHTML = `<div class="section">Recent sessions <span class="cnt">${rows.length}</span> <span class="sub">— per visit: who (visitor id), their IP + location. Click replay to see the exact path.</span></div>
    <table><thead><tr><th>Started</th><th>Visitor</th><th>IP</th><th>Location</th><th>Site</th><th class="r">Pages</th><th class="r">Events</th><th class="r">Duration</th><th></th></tr></thead><tbody>
    ${rows.map(s => `<tr><td class="mono sub">${esc(s.started || "")}</td>
      <td><a class="mono" href="#/visitor/${encodeURIComponent(s.visitor_id || "")}">${esc((s.visitor_id || "—").slice(0, 8))}…</a></td>
      <td class="mono">${esc(s.ip || "—")}</td>
      <td class="sub">${esc(s.city || "—")}${s.region ? ", " + esc(s.region) : ""}${s.country_code ? " · " + esc(s.country_code) : ""}</td>
      <td class="sub">${esc(s.site || "")}</td>
      <td class="r">${fmtNum(s.pages)}</td><td class="r">${fmtNum(s.events)}</td>
      <td class="r sub">${s.duration_s != null ? fmtElapsedSec(s.duration_s) : "—"}</td>
      <td><a class="btn sm" href="#/session/${encodeURIComponent(s.session_id || "")}">replay ▸</a></td></tr>`).join("") || "<tr><td colspan='9' class='muted'>no sessions yet</td></tr>"}
    </tbody></table>`;
};
AN_RENDER.visitors = async () => {
  const d = await api(`/api/analytics/fp/visitors?limit=150`);
  const b = $("#anBody"); if (!d.ok) { b.innerHTML = anNotReady(d); return; }
  const rows = d.visitors || [];
  b.innerHTML = `<div class="section">Frequent visitors <span class="cnt">${rows.length}</span> <span class="sub">— one profile per person. Signed-in users are shown by email with every device/cookie merged into one; anonymous visitors keep their cookie id. Most sessions first — click to open full history + tickers searched.</span></div>
    <table><thead><tr><th>Visitor</th><th>Last IP</th><th>Location</th><th>Net</th><th class="r">Sessions</th><th class="r">Events</th><th class="r">IPs</th><th>First seen</th><th>Last seen</th></tr></thead><tbody>
    ${rows.map(v => `<tr>
      <td>${v.is_user
        ? `<a href="#/visitor/${encodeURIComponent(v.visitor_id || "")}"><b>${esc(v.email || "registered user")}</b></a> <span class="statpill s-ok">registered</span>`
        : `<a class="mono" href="#/visitor/${encodeURIComponent(v.visitor_id || "")}">${esc((v.visitor_id || "—").slice(0, 10))}…</a>`
      }${(v.identities > 1) ? ` <span class="statpill s-mut">${fmtNum(v.identities)} devices</span>` : ""}</td>
      <td class="mono">${esc(v.last_ip || "—")}</td>
      <td>${esc(v.city || "—")}${v.region ? ", " + esc(v.region) : ""}${v.country_code ? " · " + esc(v.country_code) : ""}</td>
      <td>${v.is_vpn ? '<span class="statpill s-warn">VPN</span>' : '<span class="sub">—</span>'}</td>
      <td class="r"><b>${fmtNum(v.sessions)}</b></td><td class="r">${fmtNum(v.events)}</td><td class="r">${fmtNum(v.ips)}</td>
      <td class="mono sub">${esc(v.first_seen || "")}</td><td class="mono sub">${esc(v.last_seen || "")}</td></tr>`).join("") || "<tr><td colspan='9' class='muted'>no visitors yet</td></tr>"}
    </tbody></table>`;
};
AN_RENDER.flow = async () => {
  const d = await api(`/api/analytics/fp/flow?days=${AN.days}&limit=40`);
  const b = $("#anBody"); if (!d.ok) { b.innerHTML = anNotReady(d); return; }
  b.innerHTML = `<div class="section">Navigation patterns (${d.days}d) <span class="sub">— most common page-to-page moves across all visitors</span></div>
    <div class="card">${anBars(d.edges || [], r => `<span class="mono an-from">${esc(r.from_path || "")}</span> <span class="an-arrow">→</span> <span class="mono an-to">${esc(r.to_path || "")}</span>`, "n")}</div>`;
};
AN_RENDER.terminal = async () => {
  const d = await api(`/api/analytics/fp/terminal?days=${AN.days}&limit=25`);
  const b = $("#anBody"); if (!d.ok) { b.innerHTML = anNotReady(d); return; }
  const t = d.totals || {};
  b.innerHTML = `<div class="grid">
      ${card(`Ticker searches (${d.days}d)`, `<div class="big">${fmtNum(t.search_total)}</div><div class="sub">Terminal + macro nav search</div>`)}
      ${card(`Ticker views (${d.days}d)`, `<div class="big">${fmtNum(t.view_total)}</div><div class="sub">charts opened</div>`)}
    </div>
    <div class="grid" style="margin-top:14px">
      <div class="card"><h3>Most searched</h3>${anBars(d.top_searches || [], r => `<b class="mono">${esc(r.ticker || "")}</b>`, "searches", { sub: r => `${fmtNum(r.visitors)} visitors` })}</div>
      <div class="card"><h3>Most viewed</h3>${anBars(d.top_views || [], r => `<b class="mono">${esc(r.ticker || "")}</b>`, "views", { sub: r => `${fmtNum(r.visitors)} visitors` })}</div>
    </div>`;
};

RENDER.analytics = async () => {
  const v = $("#view");
  v.innerHTML = `
    <div class="an-bar">
      <div class="an-tabs">${AN_TABS.map(([id, l]) => `<button class="an-tab${AN.tab === id ? " active" : ""}" data-at="${id}">${l}</button>`).join("")}</div>
      <span class="an-spacer"></span>
      <span class="pill an-live" title="visitors active in the last 5 minutes"><span class="led ok"></span>&nbsp;<b id="anLiveN">…</b>&nbsp;active</span>
      <select id="anDays" class="an-days" title="time window"><option value="1">24h</option><option value="7">7 days</option><option value="30">30 days</option><option value="90">90 days</option></select>
    </div>
    <div id="anBody"><div class="spin">loading…</div></div>`;
  $("#anDays").value = String(AN.days);
  $("#anDays").onchange = (e) => { AN.days = parseInt(e.target.value, 10) || 7; anLoad(AN.tab); };
  $(".an-tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".an-tab"); if (!btn) return;
    AN.tab = btn.dataset.at;
    document.querySelectorAll(".an-tab").forEach(x => x.classList.toggle("active", x.dataset.at === AN.tab));
    anLoad(AN.tab);
  });
  const poll = async () => {
    if (CURRENT !== "analytics" || !$("#anLiveN")) { if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; } return; }
    try { const r = await api("/api/analytics/fp/realtime"); const el = $("#anLiveN"); if (el) el.textContent = r.ok ? fmtNum((r.active || {}).visitors) : "—"; } catch (e) {}
  };
  RT_TIMER = setInterval(poll, 15000); poll();
  anLoad(AN.tab);
};

/* detail "pages" (hash-routed) — session replay + visitor identity */
function currentAnalyticsDetail() {
  let m = location.hash.match(/^#\/session\/(.+)$/); if (m) return { kind: "session", id: decodeURIComponent(m[1]) };
  m = location.hash.match(/^#\/visitor\/(.+)$/); if (m) return { kind: "visitor", id: decodeURIComponent(m[1]) };
  return null;
}
function anDetailHead(title) {
  const head = h(`<div class="an-detail-head"><a class="btn" href="#" id="anBack">← Analytics</a><span class="an-detail-title">${title}</span></div>`);
  return head;
}
async function renderSessionDetail(id) {
  if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; }
  CURRENT = "analytics"; setActiveNav("analytics"); setTopbarTitle("Session replay");
  const v = $("#view");
  v.innerHTML = `<div class="an-detail-head"><a class="btn" href="#" id="anBack">← Analytics</a><span class="an-detail-title">Session <code>${esc(id.slice(0, 12))}…</code></span></div><div id="anDet"><div class="spin">loading…</div></div>`;
  $("#anBack").onclick = (e) => { e.preventDefault(); location.hash = ""; go("analytics"); };
  const d = await api(`/api/analytics/fp/session?id=${encodeURIComponent(id)}`);
  const det = $("#anDet");
  if (!d.ok) { det.innerHTML = card("Session", `<div class="sub">${esc(d.reason || d.error || "not found")}</div>`); return; }
  const head = d.head || {}, path = d.path || [];
  det.innerHTML = `
    <div class="grid">
      ${card("Visitor", `<div class="big" style="font-size:15px"><a class="mono" href="#/visitor/${encodeURIComponent(head.visitor_id || "")}">${esc((head.visitor_id || "—").slice(0, 12))}…</a></div><div class="sub">${head.user_id ? "user " + esc(String(head.user_id).slice(0, 8)) : "anonymous"}</div>`)}
      ${card("Origin", `<div class="big" style="font-size:15px">${esc(head.site || "—")}</div><div class="sub mono">${esc(head.ip || "")}</div>`)}
      ${card("Events", `<div class="big">${fmtNum(path.length)}</div><div class="sub">ordered path below</div>`)}
    </div>
    <div class="section">Path (in order)</div>
    <div class="an-timeline">${path.map(anTimelineRow).join("") || "<div class='muted sub'>no events</div>"}</div>`;
}
async function renderVisitorDetail(id) {
  if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; }
  CURRENT = "analytics"; setActiveNav("analytics"); setTopbarTitle("Visitor");
  const v = $("#view");
  v.innerHTML = `<div class="an-detail-head"><a class="btn" href="#" id="anBack">← Analytics</a><span class="an-detail-title">Visitor <code>${esc(id.slice(0, 12))}…</code></span></div><div id="anDet"><div class="spin">loading…</div></div>`;
  $("#anBack").onclick = (e) => { e.preventDefault(); location.hash = ""; go("analytics"); };
  const d = await api(`/api/analytics/fp/visitor?id=${encodeURIComponent(id)}`);
  const det = $("#anDet");
  if (!d.ok) { det.innerHTML = card("Visitor", `<div class="sub">${esc(d.reason || d.error || "not found")}</div>`); return; }
  const p = d.profile || {}, ips = d.ips || [], linked = d.linked || [], recent = d.recent || [], searches = d.searches || [], viewed = d.tickers_viewed || [];
  det.innerHTML = `
    <div class="grid">
      ${card("Identity", `<div class="big" style="font-size:15px">${d.email ? esc(d.email) : (p.user_id ? "user " + esc(String(p.user_id).slice(0, 8)) : "anonymous")}</div><div class="sub">${d.email ? '<span class="statpill s-ok">registered</span> ' : ""}${(p.identities > 1) ? fmtNum(p.identities) + " cookies merged · " : ""}first ${esc(String(p.first_seen || "").slice(0, 16))}</div>`)}
      ${card("Activity", `<div class="big">${fmtNum(p.events)}</div><div class="sub">${fmtNum(p.sessions)} sessions</div>`)}
      ${card("Devices / IPs", `<div class="big">${fmtNum(p.ips)}<span class="sub"> IPs</span></div><div class="sub">${fmtNum(p.fingerprints)} fingerprints</div>`)}
      ${card("Linked identities", `<div class="big" style="color:${linked.length ? "var(--warn)" : "var(--text)"}">${fmtNum(linked.length)}</div><div class="sub">same device/IP, other cookie</div>`)}
    </div>
    <div class="section">IP addresses & location</div>
    <table><thead><tr><th>IP</th><th>City</th><th>Country</th><th>Network</th><th>Flags</th><th class="r">Events</th></tr></thead><tbody>
    ${ips.map(r => `<tr><td class="mono">${esc(r.ip || "")}</td><td>${esc(r.city || "—")}${r.region ? ", " + esc(r.region) : ""}</td><td>${esc(r.country_code || "—")}</td><td class="sub">${esc(r.org || r.asn || "—")}</td><td>${anFlags(r)}</td><td class="r">${fmtNum(r.events)}</td></tr>`).join("") || "<tr><td colspan='6' class='muted'>no IPs</td></tr>"}
    </tbody></table>
    ${linked.length ? `<div class="section">Linked visitors <span class="cnt">${linked.length}</span> <span class="sub">— same fingerprint or IP, different cookie (likely one person)</span></div>
    <table><thead><tr><th>Visitor</th><th>Matched by</th><th class="r">Shared events</th></tr></thead><tbody>
    ${linked.map(l => `<tr><td><a class="mono" href="#/visitor/${encodeURIComponent(l.visitor_id)}">${esc((l.visitor_id || "").slice(0, 12))}…</a></td><td>${l.via_fp ? '<span class="statpill s-warn">device</span> ' : ""}${l.via_ip ? '<span class="statpill s-mut">IP</span>' : ""}</td><td class="r">${fmtNum(l.shared_events)}</td></tr>`).join("")}
    </tbody></table>` : ""}
    <div class="grid" style="margin-top:4px">
      <div class="card"><h3>Tickers searched <span class="cnt">${searches.length}</span></h3>${searches.length ? anBars(searches, r => `<b class="mono">${esc(r.ticker || "")}</b>`, "n", { sub: r => r.last ? esc(String(r.last).slice(0, 10)) : "" }) : "<span class='muted sub'>none yet</span>"}</div>
      <div class="card"><h3>Tickers viewed <span class="cnt">${viewed.length}</span></h3>${viewed.length ? anBars(viewed, r => `<b class="mono">${esc(r.ticker || "")}</b>`, "n") : "<span class='muted sub'>none yet</span>"}</div>
    </div>
    <div class="section">Recent events</div>
    <div class="an-timeline">${recent.map(ev => `<div class="an-trow"><span class="an-tt mono">${esc(ev.t || "")}</span><span class="an-ty">${esc(ev.type)}</span><span class="an-td">${ev.ticker ? `<b class="mono">${esc(ev.ticker)}</b>` : `<span class="mono">${esc(ev.path || "")}</span>`}</span></div>`).join("") || "<div class='muted sub'>none</div>"}</div>`;
}


/* ---- USERS (Supabase) --------------------------------------------------- */
RENDER.users = async () => {
  const v = $("#view");
  const d = await api("/api/users");
  if (!d.ok) {
    v.innerHTML = `<div class="card"><h3>Users — not connected</h3><div class="sub">${esc(d.reason || d.error || "")}</div>
      <ol class="steps" style="margin-top:10px">${(d.setup_steps || []).map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>`;
    return;
  }
  const s = d.summary || {};
  const series = d.signups_daily || [];
  const maxN = Math.max(1, ...series.map(x => x.n));
  v.innerHTML = `
    <div class="grid">
      ${card("Total users", `<div class="big">${fmtNum(s.total)}</div><div class="sub">${fmtNum(s.confirmed)} confirmed</div>`)}
      ${card("New", `<div class="big">${fmtNum(s.new_7d)}<span class="sub"> /7d</span></div><div class="sub">${fmtNum(s.new_24h)} today · ${fmtNum(s.new_30d)}/30d</div>`)}
      ${card("Active sign-ins", `<div class="big">${fmtNum(s.active_7d)}<span class="sub"> /7d</span></div><div class="sub">${fmtNum(s.active_24h)} in 24h</div>`)}
      ${card("Sign-in methods", `${(d.providers || []).map(p => `<div class="kv"><span>${esc(p.provider)}</span><b>${fmtNum(p.n)}</b></div>`).join("") || "<span class='muted'>—</span>"}`)}
    </div>
    <div class="section">Signups (30d)</div>
    <div class="card"><div class="spark">${series.map(x => `<i style="height:${Math.round(x.n / maxN * 100)}%" title="${esc(x.day)}: ${x.n}"></i>`).join("") || "<span class='muted'>no signups in 30d</span>"}</div></div>
    <div class="section">Recent users <span class="cnt" id="uCnt"></span></div>
    <div id="uTbl"><div class="spin">loading…</div></div>`;
  const rec = await api("/api/users/recent?limit=50");
  if (rec.ok) {
    $("#uCnt").textContent = rec.users.length;
    $("#uTbl").innerHTML = `<table><thead><tr><th>Email</th><th>Provider</th><th>Joined</th><th>Last sign-in</th><th>Confirmed</th></tr></thead><tbody>
      ${rec.users.map(u => `<tr><td class="mono">${esc(u.email)}</td><td>${esc(u.provider)}</td><td class="mono sub">${esc(u.created_at || "—")}</td>
        <td class="mono sub">${esc(u.last_sign_in_at || "—")}</td><td>${u.confirmed ? "<span class='statpill s-ok'>yes</span>" : "<span class='statpill s-mut'>no</span>"}</td></tr>`).join("")}
    </tbody></table>`;
  } else { $("#uTbl").innerHTML = `<div class="card sub">${esc(rec.error || "could not load")}</div>`; }
};

/* ---- SYSTEM + SERVICES + UPTIME ----------------------------------------- */
RENDER.system = async () => {
  const v = $("#view");
  const sys = SUMMARY.system || {}, sv = SUMMARY.services || {};
  const mem = sys.memory || {}, swap = sys.swap, disk = sys.disk || {}, cpu = sys.cpu || {};
  const up = sys.uptime_s != null ? `${Math.floor(sys.uptime_s / 86400)}d ${Math.floor(sys.uptime_s % 86400 / 3600)}h` : "—";
  v.innerHTML = `
    <div class="grid">
      <div class="card"><h3>Server resources</h3>
        ${sys.available ? `
        ${meter("CPU load (last 1 min)", cpu.load1_pct, (cpu.load1 != null ? cpu.load1.toFixed(2) : "—") + ` / ${cpu.count} cores`)}
        ${meter("Memory", mem.used_pct, fmtBytes(mem.used) + " / " + fmtBytes(mem.total))}
        ${swap ? meter("Swap", swap.used_pct, fmtBytes(swap.used) + " / " + fmtBytes(swap.total)) : ""}
        ${meter("Disk", disk.used_pct, fmtBytes(disk.used) + " / " + fmtBytes(disk.total))}
        <div class="sub">running for ${up} · load 5m/15m ${cpu.load5 != null ? cpu.load5.toFixed(2) : "—"} / ${cpu.load15 != null ? cpu.load15.toFixed(2) : "—"}</div>
        ` : `<div class="sub">Server stats are only available when this console is running on the server itself.</div>`}
      </div>
      <div class="card"><h3>Site uptime</h3><div id="upBoard"><button class="btn" id="upBtn">Check all sites are up</button></div></div>
    </div>
    <div class="section">Background services <span class="cnt">${sv.available ? sv.ok_count + "/" + sv.total + " up" : "server only"}</span></div>
    <div id="svcs"></div>`;
  const svcs = $("#svcs");
  if (!sv.available) svcs.innerHTML = `<div class="card sub">${esc(sv.reason || "systemctl unavailable")}</div>`;
  else (sv.services || []).forEach(s => {
    const led = s.ok ? "ok" : (s.active === "activating" ? "warn" : "bad");
    const mem = s.memory != null ? " · " + fmtBytes(s.memory) : "";
    svcs.appendChild(h(`<div class="svc"><span class="led ${led}" style="width:10px;height:10px;border-radius:50%;flex:none"></span>
      <div><div class="nm">${esc(s.label)}</div><div class="meta mono">${esc(s.unit)} — ${esc(s.active || "?")}/${esc(s.sub || "")}${mem}${s.restarts ? " · " + s.restarts + " restarts" : ""}</div></div>
      <span class="spacer"></span><span class="statpill ${s.ok ? "s-ok" : "s-bad"}">${esc(s.active || "?")}</span></div>`));
  });
  $("#upBtn").onclick = async () => {
    $("#upBoard").innerHTML = "<span class='muted'>probing…</span>";
    const u = await api("/api/uptime/all");
    $("#upBoard").innerHTML = (u.targets || []).map(t => `<div class="kv"><span>${esc(t.label)}</span>
      <b style="color:${t.ok ? "var(--ok)" : "var(--bad)"}">${t.ok ? (t.status || "up") + " · " + t.ms + "ms" : (t.status || "down")}</b></div>`).join("");
  };
};

/* ---- FEATURES ----------------------------------------------------------- */
RENDER.features = async () => {
  const v = $("#view");
  const data = await api("/api/flags");
  const meta = SUMMARY.meta || {};
  const writable = !meta.deployed || (meta.integrations && meta.integrations.github_write);
  const note = meta.deployed
    ? (writable
        ? `Turning a switch on or off saves it straight to the live site's settings; the change takes effect within a few minutes.`
        : `Read-only. To change switches from here, a GitHub access token (<code>GH_TOKEN</code>, with Contents-write permission) must be set on the server.`)
    : `Turn features on or off. Changes are saved locally and go live on the next build.`;
  let html = `<div class="sub" style="margin-bottom:12px">${note}</div>`;
  data.order.forEach(cat => { html += `<div class="section">${esc(cat)} <span class="cnt">${data.groups[cat].length}</span></div><div id="g-${cat.replace(/\W/g, "")}"></div>`; });
  v.innerHTML = html;
  data.order.forEach(cat => { const box = $("#g-" + cat.replace(/\W/g, "")); data.groups[cat].forEach(f => box.appendChild(flagRow(f, writable))); });
};
function flagRow(f, writable) {
  const row = h(`<div class="row"></div>`);
  const sw = h(`<label class="switch"><input type="checkbox" ${f.value ? "checked" : ""} ${writable ? "" : "disabled"}><span class="slider"></span></label>`);
  const cb = sw.querySelector("input");
  cb.onchange = async () => {
    const r = await post("/api/flags/toggle", { path: f.path, value: cb.checked });
    if (r.ok) { toast(`${f.label} → ${r.new}${r.commit ? " (committed)" : ""}`); await refresh(); renderBanner(); refreshRowTags(row, f, cb.checked); }
    else { cb.checked = !cb.checked; toast(r.error || "toggle failed", true); }
  };
  row.appendChild(sw);
  row.appendChild(h(`<div><div class="lab">${esc(f.label)} ${f.master ? '<span class="tag master">main switch</span>' : ""} <span class="rowtags"></span></div><div class="note">${esc(f.note)} <code class="muted">${esc(f.path)}</code></div></div>`));
  refreshRowTags(row, f, f.value === true);
  return row;
}
function refreshRowTags(row, f, on) {
  const box = row.querySelector(".rowtags"); if (!box) return; box.innerHTML = "";
  if (on && f.missing_secrets && f.missing_secrets.length)
    box.appendChild(h(`<span class="tag inert" title="ON but required secret missing">⚠ needs ${esc(f.missing_secrets.join(", "))}</span>`));
}

/* ---- AI BRIEF ----------------------------------------------------------- */
RENDER.brief = async () => {
  const v = $("#view");
  const d = await api("/api/brief");
  const mb = d.master_brain, ad = d.ai_desk;
  const intervalSel = (target, cur) => `<select data-int="${target}" data-prev="${cur}">${[1, 2, 3, 4, 5, 6, 7].map(n => `<option value="${n}" ${n === cur ? "selected" : ""}>every ${n} day${n > 1 ? "s" : ""}</option>`).join("")}</select>`;
  v.innerHTML = `
    ${!d.deepseek_key ? `<div class="banner show" style="position:static">⚠︎ No AI key set (<code>DEEPSEEK_API_KEY</code>) — briefs won't generate even if turned on.</div>` : ""}
    <div class="section">AI morning briefs</div>
    <div class="row"><label class="switch"><input type="checkbox" id="mbEn" ${mb.enabled ? "checked" : ""}><span class="slider"></span></label>
      <div><div class="lab">Generate the morning briefs</div><div class="note">topics: ${(mb.lenses || []).join(", ")} · AI model <code>${esc(mb.model || "?")}</code></div></div>
      <span class="spacer"></span>${intervalSel("master_brain", mb.interval_days)}</div>
    <div class="row"><label class="switch"><input type="checkbox" id="mbZh" ${mb.translate_zh ? "checked" : ""}><span class="slider"></span></label>
      <div><div class="lab">Chinese version (中文)</div><div class="note">adds a low-cost AI translation to each brief</div></div></div>
    <div class="section">Last generated <span class="cnt">per topic</span></div>
    <table><thead><tr><th>Topic</th><th>Generated</th><th class="r">Age</th><th>Model</th><th>Status</th></tr></thead><tbody>
      ${(mb.items || []).map(it => `<tr><td><b>${esc(it.lens)}</b></td><td class="mono">${esc((it.generated_at || "—").replace("T", " ").slice(0, 16))}</td>
        <td class="r">${it.age_days == null ? "—" : it.age_days + "d"}</td><td class="mono">${esc(it.model || "—")}</td>
        <td>${it.degraded_reason ? `<span class="statpill s-warn">${esc(it.degraded_reason)}</span>` : `<span class="statpill s-ok">ok</span>`}</td></tr>`).join("")}
    </tbody></table>
    <div class="section">AI analyst desk</div>
    <div class="row"><label class="switch"><input type="checkbox" id="adEn" ${ad.enabled ? "checked" : ""}><span class="slider"></span></label>
      <div><div class="lab">Generate the desk note</div><div class="note">${ad.panel_enabled ? "4-analyst debate panel" : "single analyst"} · last ${ad.age_days == null ? "—" : ad.age_days + "d ago"} · ${ad.theses} calls on record</div></div>
      <span class="spacer"></span>${intervalSel("ai_desk", ad.interval_days)}</div>`;
  const meta = SUMMARY.meta || {};
  const writable = !meta.deployed || (meta.integrations && meta.integrations.github_write);
  v.querySelectorAll('input[type=checkbox], select[data-int]').forEach(el => { if (!writable) el.disabled = true; });
  $("#mbEn").onchange = (e) => toggleFlag(e.target, "master_brain.enabled", e.target.checked, "AI Brief");
  $("#mbZh").onchange = (e) => toggleFlag(e.target, "master_brain.translate_zh", e.target.checked, "中文 translation");
  $("#adEn").onchange = (e) => toggleFlag(e.target, "ai_desk.enabled", e.target.checked, "AI Desk");
  v.querySelectorAll("[data-int]").forEach(sel => sel.onchange = async () => {
    const prev = sel.dataset.prev;
    const r = await post("/api/brief/interval", { target: sel.dataset.int, days: Number(sel.value) });
    if (r.ok) { sel.dataset.prev = String(r.new); toast(`${sel.dataset.int} → every ${r.new} day(s)`); await refresh(); renderBanner(); }
    else { sel.value = prev; toast(r.error || "failed", true); }
  });
};
async function toggleFlag(el, path, value, label) {
  const r = await post("/api/flags/toggle", { path, value });
  if (r.ok) { toast(`${label} → ${r.new}${r.commit ? " (committed)" : ""}`); await refresh(); renderBanner(); }
  else { if (el) el.checked = !el.checked; toast(r.error || "failed", true); }   // revert UI on failure
}

/* ---- BUILD & DEPLOY ----------------------------------------------------- */
async function dispatch(workflow) {
  const names = { "daily.yml": "full rebuild + deploy", "pages.yml": "redeploy committed site", "weekly.yml": "weekly deep rebuild" };
  if (!confirm(`Trigger ${names[workflow] || workflow} on main? This runs GitHub Actions and may update the live site.`)) return;
  const r = await post("/api/deploy/dispatch", { workflow, confirm: true });
  if (r.ok) { toast(`Dispatched ${workflow}`); setTimeout(() => { if (CURRENT === "deploy") RENDER.deploy(); }, 1500); }
  else toast(r.error || "dispatch failed", true);
}
const STATUS_PILL = (r) => {
  if (r.status !== "completed") return `<span class="statpill s-warn">${esc(r.status)}</span>`;
  const c = r.conclusion, cls = c === "success" ? "s-ok" : (c === "failure" || c === "timed_out") ? "s-bad" : "s-mut";
  return `<span class="statpill ${cls}">${esc(c || "?")}</span>`;
};
RENDER.deploy = async () => {
  const v = $("#view"); const hasTok = SUMMARY.meta && SUMMARY.meta.has_token;
  v.innerHTML = `<div id="depActions"></div><div class="section">Recent build runs</div><div id="runs"><div class="spin">loading…</div></div>`;
  const a = $("#depActions");
  [["daily.yml", "▶ Rebuild & deploy", "primary"], ["pages.yml", "⟳ Redeploy site only", ""], ["weekly.yml", "↻ Weekly deep build", ""]].forEach(([wf, label, cls]) => {
    const b = h(`<button class="btn ${cls}" style="margin-right:8px">${label}</button>`); b.disabled = !hasTok; b.onclick = () => dispatch(wf); a.appendChild(b);
  });
  if (!hasTok) a.appendChild(h(`<div class="sub" style="margin-top:8px">The buttons above need a GitHub access token (<code>GH_TOKEN</code>, Actions-write) set on the server. The run history below works without one.</div>`));
  const data = await api("/api/deploy"); const runs = $("#runs");
  if (!data.ok) { runs.innerHTML = `<div class="card sub">Could not load runs: ${esc(data.error || "?")}</div>`; return; }
  runs.innerHTML = `<table><thead><tr><th>Build</th><th>Trigger</th><th>Status</th><th>Branch</th><th>Started</th><th></th></tr></thead><tbody>
    ${data.runs.map(r => `<tr><td><b>${esc(r.workflow || r.name)}</b></td><td class="sub">${esc(r.event)}</td><td>${STATUS_PILL(r)}</td>
      <td class="mono">${esc(r.branch)}</td><td class="sub mono">${esc((r.run_started_at || r.created_at || "").replace("T", " ").slice(0, 16))}</td>
      <td><a href="${esc(r.html_url)}" target="_blank" rel="noopener">open ↗</a></td></tr>`).join("")}
  </tbody></table>`;
};

/* ---- HEALTH ------------------------------------------------------------- */
RENDER.health = async () => {
  const v = $("#view"); const d = await api("/api/health");
  if (d.error) { v.innerHTML = card("Error", `<div class="sub" style="color:var(--bad)">${esc(d.error)}</div>`); return; }
  const src = d.sources || {};
  const sp = (s) => { const lbl = s === "stale" ? "out of date" : s === "dead" ? "down" : s; return `<span class="statpill ${s === "ok" ? "s-ok" : s === "stale" ? "s-warn" : s === "dead" ? "s-bad" : "s-mut"}">${esc(lbl)}</span>`; };
  v.innerHTML = `
    <div class="sub" style="margin-bottom:10px">Health of the nightly data pipeline and each data feed it pulls from.</div>
    <div class="grid">
      ${card("Nightly pipeline", `<div class="big" style="color:${d.healthy ? "var(--ok)" : "var(--warn)"}">${d.healthy ? "Healthy" : "Attention"}</div><div class="sub">last run ${fmtAge(d.age_hours)} ago${d.stale ? " · OUT OF DATE" : ""}</div>`)}
      ${card("Data feeds", `<div class="big">${src.ok}/${src.total}</div><div class="sub">${src.stale} out of date · ${src.dead} down</div>`)}
      ${card("Auto-paused feeds", `<div class="big" style="color:${d.broad_outage ? "var(--bad)" : "var(--text)"}">${d.breaker_tripped}</div><div class="sub">paused after repeated errors${d.broad_outage ? " · MANY FEEDS DOWN" : ""}</div>`)}
    </div>
    <div class="section">Dashboard freshness</div>
    <div class="grid">${(d.markets || []).map(m => `<div class="card"><h3>${esc(m.label)}</h3><div class="big" style="font-size:18px">${m.exists ? fmtAge(m.age_hours) + " ago" : "<span style='color:var(--bad)'>missing</span>"}</div><div class="sub">${esc(m.date || "")}</div></div>`).join("")}</div>
    <div class="section">Data feeds <span class="cnt">${(d.source_rows || []).length}</span></div>
    <table><thead><tr><th>Feed</th><th>Status</th><th class="r">Rows</th><th>Last date</th><th class="r">Auto-pause</th><th>Error</th></tr></thead><tbody>
      ${(d.source_rows || []).map(s => `<tr><td class="mono">${esc(s.name)}</td><td>${sp(s.status)}</td><td class="r">${s.rows ?? "—"}</td>
        <td class="mono sub">${esc(s.last_date || "—")}</td><td class="r">${s.breaker || 0}</td><td class="sub" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(s.error || "")}">${esc(s.error || "")}</td></tr>`).join("")}
    </tbody></table>`;
};

/* ---- AI COST ------------------------------------------------------------ */
RENDER.cost = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="sub muted">Loading AI cost data…</div>`;
  const d = await api("/api/cost");
  if (d.error) { v.innerHTML = card("Error", `<div class="sub" style="color:var(--bad)">${esc(d.error)}</div>`); return; }
  const r = d.realized || {};
  const m = d.measured || {};
  const ms = m.summary || null;

  // ── (a) Measured usage summary cards ────────────────────────────────────
  const oauthNote = `<div class="sub muted" style="font-size:11px;margin-top:3px">subscription keys — API-equivalent value, not billed</div>`;
  const hasOAuth = ms && ms.by_provider && ms.by_provider["claude_oauth"] && (ms.by_provider["claude_oauth"].calls > 0);

  let measuredHtml = "";
  if (ms) {
    const tod = ms.today || {};
    const d7  = ms.d7  || {};
    const d30  = ms.d30  || {};
    measuredHtml = `
      <div class="section">Measured usage</div>
      <div class="grid">
        ${card("Today", `<div class="big">${fmtUSD(tod.usd || 0)}</div><div class="sub">${(tod.calls||0)} calls · ${fmtTokens(tod.input_tokens||0)} in / ${fmtTokens(tod.output_tokens||0)} out</div>${hasOAuth ? oauthNote : ""}`)}
        ${card("Last 7 days", `<div class="big">${fmtUSD(d7.usd || 0)}</div><div class="sub">${(d7.calls||0)} calls · ${fmtTokens(d7.input_tokens||0)} in / ${fmtTokens(d7.output_tokens||0)} out</div>${hasOAuth ? oauthNote : ""}`)}
        ${card("Last 30 days", `<div class="big">${fmtUSD(d30.usd || 0)}</div><div class="sub">${(d30.calls||0)} calls · ${fmtTokens(d30.input_tokens||0)} in / ${fmtTokens(d30.output_tokens||0)} out</div>${hasOAuth ? oauthNote : ""}`)}
      </div>`;
  } else {
    measuredHtml = `<div class="section">Measured usage</div><div class="card sub muted">No usage ledger yet — data/ai_costs/usage.jsonl will be written as lanes record calls.</div>`;
  }

  // ── (b) By consumer / By key tables ─────────────────────────────────────
  let consumerHtml = "";
  if (ms && ms.by_lane && Object.keys(ms.by_lane).length) {
    consumerHtml += `<div class="section">By consumer (30d)</div>
      <table><thead><tr><th>Lane</th><th class="r">Calls</th><th class="r">Tokens in</th><th class="r">Tokens out</th><th class="r">Est USD</th></tr></thead><tbody>
      ${Object.entries(ms.by_lane).map(([lane, lb]) => `<tr>
        <td class="mono">${esc(lane)}</td>
        <td class="r">${(lb.calls||0)}</td>
        <td class="r">${fmtTokens(lb.input_tokens||0)}</td>
        <td class="r">${fmtTokens(lb.output_tokens||0)}</td>
        <td class="r">${fmtUSD(lb.usd||0)}</td>
      </tr>`).join("")}
      </tbody></table>`;
  }
  if (ms && ms.by_key && Object.keys(ms.by_key).length) {
    consumerHtml += `<div class="section">By key (30d)</div>
      <table><thead><tr><th>Key / env var</th><th class="r">Calls</th><th class="r">Tokens in</th><th class="r">Tokens out</th><th class="r">Est USD</th></tr></thead><tbody>
      ${Object.entries(ms.by_key).map(([kid, kb]) => `<tr>
        <td class="mono">${esc(kid||"—")}</td>
        <td class="r">${(kb.calls||0)}</td>
        <td class="r">${fmtTokens(kb.input_tokens||0)}</td>
        <td class="r">${fmtTokens(kb.output_tokens||0)}</td>
        <td class="r">${fmtUSD(kb.usd||0)}</td>
      </tr>`).join("")}
      </tbody></table>`;
  }

  // ── (c) Metabolism runs with achievements ────────────────────────────────
  const cycleRows = (m.recent_cycles || []);
  let cyclesHtml = "";
  if (cycleRows.length) {
    cyclesHtml = `<div class="section">Metabolism runs (cost per cycle)</div>
      <table><thead><tr><th>Cycle</th><th>What it did</th><th class="r">Tokens in</th><th class="r">Tokens out</th><th class="r">Est USD</th></tr></thead><tbody>
      ${cycleRows.map(cy => `<tr>
        <td class="mono sub">${esc((cy.cycle_id||"").slice(0,32))}</td>
        <td class="sub">${esc(cy.achievement || "—")}</td>
        <td class="r">${fmtTokens(cy.input_tokens||0)}</td>
        <td class="r">${fmtTokens(cy.output_tokens||0)}</td>
        <td class="r">${cy.est_cost_usd != null ? fmtUSD(cy.est_cost_usd) : "—"}</td>
      </tr>`).join("")}
      </tbody></table>`;
  }

  // ── (d) Mastermind portfolio bot ──────────────────────────────────────────
  const mm = m.mastermind || null;
  let mmHtml = `<div class="section">Mastermind portfolio bot</div>`;
  if (!mm) {
    mmHtml += `<div class="card sub muted">No bot cost data yet — data/mastermind/cost_summary.json is written by the bot process.</div>`;
  } else {
    const t30 = mm.totals_30d || {};
    mmHtml += `<div class="grid">
      ${card("Bot 30d total", `<div class="big">${fmtUSD(t30.usd||0)}</div><div class="sub">${fmtTokens((t30.input_tokens||0)+(t30.output_tokens||0))} tokens</div>`)}
    </div>`;
    const byBook = t30.by_book || {};
    if (Object.keys(byBook).length) {
      mmHtml += `<table><thead><tr><th>Book</th><th class="r">Calls</th><th class="r">Tokens</th><th class="r">Est USD</th></tr></thead><tbody>
        ${Object.entries(byBook).map(([book, bb]) => `<tr>
          <td class="mono">${esc(book)}</td>
          <td class="r">${(bb.calls||0)}</td>
          <td class="r">${fmtTokens((bb.input_tokens||0)+(bb.output_tokens||0))}</td>
          <td class="r">${fmtUSD(bb.usd||0)}</td>
        </tr>`).join("")}
        </tbody></table>`;
    }
    if (mm.as_of) mmHtml += `<div class="sub muted" style="margin-top:6px">as of ${esc(mm.as_of)}</div>`;
  }

  // ── (e) Raw Key Usage table (moved from Metabolism tab) ──────────────────
  const rawKeySection = `<div class="section">Raw Key Usage (rate-limit headers)</div>
    <div class="card" id="costKeysCard"><div class="sub muted">Loading…</div></div>`;

  // ���─ (f) Legacy DeepSeek estimator ────────────────────────────────────────
  const legacyHtml = `
    <div class="section">DeepSeek cost estimates (estimate only)</div>
    <div class="card sub muted" style="margin-bottom:8px">Estimate only — based on call counts × assumed token sizes, not measured token usage.</div>
    <div class="grid">
      ${card("Est. monthly", `<div class="big">${fmtUSD(d.monthly_usd)}</div><div class="sub">~${(d.assumptions||{}).build_days_per_month||21} build-days/mo</div>`)}
      ${card("Per build", `<div class="big">${fmtUSD(d.per_build_usd)}</div><div class="sub">${fmtUSD(d.effective_daily_usd)}/day effective</div>`)}
      ${card("Actually generated", `<div class="big">${r.stockbrief_files || 0}</div><div class="sub">stock briefs · ${r.ai_desk_theses_logged || 0} analyst calls</div>`)}
    </div>
    ${!d.deepseek_key ? `<div class="card sub" style="margin-top:12px;color:var(--warn)">No AI key set — actual spend is $0.</div>` : ""}
    <div class="section">What's using AI (DeepSeek)</div>
    <table><thead><tr><th>Feature</th><th>On</th><th>Model</th><th class="r">Calls/build</th><th class="r">$/build</th><th>How often</th></tr></thead><tbody>
      ${(d.components || []).map(c => `<tr><td><b>${esc(c.name)}</b><div class="sub">${esc(c.note)}</div></td>
        <td>${c.enabled ? "<span class='statpill s-ok'>yes</span>" : "<span class='statpill s-mut'>no</span>"}</td>
        <td class="mono">${esc(c.model)}</td><td class="r">${c.calls_per_build}</td><td class="r">${fmtUSD(c.cost_per_build)}</td><td class="sub">every ${c.interval_days}d</td></tr>`).join("")}
    </tbody></table>`;

  v.innerHTML = measuredHtml + consumerHtml + cyclesHtml + mmHtml + rawKeySection + legacyHtml;

  // Async raw key usage loader (same endpoint as Metabolism tab)
  (async () => {
    const keysCard = $("#costKeysCard");
    if (!keysCard) return;
    let ku;
    try {
      ku = await api("/api/metabolism/keys");
    } catch (e) {
      const kc = $("#costKeysCard");
      if (kc) kc.innerHTML = `<div class="sub muted">Could not load key usage: ${esc(String(e))}</div>`;
      return;
    }
    const kc = $("#costKeysCard");
    if (!kc) return;
    if (ku && ku.error) {
      kc.innerHTML = `<div class="sub muted">${esc(ku.error)}</div>`;
      return;
    }
    const rows = Array.isArray(ku) ? ku : [];
    if (!rows.length) {
      kc.innerHTML = `<div class="sub muted">No key usage data available.</div>`;
      return;
    }
    const fmtTok = (n) => n == null ? "—" : Number(n) >= 1000 ? `${(Number(n)/1000).toFixed(1)}k` : String(n);
    kc.innerHTML = `<table><thead><tr>
      <th>Key ID</th><th>Enabled</th><th>Cooling</th><th>Reset hint</th>
      <th class="r">5h est tokens</th><th class="r">5h sessions</th>
      <th class="r">7d est tokens</th><th class="r">7d sessions</th>
      <th>Last outcome</th><th>Reported rate-limit headers</th>
    </tr></thead><tbody>
    ${rows.map(k => {
      const coolLabel = k.cooling ? (k.cool_kind ? `<span class="statpill s-warn">${esc(k.cool_kind)}</span>` : `<span class="statpill s-warn">cooling</span>`) : `<span class="statpill s-ok">ok</span>`;
      const enabledLabel = k.enabled ? `<span class="statpill s-ok">on</span>` : `<span class="statpill s-bad">off</span>`;
      const presentLabel = k.present ? "" : ` <span class="statpill s-mut">absent</span>`;
      const headers = k.ratelimit_headers && typeof k.ratelimit_headers === "object"
        ? Object.entries(k.ratelimit_headers).map(([h, hv]) => `<div class="sub mono">${esc(h)}: <b>${esc(String(hv))}</b> <span class="muted">(reported)</span></div>`).join("")
        : `<span class="muted sub">—</span>`;
      const displayKeyId = k.key_id === "legacy" ? "legacy (deprecated)" : (k.key_id || "—");
      return `<tr>
        <td class="mono">${esc(displayKeyId)}${presentLabel}</td>
        <td>${enabledLabel}</td>
        <td>${coolLabel}</td>
        <td class="sub mono">${esc(k.reset_hint || "—")}</td>
        <td class="r">${fmtTok(k.window_5h_est_tokens)} <span class="muted sub">est.</span></td>
        <td class="r">${k.window_5h_sessions != null ? k.window_5h_sessions : "—"}</td>
        <td class="r">${fmtTok(k.weekly_est_tokens)} <span class="muted sub">est.</span></td>
        <td class="r">${k.weekly_sessions != null ? k.weekly_sessions : "—"}</td>
        <td>${k.last_outcome ? `<span class="statpill ${k.last_outcome === "ok" ? "s-ok" : "s-bad"}">${esc(k.last_outcome)}</span>` : `<span class="muted sub">—</span>`}</td>
        <td style="max-width:320px">${headers}</td>
      </tr>`;
    }).join("")}
    </tbody></table>
    <div class="sub muted" style="margin-top:8px">est. = locally-observed rolling window estimate · reported = Anthropic response header value</div>`;
  })();
};

/* ---- CONTENT ------------------------------------------------------------ */
RENDER.content = async () => {
  const v = $("#view"); const d = await api("/api/content");
  v.innerHTML = `
    <div class="grid">
      ${card("Pages", `<div class="big">${d.total_pages}</div><div class="sub">published pages</div>`)}
      ${card("Total size", `<div class="big">${d.total_mb} MB</div><div class="sub">${d.total_kb} KB</div>`)}
      ${card("Is the site up?", `<div id="upBox"><button class="btn" id="upBtn2">Check live site</button></div>`)}
      ${card("Links", `<div id="lkBox"><button class="btn" id="lkBtn">Check internal links</button></div>`)}
    </div>
    <div class="section">All pages <span class="cnt">${d.total_pages}</span></div>
    <table><thead><tr><th>Page</th><th class="r">Size (KB)</th><th class="r">Updated</th></tr></thead><tbody>
      ${d.pages.map(p => `<tr><td class="mono">${esc(p.name)}</td><td class="r">${p.kb}</td><td class="r sub">${fmtAge(p.age_hours)} ago</td></tr>`).join("")}
    </tbody></table>`;
  $("#upBtn2").onclick = async () => {
    $("#upBox").innerHTML = "<span class='muted'>probing…</span>"; const u = await api("/api/uptime");
    $("#upBox").innerHTML = u.ok ? `<div class="big" style="font-size:18px;color:var(--ok)">200 OK</div><div class="sub">${u.ms} ms · ${(u.bytes / 1024).toFixed(0)} KB</div>`
      : `<div class="big" style="font-size:18px;color:var(--bad)">${u.status || "down"}</div><div class="sub">${esc(u.error || "")}</div>`;
  };
  $("#lkBtn").onclick = async () => {
    $("#lkBox").innerHTML = "<span class='muted'>scanning…</span>"; const l = await api("/api/content/links");
    $("#lkBox").innerHTML = `<div class="big" style="font-size:18px;color:${l.count ? "var(--warn)" : "var(--ok)"}">${l.count} broken</div><div class="sub">${l.checked_pages} pages scanned</div>`;
    if (l.count) { const sec = h(`<div></div>`); sec.innerHTML = `<div class="section">Broken internal links <span class="cnt">${l.count}</span></div>
      <table><thead><tr><th>Page</th><th>Link</th></tr></thead><tbody>${l.broken.map(b => `<tr><td class="mono">${esc(b.page)}</td><td class="mono" style="color:var(--bad)">${esc(b.link)}</td></tr>`).join("")}</tbody></table>`; $("#view").appendChild(sec); }
  };
};

/* ---- NEURAL WEB (W8a) --------------------------------------------------- */
/* Operator HQ: four collapsible sections over the whole nervous system.
   Panel reads COMMITTED artifacts only — the VPS-clone model (no engine imports).
   Every section fails-open: missing artifact → honest 'not yet written' card. */

function nwCollapse(id, title, bodyHtml, open = true) {
  const uid = "nwsec-" + id;
  return `<details ${open ? "open" : ""} class="nw-section">
    <summary class="section" style="cursor:pointer;user-select:none;list-style:none;display:flex;align-items:center;gap:8px">
      <span style="font-size:11px;opacity:.5">${open ? "▾" : "▸"}</span>${title}
    </summary>
    <div id="${uid}">${bodyHtml}</div>
  </details>`;
}

function nwMissing(note) {
  return `<div class="card"><div class="sub" style="color:var(--warn)">${esc(note || "not generated yet")}</div></div>`;
}

function nwFmtAge(hrs) {
  if (hrs == null) return `<span class="muted">—</span>`;
  const cls = hrs > 48 ? "bad" : hrs > 30 ? "warn" : "ok";
  return `<span style="color:var(--${cls})">${fmtAge(hrs)}</span>`;
}

function nwPill(label, cls) {
  return `<span class="statpill ${cls}">${esc(label)}</span>`;
}

/* Section A — Engine-Health Board */
function nwSectionEngineHealth(eh) {
  if (!eh) return nwMissing("engine_health missing");
  let html = `<div class="grid">`;

  // Spine index card
  const sp = eh.spine || {};
  html += card("Daily data snapshot", sp.missing
    ? `<div class="sub" style="color:var(--warn)">${esc(sp.note)}</div>`
    : `<div class="kv"><span>Built</span><b>${nwFmtAge(sp.age_hours)} ago</b></div>
       <div class="kv"><span>At</span><span class="mono sub">${esc(sp.produced_at || "—")}</span></div>
       <div class="kv"><span>Fingerprint</span><span class="mono sub">${esc(sp.inputs_hash || "—")}</span></div>`);

  // Kernel decisions card
  const kd = eh.kernel || {};
  html += card("Signal test results", kd.missing
    ? `<div class="sub" style="color:var(--warn)">${esc(kd.note)}</div>`
    : `<div class="kv"><span>Test run</span><b>${kd.display_only ? nwPill("none yet — view-only", "s-warn") : nwPill("done", "s-ok")}</b></div>
       <div class="kv"><span>Next test due</span><b>${esc(kd.next_batch_due || "—")}</b></div>
       <div class="kv"><span>Signals that passed</span><b>${kd.n_survivors != null ? kd.n_survivors : "—"}</b></div>
       <div class="note muted" style="margin-top:6px">${esc(kd.note || "")}</div>`);

  // SLA compliance card
  const sla = eh.sla || {};
  const slaColor = sla.missing ? "warn" : sla.n_breaches === 0 ? "ok" : sla.n_breaches < 5 ? "warn" : "bad";
  html += card("On-time data", sla.missing
    ? `<div class="sub" style="color:var(--warn)">${esc(sla.note)}</div>`
    : `<div class="big" style="color:var(--${slaColor})">${sla.n_breaches}<span class="sub"> late</span></div>
       <div class="sub">${sla.total} data files tracked · ${sla.n_no_mtime || 0} only on the server</div>`);

  // Kernel families armed
  const kf = eh.kernel_families || {};
  html += card("Signal groups active", kf.missing
    ? `<div class="sub" style="color:var(--warn)">${esc(kf.note)}</div>`
    : `<div class="big">${kf.n_armed}<span class="sub"> of ${kf.n_total} on</span></div>
       <div class="sub">${kf.n_armed === 0 ? "None turned on yet" : kf.armed_names.join(", ")}</div>`);

  // Lagging signal families
  const lg = eh.lagging || {};
  html += card("Slow / stale signal groups", lg.missing
    ? `<div class="sub" style="color:var(--warn)">${esc(lg.note)}</div>`
    : `<div class="big" style="color:${lg.n_flagged > 0 ? "var(--warn)" : "var(--ok)"}">${lg.n_flagged}<span class="sub"> flagged</span></div>
       <div class="sub">${lg.n_families} groups total${lg.n_flagged ? " — " + lg.flagged_names.slice(0, 4).join(", ") + (lg.flagged_names.length > 4 ? "…" : "") : " — all clear"}</div>`);

  // Read-gate baseline
  const rg = eh.read_gate || {};
  html += card("Data-access check", rg.missing
    ? `<div class="sub" style="color:var(--warn)">${esc(rg.note)}</div>`
    : `<div class="big">${rg.n_undeclared}<span class="sub"> unexpected readers</span></div>
       <div class="sub">new unexpected data readers block the build</div>`);

  html += `</div>`;

  // SLA breach table (if any)
  if (!sla.missing && sla.n_breaches > 0) {
    const breaches = sla.breaches || [];
    html += `<div class="section" style="margin-top:14px">Late data files — worst first <span class="cnt">${breaches.length}</span></div>
      <table><thead><tr><th>File</th><th>Tier</th><th>Owner</th><th class="r">Target (h)</th><th class="r">Age (h)</th><th class="r">Overdue (h)</th><th>Location</th></tr></thead><tbody>
      ${breaches.map(b => `<tr>
        <td><b>${esc(b.id)}</b></td>
        <td class="sub">${esc(b.tier)}</td>
        <td class="sub">${esc(b.owner)}</td>
        <td class="r">${b.sla_hours}</td>
        <td class="r" style="color:var(--warn)">${b.age_hours}</td>
        <td class="r" style="color:var(--bad)">+${b.overdue_hours}</td>
        <td class="mono sub" style="font-size:11px">${esc(b.path)}</td>
      </tr>`).join("")}
      </tbody></table>`;
  }

  // Kernel families detail table
  if (!kf.missing && kf.families && kf.families.length) {
    html += `<div class="section" style="margin-top:14px">Signal groups — detail <span class="cnt">${kf.families.length}</span></div>
      <table><thead><tr><th>Group</th><th>On</th><th>Days since last signal</th><th>Last signal</th><th>Time-frames</th><th>Sample size</th></tr></thead><tbody>
      ${kf.families.map(f => `<tr>
        <td><b>${esc(f.name)}</b></td>
        <td>${f.armed ? nwPill("on", "s-ok") : nwPill("off", "s-mut")}</td>
        <td class="r">${f.staleness_days != null ? f.staleness_days : "—"}</td>
        <td class="mono sub">${esc(f.date_last || "—")}</td>
        <td class="sub">${esc((f.horizon_keys || []).join(", ") || "—")}</td>
        <td class="r">${f.n_eff != null ? f.n_eff : "—"}</td>
      </tr>`).join("")}
      </tbody></table>`;
  }

  return html;
}

/* Section B — Reflexes & Firings */
function nwSectionReflexLog(rl) {
  if (!rl) return nwMissing("reflex_log missing");
  if (rl.missing) return nwMissing(rl.note);

  let html = `<div class="sub" style="margin-bottom:10px">Small automatic rules that watch for a condition and react. This shows which ones exist and how often they've triggered.</div>
    <div class="grid">
    ${card("Set-up reactions", `<div class="big">${rl.n_registered}</div><div class="sub">rules defined</div>`)}
    ${card("Actively logging", `<div class="big" style="color:${rl.n_mirroring > 0 ? "var(--ok)" : "var(--muted)"}">${rl.n_mirroring}</div><div class="sub">of ${rl.n_registered} are recording activity</div>`)}
  </div>`;

  html += `<div class="section" style="margin-top:14px">All reactions <span class="cnt">${(rl.per_reflex || []).length}</span></div>
    <table><thead><tr><th>Reaction</th><th>Status</th><th>Times fired (7d)</th><th>Last fired</th><th>Alert candidate</th><th>Category</th></tr></thead><tbody>
    ${(rl.per_reflex || []).map(r => `<tr>
      <td><b>${esc(r.name)}</b><div class="note sub" style="max-width:280px">${esc(r.description || "")}</div></td>
      <td>${r.mirroring ? nwPill("logging", "s-ok") : nwPill("set up", "s-mut")}</td>
      <td class="r">${r.n_firings_7d}</td>
      <td class="mono sub">${r.last_fired ? nwFmtAge(r.last_fired_age_hours) + " ago" : "—"}</td>
      <td>${r.push_tier_candidate ? nwPill("alert candidate", "s-warn") : nwPill("background", "s-mut")}</td>
      <td class="mono sub" style="font-size:11px">${esc(r.claim_family || "—")}</td>
    </tr>${(r.recent_firings || []).length ? `<tr style="background:var(--line)"><td colspan="6" style="padding:4px 8px">
      <span class="muted sub">Recently fired: </span>
      ${r.recent_firings.map(f => `<span class="mono sub" style="margin-right:12px">${esc(f.ts || f.timestamp || f.fired_at || "?")} · ${esc(f.trigger_key || f.action || f.scope_key || "")}</span>`).join("")}
    </td></tr>` : ""}`).join("")}
    </tbody></table>`;

  return html;
}

/* Section C — Bus Graph (Confluence) */
function nwSectionBusGraph(bg) {
  if (!bg) return nwMissing("bus_graph missing");
  if (bg.missing) return nwMissing(bg.note);

  let html = `<div class="card" style="margin-bottom:10px"><div class="sub" style="color:var(--warn)">
    This section is <b>view-only</b> — it doesn't change or rank anything the site does. The numbers below are for information only.
  </div></div>`;

  html += `<div class="grid">
    ${card("Signals", `<div class="big">${bg.n_nodes}</div><div class="sub">individual signals tracked</div>`)}
    ${card("Links", `<div class="big">${bg.n_edges}</div><div class="sub">${Object.entries(bg.edge_types || {}).map(([t, n]) => `${n} ${t}`).join(" · ") || "—"}</div>`)}
    ${card("Disagreements", `<div class="big" style="color:${bg.n_contradictions > 0 ? "var(--warn)" : "var(--ok)"}">${bg.n_contradictions}</div>
      <div class="sub">${Object.entries(bg.by_severity || {}).map(([s, n]) => `${n} ${s}`).join(" · ") || "none"}</div>`)}
  </div>`;

  if (bg.top_pair_ids && bg.top_pair_ids.length) {
    html += `<div class="section" style="margin-top:14px">Biggest disagreements</div>
      <table><thead><tr><th>Signals</th><th>Details</th></tr></thead><tbody>
      ${bg.top_pair_ids.map(pid => {
        const rec = (bg.top_contradictions || []).find(r => r.pair_id === pid);
        return `<tr><td class="mono"><b>${esc(pid)}</b></td><td class="sub">${rec
          ? esc(rec.note || rec.description || JSON.stringify(rec).slice(0, 120))
          : "—"}</td></tr>`;
      }).join("")}
      </tbody></table>`;
  }

  html += `<div class="sub muted" style="margin-top:8px">as of ${esc(bg.asof || "—")} · view-only by design</div>`;
  return html;
}

/* Section D — Governance */
function nwSectionGovernance(gov) {
  if (!gov) return nwMissing("governance missing");
  let html = "";

  // Cortex probation card
  const prob = gov.probation || {};
  html += `<div class="grid">`;
  if (prob.missing) {
    html += card("AI \"cortex\" trial status", `<div class="sub" style="color:var(--warn)">${esc(prob.note)}</div>`);
  } else {
    html += card("AI \"cortex\" trial status", `
      <div class="kv"><span>Level</span><b>${nwPill(prob.tier || "?", prob.granted ? "s-ok" : "s-warn")}</b></div>
      <div class="kv"><span>Authority granted?</span><b style="color:${prob.granted ? "var(--ok)" : "var(--warn)"}">${prob.granted ? "YES" : "NO"}</b></div>
      <div class="kv"><span>Reason</span><span class="sub">${esc(prob.reason || "—")}</span></div>
      <div class="kv"><span>Scored so far / needed</span><b>${prob.n_graded != null ? prob.n_graded : "—"} / ${prob.min_n}</b></div>
      <div class="kv"><span>Correct hits / needed</span><b>${prob.hits != null ? prob.hits : "—"} / ${prob.min_events}</b></div>
      ${prob.lapses_at ? `<div class="kv"><span>Trial ends</span><b>${esc(prob.lapses_at)}</b></div>` : ""}`);
  }

  // Cortex memo card
  const cm = gov.cortex_memo || {};
  if (cm.missing) {
    html += card("AI \"cortex\" latest note", `<div class="sub" style="color:var(--warn)">${esc(cm.note)}</div>`);
  } else {
    html += card("AI \"cortex\" latest note", `
      <div class="kv"><span>As of</span><span class="mono sub">${esc(cm.as_of || "—")}</span></div>
      <div class="note" style="margin-top:6px">${esc(cm.summary || "—")}</div>
      ${cm.what_fired && cm.what_fired.length ? `<div class="kv" style="margin-top:8px"><span>What it flagged</span><span class="sub">${cm.what_fired.map(s => esc(s)).join("; ")}</span></div>` : ""}
      ${cm.deserves_operator && cm.deserves_operator.length ? `<div class="kv"><span>For you to review</span><span class="sub">${cm.deserves_operator.map(s => esc(s)).join("; ")}</span></div>` : ""}
      <div class="kv" style="margin-top:6px"><span>Tool calls</span><span class="mono sub">${Object.entries(cm.tool_call_census || {}).map(([k, n]) => `${k}×${n}`).join(", ") || "—"}</span></div>
      ${cm.is_context_only ? `<div class="note muted" style="margin-top:4px">background context only — it can't act on its own</div>` : ""}`);
  }

  html += `</div>`;

  // Governance ledger table
  const evts = gov.recent_events || [];
  const EVT_CLS = { authority_grant: "s-ok", authority_lapse: "s-bad", tier_promotion: "s-ok", tier_demotion: "s-bad", article3_review: "s-warn", article6_review: "s-warn", a6_auto_apply: "s-warn", a6_llm_proposed: "s-warn", config_arm: "s-ok", config_disarm: "s-bad", operator_override: "s-warn" };
  html += `<div class="section" style="margin-top:14px">Permissions &amp; changes — last ${evts.length} events (newest first)</div>`;
  if (!evts.length) {
    html += `<div class="card"><div class="sub muted">No changes recorded yet.</div></div>`;
  } else {
    html += `<table><thead><tr><th>When</th><th>What happened</th><th>Target</th><th>Rule</th><th>By</th><th>Note</th></tr></thead><tbody>
      ${evts.map(e => `<tr>
        <td class="mono sub" style="font-size:11px;white-space:nowrap">${esc((e.ts || "?").slice(0, 19))}</td>
        <td>${nwPill(e.event_type || "?", EVT_CLS[e.event_type] || "s-mut")}</td>
        <td class="mono sub" style="max-width:180px;word-break:break-all">${esc(e.target || "—")}</td>
        <td class="sub">${e.article != null ? "A" + e.article : "—"}</td>
        <td class="sub">${esc(e.authored_by || "—")}</td>
        <td class="sub" style="max-width:300px">${esc((e.note || "").slice(0, 160))}</td>
      </tr>`).join("")}
    </tbody></table>`;
  }

  return html;
}

/* Section E — Factor Intelligence (§D PR-4, RUL-NW7/NW8) */
function nwSectionFactorIntelligence(fi) {
  if (!fi) return nwMissing("factor_intelligence section missing");
  let html = `<div class="grid">`;

  // State artifact freshness card
  if (fi.state_missing) {
    html += card("State Artifact", `<div class="sub" style="color:var(--warn)">data/neuralweb/factor_intelligence_state.json not yet written — factor_panel job has not run. Panel dormant.</div>`);
  } else {
    const ageColor = fi.state_age_hours == null ? "muted" : fi.state_age_hours > 48 ? "bad" : fi.state_age_hours > 30 ? "warn" : "ok";
    html += card("State Artifact", `
      <div class="kv"><span>As of</span><b>${esc(fi.state_as_of || "—")}</b></div>
      <div class="kv"><span>Freshness</span><b>${nwFmtAge(fi.state_age_hours)}</b></div>`);
  }

  // Panel health card
  const ph = fi.panel_health || {};
  html += card("Panel Health", fi.state_missing
    ? `<div class="sub" style="color:var(--warn)">state artifact absent</div>`
    : `<div class="kv"><span>Dates</span><b>${ph.n_dates != null ? ph.n_dates : "—"}</b></div>
       <div class="kv"><span>Latest</span><b>${esc(ph.latest_date || "—")}</b></div>
       <div class="kv"><span>Floor (≥60d)</span><b style="color:var(--${ph.floor_met ? "ok" : "warn"})">${ph.floor_met ? "✓ met" : "pending"}</b></div>`);

  // Pair G ledger card
  const pg = fi.pair_g || {};
  html += card("Pair G Ledger", `
    <div class="kv"><span>Ledger present</span><b style="color:var(--${pg.ledger_present ? "ok" : "muted"})">${pg.ledger_present ? "yes" : "not yet"}</b></div>
    <div class="kv"><span>Today count</span><b>${pg.today_count != null ? pg.today_count : "—"}</b></div>
    <div class="note muted" style="margin-top:4px">Severity ceiling: note (H2 gate-passed required for tension)</div>`);

  // Factor attention authority card
  const fa = fi.factor_attention || {};
  const attColor = fa.granted ? "ok" : "muted";
  html += card("Factor Attention Authority", `
    <div class="kv"><span>Tier</span><b>${esc(fa.tier || "—")}</b></div>
    <div class="kv"><span>Granted</span><b style="color:var(--${attColor})">${fa.granted ? "yes" : "no"}</b></div>
    <div class="kv"><span>Firings</span><b>${fa.n_firings != null ? fa.n_firings : "—"}</b></div>
    <div class="kv"><span>Graded</span><b>${fa.n_graded != null ? fa.n_graded : "—"}</b></div>
    <div class="note muted" style="margin-top:4px">${esc(fa.reason || "")}</div>`);

  // Hypotheses block card
  const hyp = fi.hypotheses || {};
  const hypEntries = ["h1","h2","h3","h4","h5"].map(hi => {
    const s = (hyp[hi] || {}).status || "not-visible-in-tree";
    const chipCls = s === "gate-passed" ? "s-ok" : s === "accruing" ? "s-warn" : "s-mut";
    return `<div class="kv"><span>${hi.toUpperCase()}</span><b>${nwPill("BH-WITHHELD", "s-bad")} ${nwPill(s, chipCls)}</b></div>`;
  }).join("");
  html += card("Hypotheses H1–H5", `
    ${hypEntries}
    <div class="note muted" style="margin-top:4px">BH-WITHHELD mandatory on all 5 until family FDR sweep (est. ≥2027)</div>`);

  // §9.2 Alerts card
  const alerts = fi.alerts || [];
  html += card("§9.2 Alerts", alerts.length === 0
    ? `<div class="sub" style="color:var(--ok)">No alerts</div>`
    : `<ul style="margin:0;padding-left:16px">${alerts.map(a => `<li class="sub" style="color:var(--warn);margin-bottom:4px">${esc(a)}</li>`).join("")}</ul>`);

  html += `</div>`;
  return html;
}

/* ---- Observatory helpers ------------------------------------------------ */
const NW_STATUS_WORD = { ok: "Operational", warn: "Attention", degraded: "Degraded", unknown: "Unknown" };
const NW_STATUS_DOT = { ok: "fresh", warn: "stale", degraded: "degraded", unknown: "unknown" };
const EDGE_CLS = { feeds: "s-mut", confirms: "s-ok", contradicts: "s-bad", leads: "s-warn", stable: "s-mut" };

function nwEmpty(title, sub) {
  return `<div class="empty"><div class="empty-icon">◍</div><div class="empty-text">${esc(title)}</div>${sub ? `<div class="empty-sub">${esc(sub)}</div>` : ""}</div>`;
}
/* SVG freshness donut — frac = age/SLA (0..1+); colour ok<.75<warn<1<=bad */
function nwRing(frac, size = 34) {
  const r = (size - 6) / 2, c = 2 * Math.PI * r, cc = size / 2;
  const f = frac == null ? 0 : Math.max(0, Math.min(1, frac));
  const cls = frac == null ? "ok" : frac >= 1 ? "bad" : frac >= 0.75 ? "warn" : "ok";
  const dash = `${(f * c).toFixed(1)} ${c.toFixed(1)}`;
  return `<span class="ring"><svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <circle class="ring-track" cx="${cc}" cy="${cc}" r="${r}"/>
    <circle class="ring-fill ${cls}" cx="${cc}" cy="${cc}" r="${r}" stroke-dasharray="${dash}"/></svg></span>`;
}
function nwIndependenceCard(indep) {
  /* R-ORTH PR-4: independence summary card for the observatory hero area. */
  if (!indep) return "";
  const eil = indep.effective_independent_lobes;
  const measurable = indep.n_lobes_measurable;
  const total = indep.n_lobes_total;
  const pctile = indep.pctile_vs_null;
  const available = indep.available;
  // same >=2 measurable floor as the committee chip: a 1-engine PR is trivially 1.0
  const eilStr = (eil != null && measurable != null && measurable >= 2) ? Number(eil).toFixed(1) : "—";
  const coverageStr = (measurable != null && total != null)
    ? `${measurable} / ${total} engines measurable${measurable < 2 ? " — accruing" : ""}`
    : (available ? "accruing" : "spine not yet written");
  const pctileStr = (pctile != null) ? ` · ${(pctile * 100).toFixed(0)}th pctile vs null` : "";
  const sameBetHtml = (indep.same_bet_warning)
    ? `<div class="note" style="color:var(--warn);margin-top:4px">Same-bet warning: ${esc(indep.same_bet_warning.text || indep.same_bet_warning.message || "active")}</div>` : "";
  const caveat = `<span class="sub" style="font-style:italic">Descriptive only — not gauntleted (F-ORTH-1)</span>`;
  return `<div class="card" style="margin-bottom:10px;padding:10px 14px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <div>
        <div class="eyebrow">Independent witnesses (R-ORTH)</div>
        <div style="font-size:22px;font-weight:700;letter-spacing:-.02em">${esc(eilStr)}</div>
        <div class="sub">${esc(coverageStr)}${esc(pctileStr)}</div>
      </div>
      <div style="flex:1;min-width:200px;font-size:12px;line-height:1.5;color:var(--fg2)">
        Estimates how many of the ${total != null ? total : "?"} active engines fire on unrelated information.
        Based on participation-ratio of the engine co-firing correlation matrix (≥30 active-weeks floor).
        ${caveat}
      </div>
    </div>
    ${sameBetHtml}
  </div>`;
}

function nwHero(d) {
  const st = d.overall_status || "unknown";
  const sc = d.summary_counts || {};
  const chip = (label, n, cls) => `<span class="pill"><span class="led ${cls}"></span>${n != null ? n : "—"} ${label}</span>`;
  const note = d.source === "synapse_registry"
    ? "Lobe map sourced live from the signal registry (config/synapse.yml). Freshness and cortex activity fill in after the nightly pipeline writes health.json."
    : `Live health as of ${esc(d.as_of || "—")}. Every lobe below is a cross-engine artifact on the Neural Web bus.`;
  return `<div class="nw-hero">
    <div class="nw-hero-row">
      <span class="status-dot" data-status="${esc(NW_STATUS_DOT[st] || "unknown")}" style="width:14px;height:14px"></span>
      <span class="nw-hero-status-word">${esc(NW_STATUS_WORD[st] || st)}</span>
      <span class="sub" style="margin-left:2px">${sc.total != null ? sc.total : "—"} lobes across ${(d.groups || []).length} systems · ${(d.graph && d.graph.n_edges) != null ? d.graph.n_edges : "—"} bus links</span>
    </div>
    <div class="nw-hero-chips">
      ${chip("fresh", sc.fresh, "ok")}
      ${chip("stale", sc.stale, "warn")}
      ${chip("missing", sc.missing, "bad")}
      ${sc.not_locally_verifiable ? chip("R2-only", sc.not_locally_verifiable, "") : ""}
    </div>
    <div class="nw-hero-note">${note}</div>
  </div>
  ${nwIndependenceCard(d.independence)}`;
}
/* Signature system map — core → group anchors (on a ring) → lobe nodes */
const NW_STATUS_MAP = (s) => s === "fresh" ? "fresh" : s === "stale" ? "stale"
  : (s === "missing" || s === "degraded") ? "missing" : "unknown";

/* Shorten a lobe label for the map: the group is already labelled, so drop the
   redundant group-ish prefix ("Kernel Estimates" → "Estimates" inside KERNEL). */
function nwMapLabel(label) {
  return String(label || "")
    .replace(/^Site Neuralweb /i, "Site ")
    .replace(/^Neuralweb /i, "")
    .replace(/^Reflex Firings /i, "")
    .replace(/^Ops Push /i, "")
    .replace(/^Rule Experiment /i, "Experiment ")
    .replace(/^Cortex Attention /i, "Attention ")
    .replace(/^Bottom Sensors /i, "Sensors ")
    .replace(/^Options Entry /i, "Options ")
    .replace(/^Site Qledger /i, "Site QLedger ")
    .trim();
}

/* Radial dendrogram: core → group hubs → named lobe leaves, with curved
   hue-coloured synapse links. Deterministic layout (angle from index). */
function nwSystemMap(d) {
  const groups = (d.groups || []).filter(g => g.lobes && g.lobes.length);
  if (!groups.length) return "";
  const W = 1160, H = 820, cx = W / 2, cy = H / 2;
  const coreR = 30, hubR = 150, leafR = 248, rimR = 374;
  const P = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  /* d3-style radial link: control points held at the mid radius so branches fan cleanly */
  const link = (r0, a0, r1, a1) => {
    const [x0, y0] = P(r0, a0), [x1, y1] = P(r1, a1);
    const rm = (r0 + r1) / 2;
    const [b0x, b0y] = P(rm, a0), [b1x, b1y] = P(rm, a1);
    return `M${x0.toFixed(1)},${y0.toFixed(1)}C${b0x.toFixed(1)},${b0y.toFixed(1)} ${b1x.toFixed(1)},${b1y.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  };
  const trunc = (s, n) => s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;

  const L = groups.reduce((s, g) => s + g.lobes.length, 0);
  const GAP = 0.10;                                  // angular gap between groups (rad)
  const slice = (2 * Math.PI - GAP * groups.length) / L;
  let a = -Math.PI / 2 + GAP / 2;                     // first leaf starts at top

  let trunks = "", hubs = "", arms = "", glabels = "";
  groups.forEach(g => {
    const hue = `var(--grp-${g.key})`;
    const n = g.lobes.length, aStart = a, gc = aStart + n * slice / 2;
    const [hx, hy] = P(hubR, gc);
    trunks += `<path class="map-link trunk" style="stroke:${hue}" d="${link(coreR + 2, gc, hubR, gc)}"/>`;
    hubs += `<circle class="map-hub" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="6" style="fill:${hue}"/>`;
    const [gx, gy] = P(rimR, gc);
    glabels += `<text class="map-group-label" x="${gx.toFixed(1)}" y="${gy.toFixed(1)}" text-anchor="middle" dy="0.32em" style="fill:${hue}">${esc(g.label.toUpperCase())} · ${n}</text>`;
    g.lobes.forEach((l, i) => {
      const al = aStart + (i + 0.5) * slice;
      const [lx, ly] = P(leafR, al);
      const [tx, ty] = P(leafR + 10, al);
      let deg = ((al * 180 / Math.PI) % 360 + 360) % 360;
      const left = deg > 90 && deg < 270;
      const rot = left ? deg + 180 : deg;
      arms += `<g class="map-arm">`
        + `<path class="map-link" style="stroke:${hue}" d="${link(hubR, gc, leafR, al)}"/>`
        + `<circle class="map-node" data-lobe="${esc(l.id)}" data-status="${NW_STATUS_MAP(l.status)}" cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" style="fill:${hue}"/>`
        + `<text class="map-leaf-label" x="${tx.toFixed(1)}" y="${ty.toFixed(1)}" dy="0.31em" text-anchor="${left ? "end" : "start"}" transform="rotate(${rot.toFixed(1)},${tx.toFixed(1)},${ty.toFixed(1)})">${esc(trunc(nwMapLabel(l.label), 18))}</text>`
        + `</g>`;
    });
    a = aStart + n * slice + GAP;
  });

  return `<div class="systemmap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Neural Web system map — core, ${groups.length} groups, ${L} lobes">
    <defs>
      <radialGradient id="nw-core-grad" cx="0.42" cy="0.4" r="0.6">
        <stop offset="0" stop-color="#a9c0ff"/><stop offset="0.5" stop-color="#5b7cff"/><stop offset="1" stop-color="#38c8d4"/>
      </radialGradient>
    </defs>
    <g class="map-links">${trunks}</g>
    <g class="map-arms">${arms}</g>
    <g class="map-hubs">${hubs}</g>
    <g class="map-glabels">${glabels}</g>
    <circle class="map-core" cx="${cx}" cy="${cy}" r="${coreR}"/>
    <text class="map-core-label" x="${cx}" y="${cy}" text-anchor="middle" dy="0.32em">NEURAL<tspan x="${cx}" dy="1.05em">WEB</tspan></text>
  </svg></div>`;
}
/* Honest badge for the plain-English description layer.
   'stale' = the registry note changed since the prose was written; 'auto' = no
   hand-written prose yet (auto-summary from the registry). 'curated' = no badge. */
function descBadge(status) {
  if (status === "stale") return `<span class="desc-badge outdated" title="The signal-registry note for this lobe changed since its plain-English description was written — it may be out of date.">outdated</span>`;
  if (status === "auto") return `<span class="desc-badge auto" title="Auto-generated summary from the signal registry — a hand-written description hasn't been added yet.">auto</span>`;
  return "";
}

function nwLobeCard(l) {
  const age = l.age_hours, sla = l.freshness_sla_hours;
  const frac = (age != null && sla) ? age / sla : null;
  const ageTxt = age == null ? "—" : fmtAge(age);
  return `<a class="lobe-card" href="#/lobe/${encodeURIComponent(l.id)}" data-lobe="${esc(l.id)}">
    <div class="lobe-card-top">
      <span class="lobe-led" data-status="${esc(l.status)}"></span>
      <span class="lobe-name">${esc(l.label)}</span>
      ${descBadge(l.desc_status)}
      <span class="group-chip" data-group="${esc(l.group)}">${esc(l.group)}</span>
    </div>
    <div class="short-desc">${esc(l.short_desc || "No description registered.")}</div>
    <div class="lobe-metrics">
      ${nwRing(frac, 26)}
      <span>${ageTxt}${sla ? ` / ${fmtAge(sla)}` : ""}</span>
      <span class="metric-sep">·</span>
      <span>${l.n_consumers} consumer${l.n_consumers === 1 ? "" : "s"}</span>
      <span class="metric-sep">·</span>
      <span>${esc(l.tier || "—")}</span>
    </div>
  </a>`;
}

/* W-AI: pinned Master Brain card — the orchestrator (nightly pipeline) itself.
   Renders nothing when orchestrator_hero is absent (older payloads). */
function mbHeroCard(o) {
  if (!o) return "";
  const st = o.overall_status || "unknown";
  const stCls = st === "ok" ? "s-ok" : (st === "unknown" ? "s-mut" : (st === "degraded" ? "s-bad" : "s-warn"));
  const chips = [
    o.run_date ? `<span class="statpill s-mut">last run ${esc(o.run_date)}</span>` : "",
    `<span class="statpill ${o.nudges_n ? "s-warn" : "s-mut"}">${o.nudges_n != null ? o.nudges_n : 0} bot nudge${o.nudges_n === 1 ? "" : "s"}</span>`,
    `<span class="statpill s-mut">${o.directives_n != null ? o.directives_n : 0} directive${o.directives_n === 1 ? "" : "s"}</span>`,
    o.last_review_at ? `<span class="statpill s-mut">review ${esc(String(o.last_review_at).slice(0, 10))}</span>` : "",
  ].filter(Boolean).join(" ");
  return `<div class="mb-hero">
    <div class="mb-hero-top">
      <span class="mb-hero-kicker">Master Brain</span>
      <span class="mb-hero-name">Neural Web Orchestrator</span>
      <span class="statpill ${stCls}">${esc(st)}</span>
      <span class="spacer"></span>
      <button class="btn primary" id="mb-open">Open Master Brain →</button>
    </div>
    <div class="sub" style="margin-top:6px">${esc(o.summary || "No run recorded yet — the first nightly pipeline run writes the orchestrator run log.")}</div>
    <div class="mb-hero-chips">${chips}</div>
  </div>`;
}

RENDER.neural_web = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="skeleton skeleton-title"></div><div class="skeleton skeleton-card"></div>
    <div class="lobe-grid">${'<div class="skeleton skeleton-card"></div>'.repeat(8)}</div>`;
  const d = await api("/api/neural_web/lobes");
  if (!d.ok) { v.innerHTML = nwEmpty("Could not load the lobe map", d.error || "panel error"); return; }
  let html = nwHero(d) + mbHeroCard(d.orchestrator_hero) + nwSystemMap(d);
  (d.groups || []).forEach(g => {
    if (!g.lobes || !g.lobes.length) return;
    html += `<div class="section">${esc(g.label)} <span class="cnt">${g.lobes.length}</span></div>
      <div class="lobe-grid">${g.lobes.map(nwLobeCard).join("")}</div>`;
  });
  html += `<details class="nw-section" style="margin-top:6px">
      <summary class="section" style="cursor:pointer;user-select:none;list-style:none">▸ Operator HQ — full diagnostic detail</summary>
      <div id="nw-legacy"><div class="spin">loading…</div></div>
    </details>`;
  /* Build id→lobe lookup for popup */
  NW_LOBE_BY_ID = {};
  (d.groups || []).forEach(g => (g.lobes || []).forEach(l => { NW_LOBE_BY_ID[l.id] = l; }));

  v.innerHTML = html;
  const mbBtn = $("#mb-open"); if (mbBtn) mbBtn.onclick = () => go("orchestrator");
  v.querySelectorAll(".map-node[data-lobe]").forEach(el => {
    el.addEventListener("click", () => gotoLobe(el.dataset.lobe));
    wireLobeTipNode(el);
  });
  loadLegacyOps();
};
/* Section G — Evidence Clock (EC-R5) */
function nwSectionEvidenceClock(ec) {
  if (!ec) return nwMissing("evidence_clock section missing");
  if (!ec.available) return nwMissing(ec.note || "data/neuralweb/evidence_clock.json not yet written (PR1 not yet merged)");

  const sum = ec.summary || {};
  const by = sum.by_state || {};
  const ml = sum.morning_line || "";
  const asOf = ec.as_of || "";

  // State chip colours
  const STATE_CLS = {
    overdue: "s-bad", due: "s-warn", human_review: "s-warn",
    missing: "s-bad", stale: "s-warn", blocked: "s-warn",
    not_ready: "s-warn", promotion_eligible: "s-ok", accruing: "s-mut",
  };

  // Count chips — only non-zero states
  const allStates = ["overdue","due","human_review","missing","stale","blocked","not_ready","promotion_eligible","accruing"];
  let chips = allStates
    .filter(s => (by[s] || 0) > 0)
    .map(s => `<span class="statpill ${STATE_CLS[s] || 's-mut'}">${esc(String(by[s] ?? 0))} ${esc(s.replace(/_/g," "))}</span>`)
    .join(" ");

  let html = `<div class="card">
    <div class="kv"><span>As of</span><b>${esc(asOf)}</b></div>
    <div style="margin:8px 0 4px">${chips || '<span class="muted">no items</span>'}</div>
    <div class="sub" style="margin-top:6px">${esc(ml)}</div>
  </div>`;

  // Queue table
  const queue = ec.queue || [];
  if (queue.length > 0) {
    html += `<div class="section" style="margin-top:14px">Action queue <span class="cnt">${queue.length}</span></div>
      <table><thead><tr>
        <th>Clock ID</th><th>State</th><th>Due</th><th>Owner</th><th>Blocking reason</th><th>Regen cmd</th>
      </tr></thead><tbody>
      ${queue.map(r => {
        const stateCls = STATE_CLS[r.state] || "s-mut";
        const cmd = r.regenerate_cmd ? `<code style="font-size:11px">${esc(r.regenerate_cmd)}</code>` : `<span class="muted">—</span>`;
        return `<tr>
          <td><b>${esc(r.clock_id || "")}</b>${r.acknowledged ? ' <span class="statpill s-mut">ack</span>' : ''}</td>
          <td><span class="statpill ${stateCls}">${esc(r.state || "")}</span></td>
          <td class="sub">${esc(r.due_at || "—")}</td>
          <td class="sub">${esc(r.owner_program || "—")}</td>
          <td class="sub" style="max-width:220px">${esc(r.blocking_reason || "")}</td>
          <td>${cmd}</td>
        </tr>`;
      }).join("")}
      </tbody></table>`;
  }

  if (ec.n_accruing > 0) {
    html += `<div class="sub muted" style="margin-top:8px">${ec.n_accruing} accruing / promotion-eligible items not shown.</div>`;
  }

  return html;
}

async function loadLegacyOps() {
  const box = $("#nw-legacy"); if (!box) return;
  const d = await api("/api/neural_web");
  if (!d || !d.ok) { box.innerHTML = nwEmpty("Diagnostic panel unavailable", (d && d.error) || ""); return; }
  box.innerHTML = `
    ${nwCollapse("engine_health", "A — System health", nwSectionEngineHealth(d.engine_health), false)}
    ${nwCollapse("reflex_log", "B — Automatic reactions", nwSectionReflexLog(d.reflex_log), false)}
    ${nwCollapse("bus_graph", "C — How signals agree &amp; disagree", nwSectionBusGraph(d.bus_graph), false)}
    ${nwCollapse("governance", "D — Permissions &amp; change log", nwSectionGovernance(d.governance), false)}
    ${nwCollapse("factor_intelligence", "E — Factor intelligence (what a stock's move is made of)", nwSectionFactorIntelligence(d.factor_intelligence), false)}
    ${nwCollapse("evidence_clock", "G — Evidence Clock (come-backs &amp; overdue actions)", nwSectionEvidenceClock(d.evidence_clock), false)}`;
}

/* ---- Lobe detail "page" (#/lobe/<id>) ----------------------------------- */
function nwCrumbs(current) {
  return `<div class="crumbs"><a href="#" data-back>← Neural Web</a><span class="crumbs-sep">/</span><span class="crumbs-current">${esc(current)}</span></div>`;
}
async function renderLobeDetail(id) {
  CURRENT = "neural_web"; setActiveNav("neural_web");
  hideLobeTip();  // clear any map-node hover popup left over from the click that navigated here
  if (RT_TIMER)   { clearInterval(RT_TIMER);   RT_TIMER   = null; }
  if (LOOP_TIMER) { clearInterval(LOOP_TIMER); LOOP_TIMER = null; }
  if (LOOP_TICK)  { clearInterval(LOOP_TICK);  LOOP_TICK  = null; }
  setTopbarTitle("Neural Web");
  const v = $("#view");
  v.innerHTML = nwCrumbs(id) + `<div class="skeleton skeleton-title"></div>
    <div class="metric-tiles-row">${'<div class="skeleton skeleton-card" style="width:120px;height:70px"></div>'.repeat(4)}</div>
    <div class="skeleton skeleton-card" style="height:120px"></div>`;
  const d = await api("/api/neural_web/lobe?id=" + encodeURIComponent(id));
  const wireBack = () => { const b = v.querySelector("[data-back]"); if (b) b.onclick = (e) => { e.preventDefault(); backToObservatory(); }; };
  if (!d || !d.ok) {
    v.innerHTML = nwCrumbs(id) + nwEmpty("Unknown lobe", `No lobe with id “${id}”.`);
    wireBack(); return;
  }
  setTopbarTitle(d.label);
  const met = d.metrics || {}, tr = d.transmission || {};
  const frac = (met.age_hours != null && met.freshness_sla_hours) ? met.age_hours / met.freshness_sla_hours : null;

  const tiles = [
    `<div class="metric-tile"><div class="eyebrow">Freshness</div>
       <div class="tile-value" style="display:flex;align-items:center;gap:8px">${nwRing(frac, 30)}<span>${met.age_hours == null ? "—" : fmtAge(met.age_hours)}</span></div>
       <div class="tile-sub">${met.freshness_sla_hours ? "SLA " + fmtAge(met.freshness_sla_hours) + (met.sla_met === false ? " · breached" : met.sla_met ? " · on time" : "") : "no SLA"}</div></div>`,
    `<div class="metric-tile"><div class="eyebrow">Rows</div><div class="tile-value">${met.row_count == null ? "—" : fmtNum(met.row_count)}</div><div class="tile-sub">records</div></div>`,
    `<div class="metric-tile"><div class="eyebrow">Size</div><div class="tile-value">${met.byte_size == null ? "—" : fmtBytes(met.byte_size)}</div><div class="tile-sub">on disk</div></div>`,
    `<div class="metric-tile"><div class="eyebrow">Consumers</div><div class="tile-value">${(tr.consumers || []).length + (tr.external_consumers || []).length}</div><div class="tile-sub">downstream readers</div></div>`,
    `<div class="metric-tile"><div class="eyebrow">As of</div><div class="tile-value" style="font-size:14px">${esc(met.as_of || met.produced_at || "—")}</div><div class="tile-sub">${esc(d.cadence || "")}</div></div>`,
  ].join("");

  const consumers = (tr.consumers || []).map(c => `<div class="flow-node" data-kind="${esc(c.kind || "module")}">${esc(c.name)}</div>`).join("") || `<div class="sub">no registered consumers</div>`;
  const external = (tr.external_consumers || []).length
    ? `<div class="external-consumers"><div class="flow-col-label">External consumers</div>${tr.external_consumers.map(e => `<span class="external-tag">${esc(e)}</span>`).join("")}</div>` : "";
  const edges = (tr.edges || []);
  const edgeList = edges.length
    ? `<div class="edge-list"><div class="flow-col-label">Confluence edges · ${edges.length}</div>
       <table><thead><tr><th>From</th><th>Type</th><th>To</th><th>Note</th></tr></thead><tbody>
       ${edges.slice(0, 40).map(e => `<tr><td class="mono sub" style="max-width:180px;word-break:break-all">${esc(e.src)}</td>
         <td>${nwPill(e.edge_type, EDGE_CLS[e.edge_type] || "s-mut")}${e.n != null ? ` <span class="sub">×${e.n}</span>` : ""}</td>
         <td class="mono sub" style="max-width:180px;word-break:break-all">${esc(e.dst)}</td>
         <td class="sub">${esc(e.note || "")}</td></tr>`).join("")}</tbody></table></div>` : "";

  const recent = (d.recent_actions || []);
  const timeline = recent.length
    ? `<div class="timeline">${recent.map(a => `<div class="timeline-item">
        <div class="timeline-ts">${esc(a.ts || "")}</div>
        <div class="timeline-header"><span class="timeline-kind">${esc(a.kind || "event")}</span></div>
        <div class="timeline-summary">${esc(a.summary || "")}</div>
        ${a.source ? `<div class="timeline-source">${esc(a.source)}</div>` : ""}</div>`).join("")}</div>`
    : nwEmpty("No recent activity", "No firings, governance events, or brief entries are currently attributable to this lobe.");

  v.innerHTML = `
    ${nwCrumbs(d.label)}
    ${d.missing ? `<div class="missing-banner"><span>⚠</span><div>This artifact isn't present on this clone — freshness metrics fill in after the nightly pipeline writes it. Its purpose and data flow (below) come from the signal registry and are always available.</div></div>` : ""}
    <div style="margin-bottom:18px">
      <div class="nw-hero-row" style="margin-bottom:10px">
        <span class="status-dot" data-status="${esc(d.status)}" style="width:14px;height:14px"></span>
        <span style="font-size:24px;font-weight:700;letter-spacing:-.02em">${esc(d.label)}</span>
        <span class="group-chip" data-group="${esc(d.group)}">${esc(d.group_label || d.group)}</span>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <span class="badge">${esc(d.tier || "—")}</span>
        <span class="badge">${esc(d.cadence || "—")}</span>
        <span class="badge">${esc(d.horizon_role || "—")}</span>
        <span class="badge">${esc(d.storage || "—")}</span>
      </div>
    </div>
    <div class="metric-tiles-row">${tiles}</div>
    <div class="card"><h3 style="display:flex;align-items:center;gap:8px">What it does ${descBadge(d.desc_status)}</h3>
      ${d.desc_status === "stale" ? `<div class="note" style="color:var(--warn);margin-bottom:8px">⚠ The signal-registry note for this lobe changed since this plain-English summary was written — it may be out of date. (Refresh it and re-stamp with the description audit tool.)</div>` : ""}
      ${d.desc_status === "auto" ? `<div class="note muted" style="margin-bottom:8px">Auto-generated from the signal registry — a hand-written summary hasn't been added yet.</div>` : ""}
      <div style="line-height:1.55">${esc(d.description || "No description registered for this lobe.")}</div>
      ${d.description_technical && d.description_technical !== d.description ? `<details style="margin-top:12px"><summary class="note muted" style="cursor:pointer;user-select:none">Technical note (from the signal registry)</summary><div class="note mono muted" style="margin-top:6px;line-height:1.5">${esc(d.description_technical)}</div></details>` : ""}
      ${d.independence_note ? `<details style="margin-top:12px"><summary class="note muted" style="cursor:pointer;user-select:none">Independence note (R-ORTH covariance spine)</summary><div class="note muted" style="margin-top:6px;line-height:1.5">${esc(d.independence_note)}${d.co_fire_cluster ? ` Co-fire cluster engines: ${esc(d.co_fire_cluster.join(", "))}.` : ""}</div></details>` : ""}
      <div class="note muted" style="margin-top:10px">Producer <code>${esc(d.producer || "?")}</code> · artifact <code>${esc(d.path || "?")}</code> · source ${esc(d.purpose_source || "config/synapse.yml")}</div>
    </div>
    <div class="section">Data transmission</div>
    <div class="transmission">
      <div class="flow-layout">
        <div class="flow-col">
          <div class="flow-col-label">Producer</div>
          <div class="flow-node" data-kind="module">${esc(d.producer || "—")}</div>
        </div>
        <div class="flow-col" style="align-items:center;justify-content:center">
          <div class="flow-hub">${esc(d.label)}</div>
        </div>
        <div class="flow-col">
          <div class="flow-col-label">Consumers · ${(tr.consumers || []).length}</div>
          ${consumers}
        </div>
      </div>
      ${external}
      ${edgeList}
    </div>
    <div class="section">Recent activity <span class="cnt">${recent.length}</span></div>
    ${timeline}`;
  wireBack();
}

/* ---- MASTER BRAIN (orchestrator) — W-AI ---------------------------------- */
const ORCH_STATUS_CLS = (st) => st === "ok" ? "s-ok" : st === "unknown" ? "s-mut" : (st === "degraded" || st === "bad") ? "s-bad" : "s-warn";
const NUDGE_SEV_CLS = (sev) => {
  const s = String(sev || "").toLowerCase();
  if (["block", "high", "critical", "error"].includes(s)) return "s-bad";
  if (["warn", "warning", "medium"].includes(s)) return "s-warn";
  return "s-mut";
};
const orchTrunc = (s, n) => { s = String(s == null ? "" : s); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
/* generic tolerant renderers for loosely-shaped bot payloads */
function kvRows(obj) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return "";
  return Object.entries(obj).map(([k, val]) => {
    const vv = (val != null && typeof val === "object") ? `<code style="font-size:11px">${esc(orchTrunc(JSON.stringify(val), 120))}</code>` : esc(val == null ? "—" : String(val));
    return `<div class="kv"><span>${esc(k)}</span><b>${vv}</b></div>`;
  }).join("");
}
function countChips(obj, cls) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return "";
  return Object.entries(obj).map(([k, n]) => `<span class="statpill ${cls || "s-mut"}">${esc(k)} · ${esc(String(n))}</span>`).join(" ");
}

let ORCH_CHAT = [];   // [{role, content, degraded?}] — page-lifetime chat history

function orchChatMsgsHtml() {
  if (!ORCH_CHAT.length) return `<div class="sub muted">Ask the pipeline what it did last night, what's stale, or what the bot nudged.</div>`;
  return ORCH_CHAT.map(m => `<div class="chat-msg ${m.role === "user" ? "user" : "bot"}">
      <div class="chat-msg-role">${m.role === "user" ? "you" : "orchestrator"}${m.degraded ? ' <span class="statpill s-warn">degraded</span>' : ""}</div>
      <div class="chat-msg-body">${esc(m.content)}</div>
    </div>`).join("");
}

RENDER.orchestrator = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="spin">loading…</div>`;
  const d = await api("/api/orchestrator");
  if (!d || !d.ok) { v.innerHTML = nwEmpty("Master Brain unavailable", (d && d.error) || "panel error"); return; }
  const hero = d.status_hero || {}, s = d.settings || {}, dia = d.dialogue || {}, cx = d.cortex || {};
  const st = hero.overall_status || "unknown";
  const ack = dia.ack || {}; const codesSeen = ack.nudge_codes_seen || []; const idsSeen = ack.directive_ids_seen || [];
  const prob = cx.probation || {};

  /* Map cortex status codes to plain-word labels for display. Raw code kept in title=. */
  const CORTEX_STATUS_WORD = { ok: "healthy", degraded: "ran without AI review", warn: "needs a look" };
  const cortexWord = (code) => CORTEX_STATUS_WORD[String(code || "").toLowerCase()] || String(code || "unknown");

  /* Render what_changed_kinds as a readable phrase. */
  function changedKindsPhrase(kinds) {
    if (!kinds || typeof kinds !== "object" || !Object.keys(kinds).length) return null;
    const parts = Object.entries(kinds).map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`);
    return parts.join(", ");
  }

  /* Kind-to-description map for nudge/dialogue kinds. */
  const NUDGE_KIND_DESC = {
    contract_drift:  "data shape drifted from what the bot expects",
    coverage_gap:    "the bot wants context we don't produce",
    staleness:       "a feed it relies on has gone stale",
    lobe_request:    "the bot asked for a new feed",
  };

  const heroHtml = `<div class="mb-hero">
    <div class="mb-hero-top">
      <span class="mb-hero-kicker">Master Brain</span>
      <span class="mb-hero-name">Neural Web Orchestrator</span>
      <span class="statpill ${ORCH_STATUS_CLS(st)}" title="${esc(st)}">${esc(cortexWord(st))}</span>
      <span class="spacer"></span>
      <button class="btn" id="orchWake" title="workflow_dispatch daily.yml — runs the full nightly pipeline now">&#9201; Wake orchestrator</button>
    </div>
    <div class="sub" style="margin-top:6px">${esc(hero.summary || "No run recorded yet — the first nightly pipeline run writes the orchestrator run log.")}</div>
    <div id="orchDailyStrip"></div>
    <div class="mb-hero-chips">
      <span class="statpill s-mut" title="lobes whose data contract is out of date">${hero.lobes_stale != null ? hero.lobes_stale : "—"}/${hero.lobes_total != null ? hero.lobes_total : "—"} stale feeds</span>
      <span class="statpill s-mut">${hero.what_changed_n != null ? hero.what_changed_n : "—"} changes</span>
      <span class="statpill ${ORCH_STATUS_CLS(cx.status)}" title="cortex status: ${esc(cx.status || "unknown")}">cortex ${esc(cortexWord(cx.status || "unknown"))}</span>
      <span class="statpill ${hero.nudges_n ? "s-warn" : "s-mut"}" title="as ingested from the bot's last feedback artifact — may lag the Mastermind AI page">${hero.nudges_n || 0} bot nudge${hero.nudges_n === 1 ? "" : "s"}</span>
      <span class="statpill s-mut">${hero.directives_n || 0} directive${hero.directives_n === 1 ? "" : "s"}</span>
      <span class="statpill s-mut">feedback ${esc(hero.feedback_state || "absent")}</span>
    </div>
    <div class="note muted" style="margin-top:8px">${esc(hero.next_run_note || "")} · ${hero.n_entries || 0} run${hero.n_entries === 1 ? "" : "s"} logged${hero.last_review_at ? ` · last review ${esc(String(hero.last_review_at).slice(0, 16).replace("T", " "))}` : ""}${prob.tier ? ` · cortex probation ${esc(prob.tier)}${prob.granted ? "" : " (not granted)"}` : ""}</div>
  </div>`;

  const numInput = (key, val, lo, hi) => `<input type="number" data-orchset="${key}" data-prev="${val}" min="${lo}" max="${hi}" value="${val}" style="width:86px">`;
  const boolSwitch = (key, val) => `<label class="switch"><input type="checkbox" data-orchsetb="${key}" ${val ? "checked" : ""}><span class="slider"></span></label>`;
  const settingsHtml = `<div class="section">Settings <span class="cnt">config.yml &middot; orchestrator</span></div>
    <div class="row">${boolSwitch("ingest_bot_feedback", s.ingest_bot_feedback)}
      <div><div class="lab">Ingest bot feedback</div><div class="note">Read the Mastermind bot's nudges and directives into the nightly build so Master Brain can acknowledge them. <code class="muted">orchestrator.ingest_bot_feedback</code></div></div></div>
    <div class="row">${boolSwitch("brief_attention_nudges", s.brief_attention_nudges)}
      <div><div class="lab">Flag nudges in the daily brief</div><div class="note">Pending bot requests show up as items for you to review in the morning brief. <code class="muted">orchestrator.brief_attention_nudges</code></div></div></div>
    <div class="row"><div class="lab" style="min-width:220px">Review cadence</div>${numInput("review_every_n_runs", s.review_every_n_runs, 2, 50)}
      <div class="note">How often Master Brain writes its report card (every N runs). Range 2&#x2013;50.</div></div>
    <div class="row"><div class="lab" style="min-width:220px">Site rows</div>${numInput("site_rows", s.site_rows, 10, 365)}
      <div class="note">How many run-log rows to keep in the published site artifact (10&#x2013;365).</div></div>`;

  const entries = d.entries || [];
  const runlogHtml = `<div class="section">Run log <span class="cnt">${entries.length}</span></div>
    <div class="sub muted" style="margin-bottom:8px">One row per nightly pipeline run &mdash; what Master Brain saw and what changed.</div>`
    + (entries.length
    ? `<table><thead><tr><th>Run</th><th>Workflow</th><th>Status</th><th title="lobes whose data contract is out of date">Stale feeds</th><th>Changes</th><th>Cortex</th><th>Nudges</th><th>Summary</th></tr></thead><tbody>
      ${entries.map(e => {
        const rawKinds = e.what_changed_kinds && Object.keys(e.what_changed_kinds).length ? Object.entries(e.what_changed_kinds).map(([k, n]) => `${k}:${n}`).join(", ") : "";
        const kindsPhrase = changedKindsPhrase(e.what_changed_kinds);
        return `<tr>
          <td class="mono"><b>${esc(e.run_date || "—")}</b></td>
          <td class="sub">${esc(e.workflow || "—")}</td>
          <td><span class="statpill ${ORCH_STATUS_CLS(e.overall_status)}">${esc(e.overall_status || "—")}</span></td>
          <td class="r mono" title="lobes whose data contract is out of date">${e.lobes_stale != null ? e.lobes_stale : "—"}/${e.lobes_total != null ? e.lobes_total : "—"}</td>
          <td class="r mono" title="${esc(rawKinds)}">${kindsPhrase ? `<span title="${esc(rawKinds)}">${esc(orchTrunc(kindsPhrase, 40))}</span>` : (e.what_changed_n != null ? e.what_changed_n : "—")}</td>
          <td><span class="statpill ${ORCH_STATUS_CLS(e.cortex_status)}" title="${esc(e.cortex_status || "")}">${esc(cortexWord(e.cortex_status || "unknown"))}</span></td>
          <td class="r mono" title="${esc((e.nudge_codes || []).join(", "))}">${e.nudges_n != null ? e.nudges_n : 0}</td>
          <td class="sub" title="${esc(e.summary || "")}">${esc(orchTrunc(e.summary, 90))}</td>
        </tr>`;
      }).join("")}</tbody></table>`
    : `<div class="sub muted">No run-log entries yet. The nightly pipeline (daily.yml, 02:00 UTC) writes the first one.</div>`);

  const reviews = d.reviews || [];
  const reviewsHtml = `<div class="section">Reviews <span class="cnt">every ${esc(String(s.review_every_n_runs || 5))} runs</span></div>
    <div class="sub muted" style="margin-bottom:8px">Every ${esc(String(s.review_every_n_runs || 5))} runs, Master Brain writes itself a report card.</div>`
    + (reviews.length
    ? reviews.map(r => {
      const c = r.completed || {};
      return `<div class="card" style="margin-bottom:10px">
        <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
          <b>${esc(r.from_run || "?")} &#8594; ${esc(r.to_run || "?")}</b>
          <span class="statpill s-mut">${r.window_runs || "?"} runs</span>
          <span class="sub">${esc(String(r.produced_at || "").slice(0, 16).replace("T", " "))}</span>
        </div>
        <div class="sub" style="margin:6px 0 4px">${c.what_changed_total != null ? c.what_changed_total : "—"} changes &middot; ${c.directives_seen != null ? c.directives_seen : "—"} directives seen ${countChips(c.what_changed_kinds)}</div>
        ${(r.assessment || []).map(a => `<div class="note" style="margin-top:3px">&bull; ${esc(a)}</div>`).join("")}
      </div>`;
    }).join("")
    : `<div class="sub muted">No reviews yet &mdash; the first roll-up is written after ${esc(String(s.review_every_n_runs || 5))} logged runs.</div>`);

  const nudges = dia.nudges || [];
  const directives = dia.operator_directives || [];
  const dialogueHtml = `<div class="section">Bot dialogue <span class="cnt">${esc(dia.feedback_state || "absent")}</span></div>
    <div class="sub muted" style="margin-bottom:8px">What the trading bot asked for &mdash; and whether it was heard.</div>
    ${nudges.length ? `<table><thead><tr><th>Code</th><th>Kind</th><th>Severity</th><th>Detail</th><th class="r">Builds seen</th><th>Ack</th></tr></thead><tbody>
      ${nudges.map(n => {
        const kindCode = String(n.kind || "");
        const kindDesc = NUDGE_KIND_DESC[kindCode] || "";
        return `<tr>
          <td class="mono"><b>${esc(n.code || "—")}</b><div class="note muted" style="font-size:11px">${esc(kindCode)}</div></td>
          <td class="sub">${kindDesc ? `${esc(kindDesc)}` : esc(kindCode || "—")}</td>
          <td><span class="statpill ${NUDGE_SEV_CLS(n.severity)}">${esc(n.severity || "—")}</span></td>
          <td class="sub" style="max-width:320px">${esc(n.detail || "")}</td>
          <td class="r mono">${n.builds_seen != null ? n.builds_seen : "—"}</td>
          <td>${codesSeen.includes(n.code) ? '<span class="statpill s-ok">ack</span>' : '<span class="statpill s-mut">pending</span>'}</td>
        </tr>`;
      }).join("")}</tbody></table>`
      : `<div class="sub muted">No nudges from the bot in the current feedback artifact.</div>`}
    ${directives.length ? `<div class="section" style="margin-top:14px">Operator directives <span class="cnt">${directives.length}</span></div>
      ${directives.map(dd => `<div class="card" style="margin-bottom:8px">
        <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
          <code>${esc(dd.id || "—")}</code><span class="sub">${esc(dd.created || "")}</span>
          ${idsSeen.includes(dd.id) ? '<span class="statpill s-ok">ack</span>' : '<span class="statpill s-mut">pending</span>'}
        </div>
        <div class="sub" style="margin-top:4px">${esc(dd.text || "")}</div>
      </div>`).join("")}` : ""}
    <div class="note muted" style="margin-top:8px">New directives are composed on the <a href="#" id="orchToMai">Mastermind AI</a> page — by hand in its composer, auto-drafted from open findings with its "⚡ Act on all findings" button, or queued automatically each cycle when its "Auto-act on findings" setting is on. The orchestrator only observes and acknowledges them.</div>`;

  const chatHtml = `<div class="section">Chat</div>
    <div class="sub muted" style="margin-bottom:8px">Ask Master Brain about its recent runs. Plain answers from the run log.</div>
    <div class="card chat-box">
      <div class="chat-msgs" id="orchChatMsgs">${orchChatMsgsHtml()}</div>
      <div class="chat-input">
        <textarea id="orchChatIn" rows="2" maxlength="2000" placeholder="e.g. What did you complete last night, and what's still stale?"></textarea>
        <button class="btn primary" id="orchChatSend">Send</button>
      </div>
      <div class="note muted" style="margin-top:6px">Read-only pipeline persona &mdash; never trading advice. Without an LLM key it degrades to a deterministic run-log digest.</div>
    </div>`;

  v.innerHTML = heroHtml + settingsHtml + runlogHtml + reviewsHtml + dialogueHtml + chatHtml;

  /* wiring */
  const meta = (SUMMARY && SUMMARY.meta) || {};
  const writable = !meta.deployed || (meta.integrations && meta.integrations.github_write);
  v.querySelectorAll("[data-orchset],[data-orchsetb]").forEach(el => { if (!writable) el.disabled = true; });
  v.querySelectorAll("[data-orchsetb]").forEach(cb => cb.onchange = async () => {
    const r = await post("/api/orchestrator/settings", { key: cb.dataset.orchsetb, value: cb.checked });
    if (r.ok) toast(`${cb.dataset.orchsetb} → ${r.new}`);
    else { cb.checked = !cb.checked; toast(r.error || "failed", true); }
  });
  v.querySelectorAll("[data-orchset]").forEach(inp => inp.onchange = async () => {
    const r = await post("/api/orchestrator/settings", { key: inp.dataset.orchset, value: Number(inp.value) });
    if (r.ok) { inp.dataset.prev = String(r.new); toast(`${inp.dataset.orchset} → ${r.new}`); }
    else { inp.value = inp.dataset.prev; toast(r.error || "failed", true); }
  });
  const wakeBtn = $("#orchWake");
  if (wakeBtn) wakeBtn.onclick = async () => {
    if (!confirm("Wake the orchestrator now? This dispatches daily.yml (full pipeline run) on GitHub Actions.")) return;
    wakeBtn.disabled = true;
    const r = await post("/api/orchestrator/wake", {});
    wakeBtn.disabled = false;
    if (r.ok) toast("Orchestrator woken — daily.yml dispatched");
    else toast((r.error || "wake failed") + (r.hint ? ` — ${r.hint}` : ""), true);
  };
  const toMai = $("#orchToMai"); if (toMai) toMai.onclick = (e) => { e.preventDefault(); go("mastermind_ai"); };
  const sendBtn = $("#orchChatSend"), inp = $("#orchChatIn");
  const sendChat = async () => {
    const msg = (inp.value || "").trim();
    if (!msg) return;
    inp.value = "";
    ORCH_CHAT.push({ role: "user", content: msg });
    const history = ORCH_CHAT.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
    const box = $("#orchChatMsgs");
    box.innerHTML = orchChatMsgsHtml() + `<div class="chat-msg bot"><div class="chat-msg-role">orchestrator</div><div class="chat-msg-body muted">thinking…</div></div>`;
    box.scrollTop = box.scrollHeight;
    sendBtn.disabled = true;
    const r = await post("/api/orchestrator/chat", { message: msg, history });
    sendBtn.disabled = false;
    if (r && r.reply) ORCH_CHAT.push({ role: "assistant", content: r.reply, degraded: !!r.degraded });
    else ORCH_CHAT.push({ role: "assistant", content: (r && r.error) || "chat failed", degraded: true });
    box.innerHTML = orchChatMsgsHtml();
    box.scrollTop = box.scrollHeight;
  };
  if (sendBtn) sendBtn.onclick = sendChat;
  if (inp) inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } });

  /* Hero: live daily-pipeline strip — one-shot fetch, fill #orchDailyStrip. */
  (async () => {
    const dailyStrip = $("#orchDailyStrip");
    if (!dailyStrip) return;
    let lr;
    try { lr = await api("/api/live_runs"); } catch (e) { return; }
    if (!lr || CURRENT !== "orchestrator") return;
    const line = dailyPipelineStripLine(lr.nightly || null);
    dailyStrip.innerHTML = line;
    if (line) {
      /* Start ticking the elapsed counter inside the strip. */
      if (LOOP_TICK) { clearInterval(LOOP_TICK); LOOP_TICK = null; }
      LOOP_TICK = setInterval(() => tickLoopElapsed(), 1000);
    }
  })();
};

/* ---- MASTERMIND AI (bot proxy) — W-AI ------------------------------------ */
const MAI_SETTING_FIELDS = [   /* [key, kind, label, note, min, max] — bounds mirror the bot's */
  ["loop_enabled", "bool", "Self-improvement loop", "Main switch for the bot's improvement loop."],
  ["llm_review", "bool", "LLM review", "Use the LLM for the every-N-loops review pass."],
  ["review_every_n_loops", "int", "Review every N loops", "Roll-up review cadence (2–50).", 2, 50],
  ["nudges_max", "int", "Max nudges", "Cap on coded nudges published to the macro repo (1–10).", 1, 10],
  ["attribution_min_n", "int", "Attribution min n", "Minimum sample size before attribution claims (6–100).", 6, 100],
  ["directives_max_open", "int", "Max open directives", "Cap on concurrently open operator directives (1–10).", 1, 10],
  ["directive_expiry_days", "int", "Directive expiry days", "Days a published directive waits for an acknowledgement before expiring (3–60).", 3, 60],
  ["auto_act_on_findings", "bool", "Auto-act on findings", "Queue auto-drafted directives from open findings on every loop cycle — no button press needed."],
];
const MAI_DIRECTIVE_CLS = { queued: "s-warn", published: "s-mut", acknowledged: "s-ok", done: "s-ok", expired: "s-bad" };
/* plain-English meanings for the bot's coded findings (nw_reflection.v1 nudge codes);
   unknown codes fall back to the nudge's own detail string */
const MAI_FINDING_MEANINGS = {
  candidate_context_empty: "The candidate-context table is present but carries zero rows — the decision rules have nothing to read.",
  fdr_cleared_absent: "No candidate is FDR-cleared, so every decision rule reading the web is inert.",
  bottom_state_vocabulary_drift: "The web never says BOTTOMING/CONFIRMED, so above-WATCH candidacy boosts can never trigger.",
  graph_conflicts_absent: "No candidate carries conflict data — the entry-shrink and clean-in-conflicted rules can never fire.",
  graph_conflicts_sparse: "Almost no candidates carry conflict data — conflict-aware sizing stays dark.",
  contradictions_empty: "The market lobe reports no contradiction records — the clean-in-conflicted tell is inert.",
  liquidity_plumbing_absent: "The market lobe's liquidity block is empty.",
  coverage_below_half: "Fewer than half of the names the bot decided on have a context row in the web.",
  context_stale_streak: "The published context artifact has been stale for 3+ consecutive builds.",
  context_absent_streak: "The published context artifact has been missing for 3+ consecutive builds.",
  gap_notes_elevated: "The latest build carries several producer gap notes — upstream collectors skipped data.",
};

RENDER.mastermind_ai = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="spin">loading…</div>`;
  const d = await api("/api/mastermind_ai");
  if (!d || d.error) {
    /* Prominent, honest unreachable banner per the operator-facing spec.
       Resolve the bot base URL from /api/live_runs so we show the actual
       configured address instead of a hardcoded fallback. */
    const detailSnip = (d && d.detail) ? esc(orchTrunc(String(d.detail), 160)) : "connection refused or timeout";
    /* Async: fetch live_runs to get the real bot base; render the banner
       immediately with a placeholder, then patch it once we know the base. */
    let botBase = "http://127.0.0.1:8000";  /* default shown immediately */
    v.innerHTML = `<div class="banner show" style="position:static;margin-bottom:16px;padding:12px 16px;border-radius:6px;display:block">
      <div style="font-size:15px;font-weight:700;margin-bottom:6px">Bot service unreachable (<span id="maiBotBase">${esc(botBase)}</span>)</div>
      <div>The Mastermind bot runs on the operator&#39;s Mac, not this server. Run cycle and settings will fail until <code>MASTERMIND_BOT_BASE</code> points at a reachable bot API.</div>
      <div class="sub muted" style="margin-top:6px">Detail: ${detailSnip}</div>
    </div>
    <div id="loopStripWrap"></div>`;
    /* Patch the base URL from live_runs when available. */
    (async () => {
      let lr;
      try { lr = await api("/api/live_runs"); } catch (e) { /* proxy error — keep placeholder */ return; }
      if (!lr || CURRENT !== "mastermind_ai") return;
      const base = (lr.mastermind_bot && lr.mastermind_bot.base) ? lr.mastermind_bot.base : null;
      if (base) {
        const el = $("#maiBotBase");
        if (el) el.textContent = base;
      }
    })();
    startLoopPoll("mastermind_ai", "loopStripWrap", false);
    return;
  }
  const st = d.settings || {}, flagsObj = d.flags || {};
  const lastLoops = d.last_loops || [];
  const lastLoop = lastLoops[lastLoops.length - 1] || {};   /* status().last_loops is oldest-first */
  const refl = d.reflection || {};
  const dia = d.dialogue;   /* status "dialogue" block — absent on older bots, degrade to "—" */

  /* honest tri-state: never claim "loop on" when the bot didn't report the setting */
  const loopPill = st.loop_enabled === true ? ["loop on", "s-ok"]
    : st.loop_enabled === false ? ["loop off", "s-warn"] : ["loop ?", "s-mut"];
  const nudgesN = refl.nudges != null ? (Array.isArray(refl.nudges) ? refl.nudges.length : refl.nudges) : null;
  const heroHtml = `<div class="mb-hero">
    <div class="mb-hero-top">
      <span class="mb-hero-kicker">Mastermind AI</span>
      <span class="mb-hero-name">Bot self-improvement loop</span>
      <span class="statpill ${loopPill[1]}">${loopPill[0]}</span>
      <span class="spacer"></span>
      <button class="btn primary" id="maiRun" title="POST /api/mastermind_ai/run — trigger one improvement cycle">▶ Run cycle now</button>
    </div>
    <div class="sub" style="margin-top:6px">${esc(lastLoop.summary || (d.last_review && d.last_review.summary) || "No loop summary reported yet.")}</div>
    <div class="mb-hero-chips">
      <span class="statpill s-mut">loop #${d.loop_n != null ? d.loop_n : "—"}</span>
      ${nudgesN != null ? `<span class="statpill ${nudgesN ? "s-warn" : "s-mut"}" title="coded fix-requests published to the NW orchestrator">${nudgesN} nudge${nudgesN === 1 ? "" : "s"}</span>` : ""}
      ${refl.contract_drift_n != null ? `<span class="statpill ${refl.contract_drift_n ? "s-bad" : "s-mut"}" title="NW context fields the bot's decision rules need but cannot use">${refl.contract_drift_n} contract drift${refl.contract_drift_n === 1 ? "" : "s"}</span>` : ""}
      ${countChips(typeof flagsObj === "object" && !Array.isArray(flagsObj) ? flagsObj : null)}
    </div>
  </div>
  <div class="note muted" style="margin:0 0 20px;line-height:1.5">Every night the bot audits the Neural Web data it trades against. A contract-drift finding means a data field its decision rules consume is missing or dead in the published artifact. A nudge is the fix request it publishes back to the macro pipeline. Nudges flow out automatically. Formal directives are queued from open findings automatically each cycle when "Auto-act on findings" is on — or by hand via "Act on findings" / the composer below.</div>`;

  const settingRow = ([key, kind, label, note, lo, hi]) => {
    const val = st[key];
    if (kind === "bool")
      return `<div class="row"><label class="switch"><input type="checkbox" data-maiset="${key}" data-kind="bool" ${val ? "checked" : ""}><span class="slider"></span></label>
        <div><div class="lab">${esc(label)}</div><div class="note">${esc(note)} <code class="muted">${esc(key)}</code>${val == null ? ' <span class="tag inert">not reported</span>' : ""}</div></div></div>`;
    return `<div class="row"><div class="lab" style="min-width:220px">${esc(label)}</div>
      <input type="number" data-maiset="${key}" data-kind="int" data-prev="${val != null ? val : ""}" value="${val != null ? val : ""}"${lo != null ? ` min="${lo}"` : ""}${hi != null ? ` max="${hi}"` : ""} style="width:86px">
      <div class="note">${esc(note)} <code class="muted">${esc(key)}</code></div></div>`;
  };
  const settingsHtml = `<div class="section">Settings <span class="cnt">bot-side</span></div>` + MAI_SETTING_FIELDS.map(settingRow).join("");

  v.innerHTML = `<div id="loopStripWrap"></div>` + heroHtml + settingsHtml
    + `<div class="section">Loop log &amp; reviews</div><div id="maiLoopLog"><div class="spin">loading…</div></div>
       <div class="section">Improvements</div><div id="maiImprovements"><div class="spin">loading…</div></div>
       <div class="section">Reflection &amp; dialogue</div><div id="maiReflection"><div class="spin">loading…</div></div>`;

  /* wiring: settings + run */
  v.querySelectorAll("[data-maiset]").forEach(el => el.onchange = async () => {
    const key = el.dataset.maiset;
    const value = el.dataset.kind === "bool" ? el.checked : Number(el.value);
    const r = await post("/api/mastermind_ai/settings", { settings: { [key]: value } });
    if (r && !r.error && r.ok !== false) { el.dataset.prev = String(value); toast(`${key} → ${value}`); }
    else {
      if (el.dataset.kind === "bool") el.checked = !el.checked; else el.value = el.dataset.prev;
      toast((r && (r.error || r.detail)) || "settings update failed", true);
    }
  });
  const runBtn = $("#maiRun");
  if (runBtn) {
    let _runElapsed = null;
    runBtn.onclick = async () => {
      if (!confirm("Run one Mastermind improvement cycle now?")) return;
      runBtn.disabled = true;
      const runStart = Date.now();
      /* Show elapsed counter up to the 30s proxy timeout. */
      _runElapsed = setInterval(() => {
        const sec = Math.floor((Date.now() - runStart) / 1000);
        runBtn.textContent = `running… ${sec}s`;
      }, 1000);
      let r;
      try { r = await post("/api/mastermind_ai/run", {}); } catch (e) { r = { error: String(e) }; }
      clearInterval(_runElapsed); _runElapsed = null;
      runBtn.disabled = false;
      runBtn.textContent = "▶ Run cycle now";
      if (r && !r.error && r.ok !== false) {
        /* Re-render only after the run resolved; surface the returned loop-row summary. */
        toast(r.summary ? `Cycle done — ${orchTrunc(r.summary, 140)}` : "Cycle started");
        if (CURRENT === "mastermind_ai") RENDER.mastermind_ai();
      } else {
        /* Show the server's error text inline under the button. */
        const errMsg = (r && (r.error || r.detail || r.skipped)) || "run failed";
        let errEl = v.querySelector("#maiRunErr");
        if (!errEl) {
          errEl = document.createElement("div");
          errEl.id = "maiRunErr";
          errEl.className = "note";
          errEl.style.color = "var(--bad)";
          errEl.style.marginTop = "6px";
          runBtn.parentElement.appendChild(errEl);
        }
        errEl.textContent = errMsg;
        toast(errMsg, true);
      }
    };
  }

  /* async sub-panels */
  (async () => {
    const box = $("#maiLoopLog"); if (!box) return;
    const d2 = await api("/api/mastermind_ai/loop_log?n=30");
    if (!d2 || d2.error) { box.innerHTML = `<div class="sub muted">loop log unavailable${d2 && d2.detail ? " — " + esc(orchTrunc(d2.detail, 120)) : ""}</div>`; return; }
    /* bot returns {loop_log: [...oldest-first tail...], reviews: [...]} — render newest-first */
    const rows = (d2.loop_log || d2.loops || d2.rows || d2.entries || (Array.isArray(d2) ? d2 : [])).slice().reverse();
    const reviews = d2.reviews || [];
    let html = rows.length
      ? `<table><thead><tr><th>Ts</th><th>As of</th><th class="r">Loop</th><th>Trigger</th><th>Summary</th></tr></thead><tbody>
        ${rows.map(r => `<tr>
          <td class="mono sub">${esc(String(r.ts || "").slice(0, 16).replace("T", " "))}</td>
          <td class="mono sub">${esc(r.asof || r.as_of || "—")}</td>
          <td class="r mono">${r.loop_n != null ? r.loop_n : "—"}</td>
          <td class="sub">${esc(r.trigger || "—")}</td>
          <td class="sub" title="${esc(r.summary || "")}">${esc(orchTrunc(r.summary, 110))}</td>
        </tr>`).join("")}</tbody></table>`
      : `<div class="sub muted">No loop entries reported.</div>`;
    if (reviews.length) {
      html += `<div class="section" style="margin-top:14px">Loop reviews <span class="cnt">${reviews.length}</span></div>`
        + reviews.map(r => `<div class="card" style="margin-bottom:8px">
            <div class="sub"><b>${esc(r.from_loop != null ? `loop ${r.from_loop} → ${r.to_loop}` : String(r.ts || r.produced_at || "review").slice(0, 16))}</b></div>
            ${(r.assessment || []).map(a => `<div class="note" style="margin-top:3px">• ${esc(a)}</div>`).join("") || `<div class="note muted">${esc(orchTrunc(r.summary || JSON.stringify(r), 200))}</div>`}
          </div>`).join("");
    }
    box.innerHTML = html;
  })();

  (async () => {
    const box = $("#maiImprovements"); if (!box) return;
    const d3 = await api("/api/mastermind_ai/improvements");
    if (!d3 || d3.error) { box.innerHTML = `<div class="sub muted">improvements unavailable${d3 && d3.detail ? " — " + esc(orchTrunc(d3.detail, 120)) : ""}</div>`; return; }
    let html = "";
    /* pinned rules by seat — tolerate {seat: [rules]} or a flat list with .seat
       (bot improvements() ships the flat list under `pins`, rows carry .seat/.rule/.status) */
    let bySeat = d3.pinned_by_seat || d3.pinned_rules_by_seat;
    if (!bySeat) {
      const flat = [d3.pins, d3.pinned_rules].find(Array.isArray);
      if (flat) {
        bySeat = {};
        flat.forEach(r => { const seat = (r && r.seat) || "unassigned"; (bySeat[seat] = bySeat[seat] || []).push(r); });
      }
    }
    if (bySeat && typeof bySeat === "object") {
      html += Object.entries(bySeat).map(([seat, rules]) => `<div class="card" style="margin-bottom:8px">
        <div class="sub"><b>${esc(seat)}</b> <span class="cnt">${(rules || []).length}</span></div>
        ${(rules || []).map(r => {
          const status = (r && (r.status || (r.pinned === false ? "unpinned" : "active"))) || "active";
          return `<div class="note" style="margin-top:4px"><span class="statpill ${status === "active" ? "s-ok" : "s-mut"}">${esc(status)}</span> ${esc(orchTrunc((r && (r.rule || r.text || r.lesson)) || JSON.stringify(r), 180))}</div>`;
        }).join("")}
      </div>`).join("");
    }
    if (d3.lessons_by_taxonomy) html += `<div class="card" style="margin-bottom:8px"><div class="sub"><b>Lessons by taxonomy</b></div><div style="margin-top:6px">${countChips(d3.lessons_by_taxonomy)}</div></div>`;
    if (d3.self_tune) html += `<div class="card" style="margin-bottom:8px"><div class="sub"><b>Self-tune</b></div>${kvRows(d3.self_tune)}</div>`;
    if (Array.isArray(d3.agenda_top) && d3.agenda_top.length) html += `<div class="card" style="margin-bottom:8px"><div class="sub"><b>Agenda</b></div>${d3.agenda_top.map(a => `<div class="note" style="margin-top:3px">• ${esc(orchTrunc(typeof a === "string" ? a : (a.title || a.summary || JSON.stringify(a)), 160))}</div>`).join("")}</div>`;
    box.innerHTML = html || `<div class="sub muted">No improvements reported.</div>`;
  })();

  (async () => {
    const box = $("#maiReflection"); if (!box) return;
    /* dialogue health — the status "dialogue" block (absent on older bots → no banner, "—" acks) */
    const codesSeen = dia && dia.last_ack ? (dia.last_ack.nudge_codes_seen || []) : null;
    const banner = dia && dia.counterparty === "absent"
      ? `<div class="warn-banner"><span>⚠</span><div>One-way for now — the macro orchestrator has never acknowledged this dialogue (its ingest lane is not live yet). Nudges and directives still publish, but nothing comes back until the macro side ships.${dia.expired_n > 0 ? ` ${dia.expired_n} directive(s) expired unacknowledged.` : ""}</div></div>`
      : "";
    /* directive queue lives on the STATUS payload (rows {id,ts,text,status,source?}) —
       the raw nw_reflection.v1 artifact carries no directives key */
    const dirs = Array.isArray(d.directives) ? d.directives : [];
    const openN = dirs.filter(dd => dd.status === "queued" || dd.status === "published").length;
    const srcChip = (dd) => {
      const src = String(dd.source || "operator");
      return src.startsWith("nudge:")
        ? `<span class="statpill s-mut mono" title="auto-drafted from the ${esc(src.slice(6))} finding">auto: ${esc(src.slice(6))}</span>`
        : `<span class="statpill s-mut">operator</span>`;
    };
    const dirsHtml = `<div class="card" style="margin-top:14px">
      <div class="section" style="margin:0 0 8px">Operator directives <span class="cnt">${st.directives_max_open != null ? `${openN}/${st.directives_max_open} slots used` : `${openN} open`}</span></div>
      ${dirs.length ? dirs.map(dd => `<div class="card" style="margin-bottom:8px">
          <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
            <code>${esc(dd.id || "—")}</code><span class="sub">${esc(String(dd.ts || dd.created || "").slice(0, 16).replace("T", " "))}</span>
            <span class="statpill ${MAI_DIRECTIVE_CLS[dd.status] || "s-mut"}">${esc(dd.status || "—")}</span>
            ${srcChip(dd)}
          </div>
          <div class="sub" style="margin-top:4px">${esc(dd.text || "")}</div>
        </div>`).join("") : `<div class="sub muted">No directives queued.</div>`}
      ${maiDirectiveComposer()}
    </div>`;
    const d4 = await api("/api/mastermind_ai/reflection");
    if (!d4 || d4.error) { box.innerHTML = banner + `<div class="sub muted">reflection unavailable${d4 && d4.detail ? " — " + esc(orchTrunc(d4.detail, 120)) : ""}</div>` + dirsHtml; wireDirectiveComposer(box); return; }
    const nudges = d4.nudges || [];
    const resolved = Array.isArray(d4.nudges_resolved_recent) ? d4.nudges_resolved_recent : [];
    const ackCell = (code) => codesSeen === null ? `<span class="sub muted">—</span>`
      : codesSeen.includes(code) ? `<span class="statpill s-ok">seen</span>` : `<span class="statpill s-mut">pending</span>`;
    let html = banner;
    html += `<div class="section" style="margin:0 0 8px">Data-contract findings
      <span class="cnt">${nudges.length} open${resolved.length ? ` · ${resolved.length} resolved` : ""}</span>
      ${nudges.length && st.auto_act_on_findings === true ? `<span class="statpill s-ok" title="auto_act_on_findings is on — every loop cycle queues directives from these automatically">auto-act on</span>` : ""}
      ${nudges.length ? `<button class="btn" id="maiActAll" style="margin-left:auto">⚡ Act on all findings</button>` : ""}
    </div>`;
    html += nudges.length
      ? `<table><thead><tr><th>Finding</th><th>What it means</th><th>Severity</th><th>Since</th><th class="r">Builds</th><th>Ack</th><th></th></tr></thead><tbody>
        ${nudges.map(n => {
          const meaning = Object.prototype.hasOwnProperty.call(MAI_FINDING_MEANINGS, n.code) ? MAI_FINDING_MEANINGS[n.code] : "";
          return `<tr>
          <td class="mono"><b>${esc(n.code || "—")}</b></td>
          <td class="sub" style="max-width:360px">${esc(meaning || n.detail || "—")}${meaning && n.detail ? `<div class="note muted mono" style="margin-top:2px" title="${esc(n.detail)}">${esc(orchTrunc(n.detail, 110))}</div>` : ""}</td>
          <td><span class="statpill ${NUDGE_SEV_CLS(n.severity)}">${esc(n.severity || "—")}</span></td>
          <td class="sub mono">${esc(String(n.first_seen || "").slice(0, 10)) || "—"}</td>
          <td class="r mono">${n.builds_seen != null ? n.builds_seen : "—"}</td>
          <td>${ackCell(n.code)}</td>
          <td><button class="btn mai-draft-btn" data-code="${esc(n.code || "")}">Draft directive</button></td>
        </tr>`;
        }).join("")}</tbody></table>`
      : `<div class="sub muted">No open findings — the bot's last audit found every contract field it needs alive in the web.</div>`;
    const statChips = [];
    const driftN = (d4.contract_drift || []).length;   /* nw_reflection.v1: contract_drift is a LIST */
    statChips.push(`<span class="statpill ${driftN ? "s-bad" : "s-mut"}" title="from the latest reflection artifact">${driftN} contract drift${driftN === 1 ? "" : "s"}</span>`);
    if (d4.nudges_dropped_n) statChips.push(`<span class="statpill s-warn" title="finding candidates cut by the max-nudges cap">${d4.nudges_dropped_n} dropped by cap</span>`);
    if (d4.coverage && typeof d4.coverage === "object") statChips.push(countChips(d4.coverage));
    else if (d4.coverage != null) statChips.push(`<span class="statpill s-mut">coverage · ${esc(String(d4.coverage))}</span>`);
    if (d4.context_quality != null) statChips.push(`<span class="statpill s-mut">context quality · ${esc(typeof d4.context_quality === "object" ? orchTrunc(JSON.stringify(d4.context_quality), 60) : String(d4.context_quality))}</span>`);
    if (d4.attribution != null) statChips.push(`<span class="statpill s-mut">attribution · ${esc(typeof d4.attribution === "object" ? orchTrunc(JSON.stringify(d4.attribution), 60) : String(d4.attribution))}</span>`);
    if (statChips.length) html += `<div style="margin-top:10px">${statChips.join(" ")}</div>`;
    html += dirsHtml;
    box.innerHTML = html;
    wireDirectiveComposer(box);
    const actAll = $("#maiActAll", box);
    if (actAll) actAll.onclick = () => maiActOnFindings(null, actAll);
    box.querySelectorAll(".mai-draft-btn").forEach(b => b.onclick = () => maiActOnFindings([b.dataset.code], b));
  })();

  /* Live-loop strip poll (20s while on mastermind_ai tab). */
  startLoopPoll("mastermind_ai", "loopStripWrap", false);
};

/* POST /api/mastermind_ai/act_on_nudges — [] / null codes means "all open findings".
   The bot auto-drafts one directive per finding (source "nudge:<code>"). */
async function maiActOnFindings(codes, btn) {
  if (!confirm("Queue auto-drafted directives for open findings? They publish to the orchestrator with the next snapshot (12:25 / 22:25 UTC).")) return;
  if (btn) btn.disabled = true;
  const r = await post("/api/mastermind_ai/act_on_nudges", codes && codes.length ? { codes } : {});
  if (btn) btn.disabled = false;
  if (r && r.ok) {
    const q = (r.queued || []).length;
    const skipped = (r.skipped || []).map(s => `${s.code}: ${s.reason}`).join("; ");
    toast(`${q} directive(s) queued${skipped ? ` — skipped ${skipped}` : ""}`, q === 0);
    if (CURRENT === "mastermind_ai") RENDER.mastermind_ai();
  } else {
    const msg = r && (r.error || r.detail);
    /* an older bot has no /act_on_nudges route — the proxy passes FastAPI's 404 {"detail":"Not Found"} through */
    toast(msg === "Not Found" ? "bot does not support act-on-findings yet — update the bot" : msg || "act on findings failed", true);
  }
}

function maiDirectiveComposer() {
  /* rendered INSIDE the Operator directives card — a divider, not a nested card */
  return `<div style="margin-top:12px;border-top:1px solid var(--grid);padding-top:12px">
    <div class="sub"><b>New directive</b> — a plain-English instruction the bot's reflection loop reads on its next cycle.</div>
    <div class="chat-input" style="margin-top:8px">
      <textarea id="maiDirText" rows="2" maxlength="280" placeholder="e.g. Stop citing the ETF lobe until its feed heals."></textarea>
      <button class="btn primary" id="maiDirSend">Send directive</button>
    </div>
    <div class="note muted" style="margin-top:4px"><span id="maiDirCount">0</span>/280 · Directives are read by the macro orchestrator on its nightly build — plain English, no secrets, no dollar amounts.</div>
  </div>`;
}
function wireDirectiveComposer(scope) {
  const ta = $("#maiDirText", scope), btn = $("#maiDirSend", scope), cnt = $("#maiDirCount", scope);
  if (!ta || !btn) return;
  ta.addEventListener("input", () => { if (cnt) cnt.textContent = String(ta.value.length); });
  btn.onclick = async () => {
    const text = (ta.value || "").trim();
    if (!text) { toast("directive text required", true); return; }
    if (text.length > 280) { toast("directive too long (max 280 chars)", true); return; }
    btn.disabled = true;
    const r = await post("/api/mastermind_ai/directive", { text });
    btn.disabled = false;
    if (r && !r.error && r.ok !== false) { ta.value = ""; if (cnt) cnt.textContent = "0"; toast("Directive queued"); setTimeout(() => { if (CURRENT === "mastermind_ai") RENDER.mastermind_ai(); }, 1200); }
    else toast((r && (r.error || r.detail)) || "directive failed", true);
  };
}

/* ---- ALERTS (operator capture) ------------------------------------------ */
const SEV_CLS = { critical: "s-bad", major: "s-warn", minor: "" };
RENDER.alerts = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="sub" style="margin-bottom:12px">Recent alerts from the live site feed. Log your action against any alert — Acted, Dismissed, Overrode, or Snoozed — to build the operator capture ledger (L4 instrumentation). All writes go through /api/actions behind auth.</div>
    <div class="sub muted" style="margin-bottom:8px">Loading…</div>`;
  const d = await api("/api/alerts");
  if (!d.ok) {
    v.innerHTML = card("Alerts", `<div class="sub" style="color:var(--bad)">${esc(d.note || d.error || "error")}</div>`);
    return;
  }
  const alerts = d.alerts || [];
  const genLine = d.generated_utc ? `<div class="sub muted" style="margin-bottom:8px">Feed generated: ${esc(d.generated_utc)} UTC${d.note ? " — " + esc(d.note) : ""}</div>` : (d.note ? `<div class="sub muted" style="margin-bottom:8px">${esc(d.note)}</div>` : "");
  if (!alerts.length) {
    v.innerHTML = `${genLine}<div class="section">Alerts <span class="cnt">0</span></div><div class="sub muted">No alerts in the feed.</div>`;
    return;
  }
  v.innerHTML = `${genLine}<div class="section">Alerts <span class="cnt">${alerts.length}</span></div>
    <table><thead><tr><th>Alert</th><th>Severity</th><th>Priority</th><th>Emitted</th><th>Your action</th></tr></thead><tbody>
    ${alerts.map(a => `<tr>
      <td><b>${esc(a.title || a.surface || a.alert_id)}</b><div class="note mono muted">${esc(a.surface || "")}</div></td>
      <td><span class="statpill ${SEV_CLS[a.severity] || ""}">${esc(a.severity || "—")}</span></td>
      <td class="r mono">${a.priority != null ? a.priority : "—"}</td>
      <td class="sub mono">${esc((a.emit_ts || "").slice(0, 10))}</td>
      <td style="white-space:nowrap">
        <button class="btn alert-act-btn" data-alert-id="${esc(a.alert_id || "")}" data-emit-ts="${esc(a.emit_ts || "")}" data-action="acted">Acted</button>
        <button class="btn alert-act-btn" data-alert-id="${esc(a.alert_id || "")}" data-emit-ts="${esc(a.emit_ts || "")}" data-action="dismissed">Dismiss</button>
        <button class="btn alert-act-btn" data-alert-id="${esc(a.alert_id || "")}" data-emit-ts="${esc(a.emit_ts || "")}" data-action="overrode">Override</button>
        <button class="btn alert-act-btn" data-alert-id="${esc(a.alert_id || "")}" data-emit-ts="${esc(a.emit_ts || "")}" data-action="snoozed">Snooze</button>
      </td></tr>`).join("")}
    </tbody></table>`;
  // Wire action buttons — POST {surface: alert_id, action, direction_note, alert_emit_ts}
  v.querySelectorAll(".alert-act-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const alertId = btn.dataset.alertId;
      const emitTs = btn.dataset.emitTs;
      const action = btn.dataset.action;
      const note = window.prompt(`Direction note (optional, ≤280 chars) for "${action}" on ${alertId}:`);
      if (note === null) return; // user cancelled
      const r = await post("/api/actions", {
        surface: alertId,
        action,
        direction_note: note,
        alert_emit_ts: emitTs || undefined,
      });
      if (r.ok) toast(`Logged: ${action} — ${alertId}`);
      else toast(r.error || "action log failed", true);
    });
  });
};

/* ---- LONG-HOLD LOBE ----------------------------------------------------- */
RENDER.long_hold = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="sub muted" style="margin-bottom:8px">Loading…</div>`;
  const d = await api("/api/long_hold");
  if (!d.ok) {
    v.innerHTML = card("Long-Hold Lobe", `<div class="sub" style="color:var(--bad)">${esc(d.reason || "not available")}</div>`);
    return;
  }

  const ageStr = d.age_hours != null ? ` · ${fmtAge(d.age_hours)} old` : "";
  const genStr = d.generated_at ? `generated ${esc(d.generated_at.slice(0, 16).replace("T", " "))} UTC${ageStr}` : "no winner autopsy artifact yet";
  const wa = d.winner_autopsy || {};
  const tf = d.thesis_funnel || {};
  const lb = d.labels || {};

  // ---- Winner Autopsy section ----
  let waHtml = "";
  if (!wa.available) {
    waHtml = `<div class="sub muted">${esc(wa.reason || "winner autopsy data not yet available")}</div>`;
  } else {
    const census = wa.census || {};
    const cases = wa.cases || {};
    const watch = wa.watch || {};

    // Census cards
    const olc = census.outcome_label_counts || {};
    const olcRows = Object.entries(olc).map(([k, n]) =>
      `<div class="kv"><span>${esc(k.replace(/_/g, " "))}</span><b>${fmtNum(n)}</b></div>`
    ).join("") || "<span class='muted'>—</span>";
    const byEra = (census.by_era || []).map(e =>
      `<tr><td>${esc(e.era || "—")}</td><td class="r">${fmtNum(e.n_episodes)}</td>` +
      `<td class="r">${e.durable_winner_rate != null ? (100 * e.durable_winner_rate).toFixed(1) + "%" : "—"}</td>` +
      `<td class="r">${e.blow_off_rate != null ? (100 * e.blow_off_rate).toFixed(1) + "%" : "—"}</td></tr>`
    ).join("");
    const censusNotes = (census.notes || []).map(n => `<div class="note">${esc(n)}</div>`).join("");

    const censusCard = card("Census", `
      <div class="kv"><span>Episodes</span><b>${fmtNum(census.n_episodes)}</b></div>
      <div class="kv"><span>Universe tickers</span><b>${fmtNum(census.universe_n_tickers)}</b></div>
      <div class="kv"><span>Date range</span><b>${esc((census.date_range || []).join(" → "))}</b></div>
      ${olcRows}
      ${byEra ? `<table style="margin-top:8px"><thead><tr><th>Era</th><th class="r">Episodes</th><th class="r">Durable winner %</th><th class="r">Blow-off %</th></tr></thead><tbody>${byEra}</tbody></table>` : ""}
      ${censusNotes}`);

    // Cases table
    const caseRows = (cases.items || []).map(it =>
      `<tr>
        <td><b>${esc(it.ticker || "—")}</b></td>
        <td>${esc(it.episode_year != null ? String(it.episode_year) : "—")}</td>
        <td>${esc(it.mechanism || "—")}</td>
        <td><span class="statpill ${it.reconcile === "matched" ? "s-ok" : it.reconcile ? "s-warn" : ""}">${esc(it.reconcile || "—")}</span></td>
        <td class="sub" style="max-width:320px">${esc(it.thesis_one_liner || "—")}</td>
        <td>${it.file ? `<a href="${esc(it.file)}" target="_blank" rel="noopener">case</a>` : "—"}</td>
      </tr>`
    ).join("") || `<tr><td colspan="6" class="muted sub">no cases yet</td></tr>`;
    const casesBlock = `
      <div class="section">Cases <span class="cnt">${fmtNum(cases.n_cases)}</span></div>
      <table><thead><tr><th>Ticker</th><th>Year</th><th>Mechanism</th><th>Reconcile</th><th>Thesis</th><th>File</th></tr></thead>
      <tbody>${caseRows}</tbody></table>`;

    // Breakaway Watch
    let watchHtml = "";
    if (!watch.available) {
      watchHtml = `<div class="sub muted">Watch list not yet populated (prices needed — runs on Mac host nightly). State counts: ${JSON.stringify(watch.state_counts || {})}</div>`;
    } else {
      const sc = watch.state_counts || {};
      const chips = Object.entries(sc).map(([k, n]) =>
        `<span class="statpill ${n > 0 ? "s-ok" : ""}" style="margin-right:4px">${esc(k.replace(/_/g, " "))} ${fmtNum(n)}</span>`
      ).join("");
      const topRows = (watch.top || []).map(row =>
        `<tr>
          <td><b>${esc(row.ticker || "—")}</b></td>
          <td>${esc(row.sector || "—")}</td>
          <td>${esc(row.benchmark || "—")}</td>
          <td><span class="statpill">${esc(row.state || "—")}</span></td>
          <td class="r mono">${row.excess_21d_pp != null ? row.excess_21d_pp.toFixed(1) + "pp" : "—"}</td>
          <td>${row.new_high_63d ? "yes" : "no"}</td>
          <td class="r mono">${row.dollar_vol_z21 != null ? row.dollar_vol_z21.toFixed(2) : "—"}</td>
          <td class="sub" style="max-width:260px">${esc((row.hazards || []).join(", "))}</td>
        </tr>`
      ).join("") || `<tr><td colspan="8" class="muted sub">no watch entries</td></tr>`;
      watchHtml = `
        <div style="margin:6px 0">${chips || "<span class='muted sub'>no state counts</span>"}</div>
        <table><thead><tr><th>Ticker</th><th>Sector</th><th>Benchmark</th><th>State</th><th class="r">Excess 21d</th><th>New high 63d</th><th class="r">Vol-z 21</th><th>Hazards</th></tr></thead>
        <tbody>${topRows}</tbody></table>
        <div class="note muted" style="margin-top:4px">as of ${esc(watch.as_of || "—")} · sorted by excess_21d_pp desc · display-only — not a trading signal</div>`;
    }

    // Clocks
    const clockRows = (wa.clocks || []).map(c =>
      `<div class="kv"><span class="mono">${esc(c.id || "—")}</span><b>${esc(c.come_back_on || "—")} <span class="statpill">${esc(c.status || "")}</span></b>
        ${c.note ? `<div class="note">${esc(c.note)}</div>` : ""}</div>`
    ).join("") || "<span class='muted sub'>no clocks</span>";

    waHtml = `
      <div class="grid">${censusCard}</div>
      ${casesBlock}
      <div class="section">Breakaway Watch</div>
      <div class="card">${watchHtml}</div>
      <div class="section">Clocks</div>
      <div class="card">${clockRows}</div>`;
  }

  // ---- Thesis Funnel section ----
  let tfHtml = "";
  if (!tf.available) {
    tfHtml = `<div class="sub muted">${esc(tf.reason || "thesis funnel manifest not available")}</div>`;
  } else {
    const sc = tf.state_counts || {};
    const scRows = Object.entries(sc).map(([k, n]) =>
      `<div class="kv"><span>${esc(k.replace(/_/g, " "))}</span><b>${fmtNum(n)}</b></div>`
    ).join("") || "<span class='muted'>—</span>";
    tfHtml = `
      <div class="kv"><span>Population (tickers)</span><b>${fmtNum(tf.population)}</b></div>
      <div class="kv"><span>As of</span><b>${esc(tf.as_of || "—")}</b></div>
      ${scRows}
      ${tf.notes ? `<div class="note" style="margin-top:6px">${esc(tf.notes)}</div>` : ""}`;
  }

  // ---- Labels section ----
  let lbHtml = "";
  if (!lb.available) {
    lbHtml = `<div class="sub muted">${esc(lb.reason || "labels manifest not available")}</div>`;
  } else {
    const dist = lb.distribution || {};
    const lbRows = Object.entries(dist).sort((a, b) => b[1] - a[1]).map(([k, n]) =>
      `<tr><td>${esc(k.replace(/_/g, " "))}</td><td class="r mono">${fmtNum(n)}</td></tr>`
    ).join("") || `<tr><td colspan="2" class="muted sub">no distribution data</td></tr>`;
    lbHtml = `
      <div class="kv"><span>Generated</span><b>${esc((lb.generated_at || "—").slice(0, 16).replace("T", " "))}</b></div>
      <table><thead><tr><th>Label</th><th class="r">Count</th></tr></thead><tbody>${lbRows}</tbody></table>`;
  }

  v.innerHTML = `
    <div class="sub muted" style="margin-bottom:8px">${esc(genStr)}</div>
    <div class="section">Winner Autopsy</div>
    <div class="card">${waHtml}</div>
    <div class="section">Thesis Funnel</div>
    <div class="card">${tfHtml}</div>
    <div class="section">Label Distribution</div>
    <div class="card">${lbHtml}</div>`;
};

/* ---- Context Lobe ------------------------------------------------------- */
RENDER.context_lobe = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="sub muted" style="margin-bottom:8px">Loading…</div>`;
  const d = await api("/api/context_lobe");

  // always ok=true; error note signals artifact is absent
  const freshStr = d.freshness
    ? `produced ${esc(String(d.freshness).slice(0, 16).replace("T", " "))} UTC · ${fmtAge(d.age_hours)} old`
    : "artifact not yet written (runs on Mac host nightly)";

  // ---- display-only / annotate-only banner ----
  const banner = `<div class="banner show" style="margin-bottom:12px;padding:8px 12px;border-radius:6px;background:var(--surface2,#1e2030);border:1px solid var(--border,#334)">
    <span style="font-weight:600">Display-only · annotate_only</span>
    <span class="sub" style="margin-left:8px">Neural Web context layer — no signals, no escalations, no scores may originate here</span>
  </div>`;

  // ---- error / absent ----
  if (d.error) {
    v.innerHTML = banner + card("Context Lobe", `<div class="sub muted">${esc(d.error)}</div>`);
    return;
  }

  // ---- gap notes ----
  const gapHtml = (d.gap_notes && d.gap_notes.length)
    ? `<div class="section">Gap Notes</div><div class="card">${d.gap_notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}</div>`
    : "";

  // ---- lobes summary ----
  const lobes = d.lobes || {};
  const lobeNames = Object.keys(lobes);
  let lobesHtml = "";
  if (lobeNames.length === 0) {
    lobesHtml = `<div class="sub muted">no lobe data</div>`;
  } else {
    lobesHtml = lobeNames.map(name => {
      const lobe = lobes[name] || {};
      if (!lobe.available) {
        return `<div class="kv"><span class="mono">${esc(name)}</span><b class="muted">—</b></div>`;
      }
      let detail = "";
      if (name === "market") {
        detail = `${esc(lobe.verdict || "—")} · score ${lobe.score != null ? lobe.score : "—"} · radar ${esc(lobe.radar_state || "—")}`;
      } else if (name === "macro_weather") {
        detail = `US ${esc(lobe.us_quad || "—")} · CN ${esc(lobe.china_quad || "—")} · HK ${esc(lobe.hk_quad || "—")}`;
      } else if (name === "bottom_sensors") {
        const counts = lobe.counts || {};
        const countStr = Object.entries(counts).map(([k, n]) => `${esc(k)} ${n}`).join(" · ") || "—";
        detail = `n=${lobe.n_rows != null ? lobe.n_rows : "—"} · ${countStr}`;
      } else if (name === "options_entry") {
        const gate = lobe.gate || {};
        detail = Object.entries(gate).map(([k, v2]) => `${esc(k)}=${esc(String(v2))}`).join(" · ") || "—";
      } else if (name === "cortex") {
        detail = `probation=${lobe.probation ? "yes" : "no"} · active_signals=${lobe.active_signals != null ? lobe.active_signals : "—"}`;
      } else if (name === "contradictions") {
        detail = `${lobe.n_records != null ? lobe.n_records : "—"} records`;
      } else if (name === "cycle_pattern") {
        detail = `gate=${esc(lobe.gate_status || "—")} · entities=${lobe.n_entities != null ? lobe.n_entities : "—"} · hazards=${lobe.n_with_hazard != null ? lobe.n_with_hazard : "—"}`;
      } else if (lobe.standing_law) {
        detail = esc(String(lobe.standing_law).slice(0, 80));
      } else {
        detail = lobe.as_of ? `as of ${esc(lobe.as_of)}` : "—";
      }
      const asof = lobe.as_of ? ` <span class="sub muted">· ${esc(lobe.as_of)}</span>` : "";
      return `<div class="kv"><span class="mono">${esc(name.replace(/_/g, " "))}</span><b>${detail}${asof}</b></div>`;
    }).join("");
  }

  // ---- lobe_manifest ----
  let manifestHtml = "";
  const manifest = d.lobe_manifest || [];
  if (manifest.length === 0) {
    manifestHtml = `<div class="sub muted">no manifest entries</div>`;
  } else {
    const mRows = manifest.map(e =>
      `<tr>
        <td class="mono">${esc(e.artifact_id || "—")}</td>
        <td class="sub" style="max-width:240px">${esc(e.path || "—")}</td>
        <td>${esc(e.tier || "—")}</td>
        <td>${esc(e.horizon_role || "—")}</td>
        <td><span class="statpill ${e.stale ? "s-warn" : "s-ok"}">${e.stale ? "stale" : "fresh"}</span></td>
        <td>${esc(e.asof || "—")}</td>
      </tr>`
    ).join("");
    manifestHtml = `<table><thead><tr><th>Artifact</th><th>Path</th><th>Tier</th><th>Horizon role</th><th>Freshness</th><th>As-of</th></tr></thead>
      <tbody>${mRows}</tbody></table>`;
  }

  // ---- candidate_context table ----
  const candidates = d.candidates || [];
  let candidatesHtml = "";
  if (candidates.length === 0) {
    candidatesHtml = `<div class="sub muted">no candidate context rows</div>`;
  } else {
    const cRows = candidates.map(row => {
      const nullDash = (v2) => v2 != null ? esc(String(v2)) : "—";
      const fmtF = (v2, dp) => v2 != null ? Number(v2).toFixed(dp != null ? dp : 2) : "—";
      const boolStr = (v2) => v2 == null ? "—" : (v2 ? "yes" : "no");
      return `<tr>
        <td><b>${esc(row.ticker || "—")}</b></td>
        <td><span class="statpill">${nullDash(row.bottom_state)}</span></td>
        <td class="r mono">${row.trigger_age_ticks != null ? fmtF(row.trigger_age_ticks, 0) : "—"}</td>
        <td>${boolStr(row.coiled)}</td>
        <td>${boolStr(row.star)}</td>
        <td>${nullDash(row.gex_confirm_verdict)}</td>
        <td class="r mono">${row.iv30 != null ? (row.iv30 * 100).toFixed(1) + "%" : "—"}</td>
        <td>${row.interest_coverage != null ? fmtF(row.interest_coverage, 1) : "—"}</td>
        <td>${row.ev_ebit != null ? fmtF(row.ev_ebit, 1) : "—"}</td>
        <td>${row.pe != null ? fmtF(row.pe, 1) : "—"}</td>
        <td>${nullDash(row.underwater_state)}</td>
        <td class="r">${row.earnings_days_to != null ? fmtF(row.earnings_days_to, 0) + "d" : "—"}</td>
        <td class="r">${row.n_graph_conflicts != null ? row.n_graph_conflicts : "—"}</td>
        <td class="sub">${nullDash(row.bottom_as_of)}</td>
      </tr>`;
    }).join("");
    candidatesHtml = `
      <div class="note muted" style="margin-bottom:6px">Showing ${d.n_candidates_shown} of ${d.n_candidates_total} tickers · sorted by sub-block richness · display-only context</div>
      <table><thead><tr>
        <th>Ticker</th><th>Bottom state</th><th class="r">Trig age</th>
        <th>Coiled</th><th>Star</th>
        <th>GEX verdict</th><th class="r">IV30</th>
        <th>Int cov</th><th>EV/EBIT</th><th>P/E</th>
        <th>Underwater</th><th class="r">Earn days</th>
        <th>Conflicts</th><th>As-of</th>
      </tr></thead>
      <tbody>${cRows}</tbody></table>`;
  }

  v.innerHTML = `
    ${banner}
    <div class="sub muted" style="margin-bottom:8px">${esc(freshStr)}</div>
    ${gapHtml}
    <div class="section">Lobes</div>
    <div class="card">${lobesHtml}</div>
    <div class="section">Lobe Manifest <span class="cnt">${manifest.length}</span></div>
    <div class="card">${manifestHtml}</div>
    <div class="section">Candidate Context <span class="cnt">${d.n_candidates_total || 0}</span></div>
    <div class="card">${candidatesHtml}</div>`;
};

/* ---- Causal Lab --------------------------------------------------------- */
RENDER.causal_lab = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="sub muted" style="margin-bottom:8px">Loading…</div>`;
  const d = await api("/api/causal_lab");

  const freshStr = d.freshness
    ? `produced ${esc(String(d.freshness).slice(0, 16).replace("T", " "))} UTC · ${fmtAge(d.age_hours)} old`
    : "artifact not yet written (runs on Mac host nightly)";

  // display-only / annotate-only banner
  const banner = `<div class="banner show" style="margin-bottom:12px;padding:8px 12px;border-radius:6px;background:var(--surface2,#1e2030);border:1px solid var(--border,#334)">
    <span style="font-weight:600">Display-only · annotate_only · not_a_signal</span>
    <span class="sub" style="margin-left:8px">CHF epistemic infrastructure — causal-candidate screened, not gauntleted. No authority surface.</span>
  </div>`;

  if (d.error) {
    v.innerHTML = banner + card("Causal Lab", `<div class="sub muted">${esc(d.error)}</div>`);
    return;
  }

  // heartbeat
  const hb = d.heartbeat || {};
  const hbHtml = `<div class="kv"><span>Program</span><b>${esc(hb.program || "—")}</b></div>
    <div class="kv"><span>Wave</span><b>${esc(hb.wave || "—")}</b></div>
    <div class="kv"><span>Status</span><b>${esc(hb.status || "—")}</b></div>`;

  // funnel counts
  const fn = d.funnel || {};
  const evByVerdict = fn.edges_by_verdict || {};
  const verdictChips = Object.entries(evByVerdict)
    .map(([k, n]) => `<span class="statpill">${esc(k)} <b>${n}</b></span>`)
    .join(" ") || "<span class='muted sub'>none</span>";
  const mechByStatus = fn.mechanisms_by_status || {};
  const mechChips = Object.entries(mechByStatus)
    .map(([k, n]) => `<span class="statpill">${esc(k)} <b>${n}</b></span>`)
    .join(" ") || "<span class='muted sub'>none</span>";
  const funnelHtml = `
    <div class="kv"><span>Edges by verdict</span><b>${verdictChips}</b></div>
    <div class="kv"><span>Total edges</span><b>${fn.total_edges || 0}</b></div>
    <div class="kv"><span>Nulls</span><b>${d.n_nulls || 0}</b></div>
    <div class="kv"><span>Mechanisms by status</span><b>${mechChips}</b></div>
    <div class="kv"><span>Total mechanisms</span><b>${d.n_mechanisms || 0}</b></div>`;

  // scan width (cumulative causal_scan FDR family width — CHF-R3)
  const sw = d.scan_width || {};
  const swHtml = `<div class="kv"><span>Cumulative causal_scan width</span><b>${sw.cumulative_width || 0}</b></div>
    <div class="sub muted" style="margin-top:4px">${esc(sw.description || "")}</div>`;

  // frontier summary
  const fr = d.frontier || {};
  const frStateCells = Object.entries(fr.cells_by_state || {})
    .map(([k, n]) => `<span class="statpill">${esc(k)} <b>${n}</b></span>`)
    .join(" ") || "<span class='muted sub'>—</span>";
  const frHtml = `
    <div class="kv"><span>Total cells</span><b>${fr.total_cells || 0}</b></div>
    <div class="kv"><span>Cells by state</span><b>${frStateCells}</b></div>
    <div class="kv"><span>Target families</span><b>${esc((fr.target_families || []).join(", ") || "—")}</b></div>
    <div class="kv"><span>Environments</span><b>${esc((fr.environments || []).join(", ") || "—")}</b></div>`;

  // surprise queue
  const sq = d.surprise_queue || {};
  const sqHtml = `<div class="kv"><span>Queue size</span><b>${sq.size || 0}</b></div>
    <div class="kv"><span>Stalest source</span><b>${esc(sq.stalest_source || "—")}</b></div>
    <div class="kv"><span>Stalest asof</span><b>${esc(sq.stalest_source_asof || "—")}</b></div>`;

  // LLM lane status
  const ll = d.llm_lane || {};
  const llStatusClass = ll.status === "ok" ? "s-ok" : (ll.status === "degraded" ? "s-warn" : "s-na");
  const llHtml = `<div class="kv"><span>Status</span><b><span class="statpill ${llStatusClass}">${esc(ll.status || "unknown")}</span></b></div>
    <div class="sub muted" style="margin-top:4px">${esc(ll.description || "")}</div>`;

  // latest edges table
  const latEdges = d.latest_edges || [];
  let edgesHtml = "";
  if (!latEdges.length) {
    edgesHtml = `<div class="sub muted">no edges yet</div>`;
  } else {
    const rows = latEdges.map(e => `<tr>
      <td class="mono">${esc(e.edge_id || "—")}</td>
      <td class="sub">${esc(e.cause_feature_id || "—")}</td>
      <td class="sub">${esc(e.target_id || "—")}</td>
      <td><span class="statpill">${esc(e.verdict || "—")}</span></td>
      <td class="r">${e.n_concerns != null ? e.n_concerns : "—"}</td>
      <td class="sub">${esc((e.scanned_at || "").slice(0, 10))}</td>
    </tr>`).join("");
    edgesHtml = `<table><thead><tr>
      <th>Edge ID</th><th>Cause</th><th>Target</th><th>Verdict</th><th class="r">Concerns</th><th>Scanned</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
  }

  // audit counts
  const ac = d.audit_counts || {};
  const auditAvail = ac.available !== false;
  const acHtml = auditAvail
    ? `<div class="kv"><span>Duplicate exposure</span><b>${ac.duplicate_exposure || 0}</b></div>
       <div class="kv"><span>Shared parent suspect</span><b>${ac.shared_parent_suspect || 0}</b></div>
       <div class="kv"><span>Collider risk</span><b>${ac.collider_risk || 0}</b></div>
       <div class="kv"><span>Total annotations</span><b>${ac.total || 0}</b></div>
       <div class="kv sub muted"><span>Audit asof</span><b>${esc(ac.asof || "—")}</b></div>`
    : `<div class="sub muted">causal_confluence_audit.json not yet written (W6 step pending)</div>`;

  // latest annotations
  const anns = d.latest_audit_annotations || [];
  let annsHtml = "";
  if (!anns.length) {
    annsHtml = `<div class="sub muted">no annotations yet</div>`;
  } else {
    annsHtml = anns.map(a => `<div style="margin-bottom:8px">
      <span class="statpill">${esc(a.rule_id || "—")}</span>
      <span class="sub" style="margin-left:6px">${esc(a.annotation_type || "—")}</span>
      <div class="note sub muted" style="margin-top:4px">${esc(a.display_text || "—")}</div>
    </div>`).join("");
  }

  // data absent notes
  const danotes = d.data_absent_notes || [];
  const daHtml = danotes.length
    ? `<div class="section">Data Absent Notes</div><div class="card">${danotes.map(n => `<div class="note muted">${esc(n)}</div>`).join("")}</div>`
    : "";

  v.innerHTML = `
    ${banner}
    <div class="sub muted" style="margin-bottom:8px">${esc(freshStr)}</div>
    ${daHtml}
    <div class="section">Heartbeat</div>
    <div class="card">${hbHtml}</div>
    <div class="section">Funnel Counts</div>
    <div class="card">${funnelHtml}</div>
    <div class="section">Causal Scan Width</div>
    <div class="card">${swHtml}</div>
    <div class="section">Frontier Map</div>
    <div class="card">${frHtml}</div>
    <div class="section">Surprise Queue</div>
    <div class="card">${sqHtml}</div>
    <div class="section">LLM Lane</div>
    <div class="card">${llHtml}</div>
    <div class="section">Latest Edges <span class="cnt">${d.n_edges || 0}</span></div>
    <div class="card">${edgesHtml}</div>
    <div class="section">Anti-Mirage Audit Counts</div>
    <div class="card">${acHtml}</div>
    <div class="section">Latest Audit Annotations <span class="cnt">${anns.length}</span></div>
    <div class="card">${annsHtml}</div>`;
};

/* ---- METABOLISM --------------------------------------------------------- */
RENDER.metabolism = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="sub muted">Loading metabolism status…</div>`;
  const d = await api("/api/metabolism");

  // State chip
  const stateChip = () => {
    if (d.state === "armed")
      return `<span class="statpill s-ok" style="font-size:15px;padding:4px 12px">ARMED</span>`;
    if (d.state === "paused")
      return `<span class="statpill s-warn" style="font-size:15px;padding:4px 12px">PAUSED</span>`;
    return `<span class="statpill s-mut" style="font-size:15px;padding:4px 12px">UNKNOWN</span>`;
  };

  const stateCopy = () => {
    if (d.state === "paused")
      return "Paused — every autonomous stage exits without acting. The loop cannot author code, open PRs, or advance ledgers.";
    if (d.state === "armed")
      return "Armed — the loop senses, proposes, builds and merges on its own schedule.";
    return "Cannot read the switch — no GitHub token configured on this server.";
  };

  // Hero card
  let heroHtml = `<div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
    ${stateChip()}
    <div class="sub">${esc(stateCopy())}</div>
  </div>`;

  // Toggle button
  let toggleHtml = "";
  if (!d.has_token) {
    toggleHtml = `<div class="sub" style="color:var(--warn);margin-top:8px">Set <code>GH_TOKEN</code> in <code>/etc/macro-admin.env</code> (needs Actions read + Variables read/write) to control the loop from here.</div>`;
  } else {
    const btnLabel = d.armed ? "Pause the loop" : "Arm the loop";
    const btnCls = d.armed ? "" : "primary";
    toggleHtml = `<button id="metToggleBtn" class="btn ${btnCls}" style="margin-top:8px">${esc(btnLabel)}</button>`;
  }

  // Key pool card
  const keysHtml = (() => {
    if (typeof d.keys === "string")
      return `<div class="sub muted">${esc(d.keys)}</div>`;
    if (!Array.isArray(d.keys) || !d.keys.length)
      return `<div class="sub muted">No key data available.</div>`;
    return `<table><thead><tr><th>Key ID</th><th>Last outcome</th><th>Last seen</th><th>Cooling</th><th class="r">5h load</th></tr></thead><tbody>
      ${d.keys.map(k => `<tr>
        <td class="mono">${esc(k.id || "—")}</td>
        <td>${k.last_outcome ? `<span class="statpill ${k.last_outcome === "ok" ? "s-ok" : "s-bad"}">${esc(k.last_outcome)}</span>` : "<span class='muted sub'>—</span>"}</td>
        <td class="sub mono">${esc((k.last_ts || "—").slice(0, 16).replace("T", " "))}</td>
        <td>${k.cooling ? `<span class="statpill s-warn">cooling</span>` : `<span class="statpill s-ok">ok</span>`}</td>
        <td class="r">${k.window_load != null ? Number(k.window_load).toFixed(2) : "—"}</td>
      </tr>`).join("")}
    </tbody></table>`;
  })();

  // Organism summary card
  const orgHtml = (() => {
    if (!d.organism) return `<div class="sub muted">organism_state.json not found — loop has not run yet.</div>`;
    const rows = Object.entries(d.organism)
      .map(([k, val]) => `<div class="kv"><span>${esc(k)}</span><b>${esc(String(val == null ? "—" : val))}</b></div>`)
      .join("");
    return rows || `<div class="sub muted">Empty.</div>`;
  })();

  // Runs table
  const runsHtml = (() => {
    if (!d.runs || !d.runs.length)
      return `<div class="sub muted">No metabolism workflow runs found.</div>`;
    return `<table><thead><tr><th>Workflow</th><th>Status</th><th>Started</th><th></th></tr></thead><tbody>
      ${d.runs.map(r => `<tr>
        <td><b>${esc(r.name || r.workflow || "—")}</b></td>
        <td>${STATUS_PILL(r)}</td>
        <td class="sub mono">${esc((r.created_at || "").slice(0, 16).replace("T", " "))}</td>
        <td>${r.html_url ? `<a href="${esc(r.html_url)}" target="_blank" rel="noopener">open ↗</a>` : ""}</td>
      </tr>`).join("")}
    </tbody></table>`;
  })();

  // --- Throttle section (V11) ---
  const thr = d.throttle || {};
  const thrIntensity = thr.intensity || {};
  const thrPace = thr.pace || {};
  const thrKeys = thr.keys_enabled || {};

  // Intensity selector: display label, value sent to API, sublabel
  const INTENSITY_OPTS = [
    { label: "Low",    val: "low",    sub: "≈ half-size docket" },
    { label: "Normal", val: "normal", sub: "standard docket" },
    { label: "High",   val: "high",   sub: "1.5× docket" },
    { label: "Max",    val: "max",    sub: "2× docket" },
  ];
  const PACE_OPTS = [
    { label: "Low",    val: "low",    sub: "1 loop / 5h" },
    { label: "Medium", val: "medium", sub: "2 loops / 5h" },
    { label: "High",   val: "high",   sub: "3 loops / 5h" },
    { label: "Max",    val: "max",    sub: "4 loops / 5h" },
  ];

  // Map legacy effective pace to the new ladder value for button highlighting.
  const PACE_LEGACY_MAP = { single: "low", "2x": "medium", "4x": "high" };

  function thrSelectorHtmlV11(id, label, opts, currentEffective) {
    const effectiveMapped = PACE_LEGACY_MAP[currentEffective] || currentEffective;
    return `<div style="margin-bottom:14px">` +
      `<span class="sub" style="font-weight:600">${esc(label)}</span>` +
      `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">` +
      opts.map(opt => {
        const active = (id === "pace" ? opt.val : opt.val) === (id === "pace" ? effectiveMapped : currentEffective);
        return `<div style="display:flex;flex-direction:column;align-items:center;gap:2px">` +
          `<button class="btn${active ? " primary" : ""}" data-thr-sel="${esc(id)}" data-thr-val="${esc(opt.val)}" style="min-width:70px">${esc(opt.label)}</button>` +
          `<span class="sub muted" style="font-size:11px;text-align:center">${esc(opt.sub)}</span>` +
          `</div>`;
      }).join("") +
      `</div></div>`;
  }

  const loopDur = d.loop_duration || {};
  const durLabel = loopDur.label || "No completed live loops yet — worst case ≈ 2.5h";

  const throttleHtml = `
    <div style="margin-bottom:8px">
      ${thrIntensity.value != null ? `<div class="kv"><span>METAB_INTENSITY (repo var)</span><b class="mono">${esc(thrIntensity.value)}</b></div>` : ""}
      ${thrPace.value != null ? `<div class="kv"><span>METAB_PACE (repo var)</span><b class="mono">${esc(thrPace.value)}</b></div>` : ""}
      ${thrKeys.value != null ? `<div class="kv"><span>METAB_KEYS_ENABLED (repo var)</span><b class="mono">${esc(thrKeys.value) || "(empty = all keys)"}</b></div>` : ""}
      ${thr.note ? `<div class="sub muted" style="margin-top:4px">${esc(thr.note)}</div>` : ""}
    </div>
    <div class="kv" style="margin-bottom:8px"><span class="sub" title="Median wall-clock from last completed runs, excluding pace-gate skips">Loop timing</span><b>${esc(durLabel)}</b></div>
    ${thrSelectorHtmlV11("intensity", "Ideas per loop", INTENSITY_OPTS, thrIntensity.effective || "normal")}
    ${thrSelectorHtmlV11("pace", "Loops per 5-hour window", PACE_OPTS, thrPace.effective_ladder || thrPace.effective || "low")}
    <div style="margin-bottom:10px">
      <span class="sub">Keys enabled (csv of 1/2/3/legacy — empty = all)</span>
      <div style="display:flex;gap:8px;margin-top:4px;align-items:center;flex-wrap:wrap">
        <input id="thrKeysInput" type="text" value="${esc(thrKeys.value || "")}" placeholder="e.g. 1,2,3,legacy or empty for all" style="padding:4px 8px;background:var(--bg2,#1e1e2e);border:1px solid var(--border,#333);color:var(--text,#ccc);border-radius:4px;width:240px">
        <button class="btn" id="thrKeysSetBtn">Set keys_enabled</button>
      </div>
      <div class="sub muted" style="margin-top:4px">1=claude_code_oauth_1, 2=claude_code_oauth_2, 3=claude_code_oauth_3, legacy=CLAUDE_CODE_OAUTH_TOKEN</div>
    </div>`;

  // --- Run-now section (V11) ---
  const RUN_MODE_DESCRIPTIONS = {
    cycle:      "Runs the whole loop in order: Agenda → Propose → Adjudicate → Build",
    agenda:     "Scans the system and ranks what deserves attention",
    propose:    "Drafts new experiment/upgrade proposals (the docket)",
    adjudicate: "Judges each proposal — approve, revise, or kill",
    build:      "Turns approved proposals into code in draft PRs (never merges)",
  };
  const lobeDatalist = `<datalist id="lobeList"><option value="til"><option value="site-us-standouts"><option value="site-china-standouts"></datalist>`;
  const runNowHtml = `
    ${lobeDatalist}
    <div style="margin-bottom:10px">
      <span class="sub">Lobe (optional — empty = all managed lobes)</span>
      <div style="display:flex;gap:6px;margin-top:4px;flex-wrap:wrap;align-items:center">
        <input id="runLobeInput" type="text" list="lobeList" placeholder="e.g. til" style="padding:4px 8px;background:var(--bg2,#1e1e2e);border:1px solid var(--border,#333);color:var(--text,#ccc);border-radius:4px;width:180px">
        <button class="btn" onclick="document.getElementById('runLobeInput').value='til'">Main lobe (til)</button>
      </div>
    </div>
    <div style="margin-bottom:10px">
      <span class="sub">Stages (for Full cycle only)</span>
      <div style="margin-top:4px">
        <select id="runStagesSelect" style="padding:4px 8px;background:var(--bg2,#1e1e2e);border:1px solid var(--border,#333);color:var(--text,#ccc);border-radius:4px">
          <option value="">full (default)</option>
          <option value="full">full</option>
          <option value="sense">sense</option>
          <option value="through-adjudicate">through-adjudicate</option>
        </select>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px">
      ${[
        { mode: "cycle",      label: "▶ Full cycle", primary: true },
        { mode: "agenda",     label: "Agenda",       primary: false },
        { mode: "propose",    label: "Propose",      primary: false },
        { mode: "adjudicate", label: "Adjudicate",   primary: false },
        { mode: "build",      label: "Build",        primary: false },
      ].map(item => `<div>
        <button class="btn${item.primary ? " primary" : ""}" data-run-mode="${esc(item.mode)}">${esc(item.label)}</button>
        <div class="sub muted" style="margin-top:3px">${esc(RUN_MODE_DESCRIPTIONS[item.mode] || "")}</div>
      </div>`).join("")}
    </div>`;

  // --- Auto-run section (V11) ---
  const runUntil = d.run_until || "off";
  const autoRunArmedLabel = runUntil === "5h_max" ? "AUTO-RUN ARMED — 5H MAX"
                          : runUntil === "weekly_max" ? "AUTO-RUN ARMED — WEEKLY MAX"
                          : "";
  const autoRunStatusHtml = autoRunArmedLabel
    ? `<div class="statpill s-warn" style="margin-bottom:10px;font-size:13px;padding:4px 10px">${esc(autoRunArmedLabel)}</div>`
    : "";
  const autoRunHtml = d.has_token ? `
    ${autoRunStatusHtml}
    <div style="display:flex;flex-direction:column;gap:10px">
      <div>
        <button class="btn primary" id="rununtil5hBtn">⚡ Max out 5-hour windows</button>
        <div class="sub muted" style="margin-top:3px">Loops until every key reaches 80% of its 5-hour window, then stops.</div>
      </div>
      <div>
        <button class="btn" id="rununtiWkBtn">📅 Max out weekly budget</button>
        <div class="sub muted" style="margin-top:3px">Keeps looping as 5-hour windows reset; stops adding work to a key at 85% weekly; fully stops when all keys hit 80% weekly.</div>
      </div>
      <div>
        <button class="btn" id="rununtiStopBtn">⏹ Stop auto-run</button>
        <div class="sub muted" style="margin-top:3px">Disarms auto-run after the current loop.</div>
      </div>
    </div>` : `<div class="sub muted">GitHub token required to set auto-run mode.</div>`;

  // --- Budget status section (V11) ---
  const bs = d.budget_status || null;
  const bsTs = bs && bs.ts ? bs.ts : null;
  let budgetHtml;
  if (!bs) {
    budgetHtml = `<div class="sub muted">No usage snapshot yet — the next loop or key probe publishes one.</div>`;
  } else {
    const perKey = bs.per_key || {};
    const verdicts = bs.verdicts || {};
    const tsAgo = (() => {
      if (!bsTs) return "";
      try {
        const diff = (Date.now() - new Date(bsTs).getTime()) / 3600000;
        return diff < 1 ? `as of ${Math.round(diff * 60)}m ago` : `as of ${diff.toFixed(1)}h ago`;
      } catch(e) { return ""; }
    })();
    const manualBlocked = (verdicts.manual || {}).blocked;
    const manualBlockedHtml = manualBlocked
      ? `<div class="statpill s-warn" style="margin-bottom:8px">Manual runs blocked — all keys ≥90% weekly. Wait for a weekly reset.</div>`
      : "";
    const barHtml = (pct, src) => {
      if (pct == null) return `<span class="sub muted">unknown</span>`;
      const fill = Math.min(100, Math.max(0, pct));
      const color = fill >= 90 ? "var(--err,#e84855)" : fill >= 80 ? "var(--warn,#f4a261)" : "var(--ok,#3cb371)";
      const badge = src === "reported" ? `<span class="statpill s-ok" style="font-size:10px;padding:1px 5px">reported</span>`
                  : src === "est"      ? `<span class="statpill s-mut" style="font-size:10px;padding:1px 5px">est</span>`
                  :                     `<span class="statpill" style="font-size:10px;padding:1px 5px">unknown</span>`;
      return `<div style="display:flex;align-items:center;gap:6px">
        <div style="flex:1;background:var(--bg3,#2a2a3a);border-radius:3px;height:8px;min-width:60px">
          <div style="width:${fill}%;background:${color};height:8px;border-radius:3px"></div>
        </div>
        <span class="sub" style="min-width:36px">${fill.toFixed(0)}%</span>${badge}
      </div>`;
    };
    const keyRows = Object.entries(perKey).map(([kid, kb]) => {
      const k = kb || {};
      return `<div style="margin-bottom:8px;padding:8px;background:var(--bg2,#1e1e2e);border-radius:4px">
        <div class="sub" style="font-weight:600;margin-bottom:4px">${esc(kid)}</div>
        <div style="display:flex;flex-direction:column;gap:4px">
          <div><span class="sub muted" style="min-width:80px;display:inline-block">5h window</span>${barHtml(k.pct_5h, k.src_5h)}</div>
          <div><span class="sub muted" style="min-width:80px;display:inline-block">Weekly</span>${barHtml(k.pct_weekly, k.src_weekly)}</div>
          ${k.reset_5h ? `<div class="sub muted" style="font-size:11px">5h resets: ${esc(k.reset_5h)}</div>` : ""}
          ${k.reset_weekly ? `<div class="sub muted" style="font-size:11px">Weekly resets: ${esc(k.reset_weekly)}</div>` : ""}
        </div>
      </div>`;
    }).join("");
    budgetHtml = `
      ${manualBlockedHtml}
      ${tsAgo ? `<div class="sub muted" style="margin-bottom:8px">${esc(tsAgo)}</div>` : ""}
      ${keyRows || `<div class="sub muted">No per-key data in snapshot.</div>`}`;
  }

  v.innerHTML = `
    <div id="loopStripWrap"></div>
    <div class="section">Autonomous Loop Switch</div>
    <div class="card">
      ${heroHtml}
      ${toggleHtml}
      <div class="kv" style="margin-top:12px"><span>AUTONOMY_PAUSED variable</span><b class="mono">${esc(d.variable_value != null ? String(d.variable_value) : "(not set)")}</b></div>
      <div class="kv"><span>Freezes (last 7d)</span><b>${d.freezes_7d != null ? d.freezes_7d : "—"}</b></div>
    </div>
    <div class="section">Auto-Run</div>
    <div class="card" id="metAutoRunCard">${autoRunHtml}</div>
    <div class="section">Metabolism Throttle</div>
    <div class="card" id="metThrCard">${d.has_token ? throttleHtml : `<div class="sub muted">GitHub token required to read/set throttle variables.</div>`}</div>
    <div class="section">Run Now</div>
    <div class="card" id="metRunCard">${d.has_token ? runNowHtml : `<div class="sub muted">GitHub token required to dispatch workflows.</div>`}</div>
    <div class="section">Key Usage</div>
    <div class="card" id="metBudgetCard">${budgetHtml}</div>
    <div class="section">Organism State</div>
    <div class="card">${orgHtml}</div>
    <div class="section">Key Pool</div>
    <div class="card">${keysHtml}</div>
    <div class="card sub muted" style="margin-top:4px">Raw key usage moved to the AI Cost tab.</div>
    <div class="section">Recent Metabolism Runs <span class="cnt">${(d.runs || []).length}</span></div>
    <div class="card">${runsHtml}</div>
    <div class="section">What the Loop Did</div>
    <div class="card" id="metAchCard">
      <div class="skeleton skeleton-text" style="width:60%"></div>
      <div class="skeleton skeleton-text" style="width:80%"></div>
      <div class="skeleton skeleton-text" style="width:50%"></div>
    </div>
    <div class="section">Change History <span class="cnt" id="mhCnt"></span></div>
    <div class="card" id="mhCard">
      <div class="skeleton skeleton-text" style="width:60%"></div>
      <div class="skeleton skeleton-text" style="width:80%"></div>
      <div class="skeleton skeleton-text" style="width:50%"></div>
    </div>
    <div class="section" style="margin-top:20px">Break-glass</div>
    <div class="card sub muted">Emergency stop: this switch, or <code>gh variable set AUTONOMY_PAUSED --body true</code>, or disable the metabolism workflows in GitHub Actions.</div>`;

  // Wire throttle selector buttons
  if (d.has_token) {
    v.querySelectorAll("[data-thr-sel]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const field = btn.dataset.thrSel;
        const val = btn.dataset.thrVal;
        if (!window.confirm(`Set ${field} = "${val}"?`)) return;
        btn.disabled = true;
        const r = await post("/api/metabolism/throttle", { [field]: val, confirm: true });
        if (r.ok) {
          toast(`Set ${field} = ${val}`);
          RENDER.metabolism();
        } else {
          const errMsg = r.errors ? JSON.stringify(r.errors) : (r.error || "unknown error");
          alert(`Failed: ${errMsg}`);
          btn.disabled = false;
        }
      });
    });

    const keysSetBtn = $("#metKeysSetBtn", v);
    if (keysSetBtn) {
      keysSetBtn.addEventListener("click", async () => {
        const val = ($("#thrKeysInput", v) || {}).value || "";
        if (!window.confirm(`Set keys_enabled = "${val || "(empty = all keys)"}"?`)) return;
        keysSetBtn.disabled = true;
        const r = await post("/api/metabolism/throttle", { keys_enabled: val, confirm: true });
        if (r.ok) {
          toast(`Set METAB_KEYS_ENABLED = "${val || ""}"`);
          RENDER.metabolism();
        } else {
          const errMsg = r.errors ? JSON.stringify(r.errors) : (r.error || "unknown error");
          alert(`Failed: ${errMsg}`);
          keysSetBtn.disabled = false;
        }
      });
    }

    v.querySelectorAll("[data-run-mode]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const mode = btn.dataset.runMode;
        const lobe = ($("#runLobeInput", v) || {}).value || "";
        const stagesEl = $("#runStagesSelect", v);
        const stages = stagesEl ? stagesEl.value : "";
        const label = mode === "cycle" ? "Full cycle" : mode.charAt(0).toUpperCase() + mode.slice(1);
        const lobeNote = lobe ? ` (lobe: ${lobe})` : "";
        const stagesNote = (mode === "cycle" && stages) ? ` stages: ${stages}` : "";
        if (!window.confirm(`Dispatch ${label}${lobeNote}${stagesNote}?`)) return;
        btn.disabled = true;
        const body = { mode, confirm: true };
        if (lobe) body.lobe = lobe;
        if (stages && mode === "cycle") body.stages = stages;
        const r = await post("/api/metabolism/run", body);
        if (r.ok) {
          toast(`Dispatched ${label}${lobeNote}`);
        } else {
          alert(`Dispatch failed: ${r.error || (r.blocked ? "All keys at or above weekly limit — wait for a reset." : "unknown error")}`);
        }
        btn.disabled = false;
      });
    });

    // Wire auto-run buttons
    async function postRununtil(mode, label) {
      const msg = mode === "off"
        ? "Stop auto-run? The current loop (if any) will finish normally."
        : `Arm auto-run: ${label}? This will dispatch a loop immediately.`;
      if (!window.confirm(msg)) return;
      const btn5h = $("#rununtil5hBtn", v);
      const btnWk = $("#rununtiWkBtn", v);
      const btnStop = $("#rununtiStopBtn", v);
      [btn5h, btnWk, btnStop].forEach(b => { if (b) b.disabled = true; });
      const r = await post("/api/metabolism/rununtil", { mode, confirm: true });
      if (r.ok) {
        toast(mode === "off" ? "Auto-run stopped." : `Auto-run armed: ${label}`);
        RENDER.metabolism();
      } else {
        alert(`Failed: ${r.error || "unknown error"}`);
        [btn5h, btnWk, btnStop].forEach(b => { if (b) b.disabled = false; });
      }
    }
    const ar5h = $("#rununtil5hBtn", v);
    if (ar5h) ar5h.addEventListener("click", () => postRununtil("5h_max", "Max out 5-hour windows"));
    const arWk = $("#rununtiWkBtn", v);
    if (arWk) arWk.addEventListener("click", () => postRununtil("weekly_max", "Max out weekly budget"));
    const arStop = $("#rununtiStopBtn", v);
    if (arStop) arStop.addEventListener("click", () => postRununtil("off", "Stop"));
  }

  // Live-loop strip poll (20s interval while on metabolism tab)
  startLoopPoll("metabolism", "loopStripWrap", false);

  const btn = $("#metToggleBtn");
  if (btn) {
    btn.onclick = async () => {
      const toArm = !d.armed;
      const msg = toArm
        ? "Arm the autonomous metabolism loop? It will start acting on its own schedule within the hour."
        : "Pause the loop? In-flight stages finish, nothing new dispatches.";
      if (!window.confirm(msg)) return;
      btn.disabled = true;
      const r = await post("/api/metabolism/toggle", { armed: toArm, confirm: true });
      if (r.ok) {
        toast(toArm ? "Metabolism loop armed." : "Metabolism loop paused.");
        RENDER.metabolism();
      } else {
        alert("Toggle failed: " + (r.error || "unknown error"));
        btn.disabled = false;
      }
    };
  }

  // Async "What the Loop Did" achievements loader — does not block the panel above.
  (async () => {
    const achCard = $("#metAchCard");
    if (!achCard) return;

    // Format a relative time-ago string from an ISO timestamp.
    const timeAgo = (ts) => {
      try {
        const diff = (Date.now() - new Date(ts).getTime()) / 3600000;
        if (diff < 0.02) return "just now";
        if (diff < 1) return `${Math.round(diff * 60)}m ago`;
        if (diff < 24) return `${diff.toFixed(1)}h ago`;
        return `${Math.round(diff / 24)}d ago`;
      } catch(e) { return ""; }
    };

    // Stage name → plain-word label mapping (FIX 8: plain words; slug kept in title= on callers).
    const stagePlain = (name) => {
      const MAP = { agenda: "picked what to work on", sense: "sense",
                    propose: "drafted ideas", adjudicate: "safety review",
                    build: "opened PRs", verify: "verify" };
      return MAP[String(name).toLowerCase()] || String(name);
    };

    // Status → pill class.
    const statusCls = (s) => {
      const m = { ok: "s-ok", authorized: "s-ok", denied: "s-bad", failed: "s-bad",
                  warn: "s-warn", never_ruled: "s-mut", skipped: "s-mut", noop: "s-mut" };
      return m[String(s).toLowerCase()] || "s-mut";
    };

    let ach;
    try {
      ach = await api("/api/metabolism/achievements");
    } catch (e) {
      const c = $("#metAchCard");
      if (c) c.innerHTML = `<div class="sub muted">Could not load loop activity: ${esc(String(e))}</div>`;
      return;
    }

    const c = $("#metAchCard");
    if (!c) return;

    if (ach && ach.error && ach.error.includes("not yet available")) {
      c.innerHTML = `<div class="sub muted">No loop activity recorded yet.</div>`;
      return;
    }
    if (ach && ach.error) {
      c.innerHTML = `<div class="sub muted">Loop activity unavailable: ${esc(ach.error)}</div>`;
      return;
    }

    const cycles = Array.isArray(ach && ach.cycles) ? ach.cycles : [];
    if (!cycles.length) {
      c.innerHTML = `<div class="sub muted">No loop activity recorded yet.</div>`;
      return;
    }

    const cycleCards = cycles.map(cy => {
      const hasBlocker = !!(cy.blocker_plain);
      const headerCls = hasBlocker ? "border-left:3px solid var(--err,#e84855);padding-left:8px;" : "";
      // FIX 2: timestamp is cy.started_at (not cy.ts which the composer never sets).
      const ago = cy.started_at ? timeAgo(cy.started_at) : "";
      const headline = esc(cy.headline_plain || cy.cycle_id || "cycle");
      const blockerHtml = hasBlocker
        ? `<div class="sub" style="color:var(--err,#e84855);margin-top:4px">${esc(cy.blocker_plain)}</div>`
        : "";

      // FIX 2: cy.lobes is a DICT {lobe: {proposed, authorized, denied, never_ruled, prs}}.
      // Use Object.entries — not Array.isArray which always fails on a dict.
      const lobeEntries = Object.entries(cy.lobes || {});
      const lobeLines = lobeEntries.map(([lobeName, lb]) => {
        const parts = [];
        const n_proposed = lb.proposed || 0;
        const n_authorized = lb.authorized || 0;
        const n_denied = lb.denied || 0;
        const n_never_ruled = lb.never_ruled || 0;
        if (n_proposed) parts.push(`${n_proposed} proposed`);
        if (n_authorized) parts.push(`→ <span class="statpill s-ok" style="font-size:11px">${n_authorized} authorized</span>`);
        if (n_denied) parts.push(`→ <span class="statpill s-bad" style="font-size:11px">${n_denied} denied</span>`);
        if (n_never_ruled) parts.push(`→ <span class="statpill s-mut" style="font-size:11px">${n_never_ruled} never ruled</span>`);
        // PR links from lb.prs (array of URLs)
        (lb.prs || []).forEach(url => {
          if (url) {
            parts.push(`<a href="${esc(url)}" target="_blank" rel="noopener">PR ↗</a>`);
          }
        });
        const summary = parts.length ? parts.join(" · ") : "no activity";
        return `<div class="sub" style="margin:3px 0"><b>${esc(lobeName)}</b>: ${summary}</div>`;
      }).join("");

      // Stage strip. FIX 2: stage notes use note_plain (not label which the composer never sets).
      const stages = cy.stages || {};
      const stageNames = ["agenda", "propose", "adjudicate", "build"];
      const stageStrip = stageNames.map(sn => {
        const st = stages[sn];
        if (!st) return `<span class="statpill s-mut" title="${sn}" style="font-size:10px;opacity:0.5">${stagePlain(sn)}</span>`;
        const cls = statusCls(st.status || "");
        return `<span class="statpill ${cls}" title="${sn}" style="font-size:10px">${stagePlain(sn)}: ${esc(st.note_plain || st.status || "—")}</span>`;
      }).join(" ");

      return `<div style="margin-bottom:16px;padding:10px;background:var(--bg2,#1e1e2e);border-radius:6px">
        <div style="${headerCls}">
          <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
            <span class="sub muted" style="font-size:11px">${esc(ago)}</span>
            <span style="font-weight:600">${headline}</span>
          </div>
          ${blockerHtml}
        </div>
        ${lobeLines ? `<div style="margin-top:8px">${lobeLines}</div>` : ""}
        ${stageStrip ? `<div style="margin-top:8px;display:flex;gap:4px;flex-wrap:wrap">${stageStrip}</div>` : ""}
      </div>`;
    }).join("");

    c.innerHTML = cycleCards;
  })();

  // Async Change History loader — does not block the panel above.
  (async () => {
    const mhCard = $("#mhCard");
    if (!mhCard) return;

    // Status pill for a history event (label = event.kind, class from status).
    const mhPill = (ev) => {
      const cls = ev.status === "ok" ? "s-ok" : ev.status === "warn" ? "s-warn" : ev.status === "bad" ? "s-bad" : "s-mut";
      return `<span class="statpill ${cls}">${esc(ev.kind || ev.status || "info")}</span>`;
    };

    // Build timeline HTML for a filtered event list.
    const mhTimeline = (events) => {
      if (!events.length) {
        return `<div class="empty"><div class="empty-icon">&#x1f4dc;</div><div class="empty-text">No autonomous changes recorded yet.</div><div class="empty-sub">This feed fills as the loop runs — PRs authored, audits filed, lobe lifecycle events, and reverts will appear here.</div></div>`;
      }
      return `<div class="timeline">${events.map(ev => {
        const ts = esc((ev.ts || "").slice(0, 16).replace("T", " "));
        const titleLink = ev.url
          ? `${esc(ev.title || "")} <a href="${esc(ev.url)}" target="_blank" rel="noopener">open &#x2197;</a>`
          : esc(ev.title || "");
        const detail = esc(ev.detail || "") + (ev.ref ? " \xb7 " + esc(ev.ref) : "");
        return `<div class="timeline-item">
          <div class="timeline-ts">${ts}</div>
          <div class="timeline-header"><span class="timeline-kind">${esc(ev.source || "")}</span> ${mhPill(ev)}</div>
          <div class="timeline-summary">${titleLink}</div>
          ${detail ? `<div class="timeline-source">${detail}</div>` : ""}
        </div>`;
      }).join("")}</div>`;
    };

    let h;
    try {
      h = await api("/api/metabolism/history?limit=200");
    } catch (e) {
      const card = $("#mhCard");
      if (card) card.innerHTML = `<div class="sub muted">Could not load change history: ${esc(String(e))}</div>`;
      return;
    }

    // Guard: user may have navigated away.
    const card = $("#mhCard");
    if (!card) return;

    if (h.error) {
      card.innerHTML = `<div class="sub muted">Change history unavailable: ${esc(h.error)}</div>`;
      return;
    }

    const allEvents = Array.isArray(h.events) ? h.events : [];
    const sources = h.sources && typeof h.sources === "object" ? h.sources : {};
    const phase0 = !!h.phase0;

    // Gather active sources (count > 0) for pills.
    const activeSources = Object.entries(sources).filter(([, v]) => v && v.count > 0).map(([k, v]) => [k, v.count]);
    const total = allEvents.length;
    const heartbeatCount = (sources.heartbeat && sources.heartbeat.count) || 0;

    // Filter state: "all" or a source name; heartbeats hidden by default.
    let activeFilter = "all";
    let showHeartbeats = false;

    const render = (filter, inclHeartbeats) => {
      const card2 = $("#mhCard");
      if (!card2) return;
      // Apply heartbeat exclusion before source filter
      const baseEvents = inclHeartbeats ? allEvents : allEvents.filter(ev => ev.source !== "heartbeat");
      const baseTotal = baseEvents.length;
      const filtered = filter === "all" ? baseEvents : baseEvents.filter(ev => ev.source === filter);
      const cnt = $("#mhCnt");
      if (cnt) cnt.textContent = filter === "all" ? baseTotal : `${filtered.length}/${baseTotal}`;

      // Source filter pills — skip heartbeat pill when excluded.
      const visibleSources = inclHeartbeats
        ? activeSources
        : activeSources.filter(([src]) => src !== "heartbeat");

      const hbToggleLabel = inclHeartbeats
        ? `hide heartbeats (${heartbeatCount})`
        : `show heartbeats (${heartbeatCount})`;
      const hbToggleStyle = inclHeartbeats
        ? "border:2px solid var(--accent);font-weight:700;"
        : "";

      const pillsHtml = [
        `<button class="btn" data-mhf="all" style="margin:0 4px 6px 0;font-size:12px;${filter === "all" ? "border:2px solid var(--accent);font-weight:700" : ""}">All ${baseTotal}</button>`,
        ...visibleSources.map(([src, cnt2]) =>
          `<button class="btn" data-mhf="${esc(src)}" style="margin:0 4px 6px 0;font-size:12px;${filter === src ? "border:2px solid var(--accent);font-weight:700" : ""}">${esc(src)} ${cnt2}</button>`),
        heartbeatCount > 0
          ? `<button class="btn" id="mhHbToggle" style="margin:0 4px 6px 0;font-size:12px;opacity:0.7;${hbToggleStyle}">${hbToggleLabel}</button>`
          : ""
      ].join("");

      const phase0Banner = phase0
        ? `<div class="sub muted" style="margin-bottom:10px">The loop is still inert (Phase 0) — only heartbeats and rehearsals appear here. Once armed, autonomous PRs, audits, lobe lifecycle events and reverts will land in this feed.</div>`
        : "";

      // Degradation notes.
      const notes = Object.values(sources).filter(v => v && v.note).map(v => `<div class="sub muted" style="margin-top:8px">${esc(v.note)}</div>`).join("");

      card2.innerHTML = `<div style="margin-bottom:8px">${pillsHtml}</div>${phase0Banner}${mhTimeline(filtered)}${notes}`;

      // Bind source filter pills.
      card2.querySelectorAll("[data-mhf]").forEach(el => {
        el.onclick = () => { activeFilter = el.dataset.mhf; render(activeFilter, showHeartbeats); };
      });

      // Bind heartbeat toggle.
      const hbBtn = $("#mhHbToggle", card2);
      if (hbBtn) {
        hbBtn.onclick = () => {
          showHeartbeats = !showHeartbeats;
          // If user was filtering by heartbeat but hides them, reset to all.
          if (!showHeartbeats && activeFilter === "heartbeat") activeFilter = "all";
          render(activeFilter, showHeartbeats);
        };
      }
    };

    render(activeFilter, showHeartbeats);
  })();
};

/* ---- Codex Research panel ----------------------------------------------- */
RENDER.codex = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="sub muted">Loading Codex Research status…</div>`;
  const d = await api("/api/codex");

  const hasToken = !!(d.mode && d.mode.allowed);  // panel returned = token may or may not be set

  // --- Mode selector ---
  const modeSel = d.mode || {};
  const lanesSel = d.lanes || {};
  const intHrs = d.interval_hours || {};

  function codexSelectorHtml(id, label, options, currentEffective) {
    return `<div style="margin-bottom:10px"><span class="sub">${esc(label)}</span><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px">` +
      options.map(opt =>
        `<button class="btn${opt === currentEffective ? " primary" : ""}" data-cdx-sel="${esc(id)}" data-cdx-val="${esc(opt)}" style="min-width:60px">${esc(opt)}</button>`
      ).join("") +
      `</div></div>`;
  }

  const modeHtml = `
    <div style="margin-bottom:8px">
      ${modeSel.value != null ? `<div class="kv"><span>CODEX_MODE (repo var)</span><b class="mono">${esc(modeSel.value)}</b></div>` : `<div class="kv"><span>CODEX_MODE</span><b class="mono muted">(not set — effective: off)</b></div>`}
      ${intHrs.value != null ? `<div class="kv"><span>CODEX_INTERVAL_HOURS (repo var)</span><b class="mono">${esc(intHrs.value)}</b></div>` : ""}
      ${lanesSel.value != null ? `<div class="kv"><span>CODEX_LANES (repo var)</span><b class="mono">${esc(lanesSel.value)}</b></div>` : ""}
    </div>
    ${codexSelectorHtml("mode", "Mode", modeSel.allowed || ["auto","interval","off"], modeSel.effective || "off")}
    <div style="margin-bottom:10px">
      <span class="sub">Interval hours (interval mode; 1–48)</span>
      <div style="display:flex;gap:8px;margin-top:4px;align-items:center;flex-wrap:wrap">
        <input id="cdxIntervalInput" type="number" min="1" max="48" value="${esc(String(intHrs.effective || 6))}" style="padding:4px 8px;background:var(--bg2,#1e1e2e);border:1px solid var(--border,#333);color:var(--text,#ccc);border-radius:4px;width:80px">
        <button class="btn" id="cdxIntervalSetBtn">Set interval</button>
      </div>
    </div>
    ${codexSelectorHtml("lanes", "Lanes", lanesSel.allowed || ["both","cases","signals"], lanesSel.effective || "both")}`;

  // --- Usage bars ---
  const usage = d.usage;
  let usageHtml = `<div class="sub muted">No usage data yet — runs will populate this.</div>`;
  if (usage) {
    const priPct = usage.primary_used_pct;
    const secPct = usage.secondary_used_pct;
    const budgetPct = usage.budget_pct || 85;
    const pausedUntil = usage.paused_until;
    const degraded = !!usage.degraded;

    const pbar = (label, pct) => {
      if (pct == null) return `<div class="kv"><span>${esc(label)}</span><b class="muted">—</b></div>`;
      const fill = Math.min(100, Math.max(0, pct));
      const cls = fill >= budgetPct ? "s-bad" : fill >= budgetPct * 0.75 ? "s-warn" : "s-ok";
      return `<div style="margin-bottom:8px">
        <div class="kv" style="margin-bottom:4px"><span class="sub">${esc(label)}</span><b>${fill.toFixed(1)}%</b></div>
        <div style="background:var(--bg2,#1e1e2e);border-radius:4px;height:8px;overflow:hidden">
          <div style="width:${fill}%;height:100%;background:var(--accent,#7f6bf5);border-radius:4px;padding:0" class="statpill ${cls}"></div>
        </div>
        ${fill >= budgetPct ? `<div class="sub muted" style="margin-top:2px">At or above ${budgetPct}% budget — lane will pause until window resets.</div>` : ""}
      </div>`;
    };

    usageHtml = `
      ${pausedUntil ? `<div class="sub" style="background:var(--bg2,#1e1e2e);padding:8px;border-radius:4px;margin-bottom:10px;border-left:3px solid var(--warn,#f5a623)">Paused until <b>${esc(pausedUntil)}</b> (usage limit hit; auto-mode resumes after reset)</div>` : ""}
      ${degraded ? `<div class="kv" style="margin-bottom:8px"><span>Mode</span><span class="statpill s-warn">degraded — est. session cap</span></div>` : ""}
      ${pbar("5h primary window used", priPct)}
      ${pbar("Weekly secondary window used", secPct)}
      <div class="kv"><span>Budget cutoff</span><b>${budgetPct}%</b></div>
      ${usage.sessions_in_window != null ? `<div class="kv"><span>Sessions in current 5h window</span><b>${usage.sessions_in_window}</b></div>` : ""}`;
  }

  // --- Run-now ---
  const runNowHtml = `
    <div style="margin-bottom:10px">
      <span class="sub">Iterations (1–20)</span>
      <div style="display:flex;gap:8px;margin-top:4px;align-items:center">
        <input id="cdxIterInput" type="number" min="1" max="20" value="1" style="padding:4px 8px;background:var(--bg2,#1e1e2e);border:1px solid var(--border,#333);color:var(--text,#ccc);border-radius:4px;width:80px">
      </div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn primary" data-cdx-run="cases">▶ Cases</button>
      <button class="btn" data-cdx-run="signals">▶ Signals</button>
      <button class="btn" data-cdx-run="both">▶ Both</button>
    </div>`;

  // --- Recent attempts ---
  const attempts = Array.isArray(d.attempts) ? d.attempts : [];
  const attemptsHtml = attempts.length === 0
    ? `<div class="sub muted">No case attempts recorded yet.</div>`
    : `<table><thead><tr><th>Episode</th><th>Status</th><th>PR</th><th>Timestamp</th></tr></thead><tbody>
      ${attempts.map(a => {
        const stCls = a.status === "pr_opened" ? "s-ok" : a.status === "audit_failed" ? "s-bad" : a.status === "skipped" ? "s-mut" : "s-warn";
        const prLink = a.pr_url ? `<a href="${esc(a.pr_url)}" target="_blank" rel="noopener">PR ↗</a>` : "—";
        return `<tr>
          <td class="mono">${esc(a.episode || "—")}</td>
          <td><span class="statpill ${stCls}">${esc(a.status || "—")}</span></td>
          <td>${prLink}</td>
          <td class="sub mono">${esc((a.ts || a.timestamp || "").slice(0, 16).replace("T", " "))}</td>
        </tr>`;
      }).join("")}
    </tbody></table>`;

  // --- Loop journal ---
  const loop = Array.isArray(d.loop) ? d.loop : [];
  const loopHtml = loop.length === 0
    ? `<div class="sub muted">No loop journal entries yet.</div>`
    : loop.map(row => {
        const ts = esc((row.ts || "").slice(0, 16).replace("T", " "));
        return `<div class="kv"><span class="sub mono">${ts}</span><span>${esc(row.action || row.event || JSON.stringify(row))}</span></div>`;
      }).join("");

  // --- Workflow runs ---
  const runs = Array.isArray(d.runs) ? d.runs : [];
  const runsHtml = runs.length === 0
    ? `<div class="sub muted">No codex-research workflow runs found.</div>`
    : `<table><thead><tr><th>Status</th><th>Conclusion</th><th>Started</th><th>Link</th></tr></thead><tbody>
      ${runs.map(r => {
        const stCls = r.conclusion === "success" ? "s-ok" : r.conclusion === "failure" ? "s-bad" : r.conclusion ? "s-mut" : "s-warn";
        return `<tr>
          <td>${esc(r.status || "—")}</td>
          <td><span class="statpill ${stCls}">${esc(r.conclusion || r.status || "—")}</span></td>
          <td class="sub mono">${esc((r.created_at || "").slice(0, 16).replace("T", " "))}</td>
          <td>${r.html_url ? `<a href="${esc(r.html_url)}" target="_blank" rel="noopener">open ↗</a>` : "—"}</td>
        </tr>`;
      }).join("")}
    </tbody></table>`;

  v.innerHTML = `
    <div class="section">Codex Mode</div>
    <div class="card" id="cdxModeCard">${modeHtml}</div>
    <div class="section">Usage</div>
    <div class="card">${usageHtml}</div>
    <div class="section">Run Now</div>
    <div class="card" id="cdxRunCard">${runNowHtml}</div>
    <div class="section">Recent Case Attempts <span class="cnt">${attempts.length}</span></div>
    <div class="card">${attemptsHtml}</div>
    <div class="section">Loop Journal</div>
    <div class="card">${loopHtml}</div>
    <div class="section">Recent Workflow Runs <span class="cnt">${runs.length}</span></div>
    <div class="card">${runsHtml}</div>`;

  // Wire mode / lanes selector buttons
  v.querySelectorAll("[data-cdx-sel]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const field = btn.dataset.cdxSel;
      const val = btn.dataset.cdxVal;
      if (!window.confirm(`Set ${field} = "${val}"?`)) return;
      btn.disabled = true;
      const r = await post("/api/codex/mode", { [field]: val, confirm: true });
      if (r.ok) {
        toast(`Set ${field} = ${val}`);
        RENDER.codex();
      } else {
        const errMsg = r.errors ? JSON.stringify(r.errors) : (r.error || "unknown error");
        alert(`Failed: ${errMsg}`);
        btn.disabled = false;
      }
    });
  });

  // Wire interval set button
  const cdxIntervalBtn = $("#cdxIntervalSetBtn", v);
  if (cdxIntervalBtn) {
    cdxIntervalBtn.addEventListener("click", async () => {
      const val = parseInt(($("#cdxIntervalInput", v) || {}).value || "6", 10);
      if (!window.confirm(`Set interval_hours = ${val}?`)) return;
      cdxIntervalBtn.disabled = true;
      const r = await post("/api/codex/mode", { interval_hours: val, confirm: true });
      if (r.ok) {
        toast(`Set CODEX_INTERVAL_HOURS = ${val}`);
        RENDER.codex();
      } else {
        const errMsg = r.errors ? JSON.stringify(r.errors) : (r.error || "unknown error");
        alert(`Failed: ${errMsg}`);
        cdxIntervalBtn.disabled = false;
      }
    });
  }

  // Wire run-now buttons
  v.querySelectorAll("[data-cdx-run]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const lane = btn.dataset.cdxRun;
      const iterEl = $("#cdxIterInput", v);
      const iterations = iterEl ? parseInt(iterEl.value || "1", 10) : 1;
      const label = lane.charAt(0).toUpperCase() + lane.slice(1);
      if (!window.confirm(`Dispatch Codex Research — lane: ${lane}, iterations: ${iterations}?`)) return;
      btn.disabled = true;
      const r = await post("/api/codex/run", { lane, iterations, confirm: true });
      if (r.ok) {
        toast(`Dispatched Codex ${label} (${iterations} iteration${iterations === 1 ? "" : "s"})`);
      } else {
        alert(`Dispatch failed: ${r.error || "unknown error"}`);
      }
      btn.disabled = false;
    });
  });
};


/* ---- boot --------------------------------------------------------------- */
/* Wrap any table in the content area so wide tables scroll horizontally
   (the shell column clips overflow, so a bare <table> would be cut off). */
function wrapViewTables() {
  const view = $("#view"); if (!view) return;
  view.querySelectorAll("table").forEach(tbl => {
    const p = tbl.parentElement;
    if (!p || p.classList.contains("table-wrap")) return;
    const w = document.createElement("div");
    w.className = "table-wrap";
    p.insertBefore(w, tbl);
    w.appendChild(tbl);
  });
}
let _tableObserver = null;
function startTableObserver() {
  if (_tableObserver) return;
  const view = $("#view"); if (!view) return;
  _tableObserver = new MutationObserver(() => wrapViewTables());
  _tableObserver.observe(view, { childList: true, subtree: true });
}

async function boot() {
  renderSidebar();
  startTableObserver();
  await refresh();
  route();
}
(async function init() {
  SESSION = await fetch("/api/session").then(r => r.json()).catch(() => ({ auth_enabled: false, authenticated: true }));
  if (SESSION.auth_enabled && !SESSION.authenticated) { showLogin(); return; }
  hideLogin(); boot();
})();
