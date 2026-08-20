---
key: EXECUTIVE-MCP-SDK-CI-BASELINE-PR89
question: >
  Is Mastermind PR #89 at df93bad6114de5c5cc8350363b8179325736bda7 a
  bounded CI dependency-baseline repair of the reviewed EXEC-MCP-A SDK,
  or an MCP product/API migration?
answer: >
  APPROVE_FOR_MERGE at exact head
  df93bad6114de5c5cc8350363b8179325736bda7. PR #89 is DEPENDENCY BASELINE
  REPAIR ONLY: it pins mcp==1.28.0 in the pyproject.toml dev extra and
  adds tests/test_executive_mcp_sdk_pin.py. No Executive MCP gateway,
  adapter, control_plane, Wake, Phase 1F, auth, launchd, or acceptance
  change. Hosted required check `test` is SUCCESS on that head. This is
  not an MCP v2 migration and authorizes no host, Gate B, acceptance, or
  Wake action.
rationale: >
  EXEC-MCP-A PR #64 declared mcp>=1.2 (resolved 1.28.0) in the dev extra
  only. Hosted CI later floated to an incompatible SDK that renamed
  Server.list_tools and ToolAnnotations.readOnlyHint. Exact-version
  pinning replays the reviewed SDK contract; a <2 ceiling would still
  float inside 1.x. The unique diff vs origin/master
  (b5e45be20a752b689e08a88d15816ef26fb2c45c) is two files. Pip on the
  required test job collected and installed mcp-1.28.0. Residual test
  hardness (test_18_15 still looks for mcp>= and is comment-satisfied;
  pin tests importorskip) is not a product-behavior change and is not
  grounds to keep the 2.x float.
alternatives:
  - option: HOLD until test_18_15 is rewritten to parse the TOML specifier
    why_not: >
      The current unique diff already pins the reviewed version in the
      only intended location. Holding Wave A would keep MCP 2.x blocking
      #87/#88. The residual is a follow-up fence, not this PR's defect.
  - option: Prefer mcp>=1.2,<2 instead of mcp==1.28.0
    why_not: >
      A ceiling still floats. The purpose is deterministic replay of the
      reviewed SDK, not a 1.x band.
  - option: Adapt server.py to MCP 2.x
    why_not: >
      That would be an Executive MCP V2 migration. Forbidden by this wave.
evidence:
  - git fetch; origin/master = b5e45be20a752b689e08a88d15816ef26fb2c45c
  - PR #89 OPEN head df93bad6114de5c5cc8350363b8179325736bda7 base b5e45be
  - git diff --name-only origin/master...df93bad = pyproject.toml tests/test_executive_mcp_sdk_pin.py
  - PR #64 body: "mcp>=1.2 (resolved 1.28.0), dev extra only"
  - required check test job 96033300073 conclusion success; run 32241643588
  - CI log: Collecting mcp==1.28.0; Successfully installed ... mcp-1.28.0
  - ci_pytest discovered=258 excluded=0 running=258; pin test not excluded
affects:
  - WS:AGENT-OS
  - DEC:EXECUTIVE-PHASE1CA-B5E45BE-FAILED-ACCEPTANCE-FORENSIC
confidence: high
reversibility: easy
decided_by: session
decided_at: 2026-08-19
---

## Scope

Wave A / PR #89 independent COO review. Not a merge, install, Gate B,
acceptance, Codex reauthorization, or Wake commission.

Wake remains `NOT_IN_SCOPE / NOT_ACCEPTED / NOT_ARMED`.
The spent b5 formal attempt remains `SPENT_FAILED`.
