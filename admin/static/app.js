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
};
const NAV_GROUPS = [
  { label: "", items: [["overview", "Overview"]] },
  { label: "Neural Web", items: [["neural_web", "Observatory"], ["alerts", "Alerts"]] },
  { label: "Growth", items: [["analytics", "Analytics"], ["users", "Users"], ["experiments", "Experiments"]] },
  { label: "System", items: [["system", "System"], ["health", "Health"], ["deploy", "Build & Deploy"], ["cost", "AI Cost"], ["content", "Content"]] },
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
    <table><thead><tr><th>Experiment</th><th>Type</th><th>Status</th><th>How often</th><th class="r">Come back</th><th>Next step</th><th>Your action</th></tr></thead><tbody>
    ${exps.map(e => `<tr${e.ready ? ' class="hl"' : ""}>
      <td><b>${esc(e.name)}</b><div class="sub">${esc(e.what || "")}</div><div class="note mono muted">${esc(e.source || "")}</div></td>
      <td class="sub">${esc(e.kind || "")}</td>
      <td>${EXP_STATUS_PILL(e.status)}</td>
      <td class="sub">${esc(e.cadence || "")}</td>
      <td class="r">${EXP_DUE(e)}</td>
      <td class="sub" style="max-width:340px">${esc(e.next_step || "")}${e.state ? `<div class="note mono muted">${esc(e.state)}</div>` : ""}</td>
      <td style="white-space:nowrap">
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
  </div>`;
}
/* Signature system map — core → group anchors (on a ring) → lobe nodes */
function nwSystemMap(d) {
  const groups = (d.groups || []).filter(g => g.lobes && g.lobes.length);
  if (!groups.length) return "";
  const W = 900, H = 480, cx = W / 2, cy = H / 2, R = 155;
  const N = groups.length;
  let edges = "", ganchors = "", lnodes = "", labels = "";
  groups.forEach((g, gi) => {
    const ang = -Math.PI / 2 + gi * 2 * Math.PI / N;
    const gx = cx + R * Math.cos(ang), gy = cy + R * Math.sin(ang);
    edges += `<line class="map-edge" x1="${cx}" y1="${cy}" x2="${gx.toFixed(1)}" y2="${gy.toFixed(1)}" style="stroke-width:1.6"/>`;
    ganchors += `<circle cx="${gx.toFixed(1)}" cy="${gy.toFixed(1)}" r="7" style="fill:var(--grp-${g.key});opacity:.9"/>`;
    const lx = cx + (R + 34) * Math.cos(ang), ly = cy + (R + 34) * Math.sin(ang);
    labels += `<text class="map-label" x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle">${esc(g.label)} · ${g.lobes.length}</text>`;
    const m = g.lobes.length, lr = Math.min(48, 14 + m * 2.2);
    g.lobes.forEach((l, li) => {
      const a2 = li * 2 * Math.PI / m;
      const nx = gx + lr * Math.cos(a2), ny = gy + lr * Math.sin(a2);
      const stt = l.status === "fresh" ? "fresh" : l.status === "stale" ? "stale" : (l.status === "missing" || l.status === "degraded") ? "missing" : "stale";
      edges += `<line class="map-edge" x1="${gx.toFixed(1)}" y1="${gy.toFixed(1)}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}"/>`;
      lnodes += `<circle class="map-node" data-lobe="${esc(l.id)}" data-status="${stt}" cx="${nx.toFixed(1)}" cy="${ny.toFixed(1)}" r="4.2" style="fill:var(--grp-${g.key})"></circle>`;
    });
  });
  return `<div class="systemmap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Neural Web system map">
    <defs><linearGradient id="nw-core-grad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#6a8dff"/><stop offset="1" stop-color="#38e0d4"/></linearGradient></defs>
    ${edges}${ganchors}${lnodes}${labels}
    <text x="${cx}" y="${cy - 42}" text-anchor="middle" class="map-label" style="fill:var(--text);font-size:12px;font-weight:600">Neural Web</text>
    <circle class="map-core" cx="${cx}" cy="${cy}" r="30"/>
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
async function loadLegacyOps() {
  const box = $("#nw-legacy"); if (!box) return;
  const d = await api("/api/neural_web");
  if (!d || !d.ok) { box.innerHTML = nwEmpty("Diagnostic panel unavailable", (d && d.error) || ""); return; }
  box.innerHTML = `
    ${nwCollapse("engine_health", "A — System health", nwSectionEngineHealth(d.engine_health), false)}
    ${nwCollapse("reflex_log", "B — Automatic reactions", nwSectionReflexLog(d.reflex_log), false)}
    ${nwCollapse("bus_graph", "C — How signals agree &amp; disagree", nwSectionBusGraph(d.bus_graph), false)}
    ${nwCollapse("governance", "D — Permissions &amp; change log", nwSectionGovernance(d.governance), false)}
    ${nwCollapse("factor_intelligence", "E — Factor intelligence (what a stock's move is made of)", nwSectionFactorIntelligence(d.factor_intelligence), false)}`;
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

/* ---- boot --------------------------------------------------------------- */
async function boot() {
  renderSidebar();
  await refresh();
  route();
}
(async function init() {
  SESSION = await fetch("/api/session").then(r => r.json()).catch(() => ({ auth_enabled: false, authenticated: true }));
  if (SESSION.auth_enabled && !SESSION.authenticated) { showLogin(); return; }
  hideLogin(); boot();
})();
