# Ship-loop branch-law and proof-gate incident attestation — 2026-08-14

## Scope

This is a fact record and a fail-closed process repair. It is not an activation
receipt, a producer receipt, or evidence of trading, publication, ranking or
training authority.

## PR #5656 — forbidden namespace and premature merge

- PR #5656 used the forbidden branch
  `codex/sparse-selector-final-integration-20260814` at head
  `86a4192baeb0a7d706c06ecde65c6fff930db9f8`.
- GitHub merged it as `34b64a1160badf5354479992a593ecb189518089` at
  `2026-08-14T16:00:13Z`, before CI plan `31816882707` had concluded and before
  its twelve pack jobs had run.
- The merge changed exactly
  `contracts/options/options.sparse_selector_runtime.v1.schema.json`,
  `engine/options_sparse_selector.py`, and
  `tests/test_options_sparse_selector_runtime.py`.
- The selector core SHA-256 changed from
  `c03375fd1affa87c456365b73febf56dbc8f490a42fe9df1434d6dff5ad41522`
  to
  `f535bf10c651a1817efa6100c4b46dcff677d4e6a255fa08174981f115a825f6`.
- The original run is not selector proof. Its pack 6 stopped on the inherited
  H+60 flow-surface failure before selector preregistration, runtime and the
  4,096-candidate benchmark executed.

A later sanctioned carrier at exact head
`eb994aec6de50888aa6d5370a8795bde59c8c836` supplied surviving-tree proof:
CI run `31818283839` concluded green for ci-plan, all twelve packs and ci-gate;
the selector preregistration, runtime and 4,096-candidate benchmark executed
green; and fences run `31818283682` concluded green. That tree merged as
`c87946fe403926207f4865728249ef42221fa678`. This closes the surviving-code
gap; it does not excuse the original process breach or turn run `31816882707`
into a pass.

## PR #5596 — blocked live-flow release merged manually

- PR #5596 used the sanctioned branch
  `claude/liveflow-rth-error-exit-20260814` at head
  `9237241c73fe5d45db7852efd2269bf6ada7dcb3`.
- It retained both `merge-on-green` and `merge-blocked`, yet GitHub merged it
  manually as `12ec544e3cf0aa43721ac9aa2a2caa8e460265ce` at
  `2026-08-14T17:29:42Z`.
- The merge changed exactly `scripts/live_flow_poller.py`,
  `tests/fixtures/r2_delivery_macro_evidence_files.v1.tsv`, and
  `tests/test_live_flow.py`.
- Exact-head CI run `31800693332` concluded failure; fences run
  `31800693321` concluded success. The post-close CI run `31824247999`
  was skipped.

The merge does not manufacture an RTH receipt or scheduled evidence. This
attestation counts no manually dispatched workflow as evidence, and no live-flow
producer was invoked or backfilled for it. The normally scheduled RSS, stage and
index evidence remains the only admissible release evidence.

## PR #5588 — target-host proof gate bypassed

- PR #5588 used the sanctioned branch
  `claude/sparse-selector-runtime-carrier-20260814` at head
  `ff4d56cfc58f086f7ed77f6ce95bd718e60e3f24`.
- It remained labelled `merge-blocked`, yet GitHub merged it as
  `899c84341542d847bc50c3c6481ade023e1e01e8` at
  `2026-08-14T17:31:19Z`.
- The merge added exactly four inert carrier paths:
  `.github/ci/legacy-jobs.yml`,
  `docs/runbooks/OPTIONS_SPARSE_SELECTOR.md`,
  `ops/launchd/run_options_sparse_selector_verified.py`, and
  `tests/test_options_sparse_selector_bootstrap.py`.
- Its last exact-head CI run before merge, `31800780518`, concluded failure.
  The post-close run `31824375278` was skipped.
- Its disposable Mac13,1 proof ran from a reviewed carrier whose selector SHA
  was `c03375fd1affa87c456365b73febf56dbc8f490a42fe9df1434d6dff5ad41522`,
  not the current core SHA
  `f535bf10c651a1817efa6100c4b46dcff677d4e6a255fa08174981f115a825f6`.
  The v1 wrapper checked the repo sources across import but discarded their
  hashes, so `runtime_closure.json` was not self-binding to either source file.
  Hosted CI cannot substitute for a corrected target-host proof.

The carrier does not install a plist, add daily/DAG/Synapse wiring, invoke a
producer, or alter data. `SELECTOR_RUNTIME_ARMED` remains the literal `False`,
and its receipts state `authority=false` and `training=false`. The code is
available but remains unarmed. A fresh normal Mac13,1 disposable current-core
v2 proof and retained receipt are still required before any activation review.

## PR #5647 — blocked carrier merged before exact-head proof

- PR #5647 used the sanctioned branch
  `claude/w4-intelligence-drawer-sanctioned-20260814` at merged head
  `9f17bf97a3f85166a16c5870144e45962462d039`.
- It remained labelled `merge-blocked`, yet GitHub merged it as
  `6c9eb208525cb967adf2221738dd8e8e98d07ddf` at
  `2026-08-14T17:31:39Z`, on parent
  `899c84341542d847bc50c3c6481ade023e1e01e8`.
- The merge delta is exactly the 40 W4 presentation, paired-asset, crop,
  manifest and focused-test paths. It did not contain this attestation,
  `.claude/hooks/ship_loop_guard.py`, or `tests/test_ship_loop_guard.py`; those
  three remediations were still uncommitted when the merge occurred.
- Its W4 README also retained the known-false statement that sector names render
  in English under `zh`, even though the merged page already publishes
  `WL_SECTOR_ZH` and uses `secCell()`. The truthful prose correction had not been
  committed when the merge occurred.
- Exact-head CI run `31824292984` was still in progress at merge. Fences run
  `31824293219` later concluded success. Earlier exact-head CI/fences attempts
  had been cancelled during branch refreshes, so the merge preceded concluded
  exact-head CI.

The 40-path delta adds no engine, producer, market-data, selector-runtime,
trading, ranking or training authority. At the incident audit, production
reported status `ok` at exact checkout
`6c9eb208525cb967adf2221738dd8e8e98d07ddf`.

## Durable remediation and evidence boundary

`ship_loop_guard.py` now rejects every session-created delivery branch that
does not start with the exact `claude/` namespace before stand-down, ancestry
or GitHub delivery probes can release it. Focused tests reject `codex/*`,
`claire/*`, unnamespaced, bare `claude` and look-alike prefixes, while proving a
valid `claude/*` branch still reaches the full delivery chain.

The self-mod-fence manifest job now explicitly owns `.claude/hooks/**`.
Therefore a hook edit selects its full guard contract rather than relying on
inference that could see the tests but miss the subprocess/path-reached hook.

The carrier v2 receipt now persists the exact SHA-256 mapping for
`engine/options_sparse_selector.py` and `engine/private_auth_dict.py`, fails
before writing a manifest if either source changes during import, and retains
literal `authority=false` / `training=false`. Those hashes bind source bytes to
the receipt; they do not assert Git provenance or activate the selector.

These changes narrow release paths; they do not claim that incident trees were
proved by runs which did not execute. The Mac13,1 gate remains independently
open. No manually dispatched workflow is counted as evidence, and no producer
was invoked, evidence backfilled, receipt fabricated, or authority/training
fence widened to produce this record.
