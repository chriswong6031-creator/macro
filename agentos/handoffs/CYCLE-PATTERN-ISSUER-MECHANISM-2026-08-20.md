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

# A-wave closure addendum (same session, post-Sol-release, 2026-08-21Z)

Sol returned **PASS / ACCEPTED FOR LANDING** on the freeze and released HOLD-FOR-SOL.
This session then completed, in one continuous arc:

- **IMCE-00 landed:** PR #6127 squash-merged 2026-08-21T03:55:28Z (merge `ec44ae7d1659`),
  verified on origin/main. Release recorded as a PR comment naming Sol's verdict and the
  accepted head; `merge-blocked` removed only after that record.
- **A1/A2/A3 dispatched in parallel exactly as frozen** (three sonnet builder lanes →
  draft PRs), each Opus-red-teamed (verdicts: REVISE ×3), each revision adjudicated by
  Fable with rulings recorded IN the artifacts, each landed on concluded checks:
  - **A2** `IMCE_A2_CPI_TRUTH_VOCABULARY_AUDIT_V1.md` — PR #6147, merge `2a0fae4672ea`
    04:57:17Z. Adjudicated: D1(c) releases only on the APPLIED heal (not audit landing);
    F6 five promoted_null rows heal to conform to the matrix class rule.
  - **A1** `IMCE_CELH1_CYCLE_AUTOPSY_V1.md` — PR #6150, merge `44ac9b89ff9e` 05:19:45Z.
    Adjudicated: strict crossover predicate frozen (33 events, 16 bullish/17 bearish,
    2009-11-27 → 2025-12-05); pre-2010 question RESOLVED consistent with [G8-v5];
    E2 ends 2024-12-31 (true partition); quarantined-tape outcome clause elided.
  - **A3** `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` — PR #6148, merge `b7b173efde83`
    05:21:18Z. Adjudicated: survivorship population rule + Centex→PHM absorption
    category; two-key re-key (majority-month pooling, zero-collision); NVR separate
    stratum FROZEN; no pit_class tokens minted; ρ typed REQUIRED-BEFORE-A4.
- **Parallel-lane reconciliation:** an operator-account lane independently landed its own
  A1 packet (PR #6153, merge `0d5bc41d3d67`, 05:01:55Z: `CELH_CYCLE_AUTOPSY_2018_2026.md`
  + `research/imce/celh/` CSVs + a NOT_ACTIVATED prospective-registration YAML), framed
  in its own WS edit as "returned to Fable for adjudication". ADJUDICATED: canonical A1 =
  #6150's record; #6153 = ACCEPTED companion machine-readable evidence packet — its event
  tape is byte-consistent (same 33 events/16 bullish dates), CSVs carry bar-state columns
  only, registration stays NOT_ACTIVATED (A4-gated). U7 ruled: phase inside the existing
  epoch until a mechanism boundary receipt dates a new one.
- **Second parallel lane (A3):** the same operator account landed PR #6154 (merge
  `c15d76130046`, 05:42:56Z) — nine HB-0 adjudication artifacts + seven evidence packets
  under `research/imce/hb0/`, four DSCs, a `-hb0` handoff, and corrections C1–C3 proposed
  for Fable/Sol. ADJUDICATED: both A3 records stand as delivered evidence; lane-1
  (#6148)'s frozen operational rulings (NVR separate stratum, two-key re-key, no minted
  pit_class tokens) BIND pre-A4. **C1 ACCEPTED in direction** — LEN's 10-K MD&A does
  disclose a 14% cancellation rate (verified in `hb0/evidence/L2_defs_DHI_LEN.md` rows
  3/3a) while stating NO formula, so the exclusion stands on the restated ground ("no
  stated formula — denominator unverifiable — plus era-correlated press-release
  absence") and the freeze's original reason owes an amendment-log entry at the A4 gate.
  **C2 (B=5 block-hardening vs the #6148 frozen 7-list) and C3 ([A18] extension)
  DEFERRED** to the Sol/Fable A4-gate adjudication with both block lists on the table;
  the six elections in `hb0/IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §8 land there too.

**verified:** every merge above re-verified via `gh pr view <n> --json state,mergedAt,mergeCommit`
and `git merge-base --is-ancestor <merge> origin/main` (A2; A1/A3 pending the same check
from this closure worktree, whose HEAD already contains both merges); the parallel tape
consistency via `awk` field extraction of `celh_recognition_events.csv` against the
canonical §5.2 table.

**A4 gate (NOT authorized; no auto-roll):** minimum prospective share; ρ / statistical-unit
and power questions (Sol reserved these to the A4-gate adjudication); pit_class candidate
vocabulary; macro-series evidence at block boundaries; "2013 taper" boundary dates; G6
UNDERLYING_MACRO_OWNERS leg-list confirmation. Separately: the CPI-owned heal wave is the
D1(c) release condition — NO issuer truth before it lands, per the adjudicated ruling in
the A2 record.

**do_not_redo (additions):** do not re-run the A1 event derivation (two independent lanes
already converged byte-identically); do not re-open the A2 token census (re-derived
byte-exact by adversarial review); do not mint pit_class or consumer-vocabulary tokens
outside the A2 §8c / A3 gap-10 decision processes; do not treat #6153's registration YAML
as activated.
