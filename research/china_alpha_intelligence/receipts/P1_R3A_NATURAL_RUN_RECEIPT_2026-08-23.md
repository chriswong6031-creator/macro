# P1-R3A Natural Production Receipt — 2026-08-23

**Workstream:** `WS:CHINA-ALPHA-INTELLIGENCE`  
**Capability:** P1 Institutional Visit Tape / P1-R3A coverage-exception write-order repair  
**Verdict:** **PASS — P1 is DONE / PROVEN_LIVE.**  
**Adjudicated by:** Sol under Chairman authority, 2026-08-24.  
**Proof lane:** first qualifying natural scheduled `asia-close` after the final repair/closeout lineage; no rerun and no manufactured malformed production input.

## 1. Why this receipt exists

The prior worker closeout correctly froze P1 code after PR #6269 and PR #6298, but at the time of that return the workstream still said the final clean natural production receipt had not accrued. That statement became stale later on 2026-08-23 when the scheduled Asia lane completed successfully with the repair and closeout lineage in its checkout.

The malformed-key branch itself is intentionally fixture/mutation-proven rather than waiting for a naturally malformed CNInfo identifier. The production acceptance condition is the first **clean natural run** proving that the new persistence ordering is inert on the normal path, the coverage-exception ledger is readable/persistable, the same-cycle filing -> visit accounting remains complete, and healthy transport can still advance success normally. Manufacturing a malformed production row to obtain a receipt would violate the frozen proof law.

## 2. Immutable run identity

- GitHub Actions run: `32626503385`
- workflow: `asia-close`
- event: `schedule`
- run attempt: `1`
- head branch: `main`
- run head: `e6339b03227ae70bede94b15bd7269a9d6c7ec84`
- run status/conclusion: `completed / success`
- created / started: `2026-08-23T07:47:21Z`
- updated: `2026-08-23T10:04:35Z`
- persisted Asia job timing: start `2026-08-23T08:25:11Z`, end `2026-08-23T10:03:13Z`, elapsed `98.0` minutes, runner `mac-builder-light`
- persisted collector attribution: `china_filings=966.5s`, `china_visits=0.0s`, source-attribution read=`ok`

Primary receipts:
- run API: `https://github.com/mastermindx-market-intelligence/macro/actions/runs/32626503385`
- timing commit: `9b3153fd9476c42020bbd0b427ebf7edf72eabb8`
- natural collection commit: `cd42b890d1df740f7fd5fddee6e582221360791b` (`data: asia collection 2026-08-23`)
- natural engine/render commit: `5b25fe3d944dc2344ddfa8abcc75b95f3fde8459` (`engine: asia dashboards 2026-08-23`)

## 3. Repair and closeout lineage was in the proving checkout

Final P1-R3A repair:
- PR #6269 squash: `0bcfef045517bcaae23271b1218f37c59bcaa864`

Records-only P1 code-closeout/adjudication:
- PR #6298 squash: `486d9976835dabb042bc053a8e5f6abe23a218ce`

Ancestry checks performed by Sol:

- compare `0bcfef045517...` -> run head `e6339b03227...`: `ahead`, `behind_by=0`, merge base exactly `0bcfef045517...`;
- compare `486d9976835d...` -> run head `e6339b03227...`: `ahead`, `behind_by=0`, merge base exactly `486d9976835d...`;
- compare run head `e6339b03227...` -> collection commit `cd42b890d1df...`: `ahead`, `behind_by=0`, merge base exactly the run head.

Therefore the natural run executed with both the final code repair and the final code-closeout ruling already present.

## 4. Natural health/accounting result

`data/china_visits/health.json` in collection commit `cd42b890d1df740f7fd5fddee6e582221360791b` records:

```text
status                     = ok
detail                     = 219 candidate row(s) this run
last_attempt_utc           = 2026-08-23T09:07:33.022647+00:00
last_success_utc           = 2026-08-23T09:07:33.022647+00:00
eligible                   = 219
represented_downstream     = 219
typed_exclusions           = 0
coverage_exceptions.open   = 0
open_scoped                = 0
open_unscoped              = 0
new_this_run               = 0
reaffirmed_this_run        = 0
resolved_this_run          = 0
ledger readable            = true
boundary_persist_ok        = true
```

This is exact full candidate accounting: **219 eligible = 219 represented downstream + 0 typed exclusions**.

## 5. Why `status=ok` proves the clean R3A acceptance path

The merged `collectors/china_visits.py` health law is fail-closed. A healthy `ok` cannot be published if any of the following is true in the same invocation:

- visit write was refused;
- `china_filings` same-run transport is unhealthy;
- same-run key integrity is unknown;
- the coverage-exception ledger is unreadable;
- the R3A boundary persistence failed.

Any such cause produces an `upstream_degraded` outcome and the run contributes no clean absence authority. The 2026-08-23 `ok` receipt therefore proves the normal production path survived the repair with clean source transport, known key integrity, readable exception state, successful boundary persistence, and balanced downstream representation.

The registry/order contract remains load-bearing: `scripts/collect.py` places `china_filings` immediately before `china_visits` in the CNInfo host group so the visit plane derives from the same invocation without a second network ingester. The natural timing record shows both members in the real scheduled collector band.

## 6. Rare malformed-key branch proof remains fixtures/mutation, not manufactured production

P1-R3/R3A exists to prevent a malformed institutional-visit observation from being forgotten before its durable coverage exception is persisted. At closeout, current production history contained no naturally malformed keys. The rare branch was therefore required to be proved with hostile fixtures and mutation tests, while this receipt proves that the repaired write ordering and ledger boundary are production-safe on the clean path.

No future worker should wait for, inject, or manufacture a malformed CNInfo identifier merely to obtain a live receipt. A naturally occurring malformed observation, if one appears, becomes an operational observation against an already-accepted contract, not a prerequisite for P1 acceptance.

## 7. Later 2026-08-24 operational degradation does not revoke acceptance

Current-main `data/china_visits/health.json` after the next Asia cycle reports:

```text
status = upstream_degraded
detail = derived over a same-run china_filings TRANSPORT degradation
         (szse: Response ended prematurely) — this run contributes no absence evidence
last_success_utc = 2026-08-23T09:07:33.022647+00:00
eligible = 230
represented_downstream = 230
typed_exclusions = 0
ledger readable = true
boundary_persist_ok = true
```

That is the intended failure-isolation behavior: the later upstream transport failure refuses clean absence authority and preserves the prior success clock. It does **not** undo the successful 2026-08-23 production traversal or move the implementation back to BUILT_NOT_PROVEN.

Operational source health and implementation acceptance are different state planes.

## 8. Final capability ruling

The P1 chain now satisfies its completion law:

- Institutional Visit Tape producer: production-proven;
- same-cycle `china_filings -> china_visits` derivation: production-proven;
- exact candidate reconciliation: production-proven;
- dossier/product surface: previously production-proven on the accepted P1 natural-run receipt of 2026-08-21;
- typed malformed-key handling: hostile-fixture + mutation-proven;
- durable coverage-exception lifecycle: built and adversarially reviewed;
- R3A persistence-before-forgetting boundary: clean natural production path proven by run `32626503385`;
- clean path remains zero-exception/inert;
- later upstream failure remains honest/fail-closed.

**Canonical acceptance state: `P1 = DONE / PROVEN_LIVE`.**

No further P1 repair is authorized merely to seek more proof. Future P1 code should open only for a new reproducible production defect or an explicitly commissioned product/intelligence extension such as P1B.

## 9. Exact continuation

The next dependency is **L0 — full-pool canonical outcomes**, not another P1 repair and not live ranking. L0 must extract/reuse the existing `engine/china_standout_track.py` grading primitives for the canonical China candidate plane and must not create a rival grader. P1B Institutional Discovery may proceed after L0 lands/proves and sufficient P1 accrual exists, under the Fable COO program delegation recorded in `DEC:CHINA-ALPHA-FABLE-COO-AUTONOMOUS-EXECUTION`.
