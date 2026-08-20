---
key: MARKET-MEMORY-W2C
title: Market Memory W2C prospective activation recovery
objective: >
  Keep the first honest W2C prospective opportunity on a live, exact activation
  chain. M0A is complete. M0B classified v1 as A — SOURCE_CLOCK_IMPOSSIBLE.
  M0C freezes v2 on single-ticker REST daily under a new registration. v1 stays
  an immutable evidence/control arm. First v2 admit waits on Sol freeze then M0D.
status: awaiting_review
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
needs_ceo:
  question: >
    Ratify DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY: v2 source =
    GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false, 04:30Z window
    preserved, technical feature versioned to raw_unadjusted_rth_daily_aggregate,
    credentials in a new source owner, disjoint experience-v2/technicals-v2,
    no public SPY R2 publisher, v1 untouched?
  options:
    - "Ratify as written and authorize M0D implementation slice"
    - "Amend source object (grouped daily or open-close) then implement"
    - "Hold implementation until the next natural close adds evening N for single-ticker first-availability"
    - "Reject REST successor and keep v1 evidence-only"
  recommendation: >
    Option 1, with the M0D evening probe as a fail-closed gate: if REST is
    absent until the 04:24–04:54Z band, stop and return rather than shipping a
    second class-A window.
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
    pr: 6065
    depends_on: [M0A]
    next_action: >
      Classified A. v1 remains the evidence/control arm. Do not retune v1 timers
      or source.
  - id: M0C
    title: Successor source qualification and v2 architecture freeze
    status: done
    depends_on: [M0B]
    next_action: >
      Packet complete. Wait for Sol ratification. Do not implement the writer
      in the qualification session.
  - id: M0D
    title: First v2 vertical slice (REST source owner + technicals-v2 + registration v2)
    status: todo
    depends_on: [M0C]
    next_action: >
      After Sol freeze, execute
      agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md. Do not mix
      D-class R2 coherence into that PR.
next_action: >
  Wait for Sol ratification of DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY. Do not
  implement M0D, mutate v1, backfill, or thin-publish SPY.
decisions:
  - "DEC:W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE"
  - "DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY"
discoveries:
  - "DSC:MASSIVE-DAY-AGGS-LASTMODIFIED-FOLLOWS-0430Z"
  - "DSC:SPY-REST-UNADJUSTED-DAILY-MATCHES-FLATFILE-OHLC"
  - "DSC:MASSIVE-GROUPED-DAILY-AVAILABLE-AT-XNYS-CLOSE"
do_not_redo:
  - Do not treat a lawful in-window abstained row as missed, absent, or an M0A failure.
  - Do not reopen #5805 or the nested __case_v1 filename admit without a live journal reproducing the noncanonical-filename exception.
  - Do not backfill a missed W2C row or fabricate an admitted opportunity.
  - Do not weaken PIT, authority, or freshness validators to manufacture admission.
  - Do not assume the old weekend context-freshness failure remains causal; diagnose from the live journal.
  - Do not reject leftover mixed-case root names in the same PR as admitting canonical nested __case_v1 paths.
  - Do not edit app/deploy/update.sh or deploy tests that #5804 already merged.
  - Do not treat the house-doc ~11:00 ET flat-file figure as the stocks day_aggs clock; HEAD the S3 object.
  - Do not move massive_stock_day collect into the 04:30 window, retune technicals :53, or add a SPY-only R2 publisher against frozen v1.
  - Do not infer Massive first-availability from when a collector happened to look.
  - Do not call REST the same unauthenticated full-market-day feature; version it.
  - Do not digest REST request_id as source identity.
  - Do not host REST bytes in the CPI ALFRED source store.
  - Do not share technicals-v1 or experience-v1 with v2.
  - Do not repair v1 abstentions with v2 evidence.
landmines:
  - Nested-path admission must round-trip artifact_relative_path. Any slash, mixed-case nested name, or hex that decodes to an uppercase ticker reopens traversal and identity-fold bugs.
  - Experience timer enabled-but-inactive is not armed. Armed means enabled plus active/waiting with a future NextElapse.
  - technical_session_absent is a lawful same-session evidence miss, not a missed window. The writer did run.
  - Technicals Result=success with a lagged session is a different defect from technicals failing closed.
  - Session 2026-08-18 also lacked a trusted same-session pin; that is concurrent with, not a substitute for, the technical lag.
  - Massive stocks day_aggs LastModified lives in the 04:30Z band. The 22:30 UTC nightly cannot see session D.
  - 2026-08-19 ticker-count then publish-last tears delayed coherent 08-18 capture to 22:57Z; they did not delay the 08-19 S3 object past 04:45Z — that object was itself 04:54Z.
  - accrue_market_memory_spy_experience.py and _expected_registration_spec() are v1-hardcoded.
  - Single-ticker bar.t is midnight ET; session identity is the request date.
artifacts:
  - agentos/handoffs/MARKET_MEMORY_M0A_CLOSEOUT_2026-08-16.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md
  - agentos/decisions/DEC-W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE.md
  - agentos/decisions/DEC-W2C-M0C-V2-REST-SINGLE-TICKER-DAILY.md
  - agentos/discoveries/DSC-MASSIVE-DAY-AGGS-LASTMODIFIED-FOLLOWS-0430Z.md
  - agentos/discoveries/DSC-SPY-REST-UNADJUSTED-DAILY-MATCHES-FLATFILE-OHLC.md
  - agentos/discoveries/DSC-MASSIVE-GROUPED-DAILY-AVAILABLE-AT-XNYS-CLOSE.md
---

M0A first-cause repair: PR #5805, merged as `e1ec8865ac92`.
M0A three-window proof: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md`.
M0B clock forensics: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md`.
M0C source freeze: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c.md`.
