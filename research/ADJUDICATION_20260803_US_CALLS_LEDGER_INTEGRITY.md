# Adjudication 2026-08-03 — us_calls ledger integrity (universe oscillation, missing stamps, store-less accruals)

Status: ADJUDICATED (Fable main loop, 2026-08-03). Chip source:
`ADJUDICATION_20260803_ORCL_NAME_SCORE_FLATLINE.md` §3, item 2 — "us_calls ledger
integrity — per-stamp universe oscillates 1,662 ↔ 2,966 across adjacent stamps,
stamps 2026-07-13/23/24 are missing entirely, and CTRA/CWEN-A/TCNNF/TPH accrue
rows with no local store." Everything below is measured against the ledger at
`ea11b059df3` (2026-08-03) and the Actions run history.

## §0. Verdicts

Three anomalies, three different causes — **none of them a scan-crash or timeout
truncation** (the partial-run hypothesis is refuted by set relations: every small
stamp is a clean source-group subset, never an alphabetical or mid-scan prefix,
and the count levels cluster tightly at ~1,700 and ~2,930 with no intermediates).

1. **Oscillation = expansion + one lane-asymmetry reversion, not noise.**
   - 06-29 → 07-20 drift (1,662–1,722): organic membership churn + curated-extras
     additions. Benign.
   - **07-21 step +1,262 names (1,704 → 2,966): the Russell 2000 breadth close
     cache came online** (`data/russell_breadth` first commit `eb2d2506b9e`,
     2026-07-20T17:58 PT — minutes before the 07-21 stamp's engine run). The
     07-20 universe is a strict subset of 07-21's (1,704/1,704 carried, 0
     dropped). A legitimate feature landing.
   - **07-25 reversion (1,704 = the pre-expansion set ± 6 names): written by the
     weekly deep-dive lane** (`5230c2b5900`), the only writer that day because
     the nightly was wedged. `weekly.yml` restored the S&P 500/600/400 closes
     caches but had **no russell restore step** (daily.yml was the only workflow
     with one), and `universe()` skipped the missing source group with a
     logger-only warning — which the Actions summary drops (annotation law). The
     stamp went thin silently.
2. **Missing stamps 2026-07-13/23/24 = failed/cancelled nightlies whose runs
   never reached the engine commit.** 07-13: both morning runs died (failure
   05:30Z, cancelled 07:54Z). 07-23/24: the runs created 07-22/07-23 23:2xZ hung
   and were cancelled by the next day's trigger, inside the wedged-nightly window
   (07-16 → 07-26 — most wedged runs still stamped because the engine commit
   lands ~3.5 h in; these two hung earlier). With keep-FIRST PIT semantics and
   the nightly-sole-advancer law, these holes are permanent by design.
3. **Store-less accrual is the architecture, not the anomaly.** `data/stocks/`
   per-name stores were never the universe source: 2,754 of the ledger's 2,989
   tickers have no per-name store — their series live in the breadth closes
   caches and the curated-extras yahoo store. What made the four named tickers
   stand out is that their **feeds died while the scan kept stamping**: CTRA and
   TPH are `stock_search` extras whose `data/yahoo` stores last printed
   2026-05-07 / 2026-05-13, TCNNF's store has 19 rows (last 2026-07-17), and
   CWEN-A's smallcap-cache column froze 2026-06-26. That is exactly the
   frozen-feed echo class PR #4441 closed: the admission gate refuses them from
   the first post-merge nightly (lag ≫ 7d), and their historical echoes are
   already quarantined at `grade()`. No further ledger-side fix is warranted;
   the upstream "why did the collectors let these go stale" question is the
   separately chipped collector-lane defect (same chip as QCOM/HOOD/MRVL/CVNA).

## §1. Does any of it move the grader's rank-IC denominators?

**Not today — measured, not assumed.** `grade()`'s US forward join resolves
tickers only through `store.read("stocks", …)` (`data/stocks/`), so the
gradeable per-stamp cross-section is **flat at 231–235 names on every stamp**,
including the thin 07-25 (which carries the full deep-store subset — `universe()`
reads `data/stocks` first, and that group was present in every lane). The
oscillating ±1,262 cache names all grade to `None` and never enter rank-IC or
hit-rates. The three missing stamps cost `n_ic_dates` −3 — real, mild, disclosed.
Residual risk: if per-name store coverage ever widens toward the cache universe,
thin stamps WOULD start moving the denominators — `grade()` now prints the
per-date IC cross-section (`ic_cross_section` min/median/max) so that insulation
is self-monitoring instead of remembered.

## §2. Ruling — disclosure, never a coverage gate

A thin stamp is real-but-incomplete coverage: strictly more information than the
missing stamp a universe-size admission block would produce (blocking 07-25
would have deleted the day outright), and accrual is never blocked (house
epistemics). The ORCL adjudication's declined-`stale`-column ruling extends here:
no ledger schema change — scanner/lane state belongs in logs and `grade()`
output. Shipped in this PR:

- **`universe()` source-group skip is loud** — missing or unreadable breadth
  cache/constituents now emit line-start `::warning` annotations (bare print,
  annotation law) naming the group, in every lane that assembles the universe.
- **Writer-side shrink disclosure** — `append_name_calls` warns (annotation,
  never a refusal) when a stamp admits < 80% of the previous stamp's names
  (floor 25; once per stamp; same-day re-runs — the only path that can widen a
  thin stamp under keep-FIRST — stay silent). Covers all five markets' ledgers
  and every truncation class, including ones with healthy caches.
- **`grade()` denominator disclosure** — per-horizon `ic_cross_section`
  {min/median/max of per-date graded rows} and cadence-aware PIT continuity
  (`n_stamp_gaps` + `stamp_gap_dates`: a gap is a missing calendar day whose
  weekday the ledger has stamped before, so the weekday-only CN ledger never
  miscounts weekends while US/HK/CA/INTL count every day).
- **Russell cache-restore parity** — the restore step existed only in daily.yml;
  added to `weekly.yml` (the measured failure), `engine-render.yml`,
  `render.yml`, `closing-bell.yml`, `earlyclose.yml` — every lane that restores
  the S&P trio for the library build. (`special-sits-backfill.yml` restores only
  the S&P 500 cache for its own narrow purpose and is not a library lane;
  `asia-close.yml` restores no US caches. Both left alone.)

## §3. Explicitly NOT done

- **No lane gate on `append_name_calls`.** The weekly write SAVED stamp 07-25
  from being a hole; nightly + weekly both advancing this ledger is the standing
  configuration (the ledger-lane-gate program's 19 gated writers deliberately
  did not include it, and that program is complete). Gating the weekly out would
  manufacture missing stamps.
- **No rebuild of PR #4441** (frozen-feed admission gate, `grade()` echo
  quarantine) — this PR is additive around it.
- **No ledger mutation or backfill.** The 07-25 thin stamp and the three holes
  stay as historical record: append-only PIT, R2 is truth, and §1 shows the
  measurement layer is insulated.
