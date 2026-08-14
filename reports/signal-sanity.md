# Signal sanity — 2026-08-14

**🚨 FAIL** · 1 failure(s), 1 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-08-13 | 71 | 71 | ok |
| briefing (Phase-5 priority queue) | 2026-08-13 | 25 | 25 | ok |
| radar (divergence radar) | 2026-08-13 | 259 | 259 | ok |
| altdata (alt-data desk) | 2026-08-14 | 30 | 30 | ok |
| news (news flow) | 2026-08-14 | 283 | 13 | 🚨 fail |
| intel_hub (5-desk command) | 2026-08-13 | 30 | 30 | ok |

## Failures (these block publish)

- news: coverage 13 < floor 100 (news flow)

## Warnings

- news.n_recent: mean drifted 134% (1.75→4.08) vs 2026-08-13

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._