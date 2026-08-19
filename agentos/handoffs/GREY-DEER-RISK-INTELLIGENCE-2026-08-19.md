---
workstream: "WS:GREY-DEER-RISK-INTELLIGENCE"
session: "claude/grey-deer-gd0a-landing (worktree grey-deer-repo-landing-5cbf52)"
model: fable
ended_because: complete
mission: >
  GD-0A durable landing: make Grey Deer a first-class canonical program —
  land Sol's architecture freeze and the hardened Turn-4 execution packets
  byte-for-byte under research/grey_deer/, mint the workstream, eight
  decisions and this handoff, register the program in
  config/mastermind_programs.yml, and regenerate the system map. Zero runtime
  behavior change.
state_before: >
  No Grey Deer program identity existed anywhere in the repo (repo-wide grep
  for grey.deer/grey_deer/GREY-DEER returned only the unrelated
  greydeercapital.com brand-site block in app/deploy/Caddyfile). The
  architecture freeze, command packet, wave matrix and Grok GD-1 packet lived
  only in the operator's Downloads pack and chat. No registry entry, no
  workstream, no decisions.
changed:
  - path: research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md
    what: Sol's architecture freeze, landed byte-for-byte (sha256 c803569ae684 matches source pack).
  - path: research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md
    what: Hardened Turn-4 Fable command packet, byte-for-byte (sha256 ac7e0a3bbf7a), renamed from FABLE_COMMAND_PACKET_GREY_DEER_GD0_GD11 per the GD-0A landing packet's target names.
  - path: research/grey_deer/GREY_DEER_WAVE_GRAPH_AND_PR_ACCEPTANCE_MATRIX_2026-08-19.md
    what: Wave DAG / PR acceptance cards / path fences / collision fences, byte-for-byte (sha256 10d7d5dd4208).
  - path: research/grey_deer/GD1_GROK_SCIENTIFIC_REPLAY_HANDOFF_2026-08-19.md
    what: GD-1A/GD-1B Grok research protocol, byte-for-byte (sha256 a1e034e29970), renamed from GROK_GD1_HARDENED_SCIENTIFIC_REPLAY_PACKET per the landing packet's target names.
  - path: research/grey_deer/README.md
    what: One-page index — canonical files, document precedence, current next action, do-not-start list. No duplicated architecture.
  - path: agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md
    what: Program workstream with the full GD-0A..GD-11 wave graph, owns_paths fences, landmines (open-PR collision fences), do_not_redo.
  - path: agentos/decisions/DEC-RISK-STATE-HAZARD-POLICY-SEPARATION.md
    what: Three-answer separation decision (measured state / hazard / policy orthogonal; no blended score).
  - path: agentos/decisions/DEC-RISK-ENVELOPE-IS-CANONICAL-DERIVED-PROJECTION.md
    what: Envelope is a derived projection through one pure composer; not a truth store or authority source.
  - path: agentos/decisions/DEC-RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES.md
    what: Durable history stays in Chronicle/Reflex Registry/QLedger; no new event store.
  - path: agentos/decisions/DEC-PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR.md
    what: Board-hash-bound sidecar after rank; raw Prophet rank/population never mutated; counterfactuals preserved.
  - path: agentos/decisions/DEC-REPAIR-IS-ORTHOGONAL-AND-FIRST-CLASS.md
    what: repair_state is its own lifecycle; IMPULSE never repaints hazard green; lift contracts per owning policy.
  - path: agentos/decisions/DEC-PORTFOLIO-CONSUMES-NOT-RECOMPUTES-MARKET-RISK.md
    what: Macro owns market truth; Portfolio consumes the envelope, keeps book authority; legacy fusion becomes a compatibility adapter until GD-10.
  - path: agentos/decisions/DEC-SCOPED-REFLEX-CONSTRAINTS-NOT-FUSED-SHIELD.md
    what: Individually registered subtract-only policies; logical intersection; no fused shield or weighted veto router.
  - path: agentos/decisions/DEC-AUTO-EXIT-NOT-IN-GREY-DEER-V1.md
    what: Automatic held-position liquidation excluded from v1; future auto-exit needs a separate Chairman-approved, user-opt-in, forward-only gauntlet.
  - path: agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-19.md
    what: This handoff.
  - path: config/mastermind_programs.yml
    what: >
      New program grey-deer-risk-intelligence (market_intelligence /
      decision_engine / building / scope project), placed after
      market-regime-risk. Relationship keys reconciled to existing registry
      keys: market-regime-risk-intelligence→market-regime-risk,
      transmission-intelligence→policy-transmission-intelligence,
      live-entry-radar→market-timing-intelligence (Entry Radar's program home;
      no live-entry-radar key exists). decision_boundary deterministic_control
      with authority_sources pointing at the freeze + command packet (generator
      requires explicit sources for that class).
  - path: docs/MASTERMIND_SYSTEM_MAP.md
    what: Regenerated via the canonical generator only; not hand-edited.
  - path: tests/test_mastermind_system_map.py
    what: >
      Census pin bumped 59→60 with a dated comment (house style, mirrors the
      existing 98→99 GMI note) — the deliberate one-line companion edit any
      program registration requires; no other assertion touched.
verified:
  - claim: AgentOS store validates with zero errors including the 10 new records
    command: python3 scripts/agentos.py validate
    result: "243 records (28 workstreams, 81 decisions, 63 discoveries, 71 handoffs) — 0 error(s), 22 warning(s); the two new warnings are phantom-owns-path on future paths (tests/test_risk_envelope, agentos/handoffs/GREY-DEER- prefix), same class as WS-LIVE-ENTRY-RADAR's future-path warnings"
  - claim: System map regenerates cleanly and the committed copy is byte-identical to the generator output
    command: python3 scripts/build_mastermind_system_map.py && python3 scripts/build_mastermind_system_map.py --check
    result: "Wrote docs/MASTERMIND_SYSTEM_MAP.md; --check: OK … is current (required full worktree opt-in first: python3 scripts/worktree_sparse.py full, because the generator path-validates site/ and data/ roots that a sparse tree omits)"
  - claim: Landed research files are byte-identical to Sol's source pack
    command: shasum -a 256 over source pack and research/grey_deer/ copies
    result: "All four sha256 pairs match: freeze c803569ae684…, command packet ac7e0a3bbf7a…, wave matrix 10d7d5dd4208…, Grok packet a1e034e29970…"
  - claim: Exactly one Grey Deer program identity exists in the repo
    command: grep -riln 'grey.deer|grey_deer|GREY-DEER' --exclude-dir=.git . (pre-landing)
    result: "Pre-landing: only app/deploy/Caddyfile (greydeercapital.com brand site, unrelated). Post-landing: research/grey_deer/, the ten AgentOS records, one registry key, generated map — one program identity"
  - claim: No open PR collides with any changed path
    command: gh pr view 5953 --json files; gh pr list --state open --search "mastermind_programs"; gh pr list --state open --search "MASTERMIND_SYSTEM_MAP"; gh pr list --state open (40 PRs reviewed)
    result: "No open PR touches config/mastermind_programs.yml, docs/MASTERMIND_SYSTEM_MAP.md, or any grey_deer/GREY-DEER path; #5953 (China Alpha) touches only its own agentos/research files — different filenames, no overlap"
  - claim: Change scope is records/semantic-registry only — no runtime, CI, site, data, template, engine or collector paths
    command: git diff --name-only origin/main...HEAD (three-dot merge-base form — plain origin/main diff picks up the nightly's own data ticks on a moving main)
    result: "Only research/grey_deer/*, agentos/*, config/mastermind_programs.yml, docs/MASTERMIND_SYSTEM_MAP.md"
  - claim: Registry and AgentOS test files pass on the changed tree
    command: python3 -m pytest tests/test_mastermind_system_map.py tests/test_agentos_schema.py tests/test_agentos_compile.py tests/test_agentos_status.py -q
    result: "First run: 1 failed, 148 passed — the sole failure was the deliberate census pin (len(programs)==59) catching the 60th program; bumped to 60 with a dated comment; re-run tests/test_mastermind_system_map.py -q: 15 passed"
unverified:
  - claim: The Grok research operator has actually begun GD-1A
    what_would_verify: "A gd1 PR or a hash-pinned research/grey_deer/gd1/GD1_PREREG_2026-08-19.md landing from the Grok lane; the operator relay (2026-08-19) says Grok runs in parallel and submits PRs"
  - claim: Sol accepts the reconciliations (renamed target filenames per the landing packet; registry keys mapped to existing keys; schema-enum mappings on the workstream record)
    what_would_verify: "Sol review of the GD-0A PR — every reconciliation is itemized in the PR body"
unresolved:
  - "GD-1A prereg hash not yet pinned (Grok lane owns it; GD-1B may not open outcomes before it lands)."
  - "GD-2/GD-4A/GD-3 archaeology commissioned as bounded read-only scouts; findings must be reconciled against the freeze before any build."
  - "Protected open PRs at landing time: #5925 (entry_radar live_pack), #5929 (radar transport), #5928 (Prophet Lab API), #5954 (CI legacy-jobs classification), #5948 (backfill push path) — collision fences in the wave matrix §5 stand until each resolves."
next_actions:
  - "Merge the GD-0A PR under normal governance (merge-on-green armed; no admin-merge exception for Grey Deer)."
  - "GD-1A: Grok executes the prereg + source-clock census under research/grey_deer/gd1/ (already commissioned; hash-pin before outcome access)."
  - "Reconcile GD-2 (settled envelope producer/consumer seam), GD-4A (CN/HK ledger freeze root cause) and GD-3 (live publisher seam) archaeology against the freeze; then author the GD-2 build packet."
  - "GD-4B/GD-4C build planning after GD-2 packet exists (safe-parallel set per wave matrix §2)."
do_not_redo:
  - "Do not re-derive the architecture from older risk masterplans (RISK_LAYER_DESIGN, contagion sensing, portfolio risk desk, market-risk bridge) — they are substrate only; the freeze supersedes their fused-authority constructions."
  - "Do not add legs/weights/consumers to engine/risk_state.py — frozen legacy compatibility (freeze §12)."
  - "Do not create a Grey Deer forward ledger, event store, or market-data plane — DEC:RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES."
  - "Do not mutate Prophet rank/population or hide candidates — DEC:PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR."
  - "Do not arm Mastermind brain/posture_decider.py or consume LLM probability_rolldown in any authoritative consumer."
  - "Do not implement automatic held-position exits — DEC:AUTO-EXIT-NOT-IN-GREY-DEER-V1."
  - "Do not start: Grey Deer policy authority, live Prophet sidecar behavior, Portfolio cutover, new model training, legacy risk-score re-weighting."
danger_areas:
  - "config/mastermind_programs.yml is shared and rarely edited — rebase carefully; the system map must be regenerated (never hand-edited) in the same PR as any registry change, and deterministic_control entries require decision_boundary.authority_sources or the generator refuses."
  - "Sparse worktrees: the system-map generator and any future GD build touching site//data/ need python3 scripts/worktree_sparse.py full first; never git add -A an unexpected data//site/ diff."
  - "The CI control-plane lane (#5954) is actively moving .github/ci/legacy-jobs.yml — a Grey Deer test needing CI registration must wait/rebase, never hand-edit the moving manifest."
  - "Any scripts/** edit sets authority_changed=true in the ship-loop guard and demands a genuinely green main to merge safely — GD-2+ builders must check main health before merging."
prs: []
decisions:
  - DEC:RISK-STATE-HAZARD-POLICY-SEPARATION
  - DEC:RISK-ENVELOPE-IS-CANONICAL-DERIVED-PROJECTION
  - DEC:RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES
  - DEC:PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR
  - DEC:REPAIR-IS-ORTHOGONAL-AND-FIRST-CLASS
  - DEC:PORTFOLIO-CONSUMES-NOT-RECOMPUTES-MARKET-RISK
  - DEC:SCOPED-REFLEX-CONSTRAINTS-NOT-FUSED-SHIELD
  - DEC:AUTO-EXIT-NOT-IN-GREY-DEER-V1
---

# GD-0A handoff — Grey Deer durable landing

**Status: architecture frozen / no runtime.** This wave landed records and
semantic registration only. A fresh session picks up from
`research/grey_deer/README.md` (precedence + next action), the workstream
record (wave graph + fences), and the eight decisions. The exact next
action is GD-1A prereg execution (Grok, commissioned) plus bounded GD-2/GD-4
archaeology in parallel; GD-2 build starts only after GD-0A is merged and the
archaeology is reconciled against the freeze.

**Authority note:** nothing landed here grants any capital, ranking, sizing,
gating or execution authority. Policy authority arrives only per-rule through
the freeze §10 gates or an explicit Chairman `temporary_operator_safety`
grant (freeze §11), each with its own named checkpoint in the wave matrix §6.
