# Signal sanity — 2026-08-20

**🚨 FAIL** · 1 failure(s), 1 warning(s)

| board | as_of | records | coverage | status |
|---|---|---:|---:|---|
| standouts (engine buy-board) | 2026-08-19 | 61 | 61 | ok |
| briefing (Phase-5 priority queue) | 2026-08-19 | 25 | 25 | ok |
| radar (divergence radar) | 2026-08-19 | 201 | 201 | ok |
| altdata (alt-data desk) | 2026-08-20 | 30 | 30 | ok |
| news (news flow) | 2026-08-20 | 251 | 10 | 🚨 fail |
| intel_hub (5-desk command) | 2026-08-19 | 30 | 30 | ok |

## Failures (these block publish)

- news: coverage 10 < floor 100 (news flow)

## Warnings

- news.n_recent: mean drifted 57% (3.25→5.1) vs 2026-08-19

_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of advanced but values identical) · staleness · distribution drift. Ground-truth-free — see engine/signal_sanity.py._