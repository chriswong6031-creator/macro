# Marketing Cockpit — Build Spec (frozen contract, round 2)

Makes the Marketing lobe legible: short real department/engine names, a **glass-cockpit admin**
(friendly, illustrated, interactive, per-department + per-engine detail), and a **Content Studio**
that generates the *actual* mixed-content plans each desk would post — anchored on Prophet signal
posts with cashtags and a chart illustration carrying a BUY marker at a hidden MACD cross.

Builds on `docs/MARKETING_LOBE_BUILD_SPEC.md` (round 1). Same invariants: deterministic (no LLM
calls at build time), fail-soft, envelope-stamped, display-tier, off the scored path, admin reads
never writes.

---

## PART 1 — Renames (short real names)

### 1.1 Departments — keep `id`, add short `name`, `formal_name`, `tagline`

Change `Department.name` to the SHORT name; add `formal_name` (old long name, for hover) and
`tagline` (one plain-word sentence "what it does"). Update `as_dict()` + `state.py` + `marketing_lobe.json`.

| id | name (short) | formal_name (hover) | tagline |
|---|---|---|---|
| office_cmo | **Command** | Office of the Autonomous CMO | Sets strategy, allocates budget, hires and retires teams. |
| growth_os | **Engine Room** | Growth Operating System & Finance | Keeps everything running — scheduling, budgets, credentials, recovery. |
| intelligence | **Radar** | Market, Audience & Opportunity Intelligence | Spots opportunities: trending questions, events, audiences, gaps. |
| products | **Workshop** | Intelligence Products & Public Tools | Builds the free tools that pull people in. |
| studio | **Studio** | Editorial, Creative Studio & Data Newsroom | Creates the posts, charts, videos, and newsletters. |
| distribution | **Broadcast** | Distribution Network | Runs the accounts and channels; posts, replies, tracks receipts. |
| lifecycle | **Funnel** | Lifecycle, Conversion & Monetization | Turns visitors into trial users into paying subscribers. |
| ecosystem | **Allies** | Creator, Partner & Community Infrastructure | Works with creators, partners, and communities. |
| growth_science | **Lab** | Growth Science & Self-Improvement | Measures what actually works; runs experiments; kills last-click myths. |
| trust_office | **Sentinel** | Autonomous Trust, Policy & Red-Team Office | Independent watchdog: fact-checks claims, catches risk, can hit pause. |

Each department also gets an `icon` key (short slug the admin maps to an SVG glyph): `command`,
`engine_room`, `radar`, `workshop`, `studio`, `broadcast`, `funnel`, `allies`, `lab`, `sentinel`.

### 1.2 Engines — real names + plain "what it does"

Change `Department.engines` from `list[str]` to `list[dict]`: each `{id, name, does}` where
- `id` = the existing snake_case key (unchanged — stable),
- `name` = a short real product name (Title Case, ≤3 words),
- `does` = one plain-word sentence a non-technical operator understands.

Name ALL engines across the 10 departments thematically. Examples to set the tone (builder completes the rest):
- Workshop: `what_changed`→"What Changed", `why_is_it_moving`→"Why It's Moving", `stock_dossier`→"Dossier Forge", `event_impact_map`→"Event Mapper", `receipt_engine`→"Receipt Book", `chart_as_url`→"Chart Studio", `portfolio_watchlist_xray`→"Portfolio X-Ray".
- Broadcast: `x_publisher`→"Desk Network", `reply_community_queues`→"Reply Desk", `publication_receipts_takedown`→"Receipt Tracker & Recall", `content_studio` (NEW engine, see Part 2)→"Content Studio".
- Lab: `randomized_holdouts`→"Holdout Runner", `cohort_retention`→"Cohort Tracker", `simulation_digital_twin`→"The Twin", `automated_postmortems`→"Postmortem Desk".
- Sentinel: `provenance_verification`→"Provenance Check", `correction_and_recall`→"Recall Bus", `autonomous_quarantine_rollback`→"The Pause Switch".
Keep names honest and non-jargony. Add a NEW engine `content_studio` under **Broadcast** (Distribution).

---

## PART 2 — Content Studio (mixed content with a tilt)

The operator's model: NOT topic-silos. Every desk posts a **mix** of content; the tilt only shifts
emphasis so desks feel distinct without being 6 clones. The **anchor** is Prophet signal posts
(cashtag reaches a stock's whole audience fast). The same signal may appear on multiple desks but is
**rendered per-desk** (different copy template + chart style) to stay distinctness-safe under X rules.

### 2.1 `engine/marketing/content_studio.py` (new, deterministic)

- `CONTENT_TYPES` — ordered list of dicts `{id, name, desc, color}`:
  `signal` (Signal Alert — a Prophet plan as a cashtag post + chart), `chart` (Chart of the Day),
  `education` (Plain-English Explainer), `macro` (Macro Note), `receipt` (Report Card / Outcome Reopen),
  `watchlist` (On Our Radar), `event` (Event Reaction). Give each a hex color.
- Per-account `tilt`: a dict over the 7 type ids summing to ~1.0. **Every account carries every type
  with a non-zero weight** (min 0.03) — the tilt only shifts emphasis. `signal` is the largest weight
  for all accounts (0.28–0.42). Read tilts from `config/marketing.yml` `desk_network.accounts[].tilt`;
  fall back to a sensible per-kind default if absent.
- `plan_account(account, plans, *, n_days=7, per_day=3, seed)` → `list[ContentItem]`: deterministically
  samples the mix per the tilt (largest-remainder allocation over `n_days*per_day` slots so observed
  counts match the tilt closely and reproducibly — NO RNG; use a fixed round-robin/largest-remainder
  by index+account-hash so it's stable across runs but differs per account). Signal items draw from
  `plans` (Prophet). Each item: `{id, type, account, cashtag, ticker, headline, body, provenance,
  chart_id (nullable), slot ("D{n}-{AM|PM|EOD}"), status:"drafted"}`.
  - **Per-account rendering:** copy templates keyed by `(type, account.voice)` so the same signal
    yields different headline/body per desk (distinctness). Body is plain, honest, carries the
    cashtag, a "what to watch / what would change this" line, and NO technical-indicator language
    (no "MACD", "RSI", "cross" in public copy — the buy marker speaks for itself).
- `distinctness(items)` → `{max_similarity, flags}` — token-Jaccard across items of the SAME type on
  DIFFERENT accounts; flag pairs > 0.7. Signal posts for the same ticker on different desks must pass.
- `content_plan(cfg, plans, *, closes_loader)` → the full artifact dict (§2.3). Chooses a bounded set
  of **featured signal posts** (≈2 per account, max 12 total) that HAVE closes available, renders a
  chart for each via `chart_render`.
- `content_mix(items)` → per-type observed counts.

### 2.2 `engine/marketing/chart_render.py` (new, deterministic, pure-Python SVG)

- `macd_cross(closes: list[float]) -> dict|None`: compute EMA12, EMA26, MACD=EMA12−EMA26,
  signal=EMA9(MACD); return the MOST RECENT bullish cross (MACD crosses above signal) as
  `{index, offset_from_end}`. **MACD/EMA values are internal only — never returned in the artifact,
  never drawn.** If no cross in the window, return None (caller falls back to the Prophet signal_date
  index, or omits the marker with a note).
- `render_signal_chart(ticker, dates, closes, *, marker_index, width=560, height=300, subtitle=None)
  -> str`: a self-contained SVG string of the CLOSE price over the window (last ≤90 sessions):
  - price polyline (cyan `#38e0d4`, ~2px), subtle horizontal gridlines + faint area fill under the line;
  - a **BUY marker** at `marker_index`: an upward triangle + "BUY" label in green `#3ddc84`, a thin
    vertical guide line at that x, and the price dot;
  - min/max/last price labels (muted `#93a0b4`), first & last date labels;
  - brand mark "MASTERMIND" bottom-right (faint), and `subtitle` (e.g. "$TNDM · signal") top-left;
  - transparent background (renders on the dark admin), literal colors (may be shared publicly later),
    `viewBox`, no external CSS/JS, no `<script>`. Keep each SVG < 9 KB.
  - **Absolutely no MACD/EMA subpanel, no indicator labels, no "cross" text.** Only price + BUY marker.
- Closes loader: read `data/stocks/<TICKER>.parquet` (columns: close/high/low/volume, Date index) via a
  small helper `load_closes(ticker, root, n=90) -> (dates, closes)|None`; fail-soft to None when absent.

### 2.3 FROZEN artifact `data/marketing/content_plan.json` (`marketing.content/v1`)

Written by the governor to `data/marketing/content_plan.json` (UNREGISTERED — lives beside the seed
ledgers; NOT a synapse artifact, so no pin/SIGNAL_BUS churn). Envelope-stamped best-effort. Shape:

```jsonc
{
  "schema_version": 1, "produced_by": "...", "produced_at": "...", "tier": "display",
  "schema": "marketing.content/v1", "as_of": "YYYY-MM-DD",
  "source": {"prophet_plans": n, "plans_with_charts": n, "note": "..."},
  "content_types": [{"id":"signal","name":"Signal Alert","desc":"...","color":"#..."}, ... 7],
  "accounts": [
    {"id":"flagship","name":"...","kind":"branded","voice":"...",
     "tilt": {"signal":0.38,"chart":0.14,...},
     "mix_observed": {"signal":8,"chart":3,"education":3,"macro":3,"receipt":2,"watchlist":1,"event":1},
     "queue": [
       {"id":"post-flagship-001","type":"signal","cashtag":"$TNDM","ticker":"TNDM",
        "headline":"...","body":"...","provenance":"neural_web","chart_id":"chart-001",
        "slot":"D1-AM","status":"drafted"}, ...
     ]}
    // ... 6 accounts
  ],
  "featured_charts": [
    {"id":"chart-001","ticker":"TNDM","account":"flagship","cashtag":"$TNDM",
     "marker_source":"macd_cross|signal_date","marker_date":"2026-06-24","marker_price":15.28,
     "svg":"<svg ...>...</svg>","headline":"...","body":"..."}
    // bounded, ≤12
  ],
  "distinctness": {"max_similarity":0.0,"flags":0,"note":"same signal rendered per-desk; variants checked"},
  "summary": {"total_posts":n,"signal_posts":n,"charts":n,"accounts":6}
}
```

### 2.4 Config `config/marketing.yml` — add `tilt` per account + keep the 6 accounts

Each `desk_network.accounts[]` gets a `tilt:` map (7 weights, all ≥0.03, signal largest). Tilts differ
per account (flagship: signal+macro; receipts: receipt+chart; theme_desk: signal+event; research_a:
macro+education; research_b: signal+chart fast; research_c: chart+watchlist) — but ALL types present.
Replace the old "corpus silo" framing in comments with the mixed-tilt model.

### 2.5 Governor + state wiring

- `marketing_governor.build_and_write` also builds the content plan (via content_studio + chart_render,
  reading Prophet `site/prophet/index.json` plans and `data/stocks/`) and writes
  `data/marketing/content_plan.json`. Fail-soft: if Prophet/closes absent, write an honest minimal plan.
- `state.py` desk_network: replace/augment per-account `corpus` with `tilt` + `mix_observed` summary;
  add a top-level `content` summary block `{total_posts, signal_posts, charts, accounts}` reading the
  content plan if present (else nulls/accruing).

---

## PART 3 — Admin glass cockpit (friendly, illustrated, interactive)

All in `admin/marketing.py` + `admin/server.py` + `admin/static/app.js` + `admin/static/styles.css`.
Match the dark Observatory aesthetic (indigo #6a8dff → cyan #38e0d4). Every page must be legible to a
NON-technical operator: plain words first, jargon in hovers, honest empty states, and visuals.

### 3.1 New/updated panels in `admin/marketing.py`
- `content(root=None)` → reads `data/marketing/content_plan.json`; returns `{ok, content_types,
  accounts, featured_charts, distinctness, summary}`. Fail-soft with honest note if absent.
- `department(root=None, dept_id=None)` → the single-department detail payload (mission/tagline/
  formal_name, engines[{id,name,does}], scorecard, authority, model mix, wave, retirement test).
- Keep/extend overview, departments, channels, campaigns, experiments, lobes, settings.

### 3.2 `admin/server.py`
- `GET /api/marketing/content` → `marketing.content()`.
- `GET /api/marketing/department?id=<id>` → `marketing.department(dept_id=id)`.

### 3.3 `admin/static/app.js` — nav, pages, illustrations, interactivity
- NAV "Marketing" group: add **"Content Studio"** item (`marketing_content`) after "Channels & Desks".
  Final order: CMO Office · Departments · Campaigns · Channels & Desks · **Content Studio** · Experiments · Engines.
  Add an ICON for `marketing_content` (a broadcast/spark glyph).
- **Renames auto-reflect** (pages read `name`/`formal_name`/`tagline`/`tagline` from state). Add `title=`
  hover = `formal_name` on department names (NO translated text in title attrs — this admin is EN-only, fine).
- **CMO Office**: add an inline **SVG flywheel illustration** (the 9-step growth loop as a friendly
  ring diagram) + a one-paragraph plain-word "How the machine works" so a newcomer gets it in 10s.
- **Departments page**: card grid using short `name` + `icon` glyph + `tagline` + lifecycle/authority
  pills + a mini "N engines" chip. Each card is CLICKABLE → department detail (hash route `#/mkt-dept/<id>`,
  mirror the existing `#/lobe/<id>` router in app.js: add `currentMktDept()` + a `route()` branch +
  `renderMktDept(id)`). Detail page: big plain mission, `formal_name`, the engines as **named cards**
  ("What Changed — spots what changed for a ticker/sector and why it matters"), scorecard, authority
  ladder position, model mix, wave, retirement test, a Back link.
- **NEW Content Studio page** (`RENDER.marketing_content`) — the flagship "see what they're doing" view:
  - Header: total posts / signal posts / charts / accounts, plain-word explainer of the mixed-tilt model.
  - **Account switcher** (tabs/pills for the 6 desks + "All").
  - Per account: a **content-mix donut** (SVG, colored by `content_types[].color`) + the tilt shown as a
    labeled bar row, + the desk voice/kind.
  - **Post gallery**: cards for the queued posts. Signal/featured posts render the **chart SVG inline**
    (the price line + BUY marker), the cashtag as a chip, the headline + body, provenance + slot + status.
    Non-featured posts render as compact text cards with a type color chip.
  - **Content-type filter** chips (toggle signal/chart/education/…); interactive (client-side filter).
  - Honest note that this is a drafted plan (shadow — not yet posted externally).
- **Channels & Desks page**: replace the "corpus silo" display with the **mixed-tilt model** — per
  account show the tilt as a small stacked bar + `mix_observed`, and a line clarifying "every desk posts
  a mix; the tilt just shifts emphasis; the same Prophet signal is rendered differently per desk."
- **Interactivity throughout**: account switcher, type filters, expand/collapse engine lists, hover
  tooltips for formal names + engine "does". Keep it snappy (client-side, no extra fetches per toggle).

### 3.4 `admin/static/styles.css`
Add scoped classes for: `.mkt-donut` (+ svg), `.mkt-tilt-bar`, `.mkt-post-card`, `.mkt-chart-embed`
(so the inline SVG sizes nicely), `.mkt-cashtag` chip, `.mkt-type-chip` (colored), `.mkt-dept-card`
(clickable hover lift), `.mkt-flywheel`, `.mkt-filter-chip` (active state). Reuse tokens; don't touch
shared `.kv`/`.card` globally.

---

## PART 4 — Tests
- `tests/test_marketing_content.py` (NEW): content_studio produces a non-empty plan for 6 accounts;
  every account's mix has ALL 7 types with ≥1 where slots allow and signal is the largest; distinctness
  passes on the generated plan; chart_render emits valid `<svg>` with a BUY marker and NO "MACD"/"RSI"/
  "EMA"/"cross" substring; `macd_cross` finds a known cross on a synthetic rising series; governor writes
  `content_plan.json` with the frozen top-level keys.
- Update `tests/test_marketing_engine.py`: departments now expose `name` (short), `formal_name`,
  `tagline`, `icon`, and `engines` as list of `{id,name,does}`.
- Update `tests/test_admin_marketing.py`: `content()` + `department()` panels return ok and are fail-soft.

## PART 5 — House-law / process
- Deterministic; no LLM calls; no new synapse artifact (content_plan.json is unregistered under
  data/marketing/, so NO pin/SIGNAL_BUS churn — avoids the collision treadmill).
- Public copy carries NO technical-indicator vocabulary (compliance + the operator's "don't reveal we
  use technicals" instruction). The chart shows a BUY marker only; MACD is computed but never surfaced.
- Run governor, commit the regenerated `data/marketing/content_plan.json` + `marketing_state.json` +
  `marketing_lobe.json`. Verify admin renders (screenshot). Then commit → PR → same-day squash-merge.
