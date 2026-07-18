# Rotation Events v2 — Universe/Family Extension Pre-Registration (FROZEN 2026-07-18)

**Program:** Rotation Events v2 (research/ROTATION_EVENTS_V2_MASTERPLAN_BY_FABLE.md, 2026-07-18).
**Parent:** Rotation Command (research/ROTATION_COMMAND_MASTERPLAN_BY_FABLE.md, 2026-07-11).
**Status:** PRE-REGISTERED — committed BEFORE any expanded-universe forward returns are
computed or looked at. The expanded-universe event census (which pairs fired, when) may be
inspected after this doc is merged; the forward-return columns may not, and the evaluation
script computes them only after this doc is merged.

**Registry hash:** 72597efb2400236b7790e6859cde6d70e4b8d89d

This pre-registration covers the new event families (B: into_strength, C: cross_handoff,
D: correlation_regime_break, E: event_faltering, F: single_sided_velocity) and the
expanded pair universe (7 cross-sector pairs, 3 contagion pairs, 1 complex) registered in
`config/rotation_universe.json`. It does NOT cover the v1 intra-sector handoff family —
that family's pre-registration and results are recorded in
`research/ROTATION_COMMAND_S1_S2_PREREG.md` (S1/S2 ACCRUE at n=13<20 as of 2026-07-17).

**This prereg RESETS the promotion clock for each new family.** n starts at 0 for every
new event kind. No historical hit-rate may be examined before the floor is reached. The
S1/S2 verdict of ACCRUE applies to the v1 universe only; the expanded universe begins
accrual from the date this doc is merged.

**Authority (frozen):** display/context tier only. `may_rank:false, may_gate:false,
may_size:false, may_escalate:false`. Nothing in this document promotes any family to
authority. Promotion requires reaching floor n≥20 per family and passing the frozen
verdict bars (§5) in a separate adjudication.

---

## 1. Universe under test

**Registry:** `config/rotation_universe.json`, version 2.0, region "us", registered 2026-07-18.
Registry SHA1 filled at integration: 72597efb2400236b7790e6859cde6d70e4b8d89d.

**Series (12 total):**

| Key | Kind | Ticker/Basket | Label EN | Sector |
|-----|------|---------------|----------|--------|
| xlk | etf | XLK | Technology | xlk |
| xlv | etf | XLV | Health Care | xlv |
| xlf | etf | XLF | Financials | xlf |
| xlp | etf | XLP | Consumer Staples | xlp |
| xlu | etf | XLU | Utilities | xlu |
| xlc | etf | XLC | Communication Services | xlc |
| xle | etf | XLE | Energy | xle |
| smh | etf | SMH | Semiconductors | xlk |
| igv | etf | IGV | Software | xlk |
| mag7_basket | basket_composite | mag7 | Mag-7 basket | xlk |
| ai_semis_basket | basket_composite | ai_semiconductors | AI semiconductors | xlk |
| big_pharma_basket | basket_composite | big_pharma | Big pharma | xlv |

Series resolution: `etf` kind loads from `data/yahoo/*.parquet` via
`basket_index._load_member_ohlcv`; `basket_composite` kind loads via
`sector_legs._basket_close(basket, membership)` using equal-weight `consolidated_candle`
with `pit=False`. The ticker `MAGS` is hard-rejected at the resolver — the mag7 leg is the
EW basket composite. Series with fewer than MIN_BARS=300 bars are dropped with a disclosed
coverage warning and do not accrue to the graded census.

**Cross-sector pairs (7):**

| ID | Donor | Receiver | Tier |
|----|-------|----------|------|
| xlk->xlv | xlk | xlv | primary |
| smh->xlv | smh | xlv | primary |
| mag7_basket->xlv | mag7_basket | xlv | primary |
| xlk->xlp | xlk | xlp | secondary |
| xlk->xlu | xlk | xlu | secondary |
| smh->xlf | smh | xlf | secondary |
| xlk->xlf | xlk | xlf | secondary |

**Contagion pairs (3):**

| ID | A | B | Complex |
|----|---|---|---------|
| smh~mag7_basket | smh | mag7_basket | xlk_complex |
| smh~igv | smh | igv | xlk_complex |
| xlk~smh | xlk | smh | xlk_complex |

**Complex (1):** `xlk_complex` — members: xlk, smh, igv, mag7_basket, ai_semis_basket;
attribution probes: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA.

**Benchmark:** SPY (ETF).

**Velocity series (10):** xlk, xlv, xlf, xlp, xlu, xlc, xle, smh, igv, mag7_basket.

---

## 2. Families under study

Each family accrues independently to its own floor n≥20 before any verdict is possible.
Families are NOT pooled for verdict purposes.

### Family B — into_strength

**Signal (frozen):** donor SPY-relative 20d return (`rs20`) ≤ −0.03 AND donor at
40-session low ×1.01 tolerance (`contagion_bleed` state, SPY-relative criterion is FINDING
8 fix from final_spec.md) AND receiver rs20 ≥ +0.05 (`rel_lead`) AND receiver off-40d-low
≥ 0.08 (`into_off_low_min`) AND receiver/donor ratio 20d change ≥ 0.05 OR ratio at 20d
high AND receiver sector breadth (pct_above_50) ≥ 0.65 and rising over 5 sessions AND
breadth_recv > breadth_donor. 2-session hysteresis (`confirm_days=2`).

**Graded outcome:** receiver minus donor forward excess return at 5d, 10d, 21d from T+1
close. Secondary: receiver vs SPY fwd excess.

**Horizons:** 5d, 10d, 21d.

**Null hypothesis:** mean/median receiver−donor fwd excess ≤ 0 (no edge over holding the
donor instead of the receiver).

**Survivorship disclosure:** basket members are hindsight-curated; mag7 basket membership
as of 2026 — approximation for pre-2023 episodes. All statistics reported on two eras:
modern (started ≥ 2023-05-01) and reconstructed (prior, labeled "membership as of 2026 —
approximation"). No claim is made that pre-2023 events were detectable point-in-time as
named cohorts.

### Family C — cross_handoff

**Signal (frozen):** donor `blowoff_crash` fires (reuses `engine/rotation_events.blowoff_crash`
byte-identical) AND receiver `turn_up` fires (reuses `engine/rotation_events.turn_up`
byte-identical) AND `pair_confirm` fires — operating over the registered cross-sector pairs
(not the intra-sector pair loop). All three conditions required.

**Graded outcome:** receiver forward return vs SPY at 5d, 10d, 21d from T+1. Excess over
receiver's own sector ETF at 10d and 21d (secondary).

**Horizons:** 5d, 10d, 21d.

**Null hypothesis:** receiver fwd excess vs SPY ≤ 0.

**Note:** this family had not yet fired on 07-17 tape (blowoff_crash does not fire for XLK
or SMH on 07-17 — FINDING 1, final_spec.md). Accrual begins from first live instances.

### Family D — correlation_regime_break

**Signal (frozen):** raw 10d rolling correlation between pair A and B ≥ 0.45 AND 7-session
rise in raw corr ≥ 0.25 AND 7-session rise in SPY-residual correlation (beta estimated
over 80d trailing window) ≥ 0.20 AND both-fell count (10 sessions, using EW basket
composites — NEVER MAGS ETF) ≥ 3 AND prior 20-session baseline correlation ≤ 0.30 (was
diversifying). 2-session hysteresis.

**Graded outcome:** realized forward dispersion between pair A and B over 10d and 21d vs
baseline dispersion; complex drawdown continuation (does the complex continue declining
after the flag?).

**Horizons:** 10d, 21d.

**Null hypothesis:** no dispersion change vs baseline; no drawdown continuation above the
unconditional rate.

**Hard constraint (binding, not overridable by any verdict):** this family may NEVER
promote to conviction/gate/size. Dispersion-regime hard-gating requires separate operator
ratification per the kill boundary in DO_NOT_REBUILD.md and ROTATION_EVENTS_V2_MASTERPLAN_
BY_FABLE.md §2.3. The only lawful consequence of any verdict for this family is a display
chip and a prominence modulation.

### Family E — event_faltering

**Signal (frozen):** applied to active events only. Fires when the parent event reaches
`lapse_count ≥ 2` OR `neg_run ≥ 2` OR ratio neg-run ≥ 3 (`ratio_exit_run`). Produces
`health.state = "weakening"` with one-step severity demotion.

**Graded outcome:** forward decay of the parent event's receiver leg over 5d and 10d from
the faltering flag date, vs unconditional fwd returns for that leg.

**Horizons:** 5d, 10d.

**Null hypothesis:** faltering label is uninformative about the parent event's forward
receiver outcome (no excess decay vs unconditional rate).

**Note:** the census for this family is bounded above by the number of active events that
reach weakening state. Accrual may be slow if events typically close before lapse=2.

### Family F — single_sided_velocity

**Signal (frozen):** one or more `velocity_series` shows multi-timeframe RS acceleration:
`accel10 = 2*mom5 − mom10` positive AND `mtf_agree` (5d, 10d, 20d RS all same sign) AND
no confirmed pair event active for this series as a receiver. This is the earliest,
lowest-authority tier — equivalent to TAPE-ONSET.

**Graded outcome:** forward continuation of the accel sign at 5d and 10d from T+1.

**Horizons:** 5d, 10d.

**Null hypothesis:** RS acceleration sign has no forward continuation (accel is not
predictive at either horizon).

**Tier ceiling (binding, not overridable by any verdict):** single_sided_velocity is
tape-onset tier permanently. A GO verdict keeps this family at tape-onset — it cannot
escalate to `watch` or higher without a separate operator ratification. The at-rest copy
"Early sign — watch, don't chase" is permanent regardless of verdict.

---

## 3. PARAMS_V2 (frozen at adjudication 2026-07-18)

All parameter values below are disclosed in the `params` field of every emitted event.
No sweeps were run on these values; they are set from the adjudication in final_spec.md §4.
No parameter may be changed after this document is merged and before the verdict is
reached, unless the change is first logged in a pre-registered amendment committed before
any results under the amended parameters are examined (§9 amendment protocol).

```
mom_windows          : [5, 10, 20, 60]
accel_lag            : 5
into_off_low_min     : 0.08
into_rel_lead        : 0.05
into_ratio_chg_min   : 0.05
into_breadth_min     : 0.65
into_breadth_rise_len: 5
bleed_low_lookback   : 40
bleed_low_tol        : 1.01
bleed_rs20_max       : -0.03
corr_win             : 10
corr_prior_lag       : 7
corr_raw_level       : 0.45
corr_raw_rise        : 0.25
corr_resid_rise      : 0.20
corr_base_max        : 0.30
both_fell_min        : 3
both_fell_window     : 10
attribution_beta_win : 60
attribution_L        : 7
lapse_warn           : 2
neg_warn             : 2
lapse_run            : 5
ratio_exit_run       : 3
ttl_sessions         : 20
lockout_sessions     : 15
confirm_days         : 2
```

---

## 4. Pre-registered gates (applied ONLY at promotion, never at build)

1. **Floor:** n ≥ 20 matured events per family before any verdict. Below floor: ACCRUE.
   No promotion, no kill, no copy change, no escalation below floor.

2. **Reporting:** precision out-of-sample and forward excess reported with confidence
   intervals. Nulls printed, not hidden. "The word validated must not appear in any
   user-facing copy" (CLAUDE.md Epistemics / check_validated_claims.py CI guard).

3. **Flow/options/gamma exclusion:** these are RECEIPTS. Excluded from every graded signal
   definition and from every verdict computation. No positioning fusion at any verdict.

4. **Family D hard-gate exclusion:** correlation_regime_break may NEVER promote to
   conviction/gate/size regardless of verdict. Separate operator ratification required.

5. **Entry-confluence kill:** rotation event outputs may NOT feed cycle stance, ENTRY-NOW
   double gate, or any confluence term at any verdict outcome. RC-R12 is BLOCKED until
   RC-R9 S1/S2 mature (currently ACCRUE). This applies to all families.

6. **Family F tier ceiling:** single_sided_velocity is tape-onset tier permanently.

7. **MAGS ETF exclusion:** the mag7 leg must be the EW basket composite. Any episode
   computed using the MAGS ETF directly is excluded from the graded census.

8. **Coldstart exclusion:** events emitted by `coldstart_replay` to
   `data/rotation_events/coldstart_seed.jsonl` are EXCLUDED from the graded census.
   Only events appended to `events.jsonl` via the lane-gated nightly path count toward n.

9. **Multiplicity:** BH-FDR at q=0.10 across the primary hypotheses for each family
   evaluated at promotion. Descriptive outputs (era breakdowns, maxdd, per-horizon
   secondaries) are uncorrected and non-gated.

---

## 5. Verdict bars (frozen)

Applied per family at promotion review when n≥20 is reached. Below floor: ACCRUE.

**Family B (into_strength) GO** requires ALL of: n ≥ 20; median receiver−donor fwd10
excess ≥ +1.0pp; win rate (receiver beats donor) ≥ 55%; one-sided bootstrap p (10,000
resamples of episodes, percentile of 0) BH-adjusted q < 0.10; false-fire rate ≤ 25%
(receiver worse than donor by > −5pp within fwd10); modern-era subgroup (started ≥
2023-05-01) median ≥ 0 if n_modern ≥ 5 (else modern clause is ACCRUE and caps overall
verdict at ACCRUE).
**KILL** if n ≥ 20 and median receiver−donor fwd10 excess ≤ −1.0pp.
**NO-GO** if n ≥ 20 and verdict bars not met and not kill. Display stays; no relabel.
**ACCRUE** if n < 20.

**Family C (cross_handoff) GO** requires ALL of: n ≥ 20; median receiver fwd10 vs SPY ≥
+1.0pp; win rate ≥ 55%; BH-adjusted q < 0.10; false-fire ≤ 25%.
**KILL** if n ≥ 20 and median excess ≤ −1.0pp. **NO-GO / ACCRUE** otherwise.

**Family D (correlation_regime_break)** — verdict is CONFIRMED (dispersion change vs
baseline statistically present, BH-adjusted q < 0.10) or INCONCLUSIVE.
CONFIRMED: display prominence chip allowed. INCONCLUSIVE: context receipt only.
Neither outcome changes any stance or gate (hard-gate exclusion, §4 item 4).

**Family E (event_faltering) GO** requires ALL of: n ≥ 20; median fwd10 receiver decay
in weakening events negative and below unconditional fwd10; BH-adjusted q < 0.10.
**KILL** if n ≥ 20 and faltering is uninformative about forward outcome — the countdown
indicator is removed from display; parent health fields (lapse_count, sessions_since_confirm)
remain. **NO-GO / ACCRUE** otherwise.

**Family F (single_sided_velocity)** — verdict is INFORMATIVE (accel sign has forward
continuation, q < 0.10 one-sided) or UNINFORMATIVE. INFORMATIVE: tape-onset display
retained, no tier escalation. UNINFORMATIVE: editorial copy "watch for continuation"
removed; readings displayed as factual state only. No outcome escalates the tier.

---

## 6. Accrual mechanics

**Ledger:** `data/rotation_events/events.jsonl` — append-only, lane-gated nightly.
The SOLE advancer is the nightly build job (`COLLECT_LANE=nightly brun build_rotation_events`).
Off-lane calls render the payload and state snapshot but do NOT advance the ledger.
This implements the pattern from ignition-ledger-lane-gate (#2693) and
us-audit-ledger-lane-gates (#2712).

**Coldstart seed:** events emitted by the coldstart replay path go to
`data/rotation_events/coldstart_seed.jsonl` (separate file, never mixed into events.jsonl).
Running cold twice produces identical line counts in both files (idempotency requirement).
These rows are EXCLUDED from the graded census.

**Forward return computation:** the RC-R9 grader (or its successor) computes forward
returns AFTER n≥20 per family and AFTER this document is merged and the integration SHA1
is filled. The grader is run only by the adjudication reviewer on demand; it is NOT run
automatically during nightly builds.

**Episode clustering:** multiple pairs firing on one market handoff constitute ONE episode.
Episode = union of events whose [started, closed] session-intervals overlap (transitively).
Representative pair: highest severity, tie → earliest `started`, tie → lexicographically
first pair_id. Statistics run on episodes; per-event rows are descriptive only.

**Survivorship watermark:** basket membership is hindsight-curated (as of 2026). All
statistics reported on two eras: modern (started ≥ 2023-05-01) and reconstructed
(2015-01 to 2023-04, labeled "membership as of 2026 — approximation").

---

## 7. Falsification pre-commitments

The following outcomes falsify each family's promotion claim. A construction-scoped kill
does NOT close the display-context use; it closes only the specific forward-return claim.

**Family B (into_strength):** if at n≥20 the median receiver−donor fwd10 excess CI lower
bound ≤ −1.0pp → KILL. The observation that a receiver is leading while a donor bleeds
remains a factual display; only the forward-return edge claim is falsified.

**Family C (cross_handoff):** same bars. A kill here closes the cross-sector handoff
construction for the forward-return claim; display and receipt chips remain.

**Family D (correlation_regime_break):** INCONCLUSIVE verdict (no dispersion change vs
baseline at n≥20, q ≥ 0.10) → retain as context receipt only, never promote. The
factual observation (two legs coupling) is not falsified. Only the predictive-of-dispersion
claim is falsified.

**Family E (event_faltering):** KILL → countdown indicator removed. Parent health fields
(lapse_count, sessions_since_confirm, sessions_to_close) remain as factual state. Only
the forward-decay-predictiveness claim is falsified.

**Family F (single_sided_velocity):** UNINFORMATIVE (q ≥ 0.10) → accrual stops for the
editorial forward-looking copy; readings displayed as factual state. Tier permanently
tape-onset. The velocity board continues operating.

---

## 8. What this prereg does NOT cover

- The v1 intra-sector handoff family (S1/S2 ACCRUE, covered by
  `research/ROTATION_COMMAND_S1_S2_PREREG.md`).
- China or HK ports of the expanded universe (future waves, each requiring their own
  prereg before any cross-sector forward returns for those regions are computed).
- The Turn Desk Family-D column integration (sequenced after this build stabilizes).
- The RC-R12 flag-gated stance experiment (requires S1 GO from the original S1/S2 prereg,
  currently ACCRUE; gate is CLOSED).
- Any intraday cadence (XSR-W6; the lane-gate blocks ledger advance off nightly regardless).

---

## 9. Amendment protocol

Any change to the frozen PARAMS_V2 values, signal definitions, pair registry, or verdict
bars in this document requires a new commit amending this document BEFORE any results are
examined under the amended parameters. The amendment commit is part of the pre-registered
record. Retroactive parameter changes that look at results first are treated as a peeking
violation and poison the promotion gate for the affected family.
