---
key: PROPHET-ASOF-IS-WALL-CLOCK
claim: >
  Top-level `asof` and `recorded_at` in site/prophet/index.json are wall-clock
  publication stamps (`args.date`, defaulting to date.today() at bake time), decoupled
  from data content. A rerun refreshes them even when every input is frozen. The honest
  freshness fields are `source_asof` (price watermark from us_standouts staleness) and
  the newest `recorded_at` cohort inside the plans array.
falsifier: >
  scripts/build_prophet.py deriving the top-level asof from source data instead of
  args.date/today (currently build_prophet.py:1499 and :2098-2109), or a fixture where
  a frozen-input rerun leaves top-level asof unchanged.
so_what: >
  Any staleness sentinel, dashboard, triage session, or LLM answering "are Prophet
  picks fresh?" MUST read source_asof and the plan cohort dates, never top-level asof.
  During the 2026-08-11/13 outage a retry bake stamped asof=2026-08-13 pre-market while
  originating zero plans (source_mixed_vintage=true, gate_go=false) — asof-based checks
  would have called it healthy. The code itself warns this at build_prophet.py:2100 and
  until PR #5487 nothing in the repo read source_asof.
kind: landmine
verified_at: 2026-08-14
verified_by: >
  scripts/build_prophet.py:1499 (args.date default today), :2098-2109 (asof/recorded_at
  assignment + in-code warning), :1529-1540 (source_asof from staleness.price_through);
  origin/main site/prophet/index.json on 2026-08-14 02:0xZ: asof=2026-08-13,
  source_asof=2026-08-12, zero plans recorded_at=2026-08-13.
scope: [macro, terminal]
confidence: verified
---

## Detail

Consumers see the same artifact three ways (git-vendored via VPS 3-min pull, public R2
`prophet/index.json` for the Terminal, and main directly), so a wall-clock-fresh but
data-stale index.json misleads every surface at once. The mixed-vintage wedge class
makes this concrete: a bake can run, publish, advance asof, and still deliver zero
picks for the session. Freshness therefore has two independent axes — data watermark
(source_asof vs lib/nyse_calendar.expected_last_session()) and origination coverage
(a plans cohort for the expected session, cross-read against the intake block's
eligible counts). PR #5487 (nightly-liveness) instruments the first axis;
scripts/prophet_rescue.py (availability-hardening PR) instruments both and responds.
