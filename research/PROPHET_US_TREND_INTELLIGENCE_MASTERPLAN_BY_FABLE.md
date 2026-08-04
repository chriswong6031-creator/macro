# PROPHET US TREND INTELLIGENCE — MASTERPLAN (BY FABLE)

**Date:** 2026-08-03 · **Trigger:** operator complaint ("sector_central knows software is the
leading theme, we hold the member maps, yet Prophet US surfaces almost none of it; US picks are
garbage while CN picks are very good; PLTR reported today +10% and was never surfaced; we need
Prophet to detect heating sectors early, analyze members, and produce higher-return picks").
**Evidence instruments:** `research/prophet_us_audit/runner_exclusion_audit.py` +
`leader_reset_study.py`, frozen results in `research/prophet_us_audit/RESULTS_2026-08-03.md`.
All numbers below are reproducible from committed caches (price data through 2026-07-31).

This masterplan is the adjudicated answer to that complaint: a full-funnel audit with receipts
(§2), a ranked root-cause diagnosis (§3), and a build program (§5) that rewires what already
exists before inventing anything new. It deliberately does NOT propose loosening the anti-chase
vetoes wholesale — §2.5 measures that idea and it fails.

---

## §0 ACCEPTANCE GATES — binding on every build wave spawned from this plan (inline in prompts)

- **G0.1 (no silent authority).** Every wave labels each surface/key it ships as one of:
  `display` / `ops-telemetry` / `shadow-accrual` / `scored`. Anything `scored` cites either an
  existing Grade-A measured ruling (`research/US_BOARD_MEASUREMENT.md`) or a fresh prereg that
  cleared its gate. A PR that moves a key between tiers without that citation is not done.
- **G0.2 (miss telemetry is the spine).** W0's nightly miss-audit artifact must exist and be
  green for 5 consecutive nightlies before any W3+ scored change merges — we never again tune
  gates without the instrument that shows what they exclude.
- **G0.3 (case-receipt proof).** A wave that claims to fix a §2 case (PLTR-class, MSFT-class,
  DLB-class, PANW-class) reproduces that case in its PR body from the shipped artifact — not
  from prose.
- **G0.4 (population fences).** `us_board_ledger` graded population changes ONLY via
  operator-ratified adjudication (DNR §1 row 49 restated). Shadow lanes grade in their own
  ledgers; the live board's buy membership stays byte-identical until a flip is ratified.
- **G0.5 (kills respected).** No wave re-ranks by 2D-freshness (#1513), re-blends
  conviction×timing (row 49), forces un-gauntleted directional calls to surfaces (row 117 /
  Mag-7), builds per-name outcome-audition gates (row 69), or claims pre-onset winner
  identification (rows 114-115). §6 lists the full fence set.
- **G0.6 (bilingual + design law).** User-facing surfaces follow DESIGN_DOCTRINE + glance-tier
  word budgets; no internal study names front-facing; falsifier language stays background
  (operator 2026-07-27).

---

## §1 The complaint, restated precisely

Four distinct failures are bundled in the operator's report. They have different mechanics and
different fixes, and conflating them is how previous attempts (Mag-7 forced board, killed
2026-07-23) went wrong:

1. **Origination miss** — the market's actual winners never enter the candidate stream
   (PANW +85%/63d: zero eligible days in the entire quarter).
2. **Conversion miss** — winners the gate DID flag never become picks
   (102 of the top-150 runners printed an eligible day; 2 became plans).
3. **Narration miss** — picks the system made and held are invisible to the operator
   (PLTR-BULL-20260701 was live through today's earnings pop; the operator believed PLTR was
   never surfaced).
4. **Context miss** — the system's own theme-heat intelligence (software = #1 of 41 themes)
   never conditions any of the above (zero pick-chain consumers).

"US picks are garbage" is the visible sum of these four, printed through a US tape that is
momentum-led and narrow while the incumbent entry family is a washout-resumption detector —
the same detector that is genuinely thriving on China's mean-reverting tape.

---

## §2 Evidence (receipts)

### 2.1 The tape vs the board (2026-08-03)

- `site/marketdata/subsector_rotation.json` (asof 2026-08-02): **Software is the #1 theme**
  (emerging_score 3.271 of 41 themes); **Software>Enterprise is the #1 subsector of 269**
  (3.835; members WDAY MSFT INTU SAP CRM ROP ORCL), AI>Enterprise #2 (3.825). The heat engine
  works.
- `site/factordata/us_standouts.json` (asof 2026-07-31): buy lane n=71, sector-capped at 10;
  top of board = SHOO (shoes), NUE (steel), PI, KWR (chemicals), ELAN. IT rows: PI NET PATH
  APPF BDC PLAB PEGA U DLB CRSR — value-tech and washouts, not the leading cohort. The leading
  cohort sits in display-only lanes: SNOW PANW OKTA CRWD in `leaders` ("watch, don't chase",
  explicitly never fed to Prophet — `engine/prophet_bridge.py:231-233`), MSFT in `ran`.
- Plans originated in the last week (site/prophet/plans): AVNT LPG **GME** TEAM NSSC **ARLO**
  CWK OLED EPAC BAH **CLF×2** CDW SFM CASY CSR **BDC×2 PI×2 JBLU** SHOO FLS KWR. The #1 theme
  contributed TEAM and arguably CDW. Duplicate originations (CLF, PI, BDC twice within days)
  burn nightly intake slots (dedup key is `<TICKER>-<DIR>-<signal_date>`, so every new
  signal_date re-originates).
- `dispersion_regime` on the same artifact: state **"lean_in"**, dispersion 75th pctile —
  the system itself prints "selection pays" — display-only.

### 2.2 Runner-exclusion audit (the gate side)

Top-150 US names by 63-session return (universe = S&P 1500 caches, n=1493 with ≥200d history),
evaluated at 2026-07-31 via the production `confluence_tiers` code path:

| Excluder (today) | n/150 |
|---|---|
| not_topped veto — `stoch_bear+macd_bear` | 42 |
| not_topped veto — `stoch_ob` | 36 |
| not_topped veto — `stoch_ob+stoch_bear` | 27 |
| not_topped veto — `macd_bear` | 21 |
| not_topped veto — `stoch_bear` | 9 |
| not_topped veto — all three | 2 |
| freshness_expired | 5 |
| rsi_cap_on_fresh_cross | 1 |
| **ELIGIBLE today** | **7** |

- **137/150 (91%) of the quarter's best performers are veto-excluded today**; the 7 eligible
  are the mean-reversion-shaped runners (CRSR GEN DXCM KSS HPQ DRH JBLU).
- Over the whole trailing 63 sessions: **48/150 never printed a single eligible day**
  (PANW +85%, DDOG +103%, DELL +94%, OKTA +93%, FTNT +92% — all zero). Median eligibility
  window for the rest: **3 sessions of 63**.
- Of the fast movers (top-50 by 21d return): 43/50 are stoch_ob-family vetoed — momentum
  leaders live in "overbought" by construction, so the absolute-oscillator veto reads a hot
  theme as permanently unbuyable.
- Sector mismatch: today's 38 cascade-eligible names skew Consumer Discretionary (9);
  the 150 runners skew Health Care (41) + IT (37). 18 of 37 IT runners never printed an
  eligible day.

### 2.3 The funnel side (conversion + narration)

- **Sighting→plan conversion: 2/102.** 102 of the top-150 runners had ≥1 eligible day in the
  last 63 sessions; exactly two (KSS, JBLU) ever became Prophet plans. The gate sees most
  winners once — a fresh cross usually fires near the run's start — and the funnel then loses
  98% of them inside a 3-day median window.
- **Plan intake sorts by the measured-worst key.** `prophet_bridge.select_candidates()`
  (engine/prophet_bridge.py:218-273) filters `band != low` + act-level and then sorts by
  `conviction.score` desc, capped at N_CANDIDATES=12/night. `research/US_BOARD_MEASUREMENT.md`
  (Grade A): board-order P@1 0.20 vs alpha-order 0.60; "Primary sort key: order by residual
  alpha (or an alpha+timing blend at the very top). NEVER by … composite." PR #4331 fixed the
  DISPLAY ordering (us_prophet_v1 priority score); intake still runs on the anti-predictive
  composite — `prophet_bridge` never reads `row["prophet"]`.
- **The closed-plan record is the honest harsh number.** `data/prophet/ledger.jsonl` holds
  16 real closed plans: 9 EXPIRED, 6 INVALIDATED, 1 T1_HIT — **win rate 12.5%, avg
  −5.03%, median −5.51%**. (Board-level 10-session marks look far better — h10 win 64.9%,
  +1.89% avg excess — but `us_track_history.json` itself prints `effective_n=1` overlap
  caveats; the two measures must never be quoted interchangeably.) Nine deaths by EXPIRY
  means most picks didn't stop out — they went nowhere for 45 sessions: chop-shaped intake,
  exactly what a washout detector feeds in a trending tape.
- **MSFT case (narration/retention):** eligible 6 days from 2026-07-16, +15.9% forward from
  first eligible day, then freshness-expired → silent through its 99.9th-pctile week
  (POSTMORTEM_20260803 covered the display half; the pick half remains: nothing re-arms).
  MSFT sits in `ran` today with `theme_confirmed:true`, +15.5% since cross — correctly
  narrated at last, still not pick-capable.
- **PLTR case (narration):** plan `PLTR-BULL-20260701` (entry 130, conviction 90, T1 168.9)
  was live and "hold" through today's earnings (+~10% on 2026-08-03) — the operator believed
  PLTR was never surfaced. The plan sat at management_confidence 32.9, phase
  `triggered_pre_t1`, human_state "Stalling", buried in a 93-plan index (65 originated in
  July; no total-active cap, no aging surface). On the BOARD, PLTR appears nowhere: its
  7/01 cross is stale, and `above200:False` (as of 7/30) structurally excludes it from the
  leaders lane too — its only trace is a `themes_in_favour` membership chip. Prophet made
  the call, held it a month, and got no credit anywhere the operator looks.
- **DLB case (conversion):** the operator's cited winner ("DLBY" — no such ticker exists
  anywhere in the repo; DLB, Dolby Labs, is the board row and the assumed intent). In the buy
  array (tier T1, now stage `ran`) but **never a plan**: conviction 29 "neutral" + act_level 1
  fails the intake filter, and its residual-alpha percentile is 0.014 with
  `alpha_entry="laggard"` (edge leg = 0), so no ordering fix alone would have admitted it
  either. Washout winners enter through a leg that both current sort keys bury.
- **Earnings are only ever a suppressor.** The one earnings consumer in the chain is the
  blackout hygiene veto — and PLTR's earnings row (`next_date=2026-08-03`, correct) carried
  `as_of=2026-06-19` (1361/1364 rows frozen), so even the veto was a stale no-op. Nothing in
  the chain can ANTICIPATE a catalyst (pre-earnings chip, post-earnings continuation).

### 2.4 CN vs US: same detector, different diet (operator hypothesis CONFIRMED)

Admission-day character (all T1/T2 eligible days, trailing 90 sessions, 400-name samples):

| Market | trailing-63d return at admission (median) | drawdown from 252d high (median) |
|---|---|---|
| CN | **−7.0%** | **−22.9%** |
| US | +0.9% | −12.4% |

China feeds the fresh-cross detector deep washouts bound for mean reversion — the construction
IS a washout-resumption detector and the CN tape is its native habitat (CN eligible today 199
vs US 107 on a comparable universe). The oft-cited CN record — win 68.6% [59.8–78.8], +2.68%
expectancy, PF 1.82, n_matured 407 — belongs to the *superseded* `cn_standout_v1` era (closed
book); live `cn_prophet_v2` has 0 matured rows. The era caveat does not weaken the regime
point: that record was earned by the same fresh-cross family on a mean-reverting tape. The US
tape currently pays continuation and theme leadership, which the same construction
structurally cannot admit (§2.2). Neither market is misconfigured; there is ONE entry family
where the market demands two.

Surfacing divergence compounds it: CN partitions **every** eligible row into a labeled lane
(featured 24 / more_actionable 110 / late_or_unfillable 16 / forming 49 — nothing eligible is
ever invisible, `engine/china_board_rank.py:631-745`), while the US ships a flat capped buy
list plus spillover; the US-only `_WIDE_PER_SECTOR=10` pre-cap is BINDING today on 5 of 11
sectors (exactly-10 counts), a cap CN does not have at the membership level.

### 2.5 The obvious fix is wrong (measured)

"Just loosen the vetoes / buy leader dips" — measured over the last 126 evaluable sessions
(H=21, excess vs same-day universe median, full universe):

| Family | n | median excess | per-name median | win% |
|---|---|---|---|---|
| Leader pullback-reset (RS63≥0.8, >50dMA, fresh 2D cross, NO veto) | 938 | **−1.50%** | **−2.12%** | 45.8 |
| Incumbent T1/T2 eligible-day | 18,097 | +0.15% | +0.63% | 50.7 |
| Same cross, RS63≤0.4 laggards | 1,994 | +0.33% | **+1.44%** | 52.0 |

The not-topped veto was DOWN on 692/938 of those leader-reset fires — i.e. per-fire, the veto
is earning its keep on exactly the cohort a naive "unblock the leaders" patch would admit.
(Exploratory, in-sample, pooled-overlap caveats apply; direction is decisive enough to fence
the design.) The winners we miss are not recoverable by deleting the anti-chase machinery —
they must be caught by DIFFERENT doors: theme-conditioned broadening (laggard crosses inside
hot themes are the one positive cell), re-arm after reset, and catalyst confirmation.

### 2.6 What is built but unwired

Confirmed zero pick-chain consumers (grep across build_stock_library / us_board_rank /
prophet_bridge / signal_gate / entry_signal): `subsector_rotation` (the #moving engine),
`sector_central`, `basket_turn_watch` (K-of-N basket ignition), `basket_turn_cohort`,
`basket_score`, `basket_mtf`, `sector_signals` (validated SPDR engine), `us_sector_rotation`
(the CN rotation ranker's US port, docstring "DISPLAY-ONLY"), `bottom_radar`, `mtf_upturn`,
`adaptive_trend_signals`, `rotation_events`. The two that do cross (`sector_pulse`,
`anticipation`) are stamped display-only. Theme context reaches the board as chips with
"zero score authority"; the ONE live theme number is `LEADERS_THEME_BOOST=0.5` inside the
display-only leaders lane. Five intelligence layers — theme heat, entry timing, edge, events,
regime — exist and never compose.

Two shipped-dark receipts sharpen the point: the us_prophet_v1 `runway` leg read **0 on all
71/71 rows** of the 07-31 board (builder calendar-mixing bug, since fixed per the
us_board_rank docstring), and the anti-chase mechanism is an explicit shadow —
"label only, ZERO enforcement", `flip_eligible=False` on every ledger row. The priority
engine's legs can ship dark for days because nothing measures the board against the tape —
which is what W0 exists to end.

---

## §3 Root causes, ranked by measured impact

1. **RC1 — Conversion collapse (2/102).** The funnel behind the gate (double verb-gate →
   conviction-sorted 12-slot intake → duplicate churn) loses ~98% of sighted winners. Largest
   single lever; needs no new signal, only already-measured rulings applied.
2. **RC2 — Origination monoculture.** One validated entry family (washout-resumption) in a
   continuation tape; 48/150 runners never admissible in principle; hot-theme members
   permanently "overbought". Needs new DOORS (shadow-first), not a loosened old door.
3. **RC3 — Theme intelligence unwired.** The system detects the leading theme (and even
   "selection pays" dispersion) and none of it conditions candidacy, priority, surfacing, or
   the operator's view of why names are absent. Also the postmortem engine already measured
   `sector_headwind` systemic among losers — the tailwind mirror is unbuilt.
4. **RC4 — Narration/retention gap.** Live winners (PLTR plan) invisible; expired sightings
   (MSFT) never re-arm; 93-plan index with no aging/pruning; the operator cannot see what
   Prophet knows, so correct calls read as misses.
5. **RC5 — Event blindness.** Earnings only suppress (and are stale); no catalyst
   anticipation or post-catalyst confirmation family despite full calendar coverage.
6. **RC6 — No missed-winner learning loop.** Postmortems autopsy picks; nothing autopsies
   MISSES. Tonight's audit had to be written by hand; it must run nightly.

---

## §4 Design principles

- **P1 — Rewire before invent.** Every wave first composes organs that already exist
  (subsector_rotation, basket_turn_watch, ran lane, prophet_live, postmortem engine).
- **P2 — Display ships freely; authority passes the gauntlet.** New context and telemetry go
  live immediately (house epistemics); anything touching picks/rank/size cites a Grade-A
  ruling or a fresh prereg (G0.1).
- **P3 — Doors, not dilution.** The incumbent family keeps its tight window and vetoes (the
  measurements defend them per-fire). New intake comes from NEW doors with their own ledgers:
  theme-relay, re-arm, catalyst. Each door is graded separately from day 1.
- **P4 — The operator must see what the system sees.** Every absence gets an attribution
  ("PANW: veto-excluded (stoch_ob) — leaders lane"), every live thesis gets a pulse. Detection
  without narration is a repeat-class defect (Mag-7 postmortem).
- **P5 — CN stays untouched.** Its record is the control group proving the machinery works
  when regime matches family.

---

## §5 The program

### W0 — Miss-audit + conversion telemetry engine (ops-telemetry; build first)
Productionize `runner_exclusion_audit.py` as `engine/prophet_miss_audit.py` + nightly artifact
`data/prophet_miss_audit/latest.json` (+ forward log):
top-decile runner exclusion histogram, eligibility-window + sighting→plan conversion,
theme-representation latency (days from theme top-5 heat → first member on buy/ran/featured),
per-case attributions for the week's top movers. Feeds prophet_governor status +
an admin/Calibration-Lab block (below the fold, honest-tier). **Gate:** G0.2 (5 green
nightlies). No authority anywhere. *Routing: builder (opus), 1 PR.*

### W1 — Plan-intake repair (scored; cites existing Grade-A measurement)
Three surgical changes to `prophet_bridge`, each independently disclosed in the PR:
1. **Sort by the shipped us_prophet_v1 priority score** (row["prophet"]["score"], the
   operator-ratified alpha+timing blend) instead of raw `conviction.score` — completes the
   US_BOARD_MEASUREMENT Conf-A ruling the board already implements; one ranking system
   everywhere. Conviction band filter stays (population unchanged; ordering only).
2. **Duplicate-churn fix:** an open plan on the same ticker+direction blocks re-origination
   while active (today CLF/PI/BDC each burned 2 of 12 slots in one week).
3. **Index hygiene:** total-active-plan surface cap with age-tiered pruning of the DISPLAY
   index (plans keep grading; the page stops drowning in 93 rows) + "originated N days ago,
   thesis playing out / stalled" pulse line per plan (fixes PLTR invisibility).
**Operator sign-off required (scored change), then default-arm.** DNR row 49 untouched: the
buy population is unchanged; only ordering among already-admitted candidates and display
hygiene move. The 9-of-16-EXPIRED closed-plan pattern also feeds the standing exit-policy
study (H=10 incumbent unbeaten in-sample, cap-63 family untested — PROPHET_LEARNING_LOOP):
re-run it as the ledger matures; W1 changes intake, not exits. *Routing: builder (opus) +
reviewer (opus). Follow-up prereg (not in this PR): DLB-class washout admits — measure whether
act_level≥2/band filters forfeit board winners (the miss-audit will count them nightly).*

### W2 — Theme spine wired into surfacing (display-tier; ships freely)
1. **Theme Tape on the Prophet index + us_stocks board:** the top-5 heating themes
   (subsector_rotation, PIT archive as source-of-truth) each rendering their member states
   from the CURRENT board artifact: in-buy / ran / setting-up / leaders / veto-excluded
   (with plain-word reason). The software case becomes: "Software>Enterprise #1 — 2 members
   on board, 4 ran, 5 excluded (overbought)" instead of silence. Answers "so what do I do"
   under glance-tier budgets; zh parity.
2. **Theme context chips on every plan + pick** (tailwind/headwind at entry, from the same
   engine that the postmortem uses to grade sector_headwind — one vocabulary).
3. **Why-not attribution rows** for hot-theme members (near_miss_reason already computed in
   signal_gate W0.2 — surface it).
4. **Adopt CN's total-partition surfacing principle on US:** nothing eligible is invisible —
   every eligible row lands in a labeled lane with a stated reason (CN ships
   featured/more_actionable/late_or_unfillable/forming and drops nothing;
   `engine/china_board_rank.py:631-745` is the reference implementation). Membership and
   grading populations unchanged (G0.4); this is presentation partitioning only.
No rank/gate/size authority anywhere in W2. *Routing: designer (opus) for the surface,
builder (opus) for wiring; frontend-design skill + DESIGN_DOCTRINE mandatory.*

### W3 — New doors, shadow-first (shadow-accrual → prereg promotion)
All three doors accrue candidates nightly into a **door ledger** (bottom_ledger/washout_watch
pattern: forward-graded, policy-free, zero authority), each with a pre-registered promotion
gate (≥100 matured, ≥60td, stop%≤incumbent ∧ clean%≥incumbent at matched horizon) before any
plan-origination right:
- **Door T (theme-relay/broadening):** fresh incumbent-family crosses on members of top-K
  heating themes, WITHOUT the global 12-slot competition — the one construction §2.5 found
  positive (laggard crosses +1.44% per-name) intersected with theme heat. Uses the validated
  detector; the new part is only candidacy routing, so promotion is primarily a routing
  adjudication.
- **Door R (re-arm):** ran-lane names (intact trend, cross 3-15 ticks stale) whose 2D leg
  resets and re-crosses while the 3D stays constructive — the MSFT/PLTR-class re-entry. The
  theme_confirmed re-arm surface (#4331) is its display precursor; this door gives it a
  ledger and a promotion path instead of a chip.
- **Door E (catalyst confirmation):** post-earnings continuation on hot-theme members that
  beat + hold (gap-and-hold ≥1 session), the PLTR/PEAD shape. Requires W4's fresh feed.
  Explicitly NOT a pre-earnings directional call (row 117 fence).
*Routing: builder (opus) per door; prereg docs adjudicated in main loop; reviewer (opus) on
grading code. First promotion reads ~Q4 2026 at current fire rates — the doors surface as
display/watch lanes immediately (lawful), so the user-visible gap closes long before
authority does.*

### W4 — Event feed repair + anticipation display (display + data hygiene)
Un-freeze the earnings sweep (1361/1364 rows at as_of 2026-06-19 — #4341 started this; finish
and alarm it: a stale earnings store must page, not fail open silently), add
pre-earnings chips on board rows + Theme Tape ("reports in N days"), and a post-earnings
reaction column (day-0 move vs history). Display-only; Door E consumes the same feed in
shadow. *Routing: builder (opus).*

### W5 — Gate-parameter adjudications (scored; each its own prereg, operator-ratified)
Strictly sequenced AFTER W0 telemetry exists, so every change is measured against live
miss/false-admit rates:
1. **macd_bear veto leg:** `research/signal_engine/VETO_LEG_AUDIT.md` already measured it
   FAILING its pre-registered ≥+3pp keep rule (+0.8pp full-sample, −3.9pp since 2023-06,
   while blocking 83% of current-regime T2-shaped fires). Execute that verdict: operator
   ratification → remove the leg from `not_topped` for T2 admission (T1's own §7 filter
   untouched), with W0 watching the false-admit rate and an auto-revert tripwire.
   §2.5's leader-cohort result does NOT contradict this — that cohort is RS-top-quintile
   resets; the audit's cohort is T2-shaped fires, where the leg fails.
2. **FRESH_TICKS window:** rerun the 2→3→4 sensitivity (prior offline read: eligible
   75→86→106) under the §7 timing ruler with per-tier stop/clean deltas; adopt only if the
   pre-registered bar clears (US_BOARD_MEASUREMENT §5's "keep it tight" stands until beaten
   by measurement, not vibes).
3. **Dispersion-regime consumer:** promote `dispersion_regime` from display to ONE narrow
   authority — scaling N_CANDIDATES (12 ↔ 16) in lean_in vs lean_out — only after its
   passport gains a survivorship-clean measured edge (its own artifact currently says
   `survives: false`; respect that).

### W6 — Learning-loop closure (ops)
Postmortem engine gains the MISS taxonomy (mirror of the loser taxonomy): for each top-decile
runner each week — never_eligible(veto leg) / sighted_unconverted(funnel stage) /
converted_undernarrated. Monthly governor report joins misses × postmortems into tilt
preregs (the existing findings→prereg pipeline; never hot-patched weights). *Routing:
builder (opus); analysis adjudicated main-loop.*

---

## §6 What this plan deliberately does NOT do

- No un-gauntleted leadership/momentum board (row 117 — the 2026-07-11→07-23 failure class).
- No FRESH-BUY-as-edge re-ranking (#1513); the tight window survives until W5.2's prereg.
- No conviction×timing blended rank, no setups.json population merge (row 49).
- No per-name best-of-grid timing selection (row 69); doors are global constructions.
- No pre-onset winner-fingerprint claims (rows 114-115) — Door T conditions on THEME state,
  a cross-sectional context, and claims nothing per-name until its ledger matures.
- No washout-depth ranking (#1747 Amendment-3); Door R keys on trend-intactness + reset, not depth.
- No CN changes; no touch of the CN ledger eras (era-pooling trap).
- No LLM-originated signals anywhere (A7/CXI-R23).

## §7 Rollout, fences, collisions

- Order: **W0 → W1 → W2 → (W3 ∥ W4) → W5 → W6.** W0-W2 are one week of build; W3 doors accrue
  from the day they merge; W5 waits for G0.2.
- Collision fences: PSI program (PR #4404) owns portfolio-level health/score surfaces — this
  plan stays inside Prophet origination/surfacing; HK board (#4421) and SI Workspace V2
  (#4372) own their pages — Theme Tape lands on us_stocks + prophet index only; seasonality
  is Codex-owned (untouched); theme-mover publish lane (#4469) is marketing-side.
  **Buy Board 2.0** (`us_standouts_v2` dual-gate shadow, flip charter independent) is a
  challenger to the BOARD, not to intake — W1 touches prophet_bridge ordering only and leaves
  the v2 shadow's precision@k race untouched. prophet_live P0 (intraday re-probe of the same
  gate) is the cadence answer for the incumbent door; doors T/R/E stay nightly until their
  own ledgers justify intraday probes.
- Model routing per CLAUDE.md: Opus builds/reviews all waves; sonnet only for any census
  sweeps inside W0; main-loop Fable adjudicates preregs and promotion reads.

## §8 Pre-registered success metrics (graded by W0's artifact; baselines = 2026-08-03 audit)

| Metric | Baseline | Target (90 sessions post-W2) |
|---|---|---|
| M1 top-decile-runner sighting rate (≥1 surfaced day incl. ran/leaders, trailing 63s) | 68% (102/150; eligible-only basis) | ≥85% incl. new lanes |
| M2 sighting→plan conversion on those runners | **2%** (2/102) | ≥15% |
| M3 theme latency: top-5 theme → first member featured/live/ran on board | weeks (software: unmeasured, > 20 sessions) | ≤5 sessions |
| M4 plan-cohort outcomes (closed-plan ledger, real management) | **12.5% win, −5.03% avg, 9/16 EXPIRED** | improving vs baseline cohort; graded, not promised |
| M5 duplicate originations per week | 3 (CLF/PI/BDC) | 0 |
| M6 operator-visible attribution coverage (hot-theme members with a stated reason) | 0% | 100% |

M4 is the honest headline: it may lag the others by a quarter of maturation — the plan
commits to grading it, not to a number. Everything else is mechanical and lands fast.

---

*Related: PROPHET_MASTERPLAN_BY_FABLE.md (program charter), PROPHET_BOARD_PRIORITY_ENGINE
(#4331), PROPHET_LEARNING_LOOP (postmortem/exit machinery), PROPHET_LIVE_INTRADAY (cadence),
US_BOARD_MEASUREMENT.md (the measurement canon this plan repeatedly cites),
POSTMORTEM_20260803_MAG7_RALLY_SILENCE (the narration failure class), VETO_LEG_AUDIT.md
(W5.1's evidence), WASHOUT veto program Lanes B/D/E (the shadow-lane pattern W3 reuses).*
