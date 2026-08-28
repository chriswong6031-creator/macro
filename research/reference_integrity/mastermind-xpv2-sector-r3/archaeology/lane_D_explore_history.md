# XPV2-SC-R3A — Lane D census: Sector Central (US) Explore/history

Scope: `templates/sector_central.html.j2` Explore view (`data-view="explore"`, lines
2424-2476) + its JS + payloads + producers. Overview (lane A), Map/Moving/Money
(lane C), Confluence (lane E) are out of scope; cited only where load-bearing to an
Explore capability (e.g. self-grader's DOM location).

Route/router context: `templates/si_workspace.js` is the SI Workspace V2 hash
router — six views `['overview','map','moving','money','explore','confluence']`
(si_workspace.js:16). `LEGACY_ANCHORS` (si_workspace.js:36-63) resolves every
pre-V2 deep link; the explore-relevant rows are `'explore-section':['explore',...]`,
`'table-section'`, `'chart-section'`, `'forming-narratives'`, `'tm-mount'`
(si_workspace.js:52-56). The Explore view lazy-loads `subsector_rotation.js` +
`time_machine.js` on first open (si_workspace.js:75, `LAZY.explore`).

---

## 1. Search / filter

Location: `templates/sector_central.html.j2:2437-2438` (table controls),
`:2450-2452` (chart controls).

Controls, all **client-side JS** operating on an already-fetched payload (no
server round-trip per filter action):

- **Mode tabs** (`#btbl-mode`, raw / vs S&P / σ) — `renderTabs` wired at
  `:3059`; state var `btblMode` (`:2601`), persisted to
  `localStorage['fw-btbl-mode']`.
- **Category chips** (`#btbl-cat-filter`) — `renderBTableCats()` (`:2607-2612`)
  builds one chip per `BASKETS.categories` (from the fetched payload, see §2);
  clicking sets `btblCat` and re-renders (`:2611`).
- **Column-header sort** — every `<th data-c>` is clickable (`:2695-2697`);
  toggles `btblSort={col,dir}`, persisted to `localStorage['fw-btbl-sort']`.
- **Chart range picker** (`#chart-ranges`) — buttons `3M/6M/YTD/1Y/All` plus a
  free-text "N days" `<input type=number>` (`:3063`), state `chartRange`
  persisted to `localStorage['fw-brange']`.
- **Chart mode/legend toggles** (`#chart-modes`) — raw vs vs-S&P; legend
  entries toggle basket visibility (`hidden{}` map, `:2702`).

There is **no free-text search box** on the Explore table (confirmed: no
`type="search"`/`placeholder=...search...` input in the file except the chart's
numeric "N days" field, `:3063`). Filtering is exclusively mode/category/sort/
range, all build-free (pure client JS over the fetched JSON — nothing here is
baked per-filter at build time).

Row click is also a "destination filter": `.bname[data-id]` rows navigate to
`basket/<id>.html` (`:2698`) — see §9.

## 2. The full table

Location: `#btable` inside `#table-section` (`:2432-2443`); rendering:
`renderBTable()` (`:2654-2699`).

- **Columns**: `Basket` name, optional `Group pulse` (GR1, only when the
  nightly artifact carries it — `:2620-2634,2675`), a `60d` sparkline, then
  `1d/5d/20d/60d/MTD/YTD` (`TBL_COLS`, `:2557`) formatted as raw %, vs-S&P %,
  or σ per the active mode. A synthetic `S&P 500` benchmark row is appended in
  raw mode (`:2686-2687`).
- **Row source**: `Object.entries(CHART.baskets)` joined to
  `BASKETS.baskets` by `id` (`:2655-2656`) — both live inside the SAME fetched
  object, `window.BASKETS` (see §3 for the payload).
- **Order**: default sort `20d` descending (`btblSort` default
  `{col:'20d',dir:-1}`, `:2602`); "Group pulse" sort is a disclosed rule
  (state-change → breadth → agreement, never a composite score —
  `:2664-2666,2692-2694`, "R-TIL-3" cited in-code). At rest only top-8 +
  bottom-8 render (`TABLE_SHOW=8`, `:2605,2667-2671`), with a "Show all"
  button revealing all 49 baskets (`btblShowAll`).
- **Producer**: `scripts/build_baskets.py` writes `site/basketdata/baskets.json`
  (confirmed live on disk, 49 baskets, 15 categories — see §3). The Explore
  table does **not** read `window.SECTOR_CENTRAL`/`sectordata/sector_central.json`
  (the build-time-embedded engine.sector_central payload) — it is entirely a
  client fetch of the baskets artifact.
- **Null/empty**: a cell with no return prints `—` (`.muted`, `:2680`); the
  fetch failure path replaces `#actnow` (not `#btable`) with a "data failed to
  load" message (`:3093`) — the Explore table itself has no visible
  fetch-failure state distinct from staying an empty `<table>` (the R2 review's
  PRC-007 concern about missing loading/error states is corroborated for this
  specific table: `sector_central.html.j2` has no `#btable`-scoped error
  branch).

## 3. The performance chart

Location: `#chart` / `#chart-legend` inside `#chart-section`
(`:2445-2455`); rendering: `renderChart()` (`:2731-2778`) via
`lightweight-charts.js` (loaded `:2531`).

- **Data source**: `CHART = payload.chart` (`:2536`), the `chart` key of the
  SAME `basketdata/baskets.json` fetch as the table (`chart: {dates, bench,
  baskets}` — confirmed on disk: `site/basketdata/baskets.json['chart'].keys()
  == ['dates','bench','baskets']`). Lines are rebased to 0% at the visible
  window start (`:2748`); "All" covers whatever history the cache holds.
- **Producer**: `scripts/build_baskets.py` (same producer as §2 — table and
  chart are two views of one fetched artifact, so they cannot drift from each
  other, only from the artifact's own staleness).
- **Accessible equivalent**: none in-DOM. The chart is an SVG/canvas rendered
  by `lightweight-charts.js`; the only textual equivalent is the `#chart-legend`
  entries and the table itself (§2), which carries the same numbers in text
  form for the same baskets. There is no `<table>`-only fallback or `aria-label`
  summary for the chart panel found in the template.
- **Deferred-mount defect note** (documented in-code, not a capability gap):
  `:2731-2740` — the chart cannot be created while `#chart` is `display:none`
  (measured 0px-wide bug, 2026-08-04); `renderChart()` sets `_chartDeferred`
  and a `si:view` event re-fires it once Explore is actually shown
  (`:3073-3076`).

## 4. Time Machine

Location: mount point `<div id="tm-mount"></div>` (`:2463`), lazy-loaded by
`si_workspace.js` (`LAZY.explore`, `:75`); logic in `templates/time_machine.js`
(1037 lines), copied to `site/time_machine.js` by `build_sector_central.py`
(asset-copy loop, `scripts/build_sector_central.py:469-482`).

- **What it is**: "the Rotation Time Machine" (`time_machine.js:1`) — a replay
  of measured historical sector/subsector/theme/factor rotation state
  ("No predictive claim — this replays measured history.", `time_machine.js:16`).
  Extracted from the retired standalone `subsector_rotation.html.j2`
  (`time_machine.js:3-5`) as part of the "Time Machine → EXPLORE, collapsed +
  lazy" masterplan move. It renders via `window.SRR` (exported by
  `subsector_rotation.js`, which the LAZY table therefore lists as a
  co-dependency, `si_workspace.js:75`).
- **Data source**: `BASE='oracledata/'`; fetches `oracledata/tm_manifest.json`
  and `oracledata/tm_episodes.json` (`time_machine.js:21-23,341-346`), then
  lazily fetches per-year chunk files (`tm_s_<YYYY-Qn>.json`,
  `tm_m_<YYYYMmm>.json`, `tm_f_<YYYY-Qn>.json` — confirmed present under
  `site/oracledata/`, quarterly factor chunks visible back to `2013Q2`).
- **Producer**: `scripts/build_oracle_timemachine.py` ("Oracle P6 — Time
  Machine feed exporter", docstring lines 1-13) reads pre-built Oracle parquet
  panels (`panel_s`, `panel_m`, `episodes_s`, `episodes_m`) via
  `engine/oracle/timemachine.py` and emits the JSON feed under
  `site/oracledata/`. It explicitly **runs OFF the 67-minute render path**
  ("Wire it into your nightly Mac cron or run manually after a panel rebuild",
  docstring lines 14-15) — a separately scheduled/manual lane, not part of
  `build_sector_central.py`'s own run.
- **Journey**: `<details>`-collapsed shell mounted at load; nothing fetched
  until first open (`time_machine.js:12-14`); unit toggle
  (sectors/subsectors/themes/factors), year chips, per-frame SVG rotation map
  with trail buffers, crosshair tooltip, keyboard nav, and preset playlists
  driven by the episode feed (`_buildPresets`/`_activatePreset`,
  `time_machine.js:888-946`). A live "shock note" overlay additionally fetches
  `live/shock_state.json` (`time_machine.js:277-279`).

## 5. Forming Narratives — classification (settled)

Location: `{% include "_forming_narratives.html.j2" %}` inside the Explore
view (`sector_central.html.j2:2464`); template `templates/_forming_narratives.html.j2`
(12 lines); logic `templates/forming_narratives.js` (211 lines, shared across
US/China/HK/Canada/Intl baskets pages).

- **Producer**: `engine/narrative_emergence.py::compute_emergence()` (called
  by the baskets builder pipeline that writes `basketdata/narrative_emergence.json`
  — read client-side, `forming_narratives.js:167`, `base + 'narrative_emergence.json'`,
  default base `basketdata/`).
- **VERDICT — display-tier commentary layered on a deterministic score,
  compliant with A7 ("LLM never originates signals/scores"):**
  - The **score** (0-100, `_emergence_score`, `engine/narrative_emergence.py:179-180`)
    and its 5 legs (`tighten/cohesion/momentum/novelty/size`, `:165-176`) are a
    **transparent fixed-weight formula** (`_W = {tighten:.40, cohesion:.30,
    momentum:.12, novelty:.10, size:.08}`, `:44`) over statistics computed by
    `engine.theme_discovery` (co-movement + change-point detection, `:236-237`)
    — **no LLM involvement**. Recommended tickers are ranked by a deterministic
    `_ENTRY_RANK` table over `engine.extension` grades (`:183-208`), again no
    LLM.
  - The **one** LLM-originated field is `ai_watch` — "The AI thematic desk's
    ONE emerging_watch hypothesis... A graded, checkable WATCH — never a buy"
    (`_ai_watch`, `:121-131`), sourced from `site/allocationdata/ai_desk_<region>.json`,
    itself produced by `engine/thematic_desk.py`, whose docstring states
    plainly: **"LLM = DeepSeek via engine.master_brain._call_model"**
    (`engine/thematic_desk.py:27`) — an "accountable LLM reasoning layer" that
    turns "the deterministic narrative_rotation state into a SHORT set" of
    theses plus at most one `emerging_watch` hypothesis
    (`thematic_desk.py:8,267`).
  - This LLM text is printed **verbatim as prose** in the "🧭 AI scout watch"
    line (`forming_narratives.js:149-151`) — it does **not** feed the 0-100
    score, the leg bars, the ticker ranking, or any gate/lane placement. A
    2026-07-27 operator ruling (#3821) additionally forced the LABEL (not the
    condition text) to be rewritten at read time from falsifier register
    ("Kill criterion: X") to a display-safe "Watching for: X" before it
    reaches a user cycle surface (`narrative_emergence.py:99-118`,
    `_watch_register`).
  - **Conclusion**: Forming Narratives is **model-analysis-ASSISTED display
    commentary, not model-originated scoring**. The card's ranking/score
    machinery is deterministic statistics; the one LLM sentence is optional,
    absent when the gated desk didn't run (`_ai_watch` returns `None` — live
    on disk today, `site/basketdata/narrative_emergence.json['ai_watch'] ==
    None`, as_of 2026-08-19), and is disclosed as a "watch," never a signal.
    This satisfies A7 as written ("LLM never originates signals/scores... may
    only de-escalate calibrated keys"): the LLM here originates neither a
    score nor an escalation, only optional watch-prose. R2's required repair
    #9 ("analysis-labelled Forming Narratives") is therefore a labeling/UI
    requirement (make the LLM provenance visible to the reader), not evidence
    the current panel is out of policy.
  - **Caveat text on the panel itself already discloses non-predictiveness**:
    "Scores rank narrative formation, not expected return. A noisy watchlist
    lens — not a buy list." (`forming_narratives.js:173`); `_caveats()`
    (`narrative_emergence.py:211-227`) adds three more standing caveats
    plus conditional ones (IPO wave, stretched share, macro-attention
    alignment).
- **Null/empty**: panel `display:none`s itself when `narrative_emergence.json`
  is absent or has zero narratives (`forming_narratives.js:170`) — silent, no
  error surfaced (self-contained, safe-to-always-include by design).
- **Access**: `basketdata/narrative_emergence.json` is **not** under the
  `/premiumdata/` prefix — free (see §8).

## 6. Track Record

Two distinct things carry this name on the estate; only one is
Explore-scoped.

**(a) The Sector Central self-grader — this page's own track record** (DOM id
`#grader`, `sector_central.html.j2:2206`, inside the `actnow-section` of the
**Overview** view, `LEGACY_ANCHORS['grader'] → ['overview','grader']`,
`si_workspace.js:41`). Flagged here because R2's product-regression review
groups it with the Explore/history requirement set ("The ledger requires the
Explore table, performance chart, Time Machine, Forming Narratives, and Track
Record", `product_regression.md:70`) even though it does not physically sit
in the `data-view="explore"` section.
  - **Source ledger**: `data/sector_central/calls.parquet`, append-only,
    keep-FIRST per `(date, id)` (`engine/sector_central_grader.py:6-8`).
  - **Who advances it**: `append_central_log(data)` — gated by
    `engine.ledger_lane.nightly_advance_enabled()` (imported
    `engine/sector_central_grader.py:25`, checked `:109`) — **nightly-only**,
    consistent with the house law "nightly is the sole advancer of forward
    ledgers." `grade()` (`:220`) then joins matured calls to realized forward
    returns (SPDR close for sectors, PIT-frozen equal-weight basket level for
    baskets — `_basket_levels()`, `:42-59`, explicitly using the frozen
    `data/basket_levels/us.parquet` "to kill the look-ahead / survivorship
    leak").
  - **What it displays**: `renderGrader()` (`sector_central.html.j2:3387-3405`)
    — by horizon (21d/63d/126d): directional hit-rate, rank-IC, mean excess
    vs SPY, broken out by conviction tier when available. Live on disk today
    (`site/sectordata/sector_central.json['grader']`): `available: true,
    n_calls: 2134`, `21d: {n:187, dir_hit_rate:0.187, rank_ic:-0.1587,
    mean_excess_vs_bench:-0.0049}`, `63d`/`126d` both `{n:0, note:'accruing'}`.
    Sparse-state copy: "Accruing — dated calls are logged and will be graded
    against realized forward returns as time passes (N calls logged)."
    (`:3389-3391`). Doc-level guarantee: "the log is NEVER read back into a
    live score" (`engine/sector_central_grader.py:15`).
  - **Producer/embed**: `scripts/build_sector_central.py:348-354` calls
    `cg.append_central_log(data)` then attaches `data["grader"] = cg.grade()`;
    this rides the SAME build-time-embedded `window.SECTOR_CENTRAL` object
    (`sector_central_data.js`, synchronous `<script data-sync>` at
    `sector_central.html.j2:3134`) that also drives the Overview cycle/regime
    reads — i.e. **build-time embed, not a client fetch** (unlike Explore's
    table/chart, which fetch `basketdata/baskets.json`).

**(b) "Forward track record" badge** — inside the Money & Breadth (lane C,
out of scope) "Index leadership rotation" module (`trackBox()`,
`sector_central.html.j2:3463`, reading `d.track_record`). Named for
completeness only; not part of Lane D.

## 7. Self-grader / receipt surface

Same artifact as §6(a) — `#grader` / `renderGrader()`. No separate
Explore-scoped self-grader or "receipt" surface was found inside
`data-view="explore"` itself; Forming Narratives and Time Machine carry their
own inline disclosure/caveat text (§4, §5) instead of a scored receipt.
The single explicit self-grading receipt for this page's conviction calls is
the Overview-mounted `#grader` scorecard described in §6(a).

## 8. Access state (free vs premium) — traced end-to-end

- **Page shell**: `sector_central.html` is served to anonymous visitors
  (house-wide 2026-08-04 change removing the HTML registration wall,
  `config/site_access.yml:6-10`). "The paid product is the PAYLOAD, not the
  page" (`config/site_access.yml:19-25`).
- **`/premiumdata/` prefix is 403'd early for anonymous AND Free**
  (`config/site_access.yml:635,648`, `enforced_early.prefixes: [/premiumdata/,
  /capital-structure-data/]`).
- **Sector Central's own premium payload**: `site/premiumdata/sector_central.json`,
  written unconditionally every build by `write_payload()`
  (`scripts/build_sector_central.py:136-167`), holds the withheld Act-Now
  board rows beyond `preview_rows` (`_gate_cfg`, `:77-88`; `split_actnow`,
  `:91-133`). Live on disk today: `schema: tier_payload.v1, gated: true,
  required_tier: essential, panels.actnow: {preview:3, locked:29, total:44}`.
  This gate applies **only to the Act-Now board**, which lives in the
  **Overview** view — confirmed by grep: `pgate` never appears inside the
  `data-view="explore"` section (`:2424-2476`), only around the Act-Now
  include (`:3-11,53,3533-3612`) and its shared partial
  `templates/_us_act_now_board.html.j2:53,64`.
- **Explore's own payloads are NOT under `/premiumdata/`** and are therefore
  free to any account that can load the page (no per-path entry found for
  `basketdata/`, `oracledata/`, or `chinabasketdata/` prefixes in
  `config/site_access.yml`'s `enforced_early`/`public` lists — grep returned
  no hits): `basketdata/baskets.json` (table+chart, §2-3),
  `basketdata/narrative_emergence.json` (Forming Narratives, §5),
  `oracledata/tm_manifest.json`/`tm_episodes.json`/chunk files (Time Machine,
  §4). Whether an anonymous (unregistered) visitor can fetch these XHRs
  depends on Caddy's separate default-deny-for-assets rule for paths not in
  this file's `public` list (`config/site_access.yml:3-10`) — **not verified
  by HTTP in this census** (no live curl was run); this is an inference from
  the config file, not a direct-request confirmation. See GAPS.
- **End-to-end summary for Explore**: table, chart, Time Machine, and Forming
  Narratives all read **ungated (non-`/premiumdata/`) JSON**; the ONLY
  premium wall reachable from this page (`/premiumdata/sector_central.json`)
  governs the Overview Act-Now board, not Explore.

## 9. Row / detail links — full inventory

| Source | Destination pattern | Verified working? |
|---|---|---|
| Explore table row name (`.bname[data-id]`, `sector_central.html.j2:2698`) | `basket/<id>.html` (relative) | **Yes** — `site/basket/<slug>.html` files exist on disk for basket ids (e.g. `site/basket/gold_miners.html`, `site/basket/us_sector_realestate.html`, confirmed via `git ls-tree`). |
| Forming-Narratives ticker chip (`.ne-tk`, `forming_narratives.js:100-120`) | none — opens an in-place code popover (ticker/sector/grade), no navigation | N/A — display popover only |
| Forming-Narratives deep-link flash (`forming_narratives.js:202-207`) | `#ne-<signature>` anchor into the same card grid, `scrollIntoView({behavior:'smooth'})` | Anchor resolves within-page (no cross-page destination) |
| Act-Now board row → trace expand (`__siWireTrace`, `sector_central.html.j2:3096-3112`, Overview lane, cited for comparison) | `basket/<id>.html`, intercepted for an inline `.si-trace` reasoning panel with a "members →" link to the same `basket/<id>.html` | **Yes**, same target pattern as Explore table |
| Legacy anchors into Explore (`si_workspace.js:52-56`) | `#explore-section`, `#table-section`, `#chart-section`, `#forming-narratives`, `#tm-mount` → resolve to `view=explore` + intra-view scroll | Router-resolved, pinned by `tests/test_si_workspace_shell.py` (not independently re-run in this census) |

No `href="#"` dead links were found inside the Explore view's own markup
(`:2424-2476`) — the `href="#"` pattern the R2 review's PRC-001 flags at
`:689-691`/`:909` is against the **candidate** mockup, not production; those
line numbers do not correspond to anything in
`templates/sector_central.html.j2` (production has no such lines flagged) —
production's Explore row destinations are the real `basket/<id>.html` links
above.

## R2 review claims — confirmed vs refuted (Explore-scoped only)

| Claim (source) | Verdict | Basis |
|---|---|---|
| "Production lazy-loads Explore organs via subsector_rotation.js and time_machine.js in si_workspace.js:76-81" (PRC-005) | **Confirmed** | `si_workspace.js:75`, `LAZY.explore = ['subsector_rotation.js','time_machine.js']` (line offset differs slightly from cited 76-81 but the fact holds) |
| "Explore table LOST/ALTERED — seven-row sample" / "Performance chart LOST/UNPROVEN" (capability-ledger delta) | **Not applicable to production** — these verdicts describe the **candidate** mockup, not current production; production's table/chart are live, data-driven, and unrelated to the seven-row static sample cited | N/A (candidate-vs-production distinction; this census only audited production) |
| "Time Machine / Forming Narratives / Track Record | RELOCATED but dead-linked" (capability-ledger delta) | **RELOCATED is confirmed for production** (Time Machine + Forming Narratives moved from the retired standalone rotation page into Explore per masterplan §6.2b, `time_machine.js:3-5`); **"dead-linked" is a candidate-mockup finding**, not reproduced in production markup (§9) | Producer code inspected directly |
| "Restore ... analysis-labelled Forming Narratives" (Required repair #9) | **Partially refuted as a production defect, valid as a forward requirement** — production's Forming Narratives already separates deterministic score from one disclosed LLM watch line (§5), but the UI text nowhere explicitly labels the `ai_watch` sentence as "AI/LLM-generated" beyond the "🧭 AI scout watch" icon+label (`forming_narratives.js:151`) — arguably already a form of labeling, but not an explicit "model analysis" disclosure string | Direct inspection of `forming_narratives.js` and `narrative_emergence.py` |

---

**Producers touched by this lane** (for the capability ledger's disposition
pass): `scripts/build_baskets.py` (table+chart payload), `engine/narrative_emergence.py`
+ `engine/thematic_desk.py` (Forming Narratives), `scripts/build_oracle_timemachine.py`
+ `engine/oracle/timemachine.py` (Time Machine), `engine/sector_central_grader.py`
+ `scripts/build_sector_central.py` (self-grader/Track Record, Overview-mounted).
