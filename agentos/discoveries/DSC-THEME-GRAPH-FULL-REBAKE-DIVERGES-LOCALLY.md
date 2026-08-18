---
key: THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY
claim: >
  Running the full theme-graph pipeline (`COLLECT_LANE=nightly python3 -m
  scripts.build_theme_graph`) in a session worktree does NOT reproduce the committed
  graph: measured 2026-08-18 at pin 9ff7bad19126 during V4-D2A, it recomputed 3,877 nodes
  against the committed 3,878 (dropping one company node that carries a
  DEFERRED_IDENTITY_EXCEPTION resolution), and it REWROTE `nodes.parquet`,
  `evidence.parquet`, and `capability.parquet` on disk even while logging "0 appended" —
  the append-only writers re-serialize the whole file, so byte-identity is lost without
  any logical append. A per-node sidecar written through the same run also stacked a
  second generation (identity_resolution grew 2,806 → 5,611 rows; correct append-only
  behavior, but not the "regenerate the first bake" a PR wants).
falsifier: >
  Two consecutive `COLLECT_LANE=nightly python3 -m scripts.build_theme_graph` runs in a
  fresh worktree at the same pin that leave `git diff --stat -- data/theme_graph/` empty
  and print identical node counts. Or a receipt showing the 3,877-vs-3,878 divergence was
  caused by a materialized-input difference specific to that worktree (e.g. a sparse or
  stale `data/` sibling) rather than by `materialize.build()` recomputing from live
  finviz/THS/crosswalk snapshots.
so_what: >
  A PR session must NEVER "re-bake" a theme-graph plane by running the full pipeline:
  the run silently diffs protected planes (`nodes/edges/evidence/capability.parquet`) and
  produces a node set from the checkout's live inputs, not the committed generation —
  exactly the kind of unreviewable data diff that gets committed by reflex with
  `git add -A`. To regenerate or first-bake ONE derived sidecar, derive it directly from
  the committed `nodes.parquet` (V4-D2A did this for
  `data/theme_graph/identity_resolution.parquet` after reverting a full-pipeline run) and
  write only that plane plus its `_meta.json` fields. The nightly lane is unaffected — it
  derives every plane over its own coherent generation.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  V4-D2A review-fix builder run receipts (session claude/prophet-v4-d2a-identity-bridge,
  pin 9ff7bad19126): COLLECT_LANE=nightly python3 -m scripts.build_theme_graph printed
  3,877 recomputed nodes vs 3,878 committed and left nodes/evidence/capability.parquet
  modified in git status while logging "0 appended"; identity_resolution.parquet grew
  2,806 → 5,611 rows across two generations; reverted via git checkout -- and re-derived
  from the committed nodes.parquet, after which git hash-object matched HEAD for all four
  protected planes (D2A adversarial review, attack 19).
scope: [macro]
confidence: verified
---

Found during `WS:PROPHET-US-V4-RECOVERY` wave d2 child D2A (2026-08-18): the review-fix
builder ran the commissioned literal re-bake, observed the divergence, reverted all four
protected planes via `git checkout --`, and re-derived the identity_resolution sidecar
from the committed graph instead. The committed D2A artifact therefore reflects the fixed
deriver over the committed 3,878-node generation, with protected planes byte-identical to
HEAD (hash-verified in the D2A adversarial review, attack 19).
