# RRI-S3 — Drawdown-Velocity Leg (prereg)

**Status: FROZEN ON MERGE — before any construction↔outcome relationship is computed.**
Family: `rri_2026h2` cells 7–8 (see [RRI_CRASH_ANTIFIRE_PROGRAM.md](RRI_CRASH_ANTIFIRE_PROGRAM.md)
§4). Shared rulers R-A..R-D bind verbatim. Scope: kr/jp/tw/in/au/gb/ez.

## 1 · The question, in plain English

Every incumbent leg is a *pressure* meter (rates, FX, extension) — the radar has no leg that
reads the tape's own downward velocity, and the cover §1 forensics show the pressure legs
mechanically *relax* once the crash starts. The ITR W1 audit found the same hole at display
tier (F3: `drawdown_risk` is a damage meter, coincident by construction; F4: dd-velocity was
entirely absent, never built). ITR W1 shipped a velocity override in the *display* turn state
machine; the scoring-tier radar still de-escalated INTO the 07-17 crash (JP risk-off 94 →
caution 76). **Does a drawdown-velocity leg — the causal percentile of the 10-session decline —
carry residual forward-drawdown information (the fall that has started tends to extend), and
does it fix the day-one escalation latency at acceptable false-positive cost?**

## 2 · Honest framing: this is NOT a lead claim (and why the RRX kills don't pre-close it)

RRX-R4/R10 killed MCO-thrust and IBD distribution-count as US radar legs for being
"coincident-by-construction" — they were auditioned as *leading* legs against an onset-lead
ruler and failed it. This prereg does not re-run that claim. Velocity is declared **fast-
coincident**: its value proposition is (a) *continuation* — conditional residual drawdown
after a fast fall has begun — and (b) *latency* — reaching the loud tier on day 1–3 of an
episode instead of day 5+ (or never, when the pressure legs anti-fire). Both are graded by
their own frozen gates below; "leading" is never claimed, and the leg would carry the
coincident label on any Tier-2 receipt. Redundancy per the REJECT-REDUNDANT precedent is NOT
merely asserted away: although no incumbent leg is a drawdown meter, `dd_velocity` and the
extension leg read the same close series, so overlap is measured and gated — see the frozen
redundancy gate in §4 (velocity must carry lift on the extension-quiet sub-sample or it caps
at ACCRUE).

## 3 · Frozen construction

```
dd_velocity(t) = pct_rank_window( -ret10, 504 )(t)      # ret10 = close.pct_change(10)
comp_legs_v3   = incumbent legs + ("velocity", ("dd_velocity",), 0.6)
```

- New sub-leg + composite leg, weight 0.6 (the FX leg's weight — the junior-leg convention;
  not tuned, not scannable).
- The composite is re-blended and re-trailing-percentiled over full history via
  `composite_series` — replay never splices the new leg onto the incumbent percentile path.
- Scare display: joins as its own Tier-A scare ("Tape breaking — fast decline") only at
  build time IF promoted; display wording is out of scope here.
- Gate law unchanged: velocity does not open the context gate; the cap law is untouched.
  Mechanism note (not an outcome claim): after a melt-up, the parabolic memory holds the gate
  open for `_GATE_MEMORY`=60 sessions after the last ≥0.98 extension print, so the gate does
  not structurally silence this leg in the melt-down-from-melt-up class.

Declared cells (family §4): **P1 (primary) = −ret10**; S3b = −ret21. No other window, weight,
or transform may be scanned.

## 4 · Primary frozen hypothesis (H1, one-sided): residual continuation

On days with dd_velocity ≥ 0.95 AND gate open AND incumbent state below elevated (the days
this leg would actually change something), pooled across the 7 markets:

> P(a *further* ≥5% drawdown from that day's close within h21) exceeds chance at matched
> trigger structure — "chance" = the R-C permutation-null mean, the only denominator any gate
> uses. **Gate:** cluster-Wilson-LB ≥ 1.25 × the R-C null mean, AND permutation p < 0.05, AND
> the BH-FDR rank threshold (cover §4) — the stricter of the two p-rules binds.

This is the standard R-A ruler measured from the trigger close — after a fast fall, a further
−5% is not mechanical; the null machinery prices exactly that.

Robustness gates (all must pass for GO): era ratio > 1.0 both eras; split-half both halves;
direction > 1.0 in ≥5 of 7 markets.

**Redundancy gate vs the extension leg (frozen — the REJECT-REDUNDANT fence).** `dd_velocity`
and the extension leg are functions of the same close series and will co-move at a
melt-down-from-melt-up; a velocity leg that only re-states the extension leg is the killed
class. Velocity must add information where extension is quiet: H1 is re-run on the sub-sample
of trigger days with extension-leg pctile < 0.88, and must hold ratio > 1.0 AND
cluster-Wilson-LB ≥ **1.10 ×** its own R-C null mean (null re-run on the sub-sampled mask).
Sub-sample floor: ≥5 pooled clusters, else this gate prints ERA-SPARSE and the cell's best
possible verdict is ACCRUE. Spearman ρ(dd_velocity, extension pctile) is printed per market as
a receipt.

**H2 (latency, gated secondary — required for Stage-B, not for the family FDR):** on R-B
episodes pooled, median latency (onset → first loud-tier day, censored grammar) under v3
improves by ≥2 sessions vs incumbent, direction-consistent in ≥5 of 7 markets with ≥3 episodes.

## 5 · FP budget (frozen)

Census: velocity ≥95th-pctile days run 4.8–6.4% of days; the below-alert subset 4.7–6.1%.
Because the leg enters a re-percentiled blend (not a floor), added loud days will be smaller
than the trigger census; budget caps them at:

- Pooled added loud-tier days ≤ **8pp** of market-days (last-10y replay); no market > 10pp.
- Trigger clusters ≥8 pooled (N floor, else ACCRUE).
- Whipsaw receipt (printed, not gated): share of trigger clusters where the market closed
  ABOVE the trigger close at h21 — the bounce-bought-the-alert cases — reported per era.

## 6 · What would kill it (frozen)

- Trigger-day clusters' Wilson UB < null mean → fast falls on these markets mean-revert
  faster than they extend; a velocity leg is anti-signal → **KILL** + DO_NOT_REBUILD row
  "drawdown-velocity composite leg on risk_radar_intl (construction-specific)". The ITR
  display-tier crash override is untouched by any RRI-S3 verdict (different tier, different
  ruler).
- H1 GO but H2 fail → the leg adds days but not timeliness: NO-GO for promotion; parks as a
  Tier-B-style confluence receipt (display ships freely; "coincident" label mandatory).

## 7 · Anti-look-ahead checklist

- ret10/percentile are causal trailing constructions; the trigger is same-day.
- Episode onsets (R-B) are enumerated on the outcome side of the study only — they never
  condition the trigger.
- Weight 0.6 and window 10 fixed here; the single declared alternative (−ret21) is a family
  cell, not a scan.
- No outcome joined before freeze (outcome-blind census only; the census DID show KR's
  velocity percentile at 97–100 on 07-13→16 — a trigger-side observation on the live tail,
  disclosed in cover §5).

## 8 · What a GO does NOT show

Not "velocity leads crashes" (never claimed); not a US-radar result (RRX owns that book); not
transferable to cn/hk/ca (byte-frozen, out of scope); not a probability statement
(flat-at-base stands). GO → Stage-B shadow accrual → operator ruling, per cover §2.

## Ratification

Drafted: Fable (main loop), 2026-07-17. Pre-freeze compute: outcome-blind census only.
Operator: ☐ ratify · ☐ decline.
