"use strict";
/* Mastermind Admin — single-page console. Vanilla JS, no external deps. */

const $ = (sel, el = document) => el.querySelector(sel);
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtAge = (hrs) => hrs == null ? "—" : hrs < 1 ? `${Math.round(hrs * 60)}m` : hrs < 48 ? `${hrs.toFixed(0)}h` : `${(hrs / 24).toFixed(0)}d`;
const fmtUSD = (n) => n == null ? "—" : "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
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
};
const NAV_GROUPS = [
  { label: "", items: [["overview", "Overview"]] },
  { label: "Neural Web", items: [["neural_web", "Observatory"], ["alerts", "Alerts"], ["long_hold", "Long-Hold Lobe"], ["context_lobe", "Context Lobe"], ["causal_lab", "Causal Lab"]] },
  { label: "Growth", items: [["analytics", "Analytics"], ["users", "Users"], ["experiments", "Experiments"]] },
  { label: "System", items: [["system", "System"], ["health", "Health"], ["deploy", "Build & Deploy"], ["metabolism", "Metabolism"], ["codex", "Codex Research"], ["cost", "AI Cost"], ["content", "Content"]] },
  { label: "Config", items: [["features", "Features"], ["brief", "AI Brief"], ["vector", "BTC Override"]] },
];
const TAB_LABELS = Object.fromEntries(NAV_GROUPS.flatMap(g => g.items));
let CURRENT = "overview";
let SUMMARY = null;
let RT_TIMER = null;

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
  if (currentLobeId()) history.replaceState(null, "", location.pathname + location.search);
  CURRENT = id;
  if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; }
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

/* ---- ANALYTICS (Umami) -------------------------------------------------- */
RENDER.analytics = async () => {
  const v = $("#view");
  const st = await api("/api/analytics");
  const dash = st.dashboard_url || "https://cloud.umami.is";
  if (!st.configured) {
    v.innerHTML = `
      <div class="grid">
        ${card("Visitor tracking", `<div class="big" style="color:var(--ok);font-size:20px">● Live</div><div class="sub">running on every page · site ID <code>${esc((st.website_id || "").slice(0, 8))}…</code></div>`)}
        ${card("Live charts here", `<div class="big" style="color:var(--warn);font-size:18px">Not connected</div><div class="sub">${esc(st.reason || "")}</div>`)}
        ${card("Full dashboard", `<div style="margin-top:6px"><a class="btn primary" href="${esc(dash)}" target="_blank" rel="noopener">Open Umami ↗</a></div>`)}
      </div>
      <div class="section">Show live charts on this page</div>
      <div class="card"><ol class="steps">${(st.setup_steps || []).map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>`;
    return;
  }
  v.innerHTML = `
    <div class="grid">
      ${card("Active now", `<div class="big" id="aNow">…</div><div class="sub">last 5 min</div>`)}
      ${card("Visitors (7d)", `<div class="big" id="aVis">…</div><div class="sub" id="aVisits"></div>`)}
      ${card("Pageviews (7d)", `<div class="big" id="aPv">…</div><div class="sub"><a href="${esc(dash)}" target="_blank" rel="noopener">dashboard ↗</a></div>`)}
    </div>
    <div class="grid" style="margin-top:14px">
      <div class="card"><h3>Top pages (7d)</h3><div id="aPages" class="sub">loading…</div></div>
      <div class="card"><h3>Top countries (7d)</h3><div id="aCty" class="sub">loading…</div></div>
      <div class="card"><h3>Top referrers (7d)</h3><div id="aRef" class="sub">loading…</div></div>
    </div>`;
  const poll = async () => {
    if (CURRENT !== "analytics" || !$("#aNow")) { if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; } return; }
    const a = await api("/api/analytics/active"); const el = $("#aNow"); if (el) el.textContent = a.ok ? a.active : "—";
  };
  RT_TIMER = setInterval(poll, 15000); poll();
  const rep = await api("/api/analytics/report?days=7");
  if (rep.ok) {
    $("#aVis").textContent = fmtNum(rep.summary.visitors); $("#aVisits").textContent = fmtNum(rep.summary.visits) + " visits";
    $("#aPv").textContent = fmtNum(rep.summary.pageviews);
    $("#aPages").innerHTML = (rep.top_pages || []).map(p => `<div class="kv"><span class="mono">${esc(p.path)}</span><b>${fmtNum(p.views)}</b></div>`).join("") || "<span class='muted'>none</span>";
    $("#aCty").innerHTML = (rep.top_countries || []).map(c => `<div class="kv"><span>${esc(c.country)}</span><b>${fmtNum(c.visitors)}</b></div>`).join("") || "<span class='muted'>none</span>";
    $("#aRef").innerHTML = (rep.top_referrers || []).map(r => `<div class="kv"><span class="mono">${esc(r.referrer)}</span><b>${fmtNum(r.visitors)}</b></div>`).join("") || "<span class='muted'>none</span>";
  } else { $("#aPages").textContent = rep.error || "no data"; }
};

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
  const v = $("#view"); const d = await api("/api/cost");
  if (d.error) { v.innerHTML = card("Error", `<div class="sub" style="color:var(--bad)">${esc(d.error)}</div>`); return; }
  const r = d.realized || {};
  v.innerHTML = `
    <div class="grid">
      ${card("Est. monthly", `<div class="big">${fmtUSD(d.monthly_usd)}</div><div class="sub">~${d.assumptions.build_days_per_month} build-days/mo</div>`)}
      ${card("Per build", `<div class="big">${fmtUSD(d.per_build_usd)}</div><div class="sub">${fmtUSD(d.effective_daily_usd)}/day effective</div>`)}
      ${card("Actually generated", `<div class="big">${r.stockbrief_files || 0}</div><div class="sub">stock briefs · ${r.ai_desk_theses_logged || 0} analyst calls</div>`)}
    </div>
    ${!d.deepseek_key ? `<div class="card sub" style="margin-top:12px;color:var(--warn)">No AI key set — actual spend is $0.</div>` : ""}
    <div class="section">What's using AI</div>
    <table><thead><tr><th>Feature</th><th>On</th><th>Model</th><th class="r">Calls/build</th><th class="r">$/build</th><th>How often</th></tr></thead><tbody>
      ${(d.components || []).map(c => `<tr><td><b>${esc(c.name)}</b><div class="sub">${esc(c.note)}</div></td>
        <td>${c.enabled ? "<span class='statpill s-ok'>yes</span>" : "<span class='statpill s-mut'>no</span>"}</td>
        <td class="mono">${esc(c.model)}</td><td class="r">${c.calls_per_build}</td><td class="r">${fmtUSD(c.cost_per_build)}</td><td class="sub">every ${c.interval_days}d</td></tr>`).join("")}
    </tbody></table>`;
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
    const chipCls = s === "gate-passed" ? "s-ok" : s === "accruing" ? "s-warn" : "s-muted";
    return `<div class="kv"><span>${hi.toUpperCase()}</span><b>${nwPill("BH-WITHHELD", "s-bad")} <span class="muted sub">(${esc(s)})</span></b></div>`;
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

RENDER.neural_web = async () => {
  const v = $("#view");
  v.innerHTML = `<div class="skeleton skeleton-title"></div><div class="skeleton skeleton-card"></div>
    <div class="lobe-grid">${'<div class="skeleton skeleton-card"></div>'.repeat(8)}</div>`;
  const d = await api("/api/neural_web/lobes");
  if (!d.ok) { v.innerHTML = nwEmpty("Could not load the lobe map", d.error || "panel error"); return; }
  let html = nwHero(d) + nwSystemMap(d);
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
    not_ready: "s-warn", promotion_eligible: "s-ok", accruing: "s-muted",
  };

  // Count chips — only non-zero states
  const allStates = ["overdue","due","human_review","missing","stale","blocked","not_ready","promotion_eligible","accruing"];
  let chips = allStates
    .filter(s => (by[s] || 0) > 0)
    .map(s => `<span class="statpill ${STATE_CLS[s] || 's-muted'}">${esc(String(by[s] ?? 0))} ${esc(s.replace(/_/g," "))}</span>`)
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
        const stateCls = STATE_CLS[r.state] || "s-muted";
        const cmd = r.regenerate_cmd ? `<code style="font-size:11px">${esc(r.regenerate_cmd)}</code>` : `<span class="muted">—</span>`;
        return `<tr>
          <td><b>${esc(r.clock_id || "")}</b>${r.acknowledged ? ' <span class="statpill s-muted">ack</span>' : ''}</td>
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
  if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; }
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
    <div class="section">Raw Key Usage (rate-limit headers)</div>
    <div class="card" id="metKeysCard"><div class="sub muted">Loading…</div></div>
    <div class="section">Recent Metabolism Runs <span class="cnt">${(d.runs || []).length}</span></div>
    <div class="card">${runsHtml}</div>
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

  // Async Key Usage loader (V10)
  (async () => {
    const keysCard = $("#metKeysCard");
    if (!keysCard) return;
    let ku;
    try {
      ku = await api("/api/metabolism/keys");
    } catch (e) {
      const kc = $("#metKeysCard");
      if (kc) kc.innerHTML = `<div class="sub muted">Could not load key usage: ${esc(String(e))}</div>`;
      return;
    }
    const kc = $("#metKeysCard");
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
    const fmtTokens = (n) => n == null ? "—" : Number(n) >= 1000 ? `${(Number(n)/1000).toFixed(1)}k` : String(n);
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
      return `<tr>
        <td class="mono">${esc(k.key_id || "—")}${presentLabel}</td>
        <td>${enabledLabel}</td>
        <td>${coolLabel}</td>
        <td class="sub mono">${esc(k.reset_hint || "—")}</td>
        <td class="r">${fmtTokens(k.window_5h_est_tokens)} <span class="muted sub">est.</span></td>
        <td class="r">${k.window_5h_sessions != null ? k.window_5h_sessions : "—"}</td>
        <td class="r">${fmtTokens(k.weekly_est_tokens)} <span class="muted sub">est.</span></td>
        <td class="r">${k.weekly_sessions != null ? k.weekly_sessions : "—"}</td>
        <td>${k.last_outcome ? `<span class="statpill ${k.last_outcome === "ok" ? "s-ok" : "s-bad"}">${esc(k.last_outcome)}</span>` : `<span class="muted sub">—</span>`}</td>
        <td style="max-width:320px">${headers}</td>
      </tr>`;
    }).join("")}
    </tbody></table>
    <div class="sub muted" style="margin-top:8px">est. = locally-observed rolling window estimate · reported = Anthropic response header value</div>`;
  })();

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
        return `<div class="empty"><div class="empty-icon">📜</div><div class="empty-text">No autonomous changes recorded yet.</div><div class="empty-sub">This feed fills as the loop runs — PRs authored, audits filed, lobe lifecycle events, and reverts will appear here.</div></div>`;
      }
      return `<div class="timeline">${events.map(ev => {
        const ts = esc((ev.ts || "").slice(0, 16).replace("T", " "));
        const titleLink = ev.url
          ? `${esc(ev.title || "")} <a href="${esc(ev.url)}" target="_blank" rel="noopener">open ↗</a>`
          : esc(ev.title || "");
        const detail = esc(ev.detail || "") + (ev.ref ? " · " + esc(ev.ref) : "");
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

    // Filter state — "all" or a source name.
    let activeFilter = "all";

    const render = (filter) => {
      const card2 = $("#mhCard");
      if (!card2) return;
      const filtered = filter === "all" ? allEvents : allEvents.filter(ev => ev.source === filter);
      const cnt = $("#mhCnt");
      if (cnt) cnt.textContent = filter === "all" ? total : `${filtered.length}/${total}`;

      // Source filter pills.
      const pillsHtml = [
        `<button class="btn" data-mhf="all" style="margin:0 4px 6px 0;font-size:12px;${filter === "all" ? "border:2px solid var(--accent);font-weight:700" : ""}">All ${total}</button>`,
        ...activeSources.map(([src, cnt2]) =>
          `<button class="btn" data-mhf="${esc(src)}" style="margin:0 4px 6px 0;font-size:12px;${filter === src ? "border:2px solid var(--accent);font-weight:700" : ""}">${esc(src)} ${cnt2}</button>`)
      ].join("");

      const phase0Banner = phase0
        ? `<div class="sub muted" style="margin-bottom:10px">The loop is still inert (Phase 0) — only heartbeats and rehearsals appear here. Once armed, autonomous PRs, audits, lobe lifecycle events and reverts will land in this feed.</div>`
        : "";

      // Degradation notes.
      const notes = Object.values(sources).filter(v => v && v.note).map(v => `<div class="sub muted" style="margin-top:8px">${esc(v.note)}</div>`).join("");

      card2.innerHTML = `<div style="margin-bottom:8px">${pillsHtml}</div>${phase0Banner}${mhTimeline(filtered)}${notes}`;

      // Bind filter pills.
      card2.querySelectorAll("[data-mhf]").forEach(el => {
        el.onclick = () => { activeFilter = el.dataset.mhf; render(activeFilter); };
      });
    };

    render(activeFilter);
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
