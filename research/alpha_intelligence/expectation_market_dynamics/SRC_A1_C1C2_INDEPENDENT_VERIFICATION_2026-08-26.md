# SRC-A1 C1→C2 independent verification receipt — 2026-08-26

A parallel Fable COO session executed the commissioned natural C1→C2 SRC-A1
audit independently of, and concurrently with, the session that produced the
canonical SRC-A1P outcome records (PR #6458, merge `f54481e16dab`). This
receipt records the concurrence and the evidence this second audit adds. It
does not restate #6458's records; on any narrative overlap, #6458 and the
`CURRENT_CAPABILITY_LEDGER.md` audit-outcome section govern.

Skillpack: bootstrapped from protected Mastermind `origin/master`
`5f9eca71ad21355b56da2a3c68fa5b61b3f4204a` (`mastermind.sol_skillpack.v1` /
`1.0.0` / bootstrap ≥ 1).

## 1. Concurrence

Independent method: parquet bodies extracted via
`git show be061c6d49e9:… / 576959b11804:…`, a 19-condition sheet covering the
`handoffs/SRC_A1.md` proof law and all ten `DATA_CLOCK_RIGHTS_MATRIX.md`
mutation gates, null-safe field-level comparison of every C1 row/receipt
against its C2 counterpart, and the frozen gate test suite.

Identical verdict, reached without sight of #6458's analysis:

- **FAIL on mutation gate 1 alone** — same 9 violation groups
  (`BRK-B` revenue `0q`; `COKE` revenue ×4; `CRVL` revenue ×4). The row-count
  difference between the two audits is counting-net only: 27 non-count
  interpretable-value rows in the empty-consensus groups (this audit's
  signature) vs 36 total zero-value rows (#6458's net). Same defect, same
  groups, same repair (#6452, post-C2).
- All exercisable conditions PASS, including: 11,200/11,200 observations and
  200/200 attempt receipts byte-identical in C2 (null-safe comparison, 0
  mutated fields); no id reuse across sessions; grain-unique; typed
  missingness total and exclusive; strict `provider_observed_at` <
  `system_observed_at` on all 11,144 new rows; every C2-new clock inside the
  producing engine job window and strictly after every C1 clock; attempt
  statuses within the frozen enum with `observation_count` reconciling
  per-attempt; legacy `latest`/`history` schema-compatible and append-only.
- Same structural finding: disjoint drip batches leave the
  revision/supersession invariants unexercised
  (`DSC:SRC-A1-DRIP-CURSOR-DEFERS-REVISION-PROOF`); C1 shows zero gate-1
  violations only because its A–B batch contained no empty-consensus group —
  identical code, no trigger.
- Frozen gate suite at current main (post-#6452): 30/30 pass; at the frozen
  merge `dc51502ba1b0` the file carried 22 tests, none discriminating the
  empty-consensus shape.

## 2. Additive evidence 1 — body-level cryptographic run binding

`accrue_expectation_observations` derives its session identity as
`sha256(json_compact_sorted(["src-a1", "yfinance", ["github_run",
GITHUB_RUN_ID]]))` (`collectors/equity_revisions.py`,
`_default_collection_session_id` + `_canonical_sha256`). Recomputing the
preimages and comparing against the accrued bodies:

| collection | recomputed preimage | body `collection_session_id` | match |
|---|---|---|---|
| C1 | H(`["src-a1","yfinance",["github_run","32786919396"]]`) = `74cfd4a7162056b1324f662d7d7685d445fc2040a8c94b8a0f54efd2c79a019c` | `74cfd4a71620…` (sole session in C1, observations AND attempts) | exact |
| C2 | H(`["src-a1","yfinance",["github_run","32908543584"]]`) = `d9fa989a6c9e3b82a1d2ab92f90c16976ad3c1fa9df75ffcca814c1141649c9d` | `d9fa989a6c9e…` (the only new session in C2) | exact |

This upgrades "publication data-consistent with the scheduler path" to
body-level proof: a row minted by a local run, a manual dispatch, or any other
workflow cannot carry the session id of the scheduled run, because
`GITHUB_RUN_ID` is baked into every row's identity by the collector itself.
It is also how this audit independently rediscovered the C1 attribution
correction: the recorded run `32790724676` hashes to `02cba0114393…`, which
appears nowhere in the bodies; `32786919396` hashes to the observed session.

## 3. Additive evidence 2 — both skip-twins verified job-by-job

Beyond C1's skip-twin (`32790724676`, 18/18 jobs skipped), the C2 night's twin
`32912351235` (created 2026-08-25T23:47:52Z, run-level `success` in ~5s) was
verified job-by-job: `et_gate` success, all 17 remaining jobs `skipped`. Both
nights follow the same DST cron-pair shape: the run-level `success` twin runs
nothing; the run-level `cancelled` builder carries the successful `engine`
job. Attribution must use the engine JOB window and the session hash
(`DSC:NIGHTLY-ARTIFACT-ATTRIBUTION-NEEDS-THE-ENGINE-JOB`).

## 4. Standing value

For every future SRC-A1P re-audit (cursor-wrap audit ~2026-09-01 and later):
recompute the session-hash preimage for the claimed producing run before
trusting any recorded run id. The check costs one sha256 and is immune to the
run-level-conclusion trap in both directions.
