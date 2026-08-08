# Signal sanity — 2026-08-08

**🚨 FAIL** · 1 failure(s), 0 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-08-07 | 78 | 78 | ok |
| briefing (Phase-5 priority queue) | 2026-08-08 | 25 | 25 | ok |
| radar (divergence radar) | 2026-08-08 | 250 | 250 | ok |
| altdata (alt-data desk) | 2026-08-08 | 30 | 30 | ok |
| news (news flow) | 2026-08-08 | 700 | 471 | 🚨 fail |
| intel_hub (5-desk command) | 2026-08-08 | 30 | 30 | ok |

## Failures (these block publish)

- news: CONTENT FROZEN — as_of advanced 2026-08-07→2026-08-08 but signal values are byte-identical to the prior vintage (builder did not recompute)

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._