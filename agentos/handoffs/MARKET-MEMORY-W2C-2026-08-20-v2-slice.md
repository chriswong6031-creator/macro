---
workstream: "WS:MARKET-MEMORY-W2C"
session: claude/market-memory-m0c-source-qual-20260820
model: local
ended_because: complete
mission: >
  Bounded implementation handoff for the first W2C v2 vertical slice. Not
  executed in M0C. Produce the first natural admitted opportunity from a
  same-session REST technical + trusted pair after Sol ratifies the freeze.
state_before: >
  M0C freeze is DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY. Hybrid session-scope
  naming is DEC:W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE. No v2 runtime exists.
  v1 continues as the evidence/control arm.
changed:
  - path: agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md
    what: Slice packet updated for hybrid price/activity contract, 04:32 stagger, and technicals-v1 isolation. No code.
verified:
  - claim: This packet still contains no v2 writer, registration JSON, or systemd unit.
    command: git diff --stat origin/main -- engine app config scripts
    result: empty of runtime paths (AgentOS records only).
unverified:
  - claim: Single-ticker REST bar exists by 20:05Z on the first live v2 session.
    what_would_verify: The slice's evening availability probe on that session.
unresolved:
  - Sol ratification of the v2 registration candidate including the hybrid basis name.
  - Live trusted HEAD capture_count (DSC:W2C-V1-TRUSTED-CAPTURES-THREE-PER-WINDOW is probable).
next_actions:
  - Wait for Sol freeze.
  - Implement exactly this slice in a new branch. Do not expand into V2 UX, analogue, W4/W5, D-class R2 repair, or the close-pass probe TypeError.
do_not_redo:
  - Do not edit config/market_memory_spy_experience_registration.v1.json.
  - Do not retune v1 technicals :53 or the 22:30 collector for v1 admission.
  - Do not backfill or replay 04:30.
  - Do not publish a public SPY parquet.
  - Do not switch the sealed source to grouped daily.
  - Do not write REST captures into technicals-v1 or experience-v1.
danger_areas:
  - Hardcoded _expected_registration_spec byte-equality. Parameterize by schema; never edit the v1 dict in place or v1's registration_id changes.
  - Sharing technicals-v1 with REST captures converts remaining v1 abstentions into missed.
  - Digesting request_id.
  - Two experience oneshots on the same second contend for the 900s window.
---

# M0D — first v2 vertical slice (do not implement in M0C)

## Not done unless

1. Evening probe at the next natural XNYS close records first 200-with-bar clock for `GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false` and a second hash of **parsed `results[]`** (not the raw HTTP body) at 04:29Z D+1. If the bar is absent until the 04:24–04:54 band, stop and return to Sol (class A again).
2. New source owner unit with MASSIVE_API_KEY/POLYGON_API_KEY writes immutable `results[]` bytes + digest + endpoint + non-secret params + session D + first_observed_at + source code version. Later vendor corrections append a revision; they never mutate the sealed object. Session identity is request date D, never `bar.t`.
3. New keyless technicals-v2 projector reads only that store, produces `market_memory.private.spy_rth_price_fullday_activity_daily_aggregate.v2` with split scopes (RTH price rungs, full-day activity counters), refuses torn/future/prior-session the same way v1 refuses, and does not read public R2. `technicals-v1` is InaccessiblePaths.
4. New registration JSON v2, new schema file, parameterized accrue registry keyed on `schema`. **v1 `_spec_v1()` bytes untouched** (pin `content_sha256 == e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3`). Feature key stays `price.raw_close_ratio_20_sessions`.
5. New experience-v2 root. v1 unit and 04:30 timer byte-unchanged. v2 experience oneshot at **04:32Z** (same registered 04:30–04:45 window, staggered start). Shared trusted-v1 **reads only**. v2 technicals writer at `*:07`, never a HEAD move inside 04:30–04:45Z.
6. Hostile tests: same-session REST before deadline can admit; after-deadline cannot pull backward; prior-session abstains; torn source refused; future refused; v1 sealed rows unchanged bytes and disposition; a REST capture in technicals-v1 would have made v1 `missed` — prove the isolation instead.
7. First **natural** 04:30–04:45Z window after merge. BUILT_NOT_PROVEN until that window. Never replay.

## Reuse

`engine/close_pass/massive_close.py` KEY_ENVS and base URL. Publication order from `market_memory_sources.py` (object → two receipts → generation → HEAD), new SOURCE_ID. Do not create a second general vendor client. Grouped daily remains a cross-check, not the sealed object.

## Owner

New files, not v1 paths: source module + unit, technicals-v2 module + unit, registration v2 + contract schema, accrue parameterization, experience-v2 unit.
