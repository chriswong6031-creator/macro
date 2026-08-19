---
key: GRAPH-REPUBLISH-RETIMES-EVERY-CANDIDATE-CLOCK
claim: >
  Republishing the reviewed recipient graph re-times EVERY candidate
  observation's known_at to the new graph_known_at uniformly (measured 64/64
  rows on defense21-v1), because candidate known_at folds the graph clock.
  Three consequences bind any future graph-minting PR: (1) any test or gate
  that byte-compares live-rebuilt candidate rows (or their observed_known_at)
  against a committed manifest reds on every legitimate republish — the
  suppression/correction manifest pair is an IMMUTABLE sha-bound incident
  chain and must never be re-stamped to chase the clock (measured: re-stamping
  candidate_historical_suppressions.v1.json broke the correction binding and
  redded 7 quarantine tests); (2) a candidate-level known_at is USELESS as a
  "newly attributable" discriminator after a republish — it carries zero
  per-row information; the row-level discriminator is the attributing
  ownership path's own known_at (ownership_path_refs resolved against the
  graph), which stays put for old paths and moves only for genuinely new
  ones; (3) the publication frozen-clock gate ("recipient graph known_at is
  after the frozen generated_at clock") reds the render lane from mint time
  until main's next candidate projection freeze — so a graph PR merges only
  after a freeze commit postdating its graph clock, and the two transitional
  first-seen candidates a new chain mints are issued forward by that same
  freeze.
falsifier: >
  A candidate build whose rows carry per-row attribution clocks decoupled from
  graph_known_at (e.g. known_at = max(event known_at, attributing-row
  known_at) instead of the document clock) would collapse consequence (2)
  back to a simple clock comparison; a projection lane that re-freezes on
  every 30-min run rather than only on data changes would shrink consequence
  (3) to minutes and make the merge-ordering constraint irrelevant.
so_what: >
  Found while shipping defense21-v1 (PR 5932): the naive graph-level temporal
  escape bound was proven vacuous by adversarial review (the 2026-08-10
  8-row incident class would have been excused), and the fix is the row-level
  ownership-path discriminator now in
  tests/test_government_revenue_candidates.py. Future graph republishers:
  never re-stamp the suppression/correction manifests, never bridge the
  frozen-clock red with a re-mint (a re-mint moves the clock FORWARD), and
  sequence the merge behind the next govrev freeze commit on main.
---
