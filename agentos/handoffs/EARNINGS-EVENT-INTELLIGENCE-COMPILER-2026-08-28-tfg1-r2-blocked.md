---
workstream: WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
session: claude/tfg1-r2-transcript-format-hardening
model: opus
ended_because: blocked
mission: >
  TFG-1 R2 (operation tfg1-r2-deterministic-transcript-format-hardening-20260827-v1):
  implement one deterministic transcript-local Q&A normalization satisfying the ratified
  R2 development truth without ticker/provider branches, guessed identity, model
  inference or production-publication widening; preserve AAPL exactly; then freeze the
  implementation head and spend the sealed eight-slot holdout once under the frozen
  source-only protocol. Return DRAFT / HOLD-FOR-SOL.
state_before: >
  TFG-1 v1 terminated at a development-gold falsifier and its records carrier (#6555) was
  Sol-accepted and merged as main 0b839e1926d9b8c9423cb6bf232b719bbeedd4db. R2 was
  NOT_BUILT: no branch, no PR, no implementation. The compiler admitted Q&A boundaries
  only on the literal "go ahead" terminal cue, which is the defect TFG exists to remove.
prs: [6591]
discoveries:
  - DSC:E3FMT-R2-GOLD-UNDERCOUNTS-ROLE-CONFLICTS-AND-OVERCOUNTS-CLEAN
  - DSC:E3FMT-ROSTER-DECLARATION-ORDERS-ARE-FALSE-FRIENDS
changed:
  - path: engine/company_intelligence/qa_reconstruction.py
    what: >
      Structural separator admission replaces the terminal-cue rule; three-way questioner
      identity (direct / explicit full-name proxy / unresolved); same-revision roster
      role evidence with the frozen five-key extended respondent; closed CEO/CFO/COO
      alias comparison with management_identity_conflict and unresolved_questioner_identity
      failure codes.
  - path: tests/test_company_intelligence_qa_tfg1_r2.py
    what: New focused R2 discriminator module, 31 tests, synthetic fixtures only.
  - path: tests/test_company_intelligence_qa_reconstruction.py
    what: >
      Two superseded assertions updated to the ratified law (a cue-less handoff now opens
      an exchange; a name mismatch refuses as unresolved_questioner_identity).
  - path: tests/test_company_intelligence_qa_generalization_e3c.py
    what: >
      GOOGL now recovers all nine real handoffs and rejects the false segment-0 boundary;
      it still refuses and publishes nothing, for a source reason rather than dialect.
  - path: research/earnings_intelligence/e3/e3a2_aapl_fy2026_q3_reconstruction_receipt.json
    what: >
      Anti-drift lock re-pinned to the R2 proof head with an r2_reproof block that marks
      is_frozen_implementation_head false.
verified:
  - claim: All 113 structural separators recovered on all 16 frozen development revisions, zero false boundaries.
    command: python3 <scratchpad>/r2/adjudicate.py <scratchpad>/r2/bodies
    result: "16/16 byte replay; separator sets exactly matching gold 16/16; gold total 113"
  - claim: AAPL production oracle unchanged by the generalization.
    command: python3 -m pytest tests/test_company_intelligence_qa_tfg1_r2.py -k aapl_boundaries -p no:randomly
    result: "pass - 7 exchanges / 26 answer turns / 68 replay spans"
  - claim: Focused Q&A suites green at the pushed head.
    command: python3 -m pytest tests/test_company_intelligence_qa_reconstruction.py tests/test_company_intelligence_qa_exchange.py tests/test_company_intelligence_qa_generalization_e3c.py tests/test_company_intelligence_qa_tfg1_r2.py -q -p no:randomly
    result: "91 passed, 0 failed"
  - claim: The R2 gold is internally coherent and reconciles to source at the separator layer.
    command: python3 <scratchpad>/r2/verify_r2_gold.py <scratchpad>/r2/bodies
    result: "16/16 replay, 16/16 separator sets, 97 direct re-derived independently, no defects"
  - claim: Agent OS records validate clean.
    command: python3 scripts/agentos.py validate
    result: "898 records - 0 error(s), 51 warning(s), all pre-existing"
  - claim: Holdout was never opened.
    command: git log -p --all -- research/earnings_intelligence/e3/ | grep -c holdout_bodies_inspected
    result: "holdout_bodies_inspected remains 0; no holdout body was fetched or read in this session"
unverified:
  - claim: Exact-head hosted CI concludes green on 636ad7fb.
    what_would_verify: "gh pr checks 6591 once the 12 ci-pack fan-out registers and all checks conclude"
unresolved:
  - >
    D1 - the ratified R2 gold declares 2 calls with explicit same-revision management role
    conflicts; the source carries 5 (ARRY, CTRE, plus BANR/Jill Rice, LTH/Erik Weaver,
    HTGC/Seth Meyer). Does not move the 9/7 partition, only the frozen refusal reason for
    three of the seven. Awaiting a Sol ruling.
  - >
    D2 - ARQQ (Nick Pointon) and FANG (Chad McAllaster) sit in the 9-call source-clean set
    but have management the revision never gives an office, so under the frozen amendment
    the true clean count is 7 and the 9/9 gate is unsatisfiable. Awaiting a Sol ruling.
  - >
    The holdout's QNA_SOURCE_CLEAN definition must be settled as part of that ruling. The
    gold's working definition counts role CONFLICT but not role ABSENCE, and freezing it
    would miscalibrate the power denominator on a non-replaceable single-use holdout.
next_actions:
  - >
    Read the Slack carrier C0BSBM78V1N thread 1787887767.050999 for Sol's ruling on D1 and
    D2 (DECISION_REQUEST at ts 1787890850.727919, head correction at 1787891121.543199).
  - >
    Apply the ruling to research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r2.json
    ONLY if Sol amends it. Never amend the gold on a worker's own authority.
  - >
    Re-run the 16-call adjudication. Every development gate must be green before anything
    else happens.
  - >
    Only then freeze the implementation head SHA plus timestamp, recording it in the
    e3a2 receipt with is_frozen_implementation_head true.
  - >
    Only after that freeze, open the exact 8 holdout revisions (ranks 17-24), verify their
    frozen SHAs under the canonical-JSON convention, and freeze tfg1.holdout_source_adjudication.v1
    for every slot BEFORE any compiler output. Under 6/8 clean is INSUFFICIENT_HOLDOUT_POWER.
  - >
    Run the GOOGL spent-falsifier regression after the freeze, then return RESULT on the
    carrier as DRAFT / HOLD-FOR-SOL. Do not merge.
do_not_redo:
  - >
    Do not re-verify that the R2 gold's separator layer matches source. It was checked
    twice at pickup - internally (all totals recompute, every call partitions exactly) and
    externally (16/16 byte replay, 16/16 separator sets, 97 direct re-derived). That check
    is spent; 113/97/6/103/10 is sound.
  - >
    Do not rebuild the roster/title parser from first principles. Four failure modes were
    measured and each produces a CONFIDENT WRONG binding, not a blank - see
    DSC:E3FMT-ROSTER-DECLARATION-ORDERS-ARE-FALSE-FRIENDS.
  - >
    Do not widen the CEO/CFO/COO alias table. CIO is excluded on purpose: CTRE declares
    James Callister Chief Investment Officer and tags him CFO, and aliasing that away
    erases a ratified role conflict.
  - >
    Do not reclassify a roleless, roster-unsupported non-questioner speaker as management.
    That was tried and it broke test_unexpected_third_party_refuses_rather_than_dropping;
    the two refusal states are distinct and both are pinned.
  - >
    Do not "fix" test_proof_receipt_matches_live_reconstruction by relaxing it. It is an
    anti-drift lock and its red means the module changed and needs re-proving.
  - >
    Do not amend the gold, freeze the head, unseal the holdout, arm merge-on-green, or
    merge #6591 before Sol rules. The v1 wave's whole value was refusing exactly this.
danger_areas:
  - >
    The holdout (ranks 17-24) is single-use and non-replaceable. Zero code changes are
    permitted after unseal, and the source-only slot adjudication must be frozen before
    any compiler output touches it.
  - >
    _parse_operator_identity and _qualifying_boundaries must agree on who was named; they
    share _handoff_hits for that reason. Changing one without the other reintroduces
    boundary/identity disagreement.
  - >
    Conflicting same-revision affiliations for the SAME questioner must stay unresolved.
    An early identity rewrite read only the last handoff and resolved them; the existing
    suite caught it.
  - >
    A sparse worktree omits data/, site/, mockups/, verify_shots/. Never git add -A an
    unexpected diff under those paths.
---

Blocked on a Sol ruling, not on implementation. The structural half of R2 is complete and
green; the two open questions are disagreements between the ratified gold and its own frozen
source, and every route past them without a ruling is a move the commission fences.

A competent stranger resuming this should read the DECISION_REQUEST on the Slack carrier first,
then this file, then the two discovery records. The compiler itself needs no further work to
satisfy the separator and questioner-identity gates.
