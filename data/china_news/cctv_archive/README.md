# CCTV 新闻联播 Raw Archive

This directory holds the full per-item broadcast archive for CCTV 新闻联播 (Xinwen Lianbo), the 19:00 national bulletin — the canonical daily readout of Chinese Communist Party policy priorities.

## Layout

```
cctv_archive/
  YYYY-MM.parquet    — one shard per calendar month, zstd-compressed
  backfill.log       — append-only progress log from backfill_cctv_archive.py
  README.md          — this file
```

## Shard schema

| Column | Type | Notes |
|---|---|---|
| `date` | str `"YYYY-MM-DD"` | Broadcast date |
| `order_idx` | int | Broadcast order; `0` = 联播头条 (lead item) |
| `title` | str | Item headline |
| `content` | str | Item body |
| `fetch_status` | str | `ok` / `empty` / `stub` / `error` |
| `fetched_at` | str ISO-8601 UTC | When this row was fetched |

**`fetch_status` legend:**
- `ok` — real content; used for tone scoring
- `empty` — weekend/holiday/not-yet-published; no broadcast that day
- `stub` — page rot on old date; row preserved for order accounting but excluded from tone
- `error` — network/akshare failure; retryable with `--repair`

## Coverage

History reliable from **2016-02-03** (per akshare docstring). Degraded 2013–2016. Total ≈ 3,800 days.

## Source

`akshare 1.18.64`: `ak.news_cctv(date="YYYYMMDD")` — free, keyless, wraps cctv.com archive. One HTTP call per day, ~30–50s per day with 2–4s politeness sleep.

## Tooling

- **Backfill / resume**: `python scripts/backfill_cctv_archive.py [--out-dir PATH]`
- **Retry stubs**: `python scripts/backfill_cctv_archive.py --repair [--out-dir PATH]`
- **Audit gaps**: `python scripts/backfill_cctv_archive.py --gap-audit [--out-dir PATH]`
- **Rebuild tone**: `python scripts/rebuild_cctv_tone_history.py`

## Gitignore policy (decided 2026-07-02)

**Shards are gitignore'd** (`data/china_news/cctv_archive/*.parquet`).

Measurement: the 2025-01→2025-03 sample run produced **≈ 2.0 MB / quarter**;  projected full archive ≈ **43 MB** for 10.4 years (≈ 4.1 MB/year × 10.4). This is under the 150 MB policy threshold and would normally be committable. However, the archive is scraped in a long background run that outlives this PR — committing partial shards as the scrape progresses would pollute `main` with noise commits. **Shards are therefore gitignored and committed in a single follow-up commit once the backfill completes** (see the follow-up note in the PR body).

The derived `data/china_news/cctv_tone_history.parquet` (the small aggregated tone series) IS committed and does not need the exemption.

## Downstream consumer

`scripts/rebuild_cctv_tone_history.py` → `data/china_news/cctv_tone_history.parquet`  
`engine/china_news.py` z-scores `tone` over the full history baseline instead of the rolling 120-day incremental window — the long pole in the China contrarian-sign falsification (W4 of the Qualitative-Intelligence Upgrade).
