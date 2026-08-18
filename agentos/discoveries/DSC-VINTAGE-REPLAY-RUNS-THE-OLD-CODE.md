---
key: VINTAGE-REPLAY-RUNS-THE-OLD-CODE
claim: >
  A point-in-time replay executing builders inside a vintage worktree runs the
  VINTAGE's code, so no fix or gate added to current lane code can protect the
  replay — the only enforceable boundary is harness-side (env the old code
  already honors or cannot bypass, e.g. dead-proxy HTTP(S)_PROXY at an
  unroutable address, plus post-run byte-assertions over stores the old code
  might refresh).
falsifier: >
  A replay mechanism that demonstrably executes CURRENT-code gates while
  reconstructing inside a historical tree (e.g. a shim module the vintage
  imports) would narrow this to the default execution model. Per-collector
  half: a CN drip collector that writes on a FAILED fetch would break the
  dead-proxy defense — disproven for all 13 as of 2026-08-18 by reading each
  refresh() (write sits after a successful fetch; build_china_library wraps
  each call in try/except).
so_what: >
  Any future replay/backfill harness budgets its lookahead defenses OUTSIDE the
  vintage subprocess, and its reviewer asks "what does the OLD code do" for
  every input, never "what does main's code do now". Found when adversarial
  review proved data/china_st (live-refreshed mid-build by vintage code, read
  with no date filter) reaches CN board admission via limit-width relay counts.
  Shipped as _vintage_env dead-proxy pins + per-market pinned_stores assertions
  in scripts/prophet_pit_replay.py.
kind: constraint
verified_at: 2026-08-18
verified_by: "adversarial review reproduction chain collectors/china_st.py:35,161 → engine/china_microstructure.py:158-183 → scripts/build_china_library.py:2920-2933; fix + tests in scripts/prophet_pit_replay.py (PR claude/prophet-pit-replay)"
scope:
  - "macro"
  - "scripts/prophet_pit_replay.py"
  - "any future PIT replay/backfill harness"
confidence: verified
---

See `research/PROPHET_PIT_REPLAY_HARNESS_V1.md` §2b(3) for the shipped
mechanics and `DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT` for the
authorizing default.
