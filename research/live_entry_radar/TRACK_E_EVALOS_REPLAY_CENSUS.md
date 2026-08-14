# Track E — Evaluation OS + replay + adjacent-program boundary census (Live Entry Radar PR-0 archaeology)

Scope: census only, no design decisions. Answers the two PENDING(TRACK-E) slots in
`research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md` §2 (DRL boundary) and §11
(eval-os registration format + PSS §7 ruler deltas). `UNVERIFIED` marks anything not
confirmed by a direct read this session. All receipts are `file:line` from a direct
`Read`/`grep` this session unless marked otherwise.

---

## 1. Evaluation OS ("eval-os")

**Location.** Engine: `engine/qledger.py` (3,258 lines — the Universal Scoreboard),
`engine/qledger_validity.py` (267 lines — metric-validity contract),
`engine/qledger_falsifier.py`, `engine/qledger_ui.py`. Scripts:
`scripts/grade_qledger.py`, `scripts/check_qledger_metric_validity.py` (the CI gate
shell), `scripts/backfill_qledger_{us,cn}.py`, `scripts/backfill_qledger_intel_hub.py`,
`scripts/sample_qledger_placebo.py`. Doc home: `research/MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md`
(+ `_CATALOG`, `_EVALUATION_STANDARDS`, `_PROPHET_EVAL_SPEC`, `_INTELLIGENCE_OS_V1_PLAN`),
shipped 2026-08-12 PR #5471. Original W1 contract spec: `research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md`
§2.2, cited in `engine/qledger.py:1`. Program memory pointer:
`mastermind-intelligence-evaluation-os-program` — "the eval machinery already
existed, the missing unit of account is an ENGINE registry" (T1, parked, not
shipped — branch `claude/eval-os-t1-engine-registry`, no PR; irrelevant to Radar's
registration path, which uses the already-shipped claim/grade substrate).

**Core objects.**
- **CLAIM** — a dict: required `desk` (any string, no fixed enum), `asof`,
  `scope={type,key}` (`SCOPE_TYPES=("entity","basket","sector","macro")`,
  `qledger.py:108`), `direction` (`DIRECTIONS=(-1,0,1)`, 0=salience-only,
  `qledger.py:109`), `horizon_d` (int >0), `timestamp_quality`. Optional:
  `claim_family`, `bench`, `control`, `falsifier`, `check_by`, `is_placebo`.
  Structural validation only (`_validate_claim`, `qledger.py:1247-1352`) — macro
  claims MUST name a machine-checkable `bench` (D4, `:1307-1310`); a claim
  declaring a `horizon_unit` whose exit window cannot resolve is REFUSED at
  registration, not silently immortalized (`:1316-1350`, "NO ZOMBIE CLAIMS").
- **GRADE** — one row per claim per in-scope horizon, from `grade_claim()`
  (`qledger.py:2065`), matched-control excess, embargo by `timestamp_quality`.
- **FAMILY** — `claim_family or desk` (`_family_key`, `qledger.py:2252-2257`). No
  registry file enumerates legal families; a family is born the first time a
  claim carries its name, and grading/aggregation runs generically over whatever
  families appear in the corpus.
- Store: `data/qledger/claims.jsonl` + `data/qledger/grades.jsonl` (append-only
  JSONL), display: `site/qledger/track_record.json` (`qledger.py:101-103`).

**How a NEW experiment/family registers (exact API).** Build a claim via
`engine.qledger.make_claim(*, desk, asof, scope_type, scope_key, direction,
horizon_d, timestamp_quality, horizon_unit=None, bench=None, control=None,
falsifier=None, check_by=None, sector=None, is_placebo=False,
claim_family=None, extra=None)` (`qledger.py:1603-1616`), then
`engine.qledger.register(claim, root=None, dedupe=True)` for one claim
(`qledger.py:1440`) or `register_batch(claims, root=None, dedupe=True)` for many
— **loop-callers must use `register_batch`**; `register()` re-reads the whole
store per call and is quadratic at volume (`qledger.py:1452-1455`). Idempotent by
`claim_id` (desk+asof+scope_key+horizon_d+direction+salt hash, `_claim_id`,
`qledger.py:1197`). Real precedents: `scripts/build_whitehouse.py:513-545`
(`desk="whitehouse"`, `claim_family="whitehouse"`); `scripts/backfill_qledger_us.py:370-598`
(desks `"altdata"`, `"radar"`, `"policy"`); `engine/basket_turn_cohort.py`
(`basket_turn.v1` family — see §3 cross-reference, a **directly analogous
prior-art registration** for a washout→turn-adjacent construction post-kill:
cohort-level claims, `direction=+1` always, `horizon_d=21`, pre-declared
"Expected-NULL forward meter... no backfill", promotion question earliest 2027
at n≥8 episodes). **Radar's registration answer:** call `make_claim(desk="entry_radar",
claim_family="entry_radar_<detector_id>"` — one family per detector (G0/C1/C2/C3/C4
are all long-only per the contract, so no family ever needs the mixed-direction
reading below) `, scope_type="entity", scope_key=ticker, direction=1, horizon_d=10`
(the contract's §10 primary H) `, timestamp_quality=..., bench="SPY", control=<sector
ETF>, falsifier=..., check_by=...)` then `register_batch()` from the PR-5 nightly
reconciler — never the intraday lane (the single-advancer law, §6 below, is the
same law the contract's §7 "single-writer law" already independently states).

**Display / accruing / validated claim tiers.** `derive_state(n_dates)`
(`qledger.py:2242-2249`): `UNGRADED` (n_dates==0) / `ACCRUING`
(0<n_dates<`GRADED_MIN_DATES`) / `GRADED` (n_dates≥`GRADED_MIN_DATES=25`,
`qledger.py:1183`) — `n_dates` = distinct `asof` dates, never overlapping
observations (`_date_cluster`, `qledger.py:2232-2239`). This 25-date floor is the
**internal qledger state chip**, distinct from the 50-observation **external
reporting floor** in `MASTERMIND_EVALUATION_STANDARDS.md` §4.7 (used by
`MASTERMIND_PROPHET_EVAL_SPEC.md:59-61` to gate Prophet's plan-ledger to
"accrual status only" at n=24) — do not conflate the two when writing Radar's
UI copy; the contract's own "ACCRUING / RESEARCH PRIORITY" label (§9) already
matches qledger's `ACCRUING` vocabulary. Registration status ∈ `{open, rejected}`
(`STATUS_OPEN`/`STATUS_REJECTED`, `qledger.py:1159-1161`) — rejected claims
persist for the D4 dark-fraction audit but are never graded.

**Append-only law** (P2; commit `668972bc5f3`, "eval-os P2: the append-only
assertion law, rebuilt around monotonicity"). A historical assertion over an
append-only store (`claims.jsonl`/`grades.jsonl`) must not become false merely
because a VALID new row was appended. Two shapes: `ASSERTION` (an assert/assertX
comparison over store content) and `EXIT_CODE` (a gate whose failing exit is
control-dependent on store content — the shape that defeated a prior attempt,
because it only matched `ast.Assert` nodes). Enforced by an AST-based detector in
`scripts/check_qledger_metric_validity.py`, mutation-tested against 7 known-bad +
13 known-legal constructions (`tests/test_append_only_assertions.py`, mutates the
detector 10 ways and fixtures 9 ways). Legal: MONOTONICITY (`>= floor`, `x in
store`, `set(keys) == FIELDS`). Illegal: equality/frozen bounds (`== 28`, `<=
frozen`) on a growing store. Registered at severity `discipline` with empty
`ci_wiring` on purpose — 47 pre-existing findings are not yet a day-one hard
gate. **Radar implication:** any test/gate over a future `data/entry_radar/*.jsonl`
ledger (or over `claims.jsonl` once Radar registers into it) must use monotonic
comparisons only.

**Own-ruler law** (P0b; commit `d4ad4dfcb6c`, "fix(qledger): P0b — grade a claim
at its OWN declared ruler, within the ceiling"). `in_scope_horizons(horizon_d)`
(`qledger.py:1213-1224`) now always includes the claim's own declared `horizon_d`
whenever it sits AT OR BELOW the fixed ladder's ceiling (`GRADE_HORIZONS[-1]=63`)
— on-rung or off (`in_scope_horizons(30) == [5,21,30]`). A horizon ABOVE the
ceiling (e.g. 126) is never dynamically added (`in_scope_horizons(126) ==
[5,21,63]`, unchanged — `config/ruling_graph.yml` LH-U6 forbids extending
`GRADE_HORIZONS` past 63 in the live nightly grader). Before this fix, 12
family/horizon pairs (~355/46,630 claims, 0.76% of the live corpus) could NEVER
be read at their own ruler — a permanent unreachability defect, not an accrual
fact. **Radar implication:** §10's primary H=10 is below the 63 ceiling, so a
Radar claim registered with `horizon_d=10` grades at `[5, 10]` automatically —
Radar gets its own-ruler verdict for free under current law.

**Mixed-direction family rule** (V1/P1; PR #5519, `engine/qledger_validity.py`).
`grades.jsonl` `excess` is RAW subject-minus-control return, NOT signed by claim
direction (`hit` carries direction: `hit == (sign(excess) == direction)`).
Pooling signed `excess_mean` across a family holding BOTH directions measures
universe drift, not skill (measured 2026-08-12: pooled figure −0.65%, t=−17.9 —
"impressive-looking, and entirely meaningless",
`engine/qledger_validity.py:16-23`). `may_pool_signed_excess()`/`profile_families()`
gate this at the single aggregation chokepoint (`_aggregate`, `qledger.py:2304`).
Moot for Radar if one `claim_family` per (long-only) detector is used, per the
registration answer above.

---

## 2. PSS §7 "timing ruler"

**Where §7 actually lives.** "Charter §7" (`research/PSS_WSIG_SHORTLIST_BY_FABLE.md:17,98,144`)
is a **house standard**, not a numbered section of any one file — the shortlist
doc itself has no §7 header (its own structure runs to a "Panel disposition"
section; the referencing masterplan `research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md`
runs §0-§6 only). The ruler's true origin and machinery: `scripts/research/ptt_w1_timing_regrade.py`
(`metric_arrays`/`null_stats`) and `scripts/research/ptt_w1_persistence_of_fit.py`
(`bars_for`/`tool_dates`) — explicitly "NOT reinvented" and restated verbatim in
each PSS family script's own pre-registered header, e.g.
`scripts/research/pss_f1_downvol.py` (header block "RULER (§7 house standard...)").

**Exact metrics** (from `scripts/research/pss_f1_downvol.py` docstring, identical
across F1-F4 per their own headers). Per signal at daily index `i` (closes only):
```
mae63 = min(close[i+1..i+63]) / close[i] − 1     (%; <=0; PRIMARY-lens raw)
prox  = close[i] / min(close[i-31..i+31]) − 1     (%; >=0; ±31td window)
w5    = prox <= 5%   (entered within 5% of the ±31td low)
tdt   = argmin offset of close in [i-31,i+31] (td; negative = trough BEFORE fire)
mfe21 = max(close[i+1..i+21]) / close[i] − 1  ;  rc21 = close[i+21]/close[i] − 1
```
Valid-day universe per half: `i>=31 AND i+63<len`. **Exactly two inferential
metrics** (everything else descriptive): `U_MAE = median signal mae63 − all-days
median mae63` (pp; += shallower/better); `U_W5 = signal within-5%-of-low rate −
all-days rate` (pp). Random-day nulls are per-name, per-half (the "69%-class
base-rate trap guard"). Inference: month-cluster bootstrap (cluster = signal
calendar month — DT-R14 forbids ticker-only clustering), NB=1000, seed pinned
per family. Era split (DT-R16): FIT ≤2020-06-30 / TEST ≥2020-07-01, plus a
2021+ sub-window; a full-sample-only effect is disqualified; all grading on TEST.

**Per-name-first aggregation.** U_MAE/U_W5 are computed per-name then
aggregated (median-of-medians / rate-of-rates), never a pooled-fire statistic —
`PSS_WSIG_SHORTLIST_BY_FABLE.md` documents a live errata (E1) where an early
pooled-fire-median-of-a-binary was a sign-flip artifact, corrected to per-name-first
(`research/DO_NOT_REBUILD.md:75`, row `KILL-PSS-F1-DOWNVOL`). "Per-name-first
self-check + main-loop recompute agree" is the standing verification pattern
cited in every PSS-F kill row (`DO_NOT_REBUILD.md:75-79`).

**Matched-construction placebos.** Each family's falsifier compares against a
mechanism-stripped, matched analog — F2's "net-return-analog", F3's "raw-return
analog... 100% mutual-exclusion", F4's "total-vol-analog" — never a generic
random-day null alone. F1 uses random NEW-LOW bars (per-name conditional base
rate) specifically because its claim is "beats an ordinary new-low bar", not
"beats an ordinary day" (`scripts/research/pss_f1_downvol.py`, F1-SPECIFIC
PRE-STATED KILL section).

**C32 gate** (`PSS_WSIG_SHORTLIST_BY_FABLE.md:193-217`) — "decline-deceleration
terminality gate", explicitly NOT a fifth family: a shared, pre-registered
conditioner column carried in all four W-SIG preregs (graded WITH and WITHOUT).
Fires true only when the rate of decline is flattening into a fresh low
(`roc20` stops making new negatives while price ≤60d low) — the only candidate
structurally FALSE during a constant-slope descent. Motivated by measured 2022
ground truth: raw stretch fired 18× in H1-2022 vs 2× near the Oct low;
swing-reclaim fired 265× vs 74× — no early family survives 2022 without it.

**The incumbent Stoch-RSI cross — exact implementation.** "Stoch-RSI<20 cross on
the fixed 2W [two-week] rung (the incumbent mag7_washout / index_momentum
construction)" (`research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md:89`).
Primitive: `engine/canon.py:437 stoch_rsi_kd(close)` (K/D stochastic-RSI),
consumed by `engine/washout_turn.py:538` (`k_raw, d_raw = stoch_rsi_kd(wk)` on
weekly-resampled closes) — the SAME primitive Amendment-3's RUL-31.2 pins for
all HTF work ("StochRSI = `confluence_tiers._stoch_rsi_kd` (14/3/3, K&D, 0-100).
**Never** `cycles.stoch_rsi` (K-only)", `ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md:108-111`).
The benchmark rung is "−2td" (fires ~2 trading days before the trough) — cited
repeatedly as the bar every W-SIG family failed to beat (F2: "fires at tdt −9td,
more POST-trough than the incumbent Stoch-RSI cross (−2td) — a LATE confirmer";
F4: same −9td, same verdict). "Structure-derived rung"
(`engine/personality_gate_shadow.py`, W3) is a per-name-tailored variant of the
same cross; −2td is specifically the UNIFORM-gate (fixed 2W) baseline's figure.

**Radar's reuse declaration (recommended text for the contract's §11 PENDING
slot).** Radar detectors are graded on the §7 ruler unmodified except: (a)
primary lens is the contract's own 10-session forward window (§10 H=10) in
place of PSS's `mae63`/`prox±31td` — Radar's object is a shorter, live,
intraday-capable turn, not a multi-week reset, but MFE/MAE/proximity-style
metrics carry over in spirit; (b) matched controls are the contract's §11
basket/sector/cap/ADV/vol-quintile cohort (richer than a single frozen
mirror-placebo, because Radar registers a live, ongoing population, not one
historical family); (c) per-name-first aggregation and month-cluster bootstrap
carry over unchanged; (d) incumbent benchmark = Stoch-RSI cross at −2td
(`engine/canon.py::stoch_rsi_kd`, consumed via `engine/washout_turn.py`) — this
is exactly what the contract's §11 Q5 ("Does G0 beat the existing entry gauge...
on earliness") already names.

---

## 3. Entry-stack Amendment-3 (PR #1747) adjudication

**Doc:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md` (308 lines).
"**Status:** RATIFIED 2026-07-06... Amends `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
(#1356) and rides on Amendments 1–2 (RUL-13..26)." "**New rulings:** RUL-27
through RUL-34." (`:1-14`). **On #1747:** the literal string does not appear
inside this doc (checked, zero hits); the PR number is sourced from
`research/DO_NOT_REBUILD.md:83`'s citation "Entry-stack Amendment-3 adjudication
(#1747)" and independently repeated by 4+ other docs
(`PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md:31`,
`MAG7_WASHOUT_REENTRY_PREREG.md:292`, `CHINA_STANDOUT_DOUBLE_CONFLUENCE_MASTERPLAN_BY_FABLE.md:155`,
`research/lessons/LESSON_20260723_OPERATOR_FORCED_CALL.md:36`) — convergent but
UNVERIFIED as a direct in-doc citation.

**RUL-27..34** (`:53-158`):
- **RUL-27** — Identity/scope/marginals-first law: A3 registers exactly 3
  interaction families (B/C/D); all further non-momentum×momentum pairings
  deferred to a follow-up amendment gated on A3's marginal survivors.
- **RUL-28** — Verdict-ceiling law (blocker): the 63-bar close-min NC-2-proxy
  band-FE arm is mandatory as a KILL-ARM in every A3 read; verdict vocabulary
  capped at DISPLAY-CANDIDATE/NULL/KILLED; CHIP promotion blocked for ALL A3
  families until the true eq_band lands.
- **RUL-29** — Admission-leg law (blocker): for any weekly-RSI-MACD-derived
  feature, the operative verdict is measured within the ¬wbull (fromos3-admitted)
  subset, never the wbull-admitted subset (which just re-reads the gate's own
  confirm leg).
- **RUL-30** — De-confound battery (kill-only diagnostics): NC-2-proxy band-FE
  (all families), realized-vol-level tercile FE, ¬bear_ctx decomposition,
  pure-age covariate, marginality-vs-A, admission-leg — each can only kill or
  downgrade, never upgrade.
- **RUL-31** — HTF PIT + faithful-math law (blocker, integrated): every HTF
  feature uses the last COMPLETED bar whose known-date ≤ fire date; math pinned
  to `confluence_tiers._rsi_macd`/`_stoch_rsi_kd` (never `cycles.stoch_rsi` or
  price `macd_parts`); leak-audit (shift audit + truncation-invariance fixture)
  mandatory per primitive.
- **RUL-32** — Trial budgets/registration mechanics: program ceiling 165→201;
  itemized budgets per family (table, `:123-132`); every runner must call
  `led.log_trial()`.
- **RUL-33** — Rejection record (citable, do-not-re-walk table, `:140-152`).
- **RUL-34** — Tape-native axes: `not_topped`/`eligible` are constants on the
  frozen tapes; any family stratifying on them is rejected at registration.

**KILL-WASHOUT-TURN / "2W operator seed" — exact construction.** Family **C =
`esx_washout_x_turn`** (`:183-188`): *"The operator's literal '2W StochRSI
washout' seed in its only live form: depth counts ONLY when the higher degree
is also turning... H1's frozen depth feature verbatim × A-turn flags."*
Registration (RUL-32 table, `:127`): *"2 interaction forms (H1-frozen
2W-D-min<25 × {A1, A2}) × 2 panels × 2 contrasts (deep∧turn vs deep∧¬turn;
deep∧turn vs rest)."* Decoded: "2W-D-min<25" = the operator's literal seed —
2-week-timeframe stochastic %D minimum falling below 25 (an oversold-depth
threshold), crossed with A1 (weekly RSI-MACD histogram rising) or A2 (2W stoch
turn = K>D ∧ K rising). **KILL verdict** (`:259`): *"The operator's literal
2W-washout × turn seed adds NEGATIVE marginal value once proximity is removed:
nc2 kills contrast-i (−0.29pp CI incl 0) and the marginality interaction is
adverse (+0.014 baskets / +0.024 deep). Re-confirms the H1 depth kill
fire-conditionally."* Registry row: `research/DO_NOT_REBUILD.md:83` — *"KILL-WASHOUT-TURN
| Washout × turn (2W operator seed) | KILLED — operator seed dies in test |
Entry-stack Amendment-3 adjudication (#1747)"*.

**Overall conclusion** (§F.2, `:263-281`). One genuinely new, cross-panel-replicated
dimension survived: decline path-SHAPE (family E, `esx_decline_geometry`,
shipped display-only). *"The operator's literal '2W/1M StochRSI washout' seed is
confirmed dead in its position form and dead in its interaction form (C KILLED...)
— but its motion form survives on the broad tradeable universe (A1 weekly-turn
on baskets), mostly as a proximity restatement with a thin genuine turn-marginal."*
(`:271-276`). Reading: cycle-scale **position** (depth/oversold-ness) is dead;
cycle-scale **weekly motion** (the turn itself) carries a small real marginal on
small/mid-caps only, not mega-caps. **Precedent for a non-revival, already in
the tree:** `research/TURN_SENSITIVITY_UPGRADE_MASTERPLAN_BY_FABLE.md:46` ships
`mtf_upturn.v1` and explicitly justifies it as *"NOT a revival of the killed
'Washout × turn (2W operator seed)' (different construction: no washout
precondition, no operator seed, per-stock granularity, K-of-N legs)"* — this is
the closest in-repo template for how Radar's own kill-registry compliance
section should be worded (contract §2 already gestures at the same distinctions:
timeframe, role, evaluation ruler).

---

## 4. Prophet selection-alpha status

**Note on the task's exact phrase.** The literal string "incomplete pricing" or
"exit management" (as a confound description) does not appear anywhere in the
repo (repo-wide grep, zero relevant hits — one unrelated match in
`SETUP_SPECIES_MASTERPLAN_BY_FABLE.md:93` about a different program). UNVERIFIED
as a direct quote. The material below is the closest grounded finding set.

**Fixed-horizon selection alpha not yet demonstrated.**
`research/MASTERMIND_PROPHET_EVAL_SPEC.md` §9 scorecard (`:213-229`) prints, as
a first-class line: *"AT ITS RULER  verdicts at declared horizon: 0"* — i.e.
Prophet currently has zero graded verdicts read at its own declared horizon.
Same doc §2 (`:34-64`): 28 closed plans, honest N = 24 distinct signal dates,
win 32.1% vs 30.3% breakeven, t=+0.178, 95% CI [−5.14%, +6.17%] — *"Under
`MASTERMIND_EVALUATION_STANDARDS.md` §4.7 (50-observation reporting floor)
Prophet may currently report accrual status only in any external surface."*
`research/MASTERMIND_INTELLIGENCE_CATALOG.md` Finding C-4 (`:318-322`): *"the
flagship currently has no defensible performance claim, and any marketing that
implies otherwise is unsupported."*

**The one favorable realized number is confounded — closest grounded reading.**
Finding C-5 (`MASTERMIND_INTELLIGENCE_CATALOG.md:324-341`, "the most fixable
defect in this document"): Prophet has two evaluation surfaces and only one is
benchmark-graded — the board (`grade_us_board.py`) grades vs SPY + sector ETF
correctly; **the plan ledger (the 28 closed trades — the surface carrying the
public performance narrative) does not** — its schema
(`[asof, asset, close_date, days_held, direction, id, option_result_pct,
outcome, plan_adherence, schema, signal_date, stock_result_pct]`) has **no
benchmark field**, so `stock_result_pct` is raw return: *"a mean of +0.51%
carries no information about whether Prophet beat SPY, its sectors, or a
matched control"* (`MASTERMIND_PROPHET_EVAL_SPEC.md:174-179`, §7 "The one
defect found"). Separately, `research/PROPHET_ARENA_REGISTRATION.md:65` records
a first-trigger-closure defect on the SAME favorable-outcome field: *"First-trigger-closes.
T1 then later T2 is recorded T1_HIT forever"* — the `T1_HIT` mean (+22.60%, n=7,
the best-performing outcome bucket) is an **incomplete accounting of the
realized move** (a plan that later also clears its T2 target is never
re-labeled), i.e. the one favorable number is confounded both by having no
benchmark leg (raw, not alpha) and by an exit-bookkeeping rule that freezes at
the first target. `MASTERMIND_PROPHET_EVAL_SPEC.md` §3 (`:68-87`) independently
flags that without MFE/MAE data *"it is impossible to tell whether the 11
invalidated plans were wrong or merely stopped out before being right"* — the
same "exit management confounds the read" shape, stated for the loss side.
Remedy already specified (§7, `:181-190`): add `bench_ret_pct`, `sector_ret_pct`,
`excess_vs_bench_pct`, `excess_vs_sector_pct`, `mfe_pct`, `mae_pct`,
direction-signed, to the plan-ledger schema.

---

## 5. DRL (Dislocation & Recovery / price pressure) program

**What it is.** `research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md`
(588 lines, v2 + §12 red-team log). §1 (`:66-80`): detect when a single name's
price is pushed materially away from what market+sector+peers justify (a
residual shock), record everything PIT, track how the residual resolves, show
an honest peer-relative read. *"It is not a buy-signal engine"* — ships
display-tier context freely; any future promotion walks the §7 gauntlet.
**Signal definition** (`:180-189`, `detect.py`): `resid = ret − sector_ex_self_peer(ret)`
(sector map `data/breadth/ticker_sectors.parquet`), `resid_z = resid /
rolling_σ(shifted)`; eligibility = non-split-day ∧ price≥$5 ∧ ADV-median≥$5M ∧ σ
known; **shock** = `|resid_z| ≥ 3 ∧ abnormal volume ≥ 2×` (both sides logged,
down side is the product focus) — imported verbatim from the killed
`DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER` construction's fence
(re-tuning any constant is out of bounds, `research/DRL_CONTINUATION_HANDOFF_2026-08-10.md:42-44`).
**Cadence:** nightly-only ledger writer, gated by `engine/ledger_lane.py::nightly_advance_enabled()`
(`COLLECT_LANE=nightly`); one non-fatal step in `daily.yml`'s tail-desks band; no
network, no intraday ledger writes (`masterplan:164-172`). **Universe:**
`data/massive_stock_day/` panel, ~19-20k tickers, measured 4,281-name eligible
panel (`:224-236`). **Engine paths:** `engine/price_pressure/{panel,detect,context,ledger,artifact,backfill}.py`
(`:162-222`) — `panel.py` (LSR panel, rebuilt in-memory each run, 45-60s, no
committed cache), `detect.py` (fence above), `context.py` (8-K flags, sector/basket
same-day co-move, `pos52`, gap%, volume multiple, CLV, Amihud-rel, VIX 252d
percentile — numeric facts only, never a categorical day taxonomy),
`ledger.py` (append/advance, `transmission_chains` episode pattern),
`artifact.py` (`data/price_pressure/latest.json`, `authority` block with
`can_rank/can_size/can_gate/can_originate_signal/can_escalate` all literal
`false`), `backfill.py` (one-shot historical, run manually, never on CI).

**Prereg format/location — the house precedent to copy.**
`research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md` (354 lines): §0 Provenance
(in-sample sighting disclosed) · §1 Frozen claims · §2 Evidence cells
(construction imported, not tunable) · §3 Conditioning variable (frozen) · §4
Inference (frozen) · §5 Floors and discipline (per masterplan §7) · §6
Consequence matrix (what grading changes) · §7 Clock (honest) · §8 Grading log
(append-only) · §9/§10 dated, append-only amendment sections (pre-merge/pre-evidence
audits, never in-place edits — the same discipline the Radar contract's own §18
"AMENDMENTS (append-only)" already adopts). Status per
`research/DRL_CONTINUATION_HANDOFF_2026-08-10.md:26-34`: R4-A is the sole gating
claim at power floors (320 stressed dates / 640 calm); R4-B demoted to
descriptive-only forever (measured weak in-sample, MDE 2.4-4.9× the sighted
effect under grade-once semantics); eligibility boundary = forward-era rows
dated ≥2026-08-11 only.

**Boundary vs Live Entry Radar (both touch "dislocation/recovery").** DRL's own
§11 "Collision clearance" (`masterplan:508-539`) predates Radar and does not
name it, but the boundary is sharp on inspection: **DRL is a reactive,
single-name, cross-sectional RESIDUAL-SHOCK detector** with an explicit,
standing refusal to become an entry system (§1 quote above; `authority` block
literal-false; `DNR:KILL-FRESH-BUY-EDGE`/`KILL-PRIMED-DIRECTIONAL-GATE` bind it,
`masterplan:141-142`) — its object is "this name got pushed away from fair
value, here is the peer-relative context," graded on a residual-magnitude fence
(`|resid_z|≥3`), and it explicitly excludes any oscillator/turn vocabulary
(`DNR:KILL-PARALLEL-SHOCK-CLASSIFIER`, numeric day-facts only). **Radar is a
prospective, technical-turn ENTRY-TIMING and RANKING system** (washout→turn
detection via StochRSI/histogram state machines, §4 of the contract) that is
explicitly building toward a future promotion path (Research Priority →
Opportunity Score, contract §9) — the opposite disposition from DRL's "never a
buy-signal engine." Zero file/namespace overlap (DRL = `engine/price_pressure/`;
Radar = `engine/entry_radar/**` per contract §16). Zero construction overlap:
DRL's trigger is a **level/magnitude** condition (return residual vs sector peer
group, unconditional on any oscillator), Radar's trigger is a **state-transition**
condition (stochastic/histogram turn, unconditional on residual magnitude) —
the two could in principle co-fire on the same name without either reading the
other's artifact. Reuse worth inheriting: the `engine/ledger_lane.py`
single-advancer gate (§6 below), the `transmission_chains` episode-ledger
pattern, the `authority: {can_rank/can_size/...: false}` display-tier block
convention, and the dated-append-only-amendment prereg shape above.

---

## 6. Forward-ledger conventions

**Single-advancer law.** `engine/ledger_lane.py` (50 lines) — *"the single
definition of the forward-ledger advance gate for the two nightly lanes."*
`nightly_advance_enabled()` (`:23-33`): `True` only when `COLLECT_LANE=nightly`
(or legacy alias `US_LANE=nightly`) — the sentinel `daily.yml`'s engine-job env
sets. `asia_advance_enabled()` (`:39-50`): `True` only when `CN_LANE=asia`
(`asia-close.yml`). Deliberately a leaf module (imports `os` only) so the import
graph stays acyclic and every engine/script that used to define a local
`_ledger_advance_enabled()` now imports from here — this IS the "nightly is the
sole advancer" house law (CLAUDE.md §Ledgers) made mechanical. A SEPARATE,
deliberately-not-unified family (`ledger_lane_armed()` in
`engine/event_window.py`, `ignition_audit.py`, `intl_run.py`,
`market_state_audit.py`, `opex_risk.py`) gates collect-lane *arming* per
invocation, not the ledger append itself — do not conflate the two when Radar
wires its own gate (contract §7 already independently states the same
single-writer law for the intraday/nightly split).

**Example producer/consumer pairs.**
1. `engine.qledger.register`/`register_batch` (producer, append to
   `data/qledger/claims.jsonl`/`grades.jsonl`) → `engine/qledger_ui.py` +
   `scripts/grade_qledger.py` (consumers) → `site/qledger/track_record.json`
   (`emit_track_record`, `qledger.py:2743`).
2. `engine/price_pressure/ledger.py` (producer, nightly-gated append) →
   `engine/price_pressure/artifact.py` (consumer, builds
   `data/price_pressure/latest.json`) → `engine/neuralweb/market_packet.py`'s
   `_pressure_block()` (consumer, chat-facing render) + the stocks-hub Pressure
   Watch band (site consumer).

**MFE/MAE computation precedents (production, not research-only).**
- `engine/forward_dist.py:27,35-36`: `mae = 100.0*(fwd_min/c - 1.0)` (worst dip,
  ≤0), `mfe = 100.0*(fwd_max/c - 1.0)` (best pop, ≥0) — full forward-path
  quantile distributions, not just point values (`:65-81`).
- `engine/track_scoring.py:79-86,197-198,232-233`: per-position `mfe`/`mae` with
  an explicit documented trap: *"`capture` (realised/MFE) needs a STRICTLY
  POSITIVE favourable excursion... a negative realised by a negative MFE prints
  a flattering positive — a −11.4% loss..."* — `MFE_FLOOR = 1e-9` guards the
  division (`:86,409-421`).
- `engine/grading.py:187-244`: `fwd_mfe_{H}` — *"max favorable excursion... the
  maximum [return] over a strictly-forward window (fill, fill+H]"* —
  `result[f"fwd_mfe_{h}"] = max(0.0, float(window.max())/entry_price - 1.0)`
  (`:244`).
- `engine/pick_forward_dist.py:283-339`: `empirical_cone`/`fit_cones` — vol-standardized
  `z_mae`/`z_mfe` quantile cones (`mae_q`, `mfe_q50`), explicitly labeled
  *"Forward outcomes (ret/mae/mfe over the next h bars) are LABELS, not
  features"* (`:30`).
- Research-tier precedent (already cited in §2): `scripts/research/pss_f1_downvol.py`'s
  `mfe21 = max(close[i+1..i+21])/close[i] − 1`.

These four production implementations converge on the same sign convention
(MFE≥0 best favorable move, MAE≤0 worst adverse move, both computed over a
strictly-forward window from a fixed entry) — Radar's §10 MFE/MAE fields should
match this convention exactly rather than inventing a new one.

---

## 7. Matched-control precedents

- **qledger's own second grading leg:** `control_for_sector(sector_name)`
  (`qledger.py:1235-1241`) resolves a sector-matched control ETF (`_GICS_ETF`
  lookup) as the second grading leg alongside `default_bench_for` (SPY default,
  `:1226-1232`) — *"a null control is a valid, honestly-recorded state
  (excess-vs-control simply stays null)."*
- **LSR/DRL's residual construction:** `resid = ret − sector_ex_self_peer(ret)`
  (§5 above) — a peer-basket-matched control built directly into the signal
  definition, not just the grading leg.
- **PSS mirror-placebos:** matched, mechanism-stripped analogs per family (§2
  above) — count as matched-control precedent per the task's framing, though
  they match on *construction* (a parallel signal build) rather than on
  *cohort* (peer selection).
- **`engine/basket_turn_cohort.py`:** cohort-level qledger claims graded
  "cohort EW return vs SPY" — a basket-vs-benchmark matched design, and (per §1
  cross-reference) a live example of registering a washout-turn-adjacent claim
  post-kill.
- **Group Reads baskets:** `research/GROUP_READS_MASTERPLAN_BY_FABLE.md` +
  session handoffs exist (basket participation program, shipped per memory
  `group-reads-basket-participation-program`) — UNVERIFIED in this session
  whether its internal machinery performs excess-vs-benchmark matching or is
  purely a participation/breadth read; not opened (out of budget; flagged for a
  targeted follow-up read if Radar's cohort design needs a second basket-matching
  reference beyond `basket_turn_cohort.py`).
- **Radar's own design already exceeds all of the above in richness:** contract
  §11 specifies matching on session date, sector, market-cap bucket, dollar-volume
  decile, trailing-60d-return quintile, realized-20d-vol quintile, and hotness
  tier (admitted-not-fired) simultaneously — closer to a proper stratified-cohort
  match than any single existing precedent; `engine.group_flow._causal_z`
  (`engine/group_flow.py:83-86`, simple rolling z-score) is cited by DRL §11 as
  the z-convention to reuse for any new z-fields Radar adds.

---

## 8. PIT/vintage precedents

**Field conventions.** The contract itself (`LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md`
§5, `:139-159`) already specifies the target shape: every signal stores
`observed_at, market_session, source_bar_time, source_bar_known_at, bar_state,
data_vintage`, with `bar_state ∈ {confirmed, provisional, stale, unavailable}`.
This matches the existing house pattern in `engine/neuralweb/market_memory_pit.py`,
`market_memory_trusted.py`, `market_memory_forward.py` (PIT-stamped market-memory
family — not opened in depth this session, UNVERIFIED field-for-field match, but
directory-level naming strongly suggests the same `known_at`/vintage discipline).
Amendment-3's RUL-31 (§3 above) is the closest EXACT precedent already in a
ratified adjudication: *"every HTF feature uses the last COMPLETED HTF bar whose
known-date ≤ fire date... Weekly = W-FRI resample with known-date mapping
(reuse `engine/oracle/oscillators.resample_weekly_leakfree`)"*
(`ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md:99-107`) — directly reusable for
Radar's own 2D/3D/weekly known_at mapping (contract §5's one PENDING(TRACK-A) row).

**Replay harness precedent.** `engine/rule_experiments.py` (R1 rule-experiment
registry) is the closest existing general-purpose replay/spec-hash harness:
append-only JSONL registry at `data/rule_experiments/registry.jsonl`
(single writer `scripts/register_rule_experiment.py`), every registration calls
`TrialLedger.log_declared_budget(grid_size, family='replay')` using one FLAT
pooled family (sub-families prohibited — "isolated multiple-testing islands"),
lifecycle `registered → executed → reported`. The runner
(`scripts/run_rule_replay.py`) calls `load_experiment` and compares every spec
hash via `verify_spec_hashes()` (`engine/rule_experiments.py:126`) before
accepting a run — this is the concrete precedent for the contract's own
`detector_spec_hash` field (§13) and PR-2's acceptance gate ("`spec_hash`
stable", §15). `TrialLedger` class: `engine/trial_ledger.py:65`, with
`log_trial()` (`:126`) and `log_declared_budget()` (`:159`) — the same
`led.log_trial()` API Amendment-3's RUL-32 mandates for every A3 runner, so
Radar's look-ledger (contract §11, "append-only look ledger") should very
likely BE `TrialLedger`, not a new store.

**Mutation-test precedents proving no-lookahead.** Repo-wide, 564 test files
reference leak/lookahead vocabulary (`grep -rl` over `tests/`, count only — not
individually opened). Representative, directly relevant to entry-timing PIT
(Amendment-3-era tests, matching RUL-31.4's "leak-audit section (shift audit +
truncation-invariance fixture per primitive) is mandatory"):
`tests/test_entry_primitives_a3.py:105,115,136` — three `test_truncation_invariance`
methods (parametrized across primitives); `tests/test_entry_primitives_a3.py:230`
— `test_no_fillna_leakage`; `tests/test_bottom_sensors_a3.py:212` —
`test_leak_guard_and_gap`. The contract's own §7 leakage matrix
(`:147-159`) already specifies the equivalent test per input row (EOD-mutation
test, same-day-use test, bar-boundary test, rank-vintage test, nomination-postdate
test, recompute-at-vintage test) — these named A3 tests are the closest existing
implementations of that same pattern for Radar's builders to mirror rather than
invent fresh.

**`spec_hash` precedent (beyond rule_experiments.py).** Also present in
`engine/seasonality/contracts.py`, `engine/seasonality/prophet_bridge.py`,
`engine/seasonality/state.py`, `scripts/register_disp_gate_1.py` — not opened
this session (out of budget); flagged as a second cluster worth a targeted read
if PR-2's `spec_hash` implementation wants more than one precedent to compare
against.

---

*Receipts follow fable-mode §3.5 (absence claims carry their search bounds):
"literal phrase not found" claims above were checked via `grep -rn` over
`research/` (and, for §4, the whole repo) for the exact phrasing quoted in the
task; a miss on those specific strings does not mean the underlying finding is
absent — the grounded equivalents are cited in full.*
