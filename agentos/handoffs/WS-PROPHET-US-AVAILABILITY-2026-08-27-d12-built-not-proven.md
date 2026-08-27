---
workstream: WS:PROPHET-US-AVAILABILITY
phase: D12
state: BUILT_NOT_PROVEN
operation_key: prophet-us-d12-pack-tip-hardening-20260827-sol-001
carrier: sol/prophet-us-d12-pack-tip-20260827
---

# D12 US Prophet pack-tip hardening

The US pack owner now quarantines a name before pack-tip selection and before gate submission when its final close index is malformed/NaT, is not a real NYSE session, or is later than the canonical last completed session. Rejected names publish `skip=invalid_series_tip` as a stale/non-verdict. The bad series is never trimmed and reused. Shared `engine/prophet_live/armed_pack.py` remains unchanged for China.

Proof: binding RED `33068839608` (5 failed / 2 passed); committed GREEN `33069264975` (8/8); mutation `33069337428` killed removal of NYSE-session validation; cross-market `33069685528` passed 81/81 existing US+CN pack tests; NaT RED `33069928015` reproduced a TypeError; repair run `33069998807` passed 9/9 before commit `e2d612e4bd3b2dbddff4b25103c09aac3dc7434d`; finalizer `33070296813` passed 9/9 on the finalized tree and wired the D12 suite into permanent Prophet P0.

This is **BUILT_NOT_PROVEN**, not PROVEN_LIVE. After merge, use the first natural US pack + evaluator + external-dead-man path. Require the canonical completed-session bound, a real completed-session pack `as_of`, explicit non-verdicts for any naturally occurring invalid tips, no global `stale_pack` darkness, and `pack_ok=True`. Do not manufacture a contaminated production row and do not manually dispatch `prophet-live.yml` while the VPS timer is primary.
