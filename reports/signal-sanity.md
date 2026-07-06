# Signal sanity — 2026-07-06

**🚨 FAIL** · 1 failure(s), 1 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-07-02 | 19 | 19 | ⚠️ warn |
| briefing (Phase-5 priority queue) | 2026-07-06 | 25 | 25 | ok |
| radar (divergence radar) | 2026-07-06 | 273 | 273 | ok |
| altdata (alt-data desk) | 2026-07-06 | 30 | 30 | 🚨 fail |
| news (news flow) | 2026-07-06 | 410 | 205 | ok |
| intel_hub (5-desk command) | 2026-07-06 | 30 | 30 | ok |

## Failures (these block publish)

- altdata: CONTENT FROZEN — as_of advanced 2026-07-05→2026-07-06 but signal values are byte-identical to the prior vintage (builder did not recompute)

## Warnings

- standouts.conviction.composite_z: mean drifted 52% (-0.00667→-0.186) vs 2026-07-01

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._