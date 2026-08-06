# Exit-policy horse race — frozen replay slice

The input grid `scripts/exit_policy_study.py` replays to produce
`reports/exit-policy-horserace.md`. It is **data, not a result** — the price and board
stores exactly as they stood at the study's as-of.

* **`PRICE_ASOF` — 2026-07-31.** The last bar in every panel here.
* **Cut from** the repo's own tracked stores at commit `ca9251861b4`
  (*data: daily collection 2026-08-01*) — the last collection whose price reach was
  2026-07-31, i.e. the state that produced the committed report. The report's numbers are
  therefore unchanged by the introduction of this slice; `git log -p` on the report shows
  only a study-date stamp and a provenance bullet.

## Why the study does not read the live stores

Read live, `run_study()` is not deterministic, and the obvious fix — an as-of pin on the
end of the panel — is not sufficient. Measured between the 2026-08-01 and 2026-08-06
collections:

| Drift | Effect | Fixed by an end-of-panel as-of pin? |
|---|---|---|
| Panel **end** advances nightly | cohort 173 episodes / 8 board days → 257 / 11 | yes |
| Panel **start** rolls forward (smallcap/midcap caches are a rolling window: first date 2023-06-27 → 2023-07-03, moving 91 of 152 cohort tickers) | `grade_us_board._ob_mask` reads the 3D StochRSI through `confluence_tiers._tf_bars`, i.e. `resample("3B")`, whose bins are **start-anchored** — move the first date and every 3D bucket in the whole history re-phases, so overbought flags from weeks ago flip and P0's exits move underneath a cohort that never changed | **no** |
| Vendor **revisions** to bars at or below the as-of (2 cohort tickers over the same three sessions: `OHI`, `REZI`) | P&L moves on an unchanged cohort | **no** |

The second row is why this directory exists rather than a one-line constant. It also
sets a rule for maintaining the slice: **the panels keep their full history.** Trimming
the start to save bytes re-phases the 3D buckets and silently rewrites the report;
`wilder_atr` is a recursive `ewm(adjust=False)` RMA and reads the beginning of the series
too. `tests/test_exit_policy_study.py::TestFrozenReplay` pins this.

## What is stored

| Path | Contents |
|---|---|
| `data/breadth/_{closes,high,low}_cache.parquet` | The four breadth groups **already merged first-hit-wins**, restricted to tickers that appear on the 17 post-cut boards (373 of 383 — a board ticker with no live column stays absent, because the report prints that exclusion count), full history, rows ≤ `PRICE_ASOF` |
| `data/yahoo/SPY.parquet` | Benchmark closes, rows ≤ `PRICE_ASOF` |
| `data/us_board_ledger/snapshots.jsonl` | Board membership **projected** to the three fields `load_board_days` reads: `as_of`, and per buy-lane row `ticker` + `hold.invalidation`. One line per source line — `prov` counts lines, not days. The live store is ~17 MB of another lane's scored columns |
| `data/us_board_ledger/retro_grades.parquet` | Projected to the `as_of` / `lane` / `ticker` columns the loader reads, post-cut rows only |

The shipped ledger the Calibration section reconciles against is deliberately **not**
frozen here: `site/factordata/us_track_ledger.json` is itself a committed artifact, so the
study meets it where it ships.

## Refreshing

A deliberate act, never a nightly one. Both steps land in the **same commit**, so the
report's numbers move together with the data that produced them:

```bash
python -m scripts.exit_policy_study --freeze --price-asof <new-as-of>
```

then bump `PRICE_ASOF` in `scripts/exit_policy_study.py` and re-run
`python -m scripts.exit_policy_study` to regenerate the report. Freezing at an as-of that
does not match the constant emits a `::warning` rather than passing quietly.

To see what current data says without re-freezing:

```bash
python -m scripts.exit_policy_study --live --out /tmp/live.md
```

It will not match the committed report — that is the point, and the difference is the
study's own staleness measured rather than assumed.
