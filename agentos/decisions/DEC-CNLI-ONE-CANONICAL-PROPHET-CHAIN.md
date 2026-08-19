---
key: CNLI-ONE-CANONICAL-PROPHET-CHAIN
question: >
  Does CN-Limit build its own candidate population, grader, identity plane,
  event store, or lifecycle — or extend the canonical China Prophet chain?
answer: >
  Extend the canonical chain only. The candidate plane stays
  engine/china_prophet_shadow.py → data/china_prophet_rank/candidates.parquet
  (additive nullable anatomy after PR-0B is proven live); the selected-board /
  T+1 path grader stays engine/china_standout_track.py; identity, company
  events, sector membership, and nightly advancement stay with their canonical
  owners. CN-Limit adds exactly two projections: derived anatomy on canonical
  candidate rows, and a referential immutable prediction/grade/correction
  sidecar (china_prophet_rank.cn_limit_research.v1) that creates no candidate
  universe, identity, lifecycle, or second grader.
rationale: >
  A duplicate candidate plane or grader creates diverging truth: two stores
  answering "what was the candidate set / what happened" differently destroys
  attribution, champion-era reconstruction, and honest G4 ablation. Every
  past incident class in this program (duplicate tapes, second ledgers,
  parallel graders) traces to a shadow store drifting from the owner plane.
  Referential binding — candidate_row_id + snapshot digest — preserves one
  truth while keeping CN-Limit's forward record immutable.
alternatives:
  - option: Dedicated CN-Limit candidate store and grader
    why_not: >
      Diverging truth; breaks keep-first identity and digest binding; the
      no-rebuild map (freeze §11) forbids a second candidate population,
      grader, identity plane, event store, composite, or lifecycle.
  - option: Write CN-Limit fields directly into the candidate writer now
    why_not: >
      Races the PR-0B telemetry seam; candidate-plane runtime edits are
      blocked until PR-0B lands and is proven live on real rows.
evidence:
  - "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md §8, §11, §12"
  - "engine/china_prophet_shadow.py; engine/china_standout_track.py (canonical owners on main)"
  - "DSC:CN-PR0B-NOT-LIVE-BLOCKS-CANDIDATE-PLANE"
affects:
  - "WS:CN-LIMIT-ALPHA"
  - "engine/china_prophet_shadow.py"
  - "engine/china_standout_track.py"
  - "research/cn_limit/"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

Sol R6 final architecture freeze. See also DEC:CN-PROPHET-RANKS-BY-BOARD-INDEPENDENT-INTELLIGENCE
for the standing provenance rule on what may enter the Prophet scorer.
