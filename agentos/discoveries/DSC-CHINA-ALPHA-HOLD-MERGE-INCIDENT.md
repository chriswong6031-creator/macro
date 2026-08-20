---
key: CHINA-ALPHA-HOLD-MERGE-INCIDENT
claim: >
  Label-based disarm does not hold a green PR. PR #5953 sat under a recorded
  CEO HOLD (Sol, 2026-08-19): `merge-on-green` removed at 09:58:28Z with a
  disarm marker comment, `merge-blocked` left on as the visible hold, GitHub
  auto-merge never enabled (`autoMergeRequest: null`, zero
  AutoMergeEnabled/Disabled timeline events). It was nevertheless
  squash-merged at 2026-08-19T16:05:16Z (merge commit c617be762ae7) by a
  direct merge action on the shared fleet/operator account, with armed
  sibling #5933 merged 8 seconds later (16:05:24Z) — a manual batch. The
  sweeper is exonerated by its own run ledger: merge-on-green.yml ran ZERO
  sweeps between 14:00Z and 18:00Z (first sweep 18:00:14Z, which then
  drained the armed GROK-CN packets 18:08–19:51Z), and its candidate
  selection (scripts/merge_on_green.py labeled_pulls) requires the
  `merge-on-green` label — `merge-blocked` alone is never a candidate. The
  head had gone fully green at 15:04:34Z (ci success + fences success +
  ci-authority success on fa791a32a051), so a plain squash-merge needed no
  --admin. On a shared token account, attribution ends at the account: a
  human UI merge and a fleet-session CLI merge are indistinguishable.
falsifier: >
  Any of: (a) a merge-on-green.yml run whose log names #5953 in the
  2026-08-19T14:00Z–18:00Z window (`gh run list --workflow
  merge-on-green.yml --created "2026-08-19T14:00:00Z..2026-08-19T18:00:00Z"`
  returned an empty set at investigation time — a run appearing there that
  processed #5953 re-attributes the merge to the sweeper); (b) an
  AutoMergeEnabledEvent or a merge-on-green LabeledEvent on #5953's timeline
  between 09:58:28Z and 16:05:16Z (the timeline query returned none); (c) a
  selection path in scripts/merge_on_green.py that admits a PR carrying only
  `merge-blocked` (labeled_pulls at scripts/merge_on_green.py:2585-2610
  filters on MERGE_ON_GREEN_LABEL only).
so_what: >
  A CEO/operator HOLD must be enforced by state that disables EVERY merge
  path — automation and humans — not by removing an arming label. Minimum
  hold protocol for a held PR, all four together: (1) remove
  `merge-on-green`; (2) verify GitHub auto-merge is disabled (`gh pr view N
  --json autoMergeRequest` must return null); (3) convert the PR to DRAFT
  (`gh pr ready --undo N`) — the only lever that also disables the UI merge
  button and `gh pr merge` for human actors; (4) a hold comment naming the
  holding authority and the release condition. Mark ready again only on that
  authority's explicit GO. Label conventions bind the sweeper, never people.
  Applies to any PR held for review by Sol, the operator, or a seat.
kind: constraint
confidence: verified
verified_at: 2026-08-19
verified_by: >
  GraphQL timelineItems on PR #5953 (LABELED/UNLABELED/AUTO_MERGE_*/MERGED
  events — no event between the 09:58:28Z disarm and the 16:05:16Z merge;
  autoMergeRequest null); gh run list --workflow merge-on-green.yml
  --created 2026-08-19T14:00:00Z..2026-08-19T20:00:00Z (first run
  18:00:14Z); scripts/merge_on_green.py labeled_pulls candidate filter
  (origin/main, lines 2585-2610: MERGE_ON_GREEN_LABEL only); gh run list
  --commit fa791a32a051 (ci success 15:04:34Z, fences success 14:18:13Z,
  ci-authority success 14:14:00Z); mergedAt census of the ten program PRs.
scope: fleet
workstreams:
  - WS:CHINA-ALPHA-INTELLIGENCE
  - WS:ALPHA-INTELLIGENCE-INTEGRATION
evidence:
  - "PR #5953 timeline (GraphQL timelineItems): labeled merge-on-green 08:17:15Z, labeled merge-blocked 08:43:08Z, UNlabeled merge-on-green 09:58:28Z, MergedEvent 16:05:16Z — no events between disarm and merge"
  - "gh run list --workflow merge-on-green.yml --created 2026-08-19T14:00:00Z..2026-08-19T20:00:00Z: first run 18:00:14Z"
  - "Grok packet mergedAt cluster: #5950 18:15:25Z, #5951 19:50:45Z, #5949 19:51:00Z, #5947 19:51:08Z, #5946 19:51:16Z, #5945 19:51:34Z, #5944 19:51:42Z — the sweeper's drain, hours after the incident merges"
  - "Head fa791a32a051 check conclusions: ci success 15:04:34Z, fences success 14:18:13Z, ci-authority success 14:14:00Z"
---

# The #5953 hold-merge incident (2026-08-19)

The revised-but-HELD China Alpha freeze artifact merged while awaiting Sol's
final freeze review. Content damage: none — the merged head fa791a32a051 is
byte-identical to the artifact Sol's revision pass produced, and the freeze
is NOT effective at merge (the masterplan's own §17 gates effectiveness on
Sol's review). Process damage: real — the recorded CEO hold did not bind the
merge path that fired. The `so_what` protocol above is the standing
mitigation until a stronger control (e.g. a hold label the fleet guards
enforce against `gh pr merge`) ships through its own reviewed wave.
