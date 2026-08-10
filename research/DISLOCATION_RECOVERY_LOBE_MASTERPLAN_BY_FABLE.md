# Dislocation & Recovery Lobe — masterplan

Author: Fable main loop, 2026-08-10. Origin: operator-supplied brainstorm
(`Mastermind_Dislocation_Recovery_Lobe.md`, ChatGPT seed) adjudicated against the
repo's standing record. Program alias: **DRL**.

**Namespace ruling (collision-cleared):** bare "dislocation" is already claimed
twice at other granularities — `engine/dislocation.py` (macro Fed-put gauge,
writes `latest.json["dislocation"]`, read by `engine/turning_point.py`) and
`engine/options_dislocation.py` (options-chain family, quant_lab-registered).
This per-name lobe therefore lives at **`engine/price_pressure/`** — the seed's
own preferred term for the phenomenon — with artifact keys `price_pressure_*`
and surface working name **Pressure Watch**. The word "dislocation" stays out of
engine/artifact namespaces entirely; research docs may use the program name.

## §0 ACCEPTANCE GATES (read first; each wave is "not done unless")

**W1 (engine + ledger + backfill), not done unless:**
- `engine/price_pressure/` computes nightly residual shocks by **reusing** the
  LSR-P0 machinery (`scripts/research_liquidity_shock_reversal.py`: panel build,
  split repair via `scripts.replay_standout_pipeline.split_adjust`, sector
  ex-self peer residualization, EDGAR 8-K flags) — no re-derived parallel math.
- A **point-in-time event ledger** exists with the schema in §5, advanced by the
  nightly lane only; intraday lanes never write it. Every row carries
  `era ∈ {backfill, gap, forward}` — `backfill` = frozen study rows; `gap` =
  rows harvested by the nightly's self-healing catch-up between the frozen
  snapshot and go-live (displayed, but never promotion evidence); `forward` =
  harvested on their own night. §7 evidence is forward-era only.
- Day-character fields key off `market_drivers.snapshot()` vocabulary — the lobe
  invents **no parallel shock taxonomy** (DNR:KILL-PARALLEL-SHOCK-CLASSIFIER).
- Lifecycle state transitions carry a **2-consecutive-close debounce**
  (DNR:KILL-ONE-TICK-ESCALATION), and terminal verdicts are horizon-named
  (`terminal_state_60d`, never a bare "recovered") per
  DNR:KILL-OFFHORIZON-VERDICTS.
- The historical **backfill** over the full `data/massive_stock_day` span is run
  once locally (off the render path), producing the frozen base-rate artifact
  (§6) with **episode-level honest-N**, survivorship/coverage statements printed
  inside the artifact, and zero claims beyond display tier.
- Tests cover: eligibility fence (price/ADV/split-day), PIT discipline (no
  future field enters an event row), ledger idempotence (re-running a night does
  not duplicate or rewrite closed rows), state transitions, artifact schema.
- No LLM anywhere in the compute path (constitution A7). No word "validated" in
  any user-visible string (`scripts/check_validated_claims.py`).
- The nightly step's wall cost is measured and stated in the PR body; it stays
  off the render critical path or adds ≤ ~60s to the lane it joins.

**W2 (user surface), not done unless:**
- Glance tier reads as **state + plain-word stance** under DESIGN_DOCTRINE word
  budgets; zero banned vocab (no internal study names, no untranslated stats, no
  raw slugs); technicals live in hover/Tier-2 receipts.
- **No bounce-picking language anywhere.** The surface's stance layer prints the
  measured truth (continuation is the modal outcome; the bounce that exists is
  sub-cost) and frames windows, never certainties. Falsifier/refutation vocab
  never front-facing (operator law 2026-07-27).
- EN/ZH shipped together (templates AND builder copy), no translated text in
  `title=` attributes, dark mode keyed on `:root[data-theme]`, reduced-motion
  honored, mono numerals for figures only.
- PR body carries per-state visual crops (light+dark+zh) of the shipped band and
  hover; fresh end-to-end render with zero manual workarounds.
- Surface follows the funnel: it ships where users already read US stocks
  (stocks hub family), not where the engine lives.

**Ship law (both waves):** commit → push → PR → `merge-on-green` label → same-day
squash-merge → live verification on the deployed site.

## §1 What this program is (and is not)

Detect when a single name's price has been pushed **materially away from what
market + sector + peers justify** (a residual shock), record everything knowable
about that moment point-in-time, track how the residual resolves, and show users
an honest, peer-relative read they cannot get from a raw movers list. The
phenomenon is **price pressure**; we hunt the footprint, never the confession —
"manipulation detected" is not a concept in this program (and never a required
condition; cf. SEC treatment of spoofing as the illegal species).

**It is not a buy-signal engine.** This repo has already measured the tempting
version of that claim to death (§2). DRL ships display-tier context freely under
the house epistemics (a null never blocks building context/detection/tagging
infrastructure); any future promotion to authority walks the §7 gauntlet on the
forward ledger this program starts accruing today.

## §2 Standing record this program is bound by (cite by key)

- **DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER** (LSR-P0, 2026-08-05) — the
  1–5d shock-reversal classifier as selection alpha or entry veto is **closed at
  OHLCV grade** on the ≥$5/≥$5M-ADV panel: information separation 0/10 (no-news
  down-shocks *continue*, −0.33% resid at 5d), microstructure features 3/36
  (noise), veto 0/6, and the real unconditional 5d bounce (+0.284% D10−D1
  liquid) breaks even at 14.2bp/leg. Re-tuning z/volume/horizon/peer-basis/label
  taxonomy is the same construction. Illiquid tail also closed (bigger gross,
  worse net). DRL **must not** re-litigate any of this; DRL *displays* these
  measured truths.
- **Open doors the same kill left, which are DRL's future research legs (§8):**
  (1) tape-grade order-flow features — never tested, blocked on entitlement
  (`trades_v1`/`quotes_v1` 403; the Massive tick-plane program is independently
  building live tape capture); (2) analyst-revisions firewall — coverage-blocked,
  `data/revisions/history.parquet` accrues from 2026-06-16, first answerable in
  years; (3) the **Nagel-shaped lead**: no-news down-shock continuation weakens
  as VIX regime rises (calm−stressed −0.860% [−1.575,−0.145] at h=5, 1 of 3
  horizons) — a *different claim* needing its own prereg with frozen breakpoints.
- **DNR:KILL-PSS-F3-RESIDUAL** — beta-stripped residual extremes as standalone
  entry timing: killed; fires concentrate in **high-R² systemic windows** (the
  mechanism-dead signature). DRL inherits the lesson as a *display feature*:
  every event carries a systemic-vs-idiosyncratic day character so users see
  whether "cheap" is really "everything fell today".
- **DNR:HOLD-SHORT-INTEREST-LEGS** — no PIT short-interest history; the
  brainstorm's short-covering engine (§6 of the seed) stays parked until that
  hold lifts. Not built here.
- **DNR:KILL-MCO-THRUST** — market-level oversold *bounce* radar legs are
  reject-killed; DRL is single-name and descriptive, and its copy never promises
  a bounce.
- **DNR:KILL-LLM-CONTAGION-TAGS / constitution A7** — no LLM originates any
  signal, score, or escalation anywhere in DRL. All fields are engine-computed.
- **DNR:KILL-PROPHET-POP-MERGE** — DRL never feeds the Prophet graded-board
  population. Any future cross-surface chip is presentation-tier only.
- **Instrument verdicts are NOT market verdicts (operator 2026-08-09):** ledger
  states describe the declared residual windows only; surface copy scopes every
  claim ("within N sessions", "no retrace yet"), and where a scored organ or the
  tape disagrees, the dual-read leads.
- Monthly-horizon reversal already NO-GO twice (`validate_reversal`,
  `validate_reversal_nonsurvivor`) — consistent with LSR-P0: real-but-marginal
  gross, dead net. The record is coherent; DRL's stance layer quotes it.
- **Second-ring bindings (overlap census 2026-08-10):**
  DNR:KILL-PARALLEL-SHOCK-CLASSIFIER — day/shock vocabulary keys off
  `market_drivers.snapshot()`, never a parallel taxonomy.
  DNR:KILL-ONE-TICK-ESCALATION — 2-close debounce on every state flip.
  DNR:KILL-OFFHORIZON-VERDICTS — recovery-vs-derating verdicts are horizon-named.
  DNR:KILL-DIRECTIONAL-SHORTING — `accepted_lower_60d` is avoid-evidence, never
  a short thesis; surface copy obeys.
  DNR:KILL-FUSED-COMPOSITE + KILL-REGIME-SCORECARD +
  KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR + KILL-PER-SIGNAL-FAMILY-RELIABILITY
  — no fused "pressure score", no regime×family reliability grid; states are
  taxonomy, base rates are frozen tables.
  DNR:KILL-PSS-SR1-ELASTICITY / SR2-PEER-DIFFUSION / SR3-PARTICIPATION — peer
  exhaustion/diffusion *mechanisms* are killed as signals; DRL stores peer
  co-move only as plain facts. DNR:HOLD-PSS-RH1/CR1/CD1/AF1 — those PSS organs
  are prospective-frozen; DRL touches none of them, and its own era split keeps
  backfilled rows out of any future evidence set.
  DNR:KILL-PM4-OVERHEAD-SUPPLY — reuse existing 52w-position column conventions
  (`pos52`/`dist_to_52wh`), no re-derived overhead-supply construction.
  DNR:KILL-FRESH-BUY-EDGE + KILL-PRIMED-DIRECTIONAL-GATE — mover/bottom boards
  carry no buy-edge or sizing authority; Pressure Watch inherits that law.
  DNR:LAW-REVERSION-RULER — if reversion capture is ever scored, it is scored as
  ~20–25d time-exit capture, not 63d factor apparatus.

## §3 Decomposition (from the seed, adjudicated to this repo)

Observed move = fundamental information + systematic repricing + temporary
pressure. The seed's eight modules map to house reality as:

| Seed module | DRL disposition |
|---|---|
| 1. Counterfactual price engine | **Build W1** — sector ex-self peer residual (LSR construction) is the shipped v1 counterfactual; richer multi-factor counterfactuals are a research leg, not v1 (PSS-F3 warns the fancier residual bought nothing) |
| 2. Fundamental damage firewall | **v1 = EDGAR 8-K facts** (earnings vs material vs none) already in `data/edgar/`; XBRL transitory-vs-permanent decomposition is a W3+ context leg, deterministic only |
| 3. Contagion engine | **Reuse, don't rebuild** — engine-originated contagion organ already ships (CSP-W1 key + glance chip; LLM tagging killed). DRL adds only per-event peer-basket co-move facts |
| 4. Liquidity-event detector | v1 = level facts computable from daily bars (52w-low distance, gap, volume multiple); tape-grade topology awaits the tick plane |
| 5. Exhaustion/absorption | **Blocked on tape** (the never-tested half of LSR-P0). W1 stores the OHLCV proxies (CLV, Amihud-rel, intraday path) as *context fields, never scores* |
| 6. Short-covering engine | **Parked** (DNR:HOLD-SHORT-INTEREST-LEGS) |
| 7. Horizon classifier / winner engine | Event **families** ship in W1 as facts (filing/no-filing/systemic/contagion); the "future winner" overlay belongs to the winners program, linked in W3+, never duplicated here |
| 8. Probability & execution layer | **Replaced** by display-tier lifecycle states + frozen base rates. Probabilities imply promotion; that walks §7 first |

## §4 W1 engine architecture

Home: `engine/price_pressure/` (new; see the namespace ruling). Compute lane:
one non-fatal step in `daily.yml`'s **tail-desks band** (the designated slot for
small Neural Web lobes; copy the liquidity-plumbing step template — no network,
`python -m scripts.build_price_pressure || echo "::warning::…"`, outputs picked
up by the later `git add data/`). Ledger writes gate on
`engine/ledger_lane.py::nightly_advance_enabled()` (COLLECT_LANE=nightly), so
intraday/express lanes can rebuild displays but never advance the ledger. All
heavy scans stay off the render path; the nightly increment touches only the
trailing window.

- `panel.py` — thin wrapper re-exporting the LSR panel build (cache-aware,
  split-repaired, `data/massive_stock_day`). One shared cache dir with the
  research script so backfill and nightly agree byte-for-byte.
- `detect.py` — the LSR `derive()` construction verbatim: `resid = ret −
  sector_ex_self_peer(ret)` (sector map `data/breadth/ticker_sectors.parquet`),
  `resid_z = resid / rolling_σ(shifted)`, eligibility = non-split-day ∧
  price ≥ $5 ∧ ADV-median ≥ $5M ∧ σ known. Shock = |resid_z| ≥ 3 ∧ abnormal
  volume ≥ 2× (both sides logged; down side is the product focus). Same
  constants, **imported not copied**. Deliberately NOT the
  `engine/residual_alpha.py` Vasicek beta regression: the frozen base rates (§6)
  were measured on the LSR construction, and the display must quote
  distributions computed on the same residual it shows. The beta-regression
  counterfactual is a §8 leg, never a silent swap.
- `context.py` — per-event PIT facts, all engine-computed: 8-K flags (±1
  calendar day, coverage bit), **day character read from
  `market_drivers.snapshot()`** plus panel shock breadth (no parallel shock
  vocabulary — DNR:KILL-PARALLEL-SHOCK-CLASSIFIER; the PSS-F3 systemic-window
  lesson is the display motive), peer basket same-day return and shock count
  (plain facts only), 52w-low distance (house `pos52` convention), gap %,
  volume multiple, CLV, Amihud-rel, VIX 252d percentile (FRED `VIXCLS`),
  revisions coverage bit (accrual clock visibility from day one).
- `ledger.py` — append/advance the forward ledger (§5). Nightly-only writer
  (`nightly_advance_enabled()` gate); follows the `transmission_chains` episode
  pattern (append-only rows + idempotent same-asof re-evaluation + snapshot).
- `artifact.py` — display snapshot `data/price_pressure/latest.json`: fixed
  shape, `authority` block with `can_rank/can_size/can_gate/
  can_originate_signal/can_escalate` all literal `false` (govrev pattern),
  fail-open `gaps: []` list (nulls printed). Registered in `config/synapse.yml`
  as `price-pressure-latest` (tier `display`, horizon_role `context`,
  owner_program `price-pressure`; `scripts/check_synapse_registry.py` gates).
- **Brain wiring:** a `_pressure_block()` in
  `engine/neuralweb/market_packet.py` (explicit registration in
  `build_packet()` + `_RENDERERS` + `_SECTION_ORDER` near the bottom — synapse
  registration alone does NOT reach chat; govrev proves it). Tiny render (top
  ~3 events, one line each) inside the packet's global char budget; product
  artifact read only (CXI-R23).
- `backfill.py` — one-shot historical run over the full panel span; emits the
  ledger seed (`era="backfill"`) + frozen base-rate artifact (§6). Run manually
  this session; never on CI or the render path.

### §4.0 Smoke-run evidence (main loop, 2026-08-10)

The LSR machinery was re-run end-to-end in this session on the freshest local
store cache (primary checkout, span 2021-07-06..2026-07-02): panel = **4,281
names** (exact match to the LSR-P0 published panel), events = **35,677**
(LSR reopeners: 35,678 — same construction, one-snapshot drift), down = 17,511,
8-K coverage 46.9%, full pipeline **58s** (45s cached-panel scan). **MU
April-2025 fired the idiosyncratic fence 0 times** — the §6 exemplar scope
statement is now measured, not predicted. R2 is the store's canonical home and
local caches lag it (git-tracked manifest reads latest_day=2026-08-07); the
nightly step therefore runs where the collect lane restores the store, and the
catch-up below heals any local-snapshot gap.

### §4.1 Data reality (census 2026-08-10)

- **Panel store:** `data/massive_stock_day/` — ~19–20k tickers, rolling ~5y
  window from 2021-07-06, **unadjusted**; split repair =
  `scripts/replay_standout_pipeline.py::split_adjust()` (verified ≤0.2% vs
  Yahoo), repaired bars stamped ineligible (LSR policy). Nightly incremental
  via `scripts/collect.py`; canonical home R2. Worktree snapshots can lag —
  the backfill reads the **freshest** store reachable (primary checkout
  `data/` read-only, or `fetch_r2`), asserts its max date, and stamps the
  artifact `asof`.
- **Sector map:** `data/breadth/ticker_sectors.parquet` (1,516 GICS names,
  SP500+400+600) — the effective residual universe is its intersection with
  the liquidity fence; coverage share printed in every artifact.
- **Event context stores:** `data/edgar/earnings_8k_dates.parquet` (98,975
  rows, 1,314 tickers, 2004→) + `material_8k_events.parquet`;
  `data/earnings/earnings.parquet` (forward calendar);
  `data/edgar/dilution_events.parquet` and `statements.parquet` (XBRL, 1,506
  tickers) for §8 leg 4.
- **Thematic baskets:** `data/baskets/membership.json` — 46 curated baskets
  with dated `members[]` + `etf_proxy`. v1 residual basis stays sector ex-self
  (LSR construction, base-rate consistency); basket same-day co-move ships as
  a context fact where membership exists.
- **Benchmarks:** `data/yahoo/` (SPY/sector ETFs/commodities/FX, dual-basis
  close), `data/fred/` (yields; `VIXCLS` for the VIX percentile, LSR
  convention).
- **Delistings/truncation:** bars simply stop for dead names. An event whose
  forward window is cut short keeps its row with null horizon fields + a
  `truncated` flag — never dropped (resolution-conditioned denominators
  delete losers). The truncated share prints in §6. `config/delisted_symbols.yml`
  + `collectors/edgar_deadnames*` exist for later enrichment.

## §5 Event ledger (the program's center of gravity)

`data/price_pressure/events.parquet` (house convention:
`data/<program>/<name>.parquet`, per `data/group_pulse/episodes.parquet`) — one
row per (ticker, shock date, side):

- **Identity/PIT block (frozen at t0, never rewritten):** date, ticker, side,
  era (backfill|forward), resid, resid_z, ret, peer_ret, vol_multiple,
  txn_multiple, clv, gap, intraday_ret, amihud_rel, dollar_adv_med, price,
  dist_52w_low, earn8k, mat8k, edgar_covered, revisions_covered,
  day_character (from `market_drivers`), panel_shock_count, sector,
  peer_shock_count, vix_pctile, engine_version.
- **Grading block (advanced by nightly as horizons mature):** cumulative
  forward residual at t+{1,3,5,10,21} (the LSR-native horizons, log
  convention) plus a t+60 ledger tail, retrace fraction of the t0 residual at
  each horizon (log-space: `fwd_h / (−log1p(r0))`), max adverse/favorable
  residual excursion, days-to-50%-retrace (null until/if hit), state (§5.1),
  state_updated, closed_at. Rows also carry `episode_id` (a follow-up shock
  landing within 5 sessions of an open same-side event joins that episode;
  base rates count first-shock-of-episode rows) and `followup_shock`.
- **Honesty invariants:** a horizon field is null until its window has fully
  elapsed (no partial peeking into the grading block); closed rows are
  immutable; every nightly run logs how many rows it advanced/closed
  (nulls printed, not hidden).

### §5.1 Lifecycle states (descriptive, windows-not-certainties)

`SHOCK` (t0) → `SLIDING` (further ≤ −0.5σ cumulative residual since t0) /
`HOLDING` (within ±0.5σ band) / `RETRACING` (recovered ≥ 33% of t0 residual) →
terminal `terminal_state_60d`: `RECOVERED` (≥ 80% retraced), `PARTIAL`
(33–80%), `ACCEPTED_LOWER` (< 33% retraced — the market kept the lower price;
avoid-evidence only, never a short thesis), or earlier `RECLAIMED` if 100%
retraced before t+60 (row closes on the day it happens). Non-terminal flips
require the condition to hold **two consecutive closes**
(DNR:KILL-ONE-TICK-ESCALATION); the first close shows as a pending badge, never
a flipped state. States are computed from realized residual paths only — no
prediction, no score. Thresholds are display taxonomy, not tuned alpha (they
slice the same frozen distributions §6 publishes; changing them is a display
decision).

## §6 Frozen base-rate artifact (the honesty layer)

`data/price_pressure/base_rates.json`, produced by the backfill and refrozen
only by an explicit re-run (never silently by nightly):

- Retrace-fraction distributions (quartiles) and terminal-state shares by
  **family × horizon**, families = {earnings-8K, material-8K, no-filing,
  systemic-day, contagion-heavy}, down side primary.
- Episode honest-N per cell (distinct ticker-episodes; overlapping shock days
  within t+5 of an open event of the same name collapse into one episode).
- Coverage + survivorship statement embedded: unadjusted-store caveats,
  split-repair ineligibility policy, EDGAR coverage share of events, span
  (2021-07..present — **five years, not twenty**; stated plainly), and the
  known small dividend bias direction.
- A `provenance` block citing LSR-P0's report numbers this display leans on
  (continuation is modal; the residual recovery that exists is sub-cost) so
  surface copy is regenerable from receipts.
- An `exemplars` block reading out the motivating episodes as facts, per the
  adjudication coverage gate (operator 2026-08-10) — the study leads with how
  the motivating exemplars actually read under the shipped construction:
  - **CDE 2026-08 (idiosyncratic type):** the construction's home case — a
    single-name earnings shock against quiet peers. Postdates the frozen
    store snapshot (2026-07-02, §4.1); the nightly **self-healing catch-up**
    (re-harvest from the ledger's own max date forward, min ~15 sessions,
    capped ~90, idempotent by (ticker,date,side)) picks it into the ledger on
    first advance with `era="gap"`, and the research doc states this rather
    than hiding it.
  - **MU April-2025 (systemic type): expected NOT to fire the idiosyncratic
    fence, and that is correct behavior** — on the tariff-shock days the
    whole semi complex fell together, so MU's sector-ex-self residual was
    modest. The construction *deliberately* separates idiosyncratic pressure
    from systemic washouts; MU-type days surface through `day_character` +
    `panel_shock_count` context (and the band's broad-selloff banner, §9),
    and the MU-type *long-horizon secular-washout* family belongs to the
    winners-program linkage (§8 leg 5), not to this fence. The study prints
    MU's actual residual path on those days as the demonstration.

## §7 Promotion gauntlet (pre-registered now, walked later or never)

Nothing in DRL ranks, sizes, or gates anything until, on the **forward ledger
only** (rows accrued after W1 ships — the backfill is context, not evidence):
- A named, frozen claim (e.g. "family F retraces ≥ X% by t+20 at rate ≥ p vs
  base") with CIs excluding the base rate under date-block bootstrap;
- Episode honest-N ≥ 200 forward episodes in the claimed cell;
- Both regime halves (VIX above/below median) hold sign;
- An adversarial reviewer pass (opus) on the exact claim text;
- And the claim is not a re-tuning of the LSR-killed construction (checked
  against DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER's scope clause by name).
Until all five: display tier, everywhere, forever.

## §8 Research legs (later sessions; each needs its own prereg)

1. **R4-gradient prereg** — "down-shock continuation weakens as market
   liquidity tightens": frozen VIX breakpoints, forward-ledger graded.
2. **Revisions firewall clock** — re-test information separation when
   `data/revisions/history.parquet` covers ≥ ~2y of events (≈2028+).
3. **Tape-grade exhaustion** — when the tick plane exposes signed
   flow/imbalance: the never-tested half of LSR-P0. Design detectors against
   the accrued ledger's event set.
4. **XBRL transitory-decomposition context** — deterministic non-cash/PPA
   extraction for earnings-family events (the CDE case from the seed);
   context field, never a score, until separately gauntleted.
5. **Winners-bucket linkage** — join DRL episodes to the winners program's
   secular-washout bucket (MU case) rather than building a second winner model.
6. **Short-interest unlock (not ours to pull):** DNR:HOLD-SHORT-INTEREST-LEGS
   is deferred on missing PIT history, but
   `scripts/backfill_finra_short_interest.py` already exists un-run (206
   settlement dates measured available to 2018). If that program ever runs its
   backfill and the HOLD lifts, DRL's ledger joins the vintage panel as
   context; DRL does not run the backfill itself.

## §9 W2 user surface (the funnel)

**Home: a Pressure Watch band on the stocks hub** — new
`<section id="pressure">` in `templates/ticker_index.html.j2` between the
movers boards (~:519-557) and theme ribbons (~:559-586), fed by a new pure
function in `engine/stocks_hub.py` shaped from `data/price_pressure/latest.json`
loaded fail-soft in `scripts/build_ticker_pages.py::_build_hub_context()`
(the `market_structure` pattern: artifact missing → warm-up state, never a
crash). Both files are mapped to the `macro` render region — a band render is
minutes, not a full bake. A standalone page is deferred until the band earns it.

Band anatomy (doctrine tiers):
- **Structural honesty (not just copy):** the band shows **both sides** —
  down-pressure and up-pressure events — so it reads as a pressure lens, not
  a dip-buy screen; and on systemic days (from `market_drivers` day
  character + panel shock breadth) the band leads with a **broad-selloff
  banner** ("most of today's pressure is market-wide, not single-name") and
  demotes single-name rows to context. This is the structural answer to
  "implicit buy list", ahead of any wording.
- **Tier 1 per row:** ticker + one line — "fell 9.8% on 6× volume; peers
  implied −2.1%" — a family chip (earnings filing / other filing / no filing
  found / broad-selloff day, from `market_drivers` + 8-K facts), and for
  tracked events a state chip (holding / still sliding / retracing 42% /
  reclaimed). Stance line for the band (not per row): plain-word honest read
  from §6 — e.g. "shocks like these kept sliding more often than they
  recovered in the following week — watch, don't chase." The words "bounce",
  "dead-cat", "giveback" are banned vocabulary (#2208); "manipulated" never
  appears anywhere.
- **Tier 2 (`?` help-tip on the band h2 + `data-tip-en/zh` per chip):** residual
  z, volume multiple, ADV floor, EDGAR coverage share, VIX regime percentile,
  base-rate table cell (family × horizon, with episode N and span 2021-07..),
  and the scope sentence ("states describe the tracked window only").
- **Colors:** all direction semantics through `--up`/`--down`-derived tokens
  (zh 红涨绿跌 flips site-wide via `html[data-lang="zh"]`); never literal hex.
- **i18n:** ZH authored as Chinese in both template `t()` macros and builder
  dicts (`stance()`-style {tone,en,zh}); no CJK or interpolation inside
  `title=` (use `data-tip-*`; `scripts/check_title_i18n.py` guards).
- **Tests:** extend `tests/test_stocks_hub.py` (pure-function contracts) +
  `tests/test_ticker_pages.py` (context build, warm-up mode, no "validated",
  ZH-pair parity); light+dark+zh crops in the PR body (doctrine §5.8).

## §10 Waves

- **W0 (this doc)** — adjudication + collision clearance. DONE when merged.
- **W1** — engine + ledger + backfill + frozen base rates + nightly wiring +
  tests (PR 1, with this doc).
- **W2** — surface (PR 2). Designer owns look/copy; builder implements.
- **W3+** — §8 legs, one session each, chained via continuation handoffs.

## §11 Collision clearance (overlap census 2026-08-10)

- **Namespace:** `engine/dislocation.py` (macro Fed-put gauge,
  `latest.json["dislocation"]` key, read by `turning_point.py`) and
  `engine/options_dislocation.py` (quant_lab options family) both untouched;
  this lobe is `engine/price_pressure/` throughout.
- **Hot same-day lane:** `blocked_entry_conditional_v1` (#5225/#5237/#5251,
  ratified 2026-08-10) — Golden Oracle bear_block override via per-name
  peer-basket median drawdown (`scripts/build_basket_washout_state.py`).
  Different territory (Oracle trigger/veto vocabulary vs residual event
  ledger/display); zero file overlap; DRL never touches Oracle trigger, veto,
  or `basket_washout_state` artifacts. Coordinate, don't fork.
- **Basket-grain state machines** (`engine/group_pulse.py` ARC ladder,
  `engine/us_basket_turn.py` washout lifecycle): basket-grain organs; DRL is
  per-name event-grain with a retrace taxonomy — visibly distinct, and DRL's
  artifact discloses non-standalone context the same way (`group_pulse`
  `tier=display, authority=context_only` precedent).
- **Stocks hub** (`engine/stocks_hub.py` boards): descriptive %/vol boards,
  no residual math — the band is additive display real estate, no analytical
  overlap. Movers boards carry no buy-edge authority
  (DNR:KILL-FRESH-BUY-EDGE); the band inherits that law.
- **Prophet US:** RS-vs-benchmark convention only; no peer-basket regression
  exists there; DRL never feeds the graded board population
  (DNR:KILL-PROPHET-POP-MERGE).
- **Open PRs:** #5204 (peak-chain falsifier gates) and #5197 (us-basket-turn
  synapse readers) are the nearest lanes; neither touches the files above.
- **Reuse commitments:** LSR-P0 panel/residual machinery (imported),
  `market_drivers.snapshot()` day vocabulary, house `pos52` convention,
  `engine/ledger_lane.py` gating, `transmission_chains` episode pattern,
  `engine.group_flow._causal_z` z convention where new z fields appear.
