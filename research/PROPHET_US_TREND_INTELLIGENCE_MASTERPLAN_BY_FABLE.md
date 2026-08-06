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
  operator-ratified adjudication (DNR:KILL-PROPHET-POP-MERGE restated). Shadow lanes grade in their own
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
**Operator sign-off required (scored change), then default-arm.** DNR:KILL-PROPHET-POP-MERGE untouched: the
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

### W7 — Show ALL ranked picks + remember the score (operator amendment 2026-08-05)

**Operator order, verbatim intent:** *"That rule where we only introduce 6-12 picks to the
board … isn't that an awful rule cuz then we have less data to train on. We should be using
the scoring system like China, adapted so it fits the US market, so that best picks are
surfaced to the top, but we should show all picks, for data as well as for users."* And:
*"we should be remembering the score that we give picks, so that it can be logged into the
ledger and so that we can later assess how robust and correct our scoring system is."*

The order has two halves and they are answered separately. **What is SHOWN** and **what is
GRADED** both widen to the full universe; **what is PICKED does not change**. Board
admission, plan intake (12/night), the gates and the score construction are untouched by
this wave — any admission-width change is a separate future adjudication (§W7.5).

#### W7.1 — The board becomes a VIEW over the ranked universe

The 6-12 number was never a data-collection decision; it is the *plan-origination* cap
(`prophet_bridge.N_CANDIDATES`), and the board's buy lane is itself a display slice. The
system already forms an opinion on the whole universe every night — it simply threw most of
it away at the surface. W7 makes the ranked universe the substrate and the board a lens over
it:

- The **single source of truth** is the US Context Vector store
  (`data/us_prophet_rank/candidates/YYYY-MM.parquet`, merged #4540): the full universe
  (~1,579 real names in this checkout, ~2,932 on the host), one row per name per night, with
  the `us_prophet_v1` priority-score legs already itemized per row. The operator's "remember
  the score" is therefore **already accruing** — this wave makes it consumable and graded,
  it does not re-log it.
- **Curated lanes stay** — featured / buy / ran / leaders / laggards remain exactly as they
  are, re-expressed as *views and filters* over the ranked list rather than as the only
  thing that exists. This is the CN total-partition principle W2.4 already adopted, carried
  to its conclusion: nothing the system evaluated is invisible.
- The **user surface** is specified in §W7.4 and built by a separate designer lane against a
  frozen contract (`research/US_ALL_PICKS_SURFACE_CONTRACT.md`).

#### W7.2 — Two graded populations, never pooled (the era law, restated)

This is the fence that makes the amendment lawful:

- The **graded CURATED record** — `us_board_ledger` / the board's buy-lane track record —
  is **UNCHANGED by this program**. Its population, its membership and its era boundaries
  are byte-identical after W7 as before. It continues as its own labeled cohort.
- The **full-population record is NEW and separately labeled**:
  `data/us_prophet_rank/grades/YYYY-MM.parquet`, accruing beside the curated one, never
  merged into it, never quoted interchangeably with it. It is a different population
  answering a different question, and §2.3's warning about board-level marks vs the
  closed-plan ledger applies here with full force: **two measures, two names, never one
  number.**

**DNR §1 row 49 adjudication (2026-08-05, operator-ordered).** Row 49 forbids any change to
the `us_board_ledger` graded population from a non-board lane, and any blended
conviction×timing ranking. Both fences hold: W7 changes NO membership, adds NO composite
(the itemized `us_prophet_v1` legs are read off, never re-weighted), and touches the curated
ledger not at all. The all-picks record is a **new, separately-labeled population authorized
by this operator order** — it accrues in its own store, under its own schema
(`us.prophet_grades/v1`), with zero authority over rank, gate, size, board or plan. A future
proposal to *pool* the two, or to let the all-picks record confer board rights, remains
forbidden and needs its own adjudication.

#### W7.2b — The universe widens: curated + scan, two cohorts, never pooled

Two further operator ratifications on 2026-08-05 change what this program grades. **Both are
recorded by the sibling lanes that own them, in their own dated subsections — this plan
cross-references rather than restates them:** the §4.5 scan-tier full universe
(`research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` §4.5 — *"a liquidity-floored
SCAN tier … board ADMISSION untouched … see everything, admit selectively"*), and the
measured lowering of the 200-bar indicator floor (owned by the signal-engine lane;
`confluence_tiers.MIN_HISTORY` and the floor constants are that lane's files, not this one's).

For W7 the consequence is exactly one thing: **the record now has two populations, and they
are never pooled.**

- **CURATED** — fully analyzed, board-admissible. Its graded record is the one that already
  exists and it is unchanged (§W7.2).
- **SCAN** — seen and stamped over the widened universe, **never board-admitted**. A new,
  separately labeled cohort, and the reason the scan tier exists at all: "see everything,
  admit selectively" only pays if what we see is graded.

Every grade row carries a `universe_tier` discriminator, and every statistic in the scorecard
— including **the median a "hit" is measured against** — is computed *inside* one cohort.
That last point is not pedantry: judging a curated pick against a median dominated by
thousands of scan names would flatter it by construction, which is the same
comparing-across-measures error that once manufactured a −69% "miss" out of a +0.7% beat.

#### W7.2c — Horizons: a 10-day headline grades the wait, not the call

Operator ruling 2026-08-05, on VALE (admitted "bottoming") and NEM: *"they take time to
base… but our board only measures for 10 day results??"* A basing-class pick and a
momentum-class pick are different bets, and one 10-session ruler systematically punishes the
first. The lawful fix is measurement, not a re-labelling of the record:

1. **The ladder widens to H=10 / 21 / 42 / 63.** H=63 covers a quarter, which is where the
   metals-cycle intuition lives. Adding maturities changes nothing else — same ruler, same
   freeze key, same idempotency; a longer horizon simply matures later.
2. **Signal class comes from labels that already exist.** `engine/cycles.py::STATE_DISPLAY`
   is the board's own vocabulary (BOTTOMING / NEARING A LOW / UPTREND / BUY ZONE / …); W7
   maps it to `basing` / `momentum` / `other` and carries the class onto each grade row.
   **Nothing new is stamped anywhere.** An unmapped label classes `other` with the original
   label preserved on the row, so a vocabulary that grows stays visible in the store.
3. **The chartered-horizon map is PRE-REGISTERED — fixed now, before any H=42/63 data
   exists.**

   | class | headline horizon | supporting |
   |---|---|---|
   | `basing` | **H=63** | H=21 |
   | `momentum` | **H=10** | H=21 |
   | `other` | H=10 | H=21 |

   Every class is graded and reported at *every* horizon, so nothing is hidden. The map fixes
   only which horizon is a class's **headline** read — because "grade each class at the
   horizon that flatters it, chosen after seeing the results" is precisely the sin this
   design must make impossible. It ships inside the nightly artifact
   (`priority_score_scorecard.chartered_horizon`) so it can be audited against later.
   **PROPOSED pending commissioner adjudication.**
4. **The headline record is UNTOUCHED (era law).** The existing H=10 record continues exactly
   as it is; the class-conditional view accrues *beside* it as measurement. **Any future
   redefinition of the headline horizon is its own dated operator adjudication, taken only
   once the long-horizon data actually exists** — never as a side effect of this wave.

The display half — a "still basing — day n of its chartered window" state, so a −10% day-8
basing row reads fairly — is **not** in this wave; it belongs to the track-dialog lane and
follows separately.

#### W7.3 — What was built (this wave)

1. **Full-population forward grader** — `engine/us_prophet_grades.py` +
   `scripts/grade_us_prophet_candidates.py --nightly`, declared in `config/dag.yml` between
   `build_site` (which stamps tonight's candidate rows) and `run_prophet_miss_audit` (which
   reads the result). Grades **every stamped row** across the **H=10/21/42/63 ladder, excess
   vs SPY** as rows mature: ~6.3k graded rows a night instead of ~12 today, ~41k once the
   scan tier lands. Nightly-lane-gated
   (`ledger_lane.nightly_advance_enabled` is the first statement of the append,
   mutation-checked in the suite), idempotent (a graded
   `(stamp_date, ticker, board_definition, horizon)` is frozen), policy-free (fixed-horizon
   marks only — no stops, exits or sizing), **zero authority**. The ruler is *reused, not
   forked*: `engine.grading.forward_metrics`, pinned mark-for-mark against
   `grade_prophet_doors.grade_flag`.
2. **Scoring-robustness scorecard** — the W0 miss-audit artifact gains a
   `priority_score_scorecard` block (same ops-telemetry tier and anti-fork idiom as
   #4537's `name_score_scorecard`: it *reads* the grade store, it recomputes nothing).
   Structured **cohort → horizon → class**, so nothing pools: per cohort and horizon,
   rank-IC by date, P@k at k=1/5/10/25, a decile lift table, and the **loser rate by score
   decile** — the operator's "it would be a disaster if high-scored names underperform" —
   plus a per-signal-class read at every horizon so basing at H=63 sits beside momentum at
   H=10 with their ns. There is deliberately **no top-level pooled leg** for a reader to
   misquote across populations. Nulls are printed with plain reasons while maturity accrues.
3. **A comparator the plan-only record could never have.** Because every name is graded, a
   pick's *hit* is judged against **that night's whole universe median**, not against the
   picks alone. "Did this beat a name drawn at random that night" is now a computable
   question, and the population leg reports the buy lane's excess against the universe it
   was drawn from.

**Honest coverage receipt (measured, not assumed).** `us_board_rank.score_rows()` is run by
the builder on the **buy lane only**, so the priority score and its legs are populated on
**~3.2% of stamped rows** (`data/us_prophet_rank/README.md`, 2026-07-31 dry run) — and the
live board agrees from the other side: on `site/factordata/us_standouts.json` (as_of
2026-07-31) `prophet.score` is present on all 60 buy rows and **null on all 74
watch/leaders/laggards rows**, while `alpha` is present on all 134. The
scorecard therefore computes its *ranking* legs (rank-IC / P@k / deciles) on the scored
subset and its *population* leg on everything, and prints the coverage percentage rather
than treating a missing score as a zero. The surface contract carries the same disclosure.

#### W7.4 — Surface contract (frozen; designer lane builds against it)

`research/US_ALL_PICKS_SURFACE_CONTRACT.md` freezes the fields, ordering, states, pagination
and honest-labelling rules for the ranked all-picks surface, so the designer lane builds
against a contract rather than a guess. Its load-bearing constraint is the coverage receipt
above: **the full universe cannot be ordered by a score that exists for 3.2% of it**, so the
contract specifies an explicit, disclosed tiered ordering rather than pretending to a single
ranked column. The graded-record split (curated vs all-picks) is named on the surface itself.

#### W7.5 — Named follow-ons (NOT in this wave)

- **Widening the score to the full universe is a SCORED change, not a display change.**
  `us_board_rank.score_rows` computes the `edge` leg from `alpha_percentiles(pool)` — a
  cross-sectional percentile *within the scored pool*. Running it over 1,579 names instead of
  ~71 would move **every existing buy-lane score**, which is a rank change under G0.1 and
  needs its own prereg + operator ratification. Until then the contract's tiered ordering is
  the honest surface, and the scorecard measures the score where it exists.
- **Admission width** (the 12/night intake cap, the `_WIDE_PER_SECTOR=10` pre-cap) is
  untouched and remains a separate adjudication.
- **CN gets the same treatment afterward** — a separate relay, explicitly not this wave
  (§P5: CN stays untouched; its record is the control group).

*Routing: builder (opus) for the data/grading half (shipped); designer (opus) for the
surface, against the frozen contract. Operator order 2026-08-05.*

---

## §6 What this plan deliberately does NOT do

- No un-gauntleted leadership/momentum board (row 117 — the 2026-07-11→07-23 failure class).
- No FRESH-BUY-as-edge re-ranking (#1513); the tight window survives until W5.2's prereg.
- No conviction×timing blended rank, no setups.json population merge (row 49). W7's
  all-picks record is a NEW separately-labeled population in its own store — it never
  pools with, and confers no rights on, the `us_board_ledger` graded population (§W7.2).
- No per-name best-of-grid timing selection (row 69); doors are global constructions.
- No pre-onset winner-fingerprint claims (rows 114-115) — Door T conditions on THEME state,
  a cross-sectional context, and claims nothing per-name until its ledger matures.
- No washout-depth ranking (#1747 Amendment-3); Door R keys on trend-intactness + reset, not depth.
- No CN changes; no touch of the CN ledger eras (era-pooling trap).
- No LLM-originated signals anywhere (A7/CXI-R23).

## §7 Rollout, fences, collisions

- Order: **W0 → W1 → W2 → (W3 ∥ W4) → W5 → W6.** W0-W2 are one week of build; W3 doors accrue
  from the day they merge; W5 waits for G0.2. **W7 (operator amendment 2026-08-05) is
  order-independent of W3-W6** — its grader accrues from the day it merges and its surface
  is display-tier, so it does not queue behind G0.2. Its own dependency is #4540: the first
  candidate stamp must land before the first grade can.
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

## §9 AMENDMENT 2026-08-05 — the indicator floor is the MEASURED warmup, not 200

**Operator ratification.** Operator order 2026-08-05: *"200 bar indicator floor, lets lift
this?"* — raised after receipts showed young names being refused a tier. This subsection
records the ratification, the arithmetic, and the population-change disclosure it requires.
Scope is the floor constant and its disclosure only; the universe/scan-tier lane and the
show-all charter lane amend elsewhere in this file and in their own programs.

**What changed.** `engine/confluence_tiers.MIN_HISTORY` 200 → **159**, and it is now
*derived* (`max` over the gating legs of `LEG_WARMUP_BARS`) rather than written down.

**The arithmetic.** Every leg's warmup was measured, not assumed, by truncating a series to
N trailing daily bars and asking whether the leg is non-NaN at the final bar. Basis: a pure
business-day index — the worst case, since holidays give a name *more* 2D/3D buckets per
daily bar, so a floor measured without them is conservative for every real ticker.

| leg | daily bars | gates | short of it, before this change |
|---|---|---|---|
| `rsi_ok` (3D RSI-14) | 43 | T2 T3 T4 | NaN → False → no tier at all |
| `k2_d2` / `recent2` / `fromos2` (2D stoch) | 63 / 65 / 77 | T4 | NaN → False |
| `k3_d3` / `recent3` / `fromos3` (3D stoch) | 94 / 97 / 115 | T2 T3 | NaN → False |
| `m2_s2` (2D RSI-MACD) | 155 | T2 T3 T4 | no cross, no bars-to-cross |
| `mb2` (2D MACD cross) | 157 | T2 | cross not computable |
| `imm2` (2D MACD projection) | 157 | T3 T4 | projection not computable |
| `imm2` ×2 (`CONFLUENCE_T3_PERSIST`=2) | **159** | **T3** | persistence not readable |
| `above200` (200dMA) | 200 | **T4 only** | now NULL + disclosed, never False |
| `m3_s3` (3D RSI-MACD) | 232 | nothing | veto's `macd_bear` leg **fails open** |
| `mb3` (3D MACD cross) | 235 | T1 raw fallback | T1 needs an explicit `take_date` |
| `wbull` (weekly RSI-MACD) | 391 | nothing | `confirm` falls back to its `fromos` arm |
| `htf_2w` (S1/S2 badges) | 776 | nothing | display badges read False |

**floor = max(gating legs) = 159.** T4 is deliberately excluded from that max: it self-gates
at 200 through its own `above200` leg, which is correct — a name with no 200-day average
cannot be graded "anti-falling-knife". The old 200 was a round number that matched no leg:
it locked out names whose T2/T3 legs were already live at 159, **and** admitted names whose
3D RSI-MACD was still NaN (232), leaving the not-topped veto's `macd_bear` leg silently
fail-open on every 200–231-bar name for as long as the floor has stood.

**Null-not-false.** `above200` is published as `True`/`False`/**`None`**, where `None` means
the 200-day average is not yet computable, with a plain-word reason in `null_legs`. The PLTR
narration-gap postmortem is the binding precedent: an `above200: False` stamped on an
unknowable value reads as "trading below its 200-day average" and excluded a live winner
from every lane that tests the field. `signal_gate` additionally *heals* the case where the
name's 200dMA **is** computable but `signal_quality` (which needs ~270 daily bars) returned
nothing — previously that left a null on a knowable value, and every `above200 is True` lane
dropped the name for a reason that was not true.

**Graded-population disclosure (DNR §49).** This IS a graded-population change: names with
fewer than the old 200 bars may now enter the curated board, which the DNR row on the
Top-setups data-lane merge forbids *from the trigger lane*. It ships here **only because the
operator ordered it**, and it is made separable rather than silent — every name tiering on
fewer than `YOUNG_HISTORY_BARS` (200, the pre-change floor) carries `young_history: true`
from the cascade through the signal-gate verdict, the board row's `confluence` block, the
slim buy verdict, and the `us_prophet_rank` candidates store. The graded record can
therefore always split the pre- and post-2026-08-05 cohorts; any forward measurement that
does not split them is reading two populations as one.

**Measured effect at ratification (2026-07-31 universe, 1,540 names).** Two names sit in the
newly-admitted band \[159, 200): SOLS (196 bars) and Q (191). **Neither becomes
tier-eligible** — every gating leg is computable at those counts, and both grade to no tier
for ordinary market reasons (Q has no 2D MACD cross in its history at all). So the floor
change admits *nobody* new to the board today; what it removes is a structural refusal that
would have been indistinguishable from a market verdict. 45 names remain below 159 bars,
where no tier is computable — including CDE (51 bars). A 35-bar listing cannot have a 2D
MACD cross history: that is arithmetic, not policy, and no floor change reaches it.

**The floor is not the binding constraint.** `scripts/build_stock_library._one` refuses a
library record below `min_days = 300` (`EXTRAS_MIN_DAYS = 252` for curated extras, which get
a LIMITED record instead), and `signal_gate.gate` is only called for names that got a
record. For every non-extra name the 300-bar library floor therefore dominates the cascade
floor, and lowering 200 → 159 cannot surface anyone until that floor or the universe lane
moves. The 300 is justified independently — the cycle ladder needs ~260 sessions — so it is
left alone here and flagged for the universe/scan-tier lane rather than changed in passing.

---

*Related: PROPHET_MASTERPLAN_BY_FABLE.md (program charter), PROPHET_BOARD_PRIORITY_ENGINE
(#4331), PROPHET_LEARNING_LOOP (postmortem/exit machinery), PROPHET_LIVE_INTRADAY (cadence),
US_BOARD_MEASUREMENT.md (the measurement canon this plan repeatedly cites),
POSTMORTEM_20260803_MAG7_RALLY_SILENCE (the narration failure class), VETO_LEG_AUDIT.md
(W5.1's evidence), WASHOUT veto program Lanes B/D/E (the shadow-lane pattern W3 reuses).*
