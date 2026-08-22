---
workstream: PROPHET-US-V4-RECOVERY
date: 2026-08-22
session: v4-d2b3-implementation (Fable orchestration seat; Sol GO)
---

# V4-D2B3 implementation — GMI Identity Correction Lineage (GOLD reuse + IBIT entity kind)

## What shipped

Implements `research/prophet_v4/d2/D2B3_FROZEN_CONTRACT_2026-08-21.md` VERBATIM including
AMENDMENT §1 (R-A1..R-A8) and AMENDMENT §2 (R-A9/R-A10). Sol closed the §0 gate by
adjudication before this session (recorded in the WS d2 entry, first commit of this
branch): D2B2-US = DONE / PROVEN_LIVE off the natural 2026-08-22 chain (Data OS
generated_at 01:07:17 → GMI natural computed_at 04:50:47Z, us 1210/25/1/1).

Delivered (8 commits):

- `engine/theme_graph/store.py` — `node_lifecycle.parquet` sibling table
  (KEY=(node_id,computed_at), schema `gmi.node_lifecycle/v1`), lane-gated
  `write_node_lifecycle()`, `read_node_lifecycle(latest=)`, `read_nodes(current=False)`
  raw-default overlay projection.
- `engine/theme_graph/materialize.py` — R-A1 POST-PASS structural suppression
  (same-build etf symbol set ∩ company mints → node+edge suppression with one typed
  `company_mint_refusals` receipt each; retired-remint refusal per R-A6 — receipts,
  never raises; materialize stays pure, lifecycle passed in by
  `scripts/build_theme_graph.py`).
- `scripts/check_theme_graph_contracts.py` — lifecycle schema/enum fail-closed;
  break-retirement invariant (ABX absent-prior passes); retired-consistency invariant;
  R-A9 unconditional `ratified_at` fail-closed; matrix-7 backdating breach; NEW
  registry-independent **conflict-retirement invariant** (unretired company/etf
  same-symbol collision = breach — makes the IBIT half load-bearing; adjudicated
  addition, review round 1 MINOR-1). Selftest fixtures for every breach class.
- `config/theme_graph_identity_breaks.yml` — additive `ratified_at: "2026-08-14"` on
  both ratified rows (R-A4).
- `scripts/correct_gmi_identity_lineage.py` — one-shot curated correction,
  registry/structure-driven, zero ticker literals in logic, no Data OS imports
  (test-pinned). Executed ONCE; idempotent (re-run = zero digest movement).
- Correction artifacts committed: `co:us:GOLD` retired (retire_date=2025-12-02
  verbatim break_date; gold_miners edge truncated valid_to=2025-12-02); `co:us:IBIT`
  retired (entity_type_conflict; crypto_rails edge ANNULLED valid_to=valid_from=
  2023-05-09); ABX = lawful no-op (absent prior, nothing minted). Blast radius vs base
  `7cb39c7f9310`: nodes.parquet byte-identical (3,878 rows), edges +2/−0 (8,294 rows /
  8,292 latest-belief — first production edge-lineage divergence), evidence +2/−0,
  node_lifecycle = 2 rows, sidecar/capability byte-identical.
- `scripts/theme_coverage_gaps.py` flipped to `current=True` (retired nodes are not
  coverage gaps). All other §11 consumers raw/no-flip per R-A5/R-A10 (decisions
  recorded in the PR body).
- `tests/test_theme_graph_lifecycle.py` — 26 tests: full §10 hostile matrix 1–14 +
  R-A1's two mandatory cross-day tests + an etf_conflict two-day fence + matrix-13
  divergence pin. Wired into `.github/ci/legacy-jobs.yml` (unrun-suite guard clean).

## Review record

Fresh-context Opus adversarial review, three rounds:

1. Round 1 FAIL (no BLOCKER): every substantive attack SURVIVED (set-diff history
   proof vs true base; real simulated next-day bake over a 6,234-edge hostile drift —
   zero resurrection, exact R-A2 state table {RESOLVED 1210, NOT_IN_MASTER 25,
   DEFERRED 1}, ENTITY_TYPE_CONFLICT 0 + typed refusal; backdating/ratified_at guard
   mutation battery all fired; lane refusals; idempotency). 2 MAJOR + 4 MINOR in the
   PROOF layer (tautological HEAD-vs-HEAD byte tests; matrix 13 untested; IBIT half
   not guard-load-bearing; stale pointer; weak matrix-8; etf_conflict not two-day
   tested).
2. Fix pass (builder) — all six adopted as adjudicated; data digests byte-identical
   across the pass.
3. Round 2: five fixes FIXED/durable; ONE NEW-DEFECT (matrix-10 global delta == 2 was
   a moving-data pin, proven red-in-one-nightly by simulation). Repaired by the
   orchestration seat with the reviewer's probe-proven subset form (`11ba026c4989`);
   26/26 green, guard strict 0, digests unchanged. Adjudicated CLOSED.

## Verification commands (all green at head)

- `TZ=UTC python3 -m pytest tests/test_theme_graph_lifecycle.py -q` → 26 passed
- 9-file targeted theme-graph battery → 314+ passed (see PR body)
- `python3 -m scripts.check_theme_graph_contracts --strict` → exit 0 on corrected store
- `python3 -m scripts.check_theme_graph_contracts --selftest` → OK (all breach classes)
- `python3 -m scripts.audit_unrun_tests` → exit 0

## do_not_redo (binding unless refuted with new evidence)

- Do NOT "fix" the 8,294 vs 8,292 edges/edges_latest_belief divergence — it is the
  lawful first production use of the closure lineage (matrix 13) and grows nightly.
- Do NOT re-run `scripts/correct_gmi_identity_lineage.py` expecting changes — it is
  idempotent (`skipped_already_retired`) and the correction is already committed.
- Do NOT pin global edge-history deltas or multi-belief edge_id sets in tests —
  changed_edges lawfully appends later-belief rows every nightly (round-2 defect).
- Do NOT assert `correction_receipt` presence in `data/theme_graph/_meta.json` — the
  nightly rewrites `_meta.json` wholesale and will drop it; the durable machine record
  is `node_lifecycle.parquet` (by design).
- Do NOT byte-compare parquets via pandas round-trip — `to_parquet` does not reproduce
  identical bytes; restore via `git checkout` (builder-verified).
- GOLD/B sidecar DEFERRED_IDENTITY_EXCEPTION and historical IBIT ENTITY_TYPE_CONFLICT
  rows are the LAWFUL end-state (§7/R-A3) — never zero them.
- The natural sidecar's DEFERRED 2→1 move (GOLD absent) is R-A2 population mechanics,
  NOT a regression — graders must not chase it.

## danger_areas

- **Conflict-retirement invariant blast radius (accepted design):** any FUTURE
  unretired company/etf same-symbol collision in raw nodes.parquet now hard-reds
  `--strict` until a curated lifecycle retirement lands. That loud fail-closed surface
  is intended (the IBIT lesson as law). Measured today: 55 etf symbols, 1 collision
  (IBIT, retired), 0 cross-market near-misses.
- **Bare-symbol suppression matching is the R-A1 frozen shape** (not market-scoped);
  a cross-market company/etf symbol share would suppress with only a ::notice. Bounded
  today (CA carries .TO; CN/HK numeric). Re-open only via a contract amendment.
- Pre-existing reds NOT of this branch (proven via byte-identity + stash):
  `tests/test_theme_graph_identity_resolution.py::TestD2B2US::
  test_cn_hk_resolution_unchanged_by_the_us_admission` (cn RESOLVED 987 vs pinned 984
  — moving-data pin broken by the 08-22 nightly) and 5 `tests/test_house_law_registry.py`
  failures naming scripts absent from this diff. Both need their owning lanes.

## Next (owed, NOT this session)

Merge = BUILT_NOT_PROVEN. DONE requires the next natural production GMI cycle showing:
retired statuses standing, gold_miners current view without an open GOLD edge, IBIT
company refusal receipt in that night's real `_meta.json`, sidecar us states
{RESOLVED 1210, NOT_IN_MASTER 25, DEFERRED 1, CONFLICT 0}, green guards on real
nightly artifacts, no unrelated population/edge mutation. Then return to Sol for
D2B3 DONE / PROVEN_LIVE adjudication. D2C/D2D/D2E/D3/D5/Canada remain NOT authorized.
