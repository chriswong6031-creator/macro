# Signal sanity — 2026-07-21

**✅ OK** · 0 failure(s), 1 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-07-20 | 45 | 45 | ⚠️ warn |
| briefing (Phase-5 priority queue) | 2026-07-20 | 25 | 25 | ok |
| radar (divergence radar) | 2026-07-20 | 254 | 254 | ok |
| altdata (alt-data desk) | 2026-07-21 | 30 | 30 | ok |
| news (news flow) | 2026-07-21 | 360 | 164 | ok |
| intel_hub (5-desk command) | 2026-07-20 | 30 | 30 | ok |

## Warnings

- standouts.conviction.composite_z: mean drifted 65% (0.156→-0.141) vs 2026-07-17

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._