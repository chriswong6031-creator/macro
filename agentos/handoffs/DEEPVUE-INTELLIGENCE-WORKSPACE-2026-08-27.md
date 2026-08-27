---
workstream: "WS:DEEPVUE-INTELLIGENCE-WORKSPACE"
session: claude/deepvue-w2a-workspace
model: fable
ended_because: complete
prs: [6473, 480]
mission: >
  Execute W2-A — versioned workspace schema + lossless migration — end to end
  under the explicit Sol commission of 2026-08-26: freeze workspace_layout.v1
  on Mastermind's existing chart_layouts owner, implement the Macro contract
  vertical and the Terminal migration/persistence/renderer/UX, survive
  adversarial review, land Macro-first, deploy, prove the guest production
  boundary, and stop before W2-B.
state_before: >
  W0-B/W1-A/W1-B/W1-C done. Terminal persisted chart-only layouts
  (LayoutConfigV2 over chart_layouts, blind upsert, no revision law, no
  rename/duplicate/import/export); no canonical workspace contract, no widget
  graph; workspace_layout.v1 existed only as a docket sketch.
changed:
  - path: research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md
    what: >
      The frozen contract with Amendments A1-A3 + NB-F recorded in-file: real
      runtime grammar, direction-scoped lossless law, canonical number/UTF-8
      form, wire mode, fail-closed projection, two-attempt conversion guard,
      content-match retry success, loaded-row-id ABA fence, key deny-list.
  - path: engine/intelligence_workspace/workspace_layout.py
    what: >
      Pure reference validator/migration/projection with frozen vocabularies;
      strict (write/import) and tolerant (read) forms; canonical digest law.
  - path: contracts/intelligence_workspace/
    what: >
      workspace_layout.v1.schema.json plus 25 golden vectors + MANIFEST at
      digest 3e7c1c50faf8b03b4fa2f3ad2c66db3ebf9ba3ebd93bbb15b228654c382ff339.
  - path: terminal (mastermind-terminal PR 480)
    what: >
      lib/workspaceLayout.ts + workspaceMigrate.ts (digest-pinned mirror),
      layouts.ts CAS save/rename/duplicate with id fence + retry-success,
      /api/layouts ops with server-side validation, TerminalShell workspace
      renderer (chart primary + brain dock membership + unsupported tile),
      LayoutMenu three-zone evolution per the committed design spec, i18n
      Workspaces noun, e2e + screenshots; mm.ws untouched.
verified:
  - claim: Both PRs merged in the frozen order with green required checks.
    command: gh pr view 6473 / gh pr view 480 --json state,mergeCommit.
    result: MERGED f507a25aee69 (macro), b1b21a17f843 (terminal).
  - claim: Deployed identity runs the merged Terminal code.
    command: ssh VPS bash /opt/terminal/terminal-build.sh.
    result: "DONE — live = origin/master @ b1b21a17f843, restart 06:11:20Z, healthy."
  - claim: Cross-repo vector parity at the final digest, both modes pinned.
    command: shasum both fixture dirs + both suites' digest tests.
    result: 25 files byte-identical; 3e7c1c50… pinned in both repos.
  - claim: Three-round adversarial review converged to PASS on both repos.
    command: Opus reviewer packets on exact heads 8b4d3265/afe87f98/c305b0a9 (macro), 37251687/495327db/085ea119 (terminal).
    result: >
      Macro: 2 BLOCKER + 8 MAJOR repaired via A2/A3+NB-F, final PASS.
      Terminal: 3 BLOCKER + 5 MAJOR + M5b repaired, final PASS. All probes re-run CLOSED.
  - claim: Guest production boundary proven in a real browser on the deployed build.
    command: In-app browser session on app.mastermind-x.com/terminal?symbol=AAOI.
    result: >
      Workspaces menu guest states exact (gate, disabled save/import/dock,
      no raw codes); gate opens the signup funnel; W1-C receipt strip
      "INOD From your question overrode AAOI" streamed live inside the
      workspace renderer with a well-formed ai_context_client.v1; 1440/820/390
      zero horizontal overflow.
  - claim: Suites green at the merged heads.
    command: pytest (macro focused suites) / tsc + vitest + playwright (terminal).
    result: >
      Macro 240 contract tests + 67 context-compiler; Terminal 3,458 vitest,
      35 e2e passed / 12 documented skips; one full-responsive CI red
      adjudicated environment by rate (master green on same base, churning
      failure sets, 3/3 local passes of the only repeat) and green on rerun.
unverified:
  - claim: Signed-in persisted-user journeys in production (create/save/reopen/rename/duplicate/export/import, stale-revision fork, cross-account RLS half).
    what_would_verify: >
      An authorized signed-in production principal (+ a second account)
      executing commission §22 items 2-14 on the live Terminal. CI proves the
      mechanisms end-to-end against the fixture store; the fleet holds no
      production principal and account creation by a session is prohibited.
unresolved:
  - >-
    The workspace menu has no phone entry point (existing product law: toolbar
    hidden ≤640px) — phone management UX would be its own commissioned wave.
  - >-
    W1-B latency and deep-provider availability residuals unchanged by design.
next_actions:
  - Return this receipt to Sol; W2-B remains held for a new explicit commission.
  - >-
    When an authorized production principal (plus a second account) exists,
    execute the signed-in production proofs and upgrade the persisted-user
    capability from BUILT_NOT_PROVEN.
do_not_redo:
  - Do not add a second workspace store, table, or migration ledger — chart_layouts + CAS is the frozen law.
  - Do not persist workspace payloads through the legacy blind-upsert path (the route guard exists for this).
  - Do not swap the strict/tolerant migration directions — write/import refuses, read tolerates with disclosure.
  - Do not re-freeze the vectors without re-pinning the digest in BOTH repos in the same landing order.
  - Do not implement W2-B propagation behavior on top of the static link-group vocabulary without its own commission.
danger_areas:
  - >-
    The golden vectors are the cross-repo law: any change to
    engine/intelligence_workspace/workspace_layout.py or the TS mirror must
    regenerate vectors and re-pin the digest in both repos, Macro first.
  - >-
    BrainWidget's singleton callbacks are write-through-bound; a future edit
    that moves them back into the mount-once effect resurrects the dead-refs
    regression (brainWidgetRebinding.test.ts pins it).
  - >-
    The full responsive e2e suite is variance-prone on shared runners; judge
    reds by rate against master's baseline before treating them as real.
---

## One-line handoff

W2-A is merged, deployed and production-proven for guests: one versioned
workspace law (chart + brain generic graph, lossless migration, zero-DDL CAS
persistence, full management UX) over the existing chart_layouts owner, with
three-round adversarial convergence recorded as freeze amendments; signed-in
persisted-user proof waits on the external principal gate, and W2-B is
explicitly unstarted.
