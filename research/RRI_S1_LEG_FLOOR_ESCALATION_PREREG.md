# RRI-S1 — Leg-Level Floor Escalation (prereg)

**Status: FROZEN ON MERGE — before any construction↔outcome relationship is computed.**
Family: `rri_2026h2` cells 1–4 (see [RRI_CRASH_ANTIFIRE_PROGRAM.md](RRI_CRASH_ANTIFIRE_PROGRAM.md)
§4). Shared rulers R-A..R-D and the verdict grammar bind verbatim. Scope: kr/jp/tw/in/au/gb/ez.

## 1 · The question, in plain English

On 2026-07-16 the KR extension leg alone printed 90.3 — inside the leg meters' published
risk-off band (≥88) — for the fourth straight session, yet the blended composite sat at
watch-59 because the FX and rateshock legs were quiet. The composite's all-legs-must-agree
blend is the anti-fire mechanism. **Does a single Tier-A leg in its published risk-off band,
with the context gate open, carry enough forward-drawdown information on these 7 markets that
the composite's band should be floored at "elevated"?**

## 2 · Frozen construction

For market m with incumbent gated state S(t):

```
trigger(t) = [ any composite leg pctile_leg(t) >= 0.88 ]  AND  gate_open(t)
S_v1(t)    = max(S(t), "elevated")   if trigger(t)   else S(t)
```

- `pctile_leg` = the leg's composite percentile exactly as `compute()` builds it (mean of its
  sub-leg causal percentiles); 0.88 is the **existing published `_SCARE_BANDS` risk-off
  band — no new tuned constant is introduced**.
- The floor NEVER lifts to risk-off; the 91 band remains reachable only by the blend.
- The context-gate cap law is unchanged: gate closed ⇒ no loud tier, trigger or not.
- Nothing else changes: probabilities stay flat-at-base; gross_factor follows state as today.

Declared cells (family §4): **P1 (primary) = any-leg @0.88**; S1b = ext+fx legs only @0.88
(rateshock excluded — it is the chronic-firing leg in hiking regimes); S1c = any-leg @0.95;
S1d = ext+fx @0.95. No other threshold or leg subset may be scanned.

## 3 · Primary frozen hypothesis (H1, one-sided)

On **escalated-only days** — trigger(t) true AND incumbent S(t) below elevated — pooled across
the 7 markets over R-D windows:

> P(≥5% drawdown within h21) on escalated-only days exceeds chance at matched trigger
> structure — "chance" = the R-C permutation-null mean, the only denominator any gate uses.
> **Gate:** cluster-Wilson-LB (R-A) ≥ 1.25 × the R-C null mean, AND permutation p < 0.05,
> AND the BH-FDR rank threshold (cover §4) — the stricter of the two p-rules binds.

Robustness gates (all must pass for GO):
- **Era:** observed/null-mean ratio > 1.0 in both the pre-2016 and 2016+ eras (pooled).
- **Split-half:** ratio > 1.0 in both halves (pooled).
- **Breadth:** ratio > 1.0 in ≥5 of 7 markets (direction only; per-market numbers are
  receipts, not gates).

Secondary (reported, not gated): paired episode capture — on R-B episodes, count episodes
where S_v1 reaches loud-tier within [onset−10, onset+15] but the incumbent does not
(and the reverse); latency medians per R-B.

## 4 · FP budget (frozen)

The census (§5 of the cover) already prices this candidate honestly: any-leg@0.88 adds ~10.1%
of days (mean of 7; kr 15.4%) to the loud tier. The budget below therefore does not pretend
the candidate is cheap — it exists to stop a promoted variant from firing beyond what was
priced in, and to force the lift gates to carry the full epistemic weight:

- Pooled added loud-tier days ≤ **12%** of market-days (last-10y replay).
- No single market's added loud-tier days > **16pp**.
- Escalated-only clusters must number ≥8 pooled (N floor, else ACCRUE; census: 355
  full-history / 111 last-10y pooled 21-gap clusters — comfortably powered).

Blowing the budget at replay = NO-GO for that cell regardless of lift. Stated plainly: the
caps are census + margin (12% ≈ mean 10.1% + 2pp; 16pp ≈ worst-market 15.4% + 0.6pp) —
deliberately census-covering. They do not constrain the primary at replay; they fence
promoted-variant drift and any future re-run on longer history from firing beyond what the
operator priced in here.

## 5 · What would kill it (frozen)

- Escalated-only days' cluster hit rate significantly BELOW null (Wilson UB < null mean):
  the quiet-legs veto was *information*, floor-lifting destroys it → **KILL** + DO_NOT_REBUILD
  row "single-leg floor escalation on risk_radar_intl composites (construction-specific)".
- All four cells NO-GO → the family's floor-escalation arm closes; leg-level risk-off readings
  remain what they are today: per-scare display meters.

## 6 · Registry-fit notes (why this is not a forbidden pattern)

- Not a **laundered override gate** (DO_NOT_REBUILD §1, BTC D1–D5 class): the trigger is a
  deterministic function of the same store data the composite reads, pre-registered here with
  its own ruler, FP budget and kill row — not a human override smuggled into scoring.
- **Calendar-agnostic** (RIC-R3): no event/OPEX conditioning anywhere in the trigger.
- Promotion path: Stage-A replay → Stage-B shadow forward log → operator ruling (cover §2).
  Until then the live radar is untouched.

## 7 · Anti-look-ahead checklist

- Leg percentiles and gate are the existing causal trailing-window constructions; the floor is
  a pointwise function of same-day values — no future data touches trigger(t).
- Replay states recomputed via `composite_series` (no re-fit, no re-percentile of history with
  knowledge of the crash).
- Census disclosed outcome-blind; no outcome joined before freeze.

## 8 · What a GO does NOT show

- Not a claim that the composite weights are wrong, that 0.88 is optimal, or that the floor
  helps cn/hk/ca (out of scope, byte-frozen).
- Not a probability statement: prob surfaces stay flat-at-base; a GO changes the *band*, and
  only after Stage-B + ruling.

## Ratification

Drafted: Fable (main loop), 2026-07-17. Pre-freeze compute: outcome-blind census only.
Operator: ☑ **RATIFIED** (in-session, 2026-07-17).
