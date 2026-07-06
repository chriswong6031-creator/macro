# F-HZ-1 — Dilution-Hazard Phase-0 Pre-Registration

**Status:** PRE-REGISTERED — numeric thresholds frozen at commit time.
Do NOT modify this document after the first commit.
**Family:** `dilution_hazard` (FDR budget 3, declared before any run)
**Program:** next-lobes PR-2
**Authored:** 2026-07-06
**Author model:** claude-sonnet-4-6 (build lane)

---

## 1. Registered Question

Do production fires (replay_boarded.parquet, verdict_grade=True cohort) that
carry an active dilution hazard at the fire date — defined by any of three
predicates (a) shelf filed <=365d, (b) takedown <=90d, (c) >=1 dilution event
trailing 365d — show higher stop5 and dead_money_21 at 21d than fires without
that hazard, after episode-clustering?

This is a descriptive phase-0 study. No alpha claim. No promotion. Display-only
permanently until a separate promotion prereg carries `derived_from_surface: f_hz1`.

---

## 2. Data Source: Backfill Depth Finding

The dilution collector (`collectors/edgar_dilution.py`) performs a bounded
trailing backfill of **~90 calendar days** on the first run (constant
`LOOKBACK_DAYS_FIRST = 90`). Subsequent nightly runs accrue a 7-day rolling
window (idempotent by accession dedup). There is **no full-history sweep**.

This means:

- If the study runs within the first ~90 days of collector activation, the
  hazard store contains at most ~90 days of S-3/S-3ASR/424B* events.
- Predicate (a) (shelf <=365d) and predicate (c) (>=1 event trailing 365d)
  require 365d of history to be fully PIT-correct; with only 90d of backfill,
  fires before the lookback horizon will falsely appear hazard-free.
- **Implication:** The ACCRUAL-CONVERT branch (§12.3) is active until the
  store accumulates >=365d of history. The n-floor check (§6) will also fail
  given an absent or freshly-seeded store, but ACCRUAL-CONVERT fires first
  (data gate precedes floor check). ACCRUAL-CONVERT is the expected outcome
  of this PR (see §12.3).

---

## 3. Predicate Definitions (FROZEN)

All thresholds in this section are frozen. They are imported verbatim by
`scripts/research/f_hz1_study.py` from the shared constants block in that
file (`F_HZ1_CONSTANTS`). If a future study modifies these thresholds it
must register a new family and prereg document.

**Source data:** `data/edgar/dilution_events.parquet`
Columns used: `filing_date` (PIT stamp — the date EDGAR accepted the filing,
no revision risk), `form` (string: one of S-3, S-3ASR, S-3/A, 424B1..424B5),
`ticker`.

**PIT law:** A filing is visible at fire_date only if
`filing_date < fire_date` (strictly before). A filing on the same calendar
day as the fire is excluded (intraday unknown, conservative).

### Predicate A — Active Shelf (<=365d)

```
hazard_shelf_active = any(
    filing_date in [fire_date - 365 days, fire_date - 1 day]
    AND form in {'S-3', 'S-3ASR', 'S-3/A'}
)
```

Threshold frozen: `SHELF_LOOKBACK_DAYS = 365`
Form set frozen: `SHELF_FORMS = {'S-3', 'S-3ASR', 'S-3/A'}`

### Predicate B — Recent Takedown (<=90d)

```
hazard_takedown_recent = any(
    filing_date in [fire_date - 90 days, fire_date - 1 day]
    AND form in {'424B1', '424B2', '424B3', '424B4', '424B5'}
)
```

Threshold frozen: `TAKEDOWN_LOOKBACK_DAYS = 90`
Form set frozen: `TAKEDOWN_FORMS = {'424B1', '424B2', '424B3', '424B4', '424B5'}`

### Predicate C — Trailing Dilution Event (>=1 in 365d)

```
hazard_trailing_event = count(
    filing_date in [fire_date - 365 days, fire_date - 1 day]
    AND form in {'S-3', 'S-3ASR', 'S-3/A', '424B1', '424B2', '424B3', '424B4', '424B5'}
) >= 1
```

Threshold frozen: `TRAILING_LOOKBACK_DAYS = 365`, `TRAILING_MIN_COUNT = 1`
Form set: all forms (shelf + takedown).

Note: Predicate C is a superset of A (on timing) and B (on count); the three
predicates are registered as independent FDR members because they represent
distinct economic hypotheses (shelf-overhang vs. issuance-recency vs.
any-dilution-activity).

---

## 4. Outcome Metric Definitions

### stop5

Binary (0/1). Frozen implementation: `stop5 = 1` iff
`fwd_mdd_5 <= (STOP_MULT - 1.0)`, where `fwd_mdd_5 = min(0, min(close[fill+1 .. fill+5]) / entry_price - 1)` is the maximum adverse excursion over fill+1..fill+5 (the minimum close in that window relative to entry, capped at 0 from below). `STOP_MULT = 0.95`, so the threshold is -0.05 (-5%).

In plain terms: stop5=1 iff the minimum close at any point within 5 trading bars after the fill reaches or breaches the -5% level from the fill price.

Source code: `entry_strata_phase0.py` line 428-429:
```python
fwd_5_ret = fm.get("fwd_mdd_5")
rec["stop5"] = (fwd_5_ret is not None and fwd_5_ret <= (STOP_MULT - 1.0))
```
`engine/grading.forward_metrics()` computes `fwd_mdd_5`.

**Degradation direction:** higher stop5 rate in the hazard arm = adverse.

### dead_money_21

Binary (0/1). Study-local metric defined as:
```
dead_money_21 = 1  iff  fwd_ret_21 <= 0.0  (flat or negative at 21d)
```
where `fwd_ret_21 = (close[fill+21] / close[fill]) - 1.0` is the simple
21-day forward return from fill price.

Rationale for separate definition: The canonical `dead_money` column
(`engine/grading.py`, `TerminalState.DEAD_MONEY`) is a 126-day window
metric (clean15_126: never hit ±8%, return < +5% at 126d). The spec
requests a 21d-horizon measure; `dead_money_21` is the closest well-defined
analog. Frozen threshold: `DEAD_MONEY_21_THRESHOLD = 0.0`.

**Degradation direction:** higher dead_money_21 rate in the hazard arm = adverse.

---

## 5. Cohort

- **Source:** `data/replay/replay_boarded.parquet` (gitignored, Mac-local;
  canonical path `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/replay/replay_boarded.parquet`
  — resolved by `run_rule_replay._CANONICAL_DATA`).
- **Filter:** `verdict_type == 'fire'` AND `verdict_grade == True`.
- **ERA LAW:** Absolute rates and comparisons computed on the
  `verdict_grade=True` cohort only. Survivor-biased cohorts are presented as
  within-cohort deltas only (never as absolute rate claims).
- **PIT integrity:** Dilution join uses `filing_date < fire_date` exclusively.
  No revision risk: EDGAR filing_date is the acceptance date, immutable.
- **Dead-name note:** The replay_boarded cohort reflects production fire history
  and inherits cheap_trap survivorship caveats. Names that were active at fire
  time but subsequently delisted remain in the cohort if present in replay;
  however, fires where forward price paths are unavailable are excluded from
  outcome computation and from the gradable counts used in floor enforcement
  (see §6). Both membership counts and gradable counts are printed.

---

## 6. Floors (PRINTED BEFORE ANY STATISTIC)

These floors are checked and printed to stdout before any p-value or rate is
computed. A floor failure routes to DEFER-on-floor or ACCRUAL-CONVERT:

```
N_FIRES_FLOOR        = 300   # minimum GRADABLE fires per arm (hazard vs. non-hazard)
N_EPISODE_FLOOR      = 25    # minimum distinct episode clusters per arm (on gradable fires)
```

**Floor enforcement is on GRADABLE counts only** — fires for which a price
path was available and outcomes (stop5, dead_money_21) were computed. Fires
where the massive_stock_day store had no entry for the ticker are excluded
from gradable counts (but their membership count is still printed for
diagnostic purposes). Episode clusters are also counted on gradable fires only.

Both membership count and gradable count are printed per arm before any
statistic. Example output:
```
FLOOR [hazard_shelf_active]: hazard membership=450, gradable=312 (need >=300),
  hazard n_clusters_gradable=38 (need >=25);
  non_hazard membership=2100, gradable=1850 (need >=300),
  non_hazard n_clusters_gradable=210 (need >=25) → PASS
```

If either floor is not met (on gradable counts):
- Print the floor message including both membership and gradable counts.
- Route to DEFER-on-floor. Exit with code 0 (not an error — expected for
  early-lifecycle runs when closes are absent).

---

## 7. Episode Clustering

Episode clusters follow `scripts/run_rule_replay._assign_episode_cluster()`:
- If `replay_boarded` has an `episode_id` column, use it directly.
- Otherwise fall back to ticker×year (YYYYQ ticker×calendar-year group).

This is identical to the run_rule_replay convention. Episode cluster count
is printed before any statistic.

---

## 8. Era-Law Splits

Two ERA splits are run on the full cohort:

1. **verdict_grade_2021plus:** fires where fire_date >= 2021-01-01.
   This is the non-survivor-biased window (massive_stock_day with dead names).
   Absolute rates and FDR tests are run on this cohort.
2. **pre_2021:** fires where fire_date < 2021-01-01.
   Presented as within-cohort deltas only. Survivorship bias caveat printed.

The primary verdict is on the `verdict_grade_2021plus` cohort. The
`pre_2021` cohort is directional context only.

---

## 9. FDR Budget (Declared BEFORE Run)

Family: `dilution_hazard`
Declared budget: `3`
Members: one per predicate — (A) shelf, (B) takedown, (C) trailing.

```python
led = TrialLedger(path=data/trial_ledger.jsonl, family="dilution_hazard")
led.log_declared_budget(3, family="dilution_hazard",
    reason="F-HZ-1: 3 predicates (A=shelf, B=takedown, C=trailing) × 1 arm each")
```

This call is made BEFORE any outcome computation. It is idempotent.
The ledger write happens even when data gates fail (so the budget is always
registered when the harness is invoked).

---

## 10. Verdict Criteria

**This batch is descriptive-only.**

- Report: arm sizes, floor check, episode cluster counts, stop5 rate per arm,
  dead_money_21 rate per arm, era-law splits.
- No promotion language. No wiring decision.
- A future promotion prereg must carry `derived_from_surface: f_hz1` and
  define its own FDR family + budget.
- No alpha is claimed or confirmed in any output of this study.

---

## 11. Coverage and Dead-Name Limitations

1. **Cheap_trap survivorship caveat:** The replay_boarded cohort contains
   production fires on surviving tickers. Tickers that fired and then delisted
   before the store was built are absent. Within-cohort comparisons of
   hazard vs. non-hazard arm are directionally meaningful; absolute rates
   carry survivorship bias.
2. **Dilution store coverage:** The EDGAR daily-index sweep covers S-3/S-3ASR/
   S-3/A and 424B1-B5 only. Other dilution mechanisms (ATM programs, convertible
   note issuances not filed as S-3) are not captured. The store covers back only
   ~90d on first run (see §2). Fires before that horizon are incorrectly labeled
   non-hazard.
3. **CIK→ticker mapping:** The CIK→ticker map uses `edgar_8k._company_tickers()`.
   Tickers with no CIK match have `ticker=None` in the dilution store and cannot
   be joined to replay fires. Such events are excluded from hazard labeling
   (treated as non-hazard). The count of unmapped events is printed.
4. **Dead-name coverage:** `data/edgar/_dead_name_coverage.json` is read by the
   vintage stamp. If absent, `stamp_degraded=True` is set in the summary JSON.

---

## 12. Pre-Committed Branches

Given the backfill-depth finding (§2), the run branches are:

### 12.1 RUN (nominal)
Conditions: dilution_events.parquet exists AND replay_boarded reachable AND
both n-floors met for at least one predicate arm AND store covers >=365d.
Action: run full study, write summary JSON + report skeleton.

### 12.2 DEFER-on-floor
Conditions: data present but n-floor not met for any predicate arm.
Action: print floor failure message, exit 0. Report is NOT written.

### 12.3 ACCRUAL-CONVERT
Conditions: dilution_events.parquet absent OR store covers <365d.
Action: print gate status including store age estimate and come-back date.
Come-back date = today + (365 - store_age_days). Exit 0.
No report written.

**Expected outcome of this PR:** ACCRUAL-CONVERT (data absent → gate fires,
exit 0 cleanly). This is the correct behavior and tests confirm it.

---

## 13. Adjacent Prior

The closest precedent is the W1 S-EV Earnings-Blackout study
(`research/entry_stack/W1_SEV_REPORT.md`). That study found:
- stop5 co-primary: **NULL** (CI includes 0 at k=3 pooled)
- mae21 co-primary: **NULL** (Welch t CI includes 0)

Implication: earnings-window proximity does not demonstrably worsen stop5 or
mae21 on the production fire set. The dilution hazard question is mechanistically
distinct (persistent dilution overhang vs. event-window timing), but if the
earnings signal produces a null, the prior on dilution producing a significant
result is modestly lower. This context is printed in the report when it runs.

---

## 14. Commit-Path Declaration (House Law)

- `data/edgar/dilution_events.parquet`: **gitignored** (nightly-only write,
  single writer = `collectors/edgar_dilution.py` via `scripts/collect.py`).
- `data/replay/replay_boarded.parquet`: **gitignored** (Mac-local,
  single writer = `scripts/run_rule_replay.py`).
- `data/research/f_hz1_summary.json`: **committed** (single-writer = this
  script; written only when study actually runs — NOT written in this PR).
- `data/trial_ledger.jsonl`: **committed** (append-only, multi-writer allowed).
- `research/dilution_hazard/F_HZ1_REPORT.md`: **committed** when study runs.
  NOT written by this PR (data absent).
