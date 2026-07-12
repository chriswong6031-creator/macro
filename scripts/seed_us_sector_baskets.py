"""Seed 11 equal-weight US GICS-sector baskets into data/baskets/membership.json.

Each basket = every S&P 500 constituent in a GICS sector, equal-weighted, paired
with its cap-weighted SPDR ETF as the ``etf_proxy``. The signal of interest is the
DIVERGENCE between the two: an equal-weight sector lagging its cap-weight ETF means
the sector's move is mega-cap-narrow; equal-weight leading means broad participation.

This complements the 34 hand-curated thematic baskets (which have no sector family)
and the heatmap's sector membership. Idempotent: re-running replaces the
``us_sector_*`` entries and leaves every other basket untouched.

    python -m scripts.seed_us_sector_baskets [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

# GICS sector (as stored in constituents.parquet) -> (id slug, SPDR ETF, en, zh)
# COPY SYNC: the generated name/name_zh/theme/thesis/etf_proxy_note strings below must match
# the live us_sector_* entries in data/baskets/membership.json — re-running replaces those
# entries wholesale, so copy edits made directly to the live file must be mirrored here.
SECTORS: dict[str, tuple[str, str, str, str]] = {
    "Information Technology": ("tech", "XLK", "Technology", "信息技术"),
    "Financials": ("financials", "XLF", "Financials", "金融"),
    "Health Care": ("health", "XLV", "Health Care", "医疗保健"),
    "Consumer Discretionary": ("discretionary", "XLY", "Consumer Discretionary", "非必需消费"),
    "Communication Services": ("comm", "XLC", "Communication Services", "通信服务"),
    "Industrials": ("industrials", "XLI", "Industrials", "工业"),
    "Consumer Staples": ("staples", "XLP", "Consumer Staples", "必需消费"),
    "Energy": ("energy", "XLE", "Energy", "能源"),
    "Utilities": ("utilities", "XLU", "Utilities", "公用事业"),
    "Real Estate": ("realestate", "XLRE", "Real Estate", "房地产"),
    "Materials": ("materials", "XLB", "Materials", "材料"),
}

# Members backfill from the curated seed date (current S&P membership applied back —
# the same hindsight caveat the engine already confidence-caps for every basket).
MEMBER_ADDED = "2023-05-09"
CREATED = "2026-06-28"


def _constituents() -> pd.DataFrame:
    df = pd.read_parquet(config.data_dir() / "breadth" / "constituents.parquet")
    if df.index.name != "symbol" and "symbol" in df.columns:
        df = df.set_index("symbol")
    return df


def build_sector_baskets() -> dict[str, dict]:
    cons = _constituents()
    out: dict[str, dict] = {}
    for gics, (slug, etf, en, zh) in SECTORS.items():
        members = sorted(cons.index[cons["sector"] == gics].tolist())
        if len(members) < 3:
            continue
        out[f"us_sector_{slug}"] = {
            "name": f"{en} (Equal-Weight)",
            "name_zh": f"{zh}（等权）",
            "theme": f"S&P 500 {en} sector, equal-weighted",
            "category": "US Sectors (EW)",
            "parent": "US Sectors",
            "etf_proxy": etf,
            "etf_proxy_note": f"{etf} is cap-weighted; this basket is equal-weight — the gap is a breadth read.",
            "created": CREATED,
            "weighting": "equal",
            "thesis": (
                f"Equal-weight S&P 500 {en} members versus {etf}. "
                f"Sector participation gauge, not a buy list."
            ),
            "members": [
                {"ticker": t, "added": MEMBER_ADDED, "removed": None,
                 "rationale": f"S&P 500 {en} constituent"}
                for t in members
            ],
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed equal-weight US sector baskets")
    ap.add_argument("--dry-run", action="store_true", help="print summary, do not write")
    args = ap.parse_args(argv)

    path = config.data_dir() / "baskets" / "membership.json"
    mem = json.loads(path.read_text())
    baskets = mem.setdefault("baskets", {})

    new = build_sector_baskets()
    # drop any prior us_sector_* before re-inserting (idempotent)
    for k in [k for k in baskets if k.startswith("us_sector_")]:
        del baskets[k]
    baskets.update(new)

    total_members = sum(len(b["members"]) for b in new.values())
    print(f"{len(new)} sector baskets, {total_members} member rows:")
    for k, b in new.items():
        print(f"  {k:24s} {b['etf_proxy']:5s} {len(b['members']):3d} names")

    if args.dry_run:
        print("(dry run — not written)")
        return 0
    path.write_text(json.dumps(mem, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path} ({len(baskets)} baskets total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
