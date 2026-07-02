"""Rebuild the long-history CCTV tone series from the raw archive.

Reads all monthly shards in data/china_news/cctv_archive/, applies the EXACT
same lexicon and scoring logic already in collectors/china_news.py (_POS/_NEG,
`_tone_features`), and writes a single parquet:

  data/china_news/cctv_tone_history.parquet
  columns: date (DatetimeIndex), tone (float), n_items (int), n_stub (int)

"date" is the broadcast date.
"tone" is (pos_hits − neg_hits) / max(n_items, 1) — same formula as the live adapter.
"n_items" is real broadcast items (fetch_status == "ok").
"n_stub" is stub rows that contributed no signal (stub + error).

This small file IS committed so the engine (engine/china_news.py) can z-score
the full 10-year baseline instead of the rolling 120-day incremental window.
Re-run after each major backfill batch to refresh it.

Usage
-----
  python scripts/rebuild_cctv_tone_history.py [--archive-dir PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Import the canonical lexicon and scoring function from the live collector.
# We deliberately import _tone_features (not copy it) so any future lexicon
# changes propagate automatically.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from collectors.china_news import _tone_features  # noqa: E402

log = logging.getLogger("rebuild_cctv_tone")

DEFAULT_ARCHIVE = REPO_ROOT / "data" / "china_news" / "cctv_archive"
DEFAULT_OUT = REPO_ROOT / "data" / "china_news" / "cctv_tone_history.parquet"


def rebuild(archive_dir: Path, out_path: Path) -> pd.DataFrame:
    shards = sorted(archive_dir.glob("*.parquet"))
    if not shards:
        raise FileNotFoundError(f"No parquet shards found in {archive_dir}")

    records: list[dict] = []
    for shard_path in shards:
        shard = pd.read_parquet(shard_path)
        if shard.empty:
            continue
        for dt_str, day_df in shard.groupby("date"):
            # Split real items from stubs/errors
            ok_rows = day_df[day_df["fetch_status"] == "ok"]
            stub_rows = day_df[day_df["fetch_status"].isin(["stub", "error"])]

            n_items = len(ok_rows)
            n_stub = len(stub_rows)

            if n_items == 0:
                # empty / all-stub day — record the day with n_items=0, tone=NaN
                records.append({
                    "date": pd.Timestamp(dt_str),
                    "tone": float("nan"),
                    "n_items": 0,
                    "n_stub": n_stub,
                })
                continue

            # _tone_features expects a raw frame in akshare's shape (date, title, content)
            # We pass only the ok rows; order_idx is preserved by the shard sort.
            feat = _tone_features(ok_rows[["date", "title", "content"]].rename(
                columns={"date": "date"}
            ))
            records.append({
                "date": pd.Timestamp(dt_str),
                "tone": feat["tone"],
                "n_items": int(feat["items"]),
                "n_stub": n_stub,
            })

    if not records:
        raise ValueError("No records derived — archive is empty or all-stubs")

    out = (
        pd.DataFrame(records)
        .set_index("date")
        .sort_index()
    )
    out.index.name = "date"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, compression="zstd")
    log.info(
        "cctv_tone_history: %d days written to %s (n_items>0: %d, NaN: %d)",
        len(out),
        out_path,
        (out["n_items"] > 0).sum(),
        out["tone"].isna().sum(),
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild long-history CCTV tone series from archive shards"
    )
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE),
                        help=f"Archive shard directory (default: {DEFAULT_ARCHIVE})")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"Output parquet (default: {DEFAULT_OUT})")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    archive_dir = Path(args.archive_dir).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    df = rebuild(archive_dir, out_path)
    print(f"Written {len(df)} rows to {out_path}")
    print(df.tail(10).to_string())


if __name__ == "__main__":
    main()
