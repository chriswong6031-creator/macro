# XPV2-SC-R3A — Lane C Archaeology: Map / Moving / Money producer binding matrix

ROUTE: census. Scope: `templates/sector_central.html.j2` §Map/§Moving/§Money +
their inline/mounted JS, `scripts/build_sector_central.py`, `scripts/build_baskets.py`,
and every payload those three views read. Overview = lane A, Explore = lane D,
Confluence = lane E — noted only as cross-references. No production edits made.

All line numbers are `file:line` in this worktree at HEAD (2026-08-20,
`310283bafe68`). All payload samples read from disk (worktree not sparse for
`site/`/`data/` at time of read) or `git show HEAD:<path>` where noted.

## 0. View boundaries (evidence for scope)

`templates/sector_central.html.j2:2259` `data-view="map"` → `:2371` `data-view="moving"` →
`:2388` `data-view="money"` → `:2424` `data-view="explore"` (out of scope) →
`:2478` `data-view="confluence"` (out of scope). A sixth view, `overview`
(`:2189`, hero/verdict lanes, `act_now` board), sits BEFORE `:2259` and is
**out of scope (lane A)** even though it is not view-gated by a `<section
data-view>` wrapper the same way — it is only reachable via `#overview` and is
the default landing view (`templates/si_workspace.js:17,274`).

Each view (except `confluence`) carries a hidden `<p class="si-view-read"
id="si-read-<view>">` "read strip" (`:2260,2372,2389,2425`) populated by
`templates/si_workspace.js` — a display-tier composer over payloads already on
the page (`si_workspace.js:130-138` doctrine comment: "Nothing here
originates a signal... every line is a re-phrasing of a field the nightly
payload already carries"). These strips are themselves visible fields and are
rows below.

---

## 1. MAP view (`data-view="map"`, `templates/sector_central.html.j2:2259-2369`)

| view | field | producer | path/key | authority | transform | clock | access | destination | state/null behavior |
|---|---|---|---|---|---|---|---|---|---|
| Map | Rotation map (SVG quadrant scatter, `#rvx-rmap`) | `engine.theme_scoring` (theme score/rank) + `engine.narrative_rotation`/`sector_pulse` (`pulse_rank_delta_5d`) via `scripts/build_baskets.py`; client composes via `rvxData()` `sector_central.html.j2:2946-2958` | `basketdata/baskets.json` → `theme_intel.themes[].{score,rank,perf.20d.rel,perf.5d.rel,pulse_rank_delta_5d,reco,category}`; fetched client-side `sector_central.html.j2:3093` (`__siFetch('basketdata/baskets.json')`) | **Context** — explicit label at `:2267`: "Only the lanes above carry a gated, graded call"; quadrant text says Leading/Improving/Weakening/Lagging describe "where a group sits vs the market right now", not an action | Client: `q` (quadrant) derived from `score>=50` and `vel>=0` sign (`:2953`); `vel` falls back to a scaled `r5` when `pulse_rank_delta_5d` is null (`:2952`) | Nightly — `basketdata/baskets.json` is written once per nightly `build_baskets.py` run (cl_baskets lane, `daily.yml`); no intraday/live refresh path in this fetch (`__siFetch`, one-shot, no `setInterval`) | **Accessible equivalent EXISTS**: the linked board below the SVG (`#rvx-board`, `renderRotBoard()` `:3004-3023`) is a full `<a>` list (rank, name, score bar, reco tag, r20%, spark, velocity) reading the SAME `RVX_D` array — a text/table alternative to the chart | If `theme_intel.themes` empty/absent: `rvxData()` returns `[]`; `renderRotationMap()` still draws axes/legend but no dots; `renderRotBoard()` renders empty board + `#rvx-count` = "0 themes" (`:3020`). Whole `boot()` call wrapped `try/catch` (`:3057`) so a JS exception is swallowed silently — no visible error. |
| Map | Linked board (`#rvx-board`, ranked rows with `reco` tag Buy/Add/Hold/Trim/Avoid) | same producer chain as above; `RVX_RECO` client map `:2941-2942` renders `t.reco` verbatim | `theme_intel.themes[].reco` (values: enter/accumulate/hold/trim/avoid per si_handoff sample below) | **Action-shaped display** — `t.reco` values render as "Buy/Add/Hold/Trim/Avoid" (`:2941`) inside a view whose own header text disclaims action authority (`:2267`). This is exactly DAC-002's concern class (see §5) — the label reads as an action tag even though the page copy calls the view context-only. | `reco` passed through unmodified from payload; only a lookup-table relabel (`enter→Buy` etc, `:2941`) | Nightly (same artifact as rotation map) | Table IS the accessible form (no separate chart needed for this element) | `RVX_RECO[d.recoKey]\|\|['—','—']` (`:3008`) — unknown/missing `reco` degrades to an em-dash tag, never an error |
| Map | Sector-cycle clock (`#sc-chart`, lazy-mounted via `LAZY.map=['@cycles']` `si_workspace.js:77`) | `scripts/build_sector_cycles.py` (`engine` cycle-detection; writes `window.SECTOR_CYCLES`) | `site/sector_cycles_data.js` → `window.SECTOR_CYCLES` (core payload); companions `sector_cycles_series_data.js`/`_narr_data.js`/`_dna_data.js` loaded on first sector focus (`si_workspace.js:104-110`) | Context (0-100 cycle-position oscillator; no reco/gate fields observed at the top-level payload in this pass) | Not traced beyond the writer file header (`scripts/build_sector_cycles.py:7`: "site/sector_cycles_data.js -> window.SECTOR_CYCLES only (core, ~2MB)") | Nightly (no separate script confirming an intraday cadence found in this pass — **GAP**, see §6) | **No accessible table equivalent found for the cycle-clock chart itself** in this view; the SVG/line chart (`#sc-chart`) is the only rendering located. **GAP** — did not confirm whether an off-chart per-sector cycle-state text list exists elsewhere on the page. | Not traced to code level (lazy-loaded script `templates/sector_cycles.js` was not opened this pass) — **GAP** |
| Map | "One gated read per sector" board (`#board`, 11 cap-weighted ETFs) | `engine/sector_central.py:compute()` via `scripts/build_sector_central.py:337-338` | `window.SECTOR_CENTRAL` (`site/sector_central_data.js:356-357`) / same data at `site/sectordata/sector_central.json:360-361` | **Action** — server-computed conviction (state→gate→confirm→risk-size chain per `engine/sector_central.py:337-430`, cited in the R2 review DAC-001) | Server-side only (engine); page renders `#board` from `window.SECTOR_CENTRAL` — render function not traced this pass (**GAP**, board-render JS not opened) | Nightly (`build_sector_central.py` runs in the nightly engine job, after `build_baskets.py`) | JSON payload itself is a readable/table-shaped artifact (`site/sectordata/sector_central.json`) — no further accessible-equivalent check performed on the rendered cards | Not traced this pass — **GAP** |

**Map / si-read-map strip**: `si_workspace.js:160-175` `readMap()` reads
`window.__siRvxData()` (the SAME `rvxData()` closure hoisted onto `window` by
`__siInitPage`, `sector_central.html.j2:2534+`) — i.e., it reads the same
`theme_intel.themes` as the map/board above, not a separate artifact. Null
behavior: `if(!d||!d.length) return null` → `paint('map', null)` sets
`el.hidden=true` (`si_workspace.js:218-220`) — strip disappears cleanly, no
error text.

---

## 2. MOVING view (`data-view="moving"`, `templates/sector_central.html.j2:2371-2386`)

| view | field | producer | path/key | authority | transform | clock | access | destination | state/null behavior |
|---|---|---|---|---|---|---|---|---|---|
| Moving | "What's moving" read strip (`#si-read-moving`) | `si_workspace.js:176-188 readMoving()` — composes from `theme_intel.themes[].pulse_rank_delta_5d` (window.BASKETS, i.e. `basketdata/baskets.json`, same producer as Map) | `basketdata/baskets.json` → `theme_intel.themes[].pulse_rank_delta_5d` | Context — receipt text: "Counts how many groups moved up or down this week's ranking... it ranks nothing and gates nothing" (`si_workspace.js:211-212`) | Counts up/down movers from the field's sign only; no new score | Nightly (`build_baskets.py`) | Text-native, is itself the accessible form | `if(!seen) return null` → strip hidden (`:183`, `paint` → `el.hidden=true`); `if(!up&&!dn)` → explicit "quiet tape" sentence (`:184-185`) rather than a blank/zero row |
| Moving | Rotation-events / flow-lane board (`#rc-events-mount`) | `scripts/build_rotation_events.py:5-7,130,173` → `engine.sector_fragmentation` + `engine.rotation_events` | `site/marketdata/sector_fragmentation.json`, `site/marketdata/rotation_events.json`; client fetch `templates/rotation_events.js:492-493` | **Context by page copy** — `sector_central.html.j2:2378` "context lens... ranks nothing, gates nothing, sizes nothing"; render-time caveat in JS itself: "these events don't rank, gate, or size anything" (`rotation_events.js:485-486`) | Client `render()`/`renderFlowLanes()`/`renderClosures()` (not traced field-by-field this pass) | Nightly (`build_rotation_events.py` docstring: "Rotation Command W1 nightly step", registered in `daily.yml` `cl_baskets` lane, `scripts/build_rotation_events.py:16`) | No separate table alternative confirmed beyond the rendered board itself — **GAP** | Both fetches `.catch(()=>null)`; if **both** null: `#rc-events-content` innerHTML = "Rotation-event data unavailable." (`rotation_events.js:495-497`); a JS exception in `.then` is swallowed by outer `.catch` leaving the loading/quiet note in place (`:501`) |
| Moving | Whole-market rotation map (`#rotation-app`, 269 subsectors + Mag-7 composite) | `scripts/build_subsector_rotation.py:1-8` → `engine.subsector_rotation`, reading committed Finviz snapshot `data/themes_heatmap/*.json` (refreshed by `scripts/fetch_finviz_themes.py`) | `site/marketdata/subsector_rotation.json`; client fetch `templates/subsector_rotation.js:260,293` (`var JSON_URL='marketdata/subsector_rotation.json'`) | Context — page header: "measures the speed of relative strength — it ranks nothing, gates nothing and sizes nothing" (`sector_central.html.j2:2378`) | Full render in `render(full)` (quadrant chart + emerging/fading columns); not traced field-by-field this pass | Nightly — writer reads a "committed Finviz themes snapshot," itself refreshed by a separate `fetch_finviz_themes.py` step; **exact refresh cadence of that upstream snapshot not confirmed this pass — GAP** | **Accessible equivalent exists**: `drawStrip()` (`subsector_rotation.js:298-312`) renders emerging/fading chip lists as text (`<a class="srx-chip">` rows) — a compact table-like alternative alongside the map; also `drawTrackRecord()` (`:319+`) is text-native | `.catch()`: `if(full) full.innerHTML='<div class="sr-empty">Could not load rotation data.</div>'` (`subsector_rotation.js:293`) — explicit failure state, not silent |
| Moving | Desk-watch panel (`#desk-watch-mount`) — turn-desk + tape-onset flags | `scripts/oracle_nightly.py` step 15 (Rotation Turn Desk, W6) `:39-42` + step 19 (TAPE-ONSET, FTR W7) `:44` | `site/basketdata/oracle_turn_desk.json` (`oracle_nightly.py:1313,1533`) + sidecar `site/basketdata/oracle_tape_onset.json` (`:1589`); client fetch `templates/desk_watch.js:20-21,373-374` | **Explicitly display-only by producer docstring**: "DISPLAY-ONLY panel" (turn desk, `oracle_nightly.py:39`) and "DISPLAY-ONLY unconfirmed flag" (tape-onset, `:44`) | Client `render()` builds `_footHtml`/`_onsetHtml` — not traced field-by-field this pass | Nightly (`oracle_nightly.py` docstring: "Runs AFTER massive_stock_day in the nightly workflow") | Explicit no-signal quiet-row text is itself the accessible form: "No early flow signs right now — a quiet tape is a valid read." (`desk_watch.js:363-365`) when nothing is flagged | Both fetches `.catch(()=>null)`; render is called with `(null,null)` and (per code read) the panel still renders a shell with the quiet-row sentence rather than a fabricated flag; a hard `.catch` on the `Promise.all` (network-level failure, not per-fetch) instead prints "Desk-watch data unavailable." (`:376-379`) |

### 2a. SPECIAL REQUIREMENT — does Moving bind to `si_handoff.json`?

**VERDICT: NO — refuted by code.** `si_handoff.json` has exactly one writer
and one reader in the whole repo:

- Writer: `scripts/build_baskets.py:590-597` —
  ```
  (fdir / "si_handoff.json").write_text(json.dumps({
      "theme_context": _theme_context,
      "factor_season": factor_season,
      "flow": ({"cluster": {"regime": ...}} if (flow or {}).get("cluster") else None),
      "basket_member_syms": _member_syms,
      "generated_utc": built,
  }, ...))
  ```
  (confirmed by `grep -rn si_handoff scripts engine templates tests` → only
  `scripts/build_baskets.py:586,590` and `scripts/build_sector_central.py:380`
  match anywhere in the repo.)
- Reader: `scripts/build_sector_central.py:379-384` reads
  `site/basketdata/si_handoff.json` **server-side, at build time** (not a
  client fetch) and passes its four keys into the Jinja render call
  (`:444-453`): `theme_context=ctx.get("theme_context")`,
  `factor_season=ctx.get("factor_season")`, `flow=ctx.get("flow")`,
  `basket_member_syms=ctx.get("basket_member_syms")`.
- Template consumption of those four vars, by view:
  - `theme_context` / `factor_season` → **Overview hero only**
    (`sector_central.html.j2:2110-2220`, all BEFORE `data-view="map"` opens at
    `:2259`) — out of scope, lane A.
  - `flow` → **Money view only**: `sector_central.html.j2:2389`
    `<p class="si-view-read" id="si-read-money" ... {% if flow ... %} data-regime="{{ flow.cluster.regime | e }}" {% endif %}>` — this is the ONE si_handoff field that reaches an in-scope view, and it is Money, not Moving.
  - `basket_member_syms` → Explore view member-symbol registry (`:2470-2474`) — out of scope, lane D.
  - `generated_utc` → footer only.

Grepping the Moving-view JS files themselves for `si_handoff` (`rotation_events.js`,
`subsector_rotation.js`, `desk_watch.js`) returns zero matches. Moving's five
mounted sub-surfaces read `marketdata/rotation_events.json`,
`marketdata/sector_fragmentation.json`, `marketdata/subsector_rotation.json`,
`basketdata/oracle_turn_desk.json`, `basketdata/oracle_tape_onset.json` — none
of which is `si_handoff.json` or a renamed successor of it. Moving's own
`si-read-moving` composer (`si_workspace.js:176-188`) reads `theme_intel`
inside `basketdata/baskets.json` — a sibling artifact `build_baskets.py` also
writes, but a structurally different file from `si_handoff.json` (baskets.json
carries the full basket/theme corpus + chart matrix; si_handoff carries only
the four hero/money/explore keys above).

**If the commissioning brief's premise was that Moving binds to si_handoff**,
that premise does not hold against current code. The artifact that DOES bind
to si_handoff in an in-scope view is **Money** (`flow.cluster.regime`, one
field). This is reported as a refutation, not forced into agreement — see
Deviations.

---

## 3. MONEY view (`data-view="money"`, `templates/sector_central.html.j2:2388-2422`)

| view | field | producer | path/key | authority | transform | clock | access | destination | state/null behavior |
|---|---|---|---|---|---|---|---|---|---|
| Money | Money read strip (`#si-read-money`, data-regime attr) | `scripts/build_baskets.py` (writes `flow.cluster.regime` into si_handoff) → `scripts/build_sector_central.py:450` (passes `flow=ctx.get("flow")` into Jinja) → template sets `data-regime` (`:2389`) → `si_workspace.js:189-200 readMoney(el)` reads the DOM attribute back out | `basketdata/si_handoff.json` → `flow.cluster.regime` (values seen on disk: `"broad"`, `git show HEAD:site/basketdata/si_handoff.json` → `"flow":{"cluster":{"regime":"broad"}}`) | Context — phrasing lifted verbatim to match the money-flow card (`si_workspace.js:191`); receipt: "Restates the money-flow reading shown on the breadth card below... Display only." (`:213-214`) | `EN[r]`/`ZH[r]` lookup table over `concentrated/broad/mixed` (`:192-197`); unknown value → `return null` | Nightly (`build_baskets.py`, server-side render — this value is BAKED INTO THE HTML at build time via the `data-regime` attribute, not re-fetched client-side) | Text-native | `if(!r) return null` (attr absent) or `if(!EN[r]) return null` (unknown value) → `paint('money',null)` → strip hidden (`si_workspace.js:220`) |
| Money | Money-flow verdict card (`.rvx-gcard` "Money flow", `#mf-etf-chips`/`#mf-vol-chip`) | template-side: same `flow.cluster.regime` server var, rendered directly (not via JS) at `:2400-2404`; chips populated client-side from separate artifacts | `flow.cluster.regime` (server Jinja, `:2401-2403` `FLOW_V_EN/FLOW_V_ZH` map) for the headline text; `basketdata/etf_pulse.json` (fetch `:2824`) for `#mf-etf-chips`; `basketdata/vol_sentiment.json` (fetch `:2845`) for `#mf-vol-chip` | Context (verdict phrasing: "Crowding into a few" / "Spread across many" / "No single group leads") | Server: dict lookup on `flow.cluster.regime`; client: `#mf-etf-chips`/`#mf-vol-chip` renderers not traced field-by-field this pass (**GAP**) | Headline: nightly (baked server-side). Chips: nightly artifacts (`basketdata/etf_pulse.json`, `basketdata/vol_sentiment.json`) fetched client-side once at page load (`__siFetch`-style one-shot fetches, `:2824,2845` — `cache:'no-store'`, no `setInterval` found) | Table/text is the native form already (no chart) | Template: `{% if flow is defined and flow and flow.cluster %}...{% else %}<div id="mkt-flow">—</div>{% endif %}` (`:2400-2404`) — absent `flow` degrades server-side to a static em-dash placeholder, never a client error |
| Money | Market breadth gcards (`#mkt-breadth`, `#mkt-ad`, `#mkt-hilo`, `#mkt-above` + sub-labels + minibars) | `engine` producer of `theme_intel.market_concentration` inside `build_baskets.py` (writer not traced to the exact `engine.*` module computing `market_concentration` this pass — **GAP**); client `renderInternals()` `sector_central.html.j2:3034-3052` | `basketdata/baskets.json` → `theme_intel.market_concentration.{verdict,adv,dec,ad_ratio,nh,nl,pct_above_200}` (comment at `:3034`: "Market internals (breadth) from THEME.market_concentration") | Context (breadth description, not a buy/sell call) | Bar widths / color thresholds computed client-side (`:3041-3051`, e.g. `pct_above_200>=60` → "healthy majority" bucket) | Nightly (same `basketdata/baskets.json` fetch as Map, one-shot) | Each metric is itself a number/ratio (text), not a chart — no separate accessible form needed | Per-field `if(mc.X!=null)` guards (`:3043,3046,3049`) — a missing sub-field leaves that one gcard at its static `—` placeholder (`:2395-2398` server default) rather than a fabricated zero; whole `renderInternals()` wrapped in `try/catch` at `boot()` (`:3058`) |
| Money | Sector-ETF flow board table (`#sc-flows`, server-rendered HTML block) | `scripts/build_sector_central.py:263-328 _flows_section_html()` → `collectors.sponsors.sector_flow_periods()` | Server-computed HTML string `flows_html`, injected `{% if flows_html %}{{ flows_html|safe }}{% endif %}` (`sector_central.html.j2:2411`) | Context — note text: "Display-only." (`build_sector_central.py:314-317`) | Full table built server-side (1D/3D/1W/2W/1M windows, per-ETF + net row) | Nightly (`build_sector_central.py` main(), same run that writes `sector_central_data.js`) | Table is itself the accessible form (already a `<table>`, no chart) | `if not data or not data.get("rows"): return None` (`:272-273`) → `flows_html=None` → whole section omitted from the page (`:2411` `{% if flows_html %}`) — no placeholder shown at all |
| Money | Market-heat treemap (`#heatmap-scorecard`) | `scripts/build_sp500_heatmap.py:123,475-477` | `site/marketdata/sp500_heatmap.json`; client fetch/poll `templates/heatmap.js:28,45-61` | Context — page copy: "Coincident color (display context, capped in the read above)" (`sector_central.html.j2:2415`) | Client colors computed from live CSS theme tokens (`heatmap.js:19-20`); tiles sized by market cap | **Nightly baseline + intraday/live splice**: docstring "offline-safe daily-close snapshot; splices a live 1D when a feed is connected" (`heatmap.js:18-19`); `startAutoRefresh()` (`:45-61`) polls the same URL on a `setInterval`, applying a fresh payload only when `fresh.generated_utc !== cur.generated_utc` — this is the **only live/polling clock found among Map/Moving/Money's payloads** in this pass | Full treemap only; no separate text/table alternative for `#heatmap-scorecard` located this pass (**GAP** — the standalone `#heatmap-full` page may have one; not checked) | Auto-refresh guards on `document.hidden` (skips refresh in background tab, `:49`) and on stale/missing `generated_utc` (`:55`, `if (!fresh.generated_utc \|\| fresh.generated_utc === cur.generated_utc) return` — a **KNOWN-TRAP-shaped guard**: this is an absolute-stamp comparison, not a baked delta, so it does not fall into the "freshness delta frozen forever" trap named in the commission) | Not traced further this pass |
| Money | Index-leadership strip (`#scc-leadership`) | `scripts/build_index_leadership.py` (per in-template comment `sector_central.html.j2:3439`) | `site/marketdata/index_leadership.json`; client fetch `sector_central.html.j2:~3521` (`fetch('marketdata/index_leadership.json',{cache:'no-cache'})`) | Mixed — "Forward track record" sub-line explicitly labels itself "Validated / Measuring / Accruing" (`:3460-3464`), i.e., a self-graded calibration note attached to a context strip, not a gate | `leadershipStrip(d)` builds hero (rising star / leader now) + comparison table across subsectors/nasdaq/russell/baskets tabs (`:3475-3499`) | Nightly (writer not opened this pass to confirm cadence beyond filename convention — **GAP**) | Table (`.lead-tbl`, `:3497`) is itself the accessible form for the leadership comparison | `.then(r=>r.ok?r.json():null).catch(()=>null).then(leadershipStrip)`; `leadershipStrip`: `if(!d||!d.ok){el.innerHTML='';return;}` (`:3477`) — empty string + `.lead-wrap:empty{display:none}` CSS (`:1005`) means an absent/not-ok payload makes the ENTIRE strip vanish from layout, not just show empty |

---

## 4. Payload → writer index (every artifact named above)

| payload | writer script(s) | engine module (where identified) | cadence evidence |
|---|---|---|---|
| `site/basketdata/baskets.json` (`theme_intel.themes[]`, `theme_intel.market_concentration`, `theme_intel.act_now`) | `scripts/build_baskets.py:413` | theme scoring pipeline feeding `data["theme_intel"]` (module not isolated this pass — **GAP**) | nightly, `cl_baskets` lane |
| `site/basketdata/si_handoff.json` | `scripts/build_baskets.py:590-597` | n/a (assembled from already-computed `_theme_context`/`factor_season`/`flow`) | nightly, written after `theme_context` compute (`:566-571`) in the same `build_baskets.py` run |
| `site/sector_central_data.js` / `site/sectordata/sector_central.json` | `scripts/build_sector_central.py:356-361` | `engine/sector_central.py:compute()` (`:337-338`) | nightly, engine job, after `build_baskets.py` |
| `site/marketdata/rotation_events.json`, `site/marketdata/sector_fragmentation.json` | `scripts/build_rotation_events.py:130,173` | `engine.sector_fragmentation`, `engine.rotation_events` (`:5-7`) | nightly, `cl_baskets` lane (`:16`) |
| `site/marketdata/subsector_rotation.json` | `scripts/build_subsector_rotation.py:335-336` | `engine.subsector_rotation` (`:20`) | nightly; source is a committed Finviz snapshot refreshed by a separate `scripts/fetch_finviz_themes.py` step — **upstream cadence of that refresh not confirmed (GAP)** |
| `site/basketdata/oracle_turn_desk.json`, `site/basketdata/oracle_tape_onset.json` | `scripts/oracle_nightly.py:1313/1533,1589` | (oracle nightly pipeline, steps 15/19, `:39-44`) | nightly, "runs AFTER massive_stock_day in the nightly workflow" (`:3`) |
| `site/marketdata/sp500_heatmap.json` | `scripts/build_sp500_heatmap.py:475-477` | (heatmap assembly, `:429`) | nightly baseline + **client-side polled live splice** (`templates/heatmap.js:45-61`) — the one live/intraday clock found in Map/Moving/Money |
| `site/marketdata/index_leadership.json` | `scripts/build_index_leadership.py` (per in-template citation only; file not opened this pass — **GAP**) | not confirmed | not confirmed — **GAP** |
| `site/basketdata/etf_pulse.json`, `site/basketdata/vol_sentiment.json` | not traced to writer this pass (comment at `sector_central.html.j2:2182` names `basketdata/{etf_pulse,vol_sentiment,theme_extension}.json via theme_addons.js`; writer referenced elsewhere as `scripts/build_theme_addons.py`, `build_baskets.py:417-419`) | — | nightly, subsidiary to `build_baskets.py` |

---

## 5. Critic claims (DAC-*) checked against code this pass

Source: `research/reference_integrity/mastermind-xpv2-turn3-r2/reviews/data_authority.md`
(critic identity `codex-xpv2-data-authority-20260820`, verdict BLOCK on the R2
freeze candidate — a DIFFERENT artifact than the current production template
audited here). These findings are about the **R2 mockup**, not current
production; production `sector_central.html.j2`/`build_sector_central.py`
were audited independently above and are NOT shown to reproduce the blocked
behavior — reported as leads confirmed/refuted against the mockup's own
citations, not re-litigated against production:

- **DAC-002** (Health Care context→action promotion): the critic's own
  canonical citation, `site/basketdata/si_handoff.json` → `theme_intel` (its
  wording) `us_sector_health` `reco: hold`, is confirmed on disk in THIS
  pass — the live artifact today (`theme_context.themes.us_sector_health`)
  reads `"reco":"hold","score":77,"rank":6"` (§ payload sample above,
  2026-08-19 as_of). Matches the critic's citation. **CONFIRMED** as of this
  read.
- **DAC-001/DAC-003 pattern (context relabeled as action)**: structurally the
  SAME pattern exists in current production's own Map board — `theme_intel.themes[].reco`
  values (`enter/accumulate/hold/trim/avoid`) render through `RVX_RECO`
  (`sector_central.html.j2:2941-2942`) as **Buy/Add/Hold/Trim/Avoid** tags
  inside a view whose header explicitly disclaims action authority
  (`:2267`, "Only the lanes above carry a gated, graded call"). This is not a
  DAC-* row from the cited review (which targeted the R2 mockup's *Explore*
  tab), but the same class of finding recurs in current Map production — flagged
  here as a lead for the adjudicating deliverable, not adjudicated by this
  census.
- Other DAC rows (004/005/006, confluence-lane) are **out of scope** (Explore/Confluence, lanes D/E) and not checked.

---

## 6. GAPS (explicit — not converted to negative claims)

1. `#board` (Map, "one gated read per sector") render function not opened —
   field-by-field binding from `window.SECTOR_CENTRAL` to the rendered card
   not traced.
2. `templates/sector_cycles.js` (cycle-clock chart renderer, lazy-loaded)
   not opened — could not confirm (a) an accessible text equivalent for
   `#sc-chart` beyond the SVG, (b) intraday vs nightly-only refresh.
3. `scripts/build_index_leadership.py` not opened — writer citation is the
   in-template comment only (`sector_central.html.j2:3439`); cadence not
   independently confirmed.
4. Exact `engine.*` module computing `theme_intel.market_concentration`
   (Money breadth gcards) not isolated — confirmed only that
   `build_baskets.py` writes it into `data["theme_intel"]` before
   `baskets.json` is serialized (`:413`).
5. Writers of `basketdata/etf_pulse.json` / `basketdata/vol_sentiment.json`
   named only via an in-template comment (`:2182`) and via
   `build_baskets.py:417-419`'s "theme_addons" sub-build reference; not opened
   directly.
6. Upstream refresh cadence of `data/themes_heatmap/*.json` (the Finviz
   snapshot `subsector_rotation.json` is built from) — `scripts/fetch_finviz_themes.py`
   not opened.
7. `#heatmap-scorecard`'s accessible text/table alternative (if any) not
   located within Money-view scope; the standalone `#heatmap-full` page was
   not checked for one.
8. `#mf-etf-chips`/`#mf-vol-chip` client renderers (Money) not traced
   field-by-field.
9. `#rc-events-mount` (`rotation_events.js` `render()`/`renderFlowLanes()`/`renderClosures()`)
   not traced field-by-field for individual sub-fields beyond the top-level
   null/quiet behavior.

## 7. DEVIATIONS

None from the assigned SCOPE. One finding deviates from the commission's
stated PREMISE: the SPECIAL REQUIREMENT presupposed Moving binds to
`si_handoff.json`; code shows Money (not Moving) is the in-scope view that
binds to it, via exactly one field (`flow.cluster.regime`). Reported as a
refutation with full citation trail (§2a) rather than forced into agreement,
per this worker's instructions to distinguish VERIFIED from INFERENCE and
never manufacture a match the evidence does not support.
