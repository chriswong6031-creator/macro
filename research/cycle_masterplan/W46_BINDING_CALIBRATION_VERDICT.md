# W4.6 — Risk-channel binding calibration: the verdict

**Wave:** W4.6 (Cycle Intelligence Masterplan), re-scoped to the RISK channel by §6.5 item 2.
**Date:** 2026-07-03.  **Basis:** the W0.4 keystone research cohort (`tr` / `tr_v0`, research-only per A1).
**Artifact:** `data/regime/ladder_risk_calibration.json`.
**Fit script:** `scripts/fit_ladder_risk_calibration.py`.

## In plain English

We asked one question: *does the cycle "ladder" state tell you anything about how deep the next
drawdown will be — once you strip out the fact that some instruments are just more volatile than
others?*

The answer is **no.** Before we correct for volatility, the raw ladder table *looks* like it carries
risk information (the "DECLINE" state shows the deepest drawdowns). But that is an illusion: DECLINE
states simply tend to occur in already-volatile instruments. Once we divide each forward drawdown by
the instrument's own recent volatility — the honest correction — **every ladder state's drawdown is
indistinguishable from its family's baseline.** So the calibration ships with **no effect**: every
state's size multiplier is exactly 1.0. This is a real, valuable result: it stops us from sizing
positions off a signal that was never there.

## What was measured

- **Evidence base:** 8,344 leak-free point-in-time stamps (11 US SPDR sectors + 24 single-country
  iShares ETFs, month-end 2005–2026), each joined to bar-i+1 forward outcomes for h ∈ {21, 63, 126}
  trading days. Reused verbatim from the keystone cohort (no re-backfill).
- **The §6.5 fix — vol-residualization:** `rdd = fwd_maxdd / trailing_63d_realized_vol`, computed
  point-in-time (only tape ≤ the stamp date). This removes the "deep-drawdown state = volatile
  instrument" confound that made the D2 §4.1 metric denominator-dominated.
- **Statistic:** per (state × family × horizon), the vol-residualized p10 drawdown **gap vs the
  family base rate**, with month-block bootstrap 95% CIs (resample whole stamp MONTHS — the
  cross-section within a month is correlated; ruling A2), counting **n_months, not n_rows**.
- **Discipline:** a cell earns a size multiplier ≠ 1.0 **only if** its gap CI excludes the null
  **AND** it survives BH-FDR (q = 0.10) within the `calibration` family.
- **Embargo:** a permanently-embargoed holdout `[2024-01-01, end]`, declared in the artifact. The
  split is a fixed calendar date, not a data-dependent quantile — refitting with more data can never
  move it (R1 reflexivity containment; unit-tested).

## The result — THE headline

**No risk-sizing signal survives.**

| horizon | (state × family) cells tested | nominal (pre-FDR) hits | BH-FDR q=0.10 survivors |
|---|---|---|---|
| 21 / 63 / 126 d, pooled | **48** | **2** (country FRESH BUY @21d p=.042; country ROLLING OVER @21d p=.048) | **0** |

The 2 nominal hits are exactly the ~2–3-by-luck rate the ledger's FDR budget (§9) fences: the
smallest p-value (0.042) must clear 1/48 × 0.10 = 0.002 to survive at rank 1, and does not.

**Every (state × family) cell ships `risk_size_mult = 1.0`.** The raw `data/regime/ladder_calibration.json`
drawdown ordering (DECLINE deepest, etc.) was ambient-vol clustering — exactly the keystone re-steer's
diagnosis (§6.5: "a vol-clustering fact, not a timing signal").

## BC-1 (return channel, as pre-registered): **FAIL**

Evaluated exactly as PREREGISTRATION.md §4 writes it (the return-per-tail metric
`mean_fwd_ret / |dd_p10|` per state): the train→holdout rank-correlation is **−0.119** (bar is
> 0.5 — and it is *negative*, i.e. the ordering inverts out of sample). `n_eff` per cell is ample
(min 98 months). This is the pre-registered §6.5 expectation: BC-1 fails, so the artifact ships
`validated = false` and the ladder is FRAME context, not a fitted score.

## BC-2 (the 'validated' grep gate): **WIRED + PASSING**

`scripts/check_validated_claims.py` scans templates/, site JS, and generated `*_data.js` in EN + zh
for `validated`/`已验证`, and fails on any **affirmative** claim that maps to no backing artifact
(`validated:true`) or justified allowlist entry. Negated/hedged uses ("no validated edge",
"unvalidated", "invalidated") and structural non-claims (engine-stamped data-field values, CSS class
tokens, i18n label pairs) are skipped by construction. The whole committed tree passes; the selftest
proves the gate fires on a synthetic unearned claim in **both** EN and zh. **No unearned uses were
found** — the existing corpus was already disciplined; the gate's value is forward-looking. Wired as
a HARD abort-lane step in `cycle-calibration.yml`. Allowlist: `data/regime/validated_claims_allowlist.json`
(166 entries, each naming the study/artifact it rests on).

## What binds, precisely

- `engine/cycles.py` reads the artifact when present and emits a NEW additive field `risk_size_mult`
  on the ladder output (fallback: 1.0 for every state — byte-identical to today; W2.8 fitted-bands
  pattern: artifact + fallback + one-time log). The directional `LADDER_SCORE` is **untouched** —
  direction was never validated and the axis-flip is **W4.7's** question.
- `engine/sector_central.py` consumes `risk_size_mult` in the SIZE path only (a capped shave of the
  above-neutral score, never a lift, never a direction change; traced in `components.risk_size_mult`).
  Inert today (all 1.0); wired so a future price-basis re-fit binds automatically.
- `engine/cycle_ontology.py:write_stance_matrix()` attaches per (phase × ladder) backfilled
  vol-residualized DD/forward evidence to each of the 42 stance cells (R3) — display/bindable
  metadata, no behavior change to `resolve_state` this wave.

## Ruling A1 note

The keystone cohort is `tr`/`tr_v0` (research-only). Because the verdict is null, the binding is
numerically inert (all 1.0) and no user-facing card is sized off the TR cohort. `validated` stays
false. Before any non-1.0 weight could ever bind to a user-facing card, the fit must be re-run on the
price-basis production backfill.

## Audit findings closed

- **cycles-core-1** (calibration decorative + inverted claim): the ladder calibration now *binds*
  (an additive field the engine reads), and the "inverted" return-lens claim is resolved honestly —
  the ordering does not reproduce OOS (BC-1 FAIL), so it is not asserted as a fitted score.
- **sector-central-us-5** (hand weights): the risk-size lever is fitted (and honestly null), not a
  hand constant; the trend/regime gates already moved to the size-cap path.
- **doctrine #4/#5:** the word "validated" is now mechanically gated to a backing artifact.

## Regenerate

```
python -m scripts.fit_ladder_risk_calibration          # fit + emit the artifact
python -m scripts.fit_ladder_risk_calibration --print   # fit + print verdict, no write
python -m scripts.check_validated_claims --selftest      # prove the grep gate fires (EN+zh)
python -m scripts.check_validated_claims                 # scan the tree (BC-2)
python -m pytest tests/test_ladder_risk_calibration.py -q
```
