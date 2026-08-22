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

# CPI-H1 + A4G closure addendum (same session, Sol's second gate, 2026-08-21Z)

Sol reviewed the A-waves (PASS), kept A4 registration on HOLD, and authorized two bounded
waves in parallel. Both are now MERGED and verified live:

- **CPI-H1** (PR #6193, merge `f74d680ce23c` 16:11:07Z): the CPI truth-consumer contract
  is canonical and machine-enforced — see the WS CPI-H1 wave entry for the full
  disposition. **FREEZE D1(c) IS RELEASED** (`research/imce/IMCE_D1C_RELEASE_RECORD.md`,
  effective on the verified merge). Two Opus red-team rounds; the late `ruling-graph`
  pack red was this PR's own truth_schema rewrite breaking two verbatim source-quote
  pins (CPI-U12/U22) — healed to the ruling-5 law with build products regenerated.
  ESCALATED TO SOL: seven class-subset advisory rows (CPI-002/004/005/008/011/014/015).
- **A4G** (PR #6189, merge `de3a8ecdb845` 13:20:37Z): contract V1.1 + YAML encode all 18
  AG rulings; DEFF struck; N ≤ raw closed blocks; A4 packet byte-ready and PROPOSED,
  NOT REGISTERED. Treasury CMT honestly S-pending (owner-direct fetches timed out).

**verified:** both merges via `gh pr view --json state,mergedAt,mergeCommit` +
`git merge-base --is-ancestor <merge> origin/main`; registry at 53 lines on origin/main
(29 + 24 append-only); validator module + release record present at origin/main.

**A4 gate (unchanged):** A4 proper opens only on Sol's acceptance of BOTH returns; then
criteria commit + declared_budget rows strictly before outcome access; next priority
after that is prospective observation activation. Open for Sol: the seven escalated
rows; boundary-date receipts; CMT verification; the phase-target→D5 mapping (binding
stop condition).

**do_not_redo (additions):** do not re-derive the A4G config_hash values (independently
reproduced twice against engine/trial_ledger.py); do not re-run the CPI-H1 row heals or
append further registry versions before Sol's disposition of the escalated rows; do not
treat the D1(c) release as authorization to append an issuer truth — vocabulary release
≠ content authorization, and every issuer truth still needs its own lawful basis.

# CPI-H1.1 + A4P closure addendum (Sol's third gate, 2026-08-21)

Sol accepted the second gate (CPI-H1 + A4G + #6203), kept A4 registration HELD, and
authorized two bounded predecessor waves in parallel. Both are now MERGED and verified
(server-side compare = identical to origin/main tip at merge time):

- **CPI-H1.1** (PR #6211, merge `5f9fbe23a300`): the seven escalated class-subset rows
  are RESOLVED — Sol adjudicated them legitimate specialized display consumers and the
  status-class envelopes incomplete. display gained exactly seven tokens, promoted_null
  gained sync_gauge_display, nothing else widened, zero registry changes; every added
  token proven required by ≥1 real row. The row⊆class subset invariant is now HARD law
  in the single canonical validator, binding validate_truth() and the CI scan (job
  confirmed gate:code / merge-gate-binding). Opus red-team ACCEPT on mutation-tested
  evidence; four hygiene fixes applied pre-merge.
- **A4P** (PR #6213, merge `18858570deea`): contract V1.2. Two red-team REVISE rounds
  dispositioned — round 1 caught a fabricated composite AG17 quotation (the A4G MAJ-2
  defect class recurring) and the order_softness construction readmitting GFC blocks;
  round 2 caught the promotion clock unpropagated to YAML/log and the AG14
  cohort-label contradiction. Final: order_softness-only targets; deterministic
  construction frozen (IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md, ≥2 floor,
  contract-governed admissibility, fail-closed era gate); B≤3 uniform, LEN excluded
  cell-level; historical arm = named_subset_basis [PHM, KBH], grind block usable
  FY2016–2019 only; share = 1.0 numeric; bootstrap 800/seed-7 on the registered
  block-cluster unit; six cell IDs minted identically in contract/YAML/disposition/
  packet; promotion clock ~2160 (ZERO historical credit) propagated everywhere with
  old figures demoted to labelled diagnostics; AP8 amendment entry consolidates both
  rounds; ruling 6 recorded PARTIALLY EXECUTED / OPEN with an honest disposition;
  Treasury availability upgraded to a first-party V-grade receipt (commissioning
  session, direct browser 2026-08-21, incl. the 2021-12-06 HS→MC series-break);
  packet leaves A4 proper exactly four mechanical acts, verbatim-or-abort. All three
  config_hash values stable and reproduced across both rounds.

**verified:** both merges via `gh pr view --json state,mergeCommit` + server-side
`gh api repos/{owner}/{repo}/compare/<merge>...main` → `status: identical` at merge
time (local fetch was intermittently timing out; the compare API is the proof).

**A4 gate:** opens only on Sol's acceptance of BOTH returns; A4 proper = the four
packet acts only, then STOP; next priority after = prospective observation activation.
FIVE escalations ride with the returns: (1) AG14 — may a ≥2-contributor read ever bear
the cohort label (named-subset labelling governs meanwhile); (2) ruling 6 OPEN — 0/8
month-level boundary receipts, dedicated housing-sector boundary-dating wave needed
(lane-1 gap 11); (3) DHI/TOL pre-FY2025 era receipting; (4) ratification of the six
minted cell IDs; (5) Treasury storage/reuse basis before persistent ingestion.

**do_not_redo (additions):** do not re-verify the eight envelope tokens' necessity
(proven by registry set-difference, one per adjudicated row); do not restore the
retired WARN-tier advisory functions (their absence is test-pinned); do not cite ~2149
or ~2153 as a promotion timeline (non-promotion diagnostics only — the promotion clock
is ~2160 at zero historical credit); do not present historical order_softness reads as
cohort claims (named_subset_basis [PHM, KBH] until DHI/TOL era receipts exist); do not
ingest Treasury CMT before the storage/reuse basis is settled.

# A4P.1 closure addendum (Sol's fourth gate, 2026-08-22)

Sol accepted A4P's architecture (amendments AP1-AP8 are FINAL, never reopened or rewritten) but
returned bounded REQUEST_CHANGES: seven rulings (R1-R7) closing every field A4 proper would
otherwise have had to invent, interpret, or choose. This build-worker packet implements all seven
as records-only edits to research/imce/* + agentos/*, on branch claude/imce-a4p1-records, DRAFT PR
#6237 (head 14ed224c4929), NOT marked ready, NOT armed merge-on-green, pending the commissioning
session's review and merge. This addendum records the state at the point the DRAFT PR opened; the
head SHA above will shift by one commit once this addendum + the WS wave entry's own PR-number
back-fill land (self-referential — the same defect every prior gate's addendum also carries).

- **R1** — retires the stale `effective_blocks_under_independent_shock_law_with_deff` YAML
  denomination (DEFF struck three gates ago at AG3); census confirms this was the ONLY live
  machine-readable hit anywhere in `research/ agentos/ config/ engine/ scripts/`; adds
  annotation-only supersession notes (additive, zero deletions) to the three hb0 lane-2 artifacts
  still recommending A4 register `rho_block`/print issuer-DEFF counts.
- **R2** — freezes the historical v0 population as PERMANENT `named_subset_basis: [PHM, KBH]` for
  the six registered historical cells (may never widen v0 after registration; later DHI/TOL
  archaeology may only support a future v1), separate from the prospective v0 eligible pooled
  cohort `[DHI, PHM, KBH, TOL]`, under a three-row label truth table (4/4 -> cohort; 2-3 ->
  named_subset + exact contributor list; <2 -> NOT_RECONSTRUCTABLE). This closes AP8's own open F2(d)
  escalation. Every live "pooled homebuilder stratum" occurrence is reworded with an
  annotation-marked "was" note — census confirms zero live, unannotated occurrences remain.
- **R3** — ratifies the six minted cell IDs and normalizes the sync family's market-risk cell from
  `forward_63d_drawdown_tail` to the canonical `forward_63_trading_day_drawdown_tail` everywhere it
  identifies the actual target/cell (YAML, contract MD, disposition, packet); historical log entries
  (this workstream's own amendment-log AG5/M2 entries) stay untouched as genuine historical
  statements; census confirms every remaining hit is either historical or annotation-marked.
- **R4** — adds a new packet section (§4a "A4 STATE TRANSITION, frozen verbatim-or-abort")
  enumerating every registration-state site (YAML `status`, `registration.*`,
  `requires_fable_adjudication`, all three `trials[].status`; contract MD's Status header and §15a
  freeze-location/repository-pin prose; the packet's own STATUS header) with byte-exact old->new
  pairs; both placeholder procedures (`repository_pin_observed` via `git rev-parse origin/main`
  before any A4 edit; `config_hash` via `git hash-object` on the as-stamped-registered contract MD,
  after the MD edits and before the YAML write) are frozen deterministically. **A4P.1 itself
  performs NONE of these flips** — every registration-state field is byte-identical to its
  pre-A4P.1 value; only the version/gate header and the R1/R2/R3/R5/R6 substantive fields changed.
- **R5** — settles Treasury CMT's storage/reuse disposition as `GO_LIMITED`, Sol's exact
  scope+basis quoted verbatim and attributed, closing the prior wave's escalation item 5. PMMS
  stays HELD, FRED/ALFRED stay excluded, NAR storage stays prohibited — all three UNCHANGED.
  GO_LIMITED authorizes a FUTURE ingestion design only; this wave ingests nothing.
- **R6** — keeps boundary receipts honestly open: `month_boundaries_receipt_status:
  proposed_not_yet_receipted` is UNCHANGED; a new YAML block plus mirrored contract-MD and
  boundary-table prose name exactly the two lawful post-registration dispositions (receipt from a
  lawful first-party source, or `NOT_RECONSTRUCTABLE_FOR_V0_OUTCOME_PARTITION`), forbid moving a
  registered v0 boundary after outcome inspection, and require a new preregistration version for
  any scientifically necessary different boundary. Zero receipts fabricated.
- **R7** — regenerates all three `declared_budget` row reason strings (V1.2.1 wording, PHM/KBH
  population phrasing, canonical target naming) and recomputes their `config_hash` values by
  importing `engine/trial_ledger.py`'s own `_hash`/`_canon` functions read-only (no `TrialLedger`
  instantiated, no ledger write) — cross-verified against a standalone hand-inlined reimplementation
  of the identical formula, byte-identical output. New hashes: `a3b8ac5c0d0205cb` (phase),
  `1d69c1fa6b897b6a` (sync), `309d76c3a8dfbb5c` (risk); superseded V1.2 hashes
  (`d4fb6b5f517fe32c`, `f76dc44e1f5edc18`, `3eff3ee65158e41b`) recorded, never dropped.

**Cross-cutting:** version bumped `1.2` -> `1.2.1` (`amendment_gate: A4P1`,
`amendment_gates_applied: [A4G, A4P, A4P1]`, `amendment_gate_authority:
sol_fourth_gate_verdict_2026_08_22`). Amendment log gains a new append-only section (`AP9.R1`-
`AP9.R7`), recording each ruling, its edit sites, the superseded hashes, and the closure of the
Treasury-storage and cell-ID-ratification escalations. Sol's explicit conditional authorization to
start A4 proper without a further Sol roundtrip — quoted verbatim, provided A4P.1 lands exactly as
frozen with no new substantive finding — and the four A4-proper acts are recorded in the amendment
log's new section and cross-referenced from the packet's four-acts list (§6).

**verified:** `python3 -c "import yaml; yaml.safe_load(...)"` on the candidate YAML exits 0;
`python3 scripts/agentos.py validate` exits 0; the hash-parity scratchpad script's output matches
the packet's three `config_hash` values byte-for-byte, cross-checked by an independent
hand-inlined reimplementation; `git diff --stat origin/main HEAD` touches only the OWNED FILES
named in this wave's commission.

**A4 gate:** unchanged in substance — A4 proper opens only on the commissioning session's
acceptance of this wave (Sol's fourth-gate rulings applied as frozen, no new substantive finding
surfacing on review), executing exactly the four acts named in `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`
§6, using the byte-exact transition table in that document's new §4a. No auto-roll; no issuer
truth appended; no outcome access before the criteria/registration commit.

**do_not_redo (additions):** do not reopen or rewrite A4P's AP1-AP8 amendments — this wave is a
bounded preflight closure on top, never a redesign; do not widen the historical v0 population past
`named_subset_basis: [PHM, KBH]` for v0 — permanent, DHI/TOL archaeology may only ever support a
future v1; do not fabricate a boundary receipt to close ruling 6 — registration-with-open-receipts
is the explicit law now; do not execute A4's state transition from anywhere but the packet's own
§4a — every flip is byte-exact and verbatim-or-abort; do not re-derive the three `config_hash`
values by hand without importing `engine/trial_ledger.py`'s actual functions — the formula is a
pure function of `(family, n, reason)` and any hand-approximation risks a silent mismatch.
