# PREREG — China Policy Events × Forward Returns (cycle-conditioned)

Date: 2026-07-06 (committed BEFORE any outcome computation — the git timestamp is the proof)
Program: `research/CHINA_INTEL_CYCLES_MASTERPLAN_BY_FABLE.md` W2 (RUL-1, RUL-2, RUL-5)
Family: `china_policy_events`
Status: PRE-REGISTERED — no forward returns have been computed for any event list below.

## Mechanism claim

PBoC easing actions (RRR cuts, LPR cuts) are discrete, dated, public policy events.
Hypothesis: they are followed by positive absolute drift in the broad A-share market
and positive relative drift in rate-sensitive sectors, and the effect differs by
macro regime context. The regime claim is DESCRIPTIVE ONLY in this study (RUL-2).

## Event families

| Family | Source (on disk, no new collection) | Events | Anchor |
|---|---|---|---|
| F-A RRR ease | `data/china_macro/rrr.parquet` `rrr_change < 0` | n=26 (2008-10-08 → 2025-05-07) | event date (see Date semantics) |
| F-B LPR cut | `data/china_macro/lpr_rate.parquet` diff(lpr_1y)<0 OR diff(lpr_5y)<0 | n=15 (2019-08-20 → 2025-05-20) | fixing date |
| F-X RRR hike | `rrr_change > 0`, n=27 (2006→2011 era) | EXPLORATORY (labeled, not FDR-gated) | event date |
| F-C MPC phrase-diff | `data/china_official/communiques.parquet` (W1.1) | EXPLORATORY/UNSIGNED per RUL-5 | publish date |
| F-D CCTV phrase events | W1.2 backfill | BLOCKED-DATA until backfill completes | — |

Date semantics (F-A): the parquet index is `REPORT_DATE` from Eastmoney
`RPT_ECONOMY_DEPOSIT_RESERVE`. The runner MUST verify announce-vs-effective
semantics against the upstream table before computing outcomes and document the
finding in the report. If only effective dates are available, the anchor is the
effective date and the report must note the bias direction (announcement precedes
effective ⇒ measured CAR understates announcement drift). This verification is a
data-honesty step, not a tunable.

## Outcomes

- Market: absolute log CAR on SHCOMP `data/china/000001.SS.parquet` (full event
  coverage 1997→). Descriptive repeat on 510300.SS where it exists (2012→).
- Sectors (relative): log CAR of Shenwan 银行 801780 and 房地产 801180
  (`data/china_sectors/`) MINUS SHCOMP log CAR.
- Entry: first close STRICTLY AFTER the event date (grader PIT convention); CAR
  measured from that close. Horizon ladder 5/10/20/40/60 sessions, descriptive
  curve; **verdict only at H=20**.
- Same-date events within a family merge to one episode before any statistic.
  Cross-family same-date coincidences are reported, not merged.

## Gated trials (BH-FDR family, verdict at H=20)

1. F-A RRR ease → SHCOMP abs CAR
2. F-A RRR ease → banks 801780 rel CAR
3. F-A RRR ease → real estate 801180 rel CAR
4. F-B LPR cut → SHCOMP abs CAR
5. F-B LPR cut → banks 801780 rel CAR
6. F-B LPR cut → real estate 801180 rel CAR

Trial budget declared via `TrialLedger.with_declared_budget(12, "china_policy_events")`
— 6 gated + headroom for the labeled exploratory legs (F-X hikes, 510300 variant,
F-C descriptive). Exploratory legs are logged in the ledger and NEVER enter the
FDR family or any verdict.

## Statistical gates (all required for GO, per gated trial)

- Episode K ≥ 8 at H=20 (else BLOCKED-POWER, reported).
- Newey–West HAC t (lags=4) on episode CARs, |t| ≥ 2.0 with hypothesized sign.
- Benjamini–Hochberg FDR α=0.10 across the 6 gated H=20 p-values only.
- Deflated Sharpe ≥ 0.90 via the family TrialLedger.
- Chronological split-half: same sign of mean CAR in both halves.
- Verdicts: GO / ACCRUE (right-signed, sub-threshold → forward ledger + registry
  entry with come-back date) / NO-GO (wrong sign or gates fail) / KILL
  (wrong-sign significant) / BLOCKED-DATA.

## Cycle/regime conditioning — DESCRIPTIVE ONLY (RUL-2)

For each gated family, print context tables cut by, at event date:
- `quad` and `liquidity` and `cycle` from `data/china_regime/regime_history.parquet`
  (1997→, full event coverage);
- sector cycle `phase` from `data/china_sector_cycles/backfill.parquet` (2010→,
  partial coverage — cells report their own n).

Cell format: n, mean CAR@20, median CAR@20. NO t-stats, NO stars, NO verdict
language in conditioning tables. Cells with n<5 print n only. A conditioning cell
may graduate to a gated hypothesis only via a future amendment committed before
its outcomes are computed, with its own budget.

## Reporting

- `data/experiments/china_policy_events_results.json` (schema: per-trial CARs by
  horizon, gates, verdicts, conditioning tables).
- `reports/china-policy-events-phase0.md` — plain-language with "In plain
  English" boxes (house standard). Nulls are printed, not hidden.
- Registry: each ACCRUE/GO family registered in
  `data/experiments/registry_seed.json` with maturation criterion + come-back date.
- No wiring: nothing feeds any engine, board, or score. Display of results on any
  page requires the standard gauntlet and never the word "validated" without the
  BC-2 allowlist.

## Void rule

Any threshold, event definition, horizon, or gate edited after outcome data has
been seen voids the affected verdict — the edit itself is the finding.
