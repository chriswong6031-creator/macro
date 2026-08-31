---
key: BREATHING-PLATFORM
title: Breathing Platform — live, continuously refreshed US signal platform
objective: >
  The US product behaves as a live signal platform, not a batch nightly website:
  market state refreshes intraday from the live plane; a same-session provisional
  Prophet board is user-visible within minutes of the close (product SLO 16:15 ET,
  first-usable target ~16:05-16:10); post-close inputs revise it in place; the
  nightly settles the canonical record; no unrelated collector failure can dark
  today's board; stale or empty state never masquerades as current. Done = the
  2026-08-28 completion masterplan's truth/product/reliability/browser gates plus
  three consecutive genuine post-change NYSE sessions green on the close→candidate→reader ruler.
status: active
program: prophet-us
p0: PROPHET_FRESHNESS
repos: [macro]
owner: ceo-sol
class: build
blast_radius: reversible
ambiguity: specified
next_action: >
  Execute fresh child C2-A from
  agentos/handoffs/BREATHING-PLATFORM-2026-08-29-c2-closepass-host-lane-repair.md.
  C0 is accepted/terminal; do not reopen it. C2-A is the first still-live causal
  dependency: the host-native close-pass lane can remain registered+locked in Git
  while missing on disk, and current prepare_lane only has a weaker error-string +
  prune recovery path that does not safely cover that state. Preferred avenue is
  CTO Sol, receiver binding is CAPACITY_SELECTABLE, and current placement state is
  WAITING_CAPACITY / needs_placement because CF2-I capacity-aware Executive
  placement is not yet production-released. Do not turn that placement debt into
  OPEN_PICKUP or routine Chairman account scheduling, and do not arm a receiver-
  specific watcher until a lawful receiver exists. After C2-A code + actual Mac
  Studio installer/preflight proof, separately reconcile C2-B backstop Massive
  same-session coverage, C1 natural D12/permanence proof, C3 W-L2 breadth, C5
  browser/degraded-state proof, then C6 three consecutive natural sessions.
owns_paths:
  - scripts/close_pass_publish.py
  - scripts/close_pass_mirror.py
  - scripts/close_pass_host_runner.py
  - scripts/close_pass_slo_report.py
  - scripts/measure_massive_close_parity.py
  - scripts/install_closepass_launchd.sh
  - ops/launchd/com.macro.closepass.plist
  - engine/close_pass/
  - .github/workflows/close-pass.yml
  - tests/test_close_pass_lane.py
  - tests/test_close_pass_massive_close.py
  - tests/test_close_pass_host_runner.py
waves:
  - id: W-L0
    title: Truth fixes (append semantics, fade hysteresis, price basis, sentinel surface, dormant honesty)
    status: done
    next_action: "Shipped 2026-08-08..09 (#4978 #4982 #5088 #5089, sentinel b278a3f9b); not reopened by completion program."
  - id: W-L1
    title: Evening SLA — close-pass provisional board, cards, receipt, reader-measured sentinel
    status: done
    next_action: >
      Shipped #5148 #5154 #5217 #5220 #5222 #5223. Historical pre-revival
      greens do not satisfy the final post-change three-session acceptance ruler.
  - id: W-L1R
    title: Revival wave — coverage + latency + ruler (Chairman directive 2026-08-15)
    status: done
    next_action: >
      Merged/deployed foundation: #5746 coverage path, #5760 host-native close
      clock, #5761 ruler/watchdog. Replay acceptance is historical foundation;
      current natural acceptance is W-ACCEPT.
  - id: C2-A
    title: Recover missing-but-locked host-native close-pass worktree
    status: todo
    depends_on: [W-L1R]
    next_action: >
      WAITING_CAPACITY / needs_placement. Use operation
      breathing-c2-closepass-host-lane-repair-20260829-sol-001 and the 2026-08-29
      C2-A handoff. PREFERRED_AVENUE=CTO Sol; CAPACITY_SELECTABLE. Require real-Git
      reproduction + RED-before regression, structurally targeted recovery that
      cannot touch unrelated worktrees, reviewed PR, existing installer deployment
      to the Mac Studio, installed-bootstrap digest proof and non-publishing lane
      readiness preflight. Weekend/pre-session preflight is not a C6 session green.
  - id: W-L2
    title: Current valid armed-level breadth outcome
    status: todo
    depends_on: [W-L1R]
    next_action: >
      Use completion masterplan C3 after the delivery/availability prerequisites.
      Do not execute the old "raise/parallelize + alerts" packet. #6554 owns D12
      correctness as BUILT_NOT_PROVEN; process fan-out already exists;
      Availability/permanence owns publication alerts; LIVE-ENTRY-RADAR owns tactical
      alerts. After trustworthy natural input proof, census current verified
      armed-level breadth and timing. Close by evidence if the old gap is superseded;
      otherwise commission one measured bottleneck repair without weakening
      parity/edge verification or inflating resources arbitrarily.
  - id: W-ACCEPT
    title: Live-session acceptance — three consecutive green sessions on the ruler
    status: in_progress
    depends_on: [W-L1R]
    next_action: >
      C0 is complete and binds the latest accepted failure evidence: 2026-08-26
      FAIL (host lane_unprepared; GitHub backstop landed hours late with 251/1764 =
      14.2% evaluated coverage) and 2026-08-27 FAIL (host lane_unprepared; no close
      board; Prophet-Live fresh-clock/global-dark stale-pack state). No later durable
      repair/acceptance proof was found in the 2026-08-29 GitHub/Slack restart
      reconciliation. Do not infer later greens from absence of a record. After the
      last relevant production-changing merge/deploy—including C2-A and any required
      C2-B/Availability repair—accrue three consecutive genuine NYSE sessions with
      close_observed_at, first_candidate_at, first_user_visible_at <=16:15 ET,
      >=95% same-session evaluable coverage, 100% universe accounting, truthful
      independent live/board clocks and real desktop+narrow browser proof.
landmines:
  - "Completion architecture is research/BREATHING_PLATFORM_COMPLETION_MASTERPLAN_2026-08-28.md. Do not implement from the older 2026-08-08 W-L2 wording without reconciling this freeze."
  - "Freshness is a vector, not one timestamp: board as_of, reader first visibility, Prophet-Live pass/quote/non-vacuity, armed-pack as_of/completed_through, nightly source_asof and sentinel heartbeat are independent clocks."
  - "Aug-27 production proved a fresh pass clock can coexist with states={} and stale_pack darkness. #6569 is merged but natural post-merge proof remains owed."
  - "D12 is BUILT_NOT_PROVEN on #6554: malformed/non-session/not-yet-completed last bars are quarantined before BOTH pack-tip selection and gate admission. Do not re-open with a stamp-only fix."
  - "The last durable exact close-pass same-session breadth proof is 1,684/1,763 (95.5%) from the 2026-08-14 replay. Never relabel it as a current natural-session census."
  - "The board universe store lacks many same-day bars without the Massive fill; source/session identity and corporate-action darking remain load-bearing."
  - "The client paints board_state ONLY off the real evaluator document and only when _bsQualify identity/freshness checks pass. A bare board_state shell is not the product."
  - "Board freshness and Prophet-Live freshness are separate: a fresh board may coexist with a degraded live strip only if the browser and monitors say so truthfully."
  - "Two writers share live/prophet_live.json via CAS (evaluator + close-pass annotation). Never add a third writer."
  - "Never manually dispatch prophet-live.yml while the VPS primary timer can publish; that can create a second live writer."
  - "Vendor ticker identity is case-sensitive at the Massive seam (TPC≠TpC, BCPC≠BCpC)."
  - "GitHub cron is not a product clock; host-native close scheduling remains primary."
  - "Never splice a raw same-day close through a same-session split/dividend ambiguity; dark the name and let nightly settle it."
  - "The provisional board carries only the score evidence it can stand behind; never renormalise or impute omitted legs."
  - "A locked missing close-pass worktree is not safely repaired by broad git worktree prune. Recovery must identify and reconcile only the exact production lane registration, or fail closed."
do_not_redo:
  - "No third live/prophet_live writer."
  - "No new Massive WebSocket for Breathing."
  - "No VPS-side canonical board compute tier."
  - "No weakening _bsQualify or the board-to-card identity gate."
  - "No second ranker, signal gate, availability semantic, alert product, monitor registry, retry daemon or liveness control plane."
  - "No Prophet rank/gate/entry-timing retune to solve delivery latency."
  - "No reconstruction of missing first_user_visible_at from candidate/R2/file timestamps."
  - "No arbitrary timeout/memory inflation standing in for measured causality."
  - "Do not turn missing automated capacity placement into recurring Chairman numbered-account allocation."
---

## State — 2026-08-29 CEO restart reconciliation

Procedural pin: protected `mastermindx-market-intelligence/Mastermind@e3d1fe6bb454df10212ce6e13bf2e4e5160f7eb5`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1 compatible. Macro reconciliation base: `2a45075ddb1139d3bcab6c6402f483040e0f6378`.

### Program lifecycle

- Parent program `breathing-completion-program-20260828-sol-001` remains ACTIVE.
- C0 `breathing-c0-production-truth-20260828-sol-001` is TERMINAL/ACCEPTED by the explicit Sol STOP at Slack `1787917466.335309`; it must not be reopened.
- A later parent-control triage correctly recorded `PARENT_ACTIVE_NO_SUCCESSOR`. The 2026-08-29 reconciliation found no subsequently commissioned Breathing child and no post-C0 GitHub/Slack receipt proving the close-pass host defect repaired.
- Sol resumes end-to-end completion ownership; organizational owner is `ceo-sol`.

### First still-live causal gap

Accepted C0 production evidence identified the primary failure as `.claude/worktrees/closepass-host-lane` being registered+locked in Git while missing on disk. The launchd clock fired, but `prepare_lane` failed before close observation. Current `main` still contains only a partial corpse recovery: after `worktree add` failure it prunes/retries only when output contains `already registered`. A locked registration is intentionally retained by prune and the real missing+locked Git state has no regression test. Therefore C2-A is a genuine current code/host repair, not speculative rework.

Fresh C2-A commission:

```text
operation_key: breathing-c2-closepass-host-lane-repair-20260829-sol-001
handoff: agentos/handoffs/BREATHING-PLATFORM-2026-08-29-c2-closepass-host-lane-repair.md
PREFERRED_AVENUE: CTO Sol
WHY NOT FABLE: C0 already froze the product/authority boundary; this is difficult but bounded host/runner engineering.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

No worker-facing Slack commission and no receiver-specific watcher exists yet. Current `WS:EXECUTIVE-CAPACITY-FABRIC` says CF2-I (capacity-aware Executive placement) is still `todo` behind CF2-H0/P0, so no production-proven automated placement is available to claim. Current routing law explicitly forbids converting that absence into routine Chairman numbered-account scheduling or OPEN_PICKUP advertising.

### What follows C2-A

C2-B is separately bounded: prove/repair the GitHub backstop's same-session Massive credential/coverage path without disclosing credentials or absorbing Massive collector ownership. C0 showed the backstop path that actually ran on Aug-26 had no Massive key and evaluated only 251/1764 names. Current workflow expects `secrets.MASSIVE_API_KEY`; credential existence/value is not readable through the safe evidence surface used by this reconciliation, so no false "fixed" claim is made.

Availability C1 remains a natural-proof dependency for D12/#6569/#6534; W-L2 C3 remains a measurement-first breadth question; C5 remains real browser/degraded-state acceptance; C6 remains three consecutive genuine post-change NYSE sessions. A weekend/pre-session C2-A preflight can restore the lane before the next close but cannot count as a market acceptance session.

## State — 2026-08-28 completion architecture freeze

Procedural pin: protected `mastermindx-market-intelligence/Mastermind@038d1271b98e88b24e039c1ce4127d6503945845`, `mastermind.sol_skillpack.v1` 1.0.1.
Macro archaeology base: `ba270c60c1fe825f2e9fce1fcf507b7272a67b63`.

Material current changes since the 2026-08-27 forensic return:

- #6554 merged D12 producer hardening. D12 is **BUILT_NOT_PROVEN**, not NOT_BUILT and not yet PROVEN_LIVE.
- #6562 merged the adjacent B1 natural-intake crash repair; it remains an owner boundary, not Breathing scope.
- #6569 merged after real Aug-27 production showed a fresh `prophet_live` pass clock with an empty state population while `stale_pack` darkened the live evaluator and the sentinel stayed green. The new repeated-empty and ahead-pack grader fences are **BUILT_NOT_PROVEN** until natural post-merge proof.
- #6532 freshness-language/browser semantics and #6534 permanence net are merged; their natural/browser production acceptance is part of the completion program.

The final completion program is C0 current production truth → C1 natural Availability/D12/permanence proof → conditional causal repair only when observed → C3 W-L2 current breadth census/conditional repair → C5 browser truth/degraded-state proof → C6 three consecutive natural ruler greens → durable closeout.
