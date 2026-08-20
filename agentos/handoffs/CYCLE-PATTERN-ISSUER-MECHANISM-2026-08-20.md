---
workstream: "WS:CYCLE-PATTERN-ISSUER-MECHANISM"
session: claude/imce-00-architecture-freeze
model: fable
ended_because: complete
mission: >
  IMCE-00: adjudicate whether Mastermind creates a bounded Issuer Mechanism Cycle
  Extension under existing CPI governance, freeze canonical owners/ports, reconcile
  estate movement, and return an accepted architecture freeze or an explicit
  no-go — records only, no runtime, stop at a review-ready PR held for Sol.
state_before: >
  Sol's Round 3 bundle (main packet, Appendix A, Grok G0-G8 commission packet,
  prereg candidate MD+YAML, three CSVs) sat in ~/Downloads; no IMCE record existed
  anywhere in the repo; WS-STOCK-IDENTITY still showed W2 in_progress four days
  after PR #5643 merged; FIF-2A (#5983) had merged hours earlier; #6021 sat
  OPEN/DRAFT/[HOLD]; main at 9dcd4c24 when this session re-pinned.
changed:
  - path: research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md
    what: >
      NEW - the accepted architecture freeze: ten decisions D1-D10 ruled, owner/port
      matrix (incl. CHF/TXI non-overlap rows), composed episode binding with
      citation hardening, four pilot dispositions, source-rights ledger with
      PIT/vintage rider, measurement freeze with predetermined historical statuses,
      worker verdict table G0-G8, red-team disposition table (§10a), authorized
      waves A1-A4, no-runtime proof.
  - path: research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md
    what: >
      NEW - Sol's Round 3 prereg candidate with all 26 G7 amendments applied
      ([A1]-[A26] tags) plus G8 hardenings: prior-carry deleted, claim classes
      split three ways, survivorship/epoch-clock/vintage riders, R_t frozen now,
      underpowered_accruing status governance. Candidate only - NOT registered,
      no outcome run.
  - path: research/imce/IMCE_PREREGISTRATION_CANDIDATE_V1.yaml
    what: NEW - lossless machine-readable projection of the V1 contract (MD binds).
  - path: agentos/decisions/DEC-CPI-ISSUER-MECHANISM-RESEARCH-EXTENSION-NOT-NEW-ENGINE.md
    what: NEW - the durable WHY for the freeze (question/answer/rationale/alternatives/evidence).
  - path: agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md
    what: NEW - program record; waves IMCE-00 (awaiting_ci) + A1-A4 (todo, gated on Sol acceptance).
  - path: agentos/workstreams/WS-STOCK-IDENTITY.md
    what: >
      STALE-FIELD HEAL ONLY - W2 status in_progress -> done with merge receipt
      (#5643 merged 2026-08-16T18:48:33Z), both stale next_action fields replaced
      with factual state; W3-W7 untouched.
  - path: agentos/handoffs/CYCLE-PATTERN-ISSUER-MECHANISM-2026-08-20.md
    what: NEW - this handoff.
verified:
  - claim: "PR #5643 merged, #5983 merged, #6021 open+draft+HOLD"
    command: "gh api graphql (batched pullRequest query for 5643/5983/6021)"
    result: "MERGED 2026-08-16T18:48:33Z / MERGED 2026-08-20T05:28:35Z / OPEN isDraft:true"
  - claim: "Zero IMCE naming or trial-family collisions"
    command: "grep -ril imce research/ agentos/ docs/ config/; grep -c imce data/trial_ledger.jsonl"
    result: "no files; 0 rows (1,665-row ledger; existing rf.cycle_pattern.* families enumerated)"
  - claim: "CPI consumer-vocabulary defect real, and worse than Sol's packet said"
    command: "sed/grep over config/cycle_pattern/truth_schema.md:69-73 + consumer_matrix.yml:35-53 + python enumeration of all 29 truths.jsonl rows (G0+G8 receipts)"
    result: ">=4 coexisting vocabularies; orphan tokens display_descriptive/research_factory_intake/display_only in neither authority; guard is a literal-path scan by its own docstring"
  - claim: "HAR-1 analogue null located and binding"
    command: "python json scan of data/cycle_pattern/truths.jsonl for 'analog'"
    result: "CPI-017 status=promoted_null, HAR-1 kNN half-cycle retrieval"
  - claim: "QLedger 63d rung exists; >63d fenced in live grader"
    command: "sed -n engine/qledger.py:114 + config/ruling_graph.yml LH-U6 (G0+G8 receipts)"
    result: "GRADE_HORIZONS=(5,21,63); LH-U6 no_build with off-render research-grader carve-out"
  - claim: "CELH price history available in canonical store; 2W tape computable"
    command: "G2 lane: lib.store.read('yahoo','CELH') + reproducible script (in scratchpad)"
    result: "4,921 daily bars 2007-01-22..2026-08-12; 16 completed-bar 2W bullish crosses; 7/16 non-positive +63td"
  - claim: "All 22 rights rows verified with zero decision reversals"
    command: "G6 lane: live fetches/browser reads of FRED/SEC/SEMI/WSTS/TrendForce/Census/FDIC terms 2026-08-20"
    result: "GO_LIMITED overall; FRED clause (q) bars store/cache/archive independent of AI clause"
  - claim: "V1 YAML parses"
    command: "python3 -c 'import yaml; yaml.safe_load(open(...))'"
    result: "OK, schema imce.preregistration_candidate.v1"
  - claim: "agentos records validate"
    command: "python3 scripts/agentos.py validate"
    result: "exit 0, 0 errors"
unverified:
  - claim: "Census effective-N figures (HB 5-7 blocks, memory 2+1, banks ~3) are exactly right"
    what_would_verify: >
      They are adjudicated census judgments from web-sourced lanes (G3/G4/G5 packets,
      receipts inline in the freeze); an independent re-count against primary filings
      would verify. Their USE was red-teamed (G8); their provenance was not re-run.
  - claim: "NY Fed CRSP-FRB link file coverage/columns (bank stock bridge)"
    what_would_verify: "successful fetch of the newyorkfed.org file (403-blocked this session); named as the banks unblock condition"
  - claim: "#5643 delivered exactly 31,119 era-pinned events over 22 names"
    what_would_verify: "opening PR #5643's diff; taken from Sol's packet + PR title, not re-counted"
unresolved:
  - "Sol/Chairman acceptance of the freeze - the PR is deliberately HELD (HOLD-FOR-SOL) and must not merge until released"
  - "A2 (CPI truth-contract audit) must land before any issuer truth is appended - scoped to full token enumeration over all 29 registry rows"
  - "IMCE-HB-0 owes the survivorship census (named delisted/bankrupt/acquired builders) and the per-source vintage audit"
  - "preregistered minimum prospective share before promotion - value TBD at registration (flagged in YAML)"
next_actions:
  - "Sol/Chairman review the PR; on acceptance, release the hold and merge (docs-only PR; the spurious Workers X is ignorable)"
  - "On acceptance: commission A1 (CELH autopsy - zero outcome computation), A2 (CPI audit), A3 (HB-0 census) in parallel per freeze §13"
  - "A4 (IMCE-03) only after A2+A3: declared_budget trial-ledger rows, criteria commit strictly before any outcome access"
do_not_redo:
  - "The G0-G8 evidence lanes (owner census, CELH sources+tape, memory/HB/bank censuses, 22-row rights verification, prereg power analysis, red team) - packets summarized in the freeze; re-verify only what a moved main invalidates"
  - "The ten-decision adjudication and the 26+G8 amendment set - supersede via a new DEC, never by silent re-litigation"
  - "Do not re-open the episode-anchor question (composed binding ruled; no new episode ID) or the parent question (CPI ruled)"
danger_areas:
  - "A recorded HOLD binds every merge path - do not arm merge-on-green on this PR; do not admin-merge it"
  - "The sub-floor prior-carry was deliberately DELETED (G8-B7) - restoring 'prospective PRIOR' language reopens a laundering path"
  - "A1 must not compute forward returns - the two-commit discipline depends on it (G8-B1)"
  - "underpowered_accruing must never appear as a CPI truth status without schema+matrix amendment (G8-M7)"
  - "Mechanism epochs vs identity epochs: different record classes; conflating them recreates the rival-epoch-stack violation (G8-M5)"
prs: []
decisions:
  - "DEC:CPI-ISSUER-MECHANISM-RESEARCH-EXTENSION-NOT-NEW-ENGINE"
---

# Production proof state

**Not owed — records only.** This wave changes seven research/agentos files and touches
no runtime, data, workflow, UI, or test path. No next wave has started: A1–A4 are gated
on Sol/Chairman acceptance of the freeze, and this session stopped at the review-ready,
HELD PR exactly as the commissioning handoff §13 required.

# Worker verdict table (for the cold stranger)

G0 census CONDITIONAL_GO · G1 CELH sources PASS · G2 CELH tape PASS · G3 memory
CONDITIONAL_GO (2+1-open blocks) · G4 homebuilders CONDITIONAL_GO (5–7 blocks) ·
G5 banks GO_FEASIBILITY/DEFER-stock · G6 rights GO_LIMITED (22/22, zero reversals) ·
G7 prereg PASS (statuses predetermined; 26 amendments) · G8 red team REVISE → all
blockers/majors amended (freeze §10, §10a carry the full table and dispositions).
