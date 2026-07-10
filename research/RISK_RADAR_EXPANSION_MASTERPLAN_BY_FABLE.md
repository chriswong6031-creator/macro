# Risk Radar Expansion — breadth thrusts, bottoming & topping signals (adjudicated research)

**Author:** Fable (main loop) · **Date:** 2026-07-10 · **Status:** RESEARCH + BUILD PLAN (no engine code in this PR)
**Method:** 8-lane parallel census+literature workflow (Sonnet) + 2-lane adversarial red-team (Opus), 47 candidate
verdicts, synthesized by Fable. Rulings herein: **RRX-R1..RRX-R10**.
**Charter:** make `engine/risk_radar.py` more robust and smarter by integrating breadth thrusts, bottoming signs,
topping signs, and other regime indicators — **without violating the evidence-gated architecture that makes it honest.**

---

## 0. TL;DR

The single highest-value finding is **not a new signal — it is a missing lane.** The radar has a validated
risk-RISING side (regime-typed scares, measured lift, context-gated banner) and a de-escalation read
(`trajectory` + `deescalation`), but the recovery panel (`engine/risk_radar_recovery.py`) confirms a turn with
**central-bank liquidity catalysts only** — it has **zero market-internal confirmation input** (no thrust, no
follow-through, no capitulation-resolution, no credit rollover), and the forward-grading audit its own docstring
asks for (`risk_radar_recovery_audit`) **does not exist**. Breadth thrusts and bottoming signals are exactly that
missing input — and in-house evidence already points the same way: the dislocation re-entry probe
(`research/DISLOCATION_VALIDATION.md`) found Zweig-thrust-confirmed re-entries hit 66.7% (n=12, medRet +6.1%,
medDD −1.7%), and `research/SP_VECTOR_VIABILITY.md` Phase 2 already plans a "breadth-thrust re-entry" leg.

Second finding: **thrust-family signals structurally cannot be Tier-A legs.** Zweig-class events fire ~1–2 per
decade; the promotion gauntlet (`risk_radar_backtest.gate_report`: day-level lift at thr_pct on ≥8% drawdown-onset
within 15bd, 2020+ holdout, frequency-matched permutation) needs hundreds of elevated days, and thrusts are
*re-risk* events scored against a *drawdown-onset* ruler — wrong direction AND wrong power. Their honest homes:
**(i)** recovery-panel confirmation chips, forward-graded at a **pre-declared rebound ruler**, **(ii)** display
context, **(iii)** context-gate modifiers. This is the epistemic backbone of the whole plan.

Third finding: the genuinely new **risk-rising** candidates that survived red-team are few and specific:
NH-contraction-at-fresh-highs (Tier-B accrue, zero data cost), **implied correlation ^COR1M/^COR3M** (the only
vol-family candidate with deep free PIT history, 2007+ — a real gauntlet attempt is possible), **JPY carry-unwind
stress** (deep FRED data, new transmission channel), and copper/gold (probe already flagged in
RISK_ENGINE_V2_FINDINGS §3). Everything else popular — Hindenburg Omen, Titanic, IBD distribution days, McClellan
variants, %>200dma washouts, absolute-VIX fade rules — was **rejected with grounds** (kill list §6, appended to
DO_NOT_REBUILD in this PR).

Data substrate: two collector builds unlock the strongest blocked family (Lowry/Desmond 90% up/down days,
Eureka/Phoenix, 9-to-1 volume days, TRIN): a **market-wide up/down-volume + up/down-points aggregate**. One
red-team "gap" was wrong: **`data/yahoo/_VIX3M.parquet` already exists (2006-07→present, 5,022 rows)** — the
VIX-backwardation-resolution confirmer is buildable *today*. (Note: `data/yahoo/COR.parquet` is Cencora the
stock, NOT implied correlation.)

---

## 1. Current state — what the radar has, and the three gaps

**Has (verified):** regime-typed scares (credit/rates/bubble/growth Tier-A; vol/global Tier-B) built from causal
504d trailing percentiles; per-leg measured lift (`_LEG_CALIB`, VALIDATED = lift_2020 ≥ 1.20); context gate
(SPY<200dma AND `pct_above_200` causal pctile ≤0.40) that lifted banner precision 0.085→0.249
(`research/RISK_RADAR_TUNING.md`); armed+confirm conjunction; forward-outcome log
(`data/risk_radar/forward_log.jsonl` — 12 rows, 0 graded yet, review loop arms at 30 graded); A6 two-lane
governance for any calibration change; trajectory/de-escalation read feeding a recovery panel.

**Gap 1 — recovery confirmation (the big one).** `risk_radar_recovery.py:_liquidity_catalysts()` is 100%
central-bank liquidity (Fed net-liq, Fed policy, PBoC, global CB tide). A liquidity turn with no market-internal
confirmation is a weaker turn than one confirmed by both. There is no `_market_catalysts()` and no
`risk_radar_recovery_audit` grader — so even if we shipped confirmation chips today, nothing could ever mature
them. **The infrastructure gap precedes the signal gap.**

**Gap 2 — topping-side pre-break blindness (acknowledged, partially structural).** The loud banner requires
SPY<200dma, deliberately sacrificing the earliest froth precursors (TUNING §5). The bubble scare has two legs
(`bubble_ext` 2.34× 2020+, `bubble_leadership` 0.38×). The tuning doc itself names the milder breadth-pctl-only
gate (precision 0.162, recall 0.76) as the pre-break alternative. New topping candidates should be judged as:
does this add a *pre-break* read the bubble scare lacks, without re-deriving the killed `breadth_div` self-canceller
(1.78× full but **0.69× 2020+** — dead in the modern era)?

**Gap 3 — orthogonal channels.** Four mechanisms have no leg at any tier: **directional volume** (conviction-
weighted breadth — immune to the pct_above_200 self-cancel failure mode), **implied correlation** (crowding /
crash-propagation), **FX-carry funding stress** (Aug-2024-class unwinds), and **funding-market plumbing**
(SOFR-OIS/FRA-OIS class; every FRED stress composite embeds equity vol → circular; a funding-only read is not).

---

## 2. Data substrate census

| Substrate | Depth | Notes |
|---|---|---|
| `data/breadth/breadth.parquet` | 1962→now, S&P 500 | n_members, pct_above_50/200, nh, nl, adv, dec, ad_line. **Survivorship-biased pre-~1990** (today's-members rebuild); `sp1500_pit_membership.parquet` exists for PIT historical builds but the live series doesn't use it |
| `_closes/_high/_low/_volume` caches | 329 rows / 35 / 35 / 35 | per-ticker wide panels, gitignored, runner-local; deep closes panel is runner-local only |
| smallcap/midcap breadth | 2023-07→now | same 8 cols — cross-tier thrust reads possible but shallow |
| china/hk/intl breadth | 1991+/2000+/2021+ | same shape (intl lacks n_members/ad_line) — every US construct here has a cheap regional port |
| `data/yahoo/_VIX3M` + `_VIX9D` | 2006+/2011+ | **already collected** — backwardation-resolution confirmer buildable now |
| VIX futures term / put-call / GEX | live-only (accruing) | unchanged from v2 findings |
| Implied correlation ^COR1M/^COR3M | **not collected** | free via Yahoo, back to ~2007 — the one missing deep vol series |
| Market-wide up/down volume, up/down points | **does not exist anywhere** | blocks Desmond/Eureka/Phoenix/9:1/TRIN family |
| FRED: DEXJPUS, T10Y2Y, BAMLH0A0HYM2, NFCI/STLFSI4; OFR FSI (API); ECB US New-CISS (API) | deep | composites carry pub lag (T+1 CISS, T+2 OFR, weekly NFCI/STLFSI) — display-tier only, lag-honest |

**Methodology guardrail (RRX-R1, binding on every construct below):** all A/D-family indicators are computed on
the **S&P panel, never raw NYSE all-issues** (preferreds/CEFs/bond-CEF contamination is the classic Hindenburg/
A/D failure); historical tallies honor the mature-universe gates (`MATURE_N`/`THRUST_MATURE_N` precedent in
`advanced_breadth.py`); any historical event roster must use PIT membership; the S&P proxy fires thrusts more
often than the canonical NYSE rosters (documented in-module) so **literature event stats do not transfer** — our
own forward log is the only ruler that counts.

---

## 3. The rebound ruler (new, pre-declared — RRX-R2)

Recovery confirmers must not be scored on the drawdown-onset ruler (wrong direction, wrong power). Per the
horizon-ladder law (verdicts only at pre-declared `horizon_role`), this plan pre-declares ONE recovery ruler
before any chip accrues:

> **Rebound-capture ruler:** conditioned on the radar in `phase ∈ {peaking, receding}` (something to recover
> FROM), a confirmer is graded on SPY forward returns and max-adverse-excursion at **h21 (primary) and h63
> (secondary)**, vs the matched base rate of all peaking/receding days without the confirmer. Significance by
> **within-episode time-preserving permutation** (episode-label permutation per the month-block-bootstrap law;
> ticker-cluster and month-block estimators forbidden). Era split at 2010 mandatory. Small-N printed, never hidden.

The grader (`engine/risk_radar_recovery_audit.py`, W0) extends the existing `forward_log.jsonl` pattern: one line
per day recording which confirmation chips were lit + the trajectory phase; deterministic SPY-path grading; same
idempotent-by-asof convention as `risk_radar_audit.py`. LLM-legality note: everything here is deterministic; the
whole lane is de-escalation-side, which is the direction LLMs/keys may legally gate — but no LLM emits any chip.

---

## 4. Adjudicated catalog — ADOPT side

### 4A. Recovery / re-risk confirmation chips (`_market_catalysts()` in the recovery panel)

All display-tier + forward-graded on the rebound ruler. None touches `_LEG_CALIB`, state, or gross. The panel's
`turn_confirmed` upgrades from "receding AND fresh liquidity catalyst" to a two-channel read: **liquidity turn ×
market-internal confirmation** (each channel shown separately; conjunction labeled).

| # | Chip | Construction | Grounds / caveats |
|---|---|---|---|
| C1 | **Thrust-confluence (K-of-N, counted ONCE)** | One chip over {Zweig 0.40→0.615/10d EMA of adv share; Deemer BAM 10d Σadv/Σdec >1.97; Whaley ADT5 5d ≥73–75% advancers; Triple-70}. A single underlying breadth burst lights ONE chip with a K count — never four chips | The 2023-01 "Breadth Trifecta" co-fire proves these are one event, not four. Shipping per-author legs would let the recovery panel double-count (RRX-R3). Lit stats (ZBT ~14–18 NYSE events since 1945, 6m +17%/12m +23%; 1984–2004 drought) are long-side, small-N, NYSE-universe — display honesty labels mandatory |
| C2 | **McClellan Summation low→high swing** (sub-100 → >+1000) | Slow second-integration expansion event (~29 since 1962), mature-window gated | Distinct from the KILLED fast-MCO constructs: SIGNAL_AUDIT's coincident-by-construction ruling targets internals *leading price* on the risk-rising side; a recovery *confirmer* is allowed to be coincident-with-the-turn — confirmation is its job (RRX-R4). The deep-oversold MCO *bounce* variant stays killed (fires at every bear rally, 2001-02/2008) |
| C3 | **ONE canonical %>Nd washout→thrust round-trip** | Two-leg event: panel %>20dma <~25% → >~90% (deGraaf-class). Pick ONE lookback; do NOT ship a %>10d and %>20d family (RRX-R5) | ~2 events/yr = a gradeable record by ~2028, unlike ZBT's 1–2/decade. Panel-computed (no NYSE contamination). Single-condition >90% version fires ~8×/yr — context descriptor only, not the chip |
| C4 | **O'Neil Follow-Through Day** | Day ≥4 of rally attempt, index +≥1.x% on volume > prior day | The only pure price+volume chip — orthogonal to all breadth chips; buildable today from index OHLCV. Honest independent stats (~55% success, Quantifiable Edges) make it a graded confirmer, not an oracle; its documented weakness (no breadth component) is covered by C1–C3 sitting beside it |
| C5 | **Retest breadth divergence (consolidated)** | At a price retest of a prior low: (a) fewer new lows than at low-1 (nh/nl) AND/OR (b) A/D line higher-low vs price lower-low. ONE chip, two facets (RRX-R6) | The bottoming mirror of the one internals leg SIGNAL_AUDIT explicitly KEPT (A/D-vs-price divergence). Retest-conditional (mute in V-bottoms); fires prematurely in grinding bears — grade it, don't trust it |
| C6 | **VIX term-structure inversion RESOLUTION** | Binary VIX>VIX3M episode ends (ratio re-crosses <1.0 and holds N days). Data already in store (2006+) | NOT the killed VIX-term-ROC (that was a risk-rising lead; this is a re-risk event). Lit: +3.04%/88% at 5d, +4.38%/91% at 21d vs +0.26%/60% base (options.cafe, ~43 episodes — small-N, misses grinding bears like 2022). ~43 episodes ⇒ within-episode permutation only |
| C7 | **HY-OAS ROC rollover** | The engine's own most era-robust series (BAMLH0A0HYM2 21d ROC, 1.94×) turning down from a ≥90th-pctile peak | **Best-positioned chip to eventually earn de-escalation authority** — it reuses an already-gauntleted series; zero new data. Failure modes on record: 2015-16 false peak, COVID simultaneity |
| C8 | **Vol-instability veto (RVV proxy)** | 21d realized vol of daily VIX changes still elevated ⇒ a `turn_confirmed` is withheld (veto, not signal) | Recovery-side gate on trust: "is vol itself still erratic?" Persistence classifier, not a lead; free proxy skirts the killed-VVIX physics only in veto role — never a scoring leg |

### 4B. Risk-rising candidates (Tier-B accrual now; Lane-(ii) gauntlet where history permits)

| # | Candidate | Tier & path | Grounds |
|---|---|---|---|
| R1 | **NH-contraction at fresh index highs** — index at/near 252d high while % of members at new 52wk highs contracts vs prior index highs | Tier-B accrue into `bubble` scare (display/escalator), zero data cost (nh in store) | Event-conditioned narrowing read — mechanically distinct from the killed continuous `breadth_div` self-canceller. Q4 52wk-window seasonality must be adjusted; 2010/2011 false-negatives on record. Realistic ceiling: permanent confluence input |
| R2 | **Implied correlation ^COR1M/^COR3M level/ROC** | **New collector + Lane-(ii) machine-registered gauntlet attempt** — the only vol-family candidate with deep free history (2007+) | v2 findings: the vol scare has NO backtestable leading leg. Fed lit (Pollet-Wilson; Park) supports variance forecasting at 3–4wk horizons. Pre-committed gate: lift_2020 ≥1.2 @ thr 0.90, era split, freq-matched perm. Pass → first real Tier-A vol leg; null → Tier-B confluence, printed |
| R3 | **JPY carry-unwind stress** — USD/JPY 10d ROC × realized-vol pctile, sign-conditioned (USD/JPY < 50dma strips safe-haven false positives) | Tier-B accrue into `global` scare + Lane-(ii) attempt (FRED DEXJPUS deep/free/no-lag) | New forced-deleveraging channel (Aug-2024: USD/JPY −12%, SPX −8%). 2022 sign-inversion documented ⇒ escalator/amplifier physics, most potent with VIX rising |
| R4 | **Copper/gold 65d ROC** | Tier-B accrue into `growth` scare | Already flagged probe-level in RISK_ENGINE_V2_FINDINGS §3 (~22d lead in probe). Days-only lead in lit + 10y-yield collinearity ⇒ likely permanent confluence |

### 4C. Context / display tier (ships freely; no promotion track unless stated)

- **Composite stress tag — pick ONE: US New-CISS** (daily, T+1 — fastest free composite; ECB API). OFR FSI (T+2)
  and NFCI/NFCIRISK (weekly, ALFRED-vintage for PIT) recorded as alternates; **STLFSI4 skipped** (weekly, dominated).
  All embed equity vol ⇒ **never fused into scoring** (circularity), lag-honored display only.
- **Bear-steepener regime tag** (2s10s steepening from inversion vs from normal; FRED T10Y2Y) — ~15 events/63y,
  display-only by construction.
- **ONE consolidated stock-bond correlation regime tag** (63d SPY×TLT sign/percentile) — hedge-validity context,
  explicitly not an equity-drawdown predictor (2023 counterexample on record).
- **Retest-vs-V-bottom morphology label** on the recovery panel — the taxonomy that tells the reader WHICH
  confirmer applies (C5 needs a retest; C1/C4 confirm V-shapes). Editorial probabilities forbidden from
  "validated" vocabulary (CI-enforced).
- **RSP/SPY concentration descriptor** — already computed in `index_leadership.py`; surface, don't rebuild;
  CXO: R²≈0.001 as return predictor ⇒ pre-declared null, display forever.
- **Coppock Curve monthly stamp** — lagging by construction (1–6mo post-trough, 45% bear-market hit rate);
  check overlap with `htf_durability` monthly phase before building; lowest priority.

---

## 5. Build plan (waves; all display/Tier-B — nothing touches state, gross, or the banner)

- **W0 — plumbing first:** `engine/risk_radar_recovery_audit.py` (rebound ruler §3, forward log, grader) +
  `_market_catalysts()` scaffold in the recovery panel with the chip interface + honesty labels. *Without W0,
  chips can accrue nothing.*
- **W1 — buildable-now chips:** C1 (confluence over adv/dec, mature-window gated), C2, C3, C4, C5, C6 (VIX3M
  in store), C7, C8. Every chip ships with `accruing` labels and its lit-stats printed as *reported, not ours*.
- **W2 — collectors:** market-wide **up/down-volume + up/down-points** nightly aggregates (from the deep closes
  panel + volume history; committed by the producing job per the cross-job-artifact law). ^COR1M/^COR3M collector.
  After ≥252 rows, the 90%-day suite (Desmond/Eureka/Phoenix, 9:1 days, TRIN as a derived ratio) joins 4A as
  accruing chips — the volume channel is the one breadth family immune to the pct_above_200 self-cancel mode.
- **W3 — risk-rising accruals + gauntlets:** R1 into `bubble` (Tier-B), R3 into `global` (Tier-B), R4 into
  `growth` (Tier-B); Lane-(ii) machine-registered experiments for R2 and R3 with pre-committed gates + come-back
  dates (A6 two-lane ruling compliance).
- **W4 — context/display tags** (§4C) on the radar card / market pages.
- **W5 — deferred dockets:** funding-only stress sub-composite (SOFR-OIS/FRA-OIS/x-ccy basis — needs its own
  data assessment); Kritzman-Li turbulence + absorption ratio as a context-gate *multiplier* (deep free data via
  sector/industry panels; flagged by red-team as the one missing "propagation speed" dimension); HY constituent
  credit breadth (blocked on constituent price feed); regional ports of C1/C3/C5 onto china/hk breadth stores.

Est. effort: W0+W1 ≈ one focused PR-pair; W2 collectors ≈ one PR each; W3 mostly registration + thin legs.

---

## 6. Adjudicated catalog — REJECT side (appended to DO_NOT_REBUILD §2 this PR)

| Candidate | Verdict | Core grounds |
|---|---|---|
| Hindenburg Omen / Titanic Syndrome as radar inputs | **REJECT-DATA + REJECT-STAT** | Need true NYSE full-universe NH/NL (not collected; panel can't reproduce); N~20–30 clusters/40y; ~40% 1y WR (≤ random); rate-shock false contexts |
| IBD distribution-day count | **REJECT-REDUNDANT** | Coincident down-day counter; `froth_fragility.py` already owns stealth-distribution physics with a forward log; OPEX volume corruption |
| McClellan oscillator thrust (+100pt swing) & MCO-oversold/MSI-washout *bounce* | **REJECT-KILLED** | SIGNAL_AUDIT `breadth-internals-thrust-confirm`: coincident-by-construction, no forward edge; fires at every bear rally; stays display in `advanced_breadth` + `fear_greed` only. (C2's rare Summation *upswing* is the adjudicated exception — different object) |
| %>50/200dma washout-extreme as a new construct | **REJECT-REDUNDANT** | Already the context gate + market_state leg; downside form IS the killed self-canceller; recovery form subsumed by C3 |
| A/D-line divergence as an *authority* leg | **REJECT (stays display)** | The identical construction measured 0.69× in 2020+ (dead); keep as the SIGNAL_AUDIT-endorsed display leg; C5 (bottoming mirror) is the only new use |
| Absolute-VIX spike-and-fade thresholds | **REJECT-STAT** | Non-stationary absolute anchors (R-SP21); <10 episodes in the >50 bucket; percentile recast collapses into existing vol legs |
| Lumber/gold (daily) | **REJECT-DATA** | FRED monthly-only; CME LBS=F thin; supply-shock contamination (2018/2021 tariffs, COVID); dominated by copper/gold |
| Dow Theory transports non-confirmation | **REJECT** | 2007 signal fired AFTER the peak; oil-confounded 20-stock index; rotation physics already covered by validated XLY/XLP + XLU legs |
| STLFSI4 | **SKIP** | Weekly + lagged; dominated by CISS/OFR for the same display job |
| Selling-climax volume detector (standalone) | **REJECT-REDUNDANT** | `dislocation.py` owns capitulation with the Fed-put veto; `conditions.py`/`regime_snap.py` cover the rest |
| Low-vol/defensive leadership as new leg | **MERGE** | Re-derivation of validated `growth_defensives`/`growth_cyc_def`; any XLU+XLP conjunction refinement rides the A6 do-no-harm harness on existing legs |
| CBOE dispersion (IC−RC) | **DEFER** | Coincident per its own lit; leading content lives in the COR level (R2); RC needs deep constituent history we lack |

**Scope clarifications (what does NOT bind here):** the `esx_washout_x_turn` kill and the `esx_div_fire`
standalone-divergence anti-validation are **per-stock entry-stack constructs** — they do not bar market-level
thrust/divergence chips (different object, different ruler). The election-cycle kill bars standalone use only
(the modulator stands). `bottom_sensors` display-only ruling and the S-TOP_RISK de-escalation gate (RO-3,
~2026-10-15) are honored: nothing here consumes options tissue or adds ranked-output consumers.

---

## 7. Rulings issued (RRX)

- **RRX-R1** — Panel-not-NYSE universe law + PIT membership + mature-window gates bind every A/D-family build (§2).
- **RRX-R2** — The rebound-capture ruler (§3) is the ONLY ruler for recovery confirmers; grading vs drawdown-onset
  or ungated long-side returns is wrong-ruler.
- **RRX-R3** — Count-thrust family ships as ONE confluence chip; per-author legs forbidden (double-counting).
- **RRX-R4** — Coincident-by-construction bars *risk-rising* internals legs; it does not bar *recovery confirmers*,
  whose job is confirmation. The MCO-bounce family stays killed regardless.
- **RRX-R5** — One canonical %>Nd washout→thrust lookback; no near-identical %>Nd families.
- **RRX-R6** — NL-retest and A/D-retest divergences consolidate into one chip (two facets).
- **RRX-R7** — Recovery chips never enter `_LEG_CALIB`, never move state/gross/banner; promotion beyond display
  requires the rebound ruler + a fresh operator-ratified ruling. C7 (credit rollover) is first in line.
- **RRX-R8** — Composite stress indices are display-only forever-until-ruled: publication-lag-honored, equity-vol
  circularity noted, never fused into scoring.
- **RRX-R9** — R2/R3 gauntlet attempts must be Lane-(ii) machine-registered with pre-committed gates and
  come-back dates; a null lands them at Tier-B confluence, printed, not hidden.
- **RRX-R10** — Kill rows in §6 are construction-specific per house law; revival needs new evidence + explicit ruling.

## 8. Clocks

- **2026-08-15** — W0/W1 live check: chips accruing in the recovery forward log? (If W0 unbuilt, nothing else matters.)
- **2026-10-15** — R2 (^COR) gauntlet come-back after collector accrues + historical pull validated; W2 volume-aggregate row count check.
- **2027-01-15** — first rebound-ruler read on C3/C4/C6/C7 (the ~2+/yr chips); ZBT-class chips will still be n≈0–1 — expected, printed.

## 9. Key sources (beyond in-repo docs cited inline)

Desmond, P. — "Identifying Bear Market Bottoms and New Bull Markets" (2002 Dow Award; 90% up/down days).
Deemer, W. — Breakaway Momentum (breakawaymomentum.com). Zweig, M. — *Winning on Wall Street* (ZBT, 9:1 days).
Quantifiable Edges — FTD success-rate studies. SentimenTrader — Summation low→high swing study. options.cafe /
CBOE — VIX3M backwardation episode stats. Pollet & Wilson (2010); Park (Fed) — implied correlation and returns.
Kritzman & Li (2010) — turbulence; Kritzman et al. (2011) — absorption ratio. CXO Advisory — RSP/SPY predictive
nulls. McClellan Financial — ratio-adjusted RANA conventions. Gayed & Bilello (2015) — lumber/gold (rejected).
