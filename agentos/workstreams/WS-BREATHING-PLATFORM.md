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
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: specified
next_action: >
  Execute child C0 from
  agentos/handoffs/BREATHING-PLATFORM-2026-08-28-completion-commission.md:
  Chairman assigns the recommended Fable principal COO in the program-control
  Slack thread; receiver ACKs, arms the exact-thread watcher, and performs
  read-only production-truth recovery for Aug-26/Aug-27 plus the current
  post-#6554/#6569/#6534 state. Do not modify code until C0 names one causal gap.
  Architecture and completion law are frozen in
  research/BREATHING_PLATFORM_COMPLETION_MASTERPLAN_2026-08-28.md.
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
  - id: W-L2
    title: Current valid armed-level breadth outcome
    status: todo
    depends_on: [W-L1R]
    next_action: >
      Use completion masterplan C3. Do not execute the old "raise/parallelize +
      alerts" packet. #6554 now owns D12 correctness as BUILT_NOT_PROVEN;
      process fan-out already exists; Availability/permanence owns publication
      alerts; LIVE-ENTRY-RADAR owns tactical alerts. After D12 natural proof,
      census current verified armed-level breadth and timing. Close by evidence
      if the old gap is superseded; otherwise commission one measured bottleneck
      repair without weakening parity/edge verification or inflating resources arbitrarily.
  - id: W-ACCEPT
    title: Live-session acceptance — three consecutive green sessions on the ruler
    status: in_progress
    depends_on: [W-L1R]
    next_action: >
      Final acceptance follows completion masterplan C0/C1/C5/C6. Recover exact
      Aug-26/Aug-27 receipts first. Aug-27 cannot be treated as a healthy whole
      product merely from a fresh pass clock: #6569 proves the independent
      Prophet-Live plane was fresh-empty/global-dark while the sentinel stayed
      green. After the last relevant production-changing merge, accrue three
      consecutive natural sessions with close_observed_at, first_candidate_at,
      first_user_visible_at <=16:15 ET, >=95% same-session evaluable coverage,
      100% universe accounting, truthful independent live/board clocks and real
      desktop+narrow browser proof.
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
do_not_redo:
  - "No third live/prophet_live writer."
  - "No new Massive WebSocket for Breathing."
  - "No VPS-side canonical board compute tier."
  - "No weakening _bsQualify or the board-to-card identity gate."
  - "No second ranker, signal gate, availability semantic, alert product, monitor registry, retry daemon or liveness control plane."
  - "No Prophet rank/gate/entry-timing retune to solve delivery latency."
  - "No reconstruction of missing first_user_visible_at from candidate/R2/file timestamps."
  - "No arbitrary timeout/memory inflation standing in for measured causality."
---

## State — 2026-08-28 completion architecture freeze

Procedural pin: protected `mastermindx-market-intelligence/Mastermind@038d1271b98e88b24e039c1ce4127d6503945845`, `mastermind.sol_skillpack.v1` 1.0.1.
Macro archaeology base: `ba270c60c1fe825f2e9fce1fcf507b7272a67b63`.

Material current changes since the 2026-08-27 forensic return:

- #6554 merged D12 producer hardening. D12 is **BUILT_NOT_PROVEN**, not NOT_BUILT and not yet PROVEN_LIVE.
- #6562 merged the adjacent B1 natural-intake crash repair; it remains an owner boundary, not Breathing scope.
- #6569 merged after real Aug-27 production showed a fresh `prophet_live` pass clock with an empty state population while `stale_pack` darkened the live evaluator and the sentinel stayed green. The new repeated-empty and ahead-pack grader fences are **BUILT_NOT_PROVEN** until natural post-merge proof.
- #6532 freshness-language/browser semantics and #6534 permanence net are merged; their natural/browser production acceptance is part of the completion program.

The final completion program is C0 current production truth → C1 natural Availability/D12/permanence proof → conditional causal repair only when observed → C3 W-L2 current breadth census/conditional repair → C5 browser truth/degraded-state proof → C6 three consecutive natural ruler greens → durable closeout.
