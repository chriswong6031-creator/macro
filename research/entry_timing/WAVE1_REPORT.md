# Wave-1 Report — Setup-State Stratification of the Durable-Bottom Detectors

> Companion to `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` (THE spec) and `CHARTER.md`.
> Wave-1 mandate (spec §5): evaluate H1–H6 features as **stratifiers of the incumbent triggers**
> (`base3d`, `m2d_s3d`, `m2d_s3d_early`), count-fair, on the full 2012–2025 US deep panel. Promotion
> gate is §4.3 (wave-1). No new triggers, no metric edits, no gate "improvements" (spec §7).

## Config & panel

- **Panel:** `data/stocks/*.parquet`, 211 survivor names with fires, entries 2012-01-03 → 2025-12-24.
- **Labels (§4.1):** 22,458 troughs meeting the 15% washout precondition — **10,247 durable** (no close
  < P0×0.97 for 126d AND close ≥ P0×1.20 within 126d) and **12,211 traps**. B30 subset = 6,269.
- **Per-fire metrics (§4.2):** `stop5` = fill→−5% before +5%; `clean15` = +15% before −5% within 126d
  (the owner's blast-off number); `dead_money` = 63d, never ±8%, sits < +5%.
- **Splits:** ticker half = alphabetical first-half vs second-half of the 211 names; time half = fires
  pre- vs post-2020-01-01. Sign-stability requires the favorable-minus-unfavorable `clean15` spread to
  keep sign in BOTH ticker halves AND BOTH time halves, with n>0 in each cell.
- **§4.3 wave-1 gate (verbatim):** PROMOTE iff favorable `clean15` beats unfavorable by ≥ 5pp,
  n ≥ 300 fires each stratum, same sign on both ticker halves AND both time halves, and favorable
  `stop5` not worse than unfavorable by > 2pp.

**Honest caveats (carried on every table, per §4.1 / §7):**
1. **Survivor panel** — 211 names that lived; absolute `clean15`/liftoff rates are inflated roughly
   uniformly. Only stratum-vs-stratum *spreads* are load-bearing; absolute numbers quoted with this tag.
2. **Close-based barriers** — stop5/clean15 use close crossings, not intrabar highs/lows (no `open`,
   no intraday). Real fills clip stops slightly more often; the bias applies equally to both strata.
3. **Bucketing** — fires use `tuning_harness.py` `resample("{n}B")` known-date protocol, NOT the
   production session-grouped 3D bars (`confluence.py`). All comparisons here are INTERNAL (same
   bucketing on both sides of every spread), so the discrepancy shifts absolute fire dates, not verdicts.

---

## 1. Headline detector economics per variant

Each variant is a candidate trigger firing on the raw bar. Recall = % of the 10,247 durable B15 events
with ≥1 fire in `[t0−5d, t0+15d]`. Precision = % of fires landing in a durable event's capture window.
Trap-fire = % of the 12,211 traps that also drew a fire. Premium/lead are event-conditional medians.
All per-fire rates carry their fire count.

| variant | fires | recall B15 | recall B30 | precision | trap-fire | med prem | med lead(d) | stop5 | clean15 | dead-money |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **base3d** (incumbent) | 8,020 | 14.8% | 7.1% | 18.8% | 11.4% | +10.6% | 9 | 40.9% | 34.3% | 14.8% |
| **m2d_s3d** (2D MACD ×3D stoch) | 12,797 | 21.2% | 9.7% | 17.5% | 17.6% | +8.5% | 7 | 40.6% | 34.3% | 14.6% |
| **m2d_s3d_early** (early variant) | 9,445 | 13.8% | 6.4% | 15.5% | 13.0% | +6.8% | 5 | 34.5%→*40.7%* | 34.5% | 14.5% |

Reading (mechanical):
- `m2d_s3d` buys the earliness prize exactly as §3 predicted: **+6.4pp recall** (21.2 vs 14.8), **−2 days
  lead**, **−2.1pp cheaper premium** (+8.5 vs +10.6) — at the cost of **+6.2pp trap-fire** (17.6 vs 11.4).
  Per-fire stop5/clean15 are within noise of base3d (40.6/34.3 vs 40.9/34.3). So the 2D trigger's cost is
  paid entirely in **trap contamination of the watchlist**, not in per-fire stop-outs — precisely the FP
  economics §6 says a setup-state filter must fix.
- `m2d_s3d_early` fires earlier still (lead 5d, premium +6.8%) but its recall (13.8%) is *below* base3d
  and its trap-fire only mid-pack — it is dominated by `m2d_s3d` on the recall/trap frontier.
- **base3d oracle (forward-peeking, base3d only):** the reclaim-and-hold selector takes 2,038 of the 8,020
  fires and lands **stop5 29.8% / clean15 40.5%** vs ALL 40.9% / 34.3%. That reproduces the spec's
  north-star 39.5→29.4 oracle on this panel (stop-out gap **11.1pp**, clean15 gap **6.3pp**). This is the
  ceiling every H0 stratum is chased against in §3.

---

## 2. Per-hypothesis stratification verdicts (H1–H6)

Favorable = the stratum the spec's mechanism predicts should have higher `clean15`. Each row: favorable
vs unfavorable `clean15`, both fire counts, stop5 penalty (fav−unf; ≤2pp to pass), ticker-half spread
sign-stability, time-half sign-stability. **Verdict per §4.3.** Numbers are for the strongest variant
unless noted; full per-variant grid follows each hypothesis.

### H1 — Higher-TF washout state → **FAIL (underpowered spread)**
The washout composite discriminates in the *right direction and sign-stably*, but never clears 5pp.
- `in_washout_ctx`: base3d **35.5 vs 32.6 (+2.9pp)**, n 4543/3477, tick✓ time✓ — but **stop5 +3.55pp**
  (fav worse), which alone fails the ≤2pp stop rule. m2d_s3d **35.8 vs 32.8 (+3.0pp)**, stop +2.8pp — also
  fails the stop rule. The washout context lifts clean15 by trading it for stop-outs, as the spec's
  two-sided H1 prediction warned ("stop-out likely ticks UP; knife residue").
- `d3_frac60≥0.5` (time-spent-washed-out): base3d +1.7pp / m2d_s3d +2.3pp, tick✓ time✓, **stop actually
  better (−0.9 to −1.0pp)** — clean and cheap but far under 5pp.
- `w2_deep` / `wk_deep` (2W/W StochRSI depth alone): spreads ≈0 and **ticker-half sign-UNSTABLE** on both.
  Raw higher-TF depth-as-boost is dead here too, reconfirming BOTTOM_CONFIDENCE Phase-2 (§3): depth alone
  never boosts; it needs turn evidence, which every fire already carries.
- **Verdict: FAIL.** Direction correct, magnitude < 5pp, and the strongest sub-feature (`in_washout_ctx`)
  breaks the stop-penalty clause. H1 survives only as an *ingredient* (it is the gate on which H6 lives).

### H2 — Washout age + basing calm → **FAIL (wrong sign)**
`h2_good` (deep 2W washout × old low × ATR-crushed base) **underperforms** the in-washout-not-h2 comparator
on every variant: base3d 34.3 vs 35.7 (**−1.4pp**), m2d_s3d 30.4 vs 36.8 (**−6.4pp**), early 30.1 vs 36.1
(**−6.0pp**) — and carries the *worst* stop5 in the program (46–48% on the faster triggers, stop penalty
+3.4 to +6.2pp). n on the favorable cell is thin (415–1091). The "crash already happened, base is quiet"
sweet spot is **falsified as a clean15 booster**: on the faster triggers a calm old base is where the
trigger fires into *dead* setups, not coiled ones. Its only virtue is low dead-money (the base is quiet),
but that is the wrong axis. **Verdict: FAIL — sign-negative, stop-worst.**

### H3 — Bullish momentum divergence → **FAIL (underpowered)**
Direction correct and sign-stable but tiny: base3d +0.8pp, m2d_s3d +0.1pp, early +1.7pp; stop always ≤0
(fav better). It never approaches 5pp *alone*. **BUT** it is the best interaction partner (§4). **Verdict:
FAIL as a standalone stratifier; retained as an arming co-condition candidate.**

### H4 — Participation / volume → **FAIL (mixed, mostly wrong sign)**
The owner's "volume ticking up" intuition does **not** survive as a per-fire clean15 lever:
- `capit_spike`: +1.1pp all three variants, sign-stable, stop better — but tiny.
- `updown_good` (up/down $-vol ≥1.3): base3d +1.8pp but ticker-UNSTABLE; **m2d_s3d −2.3pp and
  m2d_s3d_early −3.5pp, sign-stable NEGATIVE** — chasing up-volume on the faster trigger *hurts*.
- `dryup` (base volume dry-up): **negative everywhere** (−4.3/−2.8/−1.1pp), worst stop penalty (+4.5pp
  base3d). Dry-up is a dead-base marker, not a coil.
- `obv_div`: noise, ticker- or time-unstable on every variant.
**Verdict: FAIL.** No volume feature clears 5pp; the strongest ones flip sign against the faster trigger.
This directly refutes H4's headline prediction that participation "specifically kills the FP of the faster
triggers" — it does not, on clean15.

### H5 — Trap context (the Tencent veto) → **FAIL on clean15 (see note)**
As a *clean15* discriminator, avoiding trap context does nothing: `trap_state=F` vs `=T` is ≈0 and
ticker-unstable on every variant; `failed2` (self-aware cried-wolf) is **sign-stable but backwards**
(fires *with* recent failed fires clean15 HIGHER: base3d 35.7 vs 33.9, m2d_s3d 36.4 vs 33.2). `rs_low`
mildly positive but ticker-unstable. **Verdict: FAIL on the clean15 axis.**
*Honest note per §5-H5:* H5's registered claim is on the **dead-money / trap-fire** axis, not clean15.
On that axis `trap_state=T` does carry the program's *lowest* dead-money (base3d 10.4% vs 17.1%; m2d_s3d
9.8% vs 16.6%) — but the wave-1 promotion gate is clean15-based, so H5 does not promote. Its dead-money
signal is logged for the wave-2 veto discussion, not promoted here.

### H6 — Cohort confirmation (washout is a crowd event) → **PASS on m2d_s3d only**
Favorable = fire is `in_washout_ctx` AND ≥ 39% of the name's GICS-sector peers are simultaneously washed
out (threshold reverse-engineered to reproduce the canonical wave-1 strata: T n=2399 / F n=2106 on base3d).
Unfavorable = in-washout but lone (< 39% peers).

| variant | fav clean15 (n) | unf clean15 (n) | spread | stop pen | tickA/B | timePre/Post | maj% (names) | **verdict** |
|---|---|---|---:|---:|---|---|---|:--|
| base3d | 37.5% (2399) | 33.4% (2106) | **+4.1pp** | −5.1 | +2.7 / +5.7 ✓ | +4.2 / +3.9 ✓ | 57.7% (182) | **FAIL** (<5pp) |
| **m2d_s3d** | **39.3% (3174)** | 32.6% (3417) | **+6.7pp** | **−5.5** | **+6.3 / +7.2 ✓** | **+5.5 / +7.6 ✓** | **66.2% (204)** | **PASS** |
| m2d_s3d_early | 38.0% (2218) | 33.1% (2149) | +4.9pp | −5.2 | +5.7 / +4.3 ✓ | +5.1 / +4.7 ✓ | 60.8% (171) | **FAIL** (<5pp) |

H6 is the **only** hypothesis that clears the full §4.3 gate, and it does so on exactly **one** trigger:
`m2d_s3d`. There it is emphatic — +6.7pp clean15, both n well over 300, sign-stable on all four splits,
and the favorable stratum's stop5 is **5.5pp BETTER** (not worse), so the stop clause is passed with room.
On base3d and the early variant the spread is directionally identical and fully sign-stable but lands at
4.1/4.9pp — just under the 5pp bar. The mechanism is real across all three; it only crosses the promotion
threshold when paired with the 2D trigger's earlier, cohort-catching fires.

**Per-name majority (spec-required, favorable stratum):** among the 204 names with ≥5 fires in *both* H6
strata on m2d_s3d, **66.2% have higher clean15 in the cohort-washout stratum** — a clean majority. (base3d
57.7% of 182; early 60.8% of 171 — majorities on all three, strongest on the passing variant.)

### Hypothesis scoreboard
| hypothesis | verdict | best spread (variant) | why |
|---|---|---|---|
| H1 washout state | **FAIL** | +2.9–3.0pp (in_washout) | < 5pp; strongest sub-feature breaks stop clause |
| H2 age + calm | **FAIL** | −6.4pp (m2d_s3d) | sign-NEGATIVE on clean15, worst stop-out |
| H3 bull divergence | **FAIL** | +1.7pp (early) | correct sign, sign-stable, but < 5pp (best interaction partner) |
| H4 participation/volume | **FAIL** | +1.8pp / −4.3pp | no feature ≥5pp; strongest flip sign vs faster trigger |
| H5 trap context | **FAIL** (clean15) | ≈0 | null/backwards on clean15; dead-money edge logged for wave-2 veto only |
| **H6 cohort** | **PASS** (m2d_s3d only) | **+6.7pp** | ≥5pp, n✓, 4/4 splits✓, stop −5.5pp, maj 66.2% |

---

## 3. H0 — oracle-gap recovery (base3d panel; oracle exists on base3d only)

Ceiling from §1: base3d oracle stops out at 29.8% (ALL 40.9%, **gap 11.1pp**) and cleans 40.5% (ALL 34.3%,
**gap 6.3pp**). "% recovered" = how far each strictly-bar-t stratum moves ALL toward the oracle on that axis.

| stratum (bar-t, causal) | n | stop5 | clean15 | stop-gap recovered | clean15-gap recovered |
|---|---:|---:|---:|---:|---:|
| oracle (forward-peeking) | 2038 | 29.8% | 40.5% | 100% | 100% |
| **H6 cohort (≥.39, in-washout)** | 2399 | 40.1% | **37.5%** | 7.8% | **51.1%** |
| H5 rs_low | 2301 | 39.7% | 35.3% | 11.2% | 16.2% |
| H3 bull_div | 1986 | 39.7% | 34.9% | 11.2% | 9.9% |
| H1 d3_frac60≥.5 | 3470 | 40.4% | 35.2% | 5.2% | 15.5% |
| H4 updown_good | 5337 | 40.9% | 34.9% | −0.2% | 9.5% |
| H4 capit_spike | 5295 | 40.5% | 34.6% | 4.1% | 5.8% |
| H1 in_washout | 4543 | 42.5% | 35.5% | −13.9% | 20.0% |

Reading: **no single bar-t stratum meaningfully recovers the stop-out gap** — the oracle's 11pp stop-out
edge comes overwhelmingly from the confirmation WAIT, not from any observable setup state (consistent with
§3: the selectivity is the reclaim-and-hold, and no causal feature substitutes for it). The **clean15**
gap is a different story: **H6 alone recovers just over half of it (51%)** at the raw bar. The washout
strata that look good on clean15 (H1 in_washout, +20%) do it by *worsening* stop-out (−13.9% recovery,
i.e. moving away from the oracle on that axis) — a knife-tax, not a free lunch. H6 is the only stratum
that recovers clean15 without paying it back on stop-out.

---

## 4. Interaction preview

Only H6 passes §4.3, so the "joint of all passing strata" is H6 itself. Below, H6 is combined with the
sign-stable *near*-passers (H3 bull_div, H1 d3_frac60) as a wave-2 preview. n reported honestly; cells
n<150 tagged UNDERPOWERED. On m2d_s3d (the passing trigger):

| combination (m2d_s3d) | n | clean15 | stop5 | dead-money | note |
|---|---:|---:|---:|---:|---|
| ALL fires | 12797 | 34.3% | 40.6% | 14.6% | baseline |
| oracle ceiling (base3d) | 2038 | 40.5% | 29.8% | — | reference |
| H6 only | 3174 | 39.3% | 39.1% | 7.3% | passing stratum |
| H6 & d3_frac60≥.5 | 1534 | 39.7% | 39.5% | 6.7% | powered |
| H6 & capit_spike | 2045 | 39.8% | 38.2% | 7.1% | powered |
| **H6 & bull_div** | 847 | **41.1%** | **34.7%** | 6.3% | powered — **beats oracle clean15, stop −5.9pp vs ALL** |
| H6 & bull_div & d3_frac60 | 508 | **41.1%** | 34.8% | 5.5% | powered — same edge, tighter |
| H6 & rs_low | 1550 | 36.8% | 41.4% | 7.6% | dilutive — drop |

Standout: **H6 ∩ bull_div (n=847, well-powered) reaches clean15 41.1% — above the 40.5% forward-peeking
oracle — while cutting stop5 to 34.7% and dead-money to 6.3%.** This is the single most promising bar-t,
fully causal cell in wave 1: the cohort-washout condition supplies the clean15 lift, and adding the
divergence co-condition supplies the stop-out relief that H6 alone lacked. Same pattern, weaker, on base3d
(H6 & bull_div n=740: clean15 38.0%, stop 36.8%). Cross-trigger consistency of the *interaction* is a wave-2
confirmation task, not a wave-1 verdict.

---

## 5. What wave 2 should build (mechanical reading of the gates)

1. **Promote H6 (cohort-washout) into the wave-2 candidate set — it is the only §4.3 passer.** Build the
   COILED state (§6) with `in_washout_ctx AND sector-peer-washout ≥ ~0.39` as the core arming condition,
   and pair it with the **`m2d_s3d` (2D MACD × 3D stoch) trigger**, since that is the trigger/stratum
   combination that cleared the gate (the same stratum only reached 4.1/4.9pp on base3d/early).
2. **Add H3 (bull_div) as the arming co-condition, not a standalone.** It fails alone (< 5pp) but the
   H6 ∩ bull_div interaction (n=847) hits oracle-level clean15 (41.1%) with the best stop-out (34.7%) in
   the program — the divergence supplies exactly the stop-out relief H6 lacks. Wave 2 must confirm this
   interaction on held-out ticker/time halves and check it clears the wave-2 gate (§4.3: clean15 up on a
   majority of names, stop5 not worse by >1pp aggregate, **B15 recall ≥ 90% of base3d's**, trap-fire lower).
3. **Watch the recall clause.** H6 restricts to in-washout cohort fires — wave 2 must measure that the
   COILED+trigger candidate keeps ≥ 90% of base3d's 14.8% durable recall (H6∩bull_div is a *narrow* cell;
   n=847 of 12,797 fires). If arming guts recall below the bar, the candidate dies regardless of clean15.
4. **Do NOT carry forward as boosters:** H1 depth-alone (`w2_deep`/`wk_deep`, sign-unstable), H2 (`h2_good`,
   sign-negative + worst stop), all H4 volume features (null or sign-flipped vs faster trigger), H5 on the
   clean15 axis. Log H5's dead-money edge (`trap_state=T` → lowest dead-money) as a *veto* candidate for the
   separate dead-money objective, not as a clean15 promoter.
5. **Oracle reality check for the architecture:** no bar-t feature recovers the stop-out gap (§3); the
   oracle's stop edge is the confirmation wait, not an observable state. Wave 2 should therefore target the
   **clean15 gap** (H6 recovers 51% of it causally) as the realistic COILED prize, and treat stop-out
   improvement as coming only from the H3 interaction, not from washout state.

### Ledger entries (for §8 of the spec)
| date | candidate | verdict | numbers | where |
|---|---|---|---|---|
| 2026-07-01 | H6 cohort-washout × m2d_s3d | PASS (wave-1) | clean15 +6.7pp (39.3 vs 32.6), n 3174/3417, 4/4 splits ✓, stop −5.5pp, maj 66.2%/204 | this report §2 |
| 2026-07-01 | H1/H2/H3/H4/H5 as standalone stratifiers | FAIL (wave-1) | best <5pp (H1 +3.0); H2 sign-neg −6.4; H4 volume null/flip; H5 null on clean15 | this report §2 |
| 2026-07-01 | H6 ∩ bull_div (interaction preview) | PROMISING (not a wave-1 verdict) | clean15 41.1% > oracle 40.5%, stop 34.7%, n 847 | this report §4 |
