---
key: MARKET-MEMORY-W2C
title: Market Memory W2C prospective activation recovery
objective: >
  Keep the first honest W2C prospective opportunity on a live, exact activation
  chain. M0A is complete. M0B classified v1 as A — SOURCE_CLOCK_IMPOSSIBLE.
  M0C froze v2 on single-ticker REST daily plus a hybrid RTH-price/full-day-
  activity technical contract. M0D-0 PASS / Sol GO_M0D froze readiness on the
  D+1 04:00–04:05Z source seal, not first REST availability. v1 stays an
  immutable evidence/control arm. First v2 admit now waits on the bounded M0D
  runtime vertical slice.
status: active
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
      Ratified by Sol in DEC:W2C-M0C-SOL-RATIFIED-REST-SUCCESSOR, including
      the hybrid price/activity correction from PR #6083. The natural-session
      probe has now passed (M0D-0). Do not reopen the source object/profile
      naming unless new evidence falsifies the hybrid scope.
  - id: M0D
    title: First v2 vertical slice (REST source owner + technicals-v2 + registration v2)
    status: in_progress
    depends_on: [M0C]
    next_action: >
      After the M0D-0 records closeout is on origin/main, implement the runtime
      vertical slice under DEC:W2C-M0D0-0400Z-SOURCE-SEAL-GO and
      agentos/handoffs/MARKET-MEMORY-W2C-2026-08-21-m0d0.md: one sealed REST
      capture per session in [04:00:00Z, 04:05:00Z) D+1; keyless technicals-v2;
      registration v2 encoding the seal predicate; experience-v2 at 04:32Z;
      strict prospective activation. Do not mix D-class R2 coherence into this PR.
next_action: >
  Implement the M0D runtime vertical slice from
  agentos/handoffs/MARKET-MEMORY-W2C-2026-08-21-m0d0.md under
  DEC:W2C-M0D0-0400Z-SOURCE-SEAL-GO. Seal one canonical results[] capture per
  session in [04:00:00Z, 04:05:00Z) D+1; do not treat first REST availability
  as readiness; keep v1 isolation and 04:32Z stagger. Stop at a design
  contradiction or first authenticated natural v2 opportunity.
decisions:
  - "DEC:W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE"
  - "DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY"
  - "DEC:W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE"
  - "DEC:W2C-M0C-SOL-RATIFIED-REST-SUCCESSOR"
  - "DEC:W2C-M0D0-0400Z-SOURCE-SEAL-GO"
discoveries:
  - "DSC:MASSIVE-DAY-AGGS-LASTMODIFIED-FOLLOWS-0430Z"
  - "DSC:SPY-REST-UNADJUSTED-DAILY-MATCHES-FLATFILE-OHLC"
  - "DSC:MASSIVE-GROUPED-DAILY-AVAILABLE-AT-XNYS-CLOSE"
  - "DSC:SPY-DAILY-AGG-IS-RTH-PRICE-FULLDAY-ACTIVITY"
  - "DSC:W2C-V1-TRUSTED-CAPTURES-THREE-PER-WINDOW"
  - "DSC:W2C-M0D0-SPY-REST-FORMING-BAR-SEAL-STABLE"
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
  - Do not name the v2 profile as if volume and n were RTH.
  - Do not switch the sealed v2 source to grouped daily.
  - Do not digest REST request_id or the raw HTTP body as source identity.
  - Do not host REST bytes in the CPI ALFRED source store.
  - Do not share technicals-v1 or experience-v1 with v2.
  - Do not edit _expected_registration_spec in place to describe v2.
  - Do not repair v1 abstentions with v2 evidence.
  - Do not treat first REST availability as W2C opportunity readiness; the D+1 04:00–04:05Z source seal is the readiness boundary.
  - Do not persist forming-bar revisions as production source generations; one stable seal equals one capture.
  - Do not re-run M0D-0 as a standing gate; the 2026-08-20 trajectory already passed.
  - Do not backdate activation_session or rush Monday 2026-08-24.
landmines:
  - Nested-path admission must round-trip artifact_relative_path. Any slash, mixed-case nested name, or hex that decodes to an uppercase ticker reopens traversal and identity-fold bugs.
  - Experience timer enabled-but-inactive is not armed. Armed means enabled plus active/waiting with a future NextElapse.
  - technical_session_absent is a lawful same-session evidence miss, not a missed window. The writer did run.
  - Technicals Result=success with a lagged session is a different defect from technicals failing closed.
  - Session 2026-08-18 also lacked a trusted same-session pin; that is concurrent with, not a substitute for, the technical lag.
  - Massive stocks day_aggs LastModified lives in the 04:30Z band. The 22:30 UTC nightly cannot see session D.
  - 2026-08-19 ticker-count then publish-last tears delayed coherent 08-18 capture to 22:57Z; they did not delay the 08-19 S3 object past 04:45Z — that object was itself 04:54Z.
  - accrue_market_memory_spy_experience.py and _expected_registration_spec() are v1-hardcoded. Editing that dict in place changes v1's registration_id and rejects every sealed v1 row.
  - Single-ticker bar.t is midnight ET; session identity is the request date.
  - REST captures in technicals-v1 make remaining v1 windows missed, not abstained.
  - v1 trusted generation grew +3 captures/window on the first three windows against a 256 reader pin budget (DSC:W2C-V1-TRUSTED-CAPTURES-THREE-PER-WINDOW).
  - Two experience oneshots at the same 04:30:00Z second contend for the 900s window; v2 starts at 04:32Z.
  - REST daily is a live forming aggregate from 09:30 ET; 546 unique digests on 2026-08-20. First availability is not a sealed source.
  - Production 04:00–04:05Z sampling may poll repeatedly; only the sealed digest is a source generation. Post-04:05Z corrections append lineage, they do not rewrite the sealed opportunity.
artifacts:
  - agentos/handoffs/MARKET_MEMORY_M0A_CLOSEOUT_2026-08-16.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c-addendum.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c-sol-ratification.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-21-m0d0.md
  - agentos/decisions/DEC-W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE.md
  - agentos/decisions/DEC-W2C-M0C-V2-REST-SINGLE-TICKER-DAILY.md
  - agentos/decisions/DEC-W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE.md
  - agentos/decisions/DEC-W2C-M0C-SOL-RATIFIED-REST-SUCCESSOR.md
  - agentos/decisions/DEC-W2C-M0D0-0400Z-SOURCE-SEAL-GO.md
  - agentos/discoveries/DSC-MASSIVE-DAY-AGGS-LASTMODIFIED-FOLLOWS-0430Z.md
  - agentos/discoveries/DSC-SPY-REST-UNADJUSTED-DAILY-MATCHES-FLATFILE-OHLC.md
  - agentos/discoveries/DSC-MASSIVE-GROUPED-DAILY-AVAILABLE-AT-XNYS-CLOSE.md
  - agentos/discoveries/DSC-SPY-DAILY-AGG-IS-RTH-PRICE-FULLDAY-ACTIVITY.md
  - agentos/discoveries/DSC-W2C-V1-TRUSTED-CAPTURES-THREE-PER-WINDOW.md
  - agentos/discoveries/DSC-W2C-M0D0-SPY-REST-FORMING-BAR-SEAL-STABLE.md
  - research/market_memory/W2C_M0D0_SPY_REST_REVISION_TRAJECTORY_2026-08-20.tsv
---

M0A first-cause repair: PR #5805, merged as `e1ec8865ac92`.
M0A three-window proof: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md`.
M0B clock forensics: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md`.
M0C source freeze: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c.md` plus hybrid-scope addendum #6083.
Sol M0C ratification: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c-sol-ratification.md`.
M0D-0 PASS / Sol GO_M0D: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-21-m0d0.md`.
