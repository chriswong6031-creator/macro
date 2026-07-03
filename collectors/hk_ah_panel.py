"""Pure-compute adapter: A/H matched-pair premium panel (masterplan §3 H3, W01A).

IMPORTANT: This adapter makes NO network calls. It reads only in-tree parquet
stores (hk_stocks, china_stocks, china/CNY=X, hk/HKD=X) and writes to
data/hk_ah_panel/. This is legal in the collect lane (RENDER_NO_DRIP compliant):
the computation is deferred to the collect lane so it runs once nightly, not on
every render.

Tripwire: FX staleness and too-few pairs both raise RuntimeError (fail-closed).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

PREMIUM_LO: float = -0.90
PREMIUM_HI: float = 10.00
FX_MAX_STALE_DAYS: int = 7
MIN_LIVE_PAIRS: int = 20

_AH_MAP: dict[str, str] = {
    "0358.HK": "600685.SS",
    "0386.HK": "600028.SS",
    "0390.HK": "601390.SS",
    "0762.HK": "600050.SS",
    "0763.HK": "000063.SZ",
    "0857.HK": "601857.SS",
    "0902.HK": "601985.SS",
    "0939.HK": "601939.SS",
    "0941.HK": "600941.SS",
    "0998.HK": "601998.SS",
    "1088.HK": "601088.SS",
    "1186.HK": "601186.SS",
    "1211.HK": "002594.SZ",
    "1288.HK": "601288.SS",
    "1398.HK": "601398.SS",
    "1766.HK": "601766.SS",
    "1833.HK": "601901.SS",
    "1898.HK": "601898.SS",
    "2318.HK": "601318.SS",
    "2333.HK": "601633.SS",
    "2600.HK": "601600.SS",
    "2601.HK": "601601.SS",
    "2628.HK": "601628.SS",
    "3328.HK": "601328.SS",
    "3988.HK": "601988.SS",
}


def _dedupe(s: pd.Series) -> pd.Series:
    return s[~s.index.duplicated(keep="last")].sort_index()


def _tripwire(h: str, s: pd.Series) -> pd.Series:
    s = s.copy()
    n_lo = (s < PREMIUM_LO).sum()
    n_hi = (s > PREMIUM_HI).sum()
    if n_lo:
        log.warning("tripwire %s: %d below %.2f -> NaN", h, n_lo, PREMIUM_LO)
    if n_hi:
        log.warning("tripwire %s: %d above %.2f -> NaN", h, n_hi, PREMIUM_HI)
    s[s < PREMIUM_LO] = float("nan")
    s[s > PREMIUM_HI] = float("nan")
    return s


class HkAhPanelAdapter(Adapter):
    """Pure-compute; builds / incrementally updates data/hk_ah_panel/."""

    name = "hk_ah_panel"
    group = "hk_ah_panel"
    stale_after_days = 5

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:  # type: ignore[override]
        data_dir = config.data_dir()
        hk_dir = data_dir / "hk_stocks"
        china_dir = data_dir / "china_stocks"
        panel_dir = data_dir / "hk_ah_panel"
        panel_dir.mkdir(parents=True, exist_ok=True)
        panel_path = panel_dir / "premium.parquet"

        cny_raw = store.read("china", "CNY=X")
        hkd_raw = store.read("hk", "HKD=X")
        if cny_raw is None or hkd_raw is None:
            raise RuntimeError("hk_ah_panel: FX stores missing")
        usdcny = cny_raw["close"].dropna()
        usdhkd = hkd_raw["close"].dropna()
        cny_per_hkd = (usdcny / usdhkd).dropna()
        cny_per_hkd = cny_per_hkd[~cny_per_hkd.index.duplicated(keep="last")].sort_index()

        fx_age = (date.today() - cny_per_hkd.index.max().date()).days
        if fx_age > FX_MAX_STALE_DAYS:
            raise RuntimeError(
                f"hk_ah_panel: FX stale {fx_age}d > {FX_MAX_STALE_DAYS}d limit"
            )

        existing = None
        since = None
        if not full_history and panel_path.exists():
            try:
                existing = pd.read_parquet(panel_path)
                existing.index = pd.to_datetime(existing.index)
                since = existing.index.max() - pd.Timedelta(days=5)
            except Exception:
                existing = None

        per_pair = []
        pairs_meta = []

        for h, a in _AH_MAP.items():
            h_path = hk_dir / f"{h}.parquet"
            a_path = china_dir / f"{a}.parquet"
            if not h_path.exists() or not a_path.exists():
                continue
            try:
                h_df = pd.read_parquet(h_path)
                a_df = pd.read_parquet(a_path)
            except Exception:
                continue
            if "close" not in h_df.columns or "close" not in a_df.columns:
                continue
            h_s = _dedupe(h_df["close"].dropna())
            a_s = _dedupe(a_df["close"].dropna())
            h_s_inc = h_s[h_s.index >= since] if since is not None else h_s
            a_s_inc = a_s[a_s.index >= since] if since is not None else a_s
            df = pd.concat({"h": h_s_inc, "a": a_s_inc, "fx": cny_per_hkd},
                           axis=1, join="inner", sort=True).dropna()
            if df.empty:
                continue
            prem = (df["a"] / (df["h"] * df["fx"])) - 1.0
            prem = _tripwire(h, prem.dropna()).rename(h)
            if prem.empty:
                continue
            per_pair.append(prem)

            df2 = pd.concat({"h": h_s, "a": a_s, "fx": cny_per_hkd},
                            axis=1, join="inner", sort=True).dropna()
            if not df2.empty:
                prem2 = ((df2["a"] / (df2["h"] * df2["fx"])) - 1.0).dropna()
                prem2 = _tripwire(h, prem2)
                pairs_meta.append({
                    "h": h, "a": a,
                    "joint_start": str(prem2.index.min().date()),
                    "n_days": len(prem2),
                })

        if not per_pair:
            raise RuntimeError("hk_ah_panel: no valid pairs found")

        new_panel = pd.concat(per_pair, axis=1, sort=True)
        new_panel.index = pd.to_datetime(new_panel.index)

        if existing is not None:
            trimmed = existing[existing.index < since] if since is not None else existing
            panel = pd.concat([trimmed, new_panel], axis=0, sort=True)
            panel = panel[~panel.index.duplicated(keep="last")].sort_index()
            for col in existing.columns:
                if col not in panel.columns:
                    panel[col] = existing[col]
        else:
            panel = new_panel

        panel = panel[[c for c in sorted(_AH_MAP.keys()) if c in panel.columns]]

        latest_nonnan = panel.iloc[-1].dropna()
        if len(latest_nonnan) < MIN_LIVE_PAIRS:
            raise RuntimeError(
                f"hk_ah_panel: only {len(latest_nonnan)} pairs with data "
                f"(min {MIN_LIVE_PAIRS})"
            )

        panel.to_parquet(panel_path)
        pairs_meta.sort(key=lambda x: x["h"])
        with open(panel_dir / "pairs.json", "w", encoding="utf-8") as f:
            json.dump(pairs_meta, f, indent=2)

        meta_df = pd.DataFrame(pairs_meta)
        return {"premium": panel, "pairs_meta": meta_df}
