# Track E — Evaluation OS + replay + adjacent-program boundary census (Live Entry Radar PR-0 archaeology)

Scope: census only, no design decisions. Answers the two PENDING(TRACK-E) slots in
`research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md` §2 (DRL boundary) and §11
(eval-os registration format + PSS §7 ruler deltas). `UNVERIFIED` marks anything
not confirmed by a direct read this session. Receipts are `file:line` from a
direct `Read`/`grep` this session unless marked otherwise.

---

## 1. Evaluation OS ("eval-os")

**Location.** Engine: `engine/qledger.py` (3,258 lines, the Universal
Scoreboard), `engine/qledger_validity.py` (267 lines, metric-validity
contract), `engine/qledger_falsifier.py`, `engine/qledger_ui.py`. Scripts:
`scripts/grade_qledger.py`, `scripts/check_qledger_metric_validity.py` (the CI
gate), `scripts/backfill_qledger_{us,cn}.py`, `scripts/sample_qledger_placebo.py`.
Doc home: `research/MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md` (+
`_CATALOG`, `_EVALUATION_STANDARDS`, `_PROPHET_EVAL_SPEC`,
`_INTELLIGENCE_OS_V1_PLAN`), shipped PR #5471. Original spec:
`research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md` §2.2, cited
`engine/qledger.py:1`. Memory pointer `mastermind-intelligence-evaluation-os-program`:
the T1 engine-registry task is parked/unshipped (no PR) — irrelevant to Radar's
registration path, which uses the already-shipped claim/grade substrate.

**Core objects.** **CLAIM** — a dict: required `desk` (any string, no fixed
enum), `asof`, `scope={type,key}` (`SCOPE_TYPES=("entity","basket","sector","macro")`,
`qledger.py:108`), `direction` (`DIRECTIONS=(-1,0,1)`, 0=salience-only,
`:109`), `horizon_d`, `timestamp_quality`; optional `claim_family`, `bench`,
`control`, `falsifier`, `check_by`, `is_placebo`. Structural validation only
(`_validate_claim`, `:1247-1352`) — macro claims must name a machine-checkable
`bench` (D4, `:1307-1310`); a claim whose declared exit window cannot resolve
is REFUSED at registration, never left immortal (`:1316-1350`, "NO ZOMBIE
CLAIMS"). **GRADE** — one row per claim per in-scope horizon
(`grade_claim`, `:2065`), matched-control excess, embargo by
`timestamp_quality`. **FAMILY** — `claim_family or desk` (`_family_key`,
`:2252-2257`); no registry enumerates legal families, one is born the first
time a claim carries its name. Store: `data/qledger/claims.jsonl` +
`grades.jsonl` (append-only JSONL); display `site/qledger/track_record.json`
(`:101-103`).

**How a NEW family registers.** Build via `engine.qledger.make_claim(*, desk,
asof, scope_type, scope_key, direction, horizon_d, timestamp_quality,
bench=None, control=None, falsifier=None, check_by=None, is_placebo=False,
claim_family=None, ...)` (`:1603-1616`), then `register(claim)` (`:1440`) or
`register_batch(claims)` (`:1474`) — loop-callers MUST use `register_batch`
(single store read/write; `register()` is quadratic at volume, `:1452-1455`).
Idempotent by `claim_id` (`_claim_id`, `:1197`). Precedents:
`scripts/build_whitehouse.py:513-545` (`desk="whitehouse"`); `engine/basket_turn_cohort.py`
(`basket_turn.v1` family — **directly analogous prior art**: cohort-level
claims for a washout-turn-adjacent K-of-N construction, pre-declared
"Expected-NULL forward meter... no backfill," promotion earliest 2027 at n≥8
episodes — cites `DO_NOT_REBUILD.md` "Washout × turn" by name). **Radar's
answer:** `make_claim(desk="entry_radar", claim_family="entry_radar_<detector_id>"`
— one family per detector, all long-only per the contract so the
mixed-direction rule below never engages — `, scope_type="entity",
direction=1, horizon_d=10` (contract §10 primary H) `, bench="SPY",
control=<sector ETF>, ...)` then `register_batch()` from the PR-5 nightly
reconciler only (never the intraday lane — same single-writer law as §6).

**Tiers.** `derive_state(n_dates)` (`:2242-2249`): `UNGRADED` (0) / `ACCRUING`
(0<n<`GRADED_MIN_DATES`) / `GRADED` (n≥`GRADED_MIN_DATES=25` distinct `asof`
dates, `:1183`, never overlapping observations, `_date_cluster:2232-2239`).
This 25-date floor is the *internal* qledger chip — distinct from the
*external* 50-observation reporting floor in `MASTERMIND_EVALUATION_STANDARDS.md`
§4.7 (gates Prophet's plan ledger to "accrual status only" at n=24,
`MASTERMIND_PROPHET_EVAL_SPEC.md:59-61`); don't conflate when writing Radar
copy — the contract's own "ACCRUING / RESEARCH PRIORITY" label (§9) already
matches qledger's `ACCRUING` word. Registration status ∈ `{open, rejected}`
(`:1159-1161`); rejected claims persist (D4 dark-fraction audit) but never grade.

**Append-only law** (P2, commit `668972bc5f3`). A historical assertion over an
append-only store must not become false merely because a valid new row was
appended. Two shapes: `ASSERTION` (assert/assertX over store content) and
`EXIT_CODE` (a gate whose exit is control-dependent on store content — the
shape that defeated a prior attempt, which only matched `ast.Assert` nodes).
AST-based detector in `scripts/check_qledger_metric_validity.py`,
mutation-tested against 7 known-bad + 13 known-legal fixtures
(`tests/test_append_only_assertions.py`). Legal = MONOTONICITY (`>= floor`,
membership); illegal = equality/frozen bounds (`== 28`) on a growing store.
Registered at severity `discipline`, empty `ci_wiring` on purpose (47
pre-existing findings, not yet a hard gate). Radar implication: any future
`data/entry_radar/*.jsonl` assertion must be monotonic, never exact-count.

**Own-ruler law** (P0b, commit `d4ad4dfcb6c`). `in_scope_horizons(horizon_d)`
(`:1213-1224`) always includes the claim's own `horizon_d` when it sits AT OR
BELOW the ladder ceiling (`GRADE_HORIZONS=(5,21,63)`, `:113`) — on-rung or off
(`in_scope_horizons(30)==[5,21,30]`); above the ceiling it is never added
(`126 -> [5,21,63]` unchanged; `config/ruling_graph.yml` LH-U6 forbids
extending the ladder itself). Before this fix, 12 family/horizon pairs
(~0.76% of the live corpus) could NEVER grade at their own ruler — a permanent
defect, not an accrual fact. Radar's §10 H=10 sits below the ceiling, so
`horizon_d=10` grades at `[5,10]` automatically — Radar gets its own-ruler
verdict for free.

**Mixed-direction family rule** (V1/P1, PR #5519, `engine/qledger_validity.py`).
`grades.jsonl` `excess` is RAW subject-minus-control return, not signed by
direction (`hit == sign(excess)==direction` carries direction instead).
Pooling signed `excess_mean` across a family holding both directions measures
universe drift, not skill (measured: pooled −0.65%, t=−17.9, "impressive-looking,
and entirely meaningless," `:16-23`). `may_pool_signed_excess()`/`profile_families()`
gate this at the single aggregation chokepoint (`_aggregate`, `qledger.py:2304`).
Moot for Radar under the one-family-per-detector registration answer above.

---

## 2. PSS §7 "timing ruler"

**Where §7 lives.** "Charter §7" (`research/PSS_WSIG_SHORTLIST_BY_FABLE.md:17,98,144`)
names a **house standard**, not a numbered section of that file (its own
sections stop before any §7; the referencing masterplan runs §0-§6 only). True
origin: `scripts/research/ptt_w1_timing_regrade.py` (`metric_arrays`/`null_stats`)
+ `scripts/research/ptt_w1_persistence_of_fit.py` (`bars_for`/`tool_dates`),
explicitly "NOT reinvented" and restated verbatim in each PSS family script's
own pre-registered header (e.g. `scripts/research/pss_f1_downvol.py`).

**Exact metrics** (from `pss_f1_downvol.py`'s header, identical across F1-F4).
Per signal at daily index `i` (closes only):
```
mae63 = min(close[i+1..i+63]) / close[i] − 1     (%; <=0; PRIMARY-lens raw)
prox  = close[i] / min(close[i-31..i+31]) − 1     (%; >=0; ±31td window)
w5    = prox <= 5%   (entered within 5% of the ±31td low)
tdt   = argmin offset of close in [i-31,i+31] (td; negative = trough BEFORE fire)
mfe21 = max(close[i+1..i+21]) / close[i] − 1  ;  rc21 = close[i+21]/close[i] − 1
```
Valid-day universe: `i>=31 AND i+63<len`. Exactly two inferential metrics
(rest descriptive): `U_MAE = median signal mae63 − all-days median mae63` (pp,
+=better); `U_W5 = signal within-5%-of-low rate − all-days rate` (pp).
Random-day nulls are per-name, per-half. Inference: month-cluster bootstrap
(cluster=calendar month; DT-R14 forbids ticker-only clustering), NB=1000, seed
pinned per family. Era split (DT-R16): FIT ≤2020-06-30 / TEST ≥2020-07-01,
plus a 2021+ sub-window; full-sample-only effects are disqualified; grading on
TEST only.

**Per-name-first aggregation.** U_MAE/U_W5 are computed per-name then
aggregated, never pooled-fire — `PSS_WSIG_SHORTLIST_BY_FABLE.md` documents a
live errata (E1) where an early pooled-fire-median-of-a-binary was a sign-flip
artifact, corrected to per-name-first (`DO_NOT_REBUILD.md:75`). "Per-name-first
self-check + main-loop recompute agree" is the standing check cited in every
PSS-F kill row.

**Matched-construction placebos.** Each family's falsifier compares against a
mechanism-stripped, matched analog (F2's "net-return-analog," F3's "raw-return
analog... 100% mutual-exclusion," F4's "total-vol-analog"), never a generic
random-day null alone; F1 additionally uses random NEW-LOW bars (per-name
conditional base rate) because its claim is "beats an ordinary new-low bar,"
not "beats an ordinary day."

**C32 gate** (`PSS_WSIG_SHORTLIST_BY_FABLE.md:193-217`) — "decline-deceleration
terminality gate," explicitly not a fifth family: a shared, pre-registered
conditioner column in all four W-SIG preregs (graded WITH and WITHOUT). Fires
only when decline rate is flattening into a fresh low; motivated by measured
2022 ground truth (raw stretch fired 18× in H1-2022 vs 2× near the Oct low;
swing-reclaim 265× vs 74×) — no early family survives 2022 without it.

**Incumbent Stoch-RSI cross — exact implementation.** "Stoch-RSI<20 cross on
the fixed 2W [two-week] rung (the incumbent mag7_washout / index_momentum
construction)" (`PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md:89`).
Primitive: `engine/canon.py:437 stoch_rsi_kd(close)`, consumed at
`engine/washout_turn.py:538` on weekly-resampled closes — the same primitive
Amendment-3's RUL-31.2 pins for all HTF work ("Never `cycles.stoch_rsi`
(K-only)," §3 below). Benchmark rung = **−2td** (fires ~2 trading days before
trough) — the bar every W-SIG family failed to beat (F2/F4 both fired at
−9td, "more POST-trough... a LATE confirmer"). "Structure-derived rung"
(`engine/personality_gate_shadow.py`) is a per-name-tailored variant; −2td is
specifically the uniform fixed-2W baseline's figure.

**Radar's reuse declaration (for contract §11's PENDING slot).** Radar reuses
the §7 ruler with four deltas: (a) primary lens = the contract's own 10-session
forward window (§10 H=10) in place of `mae63`/`prox±31td` — shorter, live,
intraday-capable object, but MFE/MAE/proximity metrics carry over in spirit;
(b) matched controls = contract §11's basket/sector/cap/ADV/vol-quintile
cohort (richer than one frozen mirror-placebo, since Radar registers a live
ongoing population); (c) per-name-first aggregation + month-cluster bootstrap
unchanged; (d) incumbent benchmark = Stoch-RSI cross at −2td
(`engine/canon.py::stoch_rsi_kd` via `engine/washout_turn.py`) — exactly what
contract §11 Q5 already names.

---

## 3. Entry-stack Amendment-3 (PR #1747) adjudication

**Doc:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md` (308 lines).
"RATIFIED 2026-07-06... rides on Amendments 1–2 (RUL-13..26)." "New rulings:
RUL-27 through RUL-34" (`:1-14`). The literal string "#1747" does not appear
inside this doc (checked, zero hits); the PR number is sourced from
`DO_NOT_REBUILD.md:83`'s citation and independently repeated by 4+ other docs
(`PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md:31`, `MAG7_WASHOUT_REENTRY_PREREG.md:292`,
`CHINA_STANDOUT_DOUBLE_CONFLUENCE_MASTERPLAN_BY_FABLE.md:155`) — convergent but
UNVERIFIED as a direct in-doc citation.

**RUL-27..34** (`:53-158`, briefly):
- **RUL-27** Identity/scope/marginals-first: A3 registers exactly 3 interaction
  families (B/C/D); further pairings deferred to a follow-up amendment.
- **RUL-28** Verdict-ceiling law (blocker): 63-bar NC-2-proxy band-FE is a
  mandatory KILL-ARM; vocabulary capped at DISPLAY-CANDIDATE/NULL/KILLED; CHIP
  promotion blocked for all A3 families pending the true eq_band.
- **RUL-29** Admission-leg law (blocker): weekly-RSI-MACD-derived features must
  read their operative verdict in the ¬wbull (fromos3-admitted) subset only.
- **RUL-30** De-confound battery (kill-only): NC-2-proxy, vol-level tercile FE,
  ¬bear_ctx decomposition, pure-age covariate, marginality-vs-A, admission-leg
  — each can only kill/downgrade, never upgrade.
- **RUL-31** HTF PIT + faithful-math law (blocker): last COMPLETED bar whose
  known-date ≤ fire date only; math pinned to `confluence_tiers._rsi_macd`/`_stoch_rsi_kd`;
  leak-audit (shift + truncation-invariance fixture) mandatory per primitive.
- **RUL-32** Trial budgets/mechanics: ceiling 165→201; every runner calls
  `led.log_trial()`.
- **RUL-33** Rejection record (citable, do-not-re-walk table).
- **RUL-34** Tape-native axes: `not_topped`/`eligible` are frozen-tape
  constants; stratifying on them is rejected at registration.

**KILL-WASHOUT-TURN / "2W operator seed" — exact construction.** Family **C =
`esx_washout_x_turn`** (`:183-188`): *"the operator's literal '2W StochRSI
washout' seed in its only live form: depth counts ONLY when the higher degree
is also turning... H1's frozen depth feature verbatim × A-turn flags."*
Registration (`:127`): *"2 interaction forms (H1-frozen 2W-D-min<25 × {A1, A2})
× 2 panels × 2 contrasts."* Decoded: "2W-D-min<25" = the operator's literal
seed — 2-week-timeframe stochastic %D falling below 25 — crossed with A1
(weekly RSI-MACD histogram rising) or A2 (2W stoch turn = K>D ∧ K rising).
**KILL verdict** (`:259`): *"adds NEGATIVE marginal value once proximity is
removed: nc2 kills contrast-i (−0.29pp CI incl 0)... Re-confirms the H1 depth
kill fire-conditionally."* Registry row (`DO_NOT_REBUILD.md:83`):
*"KILL-WASHOUT-TURN | Washout × turn (2W operator seed) | KILLED — operator
seed dies in test | Entry-stack Amendment-3 adjudication (#1747)."*

**Overall conclusion** (§F.2, `:263-281`). One new dimension survived: decline
path-SHAPE (family E, shipped display-only). *"The operator's literal '2W/1M
StochRSI washout' seed is confirmed dead in its position form and dead in its
interaction form (C KILLED...) — but its motion form survives on the broad
tradeable universe (A1 weekly-turn on baskets), mostly as a proximity
restatement with a thin genuine turn-marginal."* Reading: cycle-scale
**position** (depth/oversold-ness) is dead; cycle-scale **weekly motion** (the
turn itself) carries a small real marginal on small/mid-caps only. Non-revival
template already in-tree: `research/TURN_SENSITIVITY_UPGRADE_MASTERPLAN_BY_FABLE.md:46`
ships `mtf_upturn.v1`, justified as *"NOT a revival... (different construction:
no washout precondition, no operator seed, per-stock granularity, K-of-N
legs)"* — the closest template for Radar's own kill-registry compliance wording.

---

## 4. Prophet selection-alpha status

The literal phrase "incomplete pricing" / "exit management" (as a confound
description) does not appear anywhere in the repo (repo-wide grep, zero
relevant hits). UNVERIFIED as a direct quote; below is the closest grounded
finding set.

**Fixed-horizon selection alpha not yet demonstrated.**
`MASTERMIND_PROPHET_EVAL_SPEC.md` §9 scorecard (`:213-229`) prints as a
first-class line: *"AT ITS RULER  verdicts at declared horizon: 0."* §2
(`:34-64`): 28 closed plans, honest N=24 distinct signal dates, win 32.1% vs
30.3% breakeven, t=+0.178, 95% CI [−5.14%,+6.17%] — *"Prophet may currently
report accrual status only in any external surface"* (§4.7 50-observation
floor). `MASTERMIND_INTELLIGENCE_CATALOG.md` Finding C-4 (`:318-322`): *"the
flagship currently has no defensible performance claim, and any marketing that
implies otherwise is unsupported."*

**The one favorable realized number is confounded — closest grounded reading.**
Finding C-5 (`MASTERMIND_INTELLIGENCE_CATALOG.md:324-341`): Prophet has two
evaluation surfaces, only one benchmark-graded — the board grades vs SPY +
sector ETF correctly; **the plan ledger (the 28 closed trades — the surface
carrying the public narrative) does not**: schema `[..., option_result_pct,
outcome, plan_adherence, ..., stock_result_pct]` has **no benchmark field**, so
the headline is raw return (`MASTERMIND_PROPHET_EVAL_SPEC.md:174-179`, §7).
Separately, `research/PROPHET_ARENA_REGISTRATION.md:65` records a
first-trigger-closure defect on the same favorable-outcome field:
*"T1 then later T2 is recorded T1_HIT forever"* — the `T1_HIT` mean (+22.60%,
n=7, the best bucket) is an incomplete accounting of the realized move (a plan
that later also clears T2 is never re-labeled). So the one favorable number is
confounded two ways: no benchmark leg (raw, not alpha) and an exit-bookkeeping
rule frozen at the first target. `MASTERMIND_PROPHET_EVAL_SPEC.md` §3
(`:68-87`) independently flags the mirror problem on the loss side: without
MFE/MAE, *"it is impossible to tell whether the 11 invalidated plans were
wrong or merely stopped out before being right."* Remedy already specified
(§7, `:181-190`): add `bench_ret_pct`, `sector_ret_pct`, `excess_vs_bench_pct`,
`excess_vs_sector_pct`, `mfe_pct`, `mae_pct`, direction-signed.

---

## 5. DRL (Dislocation & Recovery / price pressure) program

**What it is.** `research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md`
(588 lines, v2 + §12 red-team log). §1 (`:66-80`): detect when a name's price
is pushed materially away from what market+sector+peers justify, record it
PIT, track resolution. *"It is not a buy-signal engine"* — display-tier
context freely; promotion walks the §7 gauntlet later. **Signal**
(`:180-189`): `resid = ret − sector_ex_self_peer(ret)`, `resid_z =
resid/rolling_σ(shifted)`; eligibility = non-split ∧ price≥$5 ∧ ADV-median≥$5M;
**shock = `|resid_z|≥3 ∧ volume≥2×`** — imported verbatim from the killed
`DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER` fence (re-tuning any constant
is out of bounds). **Cadence:** nightly-only, gated by
`engine/ledger_lane.py::nightly_advance_enabled()`; one non-fatal
`daily.yml` tail-desks step; no intraday ledger writes. **Universe:**
`data/massive_stock_day/`, measured 4,281-name eligible panel. **Engine
paths:** `engine/price_pressure/{panel,detect,context,ledger,artifact,backfill}.py`
— `artifact.py` emits `data/price_pressure/latest.json` with `authority:
{can_rank/can_size/can_gate/can_originate_signal/can_escalate: false}` (all
literal false).

**Prereg format/location — the house precedent to copy.**
`research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md` (354 lines): §0 Provenance
(in-sample sighting disclosed) · §1 Frozen claims · §2 Evidence cells
(imported, not tunable) · §3 Conditioning variable · §4 Inference · §5 Floors
and discipline · §6 Consequence matrix · §7 Clock · §8 Grading log
(append-only) · §9/§10 dated, append-only amendment sections (pre-evidence
audits, never in-place edits — the same discipline the Radar contract's own
§18 already adopts). Status: R4-A is the sole gating claim at power floors
(320 stressed / 640 calm dates); R4-B demoted descriptive-only forever
(measured weak in-sample); eligibility = forward-era rows dated ≥2026-08-11 only.

**Boundary vs Live Entry Radar.** DRL's own §11 "Collision clearance"
(`:508-539`) predates Radar and doesn't name it, but the split is sharp: **DRL
is a reactive, single-name, cross-sectional RESIDUAL-SHOCK detector** with a
standing refusal to become an entry system (`authority` block literal-false;
bound by `DNR:KILL-FRESH-BUY-EDGE`/`KILL-PRIMED-DIRECTIONAL-GATE`) — its
object is "this name got pushed away from fair value," graded on a
residual-magnitude fence, and it explicitly excludes oscillator/turn
vocabulary (`DNR:KILL-PARALLEL-SHOCK-CLASSIFIER`). **Radar is a prospective,
technical-turn ENTRY-TIMING and RANKING system** explicitly building toward
future promotion (Research Priority → Opportunity Score) — the opposite
disposition. Zero namespace overlap (`engine/price_pressure/` vs
`engine/entry_radar/**`). Zero construction overlap: DRL triggers on a
**level/magnitude** condition (return residual vs sector peers, unconditional
on any oscillator); Radar triggers on a **state-transition** condition
(stochastic/histogram turn, unconditional on residual magnitude) — the two
could co-fire on the same name without either reading the other's artifact.
Worth inheriting: the `ledger_lane.py` single-advancer gate (§6), the
`transmission_chains` episode pattern, the `authority: {...: false}`
display-tier convention, and the dated-append-only-amendment prereg shape.

---

## 6. Forward-ledger conventions

**Single-advancer law.** `engine/ledger_lane.py` (50 lines) — *"the single
definition of the forward-ledger advance gate for the two nightly lanes."*
`nightly_advance_enabled()` (`:23-33`): `True` only when `COLLECT_LANE=nightly`
(`daily.yml`'s engine-job env). `asia_advance_enabled()` (`:39-50`): `True`
only when `CN_LANE=asia`. Deliberately a leaf module (imports `os` only) —
every engine/script that used to define a local `_ledger_advance_enabled()`
now imports from here; this IS the CLAUDE.md "nightly is the sole advancer"
law, made mechanical. A separate, deliberately-not-unified family
(`ledger_lane_armed()` in `engine/event_window.py`, `ignition_audit.py`, etc.)
gates collect-lane *arming*, not the ledger append itself.

**Example producer/consumer pairs.** (1) `engine.qledger.register`/`register_batch`
(producer → `claims.jsonl`/`grades.jsonl`) → `engine/qledger_ui.py` +
`scripts/grade_qledger.py` (consumers) → `site/qledger/track_record.json`
(`emit_track_record`, `qledger.py:2743`). (2) `engine/price_pressure/ledger.py`
(producer, nightly-gated) → `engine/price_pressure/artifact.py` (consumer,
`data/price_pressure/latest.json`) → `market_packet.py`'s `_pressure_block()`
+ the stocks-hub Pressure Watch band (site consumers).

**MFE/MAE computation precedents (production).**
- `engine/forward_dist.py:35-36`: `mae = 100.0*(fwd_min/c-1.0)` (≤0),
  `mfe = 100.0*(fwd_max/c-1.0)` (≥0) — full forward-path quantile
  distributions, not just point values.
- `engine/track_scoring.py:79-86,197-198,232-233,409-421`: per-position
  `mfe`/`mae` with a documented trap: *"capture (realised/MFE) needs a
  STRICTLY POSITIVE favourable excursion... a negative realised by a negative
  MFE prints a flattering positive."* `MFE_FLOOR=1e-9` guards the division.
- `engine/grading.py:191,244`: `fwd_mfe_{H}` = *"max favorable excursion...
  strictly-forward window (fill, fill+H]"* —
  `max(0.0, window.max()/entry_price - 1.0)`.
- `engine/pick_forward_dist.py:30,283-339`: `empirical_cone`/`fit_cones` —
  vol-standardized `z_mae`/`z_mfe` quantile cones, labeled *"Forward outcomes
  (ret/mae/mfe...) are LABELS, not features."*

All four converge on the same sign convention (MFE≥0, MAE≤0, both over a
strictly-forward window from a fixed entry) — Radar's §10 MFE/MAE fields
should match this rather than invent a new one.

---

## 7. Matched-control precedents

- **qledger's second grading leg:** `control_for_sector(sector_name)`
  (`qledger.py:1235-1241`) resolves a sector-matched control ETF (`_GICS_ETF`)
  alongside `default_bench_for` (SPY default, `:1226-1232`) — *"a null control
  is a valid, honestly-recorded state."*
- **LSR/DRL's residual construction:** `resid = ret − sector_ex_self_peer(ret)`
  (§5) — a peer-basket-matched control built into the signal itself.
- **PSS mirror-placebos** (§2): matched, mechanism-stripped construction
  analogs, not cohort matches, but count per the task's framing.
- **`engine/basket_turn_cohort.py`:** cohort-level claims graded "cohort EW
  return vs SPY" — a basket-vs-benchmark design, and (§1) a live example of
  registering a washout-turn-adjacent claim post-kill.
- **Group Reads baskets:** `research/GROUP_READS_MASTERPLAN_BY_FABLE.md` +
  session handoffs exist; UNVERIFIED this session whether the internal
  machinery performs excess-vs-benchmark matching or is a pure
  participation/breadth read — not opened (budget); flag for a targeted
  follow-up if Radar needs a second basket-matching reference.
- **Radar's own §11 design already exceeds all of the above:** simultaneous
  matching on session date, sector, cap bucket, dollar-volume decile,
  trailing-60d-return quintile, realized-20d-vol quintile, hotness tier —
  closer to a proper stratified-cohort match than any single existing
  precedent. `engine.group_flow._causal_z` (`engine/group_flow.py:83-86`,
  rolling z-score) is DRL's cited z-convention for any new z-fields.

---

## 8. PIT/vintage precedents

**Field conventions.** The contract itself (§5, `:139-159`) specifies:
`observed_at, market_session, source_bar_time, source_bar_known_at, bar_state,
data_vintage`, `bar_state ∈ {confirmed, provisional, stale, unavailable}`.
Directory-level naming in `engine/neuralweb/market_memory_pit.py`,
`market_memory_trusted.py`, `market_memory_forward.py` suggests the same
`known_at`/vintage discipline (UNVERIFIED field-for-field, not opened this
session). Amendment-3's RUL-31 (§3) is the closest EXACT precedent already
ratified: *"every HTF feature uses the last COMPLETED HTF bar whose known-date
≤ fire date... Weekly = W-FRI resample with known-date mapping (reuse
`engine/oracle/oscillators.resample_weekly_leakfree`)"* — directly reusable
for Radar's 2D/3D/weekly known_at mapping (contract §5's one open row).

**Replay harness precedent.** `engine/rule_experiments.py` (R1 rule-experiment
registry) is the closest general-purpose replay/spec-hash harness: append-only
JSONL at `data/rule_experiments/registry.jsonl` (single writer
`scripts/register_rule_experiment.py`), every registration calls
`TrialLedger.log_declared_budget(grid_size, family='replay')` under one FLAT
pooled family (sub-families prohibited), lifecycle `registered → executed →
reported`. The runner (`scripts/run_rule_replay.py`) compares every spec hash
via `verify_spec_hashes()` (`engine/rule_experiments.py:126`) before accepting
a run — the concrete precedent for the contract's `detector_spec_hash` field
(§13) and PR-2's "`spec_hash` stable" gate (§15). `TrialLedger`:
`engine/trial_ledger.py:65`, `log_trial()` (`:126`), `log_declared_budget()`
(`:159`) — the same API Amendment-3's RUL-32 mandates for every A3 runner, so
Radar's "append-only look ledger" (contract §11) should very likely BE
`TrialLedger`, not a new store.

**Mutation-test precedents proving no-lookahead.** 564 test files reference
leak/lookahead vocabulary repo-wide (`grep -rl` over `tests/`, count only).
Representative, directly relevant (Amendment-3-era, matching RUL-31.4's
mandatory "shift audit + truncation-invariance fixture per primitive"):
`tests/test_entry_primitives_a3.py:105,115,136` (three parametrized
`test_truncation_invariance` methods), `:230` `test_no_fillna_leakage`;
`tests/test_bottom_sensors_a3.py:212` `test_leak_guard_and_gap`. The
contract's own §7 leakage matrix (`:147-159`) already specifies an equivalent
test per input row (EOD-mutation, same-day-use, bar-boundary, rank-vintage,
nomination-postdate, recompute-at-vintage) — these named A3 tests are the
closest existing implementations to mirror rather than invent fresh.

**`spec_hash` precedent, second cluster.** Also present in
`engine/seasonality/contracts.py`, `engine/seasonality/prophet_bridge.py`,
`engine/seasonality/state.py`, `scripts/register_disp_gate_1.py` — not opened
this session (budget); flagged if PR-2 wants a second comparison point.

---

*Absence claims above ("literal phrase not found") were checked via `grep -rn`
over `research/` (whole repo for §4) for the exact task phrasing; a miss on
those specific strings does not mean the underlying finding is absent — the
grounded equivalents are cited in full (fable-mode §3.5).*
