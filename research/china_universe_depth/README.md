# CN search-universe depth — measurement scripts

Reproduce the receipts behind
`research/CHINA_FULL_UNIVERSE_MASTERPLAN_BY_FABLE.md` §7 (W-DEPTH).

Run from the repo root:

| script | what it measures |
|---|---|
| `sina_walk.py` | live Sina market-cap walk past rank 4,000 → `sina_rank.json` (rank → ticker, mktcap 亿). The denominator behind every "+N net-new" figure. |
| `revz_sens.py` | `engine.china_reversal.reversal_watch` recomputed on a narrow vs the full committed panel — the rev_z / deepest-quintile / top-16 delta a widening imposes on already-covered names. |
| `revz_series.py` | the same at 300 / 400 / 600 / 800 / full, so the per-step re-base is a series rather than one pair. |

`sina_walk.py` writes `sina_rank.json` into the session scratchpad path hard-coded
at the bottom of the file; point it somewhere durable before running the other two,
which read it back.

Unit costs (seconds/name, MB/name) are **not** re-derivable from these scripts —
they come from CI run 30905719412 (`asia-close.yml`, 2026-08-04) and a local
`git pack-objects` test. Both are cited inline in §7.
