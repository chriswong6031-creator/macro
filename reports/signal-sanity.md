# Signal sanity — 2026-07-16

**✅ OK** · 0 failure(s), 1 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-07-15 | 28 | 28 | ⚠️ warn |
| briefing (Phase-5 priority queue) | 2026-07-16 | 25 | 25 | ok |
| radar (divergence radar) | 2026-07-16 | 242 | 242 | ok |
| altdata (alt-data desk) | 2026-07-16 | 30 | 30 | ok |
| news (news flow) | 2026-07-16 | 643 | 402 | ok |
| intel_hub (5-desk command) | 2026-07-16 | 30 | 30 | ok |

## Warnings

- standouts.conviction.composite_z: mean drifted 52% (-0.143→0.0752) vs 2026-07-14

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._