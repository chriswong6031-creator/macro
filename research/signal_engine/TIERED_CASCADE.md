# Tiered Confluence Cascade — Assessment

**Scope.** This judges the owner's four-tier confluence cascade (T1 master → T4 earliest) as
**one door** in a multi-door funnel — the sector-cycle/rotation engine and the owner's own
sector-leadership / risk-on-off read are the other doors, and the owner's eyeball + a hard
≤ −5% stop are the final filter. It is **not** an autonomous algo and is **not** judged on
return or buy-and-hold (per `CHARTER.md` §2–§3). Each tier is scored on the only balance that
matters here: **EARLINESS** (trading days it leads the validated master confirmation) vs
**GARBAGE-RATE** (stop-out frequency under a −5% hard stop — the picks that get faked out and
become unbuyable). Source: full-panel run of `tuning_tiers.py --stop 0.05` on 110 held-out US
names; numbers cross-checked by four adversarial angles (subpanel split-half, −3% stop,
leak audit, above-200 tail-check).

The tiers, strongest/most-confirmed → earliest/least-confirmed:

| Tier | Definition | n | stop% | clean% | MFE% | %lead master | mean lead (d) |
|------|------------|---|-------|--------|------|--------------|---------------|
| **T1 master** | 3D MACD-RSI cross **&** 3D StochRSI crossed | 919 | **38.3** | 43.5 | 6.64 | 8.8 | 10.0 |
| **T2 early** | 2D MACD-RSI cross **&** 3D StochRSI crossed (= `m2d_s3d`) | 1499 | 40.6 | 41.0 | 6.34 | 51.0 | 5.7 |
| **T3 earlier** | 2D MACD-RSI **projected ≤1-2d** **&** 3D StochRSI **already crossed** (= `early_now`) | 1616 | 42.3 | 38.2 | 6.16 | 42.0 | 7.9 |
| **T4 earliest** | 2D MACD-RSI projected **&** 2D StochRSI crossed **&** above-200MA | 1142 | 43.1 | 37.4 | 5.97 | 32.0 | 7.8 |

> **2026-07-01 re-grade (W1c, audit #15).** Re-ran `tuning_stops.py --stop 0.05` on the current
> (219-name) panel. The held-out stop-out rates reproduce and the monotone gradient holds:
> **base3d 39.5% · m2d_s3d 42.5% · m2d_s3d_early 41.8%** (vs the documented T1 38.3 / T2 40.6 /
> T3 42.3 — within ~1-2pp on the larger panel). The cascade harness already fills **next-bar**
> (`f = i + 1` in `tuning_harness.py`), so these numbers were never contaminated by the same-bar
> bias the audit flagged; W1c aligned the *live* graders (`track_record`, `sector_signals`,
> `meta_label`, `name_score_grader`, `sector_central_grader`) to this same convention via
> `engine/grading.py`, so the live surface can no longer disagree with the validated claim.

---

## 1. Verdict — the cascade is SOUND

**Yes. It buys earlier without a garbage-rate explosion.** The defining property is a
**monotonic, GENTLE stop-out gradient**: as you step from the fully-confirmed master to the
earliest projected tier, the stop-out rate climbs

> **38.3 → 40.6 → 42.3 → 43.1** (T1 → T2 → T3 → T4)

— strictly increasing, but the **total cost of earliness is only ~4.8pp** of stop-out across
three full tiers of relaxation. That is the whole ballgame: you are paying *single-digit*
incremental garbage-rate to move the entry meaningfully forward. The leads are real and
material — **T2 leads the master on 51% of its fires (~5.7d earlier), T3 on 42% (~7.9d),
T4 on 32% (~7.8d)** — so the earlier tiers are not cosmetic; about half the time T2 is
genuinely standing where the master will only later confirm. Clean-entry rate decays in the
mirror direction (43.5 → 41.0 → 38.2 → 37.4) and MFE bleeds gently (6.64 → 5.97), exactly the
shape you want: each step trades a little hit-rate for a lot of lead time, with no cliff.

Crucially, **no tier is "garbage" in absolute terms.** Even the earliest, least-confirmed
T4 stops out 43.1% of the time — only ~5pp worse than the validated master. Under a −5% stop
that is a *survivable* false-positive rate **for a surfacing tool whose output is then filtered
by three more doors**; it would be marginal for a blind auto-buy, which is precisely why the
charter forbids treating it as one.

**Robustness (honest).** The gradient is directionally stable but not bulletproof:

- **−3% stop (holds):** the whole stop-out curve shifts up ~21pts (59.2 → 60.2 → 62.1 → 63.0)
  but stays **monotone T1→T4** — earliness still costs garbage-rate in the same order at a
  tighter stop. The ordering is not an artifact of the −5% choice.
- **Split-half (mixed):** sorting the 114 parquet files and splitting even/odd tickers, the
  gradient is **clean and strictly increasing on Half A (38.7 → 41.1 → 43.3 → 46.4)** but
  **inverts at the last step on Half B (38.0 → 40.2 → 41.2 → 40.0** — T4 dips *below* T3).
  So the T1≤T2≤T3 backbone replicates on both halves; only the **T3-vs-T4 ordering is fragile**
  (T4's 200MA gate makes it a different population, see §3). Read this as: the *master-is-safest,
  earlier-is-riskier* spine is robust; the fine ranking of the two earliest tiers is within noise.
- **Leak audit (holds):** the `imm2` 2D-cross projection is a pure forward linear extrapolation
  from bars *t* and *t−1* (`btc = −hist/slope`, fires when `0 < btc ≤ 1.5`) — no `.shift(-k)`,
  no future indexing; every TF leg maps onto its true known-date close, fills are `e+1`, the
  triple-barrier is strictly forward, weekly gate uses the prior closed week. The cascade is
  **leak-free** — the lead is a real lead, not a peek.

**Bottom line:** earliness is cheap here. The cascade achieves it, and the cost curve has no
explosion. It is sound as a graded surfacing funnel.

---

## 2. Recommended tier weights

Because the gradient is *gentle* (only ~5pp master→earliest, and the leads on the earlier tiers
are large), the earlier tiers deserve **real weight, not a token.** Down-weighting T2/T3 to near-
zero would throw away the engine's actual contribution — its job is to surface the move **before**
the master confirms, and T2 alone front-runs the master half the time. A defensible weighting that
honors the stop-out-vs-lead tradeoff:

| Tier | Weight | Justification |
|------|--------|---------------|
| **T1 master** | **1.00** | The validated keeper. Lowest stop-out (38.3), highest clean (43.5), highest MFE. Full conviction; this is the anchor the others are measured against. |
| **T2 early** | **0.80** | Costs only **+2.3pp** stop-out for a **51% lead rate / ~5.7d** head start. This is the best earliness-per-garbage trade on the board — it should be a near-peer of the master, not a footnote. |
| **T3 earlier** | **0.60** | +4.0pp stop-out vs master, but the **longest mean lead (~7.9d)** and still 42% lead-rate. Solid context weight; the projected 2D leg adds genuine forward information. |
| **T4 earliest** | **0.40** | +4.8pp stop-out, 32% lead-rate, and the only tier whose ranking is split-half-fragile. Real but lowest weight — useful as the earliest scout, explicitly the noisiest. |

These are **convergence weights for the multi-door funnel / brain leaf**, not position sizes —
sizing is the owner's discretion + stop. The shape to preserve: **monotone decreasing, but no
tier below ~0.4.** The data does not support collapsing the earlier tiers to zero; it supports
discounting them, gently, in proportion to a ~1.5pp-per-tier stop-out tax.

---

## 3. The above-200MA gate on T4 — KEEP (but understand what it actually buys)

**Keep it on the scored T4 tier — but be honest that it is a *frequency/process* control, not a
per-event quality upgrade.** The tail-check is unambiguous and slightly uncomfortable:

- The gate removes **527 below-200 events** (1669 → 1142, −31.6%).
- Implied stop-out of the *removed* below-200 subset ≈ **42.1%** — essentially identical to, and
  in fact **~1pp LOWER** than, the above-200 events it keeps (43.1%).
- Implied clean-rate of the removed subset ≈ **40.3% vs 37.4%** kept — i.e. the dropped bucket is
  *marginally cleaner.*

So on a **per-event** basis the gate buys **zero** stop-out improvement and even mildly inverts it
(+0.3pp stop-out on the full panel from gating). The "anti-falling-knife" framing overstates the
per-trade effect — a single below-200 oversold bounce is *not* meaningfully more likely to stop
out than an above-200 one once the −5% stop is already capping single-name tail risk.

**What the gate genuinely does** is cut the **event COUNT** by a third, and every one of those 527
removed fires sits in a confirmed downtrend (price under the 200MA). The −5% hard stop caps the
*depth* of any one name (you can't ride it to −80%) but does **not** cap the *frequency* of being
chopped — in a sustained downtrend the oscillator re-fires repeatedly and each fire is a fresh −5%
clip. The gate is **death-by-a-thousand-cuts protection**: fewer downtrend re-entries → fewer
cumulative small stop-outs → and it aligns with the owner's trend-respecting book. That is a real
benefit for a tight-stop scored leaf, so it **earns the keep on T4**.

**The honest caveat (why this is "keep," not "keep everywhere"):** the removed subset is the
*cleanest* bucket in the whole comparison and no more stop-prone — so the gate is amputating a
tranche of decent oversold-bounce entries (the expensive false-negative the §9.3 watchlist framing
warns about). **Recommendation:** keep the 200MA on the **scored** T4 tier (frequency control +
process alignment), but **do not let it gate the display-only surfacing layer** — surface the
below-200 fires as dimmed context. False positives there are cheap; the owner's eyeball + sector
door + −5% stop are exactly what's there to triage them, and those below-200 oversold bounces are
sometimes the trade.

---

## 4. The SHALLOW-vs-DEEP finding — the assumption is BACKWARDS

The confidence modifier in the code (and the charter docstring) assumes a stoch cross **from deep
oversold (<20)** is *higher* confidence and a **shallow cross (>20)** is *lower* confidence. **The
data flatly contradicts this.** Splitting T2 by stoch origin:

| T2 origin | n | stop% | clean% |
|-----------|---|-------|--------|
| deep oversold (<20) | 1189 | **41.8** | 40.4 |
| shallow cross (>20) | 310 | **36.1** | **43.5** |

The **shallow cross stops out LESS (36.1% vs 41.8%) and is CLEANER (43.5% vs 40.4%)** — and this
is one of the most robust results in the whole study: it replicates **same-sign on both split-
halves** (Half A 37.5 vs 42.0; Half B 34.9 vs 41.6) and **survives the −3% stop** (shallow 55.5
vs deep 61.4, with lower MFE too). The "shallow = lower confidence" label is **wrong** and should
not down-weight anything.

**Mechanism (why shallow is safer, not weaker).** A cross *from deep oversold* means price got
there via a **violent selloff** — the move that drove the oscillator under 20 is exactly the kind
of high-velocity decline that overshoots the −5% stop on the bounce-and-retest, so the entry gets
shaken out before it works. A **shallow cross** is a **calm pullback** that turned without a
capitulation leg — no violent down-impulse, so the entry sits closer to support and is far less
likely to be wicked through the stop. Deep-oversold trades **do** carry the higher *amplitude*
(deep buckets keep the higher MFE) and the dominant lead-the-master rate — but amplitude is not
the metric here; **stop-survival is**, and on that axis the calm cross wins.

**Recommendation:** treat shallow stoch crosses at **EQUAL weight** to deep ones — do **not**
down-weight them. If anything the data would justify a small *up-weight* for stop-survival, but
"equal" is the safe, non-overfit call (the deep bucket's higher MFE/lead earns it parity, not a
penalty). Keep the deep-vs-shallow split as a **descriptive context tag** (it tells the owner
whether the entry came out of capitulation or a quiet dip), but flip its meaning: shallow =
*calmer, stop-safer*, not *low confidence*.

---

## 5. T3 definition — confirmed

**T3 (`early_now`) is NOT a 2D-MACD solo.** It requires **both legs**: the **3D StochRSI cross has
already happened** *and* the **2D MACD-RSI is projected to cross within ~1-2 days** (`imm2`,
`btc ≤ 1.5` bars). In code (`tuning_tiers.py:96`):

```python
t3 = (B["imm2"] & B["recent3"] & confirm & rsi_ok)
```

`B["recent3"]` is the already-crossed 3D stoch (within the 8-bar confirm window); `B["imm2"]` is
the imminent 2D-MACD projection. The 3D stoch cross is the **required confirmation** — T3 never
fires on a projected 2D-MACD cross alone. This matches the owner's clarification exactly and is
what makes T3 a *confluence* tier (one confirmed leg + one projected leg), not a single-indicator
guess. Same structure holds T4, which swaps the 3D-stoch confirm for a **2D-stoch crossed +
above-200** gate — a legitimately earlier/looser leaf, correctly placed last.

---

## 6. Honest caveats

- **~40% stop-out is mechanical, not a defect.** On a panel of high-beta US names with a tight
  −5% stop and a 20-day horizon, **even the validated master stops out 38.3%** of the time — and
  the floor is the noise, not the signal. The mechanical take-every-signal rate sits near ~52% WR
  (per charter §2c); the owner's reported 80–90% WR is **discretion + selection + exits**, not the
  oscillator. **Do not "fix" the tiers until they hit 80–90% — that gap is the other doors' job.**
- **The cascade is a SURFACING / FUNNELING tool, not a buy list.** Its output is candidates ranked
  by earliness-vs-confirmation, which the **sector-cycle engine + the owner's sector-leadership /
  risk-on-off read + the −5% stop** then accept or kill. The tier weights in §2 are *inputs to that
  funnel*, never standalone triggers. The whole reason a 43% stop-out tier is acceptable is that it
  is **never the last word.**
- **T3-vs-T4 ranking is within noise** (split-half inverts at T4), and **T4's 200MA gate buys
  count-reduction, not per-event edge** (§3). Don't over-read the precise T3/T4 ordering or claim
  the gate "improves entry quality" — it controls *frequency*.
- **Detect, don't predict (still true).** The `imm2` projection is a 1-2 day linear extrapolation
  of an *already-developing* histogram — it is reading momentum that exists, not forecasting a
  catalyst. It is leak-free and contemporaneous; it does not, and must not, claim to foresee turns.

---

## 7. How this maps onto the merged `signal_gate` (take / pending / early)

The cascade **extends** the already-merged `engine/signal_quality.py` leaf, it does not replace it.
The merged engine emits two things per name: the **validated confirmed-buy quality** —
`take` / `block` / `pending` from the reclaim-and-hold buy-filter (the keeper) — and a separate
**display-only `early` / `early_now`** advance-warning flag (the 2D-MACD pre-cross). The cascade
**grades that single `early` flag into T2/T3/T4** and re-weights it: the merged `take` ≈ **T1
master** (full confirmation, weight 1.0), `pending` is the unconfirmed-latest state orthogonal to
the tiers, and the merged `early_now` is exactly **T3 (`early_now`)** — which the cascade now
formalizes alongside T2 (`m2d_s3d`) and T4, each carrying the graded weight from §2 instead of the
current flat "display-only context" treatment. **Net: same contract, finer resolution** — the
cascade turns a binary early-flag into a weighted earliness ladder, all of it still display-only /
brain-input, none of it auto-traded (charter §6–§7).


---

## 8. 2026-07-06 operator re-weight — T2 1.00 / T1 0.90

**Previous weights:** T1 1.00 · T2 0.80 · T3 0.60 · T4 0.40

**New weights:** T2 1.00 · T1 0.90 · T3 0.60 · T4 0.40

### Rationale

A 2026-07-05/06 entry-quality deep-dive (Opus red-teamed) produced three findings that collectively
justify ranking T2 above T1 for entry-quality purposes on display boards:

1. **Monotone fill-premium ladder.** Production-true dating of entry fills showed a strict
   T1 > T2 > T3 > T4 gradient in how far above the 20-day trough a confirmed entry fills:
   T1 ~10.9% median above trough vs T2 ~7.5%. T2 consistently fills closer to the structural low.

2. **Confirmed-bar, low repaint.** T2 fires on a completed 2D bar (the cross is on a closed
   candle), measured repaint rate ~9% — below the ~15% flip criterion. T1 confirmation by design
   waits for the reclaim-and-hold forward period, meaning T1 fires structurally later and
   adversely selects on price when the operator acts on the signal.

3. **Delayed-user context.** The human operator typically enters on the session after the signal
   appears. For T1 this means the entry is even more extended; T2's confirmed-bar nature makes
   it actionable at open the next session with less gap risk.

### What this is and is not

This is an **operator-ratified entry-quality ranking decision, not a gauntleted excess-return
promotion.** No tier showed robust standalone 21-day benchmark-excess returns with confidence
intervals clearly above zero — all 21d excess CIs straddle zero. The re-weight applies only to
board display ordering (the `blend_sorted` cascade and the `basket_detail` recommend sort). It
does not change:

- which tiers are BUYABLE (`BUYABLE_TIERS = ("T1", "T2", "T3")` — unchanged)
- eligibility criteria or gate semantics
- provisional flags (T3 only)
- TIER_FRAC, CN_TIER_FRAC, CN_WN_FLOOR

T1 remains the highest-precision confirmed state; the re-weight acknowledges that by the time
T1 fires, the entry window may have passed. T2 is now the board's primary “actionable now” tier.

### Files changed

- `engine/confluence_tiers.py` — WEIGHTS dict (T1 1.00→0.90, T2 0.80→1.00)
- `engine/signal_gate.py` — _CASCADE_RANK (T2=0, T1=1) + tier_rank docstring/T1-pending=2
- `templates/basket_detail.html.j2` — client-side TIER_W dict synced

---

## Amendment 2026-07-06 — T3 2-session persistence hardening (CONFLUENCE_T3_PERSIST)

**Date:** 2026-07-06  **PR:** feat/t3-persistence-hardening  **Status:** shipped

### Change

T3 now requires the `imm2` (2D MACD imminence) condition to hold for **N=2 consecutive
completed 2D-bucket evaluations** before the tier fires. N is controlled by the env var
`CONFLUENCE_T3_PERSIST` (default 2). N=1 restores the legacy single-session behavior.

The implementation checks `imm2.rolling(N).min()` at the 2D-TF level before mapping to the
daily grid — applied in both `cascade()` (stateless live path) and `tier_stream()`
(vectorized completed-bucket path). The stable legs (`recent3`, `confirm3`, `rsi_ok`) are
checked at the current daily bar only (they do not contribute to the repaint problem).

### Measured trade-off (backtest /tmp/tier_deepdive/v3/, 2026-07-06)

| Metric | T3 (N=1, legacy) | T3p (N=2, new default) |
|---|---|---|
| US repaint rate | 15.5% | 9.4% |
| CN repaint rate | 16.0% | 0.0% |
| US 21d excess mean | +0.16% | +0.41% |
| US median lead vs T1 | 11.0 sessions | 10.5 sessions |
| US event count | 3,208 | 2,041 (~36% fewer) |
| CN event count | 750 | 485 (~35% fewer) |

### What this is NOT

**De-escalation only.** T4 is untouched. The priority cascade order is unchanged (T3 still
ranks above T4). BUYABLE_TIERS unchanged. T3 still carries `provisional=True` (it remains
projection-based).

### Stale documentation (recalibration clock, separate task)

The following numbers predate this change and need re-measurement before being updated:
- `calibration/provisional_replay.json` repaint figures: 23.8% US / 15.1% CN (T3 section)
- The T3 tooltip repaint copy rendered on display boards

These are LEFT UNCHANGED here — recalibration is a separate clock.

---

## §9 — S1 HTF-sponsorship badge (2026-07-06)

**Status:** display-only, rank-neutral. S1 fires as a supplementary badge alongside the existing
T1–T4 tier display. It does NOT change tier values, WEIGHTS, `_CASCADE_RANK`, `BUYABLE_TIERS`,
board ORDER, or any existing pinned tests.

### Definition

**S1** = 2-week confluence-active **AND** 3-day confluence-active **AND** not-topped (3D basis).

Confluence-active on each timeframe = MACD-RSI (RSI-based MACD, same as production) crossed up
within **FW=2 native bars** (ratified) AND StochRSI K ≥ D (crossed up within 8 native bars and
still constructive). Not-topped veto uses the 3D basis: stoch_ob OR stoch_bear OR macd_bear on the
3D timeframe blocks the badge regardless of higher-TF state.

**Resampling:** 2W and 1W legs use completed-bucket resample (`W-FRI` / `2W-FRI` offset rules
dropping the in-progress tail bar per RUL-31 PIT gate). 3D leg uses `_tf_bars(c, 3)` — session
buckets with known-date mapping, identical to production `tier_stream()`.

**S2** = shadow field only — never displayed. S2 = 3D active AND 1W active AND 2W MACD pending
(hist < 0, slope > 0, 0 < bars-to-cross ≤ 1.0 native 2W bar) AND not-topped (3D basis). Parked
pending ≥ n=50 accruing fires; revisit ≥ 2026-10.

### Measured performance (same-ruler, HTF_SUPER_TIERS_PHASE0.md)

| Metric | S1 | T1 (master, reference) |
|--------|----|-----------------------|
| Close-only stop-out (−5%) | **27.2%** | 30.4% |
| Intraday-low stop-out (−5%) | **35.0%** | 37.5% |
| 21d excess return (vs SPY) | **+0.90%** CI [+0.16, +1.67] | — |
| Fill quality vs T1 | −0.9pp (fills slightly worse) | reference |
| n events (US, FW=2) | 427 | — |

S1 ⊂ T1-active: S1 fires predominantly during active T1 windows (overlap ~68%). Its role is
**durability and long-hold context** — confirming higher-timeframe sponsorship for names already
in a T1/T2 confirmed state. It is NOT a standalone entry signal and is NOT fed to the conviction
allocator or auto-trade logic.

### Implementation

- `engine/confluence_tiers.py`: `HTF_FW=2`, `HTF_CONF_W=8`, `HTF_BTC=1.0`, `_HTF_BLANK`,
  `_completed_resample()`, `_htf_confluence_active()`, `_htf_2w_pending()`,
  `_htf_not_topped_3d()`, `_compute_htf()` (cascade last-bar), `_compute_htf_stream()`
  (tier_stream vectorized path). `cascade()` returns `{"htf": {"s1": bool, "s2": bool}}` in the
  result dict. `tier_stream()` returns additional `s1`, `s2` boolean columns.
- `engine/signal_gate.py`: `"htf_s1"`, `"htf_s2"` added to `_VERDICT_KEYS` and propagated
  through `gate()` from the cascade `htf` dict. `buy_signal(None)` returns these as `False`.
- `templates/_sig_badge.html.j2`: S1 chip rendered BEFORE the eligible block when `sig.htf_s1`
  is true. CSS class `sig-htf-s1` (purple `#7c6ece`) added to `templates/theme.css`.
- `scripts/build_stock_library.py`: `confluence` block (htf_s1/htf_s2) and `sniper` block
  (w2_washout, w2_stoch_d, days_since_63d_low, coiled) added to the per-ticker stockdata JSON.
  `sniper.coiled` is injected in a second pass after `coiled_by` is computed cross-sectionally.
- `tests/test_htf_super_tiers.py`: 32 tests covering blank/short-history paths, truncation
  invariance, S2 pending leg, signal_gate passthrough, tier_stream columns, structural keys.

### Clocks

| Clock | Date | Action |
|-------|------|--------|
| S2 shadow revisit | ≥ 2026-10 | Check if S2 has accrued ≥ 50 fires; authorize display if n is sufficient |
| S1 recalibration | ≥ 2027-01 | Re-measure stop-out and excess-return with live accrual |

### Reference

Full adjudication and pre-registration: `research/signal_engine/HTF_SUPER_TIERS_ADJUDICATION_AND_PREREG.md`
Phase-0 study results: `research/signal_engine/HTF_SUPER_TIERS_PHASE0.md`
