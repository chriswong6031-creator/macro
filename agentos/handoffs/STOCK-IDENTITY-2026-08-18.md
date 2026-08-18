---
workstream: WS:STOCK-IDENTITY
session: claude/w1a1-ohlcv-digest-tripwire
model: fable
ended_because: complete
mission: >
  Heal the fleet-wide CI red caused by W1-A1's exact-equality digest over the live
  B OHLCV plane, as the owning session, without re-stamping the registered constant.
state_before: >
  origin/main red since 2026-08-18T04:02Z. ci-pack-3 (job `trial-budgets`) failing on
  tests/test_stock_identity_atlas.py::test_b_source_is_exactly_the_registered_curated_plane
  with "B source logical prefix differs from registration: a77fdc41...", taking ci-gate
  with it and pinning every session. A second, unrelated pack (ci-pack-6,
  tests/test_government_revenue_candidates.py) was red at the same time and is NOT
  covered by this work.
changed:
  - path: data/stock_identity/sources/w1a1_b_ohlcv_prefix_v0.parquet
    what: >
      NEW immutable snapshot — the 3,172-row 2014-01-02..2026-08-13 prefix A1 was built
      from, cut from the #5632 seed blob at commit 6d04e9b3 under the plane.load_symbol
      normalization. Reproduces the registered logical digest 6d8988fc exactly.
  - path: data/stock_identity/sources/manifest.json
    what: NEW store manifest carrying the all-false authority block and the snapshot's provenance.
  - path: scripts/stock_identity_build_w1a1.py
    what: >
      A1 now reads the snapshot instead of the live plane; `_load_b_prefix_snapshot`
      checks it at both the container and logical layer; `_tripwire_b_live_plane`
      replaces the live-file equality assert; receipt gains snapshot + live-revision blocks.
  - path: tests/test_stock_identity_atlas.py
    what: >
      Failing test repointed at the snapshot; added tripwire tests in both directions;
      authority sweep now excludes price stores by path, not bare directory name.
  - path: research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md
    what: >
      §A1.3's "post-asof appends may not move it" struck as superseded; new §A1.3a records
      the false premise, the snapshot, the measured drift and the enforced bands.
  - path: agentos/decisions/DEC-SEALED-INPUTS-ARE-FROZEN-NOT-REPINNED.md
    what: NEW decision record for the general fix shape.
verified:
  - claim: The frozen snapshot reproduces the registered digest exactly, so no constant was re-stamped.
    command: "python3 -c \"from scripts.stock_identity_build_w1a1 import _load_b_prefix_snapshot, _ohlcv_prefix_sha256, B_SOURCE_PREFIX_SHA256; print(_ohlcv_prefix_sha256(_load_b_prefix_snapshot()) == B_SOURCE_PREFIX_SHA256)\""
    result: "True — digest 6d8988fc8ec3990d3a5c2a6d5f4bb31d94b3ab46ac49978d21fb3770482ae8db"
  - claim: The whole stock-identity atlas suite passes, including the previously failing test.
    command: python3 -m pytest tests/test_stock_identity_atlas.py -q
    result: 114 passed
  - claim: Every step of the enclosing CI job (`trial-budgets`, ci-pack-3) is green locally.
    command: "python3 scripts/check_trial_registration.py; python3 scripts/check_reliability_contract.py; python3 -m pytest <the job's 14 test files> -q"
    result: "OK; clean; 357 passed"
  - claim: Appending §A1.3a did not move the sealed §4 partition procedure hash.
    command: "python3 -c \"from engine.stock_identity import partition as p; print(p.partition_procedure_sha256(REGISTRATION)[0])\""
    result: a546c649... equals partition_manifest_v1.json's pin
  - claim: The live prefix really does move nightly — three distinct digests exist in git.
    command: "git show <commit>:data/baskets/ohlcv/B.parquet for 6d04e9b3, 59ccb9c7, 93ab221b, then digest each prefix"
    result: "6d8988fc -> 2f4d9467 -> a77fdc41; 2,214 then 2,341 of 3,172 rows moved"
  - claim: ci-pack-3's ONLY failure was this test (so one PR carries the whole pack heal).
    command: gh api repos/mastermindx-market-intelligence/macro/actions/jobs/95601375518/logs
    result: single FAILED line, test_b_source_is_exactly_the_registered_curated_plane
  - claim: The ci-authority red on this PR is fleet-wide, not caused by this branch.
    command: gh pr view <n> --json statusCheckRollup for PRs 5863-5868
    result: "ci-authority/codex/merge-queue-pilot FAILURE on all six"
  - claim: Agent OS records validate.
    command: python3 scripts/agentos.py validate
    result: 175 records, 0 errors (10 pre-existing phantom-owns-path warnings)
unverified:
  - claim: >
      The 1e-5 residual band has decades of headroom against accumulation across a
      lengthening back-adjustment chain.
    what_would_verify: >
      Re-measure the residual after several dividends have passed the asof (next natural
      check ~Q4 2026). The three collections measured span four days and contain no
      dividend, so they bound re-derivation jitter only. Nothing re-measures this
      automatically — the tripwire has no telemetry, so drift toward the band would
      surface as a fleet red rather than as a warning.
  - claim: Raw O/H/L prints are stable at the float32 grid over long horizons.
    what_would_verify: >
      Sample the raw (unadjusted) prints across many collection nights. Observed stable
      over 3 collections/4 days; the 1e-6 coherence band was chosen to tolerate a 1-ULP
      wobble precisely because the frequency is unmeasured.
unresolved:
  - >
      ci-pack-6 is red on main for an unrelated reason —
      tests/test_government_revenue_candidates.py::test_reviewed_historical_cohort_rebuilds_byte_exact_and_nothing_escapes_review,
      26 candidates with neither a ledger issuance nor a reviewed historical suppression.
      Different pack, so per house law it needs its own heal PR. Chipped as a separate lane.
next_actions:
  - Confirm PR #5868 merged and ci-pack-3 green on a main descendant.
  - Heal ci-pack-6 (government-revenue candidate review) in its own PR so ci-gate can go green.
do_not_redo:
  - >
      Do NOT re-stamp B_SOURCE_PREFIX_SHA256 to a fresh digest. The live file is rewritten
      every collection night; a re-stamp re-reds the same evening and requires editing
      sealed A1 receipts the builder's REFUSING guard protects.
  - >
      Do NOT band the price LEVEL (|ratio-1|) in the tripwire, which is the obvious
      reading of "tolerance-aware". auto_adjust rescales all elapsed history on every
      future dividend (~2.4e-3, ~240x the noise floor), so a level band fires on the next
      ordinary Barrick dividend. Band the UNIFORMITY (residual vs the window median factor).
  - >
      Do NOT quantize-then-hash as a way to keep an equality check. Rounding flips
      whenever a value sits within the drift of a boundary; with ~9,500 price cells and
      drift ~8.6e-07 the granularity needed to hold flip risk under 1% is ~1.6 relative.
  - >
      Do NOT tighten the coherence band to the observed 4.4e-16. That sits ~5 orders BELOW
      the float32 grid of the raw prints (~6e-8); a 1-ULP wobble or a yfinance bump would
      then report vendor noise as a print revision.
  - >
      Do NOT edit the sealed receipts naming 6d8988fc (episodes/amendments/B.json,
      amendments/w1a1_gold_wrong_issuer.json) — the snapshot re-anchors that digest, so
      they are already true and were deliberately left byte-identical.
  - >
      The pack index in a failure report is not identity. This red was reported as
      ci-pack-7 and was actually ci-pack-3; run_ci_pack.py rebalances by job weight.
danger_areas:
  - >
      data/stock_identity/sources/ is an immutable BUILD INPUT. No lane may write to it.
      Regenerating it changes the container sha256 pinned at
      scripts/stock_identity_build_w1a1.py B_SOURCE_SNAPSHOT_SHA256.
  - >
      Session worktrees are SPARSE and data/ is omitted by default. Run
      `python3 scripts/worktree_sparse.py add data` before touching anything here or the
      suite fails in ways that have nothing to do with the code.
  - >
      The registration is hash-pinned: editing anything inside the §4 partition procedure
      region moves partition_procedure_sha256 and breaks the seal. §A1.3a was appended
      outside it deliberately; re-check with partition_procedure_sha256 after any edit.
  - >
      _validate_b_source sets a module-level _LIVE_REVISION_RECEIPT consumed during
      staging. If the builder is ever restructured, that ordering must hold or the receipt
      records a different live reading than the one the run validated.
prs: [5868]
decisions:
  - DEC:SEALED-INPUTS-ARE-FROZEN-NOT-REPINNED
---

## Why this took an architecture change rather than a new digest

The registration asserted that only post-asof appends could move the pinned prefix. That
premise was false for this file from the day it was written: `fetch_basket_ohlcv.py`
re-downloads the full auto-adjusted history nightly and lets the new vendor frame win, so
the already-elapsed 2014..asof window is re-derived every night. The pin survived three
days only because of a weekend plus the 08-15→17 ruleset push freeze.

The load-bearing move is that the fix **re-anchors** the receipt instead of re-stamping
it: the seed blob still reproduces `6d8988fc` exactly, so the constant, its five mirrors
and both sealed receipts are untouched and remain true. Freezing also repaired something
CI had not yet caught — a sealed result whose inputs drift nightly could no longer
reproduce its own sealed outputs, so the seal was already nominal.

The subtler half is the tripwire's calibration, and it is where a plausible fix fails.
Banding the price *level* passes today's noise and fires on the next ordinary dividend,
which would have reproduced this same fleet red on a quarterly clock. The invariant that
actually protects A1 is the *uniformity* of the rescale: any uniform rescale preserves
every return, drawdown and percentage gap, so it cannot move a conclusion, while a change
in relative prices can. Corporate actions remain covered on a separate channel, because
split adjustment rescales share counts and settled volume must match exactly.
