---
key: MARKET-MEMORY-W2C
title: Market Memory W2C prospective activation recovery
objective: >
  Keep the first honest W2C prospective opportunity on a live, exact activation
  chain. M0A is complete: production executed all three registered windows
  2026-08-17/18/19 inside 04:30–04:45 UTC and sealed lawful abstained rows.
  M0B classified the remaining path to admitted as A — SOURCE_CLOCK_IMPOSSIBLE
  under frozen v1. No runtime repair until Sol rules on registration or source.
status: blocked
program: market-memory
p0: US_PROPHET_ENTRY_TIMING
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - engine/neuralweb/market_memory_technical_observation.py
  - engine/neuralweb/market_memory_technical_store.py
blocked_by:
  - >
    Sol architecture ruling on v1 source/window. DEC:W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE
    forbids timers, validators, registration edits, substitute sources, and a second
    R2 publisher until that ruling.
needs_ceo:
  question: >
    Frozen v1 cannot lawfully admit a same-session W2C opportunity from Massive
    us_stocks_sip/day_aggs_v1 through public R2 massive_stock_day: the S3 object
    LastModified clusters inside the 04:30–04:45 UTC window (29% after 04:45 on
    24 sessions). How should the remaining 123 expected sessions be spent?
  options:
    - "Keep v1 as an evidence-only pilot: lawful in-window abstention continues; do not spend runtime repairs against this source/window"
    - "Mutate registration (window open/duration or following-session rather than following-calendar-day 04:30Z) so vendor LastModified plus canonical publish plus technicals capture fit; this is a v1 freeze break"
    - "Authorize a new source (REST grouped daily, available minutes after 20:00 UTC close) under a new registration — not a silent substitute inside v1"
    - "Authorize a thin same-session SPY current publication distinct from the 21k nightly store — a new publisher contract, still Sol-gated"
  recommendation: >
    Option 1 until a written ruling on 2 or 3. Do not implement B/C/D runtime
    repairs against v1. Do not consume further frozen sessions chasing a 15-minute
    race with a vendor clock that is the window.
  by_when: 2026-08-21
waves:
  - id: M0A
    title: First-cause repair and three-window prospective proof
    status: done
    pr: 5805
    next_action: >
      Proven. Do not reopen the nested __case_v1 intake repair unless the live
      technicals journal reproduces the noncanonical-filename exception.
  - id: M0B
    title: First-admission clock forensics and causal classification
    status: done
    depends_on: [M0A]
    next_action: >
      Classified A. Clock ledger and DEC:W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE
      returned to Sol. Do not start a B/C/D runtime PR without that ruling.
next_action: >
  Wait for Sol's ruling on the four options in needs_ceo. Do not move the
  22:30 UTC collect, do not retune the technicals :53 timer, do not thin-publish
  SPY, do not open a REST source, and do not backfill.
decisions:
  - "DEC:W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE"
discoveries:
  - "DSC:MASSIVE-DAY-AGGS-LASTMODIFIED-FOLLOWS-0430Z"
do_not_redo:
  - Do not treat a lawful in-window abstained row as missed, absent, or an M0A failure.
  - Do not reopen #5805 or the nested __case_v1 filename admit without a live journal reproducing the noncanonical-filename exception.
  - Do not backfill a missed W2C row or fabricate an admitted opportunity.
  - Do not weaken PIT, authority, or freshness validators to manufacture admission.
  - Do not assume the old weekend context-freshness failure remains causal; diagnose from the live journal.
  - Do not reject leftover mixed-case root names in the same PR as admitting canonical nested __case_v1 paths.
  - Do not edit app/deploy/update.sh or deploy tests that #5804 already merged.
  - Do not treat the house-doc ~11:00 ET flat-file figure as the stocks day_aggs clock; HEAD the S3 object.
  - Do not move massive_stock_day collect into the 04:30 window, retune technicals :53, or add a SPY-only R2 publisher against frozen v1 without Sol.
  - Do not infer Massive first-availability from when a collector happened to look.
landmines:
  - Nested-path admission must round-trip artifact_relative_path. Any slash, mixed-case nested name, or hex that decodes to an uppercase ticker reopens traversal and identity-fold bugs.
  - Experience timer enabled-but-inactive is not armed. Armed means enabled plus active/waiting with a future NextElapse.
  - technical_session_absent is a lawful same-session evidence miss, not a missed window. The writer did run.
  - Technicals Result=success with a lagged session is a different defect from technicals failing closed.
  - Session 2026-08-18 also lacked a trusted same-session pin; that is concurrent with, not a substitute for, the technical lag.
  - Massive stocks day_aggs LastModified lives in the 04:30Z band. The 22:30 UTC nightly cannot see session D.
  - 2026-08-19 ticker-count then publish-last tears delayed coherent 08-18 capture to 22:57Z; they did not delay the 08-19 S3 object past 04:45Z — that object was itself 04:54Z.
artifacts:
  - agentos/handoffs/MARKET_MEMORY_M0A_CLOSEOUT_2026-08-16.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md
  - agentos/decisions/DEC-W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE.md
  - agentos/discoveries/DSC-MASSIVE-DAY-AGGS-LASTMODIFIED-FOLLOWS-0430Z.md
---

M0A first-cause repair: PR #5805, merged as `e1ec8865ac92`.
M0A three-window proof: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md`.
M0B clock forensics: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md`.
