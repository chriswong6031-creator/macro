# Signal sanity — 2026-07-13

**🚨 FAIL** · 1 failure(s), 1 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-07-10 | 36 | 36 | ⚠️ warn |
| briefing (Phase-5 priority queue) | 2026-07-13 | 25 | 25 | ok |
| radar (divergence radar) | 2026-07-13 | 241 | 241 | ok |
| altdata (alt-data desk) | 2026-07-13 | 30 | 30 | ok |
| news (news flow) | 2026-07-13 | 28 | 28 | 🚨 fail |
| intel_hub (5-desk command) | 2026-07-13 | 30 | 30 | ok |

## Failures (these block publish)

- news: coverage 28 < floor 100 (news flow)

## Warnings

- standouts.conviction.composite_z: mean drifted 79% (0.162→-0.0236) vs 2026-07-09

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._