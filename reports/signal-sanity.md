# Signal sanity — 2026-07-12

**✅ OK** · 0 failure(s), 1 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-07-10 | 31 | 31 | ⚠️ warn |
| briefing (Phase-5 priority queue) | 2026-07-11 | 25 | 25 | ok |
| radar (divergence radar) | 2026-07-11 | 241 | 241 | ok |
| altdata (alt-data desk) | 2026-07-12 | 30 | 30 | ok |
| news (news flow) | 2026-07-12 | 514 | 297 | ok |
| intel_hub (5-desk command) | 2026-07-11 | 30 | 30 | ok |

## Warnings

- standouts.conviction.composite_z: mean drifted 74% (0.162→-0.0114) vs 2026-07-09

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._