# Signal sanity — 2026-08-03

**🚨 FAIL** · 1 failure(s), 0 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-07-31 | 71 | 71 | ok |
| briefing (Phase-5 priority queue) | 2026-08-02 | 25 | 25 | ok |
| radar (divergence radar) | 2026-08-02 | 229 | 229 | ok |
| altdata (alt-data desk) | 2026-08-03 | 30 | 30 | 🚨 fail |
| news (news flow) | 2026-08-03 | 599 | 383 | ok |
| intel_hub (5-desk command) | 2026-08-02 | 30 | 30 | ok |

## Failures (these block publish)

- altdata: CONTENT FROZEN — as_of advanced 2026-08-02→2026-08-03 but signal values are byte-identical to the prior vintage (builder did not recompute)

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._