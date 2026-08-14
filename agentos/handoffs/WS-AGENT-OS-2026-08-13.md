---
workstream: "WS:AGENT-OS"
session: claude/agentos-phase3-context-compiler
model: fable
ended_because: ci_handoff
mission: >
  Ship Agent OS Phase 3 (context compiler): register agentos/** in the existing context
  index and implement `agentos.py compile-context` — a bounded, cited, deterministic
  context_bundle.v1 for a workstream or free-text task.
state_before: >
  Phase 0 and Phase 2 merged (#5472 and follow-ups); compile-context was a stub printing
  a not-implemented warning; agentos/ was not in config/context_index.yml; handoffs/ was
  empty. All five architecture conflicts already ruled.
changed:
  - path: config/context_index.yml
    what: >
      Five agentos sources (workstreams+handoffs A4, decisions+discoveries A3, README A3;
      whole_file chunker for records), schema/*.yml deliberately not indexed, generated
      docs/AGENT_OS_STATE.md added to deny.
  - path: scripts/agentos.py
    what: >
      compile-context implemented (~1,200 lines): direct + free-text resolution (index
      hits vote, never inject content), by-field exclusions each named in `excluded`,
      authority-ordered sections with framing contracts, payload-priced token budget with
      always-included constraint tier and named overruns, pointer authority resolved from
      config/context_index.yml, superseded_by/supersedes shape validation (hard),
      workstream-cycle attributed to every cycle member, discovery_citation_counts shared
      between check_references and the compiler.
  - path: tests/test_agentos_compile.py
    what: new suite — seed compiles, negative fixtures, determinism, free-text seams, zero-writes.
  - path: tests/test_agentos_schema.py
    what: stub test replaced with the real contract; supersedes bare-key test added.
  - path: .github/ci/legacy-jobs.yml
    what: compile suite folded into the existing agent-os step (no new job — narrow-diff ceiling).
  - path: agentos/README.md
    what: compile-context usage + exit-code contract documented.
  - path: research/MASTERMIND_AGENT_OS_V1_IMPLEMENTATION_PLAN.md
    what: Phase 3 heading marked implemented.
  - path: agentos/workstreams/WS-AGENT-OS.md
    what: "W0 done (pr 5472), W2 done, W3 awaiting_ci (pr 5561); next_action updated."
verified:
  - claim: full record set validates clean after every change
    command: python3 scripts/agentos.py validate
    result: "18 records (6 WS, 9 DEC, 3 DSC, 0 handoffs pre-this-file) — 0 errors, 0 warnings, exit 0"
  - claim: all agentos suites green including the new compile suite
    command: python -m pytest tests/test_agentos_schema.py tests/test_agentos_status.py tests/test_agentos_compile.py -q
    result: 121 passed
  - claim: context-index suites unaffected by the corpus registration
    command: python -m pytest tests/test_context_index_schema.py tests/test_context_index_ingest.py tests/test_context_index_multirepo.py tests/test_context_index_packet.py -q
    result: 66 passed
  - claim: the CI manifest still parses with the folded-in suite
    command: python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index 0 --pack-count 12 --validate-only
    result: 187 jobs, 12 packs, valid
  - claim: every exclusion filter is load-bearing, not decorative
    command: "python -m pytest tests/test_agentos_compile.py -q  # after each of 12 hand-applied mutations"
    result: >
      12/12 mutations killed by a named test (budget, overrun signal, superseded and
      unresolvable-supersession, stale, affects gate, glob door, repo-scope strip,
      fail-closed re-widen, _flat dict+set determinism, superseded_by validation,
      supersedes shape); all restored by re-edit, tree clean.
  - claim: agentos corpus is discoverable through the real index loader with correct attribution
    command: "python3 -c 'from engine.context_index.sources import load_config, discover_files' # + discovery probe over config/context_index.yml"
    result: >
      all five sources resolve; records discovered A4/A3 as configured;
      docs/AGENT_OS_STATE.md denied; schema/*.yml absent.
unverified:
  - claim: free-text resolution against a BUILT index resolves real tasks to the right workstream
    what_would_verify: >
      after the nightly rebuilds .context-index/ post-merge, run
      `python3 scripts/agentos.py compile-context "Work on Prophet US entry timing"`
      on a machine with the index present; expect resolution=search, WS:PROPHET-US-ENTRY-TIMING.
  - claim: wave/PR join renders MERGED states on a full checkout
    what_would_verify: >
      run `python3 scripts/agentos.py compile-context --workstream AGENT-OS --text` where
      data/governance/active_builds.json exists (any non-sparse checkout after a nightly).
unresolved:
  - >
    The local Mastermind checkout at ~/Documents/Cluade/Mastermind predates
    config/strategic_state.yml (shipped 2026-08-11), so the P0 higher-law join degrades on
    this machine until that clone is pulled. The compiler's degraded line names it; pulling
    the sibling repo resolves it — nothing to fix in macro.
next_actions:
  - "Watch nothing: merge-on-green owns #5561 (armed). After merge, the first nightly rebuilds the index with the agentos corpus."
  - Run the two unverified checks on a full checkout with a built index.
  - Start Phase 1 (adoption) per the implementation plan — it is the only phase that makes handoffs like this one routine.
do_not_redo:
  - "Do not re-litigate compile-context architecture: search votes for a workstream, content comes only from the graph walk. Reviewer-verified; changing it reopens the other-program leak."
  - "Do not add a vector store or second retriever — plan §Phase 3 non-goal, reaffirmed in DEC:AGENTOS-CXI-R12-OVERRULED; revisit only against a measured miss-rate on research/context_index/BENCHMARK_RESULTS.md."
  - "Do not make higher-law/constraint items budget-tradable; the always-include ruling is deliberate and tested (test_a_binding_cap_never_costs_a_constraint)."
danger_areas:
  - >
    cmd_compile_context's exit-1 gate must stay restricted to record-local schema rules:
    CROSS_RECORD_RULES (dangling-ref, workstream-cycle, unreciprocated-supersession) are
    join failures and fail OPEN. Re-widening `fatal` reds every compile whose sibling is
    mid-rename (tested: test_a_dangling_citation_on_the_target_degrades_rather_than_refusing).
  - >
    The budget prices item JSON plus envelope tails; pricing excerpts alone under-reports
    the payload 2-6x (reviewer finding, fixed). If context_bundle.v1 grows a field, the
    cost function follows it automatically only because it serializes the whole item.
prs: [5561]
---

Phase 3 of `research/MASTERMIND_AGENT_OS_V1_IMPLEMENTATION_PLAN.md`, shipped from a
single session: Opus builder implemented against a pinned spec, an Opus red-team review
returned six blocking findings (all fixed and mutation-receipted in the same PR), and the
seeded store compiles 634–5,774 tokens per workstream against the 8,000 default budget.
This file is the store's first handoff record — written where ci_handoff.py already runs,
which is the steady-state cost the architecture promises.
