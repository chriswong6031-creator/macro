# MWR — Mag-7 washout re-entry gate (pre-registration)

Status: REGISTERED (Fable, 2026-07-24). Operator-chartered, same day as the forced-call
postmortem: "the mag 7 board can be resurfaced when there's an actual washout in mag 7 …
2W STOCH RSI bullish cross under 20 is the best tool for MAGS … the 3D MACD-RSI called the
2024, 2025, 2026 bottoms exactly." This prereg is the lawful path mandated by
`DO_NOT_REBUILD.md` §2 (a Mag-7 leadership read returns only via prereg + gauntlet) —
operator conviction entering as a pre-registration, exactly as
`POSTMORTEM_20260723_MAG7_FORCED_CALL_BY_FABLE.md` R1 requires.

Engine: `engine/mag7_washout.py` (MWR-W0, background-only; `data/mag7_washout/`).
Phase-0 census: `reports/mag7_washout_scan.md` (regenerate:
`python3 scripts/research/mag7_washout_scan.py`). Sibling organ:
`engine/index_momentum.py` (IHM) — RSI-MACD washout_turn tags on the same EW carrier at
1D/2B/3B/W; MWR adds the 2W layer, member breadth, and the gate ladder.

## §0. Epistemic status — read this first

The constructions were chosen by the operator **after** seeing three bottoms on a
TradingView chart of MAGS (ETF history starts 2023). That is a post-hoc fit on n=3 with
selection bias. What phase-0 adds: the same constructions replayed on the house EW basket
2014→2026 (12.5y, 39 signals across families) — the operator's three instances reproduce,
AND the census exposes the failure regime chart-memory missed. Nothing here is validated;
the forward gates below are what can promote it. The word "washout" names three PRIOR
registry kills (§6) — the constructions are distinguished there explicitly.

## §1. Pinned constructions (changing any = prereg amendment, disclosed)

- **Series**: daily-rebalanced equal-weight basket of AAPL MSFT NVDA AMZN GOOGL META TSLA
  from `data/baskets/ohlcv` (house form — NOT MAGS; longer history, no inception
  truncation). Members individually for breadth.
- **Bars**: 2W = W-FRI closes at even index from the 2014 series start (**anchor A**,
  pinned — TV 2W bars are phase-sensitive; A matched the operator's chart K≈53 vs our
  55.1 on 2026-07-24; anchor-B values are emitted in the scan for robustness reads).
  3D = 3-trading-day block closes. 1W = W-FRI.
- **Stoch-RSI**: Wilder RSI(14) (`engine.technicals.rsi`), stoch window 14, K smooth 3,
  D smooth 3 (TV defaults).
- **RSI-MACD**: MACD(12,26,9) computed ON the RSI(14) series (TH_RSIMACD+ analog; the TV
  script's exact params are unpinned — operator to confirm; amendment allowed BEFORE any
  forward trigger is graded, never after).
- **S1 (primary)**: 2W Stoch-RSI K crosses above D with prior-bar K < 20.
- **S3 (precision arm)**: 3D RSI-MACD line crosses above signal while line < 0, valid
  only while the gate is ARMED (2W K < 20 within the last three 2W bars, or breadth).
- **Breadth**: count of members with 2W-A Stoch-RSI K < 20; ≥4/7 = cohort washout
  (operator's heterogeneity point: TSLA ≠ AAPL — a 1-2 name drag is not a cohort event).
- **States**: idle → washed_out (2W K<20 or breadth ≥4/7) → triggered (cross while
  armed). Triggers append once to `data/mag7_washout/triggers.jsonl` (nightly-only).
- **Member-level series**: same parameters on each member's own closes — census and
  attribution context ONLY (§2b); no per-name signal claim exists in this prereg.
- **Registration**: both artifacts are on the signal bus (`config/synapse.yml`
  owner_program `mag7-washout`, tier `display`, no site consumers by ruling).

## §2. Phase-0 census results (descriptive, not a gauntlet pass)

S1 anchor-A, 2015→2026: **13 signals — 10 good, 3 bad** by the descriptive lens
(fwd63 > 0 and adverse > −10%). Median fwd63 ≈ +15.7% vs +8.9% all-days baseline.
Caught 2016-02, 2018-05, 2019-01, 2020-05, 2021×2, 2023-01, 2024-09, 2025-04, 2026-04.
**All three failures are the sustained 2022 bear** (2022-03: fwd63 −26.1%, adverse
−27.2%; 2022-06: −8.2%; 2022-11: −15.6% adverse first). S2 (1W) and S3 (3D) show the
same shape: superb at capitulation lows inside secular uptrends (S3 2025-04-24: +28.6%,
adverse 0; 2026-04-09: trough 7td prior), lethal in 2018-Q4/2022 downtrend rallies
(S3 2018-12-03: −18.2% adverse; 2022-03-18: −27.2%). The operator's three claimed calls
all reproduce in our stores.

**The open question phase-0 does NOT answer**: the 2022-class conditioner. Three failure
instances are not fitting material — any "bear-regime guard" tuned on them would be
overfit-on-the-overfit. The NAMED candidate list below is the phase-1 comparison budget
(multiplicity-counted; adding a candidate = amendment):

1. **Policy-direction / tightening-speed regime** (operator hypothesis 2026-07-24:
   "2022 … was a rate hike year"): ΔFFR over trailing ~6mo from the house DFF store;
   see §2c tags.
2. **Election-cycle position — as MODULATOR ONLY** (operator: "2022 is a midterm
   year"): prior art REQUIRES this form — "Election / midterm cycle as standalone
   signal: REFUTED — survives only as US-only Risk-Radar modulator" (registry §2), and
   hard-wiring a midterm gate without adjudication is a FORBIDDEN pattern (registry §1,
   "midterm-blackout gate" laundering row, BTC-vector audit). It enters through this
   prereg's phase-1 or not at all.
3. **Weekly+monthly structure veto** (postmortem rule R2 — the 2022 cluster is R2's
   evidence from the long side; may unify with #1).
4. **Drawdown depth/duration at signal** (fast-shock V-bottoms 2019/2020/2023 vs the
   2022 slow grind).

## §2b. Per-member census (phase-0b, operator ask 2026-07-24 — "which stocks does it
work on, which are noise / a different beast")

Same S1 construction, each member on its own tape, 2015→2026 (report has full tables):

| series | n | good (fwd63>0 & adverse>−10%) | median fwd63 | worst adverse |
|---|---|---|---|---|
| **EW basket** | **13** | **10 (77%)** | **+15.7%** | **−27.2%** |
| AAPL | 19 | 11 (58%) | +9.3% | −28.7% |
| MSFT | 16 | 9 (56%) | +7.8% | −24.4% |
| NVDA | 19 | 7 (**37%**) | +8.0% | −35.2% |
| AMZN | 18 | 11 (61%) | +9.4% | −26.2% |
| GOOGL | 16 | 10 (63%) | +9.3% | −24.5% |
| TSLA | 18 | 11 (61%) | +13.1% | −37.6% |
| META | 15 | 8 (53%) | +8.4% | **−47.1%** |

Findings (descriptive; no per-name authority is created here):
1. **The basket beats every member on every column** — fewer signals (13 vs 15-19),
   higher good-rate (77% vs 37-63%), double the median payoff. The cohort aggregation
   IS the signal: the EW basket only washes out when selling is synchronized, which
   filters the idiosyncratic single-name flushes that dominate member-level series.
   Basket-primary stands; member series are context/attribution, not signals.
2. **NVDA is the different beast** (37% good — a momentum name whose washouts tend to
   CONTINUE; buying NVDA weakness on this tool alone was a coin flip with a −35% tail).
   **META carries the catastrophe tail** (−47.1% = the 2022 structural repricing —
   washout oscillators cannot see fundamental regime breaks). TSLA — contrary to the
   heterogeneity intuition — is one of the BEST per-name fits (61%, highest median
   +13.1%: high-beta mean-reverter). Any NVDA/META-specific entry tool is a different
   mechanism and requires its own prereg; nothing here transfers.
3. **Attribution:** the strongest basket signals came with full-cohort washes
   (2025-04-25 and 2026-04-10 = 7/7 members; 2019-01 = 6/7) — but the 2022 failures
   ALSO ran 5-7/7. Breadth therefore CANNOT be the 2022-class conditioner (§2's open
   question stands as a regime question, not a breadth question). Breadth ≥4/7 is
   retained ONLY as an alternative arming condition, never as a quality filter.

## §2c. Environment tags on the S1-A census (descriptive; conditioner hypothesis)

Every basket S1-A signal tagged with midterm-year + trailing-6mo ΔFFR (DFF store;
full table in the report). The honest reading at n=13:

- **All three failures sit in the midterm ∧ hiking cell** (2022-03/06/11 at +25/+150/
  +300bp) — the operator's environment claim has real support;
- **but the cell contains a winner** (2018-05, midterm + hiking +54bp, +12.8% fwd63),
  hiking-alone is 3 GOOD / 3 bad (2019-01 +49bp and 2023-01 at +275bp trailing — the
  terminal-hike pivot — were among the best entries), and
- **2026-04 is itself a midterm-year washout that WORKED — with the Fed cutting
  (−46bp)**: the cleanest single illustration that 2022's poison was the environment
  conjunction, not the calendar year.

No threshold is fitted here. Instead the ENGINE now stamps every forward trigger with
`midterm_yr` / `policy` / `dffr_6m_bp` AT FIRE TIME (hindsight-proof); the phase-1
conditioner adjudication runs on those stamped forward triggers plus this census under
one pre-stated ruler.

## §3. What accrues now (display-tier, freely)

Nightly `snapshot()`: gate state + 2W K/D + 1W/3D RSI-MACD + member breadth into
`latest.json`; trigger events into `triggers.jsonl`. No surface, no consumer — the
artifact exists to build the forward record. Interactive sessions never advance the
ledger (house ledger law).

## §4. Uses and gates

- **Use-A — process gate (in force now).** Any proposal to resurface a Mag-7
  leadership/entry surface must cite a `triggers.jsonl` event within the preceding 63
  trading sessions, plus the DO_NOT_REBUILD §2 conditions (prereg + gauntlet + operator
  ruling). No trigger → no proposal. This is de-escalatory only (it can delay, never
  force) — promotable without a gauntlet as process law.
- **Use-B — timing signal (authority; NOT in force).** Claim to be tested: an S1/S3
  trigger marks a favorable Mag-7 entry. Grading per trigger (pre-stated): HIT =
  fwd63 > all-days baseline median AND adverse > −10%; FAIL = fwd63 < 0 OR adverse
  < −15%; else MIXED. Promotion needs: ≥8 graded forward triggers (history: ~2-3/yr)
  with ≥6 HIT and 0 catastrophic (adverse < −20%), OR a jointly-adjudicated read of
  forward triggers + the 39-signal census under one ruler. KILL: 2 consecutive forward
  FAILs, or any single adverse < −25% (the 2022-03 class) → construction returns here
  for redesign, not to a surface.

**Adjudication log — 2026-07-24 (operator activation motion).** The operator moved to
activate Use-B on census evidence ("statistical significance and reliability (ex-2022)").
§4's jointly-adjudicated-census clause was invoked: ruler pre-stated in
`scripts/research/mwr_phase1_adjudication.py`, results in
`reports/mwr_phase1_adjudication.md`. **VERDICT: FAIL against the pre-stated bar.**
The decisive number: the all-days baseline GOOD-rate is **69%** — in a 12-year secular
Mag-7 uptrend, a random entry was "good" (fwd63>0, adverse>−10%) two times in three, so
the signal's 10/13 has p=0.367 against spacing-matched random days. Primary
median-fwd63 (+14.7% vs +9.5% baseline) reaches p=0.048 raw but **0.238 after the ×5
construction-selection haircut**; the anchor-B twin of the same construction shows
p=0.314 (anchor-phase fragility). Era-split and LOCO are stable-positive, so a modest
real edge is NOT excluded — but the census cannot ratify it. Forward gauntlet stands.
"Ex-2022" conditioning remains unlawful without a pre-registered conditioner (§2).
Any operator override from here requires an explicit `DO_NOT_REBUILD` §2 amendment made
against these recorded numbers, eyes open.

**AMENDMENT 2 — operator override: Use-B → CONDITIONAL-LIVE (2026-07-24).**
Operator ruling, issued twice and executed here: *"we will use first principles
conclusion for this, and you can change the prereg to allow for this exception, i
authorize it."* Evidence basis at ruling time (`reports/mwr_phase1_conditioner_study.md`,
1,630 names / 27,647 signals): mechanism-interaction gradient CONFIRMS direction
(chop −0.59% → strong-trend +0.58% median uplift; MAG7-EW +5.74% — a 10× outlier even
in the favorable class); conditioner direction CONFIRMS the operator's 2022 narrative
(hike_accel −1.02% vs hike_decel +1.98% / cutting +2.44%); corrected family-wise
p = 0.143 (max-stat null — the earlier ×5 Bonferroni was over-conservative and is
retracted). ON THE RECORD against it: MCD −0.03% / COST −2.91% (the operator's own
example names show no uplift — the class does not explain the MAG7 magnitude);
hike_accel CI includes 0 [−5.08, +1.61]; anchor-B fragility stands. Fable's position:
magnitude unproven, promotion premature — recorded, not relitigated. The override is
the operator's constitutional right (PRD Amendment-1 precedent).

Terms (binding):
1. **Conditional-live**: a trigger is ACTIONABLE only when the fire-time regime ≠
   `hike_accel` (trailing-6m ΔFFR ≥ +25bp AND still rising vs 91d prior). Engine emits
   `regime` / `gate_actionable` / `veto`; the operator ping carries
   ACTIONABLE / VETOED / regime-unknown copy. Disclosed cost: the veto would have
   removed 2018-05-04 (+12.8%) along with all three 2022 failures.
2. **Regime unknown** (DFF store absent) → `gate_actionable: null` — manual check,
   never a silent pass.
3. **Kill-switch unchanged and binding**: 2 consecutive live FAILs, or any single
   adverse < −25%, auto-demotes Use-B back to background and reopens this log.
4. **Prophet linkage stays presentation-tier**: entries NEVER join the graded board
   population (`DO_NOT_REBUILD` §1 Top-setups contamination row, ratified 2026-07-24,
   governs identically here); the W2 surface is a washout-entry card beside Prophet +
   admin gate console, built through the normal build lane before any plausible
   trigger (gate is idle, 2W K ≈ 55).
5. The shadow book continues as the live grading record; §7 recipes unchanged.

## §5. Non-goals

No auto-alerts, no page panel, no stance copy, no feed into rank/size/gate anywhere.
A future surface, if earned, starts as a Tier-2 receipt inside an existing Mag-7 data
display, not a board.

*(Amendment 2026-07-24-b, pre-forward-trigger per §1: an OPERATOR-audience ops
notification on trigger events is allowed — Discord ops channel via
`scripts/notify_turn_events.py` source (f), state-day dedup, ~2-3 events/yr expected.
The gate must reach the operator to function as a gate. PUBLIC surfaces remain out
until the gauntlet; nothing in §7 touches selection, rank, size, or the live board.)*

## §7. W1 integration map (registered 2026-07-24 — wiring built dark; recipes pinned
BEFORE the code, promotion stays behind §4)

Operator intent: "tie this deeper … triggering entries and getting these picks onto
Prophet … a very important key indicator." Lawful decomposition: everything below is
display/shadow tier. The live-entry and live-Prophet paths are NOT built — not even
behind a flag — so no un-gauntleted selection path exists to flip on by accident.

- **W1a — Shadow book** (`engine/mag7_washout_shadow.py`, the §4 Use-B evidence
  vehicle; mirrors `prophet_stage_shadow`'s pure-accrual discipline). Recipe, pinned:
  every `triggers.jsonl` row spawns 8 hypothetical unit-notional entries — the EW
  basket + each member (per-name accrual continues §2b's beast question forward).
  Entry basis = **next-session CLOSE after trigger date** (one price basis, closes
  only, conservative vs the census's t0 close). Grades at maturity from store closes:
  ret21, ret63, adverse63 (worst close ≤63td), env tags carried from the trigger row.
  Ruler (frozen): HIT = ret63 > +8.9% (census all-days median, pinned) AND adverse
  > −10%; FAIL = ret63 < 0 OR adverse ≤ −15%; else MIXED. One row per
  (tf, trigger_date, instrument), appended ONLY at 63td maturity — idempotent;
  `data/mag7_washout/shadow_book.jsonl`; nightly is the sole advancer
  (`ledger_lane.nightly_advance_enabled()`). Open positions mark-to-market in
  `shadow_state.json` (display context). The BASKET rows are the §4 gauntlet rows;
  member rows are diagnostic only.
- **W1b — Operator trigger ping** (`notify_turn_events` source (f)): fires on fresh
  trigger rows, dedup (kind=`mwr_trigger`, tf, date). Copy is process-language
  ("gate open — re-entry proposals lawful per MWR §4 Use-A"), never a buy call.
- **W1c — Neural-web context lobe** (`world_state._compose_mag7_washout`): gate
  state + K/D + breadth + last trigger as an always-display_only/is_context_only
  block (darkpool-lobe discipline: honest-null when absent, LLM consumers may only
  de-escalate).
- **W1d — Prophet confluence sidecar** (`data/mag7_washout/prophet_confluence.jsonl`):
  nightly, for every US board pick with ticker ∈ M7 (snapshots_v2 lanes), append
  (as_of, lane, ticker, gate state, K, breadth) — dedup (as_of, lane, ticker).
  READ-ONLY with respect to Prophet: stamps context on picks Prophet already made;
  selection/rank untouched. This accrues the natural experiment "do Prophet Mag-7
  picks behave differently when the gate is armed?" — graded jointly with the board
  ledger's own outcomes at gauntlet time, ruler to be fixed in a §7 amendment BEFORE
  first read of the joint result.
- **Deferred to W2 (not built)**: mastermind brain lobe (`mastermind_context`
  summarize), admin gate tile, any prophet-governor lane registration (deliberately
  absent per the no-dark-selection-path rule above), any public Tier-2 receipt
  (§5 gauntlet condition unchanged).

## §6. Distinctions from prior washout kills (blocklist compiler: these are different constructions)

- "Washout × turn (2W operator seed)" KILLED (#1747) — an entry-stack interaction
  feature on a different universe; not a cohort-scoped re-entry gate. The rhyme (operator
  seed, 2W, washout) is exactly why THIS one is pre-registered instead of shipped.
- "Buyback-floor washout (S11)" FALSIFIED — buyback-support mechanism, unrelated.
- "MCO thrust / MCO-oversold+MSI-washout bounce as radar legs" REJECT-KILLED
  (coincident-by-construction) — breadth-oscillator radar legs graded on coincidence.
  Acknowledged head-on: MWR's Use-B is graded on FORWARD returns with pre-stated
  hit/fail/kill rules, and Use-A is a gate, not a forecast.
- DO_NOT_REBUILD §2 forced-call row — this prereg is that row's mandated re-entry path.
