# Signal sanity — 2026-08-13

**🚨 FAIL** · 1 failure(s), 0 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-08-12 | 70 | 70 | ok |
| briefing (Phase-5 priority queue) | 2026-08-13 | 25 | 25 | ok |
| radar (divergence radar) | 2026-08-13 | 264 | 264 | ok |
| altdata (alt-data desk) | 2026-08-13 | 30 | 30 | ok |
| news (news flow) | 2026-08-13 | 325 | 59 | 🚨 fail |
| intel_hub (5-desk command) | 2026-08-13 | 30 | 30 | ok |

## Failures (these block publish)

- news: coverage 59 < floor 100 (news flow)

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._