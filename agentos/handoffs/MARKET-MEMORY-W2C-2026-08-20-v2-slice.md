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
  M0C freeze is DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY. No v2 runtime exists.
  v1 continues as the evidence/control arm.
changed:
  - path: agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md
    what: This slice packet. No code.
verified:
  - claim: M0C did not implement a v2 writer, registration JSON, or systemd unit.
    command: git diff --stat origin/main -- engine app config scripts
    result: empty of runtime paths in the M0C packet (AgentOS records only).
unverified:
  - claim: Single-ticker REST bar exists by 20:05Z on the first live v2 session.
    what_would_verify: The slice's evening availability probe on that session.
unresolved:
  - Sol ratification of the v2 registration candidate.
  - Whether two 04:30 oneshots or one iterating two roots; default two units.
next_actions:
  - Wait for Sol freeze.
  - Implement exactly this slice in a new branch. Do not expand into V2 UX, analogue, W4/W5, or D-class R2 repair.
do_not_redo:
  - Do not edit config/market_memory_spy_experience_registration.v1.json.
  - Do not retune v1 technicals :53 or the 22:30 collector for v1 admission.
  - Do not backfill or replay 04:30.
  - Do not publish a public SPY parquet.
danger_areas:
  - Hardcoded _expected_registration_spec and accrue closure list.
  - 256-cap if v2 writes technicals-v1.
  - Digesting request_id.
---

# M0D — first v2 vertical slice (do not implement in M0C)

## Not done unless

1. Evening probe at the next natural XNYS close records first 200-with-bar clock for `GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false` and a second hash at 04:29Z D+1. If the bar is absent until the 04:24–04:54 band, stop and return to Sol (class A again).
2. New source owner unit with MASSIVE_API_KEY/POLYGON_API_KEY writes immutable `results[]` bytes + digest + endpoint + non-secret params + session D + first_observed_at + source code version. Later vendor corrections append a revision; they never mutate the sealed object.
3. New keyless technicals-v2 projector reads only that store, produces `market_memory.private.spy_raw_rth_daily_aggregate.v2`, refuses torn/future/prior-session the same way v1 refuses, and does not read public R2.
4. New registration JSON v2, new schema file, parameterized accrue closure. v1 spec function untouched.
5. New experience-v2 root and 04:30 oneshot. v1 unit untouched. Shared trusted-v1 read-only.
6. Hostile tests: same-session REST before deadline can admit; after-deadline cannot pull backward; prior-session abstains; torn source refused; future refused; v1 sealed rows unchanged bytes and disposition.
7. First **natural** 04:30–04:45Z window after merge. BUILT_NOT_PROVEN until that window. Never replay.

## Reuse

`engine/close_pass/massive_close.py` KEY_ENVS and base URL. Publication order from `market_memory_sources.py` (object → two receipts → generation → HEAD), new SOURCE_ID. Do not create a second general vendor client.

## Owner

New files, not v1 paths: source module + unit, technicals-v2 module + unit, registration v2 + contract schema, accrue parameterization, experience-v2 unit.
