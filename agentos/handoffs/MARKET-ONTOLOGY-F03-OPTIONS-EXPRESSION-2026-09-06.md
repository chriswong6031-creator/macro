# Handoff — MARKET-ONTOLOGY-F03-OPTIONS-EXPRESSION (A-F03-W2-1)

date: 2026-09-06
packet: A-F03-W2-1 — Skew source migration to the ThetaData chain store
ledger row: MO-PAID-013
branch: claude/mo-a-2-a-f03-w2-1
PR: opened DRAFT (see PR link in the calling session's report)

## What happened

`engine/options_skew.py` now sources its per-strike chain from
`engine/thetadata_store.chain()` via `make_chain_provider()` instead of the
legacy `data/polygon_gex/chains/*.parquet` glob. The legacy glob is retired
into `_legacy_chain()`, reachable only behind the explicit
`OPTIONS_SKEW_LEGACY_CHAIN=1` env flag (off by default) — never an automatic
fallback. `build_snapshot()` gained additive `source`/`source_state`/
`source_detail` keys; a non-`ok` state publishes `names={}` (never a 0.0)
and prints a `::warning` GitHub annotation.

`tests/test_options_skew.py` extended from 6 to 12 tests (all pass locally).
`.github/ci/legacy-jobs.yml`'s `flow-surface` job gained the `run:` step and
paths-trigger entry that actually execute this test file — it had zero CI
coverage before this PR.

## Verified (falsifiable claims)

- `verified: python -m pytest tests/test_options_skew.py -q` → 12 passed,
  run on this checkout 2026-09-06.
- `verified: python -m scripts.build_options_skew` → exit 0, writes
  `site/options_skew/latest.json` with
  `names={}, n=0, source=None, source_state="thetadata_store_unresolved"`
  and a `::warning title=options-skew-source::` line on stdout — this host's
  ThetaData store genuinely does not resolve (`data/thetadata_eod/` holds
  only `_backfill_state.json`/`_manifest.json`).
- `verified: grep -n polygon_gex engine/options_skew.py` → hits only in the
  module docstring/comments and inside `_legacy_chain()` — no automatic path
  reaches the glob.

## do_not_redo

- Do not add a second chain/surface/Greeks adapter — reuse
  `engine.thetadata_store.make_chain_provider` (F03 standing do_not_redo,
  `agentos/handoffs/MARKET-ONTOLOGY-F03-OPTIONS-EXPRESSION-FABLE-COO-2026-08-26.md:31-33`).
- Do not touch `scripts/validate_options_skew.py` — the gate stays closed
  (`DNR:KILL-SKEW-DECELERATION`, `research/DO_NOT_REBUILD.md:88`).

## danger_areas / open items for the next session

- `python3 scripts/check_contract_delta.py --base origin/main` was launched
  against this diff but was still running (>2 min CPU) when this worker's
  tool-call budget ran out — its PASS/FAIL was not observed before the PR was
  opened. The `.github/ci/legacy-jobs.yml` diff is minimal (one `run:` line +
  one paths entry) and should be low-risk, but the ship/review stage should
  re-run this check before arming `merge-on-green`.
- No ThetaData store resolves on this host, so the real-store overlap
  acceptance line (§9 line 4 of the frozen spec) is discharged only via the
  synthetic `test_thetadata_and_legacy_overlap` test — the PR body states
  this explicitly rather than claiming a real measurement that doesn't exist.
- Per the frozen spec, `merge-on-green` must NOT be armed on this PR until an
  Opus PASS review — the ship stage should arm it after that review, not
  before.
