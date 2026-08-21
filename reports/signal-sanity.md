# Signal sanity — 2026-08-21

**🚨 FAIL** · 2 failure(s), 0 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-08-20 | 43 | 43 | ok |
| briefing (Phase-5 priority queue) | 2026-08-20 | 25 | 25 | ok |
| radar (divergence radar) | 2026-08-20 | 197 | 197 | ok |
| altdata (alt-data desk) | 2026-08-21 | 30 | 30 | ok |
| news (news flow) | 2026-08-21 | 251 | 10 | 🚨 fail |
| intel_hub (5-desk command) | 2026-08-20 | 30 | 30 | ok |

## Failures (these block publish)

- news: coverage 10 < floor 100 (news flow)
- news: CONTENT FROZEN — as_of advanced 2026-08-20→2026-08-21 but signal values are byte-identical to the prior vintage (builder did not recompute)

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._