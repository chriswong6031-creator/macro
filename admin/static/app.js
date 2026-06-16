"use strict";
/* Macro Admin — single-page UI. Vanilla JS, no external deps (works offline). */

const $ = (sel, el = document) => el.querySelector(sel);
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtAge = (hrs) => hrs == null ? "—" : hrs < 1 ? `${Math.round(hrs * 60)}m` : hrs < 48 ? `${hrs.toFixed(0)}h` : `${(hrs / 24).toFixed(0)}d`;
const fmtUSD = (n) => n == null ? "—" : "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({ error: "bad json" }));
  return j;
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

let TOAST_T;
function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast show" + (err ? " err" : "");
  clearTimeout(TOAST_T); TOAST_T = setTimeout(() => t.className = "toast", 2600);
}

const TABS = [
  ["overview", "Overview"], ["features", "Features"], ["brief", "AI Brief"],
  ["traffic", "Traffic"], ["deploy", "Build & Deploy"], ["health", "Health"],
  ["cost", "AI Cost"], ["content", "Content"],
];
let CURRENT = "overview";
let SUMMARY = null;
let RT_TIMER = null;

function renderTabs() {
  const nav = $("#tabs"); nav.innerHTML = "";
  TABS.forEach(([id, label]) => {
    const b = h(`<button data-tab="${id}">${label}</button>`);
    if (id === CURRENT) b.classList.add("active");
    b.onclick = () => go(id);
    nav.appendChild(b);
  });
}

function go(id) {
  CURRENT = id;
  if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; }
  renderTabs();
  RENDER[id]();
}

/* ---- header + banner ---------------------------------------------------- */
function renderHeader() {
  const m = SUMMARY.meta || {};
  const hh = SUMMARY.health || {};
  const led = hh.healthy ? "ok" : (hh.broad_outage || (hh.sources && hh.sources.dead) ? "bad" : "warn");
  const el = $("#hmeta");
  el.innerHTML = "";
  el.appendChild(h(`<span class="pill"><span class="led ${led}"></span>${hh.healthy ? "Healthy" : "Attention"}</span>`));
  el.appendChild(h(`<span>repo <code>${esc(m.repo || "?")}</code></span>`));
  el.appendChild(h(`<span>token ${m.has_token ? "✓" : "✗"}</span>`));
  el.appendChild(h(`<span>GA ${m.ga_configured ? "✓ live" : "tag-only"}</span>`));
  if (m.site_url) el.appendChild(h(`<a href="${esc(m.site_url)}" target="_blank" rel="noopener">live site ↗</a>`));
}

function renderBanner() {
  const g = SUMMARY.git || {};
  const b = $("#banner");
  if (!g.config_dirty) { b.className = "banner"; b.innerHTML = ""; return; }
  b.className = "banner show";
  b.innerHTML = `<span>⚠︎ <b>config.yml changed</b> in the working tree — not live until committed to <code>main</code> and rebuilt.</span>`;
  const sp = h(`<span class="spacer"></span>`); b.appendChild(sp);
  const commit = h(`<button class="btn">Commit locally</button>`);
  commit.onclick = () => doCommit(false);
  b.appendChild(commit);
  if (g.can_push_live) {
    const cp = h(`<button class="btn primary">Commit &amp; push to main</button>`);
    cp.onclick = () => doCommit(true);
    b.appendChild(cp);
  } else {
    b.appendChild(h(`<span class="sub">on <code>${esc(g.branch || "?")}</code> — push from a main checkout to go live</span>`));
  }
}

async function doCommit(push) {
  if (push && !confirm("Commit config.yml and PUSH to the live branch? This will reach the deploy pipeline on the next build.")) return;
  const r = await post("/api/git/commit", { push, confirm: true });
  if (r.ok) { toast(r.pushed ? "Committed & pushed" : "Committed locally" + (r.warning ? " (" + r.warning + ")" : "")); await refresh(); }
  else toast(r.error || "commit failed", true);
}

/* ---- refresh ------------------------------------------------------------ */
async function refresh() {
  SUMMARY = await api("/api/summary");
  if (SUMMARY.error) { toast(SUMMARY.error, true); return; }
  renderHeader(); renderBanner();
}

/* ---- OVERVIEW ----------------------------------------------------------- */
function card(title, bodyHtml) { return `<div class="card"><h3>${title}</h3>${bodyHtml}</div>`; }

const RENDER = {};
RENDER.overview = async () => {
  const v = $("#view");
  const s = SUMMARY, hh = s.health || {}, br = s.brief || {}, c = s.cost || {};
  const flagsOn = Object.values((s.flags && s.flags.groups) || {}).flat().filter(f => f.value === true).length;
  const flagsTot = Object.values((s.flags && s.flags.groups) || {}).flat().length;
  const mb = br.master_brain || {};
  v.innerHTML = `
    <div class="grid">
      ${card("Pipeline", `<div class="big">${hh.healthy ? "Healthy" : "Attention"}</div>
        <div class="sub">last run ${fmtAge(hh.age_hours)} ago · ${(hh.sources || {}).ok || 0}/${(hh.sources || {}).total || 0} sources ok${(hh.sources || {}).dead ? ` · <span style="color:var(--bad)">${hh.sources.dead} dead</span>` : ""}</div>`)}
      ${card("AI Brief", `<div class="big">${mb.enabled ? "On" : "Off"}</div>
        <div class="sub">every ${mb.interval_days || 1} day(s) · ${(mb.lenses || []).length} lenses${mb.translate_zh ? " · 中文" : ""}</div>`)}
      ${card("Est. AI cost", `<div class="big">${fmtUSD(c.monthly_usd)}<span class="sub"> /mo</span></div>
        <div class="sub">${fmtUSD(c.effective_daily_usd)}/day effective</div>`)}
      ${card("Features on", `<div class="big">${flagsOn}<span class="sub"> / ${flagsTot}</span></div>
        <div class="sub">managed feature flags</div>`)}
    </div>
    <div class="section">Quick actions</div>
    <div id="qa"></div>`;
  const qa = $("#qa");
  const rebuild = h(`<button class="btn primary">▶ Rebuild &amp; deploy now</button>`);
  rebuild.onclick = () => dispatch("daily.yml");
  rebuild.disabled = !(s.meta && s.meta.has_token);
  qa.appendChild(rebuild);
  const redeploy = h(`<button class="btn" style="margin-left:8px">⟳ Redeploy site only</button>`);
  redeploy.onclick = () => dispatch("pages.yml");
  redeploy.disabled = !(s.meta && s.meta.has_token);
  qa.appendChild(redeploy);
  if (!(s.meta && s.meta.has_token)) qa.appendChild(h(`<div class="sub" style="margin-top:8px">Set <code>GH_TOKEN</code> (Actions: write) in <code>.env</code> to enable rebuild/deploy from here.</div>`));
};

/* ---- FEATURES ----------------------------------------------------------- */
RENDER.features = async () => {
  const v = $("#view");
  const data = await api("/api/flags");
  let html = `<div class="sub" style="margin-bottom:12px">Toggle features in <code>config.yml</code>. Changes edit the working tree immediately and go live on the next build (commit + rebuild from the banner / Build tab).</div>`;
  data.order.forEach(cat => {
    html += `<div class="section">${esc(cat)} <span class="cnt">${data.groups[cat].length}</span></div><div id="g-${cat.replace(/\W/g, "")}"></div>`;
  });
  v.innerHTML = html;
  data.order.forEach(cat => {
    const box = $("#g-" + cat.replace(/\W/g, ""));
    data.groups[cat].forEach(f => box.appendChild(flagRow(f)));
  });
};

function flagRow(f) {
  const row = h(`<div class="row"></div>`);
  const sw = h(`<label class="switch"><input type="checkbox" ${f.value ? "checked" : ""}><span class="slider"></span></label>`);
  const cb = sw.querySelector("input");
  cb.onchange = async () => {
    const r = await post("/api/flags/toggle", { path: f.path, value: cb.checked });
    if (r.ok) { toast(`${f.label} → ${r.new}`); await refresh(); renderBanner(); refreshRowTags(row, f, cb.checked); }
    else { cb.checked = !cb.checked; toast(r.error || "toggle failed", true); }
  };
  row.appendChild(sw);
  const txt = h(`<div><div class="lab">${esc(f.label)} ${f.master ? '<span class="tag master">kill-switch</span>' : ""} <span class="rowtags"></span></div><div class="note">${esc(f.note)} <code class="muted">${esc(f.path)}</code></div></div>`);
  row.appendChild(txt);
  refreshRowTags(row, f, f.value === true);
  return row;
}
function refreshRowTags(row, f, on) {
  const box = row.querySelector(".rowtags"); if (!box) return;
  box.innerHTML = "";
  if (on && f.missing_secrets && f.missing_secrets.length)
    box.appendChild(h(`<span class="tag inert" title="ON but required secret missing — no effect">⚠ needs ${esc(f.missing_secrets.join(", "))}</span>`));
}

/* ---- AI BRIEF ----------------------------------------------------------- */
RENDER.brief = async () => {
  const v = $("#view");
  const d = await api("/api/brief");
  const mb = d.master_brain, ad = d.ai_desk;
  const intervalSel = (target, cur) => `<select data-int="${target}" data-prev="${cur}">${[1, 2, 3, 4, 5, 6, 7].map(n => `<option value="${n}" ${n === cur ? "selected" : ""}>every ${n} day${n > 1 ? "s" : ""}</option>`).join("")}</select>`;
  v.innerHTML = `
    ${!d.deepseek_key ? `<div class="banner show" style="position:static">⚠︎ <code>DEEPSEEK_API_KEY</code> is not set — briefs are a no-op even when enabled.</div>` : ""}
    <div class="section">AI Daily Brief (Master Brain)</div>
    <div class="row"><label class="switch"><input type="checkbox" id="mbEn" ${mb.enabled ? "checked" : ""}><span class="slider"></span></label>
      <div><div class="lab">Generate the morning briefs</div><div class="note">${(mb.lenses || []).join(", ")} · model <code>${esc(mb.model || "?")}</code></div></div>
      <span class="spacer"></span>${intervalSel("master_brain", mb.interval_days)}</div>
    <div class="row"><label class="switch"><input type="checkbox" id="mbZh" ${mb.translate_zh ? "checked" : ""}><span class="slider"></span></label>
      <div><div class="lab">Chinese translation (中文)</div><div class="note">extra cheap LLM pass per brief</div></div></div>
    <div class="section">Last generated <span class="cnt">per lens</span></div>
    <table><thead><tr><th>Lens</th><th>Generated</th><th class="r">Age</th><th>Model</th><th>Status</th></tr></thead><tbody>
      ${(mb.items || []).map(it => `<tr><td><b>${esc(it.lens)}</b></td><td class="mono">${esc((it.generated_at || "—").replace("T", " ").slice(0, 16))}</td>
        <td class="r">${it.age_days == null ? "—" : it.age_days + "d"}</td><td class="mono">${esc(it.model || "—")}</td>
        <td>${it.degraded_reason ? `<span class="statpill s-warn">${esc(it.degraded_reason)}</span>` : `<span class="statpill s-ok">ok</span>`}</td></tr>`).join("")}
    </tbody></table>
    <div class="section">AI Desk (accountable analyst)</div>
    <div class="row"><label class="switch"><input type="checkbox" id="adEn" ${ad.enabled ? "checked" : ""}><span class="slider"></span></label>
      <div><div class="lab">Generate the desk note</div><div class="note">${ad.panel_enabled ? "4-analyst panel" : "single analyst"} · last ${ad.age_days == null ? "—" : ad.age_days + "d ago"} · ${ad.theses} theses</div></div>
      <span class="spacer"></span>${intervalSel("ai_desk", ad.interval_days)}</div>`;

  $("#mbEn").onchange = (e) => toggleFlag("master_brain.enabled", e.target.checked, "AI Brief");
  $("#mbZh").onchange = (e) => toggleFlag("master_brain.translate_zh", e.target.checked, "中文 translation");
  $("#adEn").onchange = (e) => toggleFlag("ai_desk.enabled", e.target.checked, "AI Desk");
  v.querySelectorAll("[data-int]").forEach(sel => sel.onchange = async () => {
    const prev = sel.dataset.prev;
    const r = await post("/api/brief/interval", { target: sel.dataset.int, days: Number(sel.value) });
    if (r.ok) { sel.dataset.prev = String(r.new); toast(`${sel.dataset.int} → every ${r.new} day(s)`); await refresh(); renderBanner(); }
    else { sel.value = prev; toast(r.error || "failed", true); }   // revert UI on save failure
  });
};
async function toggleFlag(path, value, label) {
  const r = await post("/api/flags/toggle", { path, value });
  if (r.ok) { toast(`${label} → ${r.new}`); await refresh(); renderBanner(); }
  else toast(r.error || "failed", true);
}

/* ---- TRAFFIC ------------------------------------------------------------ */
RENDER.traffic = async () => {
  const v = $("#view");
  const st = await api("/api/traffic");
  if (!st.configured) {
    v.innerHTML = `
      <div class="grid">
        ${card("Data tag", `<div class="big">Live</div><div class="sub">measurement id <code>${esc(st.measurement_id)}</code> on every page</div>`)}
        ${card("Reading traffic", `<div class="big" style="color:var(--warn)">Not connected</div><div class="sub">${esc(st.reason || "needs a service account")}</div>`)}
      </div>
      <div class="section">Connect live traffic + real-time users</div>
      <div class="card"><ol class="steps">${(st.setup_steps || []).map(s => `<li>${esc(s)}</li>`).join("")}</ol></div>
      <div class="card" style="margin-top:12px"><h3>China</h3><div class="sub">${esc(st.china_note)}</div></div>`;
    return;
  }
  v.innerHTML = `
    <div class="grid">
      ${card("Active users now", `<div class="big" id="rtUsers">…</div><div class="sub">last 30 min · auto-refresh</div>`)}
      ${card("Sessions (7d)", `<div class="big" id="rep7s">…</div><div class="sub" id="rep7u"></div>`)}
      ${card("Pageviews (7d)", `<div class="big" id="rep7v">…</div><div class="sub">property <code>${esc(st.property_id)}</code></div>`)}
    </div>
    <div class="grid" style="margin-top:14px">
      <div class="card"><h3>Top pages (7d)</h3><div id="topPages" class="sub">loading…</div></div>
      <div class="card"><h3>Top countries (7d)</h3><div id="topCountries" class="sub">loading…</div></div>
      <div class="card"><h3>Active now by country</h3><div id="rtCountries" class="sub">loading…</div></div>
    </div>`;
  const pollRT = async () => {
    // self-cancel if the user left the Traffic tab (so a stale interval can't throw)
    if (CURRENT !== "traffic" || !$("#rtUsers")) { if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; } return; }
    const rt = await api("/api/traffic/realtime");
    const el = $("#rtUsers"); if (!el || CURRENT !== "traffic") return;   // re-check after await
    el.textContent = rt.ok ? rt.active_users : "—";
    const cc = $("#rtCountries");
    if (rt.ok && cc) cc.innerHTML = (rt.by_country || []).map(c => `<div class="kv"><span>${esc(c.country)}</span><b>${c.active}</b></div>`).join("") || "<span class='muted'>none</span>";
  };
  if (RT_TIMER) { clearInterval(RT_TIMER); RT_TIMER = null; }
  RT_TIMER = setInterval(pollRT, 15000);   // assign the handle BEFORE the first await
  pollRT();
  const rep = await api("/api/traffic/report?days=7");
  if (rep.ok) {
    $("#rep7s").textContent = rep.summary.sessions.toLocaleString();
    $("#rep7u").textContent = rep.summary.users.toLocaleString() + " users · " + rep.summary.new_users.toLocaleString() + " new";
    $("#rep7v").textContent = rep.summary.pageviews.toLocaleString();
    $("#topPages").innerHTML = rep.top_pages.map(p => `<div class="kv"><span class="mono">${esc(p.path)}</span><b>${p.views}</b></div>`).join("");
    $("#topCountries").innerHTML = rep.top_countries.map(c => `<div class="kv"><span>${esc(c.country)}</span><b>${c.users}</b></div>`).join("");
  }
};

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
  const c = r.conclusion;
  const cls = c === "success" ? "s-ok" : (c === "failure" || c === "timed_out") ? "s-bad" : "s-mut";
  return `<span class="statpill ${cls}">${esc(c || "?")}</span>`;
};
RENDER.deploy = async () => {
  const v = $("#view");
  const hasTok = SUMMARY.meta && SUMMARY.meta.has_token;
  v.innerHTML = `
    <div id="depActions"></div>
    <div class="section">Recent workflow runs</div>
    <div id="runs"><div class="spin">loading…</div></div>`;
  const a = $("#depActions");
  [["daily.yml", "▶ Rebuild & deploy", "primary"], ["pages.yml", "⟳ Redeploy site only", ""], ["weekly.yml", "↻ Weekly deep build", ""]].forEach(([wf, label, cls]) => {
    const b = h(`<button class="btn ${cls}" style="margin-right:8px">${label}</button>`);
    b.disabled = !hasTok; b.onclick = () => dispatch(wf);
    a.appendChild(b);
  });
  if (!hasTok) a.appendChild(h(`<div class="sub" style="margin-top:8px">Set <code>GH_TOKEN</code> (Actions: write) in <code>.env</code> to trigger runs. (Run status below works without a token on a public repo.)</div>`));
  const data = await api("/api/deploy");
  const runs = $("#runs");
  if (!data.ok) { runs.innerHTML = `<div class="card sub">Could not load runs: ${esc(data.error || "?")}</div>`; return; }
  runs.innerHTML = `<table><thead><tr><th>Workflow</th><th>Event</th><th>Status</th><th>Branch</th><th>Started</th><th></th></tr></thead><tbody>
    ${data.runs.map(r => `<tr><td><b>${esc(r.workflow || r.name)}</b></td><td class="sub">${esc(r.event)}</td><td>${STATUS_PILL(r)}</td>
      <td class="mono">${esc(r.branch)}</td><td class="sub mono">${esc((r.run_started_at || r.created_at || "").replace("T", " ").slice(0, 16))}</td>
      <td><a href="${esc(r.html_url)}" target="_blank" rel="noopener">open ↗</a></td></tr>`).join("")}
  </tbody></table>`;
};

/* ---- HEALTH ------------------------------------------------------------- */
RENDER.health = async () => {
  const v = $("#view");
  const d = await api("/api/health");
  if (d.error) { v.innerHTML = card("Error", `<div class="sub" style="color:var(--bad)">${esc(d.error)}</div>`); return; }
  const src = d.sources || {};
  const sp = (s) => `<span class="statpill ${s === "ok" ? "s-ok" : s === "stale" ? "s-warn" : s === "dead" ? "s-bad" : "s-mut"}">${esc(s)}</span>`;
  v.innerHTML = `
    <div class="grid">
      ${card("Pipeline", `<div class="big" style="color:${d.healthy ? "var(--ok)" : "var(--warn)"}">${d.healthy ? "Healthy" : "Attention"}</div><div class="sub">last run ${fmtAge(d.age_hours)} ago${d.stale ? " · STALE" : ""}</div>`)}
      ${card("Sources", `<div class="big">${src.ok}/${src.total}</div><div class="sub">${src.stale} stale · ${src.dead} dead</div>`)}
      ${card("Circuit breakers", `<div class="big" style="color:${d.broad_outage ? "var(--bad)" : "var(--text)"}">${d.breaker_tripped}</div><div class="sub">tripped${d.broad_outage ? " · BROAD OUTAGE" : ""}</div>`)}
    </div>
    <div class="section">Dashboard freshness</div>
    <div class="grid">${(d.markets || []).map(m => `<div class="card"><h3>${esc(m.label)}</h3><div class="big" style="font-size:18px">${m.exists ? fmtAge(m.age_hours) + " ago" : "<span style='color:var(--bad)'>missing</span>"}</div><div class="sub">${esc(m.date || "")}</div></div>`).join("")}</div>
    <div class="section">Data sources <span class="cnt">${(d.source_rows || []).length}</span></div>
    <table><thead><tr><th>Source</th><th>Status</th><th class="r">Rows</th><th>Last date</th><th class="r">Breaker</th><th>Error</th></tr></thead><tbody>
      ${(d.source_rows || []).map(s => `<tr><td class="mono">${esc(s.name)}</td><td>${sp(s.status)}</td><td class="r">${s.rows ?? "—"}</td>
        <td class="mono sub">${esc(s.last_date || "—")}</td><td class="r">${s.breaker || 0}</td><td class="sub" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(s.error || "")}">${esc(s.error || "")}</td></tr>`).join("")}
    </tbody></table>`;
};

/* ---- AI COST ------------------------------------------------------------ */
RENDER.cost = async () => {
  const v = $("#view");
  const d = await api("/api/cost");
  if (d.error) { v.innerHTML = card("Error", `<div class="sub" style="color:var(--bad)">${esc(d.error)}</div>`); return; }
  const r = d.realized || {};
  v.innerHTML = `
    <div class="grid">
      ${card("Est. monthly", `<div class="big">${fmtUSD(d.monthly_usd)}</div><div class="sub">~${d.assumptions.build_days_per_month} build-days/mo</div>`)}
      ${card("Per build", `<div class="big">${fmtUSD(d.per_build_usd)}</div><div class="sub">${fmtUSD(d.effective_daily_usd)}/day effective</div>`)}
      ${card("Realized", `<div class="big">${r.stockbrief_files || 0}</div><div class="sub">stock briefs · ${r.ai_desk_theses_logged || 0} theses logged</div>`)}
    </div>
    ${!d.deepseek_key ? `<div class="card sub" style="margin-top:12px;color:var(--warn)">DEEPSEEK_API_KEY not set — actual spend is $0 (briefs are a no-op).</div>` : ""}
    <div class="section">Components</div>
    <table><thead><tr><th>Component</th><th>On</th><th>Model</th><th class="r">Calls/build</th><th class="r">$/build</th><th>Cadence</th></tr></thead><tbody>
      ${(d.components || []).map(c => `<tr><td><b>${esc(c.name)}</b><div class="sub">${esc(c.note)}</div></td>
        <td>${c.enabled ? "<span class='statpill s-ok'>yes</span>" : "<span class='statpill s-mut'>no</span>"}</td>
        <td class="mono">${esc(c.model)}</td><td class="r">${c.calls_per_build}</td><td class="r">${fmtUSD(c.cost_per_build)}</td>
        <td class="sub">every ${c.interval_days}d</td></tr>`).join("")}
    </tbody></table>
    <div class="section">Monthly cost vs brief interval</div>
    <div class="card"><div class="sub" style="margin-bottom:8px">If you set the Master Brain + AI Desk interval to N days (per-stock briefs stay daily):</div>
    <table><thead><tr><th>Interval</th><th class="r">Est. monthly</th></tr></thead><tbody>
      ${(d.savings_by_interval || []).map(s => `<tr><td>every ${s.interval} day${s.interval > 1 ? "s" : ""}</td><td class="r">${fmtUSD(s.monthly_usd)}</td></tr>`).join("")}
    </tbody></table></div>
    <div class="card sub" style="margin-top:12px">⚠︎ ${esc(d.assumptions.disclaimer)}</div>`;
};

/* ---- CONTENT ------------------------------------------------------------ */
RENDER.content = async () => {
  const v = $("#view");
  const d = await api("/api/content");
  v.innerHTML = `
    <div class="grid">
      ${card("Pages", `<div class="big">${d.total_pages}</div><div class="sub">deployed *.html</div>`)}
      ${card("Total size", `<div class="big">${d.total_mb} MB</div><div class="sub">${d.total_kb} KB</div>`)}
      ${card("Checks", `<div id="upBox"><button class="btn" id="upBtn">Probe live site</button></div>`)}
      ${card("Links", `<div id="lkBox"><button class="btn" id="lkBtn">Check internal links</button></div>`)}
    </div>
    <div class="section">All pages <span class="cnt">${d.total_pages}</span></div>
    <table><thead><tr><th>Page</th><th class="r">Size (KB)</th><th class="r">Updated</th></tr></thead><tbody>
      ${d.pages.map(p => `<tr><td class="mono">${esc(p.name)}</td><td class="r">${p.kb}</td><td class="r sub">${fmtAge(p.age_hours)} ago</td></tr>`).join("")}
    </tbody></table>`;
  $("#upBtn").onclick = async () => {
    $("#upBox").innerHTML = "<span class='muted'>probing…</span>";
    const u = await api("/api/uptime");
    $("#upBox").innerHTML = u.ok ? `<div class="big" style="font-size:18px;color:var(--ok)">200 OK</div><div class="sub">${u.ms} ms · ${(u.bytes / 1024).toFixed(0)} KB</div>`
      : `<div class="big" style="font-size:18px;color:var(--bad)">${u.status || "down"}</div><div class="sub">${esc(u.error || "")}</div>`;
  };
  $("#lkBtn").onclick = async () => {
    $("#lkBox").innerHTML = "<span class='muted'>scanning…</span>";
    const l = await api("/api/content/links");
    $("#lkBox").innerHTML = `<div class="big" style="font-size:18px;color:${l.count ? "var(--warn)" : "var(--ok)"}">${l.count} broken</div><div class="sub">${l.checked_pages} pages · .html nav links in local site/</div>`;
    if (l.count) {
      const sec = h(`<div></div>`);
      sec.innerHTML = `<div class="section">Broken internal links <span class="cnt">${l.count}</span></div>
        <table><thead><tr><th>Page</th><th>Link</th></tr></thead><tbody>${l.broken.map(b => `<tr><td class="mono">${esc(b.page)}</td><td class="mono" style="color:var(--bad)">${esc(b.link)}</td></tr>`).join("")}</tbody></table>`;
      $("#view").appendChild(sec);
    }
  };
};

/* ---- boot --------------------------------------------------------------- */
(async function boot() {
  renderTabs();
  await refresh();
  go("overview");
})();
