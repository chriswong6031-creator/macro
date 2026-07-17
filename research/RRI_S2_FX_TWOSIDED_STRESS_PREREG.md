# RRI-S2 — Two-Sided FX Stress Leg in Risk-Off Regimes (prereg)

**Status: FROZEN ON MERGE — before any construction↔outcome relationship is computed.**
Family: `rri_2026h2` cells 5–6 (see [RRI_CRASH_ANTIFIRE_PROGRAM.md](RRI_CRASH_ANTIFIRE_PROGRAM.md)
§4). Shared rulers R-A..R-D bind verbatim. Scope: kr/jp/tw/in/au/gb/ez (the profiles carrying a
per-market `fx_pair`).

## 1 · The question, in plain English

The FX leg scores *depreciation* (one-sided): local-currency weakness = outflow pressure. That
is the validated CN-lineage mechanism in calm-to-stress transitions. But in an unfolding crash,
safe-haven flows *strengthen* KRW/JPY — on 2026-07-16 KRW had strengthened −3.47%/21d, pinning
`krw_depreciation` at the 17th percentile and dragging the KR composite to 59 while the market
stood one session from a −6% day. **When the context gate is open (the market is already in a
stress regime), is FX *dislocation* (a large move in either direction) the right risk carrier,
rather than depreciation alone?** Mechanism: violent safe-haven appreciation is itself a
deleveraging/carry-unwind symptom (JPY 2007-08, 2024-08; KRW risk episodes).

## 2 · Frozen construction

For market m with FX change series fx(t) = pair 21d %-change × `fx_risk_sign` (exactly the
existing sub-leg input, DXY-stitch included):

```
one_sided(t) = pct_rank_window(fx, 504)(t)            # the incumbent leg
two_sided(t) = pct_rank_window(|fx|, 504)(t)
leg_v2(t)    = max(one_sided(t), two_sided(t))   if gate_open(t)
             = one_sided(t)                      otherwise
```

`leg_v2` replaces the fx sub-leg percentile in the composite blend; weight (0.6) and everything
downstream unchanged. On calm days the leg VALUE is pointwise-identical to the incumbent — but
the composite's trailing 504d re-percentile window will contain gate-open days where
leg_v2 > one_sided, so calm-day composite percentiles can still shift; that blast radius is
exactly what the do-no-harm gates below are for.

Declared cells (family §4): **P1 (primary) = gate-conditional max-blend** (above);
S2b = two-sided always (`max` applied unconditionally). No other variant may be scanned.

## 3 · Primary frozen hypothesis (H1, one-sided)

Replay the full composite with leg_v2 (via `composite_series` substrate). On **gained-alert
days** — days loud-tier under v2 but not under the incumbent — pooled across the 7 markets:

> P(≥5% drawdown within h21) on gained-alert days exceeds chance at matched trigger
> structure — "chance" = the R-C permutation-null mean, the only denominator any gate uses.
> **Gate:** cluster-Wilson-LB ≥ 1.25 × the R-C null mean, AND permutation p < 0.05, AND the
> BH-FDR rank threshold (cover §4) — the stricter of the two p-rules binds.

Robustness gates (all must pass for GO): era ratio > 1.0 both eras; split-half both halves;
direction > 1.0 in ≥5 of 7 markets. (Same grammar as S1 §3.)

**Do-no-harm gates (frozen, both must pass):**
- **Lost-alert days** (loud under incumbent, not under v2 — possible because the trailing
  re-percentile of the blend can shift): lost-alert clusters' hit rate must NOT exceed
  gained-alert clusters' hit rate (v2 must not trade good alerts for bad ones), AND R-B episode
  capture under v2 ≥ incumbent's episode capture (pooled count).
- **De-escalation harm** (the recovery trap: FX also moves violently in rebounds, so a
  two-sided leg risks holding alerts through recoveries): median sessions from episode trough
  (the ≥8% episode's minimum close) to the first sub-elevated state must not increase by more
  than **5 sessions** vs the incumbent, pooled across R-B episodes.

## 4 · FP budget (frozen)

Census: two-sided-flip days (two-sided ≥85 while one-sided ≤50, gate open) run 1.6–3.6% of
last-10y days across the 7. Budget:

- Pooled added loud-tier days ≤ **4pp** of market-days (last-10y replay); no market > 6pp.
- Gained-alert clusters ≥8 pooled (N floor, else ACCRUE). Census context: the two-sided-flip
  days form 156 full-history / 62 last-10y pooled 21-gap clusters; gained-ALERT clusters are a
  subset of those, so the floor is reachable but not guaranteed — an ERA-SPARSE print here is
  a legitimate outcome, not a failure of the study.

## 5 · What would kill it (frozen)

- Gained-alert clusters' Wilson UB < null mean → safe-haven appreciation during open-gate
  regimes is *not* a drawdown carrier on these markets → **KILL** + DO_NOT_REBUILD row
  "two-sided FX dislocation leg on risk_radar_intl (construction-specific)".
- Either do-no-harm gate fails → NO-GO (the incumbent one-sided leg stands; the two-sided
  read may still ship as a Tier-2 display receipt — display ships freely).

## 6 · Lineage honesty

The one-sided depreciation construction carries the CN validation lineage (USD/CNH 1.9×);
none of that transfers to this variant — leg_v2 starts unproven and is graded only by this
prereg's gates and its own shadow log. prob_cal stays flat-at-base regardless of verdict
(2026-07-16 ruling). The 2022-class caveat on `jpy_carry` (USD/JPY weakness ≠ risk-off in a
pure Fed-hike regime) is exactly the failure mode the gate-conditioning is designed to fence:
two-sided treatment activates only inside an already-open stress gate, never in calm regimes.

## 7 · Anti-look-ahead checklist

- `two_sided` uses the same trailing 504d causal percentile machinery as every radar leg.
- Gate-conditioning uses the same-day gate value (itself causal).
- Replay recomputes the full blend + trailing composite percentile from history start — the
  variant is not spliced onto the incumbent's percentile history.
- No outcome joined before freeze (outcome-blind census only).

## 8 · What a GO does NOT show

Not a general "FX vol is risk" claim; not a change to the CN/HK/CA fx legs (out of scope); not
a probability statement (flat-at-base stands). A GO advances the variant to Stage-B shadow
accrual only; the live swap needs the operator ruling per cover §2.

## Ratification

Drafted: Fable (main loop), 2026-07-17. Pre-freeze compute: outcome-blind census only.
Operator: ☑ **RATIFIED** (in-session, 2026-07-17).
