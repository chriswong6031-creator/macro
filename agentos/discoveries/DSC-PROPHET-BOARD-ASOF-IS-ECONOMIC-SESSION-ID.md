---
key: PROPHET-BOARD-ASOF-IS-ECONOMIC-SESSION-ID
claim: >
  Prophet board `as_of` is an economic session identifier, not a publication
  version. Multiple production executions may legally produce different board
  bytes (including a different W3 structural receipt) while retaining the same
  `as_of`.
falsifier: >
  A production `us_prophet_ledgers` pair on the same committed `as_of` whose
  `site/factordata/us_standouts.json` (or the W3 family grain derived from its
  `prophet_fusion.w3_structural.v1` receipt) is byte-identical across both
  executions; or a product change that versions republishes under a new `as_of`
  / publication id so same-stamp bytes cannot diverge. Check against the 2026-08-17
  F1_TECHNICAL_CONFLUENCE witness: frozen family `mean_abs_rank_delta=3.696969697`
  versus later same-stamp receipt `3.8484848485` on run 32084697588 / job 95749508810.
so_what: >
  W3 must treat `stamp_date` as the economic session grain. The first durably
  committed complete W3 observation wins; a later same-stamp publication is a
  refused revision, not a second session and not a rewrite. Do not change the
  general Prophet product's republish policy (#5878). Do not treat git commit
  date, workflow date, or run id as a new W3 observation.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  GitHub Actions run 32084697588 job 95749508810 (`us_prophet_ledgers`):
  W3ConflictError on ('2026-08-17','F1_TECHNICAL_CONFLUENCE') existing
  mean_abs_rank_delta 3.696969697 vs incoming 3.8484848485; frozen parts
  4486cd6199b465431b0e1f27b1057e87b1aaf628 /
  6885cfc4f5c180177ed307953f3b67b2021e0371 /
  dc5edb4082b536adcbb5d3fbc1b22af8a57f6d2e remained byte-identical.
  Related but distinct from DSC:BOARD-RECOMMIT-IS-NOT-A-BOARD-ADVANCE
  (mtime/commit clock vs content stamp) — here CONTENT itself moved under the
  same as_of.
scope: [macro]
confidence: verified
---

## Detail

The 2026-08-17 W3 paired/family/coverage parts were first written by PR-3C
code on a natural nightly. A later `us_prophet_ledgers` execution rebuilt the
family grain from the *current* board structural receipt, which still carried
`as_of=2026-08-17` but a different F1 LOFO displacement. Keep-first correctly
refused the rewrite. The hole this discovery names is treating that refusal as
a crash instead of a same-stamp revision of an already-complete observation.

This does not authorize averaging, float tolerance, latest-wins, or a second
honest-N session. It does not change how the live Prophet board may republish.
