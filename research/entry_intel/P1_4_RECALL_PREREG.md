# P1.4 Recall Audit — Pre-Registration

**STATUS: APPROVED — Fable 2026-07-05 (see §APPROVAL at end; original draft-gate text follows) (ruling R8: does not execute before replay golden test + PIT audit are clean)**
**Revision:** 2026-07-04 — blocking fix applied (P1.4-B1: NEVER-TRIGGERED data clause amended — denominators computed from PIT price store + replay verdict join, false 'replay columns only' claim corrected) + era law absorbed from P0_MEASUREMENT_MEMO.md v1.0; §5 conformance checklist reference added.

*2026-07-04 · Entry Intelligence program (research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §5/P1.4) ·
registered BEFORE first run — this file's merge commit precedes any analysis.*

---

## Study identity

**Label:** P1.4 Recall Audit
**Purpose:** The program's first coverage metric — a denominator-first census that measures
what fraction of objectively significant price events the funnel fires on, near-misses, rejects
by known reason, or misses entirely (never triggered). This is the standing counterweight to
precision-stacking (rulings R7, §8 risks): a gate-heavy funnel can report perfect entry quality
while missing the market.

**Relationship to other P1 studies:** this study reads the same replay artifact as P1.1–P1.3
and P1.5 but is NOT an outcome study — it is a denominator audit. No terminal-state partition
is tested here; no promotion gate can be cleared by it. The recall numbers become standing
quarterly KPIs that accompany any precision/gate-quality claim.

---

## Data source (frozen — two-source design, explicitly declared)

This study uses a **two-source design** to resolve the structural constraint that NEVER-TRIGGERED events, by definition, have no replay row — they cannot be detected from the replay artifact alone. The two sources and their roles are:

**Source 1 (denominator detection + in-universe membership):** the canonical PIT price panel (`data/massive_stock_day/` for 2021+ primary window names; absolute path used at run time). This source supplies the price columns needed to (a) identify durable-low events (Denominator A) and large-forward-move events (Denominator B) for every in-universe name, including NEVER-TRIGGERED names; and (b) confirm in-universe membership by the same universe definition the replay uses. The price panel is read point-in-time: forward windows use only bars available at the time the denominator event would be observable (no forward-fill beyond available data; delisting excluded). This is not leakage because the denominator is the ground-truth event set, not a funnel feature.

**Source 2 (verdict lookup):** `data/replay/standout_replay.parquet` (the P0.1 production replay artifact). All funnel verdicts (FIRED / NEAR-MISSED / REJECTED) are looked up exclusively in the replay artifact. A NEVER-TRIGGERED event is one where the in-universe (ticker, date) pair has a denominator event in Source 1 but has zero matching rows in Source 2.

**No other data files are read.** No live board JSON, no `site/factordata/` files, no online calls. The narrow PIT-price-panel exception (Source 1) is the only addition to the former "replay-only" clause; it is declared explicitly here and does not constitute a study-era feature that could leak signal-time information into the denominator.

**Leak-audit note:** Source 1 is used solely for denominator event detection. It supplies no feature values that enter the funnel-verdict partition — those are all from the replay. The price panel is confirmed PIT by construction (Massive store holds delisted names with full history through last trading day; no survivorship selection applies within the 2021+ window).

If Source 1 (the Massive price panel for the primary window) is absent or incomplete, this study **HALTS** and returns a blocker report rather than silently collapsing NEVER-TRIGGERED detection to zero.

If the replay artifact (Source 2) is absent or its golden test has not passed, this study does not run (ruling R8).

---

## Era handling clause

**Memo citation (mandatory):** `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)`. Every run prints this citation in the preamble.

**Primary window:** `2021-07-06 → last-full-replay-date` — the sole verdict-grade era per the P0 Measurement Memo §1 era table (STRICT-WINS ruling). The former PREREG placeholder "pre-2015" is superseded; the memo §1.2 makes clear the boundary is `2021-07-06`, not 2015. Every recall rate, denominator count, and Wilson CI reported as a verdict-grade result uses only unstamped (`survivor_bias = false`) rows from this window.

**Survivor-stamped rows (context appendix only):** replay rows carrying the `survivor_stamp` flag (pre-2021 or any row whose price source cannot be confirmed as Massive-or-equivalent, per memo §2.1) are segregated into a context appendix labeled "PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE." They are NOT included in any primary recall rate. They may be printed as an appendix table with explicit stamp disclosure for directional context only.

If `P0_MEASUREMENT_MEMO.md` does not exist at execution time, the study **HALTS** and returns a blocker report — it does not self-select an era.

**Why this matters:** the replay's pre-2021 rows are survivor-priced (delisted names largely absent; 92.7% of delisted member-months invisible in the production panel). Recall computed on survivor-priced rows will overcount funnel fires on the "easy" surviving universe while undercounting false-bottoms from names that subsequently delisted. The 2021+ Massive-sourced window is the only one where bias is bounded.

**§5 conformance checklist** (P0_MEASUREMENT_MEMO.md §5 — confirmed at run start):
- [ ] Cites `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` in preamble.
- [ ] Primary window = `2021-07-06 → last-full-replay-date`.
- [ ] Verdict-grade recall rates on `survivor_bias = false` rows only.
- [ ] Confirms via per-row source stamp that unstamped rows are Massive-sourced.
- [ ] All pre-2021 rows stamped, routed to labeled context appendix, excluded from primary recall rates.
- [ ] `horizon_censored` rows excluded per-horizon, tracked separately.
- [ ] Mandatory stamp text printed with era census missing-fraction.
- [ ] If unstamped denominator size < 50, returns thin-denominator flag (honest null) rather than borrowing pre-2021 rows.

---

## Denominator definitions (frozen before any look)

Two independent denominators are registered. Both must be computed from the replay artifact's
price columns (or features derived solely from those columns) using point-in-time data only —
no forward information enters the denominator construction.

### Denominator A: Durable-low events

A **durable-low event** for name *i* on date *t* satisfies ALL of the following conditions:

1. **Local low:** the close price at *t* is a 60-trading-day rolling minimum — i.e., it is
   the lowest adjusted close over the 60-bar window ending at *t* (bars *t−59* through *t*).
   If fewer than 60 prior bars exist for the name in the window, the event is excluded.

2. **Not undercut in 60 forward trading days:** the adjusted low price on no bar in the window
   *t+1* through *t+60* falls below `close_t × 0.95`. This is the exact `durable_bottom_60d`
   condition from the validated backtest harness (`research/bottom_signal_backtest/metrics.py`
   line 57: `not (win60["low"] < signal_low * 0.95).any()`). The 0.95 floor (a 5% undercut
   tolerance) is registered here and may not be changed post-hoc.

3. **Depth floor (ATR-scaled):** the 60-day rolling minimum close at *t* must lie at least
   1.0 × ATR(14) below the 60-day rolling maximum close over the same trailing window
   (`max_close_{t-59:t}`). This ensures the event represents a meaningful drawdown, not a
   flat series that trivially produces a 60-day local minimum.
   `depth_ok = (max_close - close_t) >= 1.0 * atr14_t`
   where `atr14_t` is the 14-bar ATR computed from the replay artifact's high/low/close columns
   at bar *t*. If ATR columns are not available in the replay artifact, this sub-condition is
   waived and the waiver is disclosed in the report's measurement-limitations section.

4. **In-universe:** the name was in the board's candidate universe on date *t* — i.e., it
   appears as a candidate row in the replay artifact for date *t* (any verdict: fire, near-miss,
   rejection, or never-triggered). Names not present in the replay universe on a given date are
   excluded from that date's denominator.

5. **In primary window:** date *t* falls within the primary era as specified by the P0
   Measurement Memo era table.

**Deduplication rule:** if a name produces durable-low events on consecutive dates (a
multi-bar rolling minimum), only the FIRST date in the consecutive sequence is retained as
the canonical event. Consecutive is defined as dates within 5 trading days of each other.
This prevents a single bottom from multiplying into many events by sliding window mechanics.

**Denominator A size = count of unique (ticker, date) durable-low events after deduplication.**

### Denominator B: Large-forward-move events

A **large-forward-move event** for name *i* on date *t* satisfies ALL of the following:

1. **+20% forward move in 60 trading days:** the adjusted close on bar *t+60* is at least
   20% above the adjusted close on bar *t*: `close_{t+60} / close_t − 1 ≥ 0.20`.
   If bar *t+60* is absent (delisting, insufficient history), the event is excluded.

2. **In-universe:** same rule as Denominator A condition 4.

3. **In primary window:** date *t* falls within the primary era; the forward 60 bars must also
   be within available price history (no forward-fill beyond available data).

**Deduplication rule:** same 5-bar consecutive-sequence rule as Denominator A.

**Denominator B size = count of unique (ticker, date) large-forward-move events after deduplication.**

**Joint overlap note:** an event may appear in both A and B simultaneously. The overlap count
is printed as a descriptive statistic. The denominators are NOT merged; all recall rates are
reported separately against each.

---

## Funnel-verdict partition (applied at the event date)

For every event in Denominator A and every event in Denominator B, the replay artifact is
queried for the funnel verdict recorded for that (ticker, date) pair. The verdict at the
event date is classified into exactly one of the following four categories:

| Category | Definition |
|---|---|
| **FIRED** | The replay artifact records a fire verdict (tier PRIME, ARMED, or APPROACHING) for this (ticker, date). The sub-tier and alignment tier are preserved as sub-columns for descriptive breakdown. |
| **NEAR-MISSED** | The replay artifact records a near-miss verdict; the `primary_rejection_reason` is taken from the `REJECTION_TAXONOMY` and preserved. A near-miss means the name was a candidate and passed all but one gate condition. Sub-counts by reason: `freshness_expired`, `not_topped_veto`, `tier_cutoff`, `extension_demote`, `knife_demote`, `sector_cap_displaced`, `board_rank_cutoff`. |
| **REJECTED** | The replay artifact records a rejection verdict (candidate evaluated but blocked, not a near-miss). The `primary_rejection_reason` from `REJECTION_TAXONOMY` is preserved. Sub-counts by reason. |
| **NEVER-TRIGGERED** | No row exists in the replay artifact for this (ticker, date) pair — the name was in-universe (satisfying denominator condition 4 by the universe definition) but the prefilter found no cross-candidate on that date; the funnel never evaluated it. |

**Verdict lookup rule:** the event date *t* is matched to the replay row with the same
ticker and date. If the replay has multiple rows for the same (ticker, date) (possible if
the prefilter produced multiple candidate bars), the row with the highest-tier fire verdict
is used; if no fire row exists, the most lenient rejection reason is used (near-miss beats
rejection beats never-triggered).

**Never-triggered disambiguation:** if a name is in the universe definition but has zero
replay rows for a date, it is NEVER-TRIGGERED. If a name has zero replay rows across its
entire history (e.g., it was added to the universe after the replay window), it is excluded
from the denominator entirely (not counted as never-triggered).

---

## Capped trial grid (enumerated explicitly)

This study is a descriptive census. There are NO hypothesis tests that require multiplicity
control and NO config knobs that produce a trial family in the PREREG sense. However, the
following enumeration is registered in the trial ledger under family `p1_4_recall_audit`
before any run, so that any post-hoc variation is automatically a new recorded trial:

| trial | description | output statistic |
|---|---|---|
| T1 | Recall rates against Denominator A (durable-low events), primary window, all funnel verdicts | Partition fractions + Wilson CIs |
| T2 | Recall rates against Denominator B (+20%/60d moves), primary window, all funnel verdicts | Partition fractions + Wilson CIs |
| T3 | Sub-breakdown of NEAR-MISSED events by rejection reason (both denominators) | Count + fraction tables |
| T4 | Sub-breakdown of REJECTED events by rejection reason (both denominators) | Count + fraction tables |
| T5 | FIRED sub-breakdown by fire tier (PRIME / ARMED / APPROACHING) for both denominators | Count + fraction tables |

m = 5 registered outputs. No significance tests are applied; Wilson CIs are confidence
intervals for a proportion, not hypothesis tests — they are not a multiplicity concern.
Any comparison across denominators, eras, or sub-windows beyond T1–T5 must be logged as a
new trial (T6+) under §8 before examination.

---

## Primary statistic and threshold

**No pre-registered pass/fail threshold.** This study is a descriptive census, not a
hypothesis test, as specified in the masterplan (§5/P1.4: "Descriptive census with CIs —
NO significance machinery needed, but definitions frozen before looking").

**The registered statistic** is the **funnel-verdict partition**, defined as:

For denominator D ∈ {A, B}:
```
recall_fired(D)         = count(FIRED events in D)       / |D|
recall_near_missed(D)   = count(NEAR-MISSED events in D) / |D|
recall_rejected(D)      = count(REJECTED events in D)    / |D|
recall_never_triggered(D) = count(NEVER-TRIGGERED events in D) / |D|
```
These four fractions sum to 1.0 by construction.

**Wilson CIs:** each fraction is reported with a 95% Wilson score interval (z = 1.96) per the
`engine/qledger.wilson_ci_low` implementation. The Wilson interval is used (not normal-approx)
because n is finite and fractions may be near 0 or 1.

**Effective-n:** denominator sizes |A| and |B| are printed beside every fraction. If
|A| < 100 or |B| < 100 in the primary window, the report flags this as thin-denominator
and the quarterly recall number is reported with an explicit low-confidence stamp.

---

## Kill vs ship decision rule

Because there is no significance threshold, the study cannot be "killed." The study always
ships a descriptive report. However, the following conditions trigger escalation to Fable
before the quarterly recall number is published:

**Escalate if:**
- `recall_fired(A) < 0.05` AND `recall_near_missed(A) < 0.10` — i.e., the funnel touches
  fewer than 15% of durable-low events in any way. This is the R7 additive-lanes concern:
  a board with near-zero recall has been precision-stacked to irrelevance.
- `|A| < 50` or `|B| < 50` in the primary window — the denominator is too thin to be
  informative and the measurement memo era table likely needs revision.
- The NEVER-TRIGGERED fraction exceeds 0.60 for either denominator — most significant events
  were never evaluated by the funnel; this is a structural gap requiring a new PREREG before
  any coverage fix is built.

**Escalate does NOT kill the study** — the report is published regardless. Escalation flags
the result for Fable review before any downstream action is taken.

---

## Standing quarterly recall number (KPI definition, frozen)

The quarterly recall number is defined as follows and is the canonical metric that appears
in all future program status reports, PR descriptions, and board summary surfaces:

```
QRN_A = recall_fired(Denominator A, primary window, trailing 252 trading days)
QRN_B = recall_fired(Denominator B, primary window, trailing 252 trading days)
```

Both numbers are produced by rolling the above census to the trailing 252-bar window, using
only primary-era rows, with the same durable-low and +20%/60d definitions above. The
quarterly production run uses only the replay artifact (which must have been refreshed within
the prior 63 trading days for the QRN to be considered current).

The QRN is a FIRE-only fraction (NEAR-MISSED and REJECTED are reported separately). It answers
the question: "Of all objectively significant lows / large moves in our universe in the past
year, what fraction did the funnel fire on?" It does NOT answer whether those fires were good
entries — that is P1.1–P1.3's domain.

The QRN does NOT have a target threshold registered here. A future PREREG may register a
target if a program decision depends on a specific coverage level.

---

## Report contract

`research/entry_intel/P1_4_RECALL_REPORT.md` with:

1. Primary-window denominator sizes |A| and |B| with breakdown by year.
2. Funnel-verdict partition table (all four categories, Wilson CIs, effective-n) for both
   denominators.
3. Sub-breakdown tables: near-miss by reason (T3), rejected by reason (T4), fired by tier (T5).
4. Overlap count: events appearing in both A and B.
5. Survivor-stamp context appendix: partition fractions on survivor-stamped rows (clearly
   labeled non-verdict-grade, for directional context only).
6. Era boundary disclosure: exact date range of the primary window per the Measurement Memo.
7. Denominator-depth flag: thin-denominator stamp if |A| or |B| < 100.
8. Escalation flags: any of the three escalation conditions triggered.
9. Standing quarterly recall number (QRN_A, QRN_B) for the trailing 252 bars.
10. Measurement-limitations section: ATR waiver (if applicable), deduplication counts,
    never-triggered disambiguation notes.
11. Trial ledger confirmation: confirmation that T1–T5 were logged to the trial ledger
    (`engine/trial_ledger`, family `p1_4_recall_audit`) before any computation.

---

## Plain-English box

> **In plain English:** imagine the funnel as a net. The precision studies (P1.1–P1.3) test
> whether the fish it catches are good fish. This study counts how many fish swam through the
> net at all — the ones it caught, the ones it nearly caught, the ones it consciously rejected,
> and the ones it never even saw. The two yardsticks are: every time a stock made a genuine
> durable low (a low that held for 60 trading days without being undercut by 5%), and every
> time a stock went up 20%+ over the next 60 trading days. Against both yardsticks, we split
> the funnel's behavior into four buckets: fired (it rang the bell), near-missed (it tried but
> one condition blocked it), rejected (it evaluated and said no), or never-triggered (it didn't
> even look). No single bucket is "bad" on its own — a high rejection rate might be correct
> discipline. But a very high never-triggered rate is a structural gap: the funnel is being
> precision-stacked toward a tiny slice of the universe and missing most of the action. This
> census runs quarterly so the program never claims good entries without also showing what it
> passed on.

---

## Inherited law and constraints

Per §3 of the masterplan, the following constraints apply and cannot be weakened by a runner:

- PREREG is immutable once committed. Results are added to `P1_4_RECALL_REPORT.md` only;
  this file is never edited to accommodate observed outcomes.
- Denominator event detection uses the canonical PIT price panel (Source 1, declared in the Data source section) as an explicit narrow exception to the former "replay-only" clause. All verdict lookups use the replay artifact (Source 2) only. No other data fetches are permitted during the study run.
- The 5-bar deduplication window and 0.95 undercut tolerance for Denominator A are frozen.
  Changing either parameter requires a new registered trial (T6+) and a §8 row.
- No significance machinery (p-values, BH-FDR correction) is applied to the recall fractions.
  Wilson CIs are descriptive only.
- The quarterly recall number (QRN_A, QRN_B) definitions above are frozen. Future program
  status reports must use exactly these definitions or explicitly note the version change.
- Ruling R8: this study does not execute before the P0.1 replay golden test passes and the
  P0.2 PIT audit is clean.
- Ruling R9: the replay artifact lives in `data/replay/` (canonical checkout, not committed
  to git). If the replay artifact is absent, this study waits; it does not substitute any
  other data source.

---

## §APPROVAL — Fable, 2026-07-05

**STATUS: APPROVED FOR EXECUTION** (supersedes the DRAFT header above; R8 gates cleared: replay golden exact-match on full ledger + PIT re-audit CLEAN).

Binding v1.1 conformance (P0_MEASUREMENT_MEMO §6, in addition to the v1.0 checklist):
1. Effective verdict window = **2022-06-30 → 2026-07-02** (250-bar Massive warmup; the nominal 2021-07-06 window does not exist in the ledger).
2. Canonical input = `data/replay/replay_boarded.parquet` ONLY. Never read the `replay_2*.parquet` parts glob.
3. Frozen substrate reference (post PR #1466 sector backfill): 961,656 rows; 57,640 fires (49,939 verdict-grade); 17,587 near-misses; 886,429 rejections; 25,783 fire episodes; rs_sector_quartile fill 92% on fires (current-GICS snapshot, 928-label constituents map). Baseline terminal states on verdict-grade fires: STOPPED 31,372 / CLEAN_LIFTOFF 16,549 / CUSHIONED 1,975 / DEAD_MONEY 43.
4. `board_rank_unresolved` rows receive descriptive treatment only — never keep/demote/flip verdicts (memo §6.3).
5. Any concordance citation uses the on-disk 98.5%/12-name value (memo §6.4).

Execution contract: outputs to `research/entry_intel/p1_runs/<study_id>/` (analysis script + RESULTS.md + results.json). Deviation from the registered grid = new recorded trial per species law; ambiguity = blocker report to Fable, never improvisation.
