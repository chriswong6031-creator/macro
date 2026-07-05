# P1.4 Recall Audit — CONFORMANCE REVIEW (Opus reviewer)

**Reviewer stance:** default skeptical; audited artifacts (run_P1_4.py, RESULTS.md, results.json) against
the approved PREREG (`P1_4_RECALL_PREREG.md`), the P0 Measurement Memo era law, and the binding §APPROVAL v1.1
clauses. All headline numbers independently recomputed against `data/replay/replay_boarded.parquet` +
`data/massive_stock_day/` with a from-scratch pandas/numpy reimplementation.

**FINAL VERDICT: DEVIATIONS.** One BLOCKING conformance failure invalidates the report's lead claim
("NEVER-TRIGGERED = 0 for both denominators"). The denominators (A=8,242, B=25,545, overlap=943) and the
core escalation verdict (ESC-1) are correct and reproduce exactly; but the funnel-verdict partition was
computed against the FULL replay (including `verdict_grade==False` / `horizon_censored` rows), in direct
violation of the program's primary-statistics law. When corrected, NEVER-TRIGGERED is ~8% (not 0%), and the
report's central narrative ("coverage gap is in momentum gates not universe reach") is not supported.

---

## Per-check results

### CHECK 1 — Trial-grid adherence: **PASS**
All executed trials (T1–T5) appear in the PREREG capped grid (§Capped trial grid, m=5). No unregistered
trial is presented as primary. `post_hoc_trials: []` in results.json and "Post-hoc trials: none" in RESULTS.md.
QRN and escalation flags are PREREG-registered outputs (§QRN, §Kill-vs-ship), not new trials. Grid conformant.

### CHECK 2 — Era / stamp discipline: **FAIL (BLOCKING)**
- Effective window `2022-06-30 → 2026-07-02` is correctly stated and matches §APPROVAL v1.1 clause 1. ✓
- Canonical input is `replay_boarded.parquet` only; no `replay_2*.parquet` glob read. ✓ (§APPROVAL clause 2)
- `survivor_bias` is uniformly `False` across all 961,656 rows (verified); the survivor appendix and stamp
  text are present and correctly declare "no stamped rows." ✓
- **VIOLATION:** primary statistics are NOT filtered to `verdict_grade==True`. `build_verdict_lookup()`
  (run_P1_4.py L160, called at L745 with the full `rdf`) constructs both the verdict lookup and the
  in-universe membership set from ALL 961,656 rows, including the 127,389 `verdict_grade==False` rows —
  which are exactly the `horizon_censored==True` rows (verified: the two flags are identical partitions).
  The program law states "primary statistics on verdict_grade==True rows only," and the PREREG §5 checklist
  requires "`horizon_censored` rows excluded per-horizon." The RESULTS.md §1 even *claims* "`horizon_censored`
  rows excluded per-horizon per memo §1.1(2)" — but the code does not do this. `load_replay()` computes a
  `primary` (verdict-grade) frame but it is never used for the lookup or universe; only the raw `rdf` feeds
  the partition.

### CHECK 3 — Independent recompute (≥3 headline numbers): **FAIL — mismatch >1% on the lead statistic**
Independent from-scratch reimplementation (split_adjust from the same harness; PREREG denominator definitions):

| Quantity | Runner | My recompute (runner's method) | My recompute (PREREG-correct: vg==True) |
|---|---|---|---|
| Denom A n | 8,242 | **8,242 ✓** | 8,242 |
| Denom B n | 25,545 | **25,545 ✓** | 25,545 |
| Overlap A∩B | 943 | **943 ✓** | 943 |
| A: fired/near/rej/never | 21 / 5 / 8,216 / **0** | 21 / 5 / 8,216 / 0 ✓ | 20 / 5 / 7,575 / **642** |
| B: fired/near/rej/never | 1,414 / 451 / 23,680 / **0** | 1,414 / 451 / 23,680 / 0 ✓ | 1,308 / 414 / 21,542 / **2,281** |
| Wilson CIs (A fired, B fired, QRN_A, QRN_B) | as reported | **exact match ✓** | — |

- Denominators, overlap, year breakdown, and all Wilson math reproduce **exactly** — the event-detection
  and CI machinery are correct.
- The **lead statistic** ("NEVER-TRIGGERED = 0 for both denominators") is an artifact of Check-2's violation.
  Under the PREREG-correct verdict-grade filter, NEVER-TRIGGERED = **642 (7.8%) for Denom A** and
  **2,281 (8.9%) for Denom B** — a deviation of +7.8 / +8.9 percentage points, far exceeding the >1% flag
  threshold. Denom B FIRED also drops 5.54% → 5.12% (1,414 → 1,308), a >1% relative shift.
- Mechanism confirmed: all 961,656 (ticker, signal_date) pairs are unique, and 127,389 are "censored-only"
  (max `verdict_grade` over the pair is False). Under the law these carry no verdict-grade verdict; the runner
  instead assigned them REJECTED/FIRED/NEAR-MISSED. Removing them surfaces them as NEVER-TRIGGERED (event in
  denominator, no verdict-grade replay row) — the exact category the study exists to measure. This is not a
  rounding artifact; it is the study's headline coverage metric being computed on the wrong row set.

### CHECK 4 — BH family: **PASS (N/A)**
PREREG registers NO significance machinery (§Primary statistic: "Wilson CIs are confidence intervals for a
proportion, not hypothesis tests — not a multiplicity concern"; §Inherited law: "No significance machinery
… is applied"). No BH family is required and none is claimed. No sign-stability halves registered. Conformant.

### CHECK 5 — n-floors / INSUFFICIENT-POWER: **PASS**
Thin-denominator floors (|A|<100, |B|<100) and escalation floors (|A|<50, |B|<50) are implemented
(run_P1_4.py L524, L448). Both denominators (8,242 / 25,545) clear all floors, so no INSUFFICIENT-POWER or
thin stamp is required, and none is borrowed. `insufficient_power_cells: []` is correct. Note: this holds
under the corrected numbers too (642 / 2,281 never-triggered still leaves n well above floors). Conformant.

### CHECK 6 — Honesty surface: **PASS (with advisory)**
- RESULTS.md leads with a "Verdict (lead)" section. ✓
- Plain-English box present and matches the PREREG text. ✓
- Escalation flag surfaced prominently. ✓
- Survivor stamp text present; survivor appendix present and correctly declares zero stamped rows. ✓
- `board_rank_unresolved`: not applicable to this descriptive census (memo §6.4 concerns concordance, not
  recall); `board_rank_cutoff` appears only as a descriptive rejection-reason sub-count, treated descriptively. ✓
- ADVISORY: the honesty of the *surface* is fine, but the lead claim it honestly surfaces is wrong (Check 3).
  The report also asserts in §1 that horizon_censored rows were excluded — a statement contradicted by the code.

---

## Findings (tagged)

- **[BLOCKING] Verdict lookup + universe built from non-verdict-grade rows.** run_P1_4.py L745 passes the full
  `rdf` to `build_verdict_lookup`; the 127,389 `verdict_grade==False` (= `horizon_censored==True`) rows are
  counted as resolved verdicts. Fix: build the lookup and in-universe set from `rdf[rdf.verdict_grade==True]`
  (the `primary`-equivalent frame). Re-run required. Corrected headline: NEVER-TRIGGERED ≈ 7.8% (A) / 8.9% (B),
  FIRED(B) ≈ 5.12%.
- **[BLOCKING] Lead narrative unsupported.** The runner report's headline ("NEVER-TRIGGERED = 0 for both
  denominators — the funnel evaluates every in-universe name daily; coverage gap is in momentum gates not
  universe reach") is falsified by the correct filter: ~8% of significant events have no verdict-grade replay
  row. Part of the coverage gap IS in universe/horizon reach (or in events that only ever produced censored
  rows), not solely in momentum gates. RESULTS.md §1's claim that censored rows were excluded is also false.
- **[ADVISORY] Downstream sub-breakdowns inherit the contamination.** T3/T4/T5 (near-miss, rejected, fired-tier)
  are computed on the same full-`rdf` partition; e.g. rejected(A) 8,216→7,575 and rejected(B) 23,680→21,542
  under the correct filter, so the `no_signal` counts and percentages shift. Secondary to the root cause but
  must be regenerated in the re-run.
- **[ADVISORY] Robust results (no change needed):** denominators (8,242 / 25,545), overlap (943), year
  breakdown, Wilson CI implementation, and the ESC-1 escalation verdict all reproduce exactly and survive the
  correction (ESC-1: fired+near on Denom A = 0.30% « 15% under both methods). The study's central finding —
  extreme precision-stacking / near-zero durable-low recall — is real and correctly escalated.
- **[ADVISORY] Reproducibility hazard (non-blocking):** the script imports `split_adjust` from a transient
  worktree path `/tmp/ei-replay-run/scripts/replay_standout_pipeline.py` (run_P1_4.py L39/L77). This path is
  ephemeral; a future re-run after /tmp is cleared will fail the import. Recommend vendoring split_adjust or
  pinning a canonical repo path. (It resolved correctly at review time, so results are auditable now.)

---

## Recompute log (independent, this review)
1. Denominator A/B sizes and overlap — reproduced EXACTLY (8,242 / 25,545 / 943).
2. Partition under runner's method (full rdf) — reproduced EXACTLY (A 21/5/8216/0; B 1414/451/23680/0).
3. Partition under PREREG-correct method (verdict_grade==True) — A 20/5/7575/**642**; B 1308/414/21542/**2281**.
4. Wilson CIs for A-fired, B-fired, QRN_A, QRN_B — reproduced EXACTLY.
5. Confirmed 127,389 censored-only (ticker,date) pairs = the flip source; verdict_grade==False ≡ horizon_censored==True.

**Disposition:** DEVIATIONS. The runner must re-run with the verdict-grade filter applied to the verdict
lookup and universe, then re-issue T1–T5, the NEVER-TRIGGERED lead, and the coverage narrative. The
escalation verdict (ESC-1) and denominators stand.
