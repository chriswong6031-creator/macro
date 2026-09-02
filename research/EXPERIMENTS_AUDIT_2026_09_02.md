# Experiments audit — 2026-09-02 (10 ready results checked and adjudicated)

Successor to `research/EXPERIMENTS_AUDIT_2026_08_26.md` (72 results) using its §9
method: lane workers re-derive each "ready" experiment's real state from artifacts
only (seed prose never trusted), the orchestrating session adjudicates and writes the
seed. Registry set: `site/marketdata/experiments.json` as of 2026-09-02 — 274
tracked, 10 flagged ready in the admin Experiments panel (4 cortex hypotheses,
2 vector/BTC track-records, 2 setup species, 1 thematic-desk track-record, 1 frozen
phase-0 backtest). Three Opus analyst lanes + one Sonnet builder lane, orchestrated
by Fable. No promotions, no demotions, no DNR kills: every read below is
display-tier, and per house law these are instrument-window verdicts, never market
verdicts.

## 1. Cortex hypotheses (4) — the repaired instrument declines to grade three; the H5 pass is formally fenced

The 08-26 audit's §3 found five evaluator wiring defects; #6503 repaired them
(evaluator now `W7b-PR3`) and built the quarterly FDR batch (`scripts/
quarterly_cortex_fdr.py`, riding weekly.yml). Today's read, from live dry-runs of
both instruments (`python3 -m scripts.evaluate_cortex_hypotheses --dry-run`;
`python3 -m scripts.quarterly_cortex_fdr --dry-run`):

- **H2 high_alibi (`…-898d24`, due 09-02)** → `invalid-gate`: threshold −0.05 is
  outside hit_rate's attainable range in absolute space — the 08-05 re-registration
  carried the same W3 gate shape the audit predicted would fail identically.
  Terminal for this registration; a corrected gate requires a NEW registration
  (Article 7 — the evaluator never rewrites a pre-committed gate).
- **H3 stopped-heterogeneity (`…-b2727c`, due 09-02)** → `invalid-gate`
  (threshold 1.01 > attainable 1.0). Same disposition.
- **Quad-unsupported (`…-4a6d7e`, due 09-02)** → `uncomputable-metric`: its gate
  metric `difference_in_mean_5d_signed_excess` is not in the W7b-PR3 metric enum
  (registered 08-21, before registration-time enforcement landed 08-26). Same
  disposition: re-register with a supported metric (`excess_mean_difference` is the
  matching shape).
- These three verdicts are written by the NIGHTLY (sole advancer of the machine
  registry); all three statuses are terminal in `metabolism.TERMINAL_STATUSES`, so
  they stop flagging on their own once the nightly's evaluator step next runs with
  them due. This audit deliberately writes no ledger rows for them.
- **H5 decay-flag (`…-1bf548`, flagged since 08-26 as the one unconsumed pass)** —
  its consumer now exists and REJECTS it: the 2026Q3 FDR batch fences the 07-13 pass
  with `no evaluator_version recorded (pre-repair verdict)` (1 candidate,
  0 eligible, 0 survivors). Adjudication: **superseding row appended** retiring the
  pass as a pre-repair instrument artifact (W7b-PR2-era, no p-value, trivially
  passable absolute floor per audit §3 W3); re-arm = NEW registration under W7b-PR3
  semantics via the Batch B re-registration lane (`rf-batch-b-cortex-watch`, 09-09).

Registry-mechanics fixes in this PR (same class as 08-26 §0):

1. **The cortex hook did not know the W7b-PR3 terminal statuses** —
   `engine/experiments_registry.py::_refresh_cortex_evaluator`'s `status_map`
   defaulted `invalid-gate` / `uncomputable-metric` / `unresolvable-query` /
   `invalid-self-reference` / `expired-insufficient-n` to "accruing", so tonight's
   three terminal verdicts would have presented as live accruals forever (not
   ready-flagged — terminal rows have `come_back` cleared — but mispresented).
   All five now map to `no_go`, pinned by
   `tests/test_experiments_registry.py::test_cortex_terminal_statuses_all_read_as_concluded`,
   which walks `metabolism.TERMINAL_STATUSES` so a future terminal status cannot
   regress this silently.
2. **`budget-rejected` is terminal in metabolism but mapped "accruing"** — same
   defect, same fix (→ `no_go`), caught by the same test.

Watch items (recorded, not fixed here): (a) the first post-repair weekly FDR
artifact has not landed on main — `data/neuralweb/cortex/fdr_batches/` does not
exist and no weekly.yml deep-dive commit appears around Saturday 08-29; verify next
Saturday's run writes `2026Q3.json` (the local dry-run proves the batch itself
works). (b) `evaluator_run.json` is only written when ≥1 row is due
(`evaluate_due` early-returns), so "ran, nothing due" and "never ran" leave the same
committed trace; the 08-18 receipt is therefore healthy, but the gap is the same
observability class the cancel-invisibility law names.

## 2. thematic-desk — the "inverted" finding is UNREPRODUCED, and independence, not n, is the variable

n tripled (50 → 161 decided) while honest independence went 1 → 2 windows — the 161
[entry, check_by] windows form ONE unbroken overlapping chain 06-18→08-31
(overlap-connected components = 1). The artifact's `independent_blocks=3` is an
interval-scheduling capacity count whose 3 selected windows contain 3 theses (1.9%
of the cohort) — the 08-03 come-back's premise ("n→150, blocks→3-4") was wrong in
construction. The strongest honest partition is two disjoint generations and they
DISAGREE: G1 (n=51) dir 0.412 below the 0.5125 null; G2 (n=20) dir 0.600 above it;
the 90 straddling theses (dir 0.311) carry the aggregate and sit inside the one
July–mid-August theme drawdown. Verdict: hold display-only, do NOT tilt and do NOT
trade the inverse; re-read 10-13 when a THIRD disjoint generation first exists.
Fix scoreboard since 08-03: (c) placebo-null-beside-hit-rate LANDED
(`c2a4dac54456`); (a) expired counter NOT landed — the uncounted-rows leak grew
8 → 12 (URNM/CIBR/IBIT cohort); (b) priceable-proxy gate NOT landed, and a NEW
failure mode was found: IBIT's series exists but ends 06-15, so the gate must
require a bar at/after the prospective check_by, not series existence. REMX
resolved itself (parquet now present, both theses graded).

## 3. species-S6 / species-S13 — every blocker still present; both convert to event-driven cadence

Zero commits have touched either species since 08-03 (`git log --since=2026-08-03
-- research/species/ data/species/` is empty). S6: the bound ledger still
physically cannot store an S6 row (closed 10-code `REJECTION_TAXONOMY`, validator
hard-reject, sole near-miss writer emits two signal_gate codes) — near-miss rows
grew 73 → 148 over two more months with species_id non-null on 0 of 59,691 ledger
rows; the phase-0 result remains unreproducible from tracked state (/tmp fire
parquets gone, hardcoded roots). S13: all three required panels remain absent,
untracked and gitignored (`.gitignore:192-195`); `assert_no_gate` is still a
private substring blocklist reached by no caller input; the 3-vs-2 trial-count/DSR
divergence stands. Both come_back_note predicates fire → per their own prescription
both entries convert `cadence: monthly` → `event_driven` with `come_back_on: null`
(precedent: macro-tx-phase0's nulled come-back, 08-26 audit §0): S6 re-arms on the
first non-zero S6 forward row, S13 on panel availability. S6's next_step now names
the fork honestly: UNBLOCK (a §8-signed taxonomy extension is an adjudication act)
or propose a KILL-or-park rather than carry a third structurally-guaranteed null.

## 4. Remaining lanes (placeholder)

- vector-btc-impulse + spvector-overlay: pending lane packet.
- s-mlc-3-weekly-wait-cost: pending builder run.

## 3. Method note

Same playbook as 08-03/08-26: lane workers re-derive state from artifacts only and
propose; the orchestrating session adjudicates, spot-verifies lane numbers against
the artifacts, and writes the seed. Statuses stay within the registry vocabulary;
every updated entry carries `state_as_of: 2026-09-02`.
