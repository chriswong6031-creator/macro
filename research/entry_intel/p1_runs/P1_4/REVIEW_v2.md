# P1.4 Recall Audit — ROUND-2 CONFORMANCE REVIEW (Opus reviewer, fresh)

**Reviewer stance:** fresh round-2 reviewer, default skeptical. I audited **artifacts, not reports**:
`run_P1_4_v2.py`, `RESULTS.md`, `results.json` against the approved PREREG (`P1_4_RECALL_PREREG.md`,
§APPROVAL binding), the P0 Measurement Memo era law (v1.0 + §6 v1.1), and the bouncing `REVIEW.md`.
I re-derived every headline number with a **from-scratch reimplementation** (my own denominator detection,
partition, Wilson, QRN — not reusing the runner's functions) reading only
`data/replay/replay_boarded.parquet` + `data/massive_stock_day/`. I additionally re-executed the runner's
own `run_P1_4_v2.py` to a scratch output dir and diffed its outputs against the shipped artifacts.

**FINAL VERDICT: CONFORMANT.** The round-1 BLOCKING defect is demonstrably dead. The corrected mechanism
(verdict lookup on `verdict_grade==True` only; in-universe membership on full replay presence) reproduces
exactly under two fully independent code paths. All ten-plus headline numbers, both denominators, the
overlap, every sub-breakdown, both QRN cells, and every Wilson CI reproduce to the unit. RESULTS.md leads
with the verdict, carries the 'Round-1 defect and fix' section, the reconciliation table, and the
plain-English box (with a round-2 note). Two carried-forward ADVISORIES (one framing nuance, one
reproducibility hazard); neither blocks.

---

## Per-check results

### CHECK 1 — Round-1 BLOCKING defect is dead (verify v2 code + reproduce mechanism): **PASS**

The round-1 defect was: `build_verdict_lookup()` was fed the full `rdf` (all 961,656 rows), counting the
127,389 `verdict_grade==False` (= `horizon_censored==True`) rows as *resolved* FIRED/NEAR/REJECTED verdicts,
so the NEVER-TRIGGERED bucket was zero by artifact.

**Fixed in v2 code** (`run_P1_4_v2.py`):
- `load_replay()` (L178-182) constructs a `primary` frame filtered to `verdict_grade==True` AND the primary
  window, and this frame is what `main()` (L817) passes as the *lookup* source to `build_verdict_lookup`.
- `build_verdict_lookup(vg_df, full_rdf)` (L200-245) builds the RESOLVED-verdict lookup **only** from
  `vg_df` (verdict-grade), while in-universe candidate membership is built from `full_rdf` presence
  (PREREG cond-4 "appears as a candidate row … any verdict"). An event whose (ticker,date) is in-universe
  but has no verdict-grade lookup entry is honestly counted NEVER-TRIGGERED (`partition_events`, L378-397).

**Reproduced the mechanism myself on the full grid** (independent reimplementation), running the partition
under BOTH lookups:

| Method | Denom A (fired/near/rej/never) | Denom B (fired/near/rej/never) |
|---|---|---|
| Round-1 defective (full-rdf lookup), my recompute | 21 / 5 / 8,216 / **0** | 1,414 / 451 / 23,680 / **0** |
| Round-2 corrected (vg-only lookup), my recompute | 20 / 5 / 7,575 / **642** | 1,308 / 414 / 21,542 / **2,281** |
| Runner v2 shipped (RESULTS.md / results.json) | 20 / 5 / 7,575 / **642** | 1,308 / 414 / 21,542 / **2,281** |

Both my recompute columns match REVIEW.md CHECK-3 to the unit (round-1 method **and** vg-correct method).
The v2 code uses the vg-only lookup → the defect is dead and the NEVER-TRIGGERED bucket is surfaced honestly.
Partition sums verified: A → 8,242; B → 25,545 (exact denominators).

**Runner-code re-execution:** I ran the shipped `run_P1_4_v2.py` verbatim (OUT_DIR redirected to a scratch
dir) and diffed: `RESULTS.md` is **byte-identical** to the shipped file; `results.json` is identical modulo
`run_date`. The shipped artifacts are the genuine product of the shipped code — no hand-editing.

### CHECK 2 — Calibration control (P1.4: spot-verify reconciliation deltas): **PASS**

Every reconciliation delta in RESULTS.md §"Round-1 vs round-2" independently reproduced from the parquet:

| Delta | RESULTS claim | My recompute | Attribution verified |
|---|--:|--:|---|
| A REJECTED 8,216→7,575 | −641 | −641 | censored rejections removed from lookup |
| A NEVER 0→642 | +642 | +642 | defect surface |
| B REJECTED 23,680→21,542 | −2,138 | −2,138 | censored rejections removed |
| B NEVER 0→2,281 | +2,281 | +2,281 | defect surface |
| A FIRED 21→20 / B FIRED 1,414→1,308 | −1 / −106 | −1 / −106 | censored fires removed |
| QRN_A 3→2 fires / QRN_B 253→149 fires | −1 / −104 | −1 / −104 | censored fires removed from trailing-252 |

Root-cause census verified: all 961,656 (ticker, signal_date) pairs are **unique** (0 duplicates);
127,389 are censored-only (`max(verdict_grade)` over the pair is False); `verdict_grade==False ≡
horizon_censored==True` **exactly** (XOR = 0 rows). Censored `verdict_type` split rejection=117,154 /
fire=7,701 / near_miss=2,534 matches results.json exactly. Every headline delta is attributable to the
single root cause the fix targets.

### CHECK 3 — Trial-grid / era-stamp / n-floor / INSUFFICIENT-POWER discipline: **PASS**

- **Trial grid:** exactly T1–T5 executed, all in the PREREG capped grid (m=5). `post_hoc_trials: []`.
  QRN and escalation are PREREG-registered outputs, not new trials. No unregistered trial presented.
- **Era/window:** effective window `2022-06-30 → 2026-07-02`, matching §APPROVAL v1.1 clause 1. Verified
  the parquet's own `signal_date` min/max is exactly `2022-06-30 → 2026-07-02` (0 rows outside).
- **Canonical input:** `replay_boarded.parquet` only; no `replay_2*.parquet` parts glob (§APPROVAL clause 2). ✓
- **Survivor stamp:** `survivor_bias` is uniformly `False` across all 961,656 rows (verified). Survivor
  appendix present and correctly declares zero stamped rows; mandatory stamp text (memo §2.3, 31.3% figure)
  printed. ✓ No stamped-row mixing (none exist).
- **Censored discipline (the fix):** 127,389 `horizon_censored` rows are excluded from the verdict lookup
  and tracked separately (per-type census printed) — this is exactly the §5 checklist item the round-1
  run violated in fact while claiming compliance. Now genuinely satisfied.
- **BH family:** PREREG registers NO significance machinery; Wilson CIs are descriptive proportion
  intervals, not a multiplicity concern. None claimed. Conformant (N/A).
- **n-floors:** thin-denominator floors (|A|<100, |B|<100) and escalation floors (|A|<50, |B|<50)
  implemented; both denominators (8,242 / 25,545) clear all floors. No thin/low-confidence stamp required
  and none borrowed. `insufficient_power_cells` not applicable — census cells are full-population, not
  under-powered. No pre-2021 borrowing (no such rows exist). ✓

### CHECK 4 — Independent recompute of ≥3 headline numbers: **PASS (10+ reproduced exactly)**

From-scratch reimplementation against `replay_boarded.parquet` + Massive store (my own event detection,
dedup, Wilson, QRN — zero reuse of runner functions):

| Quantity | Runner | My independent recompute | Match |
|---|--:|--:|:--:|
| Denom A n | 8,242 | 8,242 | ✓ |
| Denom B n | 25,545 | 25,545 | ✓ |
| Overlap A∩B | 943 | 943 | ✓ |
| Year breakdown A/B | (5 yrs each) | identical (2022:1141… / 2022:3329…) | ✓ |
| A partition 20/5/7,575/642 | — | 20/5/7,575/642 | ✓ |
| B partition 1,308/414/21,542/2,281 | — | 1,308/414/21,542/2,281 | ✓ |
| A NEVER 7.79% / B NEVER 8.93% | — | 7.79% / 8.93% | ✓ |
| A FIRED 0.24% / B FIRED 5.12% | — | 0.24% / 5.12% | ✓ |
| Wilson: A-fired [0.16,0.37] B-fired [4.86,5.40] | — | identical | ✓ |
| Wilson: A-never [7.23,8.39] B-never [8.59,9.29] | — | identical | ✓ |
| T3 near-miss A {fresh:2,ntv:3} / B {ntv:231,fresh:183} | — | identical | ✓ |
| T4 rejected A {no_signal:7136,ntv:268,hyg:117,brc:54} | — | identical | ✓ |
| T4 rejected B {no_signal:18682,ntv:2246,brc:424,hyg:190} | — | identical | ✓ |
| T5 fired-tier A {T1:13,T2:7} / B {T2:636,T1:621,T3:51} | — | identical | ✓ |
| QRN_A 2/1,713 (0.12%) / QRN_B 149/5,706 (2.61%) | — | identical | ✓ |

Escalation math independently verified: ESC-1 fires (fired%+near% = 0.303% « 15%); ESC-2 (n<50) and
ESC-3 (never>60%) correctly do NOT fire. Universe = 1,007 tickers, all present in the Massive store
(0 missing) — corroborating `never_absent = 0`.

### CHECK 5 — RESULTS.md honesty surface: **PASS**

- Line 1 is the verdict-grade title; `## Verdict (lead)` precedes any partition table. ✓
- `## Round-1 defect and fix` section present, with the round-1-vs-round-2 reconciliation table. ✓
- `## In Plain English` box present, matches PREREG text, plus an honest **Round-2 note** explaining the
  censored-row error and the ~8-9% corrected never-triggered rate. ✓
- ESC-1 escalation surfaced prominently under a dedicated header. ✓
- Survivor stamp text + survivor appendix (declaring zero stamped rows) present. ✓
- Measurement-limitations section documents the censored-row handling, ATR waiver, dedup, forward-bar
  exclusion. ✓

---

## Findings (tagged)

- **[ADVISORY — framing] `never_absent = 0` is a structural identity, not an empirical discovery.**
  The denominator's in-universe gate requires full-replay presence (`replay_pairs`), so any
  never-triggered event necessarily sits on a pair that IS present in replay but absent from the
  verdict-grade lookup — i.e. a censored-only pair. Therefore `never_absent` **cannot** be > 0 under this
  gate; it is 0 by construction (verified: 834,267 vg pairs + 127,389 censored-only = 961,656 total, and
  events are gated on full presence). The runner report's phrasing that "100% censored-only, 0 absent …
  refines the review's framing precisely," and RESULTS.md's "or never produced a candidate row at all,"
  present a structurally-impossible branch as an empirical outcome. This does **not** affect any count,
  fraction, CI, or the verdict — the never-triggered total (642 / 2,281) and its correct interpretation
  (in-universe candidate, horizon-censored, no settled verdict) are right. It is a wording over-claim only.
  Recommend a one-line note that the absent branch is empty by construction of the in-universe gate.

- **[ADVISORY — reproducibility, carried from round 1] Ephemeral `/tmp` import path persists.**
  `run_P1_4_v2.py` L58/L104-108 imports `split_adjust` from `/tmp/ei-replay-run/scripts/replay_standout_pipeline.py`,
  an ephemeral worktree path. It resolved at review time (I executed the script successfully and the file
  is present), so results are auditable now, but a re-run after `/tmp` is cleared will fail the import.
  Recommend vendoring `split_adjust` or pinning a canonical repo path. Non-blocking (round-1 review already
  flagged this as ADVISORY; the fix did not address it, which is acceptable for a defect-corrected re-run).

- **[ROBUST — no change needed] The corrected mechanism and every number are validated.** The universe /
  lookup split (universe = full presence, lookup = verdict-grade) is the *correct* reconciliation of the
  round-1 review's two constraints: it preserves the review-validated denominators (8,242 / 25,545 — a
  verdict-grade-only universe would have shrunk them below the certified values) AND surfaces the
  never-triggered bucket. The runner's choice is more faithful to PREREG cond-4 ("appears as a candidate
  row … any verdict") than the review's shorthand ("build the universe from verdict_grade==True"), and it
  keeps the denominators the review explicitly said "stand." Confirmed correct.

- **[ROBUST] ESC-1 escalation stands under corrected numbers.** fired+near on Denom A = 0.303% « 15%;
  the R7 precision-stacking concern is real and correctly escalated. The central finding (near-zero
  durable-low recall) is unchanged from round 1 and correct.

---

## Recompute log (independent, this review)

1. Parquet foundation — 961,656 rows; all `survivor_bias==False`; 834,267 vg / 127,389 censored;
   `verdict_grade==False ≡ horizon_censored==True` (XOR = 0). ✓
2. Pair uniqueness — 0 duplicate (ticker, signal_date); 127,389 censored-only pairs. ✓
3. Denominators from scratch — A 8,242 / B 25,545 / overlap 943; year breakdown identical. ✓
4. Partition under vg-only lookup — A 20/5/7,575/642; B 1,308/414/21,542/2,281 (sums to n). ✓
5. Partition under full-rdf lookup (round-1 method) — A 21/5/8,216/0; B 1,414/451/23,680/0 (matches the
   bounced round-1 and REVIEW.md CHECK-3 round-1 column). ✓ — defect-death demonstrated.
6. Wilson CIs (A/B fired, A/B never, QRN_A, QRN_B) — reproduced exactly. ✓
7. T3/T4/T5 sub-breakdowns — reproduced exactly. ✓
8. QRN window `2025-07-15 → 2026-07-02` (busday_offset −252) and cells (A 2/1,713; B 149/5,706) — exact. ✓
9. Escalation logic (ESC-1 fires; ESC-2/ESC-3 do not) — reproduced. ✓
10. Ran the shipped `run_P1_4_v2.py` verbatim → RESULTS.md byte-identical, results.json identical modulo
    run_date. ✓
11. Universe 1,007 tickers, 0 missing from Massive → corroborates `never_absent = 0` (and confirms it is
    structural). ✓

---

## Disposition

**CONFORMANT.** The round-1 BLOCKING defect (verdict lookup built from non-verdict-grade rows) is
demonstrably dead: the corrected lookup runs on `verdict_grade==True` only, the NEVER-TRIGGERED bucket is
honestly surfaced at 7.79% (Denom A, 642) / 8.93% (Denom B, 2,281), and every headline number, denominator,
overlap, sub-breakdown, QRN cell, and Wilson CI reproduces exactly under a fully independent from-scratch
recompute and under re-execution of the runner's own code. Trial grid (T1–T5), era/stamp discipline,
censored-exclusion, n-floors, and the descriptive-census (no-BH) treatment are all conformant. RESULTS.md
leads with the verdict, contains the defect/fix section and reconciliation table, and carries the
plain-English box with an honest round-2 note. Two ADVISORIES (the structurally-guaranteed `never_absent=0`
framing over-claim; the persisting ephemeral `/tmp` import path) do not affect any result or the verdict
and do not require a re-run.
