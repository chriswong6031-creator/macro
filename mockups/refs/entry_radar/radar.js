/* LIVE ENTRY RADAR — W8 reference renderer. Not production. */
(function () {
  const Q = new URLSearchParams(location.search);
  const theme = Q.get("theme") === "light" ? "light" : "dark";
  const lang = Q.get("lang") === "zh" ? "zh" : "en";
  const state = Q.get("state") || "board";
  const lifeF = Q.get("life") || "";
  const laneF = Q.get("lane") || "all";
  const chrome = Q.get("chrome") === "0" ? "0" : "1";
  const openDrawer = Q.get("drawer") === "1";

  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.lang = lang;
  document.documentElement.dataset.chrome = chrome;
  document.documentElement.lang = lang === "zh" ? "zh-Hans" : "en";

  const C = window.RADAR_COPY;
  const FIX = window.RADAR_FIXTURES;
  const STATES = window.RADAR_STATES;
  const META = window.RADAR_META;
  const EXP = window.RADAR_EXPERTS;
  const VLAB = window.RADAR_C2_VARIANT_LABEL;

  function t(node) {
    if (!node) return "";
    return node[lang] || node.en || "";
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function both(en, zh) {
    return `<span class="l-en">${esc(en)}</span><span class="l-zh">${esc(zh)}</span>`;
  }
  function href(extra) {
    const n = new URLSearchParams(Q);
    Object.entries(extra).forEach(([k, v]) => {
      if (v === "" || v == null) n.delete(k);
      else n.set(k, v);
    });
    const s = n.toString();
    return s ? `?${s}` : "?";
  }

  const keys = STATES[state] || STATES.board;
  let rows = keys.map((k) => FIX[k]).filter(Boolean);

  function laneOf(r) {
    const e = EXP[r.expert];
    return e && e.lane ? e.lane : "";
  }
  function isFiringExpert(r) {
    const e = EXP[r.expert];
    return !!(e && e.firing);
  }

  /* C4 must never appear as a row expert */
  rows.forEach((r) => {
    if (r.expert === "C4") throw new Error("C4 cannot be a firing / row expert");
  });

  function inLane(r, lane) {
    if (!lane || lane === "all") return true;
    if (lane === "best") return r.lifecycle === "candidate" && isFiringExpert(r) && !r.stale && !r.unavailable && !r.degraded && !r.raw_basis;
    return laneOf(r) === lane;
  }
  if (lifeF) rows = rows.filter((r) => r.lifecycle === lifeF);
  if (laneF) rows = rows.filter((r) => inLane(r, laneF));

  /* Printed sort is implemented (PRC-002). Live enclosure first, then
     terminal; then expert identity G0→C1→C2→C3→C5; then ticker. */
  const LIFE_ORD = { candidate: 0, pre_candidate: 1, probing: 2, invalidated: 3, expired: 4 };
  const EXP_ORD = { G0: 0, C1: 1, C2: 2, C3: 3, C5: 4 };
  rows.sort((a, b) => {
    const ld = (LIFE_ORD[a.lifecycle] ?? 9) - (LIFE_ORD[b.lifecycle] ?? 9);
    if (ld) return ld;
    const ed = (EXP_ORD[a.expert] ?? 9) - (EXP_ORD[b.expert] ?? 9);
    if (ed) return ed;
    return String(a.ticker).localeCompare(String(b.ticker));
  });

  const counts = {
    probing: 0, pre_candidate: 0, candidate: 0, invalidated: 0, expired: 0,
    g0: 0, c1: 0, c2: 0, c3: 0, c5: 0, best: 0,
  };
  const universe = (STATES[state] || STATES.board).map((k) => FIX[k]).filter(Boolean);
  universe.forEach((r) => {
    if (counts[r.lifecycle] != null) counts[r.lifecycle] += 1;
    const ln = laneOf(r);
    if (ln && counts[ln] != null) counts[ln] += 1;
    if (inLane(r, "best")) counts.best += 1;
  });
  const liveTotal = counts.probing + counts.pre_candidate + counts.candidate;
  /* Quiet is no-candidates, not no-probes. Never force the Probe Set to 0
     while the empty well says the Probe Set can still be live (PRC-001). */
  const probeSet = META.probe_set;

  window.RADAR = {
    theme, lang, state, life: lifeF, lane: laneF,
    rows, counts, liveTotal, probeSet,
    synthetic: true,
    pinned_prophet_merge: META.pinned_prophet_merge,
    pinned_prophet_tree: META.pinned_prophet_tree,
  };

  function spark(vals, r) {
    if (!vals || vals.length < 2) {
      const msg = r && r.stale
        ? both("Path is stale", "路径已过期")
        : both("No path yet", "尚无路径");
      return `<div class="pv-nochart"><span class="pv-nochart-l">${msg}</span></div>`;
    }
    const w = 240, h = 74, p = 4;
    const mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals);
    const span = mx - mn || 1;
    const pts = vals.map((v, i) => {
      const x = p + (i / (vals.length - 1)) * (w - p * 2);
      const y = h - p - ((v - mn) / span) * (h - p * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    return `<div class="pv-chart" aria-hidden="true"><svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}"><polyline fill="none" stroke-width="1.6" points="${pts}"/></svg></div>`;
  }

  function px(r) {
    if (r.price == null) return "—";
    return r.price.toFixed(2);
  }
  function chg(r) {
    if (r.change == null) return { txt: "—", cls: "" };
    const sign = r.change > 0 ? "+" : "";
    return {
      txt: `${sign}${r.change.toFixed(2)}`,
      cls: r.change > 0 ? "up" : r.change < 0 ? "down" : "",
    };
  }
  function tone(r) {
    if (r.stale || r.unavailable || r.degraded || r.raw_basis) return "er-stale";
    if (r.lifecycle === "candidate") return "er-cand";
    if (r.lifecycle === "pre_candidate") return "er-pre";
    if (r.lifecycle === "probing") return "er-probe";
    return "er-term";
  }
  function flags(r) {
    const out = [];
    if (r.stale) out.push("er-stale");
    if (r.unavailable) out.push("er-unav");
    if (r.degraded) out.push("er-degraded");
    if (r.raw_basis) out.push("er-raw");
    /* Featured aura = Best-lane filter. Not a fixture flag of 2 (PRC-004). */
    if (inLane(r, "best")) out.push("pv-featured");
    return out.join(" ");
  }

  function card(r) {
    const life = t(C.life[r.lifecycle]);
    const ch = chg(r);
    const v = r.c2_variant ? VLAB[r.c2_variant] : null;
    const fresh = r.freshness ? t({ en: r.freshness.label_en, zh: r.freshness.label_zh }) : "";
    const why = lang === "zh" ? r.why_candidate_zh : r.why_candidate_en;
    const name = lang === "zh" ? r.name_zh : r.name_en;
    const fsN = (r.false_starts || []).length;
    const sib = (r.siblings || []).length;
    const cls = ["pvcard", tone(r), flags(r)].filter(Boolean).join(" ");
    const hero = spark(r.spark, r);
    return `<article class="${cls}" data-id="${esc(r.id)}" data-ticker="${esc(r.ticker)}"
      data-expert="${esc(r.expert)}" data-expert-id="${esc(r.expert_id)}"
      data-life="${esc(r.lifecycle)}" data-bar="${esc(r.bar_state)}"
      data-c2-variant="${esc(r.c2_variant || "")}"
      data-synthetic="true"
      data-stale="${r.stale ? "1" : "0"}"
      data-unavailable="${r.unavailable ? "1" : "0"}"
      data-degraded="${r.degraded ? "1" : "0"}"
      data-raw-basis="${r.raw_basis ? "1" : "0"}"
      data-c4="${r.c4 ? "context" : "none"}">
      ${hero}
      <div class="pv-ov pv-ovl">
        <span class="pv-stance">
          <span class="pv-axis">${t(C.life_axis)}</span>
          <span class="pv-chip er-lifechip ${r.unavailable ? "pv-chip--unav" : ""}">${esc(life)}</span>
        </span>
        <span class="er-xchip" data-expert="${esc(r.expert)}">
          <span class="pv-axis">${t(C.expert_axis)}</span> ${esc(r.expert)}
        </span>
      </div>
      <div class="pv-ov pv-ovr">
        <span class="pv-quote" data-mock-live="1">
          <span class="nb-px pv-px">${esc(px(r))}</span>
          <span class="nb-chg pv-chg ${ch.cls}">${esc(ch.txt)}</span>
        </span>
      </div>
      <div class="pv-bd">
        <div class="pv-hd">
          <span class="pv-idw">
            <span class="pv-tk">${esc(r.ticker)}</span>
            <span class="pv-nm">${esc(name)}</span>
          </span>
          <span class="pv-pri" tabindex="0"
            data-tip-t-en="${esc(C.pri_label.en)}" data-tip-t-zh="${esc(C.pri_label.zh)}"
            data-tip-en="${esc(C.pri_tip.en)}" data-tip-zh="${esc(C.pri_tip.zh)}">
            <span class="pv-pril">${t(C.pri_label)}</span>
            <span class="pv-prin pv-prin--na" data-priority="accruing">—</span>
          </span>
        </div>
        <div class="pv-mk">
          <span class="pv-mk-i">${esc(lang === "zh" ? r.cohort_zh : r.cohort_en)}</span>
          ${v ? `<span class="pv-mk-i" data-c2-variant="${esc(r.c2_variant)}">${esc(t(v))}</span>` : ""}
          ${r.c4 ? `<span class="er-c4 er-xchip" data-expert="C4" data-role="stratification_only">${t(C.c4_chip)}</span>` : ""}
          ${sib ? `<span class="pv-mk-i" data-siblings="${sib}">${sib + 1} ${both("experts", "位专家")}</span>` : ""}
        </div>
        <div class="pv-life">
          <span class="mx-mark mx-mark--${esc(r.lifecycle)}" aria-hidden="true"></span>
          <span class="pv-life-w">${esc(life)}</span>
          <button type="button" class="er-drawer-btn" aria-expanded="false" data-open="${esc(r.id)}">${both("Why", "为何")}</button>
        </div>
        <div class="er-why">${esc(why)}</div>
        ${fsN ? `<div class="er-fs" data-false-starts="${fsN}">${fsN} ${both("prior false start(s) recorded", "次已记录的假启动")}</div>` : ""}
      </div>
      <div class="pv-zn">
        <span class="pv-znl">${both("Fresh", "新鲜度")}</span>
        <span class="pv-znm">${esc(fresh)}</span>
        <span class="pv-dt fig">${esc(r.asof || "—")}</span>
      </div>
      <div class="er-drawer" id="drawer-${esc(r.id)}" hidden>
        <dl class="er-dl">
          <div><dt>${t(C.drawer.why_here)}</dt><dd>${esc(lang === "zh" ? r.why_probe_zh : r.why_probe_en)}</dd></div>
          <div><dt>${t(C.drawer.why_armed)}</dt><dd>${esc(lang === "zh" ? r.why_armed_zh : r.why_armed_en)}</dd></div>
          <div><dt>${t(C.drawer.why_cand)}</dt><dd>${esc(why)}</dd></div>
          ${v ? `<div><dt>${t(C.drawer.variant)}</dt><dd data-c2-variant="${esc(r.c2_variant)}">${esc(r.c2_variant)} — ${esc(t(v))}</dd></div>` : ""}
          ${r.c4 ? `<div><dt>${t(C.drawer.c4)}</dt><dd data-c4-role="stratification_only">${esc(lang === "zh" ? r.c4.note_zh : r.c4.note_en)}</dd></div>` : ""}
          <div><dt>${t(C.drawer.invalidation)}</dt><dd>${esc(lang === "zh" ? r.invalidation_zh : r.invalidation_en)}</dd></div>
          <div><dt>${t(C.drawer.expiry)}</dt><dd>${esc(lang === "zh" ? r.expiry_zh : r.expiry_en)}</dd></div>
          <div><dt>${t(C.opp_label)}</dt><dd data-opportunity="not_yet_measured">${t(C.opp_none)}</dd></div>
          <div><dt>${t(C.drawer.clocks)}</dt><dd class="er-clocks">
            known_at ${esc(r.known_at || "—")} · as-of ${esc(r.asof || "—")}
          </dd></div>
          ${fsN ? `<div><dt>${t(C.drawer.history)}</dt><dd data-false-starts="${fsN}">${
            r.false_starts.map((f) => esc(lang === "zh" ? f.zh : f.en)).join("<br>")
          }</dd></div>` : ""}
          ${sib ? `<div><dt>${t(C.drawer.siblings)}</dt><dd>${esc(r.siblings.join(", "))}</dd></div>` : ""}
        </dl>
      </div>
    </article>`;
  }

  function cell(id, n, lastLive, term) {
    const pressed = lifeF === id;
    return `<button type="button" class="mx-cell${lastLive ? " mx-cell--last-live" : ""}${term ? " mx-cell--term" : ""}"
      data-life="${id}" aria-pressed="${pressed}" data-zero="${n === 0 ? "1" : "0"}">
      <span class="mx-cap mx-cap--${id}"></span>
      <span class="mx-cell-n fig">${n}</span>
      <span class="mx-cell-l">${t(C.life[id])}</span>
    </button>`;
  }

  function laneBtn(id, n) {
    if (id === "c4") {
      return `<span class="er-lane er-lane--c4" data-lane="c4" data-role="stratification_only" aria-disabled="true">
        ${t(C.c4_chip)}</span>`;
    }
    const label = C.lanes[id];
    /* Best is an unmeasured filter, not a ranked count (PRC-003). */
    const count = id === "best"
      ? `<b class="fig" data-best-unranked="1">—</b>`
      : `<b class="fig">${n}</b>`;
    return `<button type="button" class="er-lane" data-lane="${id}" aria-pressed="${laneF === id}">
      ${t(label)} ${count}</button>`;
  }

  function harness() {
    const states = ["board","quiet","g0","c1","c2","c3","c5","multi","expired","invalidated","history","stale","unavailable","raw","degraded","partial","anon","ipo","lobe"];
    const st = states.map((s) => `<a class="${state === s ? "on" : ""}" href="${href({ state: s })}">${s}</a>`).join("");
    return `<div class="harness" id="harness">
      <strong>Radar W8 ref</strong>
      <div class="harness-g">
        <a class="${theme === "dark" ? "on" : ""}" href="${href({ theme: "dark" })}">dark</a>
        <a class="${theme === "light" ? "on" : ""}" href="${href({ theme: "light" })}">light</a>
        <a class="${lang === "en" ? "on" : ""}" href="${href({ lang: "en" })}">EN</a>
        <a class="${lang === "zh" ? "on" : ""}" href="${href({ lang: "zh" })}">ZH</a>
      </div>
      <div class="harness-g">${st}</div>
    </div>`;
  }

  const showStaleBanner = state === "stale" || state === "degraded" || rows.some((r) => r.stale || r.degraded);
  const degraded = state === "degraded";

  let main = "";
  if (state === "anon") {
    main = `<section class="mx-tier-gate" data-anon="1">
      <div>
        <h2>${t(C.anon_title)}</h2>
        <p>${t(C.anon_body)}</p>
      </div>
      <div>
        <p class="mock-note">${t(C.ref_banner)}</p>
      </div>
    </section>`;
  } else {
    const cards = rows.map(card).join("");
    main = `
      <header class="bh">
        <div class="bh-top">
          <div>
            <h1 class="bh-title">${t(C.title)}</h1>
            <p class="bh-purpose">${t(C.purpose)}</p>
            <p class="er-sister">${t(C.not_prophet)}</p>
          </div>
          <div class="bh-stamp">
            <span class="dtp-token${degraded ? " closed" : ""}">
              <span class="dtp-dot"></span>
              ${esc(lang === "zh" ? META.session_label_zh : META.session_label_en)}
            </span>
            <span class="pbs${degraded ? " pbs--warn" : ""}">${degraded
              ? both("DEGRADED evaluator", "评估器降级")
              : both("SYNTHETIC session", "合成会话")}</span>
            <span class="dtp-asof fig">${esc(META.asof)}</span>
          </div>
        </div>
        <p class="mock-note"><b>${t(C.ref_banner)}</b> — ${esc(lang === "zh" ? META.note_zh : META.note_en)}</p>
        <div class="ladder-block">
          <div class="ladder-headline">
            <span class="ladder-n fig" data-probe-set="${probeSet}">${probeSet}</span>
            <span class="ladder-nl">${both("in the Probe Set", "在探针集中")}</span>
            <span class="ladder-sub">${both(
              `${counts.pre_candidate} pre-candidates · ${counts.candidate} candidates`,
              `${counts.pre_candidate} 预候选 · ${counts.candidate} 候选`
            )}</span>
          </div>
          <div class="mx-ladder" role="toolbar" aria-label="lifecycle">
            ${cell("probing", counts.probing, false, false)}
            ${cell("pre_candidate", counts.pre_candidate, false, false)}
            ${cell("candidate", counts.candidate, true, false)}
            <div class="mx-ladder-gap" aria-hidden="true"></div>
            ${cell("invalidated", counts.invalidated, false, true)}
            ${cell("expired", counts.expired, false, true)}
          </div>
          <div class="ladder-foot">
            <button type="button" class="ladder-clear" data-clear="1">${both("Clear filter", "清除筛选")}</button>
            <span>${both("Live cells are Radar lifecycle, not Prophet plan cells.", "活单元格是雷达生命周期，不是先知计划格。")}</span>
          </div>
        </div>
        <div class="er-lanes" role="toolbar" aria-label="expert lanes">
          ${laneBtn("all", universe.length)}
          ${laneBtn("best", counts.best)}
          ${laneBtn("g0", counts.g0)}
          ${laneBtn("c1", counts.c1)}
          ${laneBtn("c2", counts.c2)}
          ${laneBtn("c3", counts.c3)}
          ${laneBtn("c5", counts.c5)}
          ${laneBtn("c4", 0)}
        </div>
        ${showStaleBanner ? `<div class="er-banner" data-stale-banner="1">${degraded ? t(C.degraded_banner) : t(C.stale_banner)}</div>` : ""}
      </header>
      <section class="mx-sec">
        <div class="mx-sec-hd">
          <h2 class="mx-sec-h2">${both("Episodes", "情节")}</h2>
          <span class="mx-sec-total">${both("Showing", "显示")} <b class="fig">${rows.length}</b></span>
        </div>
        <div class="setups-bar">
          <span class="sort-rule">${both(
            "Sorted by lifecycle (live cells first), then expert identity. No Opportunity rank — W7 has not measured one.",
            "按生命周期（活单元格在前）、再按专家身份排序。没有机会分——W7尚未测量。"
          )}</span>
          <span class="er-pri-board" data-priority-board="accruing">${both(
            "Priority ACCRUING — W6 has not measured a rank.",
            "优先级尚未测量 — W6尚未给出排名。"
          )}</span>
        </div>
        ${rows.length ? `<div class="pv-grid">${cards}</div>` : `<div class="er-empty" data-empty="1">${t(C.empty)}</div>`}
      </section>`;
  }

  document.getElementById("harness").outerHTML = harness();
  document.getElementById("board").innerHTML = main;

  document.querySelectorAll(".mx-cell").forEach((btn) => {
    btn.addEventListener("click", () => {
      location.search = href({ life: btn.dataset.life === lifeF ? "" : btn.dataset.life }).slice(1);
    });
  });
  document.querySelectorAll(".er-lane[data-lane]").forEach((btn) => {
    if (btn.dataset.lane === "c4") return;
    btn.addEventListener("click", () => {
      location.search = href({ lane: btn.dataset.lane }).slice(1);
    });
  });
  const clear = document.querySelector("[data-clear]");
  if (clear) clear.addEventListener("click", () => {
    location.search = href({ life: "", lane: "all" }).slice(1);
  });
  document.querySelectorAll(".er-drawer-btn").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const cardEl = btn.closest(".pvcard");
      const open = !cardEl.classList.contains("is-open");
      document.querySelectorAll(".pvcard.is-open").forEach((c) => {
        c.classList.remove("is-open");
        const d = c.querySelector(".er-drawer");
        if (d) d.hidden = true;
        const b = c.querySelector(".er-drawer-btn");
        if (b) b.setAttribute("aria-expanded", "false");
      });
      if (open) {
        cardEl.classList.add("is-open");
        const d = cardEl.querySelector(".er-drawer");
        if (d) d.hidden = false;
        btn.setAttribute("aria-expanded", "true");
      }
    });
  });
  if (openDrawer) {
    const first = document.querySelector(".er-drawer-btn");
    if (first) first.click();
  }

  /* Sister lens: one language at a time. Never title= (house i18n law). */
  const pop = document.createElement("div");
  pop.className = "lens-pop";
  pop.setAttribute("role", "tooltip");
  document.body.appendChild(pop);
  function lensShow(el) {
    const zh = lang === "zh";
    const title = el.getAttribute(zh ? "data-tip-t-zh" : "data-tip-t-en") || el.getAttribute("data-tip-t-en");
    const body = el.getAttribute(zh ? "data-tip-zh" : "data-tip-en") || el.getAttribute("data-tip-en");
    if (!body) return;
    pop.innerHTML = (title ? `<div class="lens-ttl">${title}</div>` : "") +
                    `<div class="lens-body">${body}</div>`;
    const r = el.getBoundingClientRect();
    pop.style.left = Math.max(10, Math.min(window.innerWidth - 312, r.left - 8)) + "px";
    pop.style.top = (r.bottom + 8) + "px";
    pop.classList.add("open");
  }
  function lensHide() { pop.classList.remove("open"); }
  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-tip-en]"); if (el) lensShow(el);
  });
  document.addEventListener("mouseout", (e) => {
    if (e.target.closest("[data-tip-en]")) lensHide();
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest("[data-tip-en]"); if (el) lensShow(el);
  });
  document.addEventListener("focusout", lensHide);
})();
