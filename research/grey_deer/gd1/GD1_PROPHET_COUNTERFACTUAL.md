# GD-1 Prophet counterfactual

Sidecar only. Boards are not rebuilt. GD-1 grants no live authority.

## Population

US raw candidates: `data/us_prophet_rank/candidates/2026-08.parquet`
CN raw candidates: `data/china_prophet_rank/candidates.parquet`

Hypothetical sidecar tested as an **illustration**, not a promotion:

> If `leadership_crack == BROKEN` (it was) and we withhold **new** buyable technology names on 2026-08-17, what happens on 2026-08-18?

That is one session, one incident, and **not** a PASS under the prereg.

## Coverage (this is the result)

Of **127 pit_live** buyable names on 2026-08-17 (not the unfiltered 241, which mixed 114 `recomputed_history` rows), only a minority had both 2026-08-17 and 2026-08-18 closes in `data/yahoo/<ticker>.parquet`. The earlier 39/241 coverage figure is withdrawn because the denominator was contaminated. **Full-board losses avoided remain BLOCKED on coverage.**

**Full-board losses avoided / upside forgone: BLOCKED on coverage.**

Priced subset (n=39), close-to-close 08-17→08-18, **descriptive coincidence only**:

| bucket | n priced | mean % | median % | share ≤ −5% |
|---|---|---|---|---|
| tech | 11 | −7.55 | −7.86 | 91% |
| other | 21 | −4.05 | −3.91 | 24% |
| defensive | 7 | −0.68 | +0.19 | 0% |
| all priced buyable | 39 | −4.43 | — | — |
| priced without tech | 28 | −3.20 | — | — |

Worst priced tech: CRDO −13.0, MTSI −10.6, ONTO −10.2, FORM −10.0, CIEN −8.9.

Withholding those 11 priced tech names would have improved the **priced-subset** mean by about 1.2 pp that session and avoided several ≥5% residuals. It would also have withheld TMUS (+1.46%). This is **not** a capital-utility estimate for the board.

## Other utility fields (packet §15)

| metric | status |
|---|---|
| losses avoided (full board) | BLOCKED — 16% price coverage |
| winners withheld (full board) | BLOCKED |
| MAE avoided | UNAVAILABLE — no intraday |
| upside forgone (full board) | BLOCKED |
| board expected-shortfall change | BLOCKED |
| time in protection | LC BROKEN entire window; a sidecar would have been on since at least 2026-07-17 |
| action churn | not computed; buyable 241→52 is the live gate, not a sidecar |

A sidecar that had been on since 2026-07-17 would have withheld tech new entries through the **August bounce** (SMH +5.55% on 2026-08-04). That upside cost is unmeasured here and is exactly why the current incident cannot be the only case.

## China board

2026-08-18: n=1635, featured=23, more_actionable=49, buyable Technology=47 (largest). Session-return column absent. **GD-H5 incremental collapse vs index: UNAVAILABLE** as a return statistic. Count-level: more_actionable 83 (08-14) → 49 (08-18); featured 24→23. Not a cross-sectional crash.

Intraday CN board quotes: **UNAVAILABLE**. `data/cn_prophet_live/forward.parquet` is empty.

## Policy counterfactual relevant to GD-6/7

Nothing here is a live new-entry restriction. The only honest product sentence on 2026-08-17:

> Leadership Crack is still BROKEN (display). The **pit_live** board still has 29 buyable tech names (22.8% of 127). Those facts coexist. A restriction would be a new policy, not something the board already did.
