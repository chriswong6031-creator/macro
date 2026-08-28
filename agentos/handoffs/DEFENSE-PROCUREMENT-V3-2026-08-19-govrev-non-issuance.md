---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/govrev-non-issuance-record
model: local
ended_because: complete
discoveries:
  - DSC:GOVREV-PUBLISHER-VINTAGE-LAG-IS-THE-ONLY-TRACE

mission: >
  Implement option B2 from the 2026-08-19 opus debug packet — an explicit
  reviewed non-issuance record (new manifest + schema + loader) so the two
  source-emitted-but-unissued BWXT candidates leave the unaccounted set by
  construction — or adjudicate B3 instead.

state_before: >
  Post-#5932 (defense21-v1 graph) and post-#5997 (candidate proof heal), the
  engine emitted 64 candidates while the published queue carried 54 and the
  append-only ledger held 62 distinct ids. The residual was exactly two BWXT
  rows, excused by the ledger issuance-frontier heuristic #5997 introduced —
  honest, but a temporal guess rather than an accounting.

changed:
  - path: tests/test_government_revenue_candidates.py
    what: >
      Added _published_graph_vintage() and the pure _escaped_candidates(), and
      conjoined the unaccounted-candidate excuse with the publisher's own
      committed graph-vintage receipt. Strict narrowing; self-retiring.
  - path: agentos/discoveries/DSC-GOVREV-PUBLISHER-VINTAGE-LAG-IS-THE-ONLY-TRACE.md
    what: New discovery recording the silent-discard mechanism and its only trace.

verified: >
  Partition measured against committed origin/main with data/ materialized:
  `build_candidate_observations` on the live payload+graph yields emitted 64,
  ledger 62, quarantined 8, queue 54, `unaccounted` exactly the two BWXT ids,
  `ledger - emitted` empty, `queue == ledger - quarantined` True. Vintage lag
  confirmed by reading both committed artifacts. Run 32258132159 step outcomes
  confirmed via `gh run view 32258132159 --json jobs`. Test suites named in the
  publish proof gate run green (see PR body).

unverified:
  - >
    That the next publishing run passes step 10's proof and actually issues the
    two rows. #5997 healed the 6 failures that aborted run 32258132159, and the
    proof suites are green locally, but no publishing run has fired since.
  - >
    The 6 failing test names from run 32258132159. pytest output went to
    $RUNNER_TEMP/govrev-candidate-proof.log and only `tail -n 40` reached the
    step summary, which `gh run view --log-failed` does not expose.

unresolved:
  - >
    The vintage lag has no alarm. A publisher that never fires again stays
    silent forever while the excuse keeps holding. See next_actions.
  - >
    Latent wedge at scripts/build_government_revenue_candidates.py:896 — if a
    run ever advances state.generated_at past 05:44:34 without appending the
    rows carrying that clock, the next run that sees them raises permanently.

next_actions:
  - >
    Build the publisher-lag alarm: an instrument that reds (or annotates) when
    candidate_projection_status.recipient_graph_id has trailed
    recipient_entity_graph.graph_id across a publishing window. Deliberately
    out of scope here; it is the next commission.
  - >
    Operator-only, unexercised: `gh workflow run government-revenue-live.yml
    -f projection_only=true` issues both rows in ~10 minutes.

do_not_redo:
  - >
    Do not write a reviewed non-issuance / suppression / correction manifest for
    the BWXT rows without first showing an unaccounted row NOT explained by the
    vintage lag and NOT issuable by a future publishing run. None existed
    2026-08-19; `unaccounted` was exactly those two.
  - Do not re-stamp or extend the immutable suppression/correction pair.
  - >
    Do not anchor the excuse on a wall clock (candidate_projection_state.generated_at,
    datetime.now) — #5997 removed exactly that anchor as self-invalidating.
  - >
    Do not pursue B3 as framed ("share one as_of"). The as_of chain is already
    coherent; the divergence is graph vintage, and pinning the rebuild to the
    digest named in the state is not implementable from committed bytes.

danger_areas:
  - >
    tests/test_government_revenue_candidates.py is INSIDE the publish proof gate
    (government-revenue-live.yml:594-598, GOVREV_CANDIDATE_PROOF_FATAL=1, with
    ..._candidate_projection.py and ..._candidate_fixture.py). A red there
    refuses the publish and freezes the render finalize gate fleet-wide. Any
    edit must be green against BOTH the committed state and the post-publish
    state.
  - >
    known_at <= prior_frozen_at at build_government_revenue_candidates.py:896 is
    a hard error, not a skip — see the latent wedge in unresolved.
---

# DEFENSE-PROCUREMENT-V3 — govrev unaccounted-candidate accounting (2026-08-19)

`WS:DEFENSE-PROCUREMENT-V3` · mints `DSC:GOVREV-PUBLISHER-VINTAGE-LAG-IS-THE-ONLY-TRACE`
· builds on `DSC:GRAPH-REPUBLISH-RETIMES-EVERY-CANDIDATE-CLOCK` and PR #5997.

## What was commissioned, and what shipped instead

Commissioned: option **B2** from the 2026-08-19 opus debug packet — an explicit
*reviewed non-issuance record* (new manifest + schema + loader) so that the two
BWXT candidates the engine emits but the queue never carries would leave the
unaccounted set by construction.

Shipped: a **vintage-bound transitional excuse**, test-side only. B2 was
refused on evidence, not on preference. The reasoning is below so a future
session does not re-propose it without new facts.

## Why B2 was refused

The two rows are not a review verdict. They are a **publication-scheduling
lag**, and the lag is already machine-readable in committed bytes:

| artifact | value |
|---|---|
| `candidate_projection_status.recipient_graph_id` | `recipient-graph:reviewed:2026-08-08:defense19-v1` |
| `recipient_entity_graph.graph_id` | `recipient-graph:reviewed:2026-08-19:defense21-v1` |

The publisher states in its own receipt that it is one reviewed graph vintage
behind. The published ledger therefore *provably could not* have carried
anything only the newer vintage resolves.

Three facts establish that the rows are transitional rather than refused
(full receipts in the DSC):

1. The graph merge (#5932, `eb81e91ef90b`) fired push run **32258132159**.
   Step 9 `build Government Revenue projection` **succeeded** — the two rows
   were admitted and appended — step 10 `prove the candidate projection before
   publishing it` **failed** under `GOVREV_CANDIDATE_PROOF_FATAL=1`, step 11
   `commit complete evidence projection` was **skipped**. The freshly-issued
   ledger died with the runner workspace.
2. The heal (#5997) touched only `tests/**`, which is absent from the lane's
   push path filter, so merging it fired **no** push run and did not re-arm the
   publisher.
3. Scheduled runs outside 00xx–01xx UTC quiet-skip the SAM collect and resolve
   `publish=no`. A wall of green scheduled runs is not evidence of a publish.

The admission predicate does **not** reject these rows:
`scripts/build_government_revenue_candidates.py:896-910` compares
`known_at 05:44:34` against `prior_frozen_at 05:25:42` and routes them to
`appendable`.

Building B2 anyway would have been actively harmful. Both existing manifests
are immutable sha-bound chains that are **never retired** — the lane's
`assert_historical_suppression_source_clean` / `assert_issuance_correction_source_clean`
forbid the builder from touching them. Two candidate ids subtracted from the
unaccounted set by a permanent manifest stay subtracted **after they issue**,
which holes the one gate that catches the 2026-08-10 incident class. It would
also have been stale within a day.

## What shipped

`tests/test_government_revenue_candidates.py` only. No `scripts/`, `engine/`,
`config/`, `contracts/` or `.github/` edit, so `authority_changed` stays false.

- `_published_graph_vintage(root)` reads `recipient_graph_id` from the
  publisher's committed status receipt.
- `_escaped_candidates(...)` — pure, so tests drive it without monkeypatching —
  conjoins the existing row-level `_attributing_path_known_at` vs
  `_issuance_frontier` comparison with `published_graph_id != committed_graph_id`.

This is a **strict narrowing**: every row the frontier comparison caught is
still caught, plus every row whose excuse rested on a lag the publisher has
since closed. It self-retires with nothing to curate — when the publisher
consumes the vintage the excuse dies for every row at once, and an
still-unissued row becomes a hard failure.

## Where the rest lives

`do_not_redo`, `danger_areas`, `unresolved`, `unverified` and `next_actions`
are in this file's frontmatter — the machine-readable copy is the only copy,
so the two cannot drift.
