# PROPHET US — W8 IGNITION LAYER (BY FABLE)

**Date:** 2026-08-05 · **Trigger:** operator-directed brainstorm converted to instruments.
**Parents:** `research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` (§0 fast-track
evidence doctrine, inherited verbatim) and
`research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (the funnel repair whose
§0 gates this charter also inherits).
**Instruments:** `research/prophet_us_audit/ignition_standins.py` ·
`research/prophet_us_audit/ignition_standins_results.json` ·
`tests/test_ignition_standins.py` (31 tests).

---

## §0 Status — what this document may and may not do

**RESEARCH / SHADOW TIER. Nothing in this charter touches admission, ranking, sizing,
gating, alerting, or any site surface.** The instruments are measurements. The four sensors
below are named S-COIL, S-RANKVEL, S-THRUST-LAG and S-INSIDER; none of them is a signal,
none has a score, and none is wired to anything.

Every sensor routes through the same ladder, in order, with no step skippable:

> **display → shadow-door → prereg → operator ruling**

A sensor that measures well here has earned a *shadow door* — a forward-accruing,
independently-graded boolean — and nothing more. Promotion to any authority (rank, size,
gate) requires its own preregistration and its own operator ruling, on the gauntlet's
terms, not this document's.

Two house laws bind this charter tightly enough to restate:

- **No composite, ever.** Not across sensors, not inside a sensor's own reporting. Each
  sensor is graded alone. The intersection cohort in §3 is a *filter with its own n*, never
  a weight, a blend, or a score. (DO_NOT_REBUILD §1: fused composites in any scored path.)
- **The gauntlet is a PROMOTION gate, not a build gate.** A null does not block accrual.
  Display-tier context accrues freely; the discipline applies at the moment something asks
  for authority.

---

## §1 The physics frame, and the constraints already measured

### 1.1 The frame

A move has three phases, and the repo has historically confused them:

| Phase | Question | What it looks like on a tape |
|---|---|---|
| **Storage** | is potential accumulating? | volatility compresses, range tightens, supply is absorbed quietly |
| **Ignition** | did the stored potential release? | the range breaks, participation broadens, rank changes fast |
| **Continuation** | does the release persist? | the move extends and holds rather than reverting |

The funnel repair (W0–W6) was mostly about *continuation* — sighting and counting names
that had already run. This charter asks the harder question one phase earlier: **is
ignition detectable at all, or is it only ever labelled after the fact?**

### 1.2 The constraints this program has already measured — binding, not decorative

These are the fences. A new ignition sensor that contradicts one of them is wrong until it
explains the contradiction.

1. **Continuation is priced.** Names the board already marks as having run are not free
   money. *(Commissioner-supplied figure: "stage-ran 14.5% / 27.6%".* **Provenance
   RESOLVED (commissioner annotation, 2026-08-05): the figure is
   `research/prophet_us_audit/label_grading_battery_results.json`
   §section_3_ran_lane.a_stage_ran_from_ledger (PR #4547, armed but UNMERGED when this
   charter branched — a checkout-lens artifact, not a missing measurement). Its basis is
   `entry_status` values bucketing to STAGE_RAN — there is deliberately no "stage" column
   in retro_grades; the flag's column search was the wrong lens. n=55, H=10, loser 14.5%
   vs 27.6% rest-of-buy, no half-split flip. The original caution stands in one respect:
   anything downstream should cite the #4547 artifact once merged, not this prose.
   leans on it.*)

2. **Generic ignition is a measured null.** The S-D relay-position stand-in
   (`relay_position_standin.py`, the #4506 CN port) found relay position does not separate
   on the US frame, and the entry-family comparison in
   `research/prophet_us_audit/RESULTS_2026-08-03.md` found the **fresh-cross chase loses**:
   the leader pullback-reset family printed −1.50% pooled / −2.12% per-name (n=938, 45.8%
   win) against the incumbent's +0.15% / +0.63%. **S-RANKVEL below independently reproduces
   and sharpens this** — see §2.2.

3. **Only two motion features survived the fingerprint kills, and they are the ONLY
   volume/motion seeds this charter may use.** From `research/winners/FINGERPRINT_CONTROLS_W4.md`
   (adjudicated 2026-07-22):
   - `realized_vol_63d` — **+11.6 gate-matched, α/m-clean**
   - `updown_dollar_vol_ratio` — **+0.13, α/m-clean**

   Both are **motion-not-quality**: they precede breakaway *motion* and hold for blow-offs;
   `updown_dollar_vol_ratio` fails on the `kept_going` split. Either one's promotion needs a
   fresh prereg AND must clear the **gate-matched t0−1 ruler**; the full-population t0
   effect sizes are known-inflated and **may not be cited as the effect size**.

4. **Two constructions are CLOSED and may not be re-proposed as pre-onset fingerprints or
   watchlist rankers:** `dollar_vol_z21` and `dv_5_60_ratio`. They are onset-bar +
   selection-gate artifacts — episode median `dollar_vol_z21` is 1.99 at t0 but **0.67 at
   t0−1**, and only **27.4%** of matched controls pass the detector's own volume gate. Both
   go NULL at α/m once controls are gate-matched AND the onset bar is excluded
   (`[−0.026, +0.374]` and `[−0.024, +0.136]`). *(Cited by rule content, not row number —
   registry row numbers have rotted.)*

   **Consequence for this charter: S-COIL carries no volume leg at all.** ESX RUL-1 also
   stands — volume-confirmation confirmers are dead (H4), and volume may appear only inside
   S-SQ's own release confirmation.

---

## §2 The four stand-ins

**Frame.** `data/baskets/ohlcv/*.parquet` — **2,768 US tickers, full OHLCV, 2014-01-02 →
2026-07-31 (3,163 sessions)**, split- and dividend-adjusted (verified equal to
`data/yahoo/` adjusted close on AAPL/KO/XOM). Benchmark `data/yahoo/SPY.parquet`.

**Coverage receipt — the brief's assumed frame does not exist locally.** The #4561
`close_panel()` over `data/massive_stock_day` (~2,252 columns) is **not merged** (it lives
on `origin/claude/prophet-us-scan-tier`, tip `5bb16b514f1`), and that store's parquets are
**R2-only** — `.gitignore:246` excludes them and the checkout holds just `_manifest.json`
and `_backfill_state.json`. Rather than fall back to the three breadth caches, this battery
uses a frame that is both **wider and far deeper** than the merged alternatives:

| Frame | Names | Span | Available? |
|---|---|---|---|
| `data/baskets/ohlcv` **(used)** | **2,768** | **2014-01-02 → 2026-07-31** | yes, git-tracked |
| 3-tier breadth union | 1,540 | 2023-06-27 → 2026-07-31 | yes |
| breadth ∪ yahoo overlay | 1,897 | mixed | yes |
| #4561 `massive_stock_day` | 2,252 | 2021-07-06 → 2026-07-28 | **no — unmerged + R2-only** |

**Named coverage debts (stated, not resolved).** The store is **survivor-lean** — of 120
sampled names, 119 carry bars to the final session, the same debt W4 carried. Forward
windows overlap (a name may fire repeatedly inside 63 sessions); the month-block bootstrap
is the time control, per DT-R14, which forbids ticker-cluster CIs *without* one.

**Ruler (W4 gate-matched).** Every sensor's primary statistic is a matched-set delta:

```
delta = excess(event) − median(excess(matched controls, SAME session))
```

aggregated as the median over events, with a **month-block bootstrap** whose resampling atom
is the matched set (primary, and the conservative one — 133–148 months vs 2,453–2,728
tickers), plus a **ticker-cluster bootstrap** as the recurrence check. Controls are
gate-matched per sensor: they pass the same trigger and differ only on the axis under test.
Outcomes at H = 10 / 21 / 63 sessions, read three ways (raw, excess vs SPY, excess vs the
same-day cross-sectional median). `loser := excess < −3pp`. Cells under n=20 print n only.
Pinned `REPRO_ASOF = 2026-07-31`, seed 20260805, 2,000 bootstrap draws.

---

### 2.1 S-COIL — compression → expansion transition

**Construction.** Compression = trailing-21d ATR percentile vs own 252d **< p25** AND close
> 50dMA AND 50dMA rising over 10 sessions. Event = **first close above the prior 21d high**
after ≥10 compressed sessions in the trailing 21. **The compression state is read at t−1**,
so the release bar's own range can never enter the ATR window that admits it — the W4
onset-bar lesson applied structurally.

**Controls (gate-matched).** Same-session names printing the *same* first-close-above-prior-
21d-high **without** the compression run. Both arms clear the breakout gate; only compression
differs.

**Kills-check — this is the constrained sensor, and the constraints changed the design.**

- The compressed/"armed" state is **never surfaced or graded standalone**. That is the
  **arming variant, BANNED by ESX §9 / DT-R5** ("the inside/armed state is the BANNED arming
  variant"). This instrument grades the **release bar only** — which is precisely the
  distinction ESX drew when it authorized S-SQ: *"S-SQ differs mechanically: it acts only on
  the confirmed release bar … confirmation vs anticipation."*
- **DURABLE_BOTTOM H2 falsified "calm-quiet-base arming"** — the aged quiet base showed the
  programme's worst stop-outs (46–48%). H2 measured a calm base **after a washout**. S-COIL
  requires price **above a RISING 50dMA**, placing it in the continuation regime H2 did not
  test. That distinction is the sensor's entire licence to exist, and it is stated rather
  than assumed.
- Distinct from the **bottom-radar PRIMED** kill (a directional durable-bottom gate for
  starter size, killed on all three pre-registered legs). S-COIL is an uptrend coil, not a
  bottoming construction, and confers no size.
- **Collision, named: species S16 (S-SQ squeeze-release) OWNS this construction** and has
  been ACCRUING since 2026-07-07. S-COIL is a **stand-in on a different frame, not a parallel
  authority.** Any promotion runs through S-SQ's registered species. Volume carries no leg.

**Fire counts** (dead-leg diagnostics): 523,778 compressed name-days → 467,892 with the
≥10-session run → 437,494 breakout days → 287,665 *first* breakouts → **25,277 events**, and
**262,388 gate-matched controls**. Every leg is live.

**Matched-set delta vs gate-matched controls** (pp, excess vs SPY):

| H | Δ | month-block CI (primary) | ticker-cluster CI | per-name Δ | n | names | months | halves | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 10 | +0.12 | [−0.02, +0.27] | [+0.06, +0.20] | −0.02 | 25,241 | 2,468 | 136 | +0.06 / +0.21 | **NULL** |
| 21 | +0.24 | [−0.00, +0.53] | [+0.12, +0.38] | −0.00 | 25,196 | 2,467 | 136 | +0.10 / +0.45 | **NULL** |
| 63 | +0.98 | [+0.42, +1.55] | [+0.68, +1.26] | +0.53 | 24,989 | 2,453 | 133 | +0.42 / +1.62 | **EXCLUDES 0** |

**Verdict: NULL at the entry horizons, POSITIVE at the swing horizon.** The compression that
precedes a breakout adds nothing measurable over an uncompressed breakout at 10 or 21
sessions, and about **+1pp at 63 sessions**, sign-stable across both time halves.

Two honesty notes that cut against the positive:
- **Per-name-first roughly halves it** (+0.98 pooled → +0.53 per-name at H63; at H10/H21 the
  per-name figure is ≈0 or negative while pooled is positive). Part of the pooled effect is
  name recurrence, exactly what per-name-first exists to expose.
- The month-block CI is **wider** than the ticker-cluster CI at every horizon, because 133
  months is a smaller atom count than 2,453 tickers. The month-block CI is the one cited.

---

### 2.2 S-RANKVEL — cross-sectional acceleration

**Construction.** RS percentile = cross-sectional PIT rank of the 63d return, computed per
session. Event = percentile gains **≥ +20 points over 5 sessions** AND **crosses above p70**.

**Controls (level-matched).** Same-session names within **±5 percentile points of the
event's own level** that did **not** accelerate (5-session change < +5 points). The axis under
test is the **derivative**, so the level is held fixed — otherwise the comparison merely
re-measures momentum.

**Kills-check.** R-4 ("rs is zero-sum tautology") is scoped to **member-dispersion gates**
and donor→recipient rotation pairs, where donor rs-repair and recipient rs-fade are the same
accounting identity. A per-name rank *derivative* graded against level-matched controls is
not that construction, and nothing here gates. The nearest measured prior is W4's
`rs_turn_21_63`, which was **NULL** pre-onset (α/m [−0.175, +0.222]) — a different
construction, and a null here would be a second strike on the rs-derivative family rather
than a repeat of one.

**Fire counts:** 6,819,291 covered name-days → 340,634 acceleration days, 2,047,419
at-level days, 368,208 level crossings → **151,474 events**, level-matched pool 1,448,260.

**Matched-set delta vs level-matched controls** (pp, excess vs SPY):

| H | Δ | month-block CI (primary) | ticker-cluster CI | per-name Δ | n | names | months | halves | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 10 | **−0.57** | [−0.80, −0.35] | [−0.65, −0.49] | −0.44 | 150,814 | 2,728 | 148 | −0.71 / −0.38 | **EXCLUDES 0, NEGATIVE** |
| 21 | **−0.80** | [−1.15, −0.47] | [−0.93, −0.68] | −0.59 | 150,260 | 2,726 | 148 | −0.96 / −0.60 | **EXCLUDES 0, NEGATIVE** |
| 63 | **−1.98** | [−2.57, −1.40] | [−2.26, −1.69] | −1.37 | 147,470 | 2,707 | 145 | −1.82 / −2.19 | **EXCLUDES 0, NEGATIVE** |

**Verdict: REFUTED, and refuted in the informative direction.** Cross-sectional acceleration
into p70 is priced **worse** than sitting at the same rank without having accelerated —
significantly so at all three horizons, negative in **both** time halves, negative on
per-name-first, and monotonically worse as the horizon lengthens.

This is the sharpest result in the battery. It is not a null; it is a **measured cost to
chasing the derivative**, on 151k events across 2,728 names and 148 months. It independently
reproduces constraint §1.2(2) — "fresh-cross chase loses" — from a completely different
construction and a 12.5-year frame, and it is the second strike on the rs-derivative family
after W4's `rs_turn_21_63` null.

**Robustness — the obvious matching artifact, checked and excluded.** The shipped control
pool requires `pct ≥ p70`, which truncates the ±5-point band from below for events sitting
just above p70 and could in principle manufacture the sign. Re-running with a **symmetric
pool** (any level, the ±5-point band alone doing the matching) reproduces the result almost
exactly: −0.56 / −0.81 / −1.86pp against the shipped −0.57 / −0.82 / −1.87pp, identical CIs
to the second decimal. The negative is a property of the derivative, not of the pool
construction.

**Standing consequence:** rank acceleration must not be proposed as an ignition signal. If it
is ever surfaced, the honest reading is *"this name is accelerating — historically that has
been a reason to wait, not to chase."*

---

### 2.3 S-THRUST-LAG — theme thrust → coiled laggard

**Construction.** Theme = curated basket from `data/baskets/membership.json` (**36 curated
baskets**; the 11 `us_sector_` GICS pseudo-baskets are excluded because they are not
curation), PIT `added`/`removed` honored, ≥6 covered active members. Thrust = the fraction of
active members above their own 20d high crosses **from < 0.30 to > 0.50 within 5 sessions**.
Candidate = a member **below** its own 20d high carrying **S-COIL compression** at thrust.

**Two control arms**, because they answer different questions:
- **(a) already-moved** — members of the **same basket** above their 20d high at thrust.
  *Should I buy the laggard or the leader inside a thrusting theme?*
- **(b) coiled-nonthrust** — compressed, below-20d-high names in themes **not** thrusting that
  day. *Does theme context pay at all?*

**Kills-check.** Composes the measured laggard-cross positive (`RESULTS_2026-08-03`: the same
cross on RS63 ≤ 0.40 laggards printed **+0.33% pooled / +1.44% per-name, 52.0% win**, against
the leader-reset family's −1.50% / −2.12%) with theme context. It creates **no rotation
surface** (`sector_rotation_schedule.v1` is DO-NOT-BUILD) and **no parallel authority** beside
the suspended Ignition Radar — see §4.

**Fire counts:** 35 baskets read, **466 thrust events**, **228 coiled-laggard candidates**,
4,294 already-moved controls, 23,544 coiled-nonthrust controls.

**Arm (a) — vs already-moved members of the same basket** (pp, excess vs SPY):

| H | Δ | month-block CI | ticker-cluster CI | per-name Δ | n | names | months | halves | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 10 | +0.24 | [−0.40, +0.97] | [−0.35, +0.95] | +0.12 | 228 | 144 | 31 | +0.81 / −0.32 | **NULL** |
| 21 | −0.22 | [−1.04, +0.90] | [−1.12, +1.00] | +0.15 | 226 | 144 | 30 | +0.27 / −0.54 | **NULL** |
| 63 | +0.39 | [−1.37, +2.42] | [−1.43, +2.09] | −0.38 | 221 | 143 | 28 | +0.21 / +0.68 | **NULL** |

**Arm (b) — vs coiled names in non-thrusting themes** (pp, excess vs SPY):

| H | Δ | month-block CI | ticker-cluster CI | per-name Δ | n | names | months | halves | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 10 | +1.31 | [+0.64, +1.95] | [+0.64, +1.95] | +1.17 | 228 | 144 | 31 | +1.54 / +1.07 | **EXCLUDES 0** |
| 21 | +2.04 | [+0.79, +4.21] | [+0.83, +3.11] | +2.51 | 226 | 144 | 30 | +2.47 / +1.69 | **EXCLUDES 0** |
| 63 | +4.67 | [+2.29, +6.41] | [+2.41, +6.25] | +4.54 | 221 | 143 | 28 | +4.97 / +4.05 | **EXCLUDES 0** |

**Verdict: the two arms disagree, and the disagreement IS the finding.** The coiled laggard
does **not** beat the already-moved members of its own theme (null at every horizon, and the
half-split sign-flips at H10 and H21 — unstable). It **does** beat coiled names in
non-thrusting themes, strongly and sign-stably.

The honest reading: **the theme context is what pays, not the laggard-versus-leader choice
inside the theme.** "Buy the laggard in a hot theme" is not supported here; "a coil inside a
thrusting theme is worth more than the same coil outside one" is.

**Thin-cell disclosure, load-bearing.** n=228 across 144 names and 28–31 months is an order of
magnitude thinner than the other two sensors. Arm (b) is also the *looser* comparison — a
228-event treatment against a market-wide 23,544-name pool — while arm (a), the tightly
matched same-basket comparison, is the null one. **Prefer the null.** This sensor is the
weakest-powered in the battery and the least entitled to a door.

---

### 2.4 S-INSIDER — cluster accumulation · **NAMED GAP, NOT RUN**

**Kills-check outcome: this construction matches a kill, so per the charter's own fence it
becomes a named gap rather than a run.** The detector is built, unit-tested, and censused;
**no outcome is graded.**

**Why.** The briefed construction — a cluster of ≥2 distinct open-market insider buyers,
graded forward at H=10/21/63 against **sector-matched** controls — collides with the
`esx_insider_sponsor` family (DO_NOT_REBUILD §2, *"Entry-time thesis at 21d (insider / macro
/ positioning) — REFUTED 3-for-3"*, RUL-18..29):

- That study tested the **same core predicate** — I1: cluster ≥2 distinct open-market buyers
  on filing-date windows; I1-sens ≥3; I2: cluster ≥2 around the fire — at the **same primary
  horizon (21d)**, on 38,250 / 113,542-fire panels.
- Its finding was **not a plain null**. Unconditional insider strata were **adverse**
  (I1 baskets stop5 **+6.22pp, CI [+4.90, +7.37]**, BH-rejected), and the **I1w** reserve
  contrast attributed that adversity to the **washout state**, not to the cluster
  (within-washout marginal **+0.5pp, CI [−0.8, +1.8]**, n_treat = 3,815).
- **The decisive methodological point is exactly what sector-matching would miss:** controls
  must hold the **co-occurring state** fixed, not merely the sector. Sector-matched controls
  would re-estimate the state, reproduce the adverse sign, and read as a discovery. Running
  it would also spend a contrast the family has explicitly closed (*"no re-run of these
  contrasts"*).
- A second row, *"Insider × T2"*, kills the T2-tier pairing specifically (#1781). This
  charter proposes no such pairing.

**Coverage census (what the store would support, for whoever writes the prereg).**
`data/sec_insider/panel/*.parquet`: **2,314,291 rows, 16,834 tickers, filing dates
2006-01-03 → 2026-03-31**, of which **402,006** are open-market purchases (`code == 'P'`; the
collector keeps only P/S and drops grants, exercises and gifts). The detector finds **35,797
cluster events across 9,435 names**, of which **10,916 events / 2,086 names** fall on this
battery's price panel. **Coverage debt: the insider panel ends 2026-03-31, four months short
of the price panel's 2026-07-31.**

Two conventions the census pins, because getting either wrong silently changes the answer:
- **PIT = `filing_date`, never `trans_date`** (RUL-23 known-date law; the store's median
  filing lag is 2 trading days, and `trans_date` additionally carries 21 corrupted rows with
  two-digit-year mis-parses).
- **Distinct buyers are counted on `rptownercik`** — the key `engine/insider_factor.py` uses.
  `context_api._insider_dim` **does not dedupe by insider** (it is a plain 90-calendar-day
  transaction/dollar roll-up), so it is the wrong reader for a cluster construction. One
  insider buying four times is not a cluster; a unit test pins exactly this.

**Lawful re-entry paths** (none claimed here, each needs its own prereg and lane owner):
1. the **63/126d holdability lane**, coordinated with `esx_ql_overlay` / S-QL per RUL-20;
2. the **252d long-hold ruler** `long_hold.insider_sponsor_lh` (Ruler-H, ~2027-H2);
3. **display-only** `sponsor_present`-style context, which carries no ranking authority.

Any of these must use **state-matched**, not sector-matched, controls — that is the single
transferable lesson from I1w.

---

## §3 The intersection-lens law

**No composite is ever formed — not across sensors, not inside one.** Sensors are surfaced,
if ever, as **independently-graded booleans** ("chips"), each carrying its own verdict and
its own forward grade. A name lighting three chips is not a name with a score of three.

The **intersection** is a **cohort filter with its own n**, graded as its own table. It is
what the lens sees, and the miss-audit grades that cohort — never a blend.

**Measured (backward-only window, ≥2 distinct sensors within a trailing 5 sessions):**

| H | n | names | median excess vs day-median | per-name | win% | loser% |
|---|---|---|---|---|---|---|
| 10 | 4,033 | 1,960 | −0.03 | −0.03 | 49.7 | 30.6 |
| 21 | 4,026 | 1,959 | +0.08 | +0.11 | 50.3 | 35.9 |
| 63 | 3,993 | 1,945 | +0.29 | +0.78 | 50.6 | 42.0 |

Composition: 3,953 S-COIL+S-RANKVEL, 59 S-COIL+S-THRUST-LAG, 21 S-RANKVEL+S-THRUST-LAG, 6
triple.

**Verdict: the intersection is a null.** Co-firing confers nothing — the weak positive coil
and the negative rank-acceleration roughly cancel. That is the correct and useful answer: it
falsifies the intuition that stacking sensors concentrates edge, and it is precisely the
result a composite score would have hidden by construction.

### 3.1 A defect this instrument found in itself — recorded because the number was seductive

The first run reported the intersection at **+6.59pp median with an 87.3% win rate at
H=10**. That was **not a finding; it was lookahead.** The cohort was assembled with a
**symmetric ±5-session** window, so an observation could be stamped on a session up to five
days *before* the sensors fired. Because every sensor here is a breakout or acceleration
event, "a sensor will fire within five sessions" is very nearly "the price rose within five
sessions" — the cohort was selected on its own outcome.

The corrected construction uses a **backward-only** window and stamps the observation on the
session the **second distinct sensor fires**, so all sensor information is knowable at the
observation date. The corrected numbers are the table above. **The inflated numbers are
reported nowhere else in this charter or in the results JSON**, and two unit tests
(`test_intersection_window_is_backward_only`,
`test_intersection_is_stamped_when_the_second_sensor_fires`) now pin the defect so it cannot
return silently.

The general lesson, worth carrying: **an implausibly good cohort statistic is a bug report
until proven otherwise.** An 87% 10-day win rate is not an edge any equity sensor produces;
it was the shape of the error that made it findable.

---

## §4 Ignition Radar reconciliation — census, not a re-surface

**This section reports the accrued record. It re-surfaces nothing.** The commissioner brings
any re-surface packet to the operator; that is not this charter's to do.

**The 2026-07-23 suspension** (DO_NOT_REBUILD §4) moved Ignition Radar's user-facing surfaces
to background-only while the engine and nightly self-grading keep accruing. Re-surface
requires **all** of: (a) ≥30 graded calls with an acceptable broad TP rate, (b) event-sector
exclusion for narrow themes, (c) an honest-null "nothing igniting" state, (d) an operator
ruling.

### 4.1 What the record actually contains

**First, a correction to the registry's own pointer.** DO_NOT_REBUILD §4 cites
`data/ignition_radar/` as the accrual location. That directory holds exactly two files —
`latest.json` (a single day's display snapshot) and `narrow_streak.json` (a 5-entry streak
cache) — and **neither contains any grading history**. The actual forward-grading ledger is
**`data/ignition_log/us_ignition.jsonl`**, written by `engine/ignition_audit.py`.

**The ledger:** 20 rows, 2026-07-11 → 2026-08-03.

| Gate | Requirement | Measured | Status |
|---|---|---|---|
| (a) graded calls | ≥30 | **0** (`graded_broad` null on 20/20; `graded_narrow` null on 20/20) | **0/30 — FAIL** |
| (a) broad TP rate | acceptable | **undefined — no denominator exists** | **FAIL** |
| (b) event-sector exclusion | present | **absent from code** | **FAIL** |
| (c) honest-null state | present | **partial** | **PARTIAL** |
| (d) operator ruling | present | not sought | **not met** |

**The gate is NOT met, and (a) is not "short of 30" — it is zero.**

**Why zero, and when that changes.** Grading is gated on forward maturity, not on a bug: the
broad arm's primary gate is h63 and the narrow arm's is h40, while only ~16 business days
have elapsed since the earliest logged call. **First possible grade: ~2026-09-04 (narrow),
~2026-10-07 (broad)** — approximate business-day arithmetic, not the NYSE holiday calendar.
The clock is real rather than blocked.

**Three findings the raw count hides:**

1. **Only 14 of the 20 rows are distinct market reads.** Six rows (2026-07-13, 07-18, 07-19,
   07-26, 08-01, 08-02) are byte-identical in every content field to the row before them —
   the pipeline stamps `asof` from `date.today()` and dedupes only on that string, so a
   weekend run re-logs Friday's data under a new date label.
2. **A 3-weekday gap: 2026-07-22, 07-23, 07-24 have no row at all** — a window containing
   **2026-07-23, the exact date of the Mag-7 forced-call incident and the suspension**. The
   data alone cannot distinguish outage from lane-gate; flagged for the operator, not
   diagnosed here.
3. **The narrow arm has no success criterion in code.** `_grade_us_narrow` computes raw
   excess numbers only — no `outcome` / TP field, unlike every other arm. **Even after h40
   matures, the narrow arm will not natively produce a TP rate**; someone must define the
   win rule. Gate (a) is therefore ill-posed for the narrow half as currently written.

**On honest-null (gate c), precisely.** The broad channel has a real `off` state (5/20 days),
the regime label has a real "No ignition" path, and the leader badge has a null guard. **But
the ranked `narrow.items` list is unconditionally sliced to the top 8 with no threshold
check** (`ignition_radar.py:1021`) — a genuinely dead tape still emits 8 ranked rows, each
correctly labelled per-item but still presented as a ranked table. The postmortem's
requirement ("no forced top-N ranking in a dead tape") is **only partially satisfied**.

**On event-sector exclusion (gate b).** Not implemented. A grep for event/geopolitical/
exclusion/single-sector logic across `ignition_radar.py`, `ignition_audit.py` and
`sector_ignition.py` returns nothing relevant. The `category` field is carried for display
and never read as a filter, so single-sector ETFs are scored and ranked on equal footing with
diversified thematic baskets — consistent with XLE holding a 9-session narrow-leader streak.

### 4.2 How S-THRUST-LAG's thrust relates to the radar's ignition — same family, different construction

Required by the no-parallel-authority rule, stated explicitly:

| | Ignition Radar (narrow channel) | S-THRUST-LAG thrust |
|---|---|---|
| Form | **weighted composite score**: 0.40×breadth + 0.40×RS + 0.20×MTF | **single-axis breadth crossing**, no score |
| Trigger | score ≥ 0.55 **and** `rs_turn > 0` | member fraction above own 20d high crosses <0.30 → >0.50 within 5 sessions |
| Output | ranked top-8 leaderboard | a boolean per basket-day |
| Universe | curated baskets **+ sector ETFs** | curated baskets only (`us_sector_` excluded) |

**Same family** — both read theme-level participation turning up. **Different construction** —
the radar blends three legs into a score and ranks; S-THRUST-LAG tests one unweighted
participation crossing and forms no score at all (which is also why it is compatible with
§3's no-composite law, and the radar's blended score is not a form this charter may adopt).

**Binding consequence:** S-THRUST-LAG must never become a second rotation surface. Its §2.3
result is in any case the battery's weakest — null against its tightly-matched arm — so no
promotion is on the table. **If it were ever proposed for a door, that proposal must
reconcile against the radar's own record rather than run beside it.** Today that record is
**zero graded calls**, so there is nothing yet to reconcile against — which is itself the
finding, and the reason a parallel surface would be especially indefensible right now.

---

## §5 Foresight lead-time study — SPEC ONLY, with a measured clock

**The brief anticipated that desk-stage history might not exist. It does — and it is still
not runnable. Both halves of that correction matter.**

**Census.** `data/foresight/log.jsonl` carries a genuine per-theme STAGE history: **122
rows, 25 distinct `asof` dates, 2026-07-01 → 2026-08-04, 18 themes, 39 stage transitions**
across 17 themes, with `stage`, `bottleneck_band`, `revision_breadth` and `members` per row.
Stage vocabulary observed: WATCH (50), BROADENING (33), RE-RATING (21), PRECIPICE (18). Of
123 member tickers referenced, **115 are on this battery's price panel** (93%).

*(Distinguish this from per-name Weinstein stages in `data/stage_analysis/`, which have **no**
PIT history at all — `stage_board_daily.json` is a current snapshot, `context/latest.json`
keeps a 1-day rolling diff that discards the day before, and `forward_ledger.jsonl` carries
no `stage` field. That store cannot answer "what stage was X in on date Y" for any past date,
and the 1-day diff is actively discarding the data such a study would need.)*

**Maturity — why the study does not run today:**

| H | last date with a matured forward window | matured transitions |
|---|---|---|
| 10 | 2026-07-17 | **33 / 39** |
| 21 | 2026-07-01 | **0 / 39** |
| 63 | 2026-04-30 | **0 / 39** |

**Verdict: SPEC ONLY — do not run.** Only H=10 has any matured transitions, and 33
transitions across 17 themes spans roughly **one month** — below the month-block bootstrap's
own requirement of ≥3 distinct months, which is this battery's primary estimator. At H=21 and
H=63 the count is literally zero. Running it now would produce a number with no inferential
content and a citation that would outlive its own recompute.

**Frozen spec, for the run when the clock matures:**

- **Question:** does a theme's foresight STAGE transition lead its members' price, and by how
  much?
- **Event:** a stage transition in `data/foresight/log.jsonl`, stamped on its `asof`.
- **Unit:** the theme's PIT `members` list at transition, mapped to the price panel.
- **Outcome:** equal-weight member forward excess vs SPY and vs the same-day cross-sectional
  median, at H = 10 / 21 / 63.
- **Controls:** same-session non-transitioning themes, matched on prior stage — the transition
  is the axis, so the starting stage must be held fixed (the I1w lesson from §2.4, applied
  before the fact rather than after).
- **Lead-time read:** transition date minus the date the member basket's own price
  participation crossed the S-THRUST-LAG threshold — signed, so a *negative* lead is honestly
  a lag.
- **Estimator:** the §2 ruler unchanged — month-block bootstrap primary, ticker-cluster as the
  recurrence check, per-name-first beside pooled, half-split.
- **Gate to run:** ≥3 distinct months of matured transitions at the horizon being read, and
  ≥30 transitions at that horizon. **Earliest plausible first read: H=21 around 2026-09, H=63
  around 2026-11**, accrual-dependent.
- **Standing caveat:** 18 themes is a small cross-section; effective n is themes-and-months,
  not transitions. State it in the report rather than discovering it in review.

---

## §6 Ship order

| # | Item | State |
|---|---|---|
| 1 | Charter + instrument + results + 31 unit tests | **this PR** |
| 2 | Recompute or retract the "stage-ran 14.5% / 27.6%" figure (§1.2.1) | **open — provenance unresolved, blocks any downstream use** |
| 3 | Fix the DO_NOT_REBUILD §4 pointer: the radar's accrual is `data/ignition_log/us_ignition.jsonl`, not `data/ignition_radar/` | open, one-line registry correction |
| 4 | Define the narrow arm's success criterion in `ignition_audit._grade_us_narrow` | open — without it, gate (a) is ill-posed for the narrow half |
| 5 | Investigate the 2026-07-22..24 radar ledger gap and the 6 duplicate weekend rows | open, operator-facing |
| 6 | Re-read the radar gate after ~2026-10-07 (first broad h63 maturity) | clock, not a task |
| 7 | S-COIL H63 result → reconcile with species **S16 / S-SQ**, which owns the construction | open — route through S-SQ, never a parallel door |
| 8 | S-RANKVEL → **no door.** File the negative as a standing constraint | closed by this charter |
| 9 | S-THRUST-LAG → **no door** on current evidence (null vs its matched arm, n=228) | closed pending materially more data |
| 10 | S-INSIDER → prereg on the 63/126d holdability lane with **state-matched** controls, coordinated with S-QL (RUL-20) | open, needs a lane owner |
| 11 | Foresight lead-time study (§5) | spec frozen; run gated on maturity |

**Nothing in rows 7–11 is authorized by this document.** Each needs its own preregistration
and its own operator ruling.

---

## Appendix — reproduction

```
python3 research/prophet_us_audit/ignition_standins.py     # ~105s, full 2,768-name panel
python3 -m pytest tests/test_ignition_standins.py -q       # 31 tests
```

Pinned `REPRO_ASOF = 2026-07-31`, seed 20260805, 2,000 bootstrap draws. Set
`IGNITION_LIMIT=<n>` to run a subset of the panel for a fast smoke test. Results are written
to `research/prophet_us_audit/ignition_standins_results.json`, which carries the frame
receipt, every fire count, and every cell reported above.
