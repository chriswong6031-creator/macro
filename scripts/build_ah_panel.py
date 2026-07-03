"""One-shot / incremental builder for the deep A/H matched-pair premium panel.

Usage
-----
  python -m scripts.build_ah_panel            # incremental (appends only new dates)
  python -m scripts.build_ah_panel --full     # full rebuild from all history
  python -m scripts.build_ah_panel --report   # print depth table and exit

Output
------
  data/hk_ah_panel/premium.parquet  -- wide date x H-ticker, fractional (not %)
  data/hk_ah_panel/pairs.json       -- mapping + per-pair joint_start + n_days

Formula
-------
  premium_t = A_cny_t / (H_hkd_t * cny_per_hkd_t) - 1
  cny_per_hkd = USDCNY / USDHKD

Tripwire
--------
  PREMIUM_LO = -0.90 (A cannot trade 90% cheaper than H; flags data error)
  PREMIUM_HI = 10.00 (1000% cap; real historical peak ~300% in 2007-2008)
  FX_MAX_STALE_DAYS = 7

Store decision: git (panel ~1MB; well under 20MB threshold).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib import config, store  # noqa: E402

log = logging.getLogger(__name__)

PREMIUM_LO: float = -0.90
PREMIUM_HI: float = 10.00
FX_MAX_STALE_DAYS: int = 7

AH_IDENTITY_MAP: dict[str, str] = {
    # Config-verified (12 pairs from config.yml hk.ah_pairs)
    "0386.HK": "600028.SS",   # Sinopec Corp
    "0857.HK": "601857.SS",   # PetroChina
    "0939.HK": "601939.SS",   # CCB
    "1088.HK": "601088.SS",   # China Shenhua Energy
    "1211.HK": "002594.SZ",   # BYD
    "1288.HK": "601288.SS",   # Agricultural Bank of China
    "1398.HK": "601398.SS",   # ICBC
    "2318.HK": "601318.SS",   # Ping An Insurance
    "2601.HK": "601601.SS",   # CPIC
    "2628.HK": "601628.SS",   # China Life Insurance
    "3328.HK": "601328.SS",   # Bank of Communications
    "3988.HK": "601988.SS",   # Bank of China
    # Additional confirmed dual-listings
    "0358.HK": "600685.SS",   # Guangzhou Shipyard International
    "0390.HK": "601390.SS",   # China Railway Group
    "0762.HK": "600050.SS",   # China Unicom
    "0763.HK": "000063.SZ",   # ZTE Corp
    "0902.HK": "601985.SS",   # China Power International Development
    "0941.HK": "600941.SS",   # China Mobile
    "0998.HK": "601998.SS",   # China CITIC Bank
    "1186.HK": "601186.SS",   # China Railway Construction Corp
    "1766.HK": "601766.SS",   # CRRC Corp
    "1833.HK": "601901.SS",   # Founder Securities
    "1898.HK": "601898.SS",   # China Coal Energy
    "2333.HK": "601633.SS",   # Great Wall Motor
    "2600.HK": "601600.SS",   # Chalco (Aluminum Corp of China)
}


def _load_fx() -> pd.Series:
    cny = store.read("china", "CNY=X")
    hkd = store.read("hk", "HKD=X")
    if cny is None or hkd is None:
        raise RuntimeError("build_ah_panel: FX stores missing (CNY=X or HKD=X)")
    usdcny = cny["close"].dropna()
    usdhkd = hkd["close"].dropna()
    if usdcny.empty or usdhkd.empty:
        raise RuntimeError("build_ah_panel: FX data empty")
    cny_per_hkd = (usdcny / usdhkd).dropna()
    age_days = (date.today() - cny_per_hkd.index.max().date()).days
    if age_days > FX_MAX_STALE_DAYS:
        raise RuntimeError(
            f"build_ah_panel: FX data stale ({age_days}d > {FX_MAX_STALE_DAYS}d limit)"
        )
    return cny_per_hkd


def _dedupe(df: pd.DataFrame) -> pd.DataFrame:
    df = df[~df.index.duplicated(keep="last")]
    return df.sort_index()


def _tripwire(h: str, s: pd.Series) -> pd.Series:
    n_lo = (s < PREMIUM_LO).sum()
    n_hi = (s > PREMIUM_HI).sum()
    if n_lo:
        log.warning("tripwire %s: %d values below %.2f clipped to NaN", h, n_lo, PREMIUM_LO)
    if n_hi:
        log.warning("tripwire %s: %d values above %.2f clipped to NaN", h, n_hi, PREMIUM_HI)
    s = s.copy()
    s[s < PREMIUM_LO] = float("nan")
    s[s > PREMIUM_HI] = float("nan")
    return s


def _build_pair(h, a, cny_per_hkd, hk_dir, china_dir, since=None):
    h_path = hk_dir / f"{h}.parquet"
    a_path = china_dir / f"{a}.parquet"
    if not h_path.exists() or not a_path.exists():
        return None
    try:
        h_df = pd.read_parquet(h_path)
        a_df = pd.read_parquet(a_path)
    except Exception as exc:
        log.warning("skipping %s/%s: read error %s", h, a, exc)
        return None
    if "close" not in h_df.columns or "close" not in a_df.columns:
        return None
    h_s = _dedupe(h_df["close"].dropna().to_frame())["close"]
    a_s = _dedupe(a_df["close"].dropna().to_frame())["close"]
    if since is not None:
        h_s = h_s[h_s.index >= since]
        a_s = a_s[a_s.index >= since]
    df = pd.concat({"h": h_s, "a": a_s, "fx": cny_per_hkd}, axis=1, join="inner", sort=True).dropna()
    if df.empty:
        return None
    h_in_cny = df["h"] * df["fx"]
    prem = (df["a"] / h_in_cny) - 1.0
    prem = prem.dropna()
    prem = _tripwire(h, prem)
    return prem if not prem.empty else None


def _build_all(full: bool = False):
    data_dir = config.data_dir()
    hk_dir = data_dir / "hk_stocks"
    china_dir = data_dir / "china_stocks"
    panel_dir = data_dir / "hk_ah_panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    panel_path = panel_dir / "premium.parquet"

    cny_per_hkd = _load_fx()

    existing = None
    since = None
    if not full and panel_path.exists():
        try:
            existing = pd.read_parquet(panel_path)
            existing.index = pd.to_datetime(existing.index)
            since = existing.index.max() - pd.Timedelta(days=5)
            log.info("incremental: recomputing from %s", since.date())
        except Exception:
            existing = None

    per_pair = {}
    pairs_meta = []

    for h, a in AH_IDENTITY_MAP.items():
        prem = _build_pair(h, a, cny_per_hkd, hk_dir, china_dir, since=since)
        if prem is None or prem.empty:
            log.debug("pair %s/%s: no data (skipped)", h, a)
            continue
        per_pair[h] = prem.rename(h)

        full_prem = _build_pair(h, a, cny_per_hkd, hk_dir, china_dir, since=None)
        if full_prem is not None and not full_prem.empty:
            joint_start = full_prem.index.min().date().isoformat()
            n_days = len(full_prem)
        else:
            joint_start = prem.index.min().date().isoformat()
            n_days = len(prem)

        pairs_meta.append({"h": h, "a": a, "joint_start": joint_start, "n_days": n_days})

    if not per_pair:
        raise RuntimeError("build_ah_panel: no valid pairs found")

    new_panel = pd.concat(per_pair, axis=1, sort=True)
    new_panel.index = pd.to_datetime(new_panel.index)

    if existing is not None:
        existing_trimmed = existing[existing.index < since]
        panel = pd.concat([existing_trimmed, new_panel], axis=0, sort=True)
        panel = panel[~panel.index.duplicated(keep="last")].sort_index()
        for col in existing.columns:
            if col not in panel.columns:
                panel[col] = existing[col]
    else:
        panel = new_panel

    panel = panel[[c for c in sorted(AH_IDENTITY_MAP.keys()) if c in panel.columns]]
    panel.to_parquet(panel_path)
    pairs_meta.sort(key=lambda x: x["h"])
    with open(panel_dir / "pairs.json", "w", encoding="utf-8") as f:
        json.dump(pairs_meta, f, indent=2)

    log.info("panel: %d dates x %d pairs, saved to %s", *panel.shape, panel_path)
    return panel, pairs_meta


def print_depth_table(panel, pairs_meta):
    cutoffs = [("2005", "2005-01-01"), ("2010", "2010-01-01"),
               ("2015", "2015-01-01"), ("2020", "2020-01-01")]
    print(f"\nA/H Premium Panel -- depth table ({date.today()})")
    print(f"{'Shape:':<20} {panel.shape[0]} dates x {panel.shape[1]} pairs")
    print(f"{'Date range:':<20} {panel.index.min().date()} -> {panel.index.max().date()}")
    print()
    for label, iso in cutoffs:
        n = sum(1 for m in pairs_meta if m.get("joint_start", "9999") <= iso)
        bar = "#" * n
        print(f"  Pairs reaching {label}: {n:>3}  {bar}")
    print()
    latest = panel.iloc[-1].dropna()
    print(f"Today's pairs with data: {len(latest)}")
    print(f"Mean premium today:  {latest.mean()*100:+.1f}%")
    print(f"Median premium today: {latest.median()*100:+.1f}%")
    print()
    print(f"{'H-ticker':<12} {'A-ticker':<14} {'joint_start':<12} {'n_days':<8} {'latest%':>8}")
    print("-" * 60)
    for m in pairs_meta:
        h = m["h"]
        latest_val = panel[h].dropna().iloc[-1] if h in panel.columns and not panel[h].dropna().empty else float("nan")
        print(f"{m['h']:<12} {m['a']:<14} {m['joint_start']:<12} {m['n_days']:<8} {latest_val*100:>7.1f}%")


def main():
    if __name__ == "__main__":
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="Build A/H premium panel")
    parser.add_argument("--full", action="store_true", help="Full rebuild")
    parser.add_argument("--report", action="store_true", help="Print depth table only")
    args = parser.parse_args()

    data_dir = config.data_dir()
    panel_dir = data_dir / "hk_ah_panel"

    if args.report:
        panel_path = panel_dir / "premium.parquet"
        if not panel_path.exists():
            print("Panel not built yet. Run without --report first.")
            sys.exit(1)
        panel = pd.read_parquet(panel_path)
        pairs_path = panel_dir / "pairs.json"
        pairs_meta = json.loads(pairs_path.read_text()) if pairs_path.exists() else []
        print_depth_table(panel, pairs_meta)
        return

    panel, pairs_meta = _build_all(full=args.full)
    print_depth_table(panel, pairs_meta)


if __name__ == "__main__":
    main()
