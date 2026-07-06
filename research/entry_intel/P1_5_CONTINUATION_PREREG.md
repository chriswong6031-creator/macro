# P1.5 Continuation Partition — Pre-Registration

**STATUS: APPROVED — Fable 2026-07-05 (see §APPROVAL at end; original draft-gate text follows) (ruling R8: does not execute before replay golden test + PIT audit are clean)**
**Revision:** 2026-07-04 — blocking fix applied (P1.5-B1: K3 era-fallback escape hatch replaced with HALT-and-blocker clause, aligning with sibling drafts) + advisory fix (P1.5-A1: H-MISLABEL second disjunct tightened to prevent H-UNDERRANK from being unreachable) + era law absorbed from P0_MEASUREMENT_MEMO.md v1.0; §5 conformance checklist reference added.

*2026-07-04 · Entry Intelligence program (research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §5/P1.5,
§2 R1–R10) · registered BEFORE first run (this file's merge commit precedes the report).*

---

## 0. Question under test

The production board gates and ranks entries using bottoming-alignment tiers (PRIME / ARMED /
APPROACHING). ARMED explicitly admits names where "the weekly has already turned up (rising)" —
meaning some continuation setups (names already in a weekly uptrend, not fresh-from-bear) enter
the board today rather than being excluded. The question is: **are these continuation-profile fires
genuinely good entries, mislabeled as bottoming entries, or underranked relative to their actual
outcome distribution?**

Three hypotheses (exactly one governs the decision rule; §4 maps each to its fix):

- **H-EXCLUDE:** continuation-profile fires have materially worse terminal-state profiles than
  freshly-turned bottoming fires; the board should not surface them in the bottoming lane (they
  belong in a separate continuation clade, or not at all).
- **H-MISLABEL:** continuation-profile fires perform comparably or better, but they are currently
  labelled and ranked as if they were bottoming entries — correct action is to relabel them into an
  explicit continuation lane without changing the gate.
- **H-UNDERRANK:** continuation-profile fires perform well but the rank formula underweights them
  (because quality scoring penalises the `rising` weekly phase at 0.35 vs 1.0 for `bear_recovering`)
  — correct action is to adjust the rank formula, not the gate.

This study measures, never assumes, which hypothesis holds.

---

## 1. Data source

**Data source: `data/replay/standout_replay.parquet` ONLY.**

The replay artifact is the canonical source for all P1 studies. Reads are by absolute path.
No live production data, no re-running the gate, no supplemental fetches.

Replay columns consumed:
- `ticker`, `date`, `verdict` (fire / near-miss / rejection), `tier` (PRIME/ARMED/APPROACHING),
  `weekly_phase` (logged at signal time from `engine/cycles.py` mtf_alignment),
  `rs_vs_sector_quartile` (logged at signal time — rank of name's trailing RS within its sector,
  1=strongest, 4=weakest), `above_200dma` (bool, logged at signal time from `signal_gate` /
  replay frozen features), `sector`, `alignment_quality`, `ext_z`, `knife_z`.
- Grading columns: `terminal_state` (STOPPED / DEAD_MONEY / CUSHIONED / CLEAN_LIFTOFF),
  `fwd_ret_5d`, `fwd_ret_10d`, `fwd_ret_21d`, `fwd_ret_63d`, `fwd_mae_21d`, `fwd_mfe_21d`,
  `episode_cluster_id`, `survivor_biased` (stamp), `era`.

If `rs_vs_sector_quartile` or `above_200dma` are absent from the replay artifact at execution
time (the harness spec says they are logged; absence = a replay harness bug, not a study design
choice): **HALT and report as a blocker**. Do not impute or reconstruct.

---

## 2. Era handling

**Memo citation (mandatory):** `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)`. Every run prints this citation in the preamble.

**Primary window:** `2021-07-06 → last-full-replay-date` — the sole verdict-grade era per the P0 Measurement Memo §1 era table (STRICT-WINS ruling). The former PREREG placeholder "2015-01-01" is superseded; the memo §1.2 explicitly rejects a 2015 boundary. All verdict-grade statistics (terminal-state proportions, Δ, BH q-values, sign-stability) are computed exclusively on UNSTAMPED rows (`survivor_biased = False`) in this window — i.e., rows with `signal_date ≥ 2021-07-06` whose price series is Massive-sourced and whose full grading horizon falls within the replay window.

**Survivor-stamped rows in context appendix only.** Any row where `survivor_biased = True` is excluded from the primary verdict partitions and printed in a clearly-labelled Appendix B ("PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE"). No verdict metric is computed on survivor-stamped rows. The per-name coverage ≥ 50% gate (former PREREG clause) remains as a hygiene filter *within* the 2021+ verdict window per memo §2.2; it does not unstamp pre-2021 rows.

If `P0_MEASUREMENT_MEMO.md` does not exist at execution time, the study **HALTS** and returns a blocker report — it does not self-select an era or run on a provisional window. This aligns with P1.1/P1.2/P1.3/P1.4, which all HALT on this condition.

**Pre-replay era (before 2012):** no rows from P1.5; the replay does not extend there. No extrapolation.

**§5 conformance checklist** (P0_MEASUREMENT_MEMO.md §5 — confirmed at run start):
- [ ] Cites `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` in preamble.
- [ ] Primary window = `2021-07-06 → last-full-replay-date`.
- [ ] Verdict-grade statistics on `survivor_biased = False` rows only.
- [ ] Confirms via per-row source stamp that unstamped rows are Massive-sourced.
- [ ] All pre-2021 rows stamped, routed to labeled context appendix, excluded from BH family, sign-stability, n-floors, and all H-EXCLUDE/H-UNDERRANK/H-MISLABEL decisions.
- [ ] `horizon_censored` rows excluded per-horizon, tracked separately.
- [ ] Mandatory stamp text printed with era census missing-fraction.
- [ ] Returns INSUFFICIENT-POWER (honest null) if unstamped episode-clustered n floor < 100 (K1).

---

## 3. Fire set

**Fires only** (verdict == 'fire'). Near-misses and rejections are NOT included — this study
grades differential quality within admitted fires, not the gate itself (P1.2 owns gate P&L).

Within fires, the primary partition separates:

- **ARMED-admitted continuation fires:** `tier == 'ARMED'` AND `weekly_phase == 'rising'`
  (the subpopulation where ARMED admits a continuation-profile name — weekly already turned up).
  This is the explicit ARMED-tier nuance from masterplan §1.
- **PRIME fires:** `tier == 'PRIME'` AND `weekly_phase in {'bear_recovering', 'basing', 'turning'}`
  (fresh-from-bear; the canonical bottoming entry). Reference arm.
- **Other ARMED:** `tier == 'ARMED'` AND `weekly_phase != 'rising'` (edge case; printed as a
  diagnostic aside, not a primary partition).

These three are mutually exclusive and exhaustive within PRIME+ARMED fires.

**Horizon class:** rotational (declared; frozen at registration). Primary verdict metric is
`clean8_21` (≥+8% before −5% within 21 trading days). Positional grid (`clean15_126`) printed
as context only, never the verdict.

---

## 4. Partition axes (capped trial grid)

All axes evaluated on the ARMED-continuation fire subpopulation vs PRIME reference arm.
Each combination below is a registered trial in the trial ledger family `p15_continuation`.

| Trial | Axis | Levels |
|---|---|---|
| T1 | Weekly phase × tier (the primary ARMED-continuation split) | ARMED/rising vs PRIME reference |
| T2 | RS-vs-sector quartile (within ARMED-continuation fires) | Q1 (top RS) vs Q2–Q4 pooled |
| T3 | RS-vs-sector quartile (within ARMED-continuation fires) | Q1–Q2 vs Q3–Q4 |
| T4 | 200DMA side (within ARMED-continuation fires) | above_200dma=True vs False |
| T5 | RS × 200DMA interaction (within ARMED-continuation fires) | Q1+above vs all others (2×2 corner) |

Total registered trials: **m = 5**.

No other knobs are searched. Any post-hoc partition variation is a new §8-recorded trial and
enters a separate registered family.

**BH family:** all five trial p-values are corrected together (Benjamini–Hochberg, m=5).
Promotion requires q ≤ 0.10 on the primary verdict metric per trial after BH correction.

---

## 5. Primary verdict metric and statistics

**Primary metric:** `P(clean8_21)` — proportion of fires in each partition cell reaching ≥+8%
before −5% within 21 trading days. This is a terminal-state proportion, not a return mean;
DSR does not apply (§3 inherited law).

**Exact statistics:**

1. **Cell proportions** with Wilson 95% confidence intervals (z=1.96), computed separately per
   partition arm.
2. **Pp-spread** between ARMED-continuation arm and PRIME reference arm:
   `Δ = P(clean8_21 | ARMED-continuation) − P(clean8_21 | PRIME)`.
3. **Episode-clustered p-value:** block bootstrap over `episode_cluster_id` units
   (blocks ≥ 21 trading days = the forward window). Cluster count n_clusters printed;
   effective-n = n_clusters (not fire count). Bootstrap replications ≥ 5,000.
4. **BH-corrected q-value** across the m=5 trial family.
5. **Both-halves sign stability:** split the primary window at midpoint; Δ must carry the
   same sign in both halves. A sign flip in either half = instability flag (printed prominently;
   verdict downgraded from SHIP to CONDITIONAL even if BH passes).
6. **Per-name majority check:** for any positive Δ claim, the majority of individual-name
   P(clean8_21) estimates must agree in direction. Pooled rates are not enough.

**Secondary context metrics (printed, never verdict):** stop-out rate (STOPPED), dead-money
rate (DEAD_MONEY), cushion rate (CUSHIONED), MAE/MFE at 21d, mean forward returns at 5/10/21/63d
(context, not verdict per §3 inherited law), fire counts with effective episode-cluster n.

**Threshold for materiality (pre-registered):** |Δ| ≥ 5 percentage points on P(clean8_21)
constitutes a material differential. Below 5pp with BH q ≤ 0.10 = statistically detectable
but operationally trivial; verdict = H-NULL (no intervention warranted).

---

## 6. Pre-registered decision rule

The decision rule maps the T1 primary result (ARMED-continuation vs PRIME comparison) to one
of three actions. The secondary partition axes (T2–T5) provide diagnostic granularity but do not
override the T1 verdict.

| Outcome | Condition | Decision |
|---|---|---|
| **H-EXCLUDE** | Δ < −5pp AND BH q ≤ 0.10 AND both-halves sign stable AND stop-out rate for ARMED-continuation is materially higher (≥5pp above PRIME) | Exclude → continuation-clade species PREREGs (P2.3): commission PREREG for Leader Reload and Compression Breakout species; these are separate from the bottoming lane. ARMED-continuation fires get a display tag "continuation profile" pending species validation. |
| **H-MISLABEL** | |Δ| < 5pp (not materially different) OR (0 < Δ ≤ +5pp AND BH q ≤ 0.10) | Mislabel → relabel lanes: ARMED-continuation fires get an explicit "continuation" lane label on the board (additive-lanes law R7 — they are NOT removed, they are re-labelled). No gate change. No rank change. |
| **H-UNDERRANK** | Δ > +5pp AND BH q ≤ 0.10 AND both-halves sign stable | Underrank → P3 re-rank inputs: ARMED-continuation is a better cohort than the rank formula implies; the `rising` weekly phase penalty (currently 0.35 vs 1.0 for `bear_recovering` in the quality formula) is a re-rank candidate for P3.2. A separate PREREG is required before any rank-formula change. |
| **H-NULL** | |Δ| < 5pp AND BH q > 0.10 | No material or detectable differential. Both populations grade similarly. No intervention. Status quo. |
| **AMBIGUOUS** | Conflicting signs across both halves, or inconsistent per-name majority | Halt; return structured report to Fable. No mechanical action. |

**Sub-partition diagnostic (T2–T5):** if the T1 verdict is H-EXCLUDE or H-UNDERRANK, the T2–T5
sub-partition results are reported as "where within ARMED-continuation the differential concentrates"
— they inform the design of P2.3 species PREREGs but do not change the T1 ruling.

---

## 7. Kill criteria (checked in order)

- **K1 (thin primary cells):** if the ARMED-continuation fire count in the primary window is
  < 100 episodes (distinct episode_cluster_id) in the primary arm — **HALT**. Report thin-cell
  warning; no verdict issued. Return structured blocker report to Fable. The study has insufficient
  effective-n for any claim.
- **K2 (replay coverage gap):** if `rs_vs_sector_quartile` or `above_200dma` are null in > 20%
  of fire rows — **HALT** and report as a replay harness gap (not a study failure; R8 applies —
  the replay harness itself is the blocker).
- **K3 (era table absent):** if `research/entry_intel/P0_MEASUREMENT_MEMO.md` does not exist at
  execution time — **HALT and return a blocker report.** Do not self-select an era; do not run
  on a provisional window; do not emit any H-EXCLUDE / H-UNDERRANK / H-MISLABEL / H-NULL ruling.
  The memo's bias-bound era table is what makes claims verdict-grade (masterplan P0.2 / §5);
  self-selecting 2015-01-01 violates R8's spirit and the survivorship-honesty law (P1.2 era
  clause: "does not self-select an era"). This aligns K3 with the identical behaviour in
  P1.1 §11, P1.2 era clause, P1.3 §1, and P1.4 era clause.
- **K4 (trial budget exceeded):** if the trial ledger family `p15_continuation` already has
  more than 5 registered trials before this run (i.e., a prior run modified the grid) — **HALT**
  and return structured blocker; the pre-registration has been violated.

---

## 8. What this study does NOT do

- Does not test near-misses or rejections (P1.2 owns gate P&L).
- Does not impose any gate change on the production board (no merge without Fable approval, R8).
- Does not test the trio of washout-proximity / RS-inflection / anti-chase (P1.3 owns those).
- Does not produce a new species. H-EXCLUDE triggers separate PREREGs (P2.3); this study
  is the predicate measurement, not the species itself.
- Does not evaluate APPROACHING fires (too few confirmed entries; backfill-only tier).
- Does not evaluate returns as a verdict — only terminal-state proportions at the declared
  horizon class (rotational, `clean8_21`). Return context is printed but never gates anything.
- Does not apply DSR (proportion metrics, not return series).

---

## 9. ARMED-tier nuance: explicit separation protocol

The masterplan §1 note — "ARMED admits 'weekly already risen' — some continuation flow may
already enter via weekly-already-risen — the partition must separate ARMED-admitted continuation
fires explicitly" — is operationalised here as follows:

The ARMED subpopulation is split by `weekly_phase` at signal time:

- `weekly_phase == 'rising'` → **ARMED-continuation** (the continuation-flow subgroup the
  masterplan flags). This is the primary study arm.
- `weekly_phase in {'bear_recovering', 'basing', 'turning'}` → **ARMED-bottoming** (the early
  weekly-still-turning cases; structurally similar to PRIME but with a later 3-day entry).

The two ARMED subgroups are NEVER pooled in the primary comparison. If the replay logs
`weekly_phase` as null for any ARMED row, that row is excluded from the partition and its count
reported in a data-quality footnote.

---

## 10. Report contract

File: `research/entry_intel/P1_5_CONTINUATION_REPORT.md`

Must include:
- T1 primary comparison table: ARMED-continuation vs PRIME, all six statistics (§5).
- T2–T5 sub-partition tables (diagnostic context).
- Both-halves stability grid.
- Per-name majority check result.
- Coverage / survivor-stamp line: # fire rows, # survivor-biased excluded, # effective clusters.
- Leak-audit section: fill rule (entry = first close strictly after signal date, per §3 inherited
  law, never same-bar); era-table source; known-date mapping for weekly_phase and
  rs_vs_sector_quartile (both logged at signal time in the replay, not look-ahead).
- Decision rule outcome mapping (one of H-EXCLUDE / H-MISLABEL / H-UNDERRANK / H-NULL / AMBIGUOUS).
- §8 row in the masterplan (appended by Fable after Opus verdict review).
- Registry updates to `data/species/registry.json` if P2.3 species PREREGs are triggered.

---

## In plain English

Some names on the buy board are there because their weekly trend already turned up weeks ago —
they are in a continuation move, not at a fresh bottom. We do not know yet whether those names
are good entries, bad entries, or just mislabelled. This study reads the production replay
log and counts outcomes: of the names that entered via the "weekly already rising" path vs the
names that entered with the weekly just turning from a low, what fraction stopped out, what
fraction went nowhere, and what fraction launched cleanly within 3 weeks? The answer drives a
specific fix: if the weekly-already-rising names stop out much more, we spin them into a
separate continuation species. If they do about the same, we just add a label. If they
actually do better, we fix the rank formula that is penalising them. We commit to the fix
before we look at the numbers.

---

## Trial ledger entry (to be written before first run)

```
family: p15_continuation
registered_date: 2026-07-04
n_trials: 5
trials:
  T1: ARMED/rising vs PRIME reference (primary)
  T2: RS Q1 vs Q2-Q4 within ARMED-continuation
  T3: RS Q1-Q2 vs Q3-Q4 within ARMED-continuation
  T4: above_200dma True vs False within ARMED-continuation
  T5: Q1+above_200dma vs all others within ARMED-continuation
bh_family_size: 5
status: pre-registered
```

---

*This pre-registration is immutable once committed. Results are added to the report file only;
this document is never edited to accommodate observed outcomes.*
*Registered 2026-07-04 — Entry Intelligence program, Sonnet subagent.*

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
