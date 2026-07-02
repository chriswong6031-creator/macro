# Durable-Bottom Entry Framework — the correct problem statement, measurement system, and hypothesis map

> **Companion to `CHARTER.md` — read that first; this document extends it, never overrides it.**
> Authored by Fable (2026-07-01) at the owner's request, after a full audit of the prior tuning
> campaign (`CONFLUENCE_TUNING.md`, `TIERED_CASCADE.md`, `GRID_GATE.md`, `research/ENTRY_QUALITY.md`)
> and the live gate (`engine/signal_quality.py`, `engine/confluence_tiers.py`, `engine/signal_gate.py`).
> Purpose: prior sessions repeatedly slid into round-trip buy/sell backtests graded on returns.
> This document pins the ACTUAL question so tightly that the wrong test is structurally hard to run.

---

## 0. TL;DR

1. The object we are hunting is a **durable bottom**: washout → trough → small perk-up → sustained
   liftoff. The gate's job is to fire **inside the perk-up window** — after the trough is in, before
   the liftoff has run.
2. We evaluate signals as **detectors of labeled bottom events** (precision / recall / lead) plus
   **count-fair per-fire outcome rates** (stop-out, clean-liftoff, dead-money). **Never** round-trip
   returns, **never** equity-curve drawdown of a trade sim as the primary verdict (that metric family
   produced the §5b exposure artifact), **never** beat-buy-and-hold.
3. There are **three distinct failure modes**, and every prior study conflated the first two and never
   measured the third: **(a) false bottom** (fires, price breaks to new lows — the stop-out),
   **(b) trap / dead money** (fires, price goes nowhere for months — Tencent), **(c) missed/late**
   (fires only after the move has run — the chase). A candidate is judged on all three axes at once.
4. The prior campaign varied the **trigger** (faster MACD TFs, trend/location guards). The unexplored
   frontier is the **setup state**: multi-timeframe washout depth/age/structure, participation
   (volume), and trap context. The headline architecture to test is the **ARMED-STATE detector**
   (§6): move selectivity out of the trigger's lag and into the setup conditions, so a fast trigger
   can be used without inheriting its false positives.
5. Everything already falsified stays falsified (§3). We do not re-run dead tests.

---

## 1. The object of study — anatomy of a durable bottom

The owner's description, made precise. A durable bottom has four phases:

```
   [WASHOUT]            [TROUGH]      [PERK-UP]                [LIFTOFF]
   sustained decline,   the durable   first small rise off     sustained advance;
   multi-TF oversold    low P0 at t0  the low; +0..~8% above   +20%+ within months,
   (2W..1D StochRSI     (never mean-  P0; volatility calm;     never re-tests P0
   pinned low)          ingfully      THE ENTRY WINDOW
                        broken again)
```

The gate exists to fire in the **perk-up window**. Firing during the washout is knife-catching
(failure a). Firing after liftoff is chasing (failure c). Firing on a bounce that isn't a durable
trough is failure (a) or (b).

**The three failure modes — each with its own metric (§4):**

| # | failure | what it looks like | cost to the owner | metric |
|---|---------|--------------------|-------------------|--------|
| a | **false bottom** | fire → price breaks below the recent low | −5% stop clipped | stop-out rate |
| b | **trap / dead money** | fire → months of chop, no liftoff (Tencent 2022-23: perpetual sub-50 2W stoch, MACD whipsawing on buybacks) | capital + attention parked; repeated small clips | dead-money rate |
| c | **missed / late** | no fire near the trough, or fire lands >8-10% above it | the expensive false negative (§9.3 of CONFLUENCE_TUNING: clean movers never surfaced) | recall + entry premium |

A detector that optimizes one axis by silently destroying another is exactly the historical trap:
the §5b location guards bought (a) by amputating recall (c); the fast triggers bought (c) by
inflating (a). **All three axes are reported on every experiment, always.**

---

## 2. Non-negotiable framing (inherited + new tripwires)

Inherited from CHARTER §2-§4 (still binding): risk tool not return engine; faithful RSI-MACD /
stoch-of-RSI math; detect-don't-predict; generalization is the only verdict; pre-committed kill
rules; no per-ticker parameter fitting.

**New tripwires specific to this program:**

- ❌ **Grading a conditioning idea on trade-sim equity drawdown.** That metric rewards trading
  less (the §5b exposure artifact). All rates in this program are **per-fire** (count-fair) and
  every result table carries **fire counts and event recall** next to the rates.
- ❌ **Reporting precision without recall.** A filter that fires 5× less and wins by 1pp is a
  worse tool (§9.3 watchlist asymmetry: false positives are cheap, missed movers are expensive).
- ❌ **Using the bottom labels as a trading input.** Labels are hindsight objects for EVALUATION
  only. Detectors must remain causal (leak-free known-date mapping, `tuning_harness.py` protocol).
- ❌ **Unregistered hypothesis mining.** The hypothesis list (§5) is pre-registered. Adding a new
  candidate mid-wave is fine — but it must be added to the list with a mechanism story BEFORE its
  first run, and the multiple-testing count it adds is acknowledged in the wave report.
- ❌ **Single-window evidence.** The prior campaign's entries started 2023-06 (one regime). This
  program labels and evaluates over the FULL deep-history panel (~2012-2026, all regimes), and every
  verdict must hold on both time halves (pre/post 2020) and both ticker split-halves.

---

## 3. Already established — build on it, never re-run it

| finding | source | consequence here |
|---|---|---|
| `base3d` beats every faster trigger on stop-out (38.3% vs 40.6-43.1%), location, and held-DD; the 3D lag is load-bearing selectivity | CONFLUENCE_TUNING §3/§9, TIERED_CASCADE | faster triggers are only viable if selectivity is REPLACED (→ armed-state, §6), not just removed |
| Earlier triggers ARE mechanically earlier (+3.7-4.9d, 1.5-2.6% cheaper, ~80% of the time) | CONFLUENCE_TUNING §3a (leak-free) | the earliness prize is real; the question is buying it without the FP tax |
| Trend/location guards (ATR-contraction, higher-low, efficiency, rising-50MA) = exposure artifact; killed on both held-DD and stop-out axes | CONFLUENCE_TUNING §5b/§9.2 | do not re-test trend guards; washout/participation/trap features are mechanistically different and ARE fair game |
| Shallow (>20) 3D stoch crosses stop out LESS than deep (<20) ones (36.1 vs 41.8), robust across halves and stops | TIERED_CASCADE §4 | recent violence predicts stop-outs. Reconciled with the washout thesis in §5-H2: HIGHER-TF washout depth + LOWER-TF calm is the hypothesized sweet spot — do not conflate the two scales |
| Proximity to the cycle low is the dominant forward-drawdown lever; staleness (>20d old cross) is the worst band | ENTRY_QUALITY.md (54k samples) | proximity/freshness enter as features of the perk-up window definition, not as return predictors |
| Near-low + fresh **anti-correlates** with forward return | ENTRY_QUALITY.md | durable-bottom detection will NOT rank winners. It times entries. Selection stays with alpha/sector engines (also #812: timing proxy has negative return-IC) |
| Reversal cut leg manufactures whipsaws (`cut_fwd` positive everywhere); faster reversal worse | CONFLUENCE_TUNING §8 | out of scope; nothing here touches exits (drawdown control is an entry problem — CHARTER §5) |
| T4's 200MA gate = frequency control, not per-event quality (+0.3pp stop-out on kept vs dropped) | TIERED_CASCADE §3 | trend gates don't discriminate per-event even on the stop axis; the trap axis (§5-H5) is where regime context must prove itself |
| ~38-43% stop-out at −5% is largely the mechanical floor of high-beta equities under a tight stop | CONFLUENCE_TUNING §9.4 | success ≠ 20% stop-out. Success = moving the SPREAD between conditioned strata, and the dead-money/recall axes |
| **The keeper's SELECTION is real; its CONFIRMATION-WAIT kills it.** Stop-aware walk-forward: the buy-filter's take-subset, entered at the RAW bar, stops out **29.4% vs 39.5% raw (better on 90% of names)** — but waiting for reclaim-and-hold fills ~2.4% higher and pays the whole edge back (filter passes on only 54% of names, below the 70% bar) | walk_forward.py `--gold`, HARNESS_USAGE.md | **the program's north-star number**: ~29% stop-out is the measured ORACLE ceiling for bar-t selection on this panel. The mission is reproducing that selection with CAUSAL features (§5-H0) and firing at the raw bar — the exact motivation for the COILED architecture (§6) |
| Raw washout DEPTH is a knife-risk, not a boost: >18% below 200MA → held21 36.9%, dd_p10 −22.5%; deep + still-falling → 29.6%. But deep + REVERSING → 55.7% (+26pp), and a weekly turn adds +19pp (68.4% vs 49.0%); 4-TF turn-confluence count is monotone (43.7→61.4%) | BOTTOM_CONFIDENCE.md Phase 1-2 (68,916 evals) | the user's thesis survives ONLY as a composite: washout × turn-evidence. Depth alone must never boost. NB: that study's "washout" = distance below 200MA, state-level, held21 @ 21d. Multi-TF STOCH washout, FIRE-conditional, on liftoff/126d-durability axes = still untested (H1) |
| Durability and blast-off are COMPETING axes: higher bottom-confidence bands hold 2× more but return LESS (63d ret 5.69%→3.57%); deep washouts bounce violently but rarely hold | BOTTOM_CONFIDENCE.md, ENTRY_QUALITY.md | no prior study measured the JOINT objective. This program's primary per-fire metric — P(+15% before −5%) — is precisely that joint number; expect washout strata to trade stop-outs for liftoffs, and judge the NET |
| Bottom-radar (durable = +8%/42d before swing-low break): score ranks durability (decile 51→61%) but E[R] inverts (BLOCKED beats PRIMED on small-caps); dead-cat veto failed; **NO-GO for sizing**, watchlist-ordering only | ANTICIPATION_ENGINE_DESIGN.md | a durable-bottom detector already failed as a SIZING tool. This program targets the GATE/WATCHLIST role (CHARTER-compliant) with a stricter durable definition (+20%/126d + no-new-low) and fire-conditional evaluation |
| "More oscillators and pure anticipation don't help; confirmation depth + orthogonal/higher-TF context do" | BOTTOM_CONFIDENCE.md Result 4 | no new oscillators in this program — only setup-STATE conditioning (washout structure, volume, trap context) on the existing triggers |

---

## 4. The measurement system

### 4.1 Labels (hindsight objects, evaluation only)

A **durable bottom event** at trough day `t0`, trough price `P0` (close-based), requires:

- **Washout precondition:** close drew down ≥ `DD_MIN` from its trailing 126d high into `t0`.
  Two label families, reported separately: `B15` (DD_MIN = 15%) and `B30` (DD_MIN = 30%).
- **Durability:** no close < `P0 × (1 − 0.03)` for the following `D = 126` trading days.
- **Liftoff:** close ≥ `P0 × 1.20` within `L = 126` trading days of `t0`.

A **trap bounce** is a trough meeting the washout precondition that FAILS durability or liftoff —
labeled separately (these are the events a good detector must NOT fire on; Tencent 2022-23 is a
string of them).

Sensitivity: every headline result is re-read at (tol 5%, liftoff +15%/+30%, D/L 189d) to confirm
no conclusion is a label-parameter artifact. Labels use dividend-adjusted closes (`data/stocks`,
`data/yahoo` — note `close` is total-return adjusted; fine, consistent on both sides).

**Panels & data notes (recon-verified 2026-07-01):**
- **Primary panel:** `data/stocks/*.parquet` — 223 deep-history US names, close/high/low/volume
  (no open), starts 1962-2001 (median 1984). Volume features (H4) run here. Entries evaluated
  from 2012-01-01 (full-regime coverage; warmup satisfied).
- **Generalization panel (wave 2+):** `data/baskets/ohlcv/` — 2,518 full-OHLCV names from 2014
  (filter to the 990 active members); survivorship check via the main checkout's
  `data/breadth/_closes_delisted.parquet` (199 dead names, close-only).
- **Survivorship honesty:** the primary panel is survivors-only, which inflates ABSOLUTE liftoff
  rates roughly uniformly; stratum-vs-stratum COMPARISONS remain informative (same caveat as
  ENTRY_QUALITY/BOTTOM_CONFIDENCE). Absolute rates are quoted with this caveat attached.
- **No US intraday exists** (`data/intraday/` absent; Polygon collector never run) → H8 stays
  deferred; the 1D leg is the fastest washout scale.
- **CN/HK are close-only** (no volume) → H4 is US-first; CN/HK generalization limited to H1-H3/H5-H6.
- **Comparability:** fires are generated with `tuning_harness.py` primitives (`resample("{n}B")`
  known-date protocol) so strata are apples-to-apples with the prior campaign's baselines. Known
  honest caveat: the production faithful port (`research/signal_engine/confluence.py`) uses
  session-grouped 3D bars, not `resample("3B")` — all comparisons here are INTERNAL (same bucketing
  both sides of every comparison), so the discrepancy shifts absolute fire dates, not verdicts.

### 4.2 Detector metrics (per candidate, per market panel)

**Event-based (vs labels):**
- **Recall** — % of durable bottoms with ≥1 fire inside the capture window `[t0 − 5d, t0 + 15d]`.
- **Entry premium** — median % above `P0` at the first captured fire (the "perked up a little" check).
- **Lead** — median days from `t0` to first fire.
- **Trap-fire rate** — % of trap bounces that also drew ≥1 fire in their window (the discriminator:
  a detector that can't tell a durable trough from a trap bounce adds nothing over the raw oscillator).

**Per-fire, count-fair (all fires, not only near events):**
- **Stop-out rate** — fire → next-close fill → hits −5% before +5% (comparable to `tuning_stops.py`).
- **Clean-liftoff rate** — hits **+15% before −5%** within 126d (the "blast-off capture" — the
  single number closest to the owner's stated goal).
- **Dead-money rate** — 63d later: never hit ±8% barrier and sits < +5% (capital parked).
- **MFE/MAE context** — median 63d MFE, MAE; time-to-+10%.

**Volume/robustness:** fires per name per year; per-name majority gates (% of names where candidate
beats baseline on the axis in question, >50% to hold); ticker split-half sign agreement; time
split (entries pre/post 2020-01) sign agreement.

### 4.3 Verdict gates (pre-committed)

- **Wave-1 (stratification):** a setup-state feature is PROMOTED to wave 2 iff the favorable
  stratum beats the unfavorable stratum on clean-liftoff rate by ≥ 5pp with n ≥ 300 fires
  panel-wide in each stratum, same sign on both ticker halves AND both time halves, and the
  favorable stratum's stop-out is not worse than the unfavorable one's by > 2pp.
- **Wave-2 (composite candidates vs `base3d`):** ship into the engine ONLY if, on held-out data:
  clean-liftoff rate higher on a majority of names with fires; stop-out rate not worse by > 1pp
  aggregate; **recall of `B15` durable bottoms ≥ 90% of `base3d`'s recall** (no watchlist gutting);
  trap-fire rate lower; stable on both splits. Anything less: `base3d` stays (kill rule).
- Failed candidates are logged in this file's ledger (§8) with their numbers. Falsified = closed.

---

## 5. Pre-registered hypothesis map (wave 1)

Each hypothesis = mechanism story + specific features + prediction. Features are computed leak-free
on the known-date grid (`tuning_harness.tf_bars/to_daily`), evaluated first as **stratifiers of the
incumbent triggers** (base3d, m2d_s3d, T3) — cheap, count-fair, no new trigger risk — then the
winners compose into wave-2 candidates.

**H0 — Reproduce the keeper's selection causally (the oracle-chase).**
The reclaim-and-hold filter proves ~29.4% stop-out is reachable by SELECTING among raw base3d fires
— but it uses `close[i+1..i+3]` to select. H0 asks: which strictly-bar-t features (drawn from
H1-H6 below) recover the most of that 39.5→29.4 oracle gap? Every wave-1 stratification table
doubles as an H0 answer: the oracle number is the printed ceiling on each table.

**H1 — Higher-TF washout state (the owner's core thesis, fire-conditional — never yet tested).**
Mechanism: a durable bottom requires sell-side exhaustion at the CYCLE scale, not just a daily dip.
Reconciliation with the knife findings (§3): raw depth-as-boost is dead (BOTTOM_CONFIDENCE Phase 2),
and deep-capitulation 3D crosses stop out MORE (TIERED_CASCADE §4). But every fire in this program
already carries turn evidence by construction (the trigger), which is the state that flipped deep
washouts from 29.6% → 55.7% held. Whether the multi-TF STOCH washout BEHIND a fire discriminates
on the liftoff/trap axes is genuinely open — H1's direction is NOT presumed.
Features: 2W StochRSI D min over trailing 6 2W-bars (< 25 deep); weekly D likewise;
fraction of last 60 trading days with 3D stoch D < 30 ("time spent washed out"); a composite
`washout_depth` = mean of (100 − D) across {2W, W, 3D} scaled 0-1.
Prediction (two-sided, resolved by data): washout-behind-fire raises clean-liftoff and dead-money
discrimination; stop-out likely ticks UP (knife residue). The NET on all three axes decides.

**H2 — Washout AGE + basing calm (reconciles TIERED_CASCADE §4 with H1).**
Mechanism: the shallow-beats-deep finding says recent violence gets entries wicked out. The washout
thesis is about the LARGER scale. Sweet spot hypothesis: the capitulation is OLD (≥ 15-20 trading
days since the 63d low), realized vol has crushed from its washout peak (ATR% now < 60% of its
peak in the washout), and the 2W washout is still deep. "The crash already happened; the base is
quiet; the turn is starting."
Prediction: `deep 2W washout × old low × calm base` is the highest clean-liftoff stratum in the
whole program, and specifically rescues the deep-capitulation cohort's stop-out problem.

**H3 — Bullish momentum divergence (the positive mirror of the shipped bearish-div veto).**
Mechanism: price lower-low + oscillator higher-low across the washout = seller exhaustion measured
mechanically. Features: over the washout window, last two confirmed price swing-lows make LL while
3D RSI-MACD (and separately 3D stoch D) makes HL.
Prediction: divergence-present fires lift off more and trap less; divergence also fires structurally
EARLIER than the MACD confirm, making it an arming condition candidate (§6).

**H4 — Participation / volume signature (what the owner's "volume ticking up through MACD" actually
wants, measured directly).**
Mechanism: durable bottoms show capitulation → dry-up → accumulation; trap bounces are low-quality
short-covering pops. Features (daily volume, where available): capitulation spike present in washout
(volume z ≥ 2 vs trailing 63d); base dry-up (20d median volume percentile < 40 vs 126d); perk-up
participation = up-day dollar volume / down-day dollar volume over last 10d ≥ 1.3; OBV higher-low
while price lower-low (volume divergence).
Prediction: participation features specifically kill the FALSE positives of the FASTER triggers
(the owner's exact request: 2D trigger + FP filters), because the thing the 2D cross lacks —
confirmation that buyers actually showed up — is what volume measures directly.
Data note: US deep panel has true volume; CN/HK/close-only names partially — wave 1 runs US-only
for H4, generalization to CN/HK in wave 3 where volume exists.

**H5 — Trap context (the Tencent veto).**
Mechanism: in a structural bear, oscillator buys recur and fail serially; the trap is a property of
the NAME'S REGIME, not the entry bar. Features: monthly RSI-MACD below signal AND falling; % of
last 252d below the 200MA (≥ 70% = entrenched bear); 200MA slope sign; **failed-fire count** — number
of this trigger's own fires in the last 180d that hit −5% before +5% (the self-aware "cried wolf"
feature, novel and fully causal); relative strength vs SPY making new 126d lows while price bounces.
Prediction: trap-context fires have the program's highest dead-money + trap-fire rates; as a veto it
must clear the recall gate (kill few durable bottoms) — measured, not assumed. NB the T4 200MA
lesson (§3): simple trend position failed per-event on the STOP axis; H5's claim is on the TRAP/
dead-money axis, which no prior study measured. If it also fails there, it dies too.

**H6 — Cohort confirmation (washout is a crowd event).**
Mechanism: durable bottoms cluster (sector/market capitulations); a name washed out ALONE is more
likely idiosyncratically broken (trap). Features: % of the name's GICS-sector peers (or subsector
basket) simultaneously in H1 washout; SPY/sector ETF 3D stoch state.
Prediction: cohort-washout fires beat lone-washout fires on clean-liftoff; lone washouts skew trap.
(Echoes the validated China finding: the drawdown edge lives in WHEN, market-wide, not WHICH name.)

**H7 — The earliness stack (the owner's explicit ask, assembled from winners).**
Take `m2d_s3d` (+3.7d earlier, +2.3pp stop-out) and gate it on the winning strata from H1-H6.
Prediction: the washout/participation/trap conditions restore ≥ the 2.3pp stop-out gap while keeping
most of the lead, and recall of durable bottoms EXCEEDS base3d's (the 2D trigger catches troughs the
3D confirm misses in the capture window). This is the direct test of "2D + stacked filters ≥ 3D".

**H8 — Sub-daily washout (4H).** Deferred: no intraday history in the repo (recon confirming; the
realistic floor is daily). The 1D stoch serves as the fastest washout leg in H1. If intraday data
is ever acquired (Polygon flatfiles), re-open.

**H9 — Barrier robustness.** All headline rates re-read with ATR-scaled barriers (stop = 1.5×ATR63,
liftoff = 4.5×ATR63) to confirm the −5%/+15% conclusions aren't a fixed-percent artifact across
vol classes. Secondary lens only.

---

## 6. The COILED-STATE architecture (wave-2 target)

(Named COILED to avoid collision with `cycles.mtf_alignment`'s existing ARMED tier, which is a
different machinery.)

The structural insight the prior campaign proved but never acted on: **the 3D MACD's lag is
load-bearing only because the trigger is carrying ALL the selectivity** — and the walk-forward
attribution (§3) proved the selectivity itself is worth 39.5→29.4 stop-out when it doesn't have to
be paid for with a confirmation WAIT. So: relocate selectivity into an explicit **setup state**
computable at bar t, then let a fast trigger fire inside it:

```
IDLE ──(washout conditions accumulate: H1 depth × H2 age/calm × H3 divergence
        × H4 capitulation/dry-up × ¬H5 trap × H6 cohort)──▶ COILED
COILED ──(fast trigger: 1D/2D stoch cross, or 2D MACD cross, or H4 up-volume
         expansion — whichever wave 1 crowns)──▶ FIRE (the entry signal)
COILED ──(conditions decay: liftoff ran >10% without us, or new low breaks the
         base, or coiled age > N bars)──▶ IDLE
```

This is mechanically how the owner actually trades (washed-out watchlist + waiting for the turn),
and it changes the false-positive economics: a 2D cross in a random chop regime never fires because
the name was never COILED; the same cross inside a deep, aged, quiet, diverging, cohort-confirmed
washout is a different event. Wave 1's stratification tells us which coiling conditions carry real
discrimination; wave 2 assembles the state machine and takes it through `walk_forward.py` (which
already enforces the banned-metric list and the ≥70%-of-names OOS kill rule) against the §4.3 gates.

The cascade mapping if it ships: COILED = a new pre-tier surfacing state; FIRE inside COILED slots
as a peer of T2/T3 with its own measured weight; nothing about T1/base3d changes (it remains the
confirmed master and the recall backstop).

---

## 7. Delegation protocol (for the sessions running the waves)

- Opus/Sonnet sessions run builds and sweeps; **the hypothesis list and the gates in this file are
  fixed inputs** — a runner session may not add metrics, drop axes, or "improve" the gates.
- Every wave report = one markdown in `research/entry_timing/` with: config, all §4.2 axes, split
  tables, fire counts, and an explicit leak-audit section (fill rule, known-date mapping, any
  forward-looking element enumerated).
- Code reuses `tuning_harness.py` primitives (`tf_bars`, `to_daily`, faithful math). New code lives
  in `research/entry_timing/`, never in `engine/` until a wave-2 candidate passes §4.3.

## 8. Ledger (results accrue here)

| date | candidate | verdict | numbers | where |
|---|---|---|---|---|
| 2026-07-01 | **Wave 1** — H1-H6 stratification, 223-name deep panel, 2012+, 22,458 labeled events (10,247 durable / 12,211 trap), fires: base3d 8,020 / m2d_s3d 12,797 / early 9,445 | see rows below | headline: base3d recall_B15 14.8%, med premium +10.6% over trough, med lead +9d — **the gate misses ~85% of durable bottoms in the perk-up window**; the lateness complaint is now a measured number | research/entry_timing/WAVE1_REPORT.md |
| 2026-07-01 | **H6 cohort washout** (≥40% of sector peers weekly-D<30, among in-washout fires) | **PASS — sole §4.3 gate passer (on m2d_s3d)** | clean15 39.29 vs 32.60 (+6.7pp), stop5 39.07 vs 44.54 (−5.5pp BETTER), dead-money 7.3% vs ALL 14.6%, n=3,174/3,417, all 4 splits sign-stable, per-name majority 66.2% (204 names). base3d +4.1pp / early +4.9pp — same sign, sub-threshold. Mechanism: cohort washout is a LOCATION feature (79% of stratum fires sit inside a labeled bottom zone vs ~35% of all fires) | fires parquets, verified independently |
| 2026-07-01 | **H6 ∩ H3 star cell** (cohort washout + bullish divergence, m2d_s3d) | wave-2 candidate core | n=847: clean15 41.09 (> oracle 40.53), stop5 34.71, dead-money 6.26%. Divergence supplies the stop-relief cohort lacks | WAVE1_REPORT.md §4 |
| 2026-07-01 | **H0 oracle decomposition** (base3d keeper selection, forward-peeking) | ceiling mapped | oracle stop5 29.8 vs ALL 40.9; clean15 40.5 vs 34.3. **No causal stratum recovers the stop-out gap — that 11pp is the confirmation WAIT itself.** The clean15 gap IS recoverable causally (H6 alone: 51% of it) | WAVE1_REPORT.md §3 |
| 2026-07-01 | **H2 washout age + calm base** | **FALSIFIED — wrong sign** | clean15 −1.4 to −6.4pp vs in-washout-not-calm, worst stop-outs in program (46-48% on fast triggers). The "aged quiet base" is where fires die, not where they fly. Framework's own §5 prediction was wrong; recorded as such | WAVE1_REPORT.md §2 |
| 2026-07-01 | **H4 volume signature** (dryup, up/down ratio, OBV-div, capitulation spike) | **FALSIFIED as positive filters** (US panel) | dryup sign-stable NEGATIVE everywhere (−4.3pp base3d); updown_good NEGATIVE on the fast triggers it was meant to rescue; obv_div/capit_spike noise. Volume dry-up = dying interest, not stealth accumulation, on this panel | WAVE1_REPORT.md §2 |
| 2026-07-01 | H1 multi-TF stoch washout depth (fire-conditional) | FAIL (weak +, pays stop tax) | in_washout_ctx +2.9pp clean15 but +3.5pp stop5; w2_deep ≈ 0 alone. Washout depth only works through the cohort lens (H6) | WAVE1_REPORT.md §2 |
| 2026-07-01 | H5 trap context / failed2 | FAIL on clean15; failed2 BACKWARDS | trap_state ≈ 0 and unstable; failed2=T has HIGHER clean15 (+1.8pp) — serial failure is mean-reversion fuel, not a veto. trap_state=T logged as lowest dead-money (10.4%) for wave-2 study | WAVE1_REPORT.md §2 |
| 2026-07-01 | m2d_s3d earliness cost, re-attributed | insight | +6.4pp recall, −2d lead vs base3d, paid in TRAP-FIRE contamination (17.6% vs 11.4%), NOT per-fire stop-outs (40.6 vs 40.9). Exactly the FP-economics COILED is designed to fix — and H6 fixes it | WAVE1_REPORT.md §1 |

**Wave-2 directive (mechanical reading):** build the COILED composite around
`m2d_s3d trigger × cohort-washout arming (H6) × bullish-divergence co-condition (H3)`, ship-shape
as a **ranking bonus / surfacing tier, NOT a hard gate** (847 fires ≈ 7% of m2d volume — a hard
gate would gut recall, §9.3 asymmetry). Take it through `walk_forward.py` (train/test, purge,
≥70%-of-names OOS) + the B30/label-sensitivity re-read + the basket-panel (2014+, 990 names,
survivorship-honest) generalization before any engine wiring. H5 trap_state dead-money veto and
the failed2 inversion are wave-2 side studies.

| date | candidate | verdict | numbers | where |
|---|---|---|---|---|
| 2026-07-01 | **Wave 2** — COILED validation: time folds, basket-panel OOS, barrier/label sensitivity, side studies (harness `wave2.py`, adversarially audited — a CRITICAL date-index serialization bug that would have leaked end-of-history cohort values was caught and fixed BEFORE the runs) | **ALL PRE-REGISTERED GATES PASS → SHIP as graded ranking bonus** | see rows below | research/entry_timing/WAVE2_REPORT.md |
| 2026-07-01 | G1 time-fold stability (deep panel, 5 folds, 180d purge) | PASS | clean15 spread positive 4/5 folds (+13.96/+12.25/+8.70/+8.75; fold-0 2012-15 −2.76 — the edge sleeps in low-vol bull legs with nothing to detect); pooled +6.69pp; COILED stop5 better every passing fold | T2 |
| 2026-07-01 | G2 basket-panel replication (2,336 names, 102,408 fires — the decisive OOS) | **PASS, edge LARGER OOS** | COILED n=6,842: clean15 38.70 vs 31.16 (+7.54pp), stop5 40.22 vs 45.86 (−5.64pp better), dead-money 6.15 vs 8.33; both time halves positive; per-name majority 65.2% of 492 names | T1/T3/T4 baskets |
| 2026-07-01 | G3 robustness | PASS | spread positive at every barrier (+10/+15/+20/+30) and 189d horizon on BOTH panels; B30/tol5/lift30/h189 label re-reads consistent (T9) | T1/T9 |
| 2026-07-01 | G4 ranking monotonicity | PASS — **graded, not binary** | cohort-fraction quartiles perfectly monotone both panels (Spearman 1.0), Q4−Q1 ≈ +10pp (baskets 30.78→41.28) | T5 |
| 2026-07-01 | STAR additivity (bull_div co-condition) | HOLDS OOS | baskets STAR n=1,766: clean15 39.69, stop5 37.83 (−2.4pp vs COILED). div WITHOUT cohort is actively BAD (31.63/48.46) — H3 is a co-condition only, never standalone | T1 |
| 2026-07-01 | Side studies | closed | trap_state veto adds nothing once COILED; failed2 inversion REPLICATES (serial failure = MR fuel, never a veto); COILED rescues deep-capitulation (fromos3) fires (38.83 vs 33.08 clean15); theme cohort works (+5.9pp) but sector cohort sharper — theme = fallback for unmapped names | T7/T3 |

**Ship record (2026-07-01):** COILED ships as a **graded ranking bonus + display chip + forward-ledger
fields** on the US standout board (CN washout-bonus precedent, `_combine_key` lift), NEVER a hard gate
(basket T8: COILED recalls only 7.35% of durable bottoms vs 59.71% for all fires — a hard gate would
gut recall ~88%). Board-ORDER methodology ownership stays with W6-US Buy Board 2.0; this bonus is the
first wave-2-validated input to that redesign, and the #812 ledger grades it forward. The `walk_forward.py`
filter-style pass was judged NOT APPLICABLE to a bonus-shaped ship (it tests subset-filters; the T2
folds + basket OOS carry the time-generalization burden here). Caveats attached: cohort map covers
~500 sector-mapped names (S&P + sector baskets) — unmapped names get no cohort and no bonus; the edge
is washout-regime-conditional (quiet in low-vol bull legs); effective n < printed n (overlapping fires).

**Wave-3 pre-registration (2026-07-02, written BEFORE the runs):** (A) CN/HK replication — CN panel
`china_search/closes.parquet` (≥800 bars, EVAL_START 2022-09-01, time halves at the 2024-09-24
stimulus pivot; sector cohort via `china_search/members.parquet` (12 sectors, all ≥6 members),
theme cohort via `baskets_china/membership.json`), HK panel `hk_search/closes_deep.parquet`
(EVAL_START 2012-01-01, halves at 2020-01-01; sector via `hk_breadth/constituents.parquet`).
Close-only markets: low_stop5 + H4 skipped. **G-CN gate:** COILED-vs-noncoiled_washout clean15
spread ≥ 3pp, same sign both halves, stop5 not worse by >1pp, n_COILED ≥ 400, per-name majority
≥ 55% (names with ≥3 fires each side). **G-HK gate:** same with n_COILED ≥ 200. **Robustness
(both):** spread sign preserved at clean10/clean20, dead-money lower. Ship per-market iff that
market passes gate + robustness. CN honesty caveat pre-declared: ~3.3y eval, one macro regime.
(B) Trigger-speed study inside COILED (deep US panel): triggers {m2d_s3d, m2d_s3d_early,
stochlead3d, m2d_s2d, m1d_s3d} × {inside, outside} the COILED state (state = washout_ctx AND
sector cohort ≥ 0.4, computed daily; div excluded from the state). **B-PASS for a faster trigger
iff inside COILED:** clean15 within 2pp of m2d_s3d-inside, stop5 not worse by >2pp, capture
economics better (median premium-over-trough lower OR recall_B15 higher), ticker-half sign-stable.
B informs wave-4 fire-layer design; nothing from B ships this wave.

**Wave-3 results (2026-07-02, harness `wave3.py`, audited clean — zero critical/major):**

| date | candidate | verdict | numbers | where |
|---|---|---|---|---|
| 2026-07-02 | **G-CN replication** (1,382 names, 20,502 m2d fires, 28,688 events) | **PASS — ship CN** | COILED n=10,784: clean15 35.57 vs 28.24 (+7.33pp), stop5 45.72 vs 51.93 (−6.21pp better), dead-money 5.06 vs 6.36; halves +6.08 / +11.46 (both +); per-name majority 59.3% of 1,139; STAR additive (37.56 / 45.00). Theme cohort weaker but consistent (+2.07pp). Pre-declared caveat stands: 3.3y, ONE macro cycle — re-grade when a second CN regime accrues | WAVE3_REPORT.md, wave3_cn |
| 2026-07-02 | **G-HK replication** (157 names, 8,576 fires) | **FAIL — do NOT ship HK** | spread −0.84pp (wrong sign), halves FLIP (−2.99/+1.63), per-name minority 46.1%, clean10 inverts; STAR is the WORST HK cell (32.57/48.05 — divergence actively hurts on HK). Mechanism read: 157 names / ~12 sectors + macro-correlated market → cohort washout is near-universal in HK drawdowns (76% of fires already in washout) and carries no discrimination | WAVE3_REPORT.md, wave3_hk |
| 2026-07-02 | **Tencent case (0700.HK)** | trap axis NOT solved on HK — recorded honestly | COILED flagged the 2021-23 sector-wide trap bounces as buyable (STAR once, 2021-08-11, stopped out): ~6 COILED stop-outs/dead fires vs one caught turn (2022-11-02, +97% MFE). It DID admit the 2025 turn (STAR 2025-01-28 +34.6%, COILED 2025-05-02 +13.4%) but missed the first 2024-08 leg. The name that motivated the trap axis is where the cohort mechanism breaks — HK trap discrimination needs a different lever (open) | tencent_case in wave3_hk |
| 2026-07-02 | **B: trigger speed inside COILED** (US deep panel) | **m1d_s3d = the COILED-architecture vindication; wave-4 nominee** | Only m1d_s3d has its stop advantage CREATED by the state (inside-gap −1.20pp vs outside +0.51pp): inside COILED n=3,787, stop5 37.87 (BETTER than m2d baseline 39.07), clean15 37.68 (−1.61, within gate), premium 6.43% vs 7.96%, lead 3d vs 6d, half-stable. m2d_s3d_early passes the gate but its stop edge is trigger-native (no state interaction); stochlead3d FAILS (clean15 −2.06); m2d_s2d FAILS (no capture gain). Unconditionally m1d was the WORST trigger of the 2026-06 campaign (−8.65pp DD) — inside COILED it is the best: selectivity successfully relocated from lag to state. Nothing ships from B (pre-registered); wave-4 = COILED×m1d fire layer through the full gate battery | WAVE3_REPORT.md, wave3_triggers T-B |

**Wave-3 ship record (2026-07-02):** CN gets the COILED graded bonus (same +0.25/+0.40 shape,
additive inside `_cn_bonus` beside WASHOUT_BONUS/EXT_PENALTY), chip + `china_standout_track`
ledger fields; the anti-chase EXT_PENALTY stays orthogonal. HK gets NOTHING (gate failed).
CN re-grade trigger: when the forward ledger accrues a second macro regime.
