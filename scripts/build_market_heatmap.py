"""Build the China / Hong Kong / Canada sector-treemap heatmap feeds.

The international sibling of ``scripts/build_sp500_heatmap.py``. Reads each
market's local close matrix + sector classification (offline-safe, no keys) and
writes ``site/marketdata/<market>_heatmap.json`` consumed by the shared
``site/heatmap.js`` (flat Sector → stock treemap, ``map_type:"stocks"``).

Sizing
------
* China  — real market cap (``china_search/members.parquet`` ``mktcap_yi`` × 1e8).
* Canada — real market cap (``canada_fundamentals`` ``marketCap``), gaps filled
           from the index ``weight`` calibrated against the names that carry a cap.
* HK     — average dollar turnover (close × volume over the last sessions) from
           the per-name OHLC store, a liquidity proxy for size (no shares feed).

Usage
-----
    python -m scripts.build_market_heatmap                 # all three markets
    python -m scripts.build_market_heatmap --market china  # one market
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import market_heatmap as hm  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_market_heatmap")

MARKETS = ("china", "hk", "canada")
_ADV_WINDOW = 30  # sessions averaged for the HK dollar-turnover size proxy


def _data(*parts: str) -> Path:
    return config.data_dir().joinpath(*parts)


# --------------------------------------------------------------------------- #
#  China
# --------------------------------------------------------------------------- #
def _load_china() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict, dict]:
    members = pd.read_parquet(_data("china_search", "members.parquet"))
    closes = pd.read_parquet(_data("china_search", "closes.parquet")).sort_index()
    closes.index = pd.to_datetime(closes.index)
    closes = closes.loc[:, ~closes.columns.duplicated()]

    # English display name from name_en (the combined `name` column is "EN / 中文").
    cons = pd.DataFrame(index=members.index)
    cons.index.name = "ticker"
    cons["name"] = members.get("name_en", members.get("name")).fillna(members.index.to_series())
    cons["sector"] = members["sector"].astype(str)

    # china_universe seeds CSI/config extras with a 30.0亿 sentinel (~46% of members
    # carry it exactly) — NOT a real cap; sizing tiles from it fabricates a uniform
    # mid-cap for half the map. Drop the sentinel, then fill the gaps with real caps
    # from the asof-gated Tushare valuation plane (same guard as build_china_library).
    _PLACEHOLDER_MCAP = 30.0
    caps: dict[str, float] = {}
    if "mktcap_yi" in members.columns:
        for t, v in members["mktcap_yi"].items():
            if pd.notna(v) and float(v) > 0 and float(v) != _PLACEHOLDER_MCAP:
                caps[t] = float(v) * 1e8  # 亿 CNY -> absolute CNY
    try:
        from engine.tushare_freshness import prefer_tushare as _prefer_tv
        tv_p = _data("tushare", "valuation.parquet")
        pe_p = _data("china_a_val", "pe.parquet")
        tv = pd.read_parquet(tv_p) if tv_p.exists() else None
        chosen, _src = _prefer_tv(tv if (tv is not None and "total_mv_yi" in tv.columns) else None,
                                  pd.read_parquet(pe_p) if pe_p.exists() else None)
        if _src == "tushare" and chosen is not None and "total_mv_yi" in chosen.columns:
            filled = 0
            member_set = set(cons.index.astype(str))
            for _, r in chosen.iterrows():
                t, v = str(r.get("ticker")), r.get("total_mv_yi")
                if t in member_set and t not in caps and pd.notna(v) and float(v) > 0:
                    caps[t] = float(v) * 1e8
                    filled += 1
            log.info("china heatmap caps: filled %d names from Tushare total_mv_yi "
                     "(30.0亿 placeholders dropped)", filled)
    except Exception as e:  # noqa: BLE001 — Tushare overlay is additive; engine floor covers the rest
        log.debug("china tushare mktcap overlay skipped (%s)", e)

    names_zh: dict[str, str] = {}
    if "name_zh" in members.columns:
        names_zh = {t: str(v) for t, v in members["name_zh"].items() if pd.notna(v) and str(v).strip()}

    return cons, closes, caps, {}, names_zh


# --------------------------------------------------------------------------- #
#  Hong Kong — size = average dollar turnover (liquidity proxy)
# --------------------------------------------------------------------------- #
def _load_hk() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict, dict]:
    cons = pd.read_parquet(_data("hk_breadth", "constituents.parquet"))
    if cons.index.name != "symbol" and "symbol" in cons.columns:
        cons = cons.set_index("symbol")
    cons.index.name = "ticker"

    # The breadth cache is fresh (latest session) but shallow (~30d for most
    # names); closes_deep carries decades of history but ends a few sessions back.
    # Merge so the fresh recent prints win and the deep history fills the rest —
    # the two stores are the same adjusted yfinance series (level-identical on
    # overlap), so the splice is seamless. This unlocks 3M/6M/YTD/1Y for HK.
    breadth = pd.read_parquet(_data("hk_breadth", "_closes_cache.parquet")).sort_index()
    breadth.index = pd.to_datetime(breadth.index)
    breadth = breadth.loc[:, ~breadth.columns.duplicated()]
    deep_p = _data("hk_search", "closes_deep.parquet")
    if deep_p.exists():
        try:
            deep = pd.read_parquet(deep_p).sort_index()
            deep.index = pd.to_datetime(deep.index)
            deep = deep.loc[:, ~deep.columns.duplicated()]
            closes = breadth.combine_first(deep).sort_index()
        except Exception as e:  # noqa: BLE001 — deep store optional; fall back to breadth
            log.warning("hk closes_deep unreadable (%s); using breadth cache only", e)
            closes = breadth
    else:
        closes = breadth

    # ADV$ from the per-name OHLC store (close × volume), averaged over the last
    # valid sessions. Tracks size/importance well (Tencent/Alibaba on top).
    turnover: dict[str, float] = {}
    sdir = _data("hk_stocks")
    if sdir.exists():
        for t in cons.index:
            fp = sdir / f"{t}.parquet"
            if not fp.exists():
                continue
            try:
                df = pd.read_parquet(fp)
            except Exception:  # noqa: BLE001 — corrupt parquet must not break the build
                continue
            if "close" not in df.columns or "volume" not in df.columns:
                continue
            tail = df.dropna(subset=["close", "volume"]).tail(_ADV_WINDOW)
            if len(tail) >= 5:
                adv = float((tail["close"] * tail["volume"]).mean())
                if adv > 0:
                    turnover[t] = adv
    missing = [t for t in cons.index if t not in turnover]
    if missing:
        log.warning("hk heatmap: no turnover for %d/%d names (sized at floor): %s",
                    len(missing), len(cons.index), ", ".join(missing[:12]))
    # Chinese tile labels from the curated map (HK has no zh-name feed). Names
    # absent from the map fall back to the English name in the renderer.
    names_zh = {t: hm.HK_NAME_ZH[t] for t in cons.index if t in hm.HK_NAME_ZH}
    no_zh = [t for t in cons.index if t not in hm.HK_NAME_ZH]
    if no_zh:
        log.info("hk heatmap: %d/%d names have no zh label (English fallback): %s",
                 len(no_zh), len(cons.index), ", ".join(no_zh[:12]))
    return cons, closes, turnover, {}, names_zh


# --------------------------------------------------------------------------- #
#  Canada — real market cap, gaps filled from the calibrated index weight
# --------------------------------------------------------------------------- #
def _canada_caps_from_fundamentals() -> dict[str, float]:
    p = _data("canada_fundamentals", "fundamentals.parquet")
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("canada fundamentals unreadable: %s", e)
        return {}
    caps: dict[str, float] = {}
    for _, row in df.iterrows():
        t = str(row.get("ticker") or "").strip()
        pl = row.get("payload")
        if not t or pl is None:
            continue
        try:
            pl = json.loads(pl) if isinstance(pl, str) else pl
        except Exception:  # noqa: BLE001
            continue
        cap = (pl or {}).get("marketCap")
        if cap is not None and float(cap) > 0:
            caps[t] = float(cap)
    return caps


def _complete_caps_from_weight(caps: dict[str, float], weights: dict[str, float]) -> dict[str, float]:
    """Estimate a cap for names missing one from the index weight, calibrated
    (cap ≈ k · weight) against the names that carry both. Keeps mid-caps that
    lack a fundamentals row sized sensibly instead of collapsing to a floor."""
    ratios = [caps[t] / weights[t] for t in weights if t in caps and weights[t] > 0]
    if not ratios:
        return caps
    k = float(np.median(ratios))
    filled = dict(caps)
    n = 0
    for t, w in weights.items():
        if filled.get(t, 0) <= 0 and w > 0:
            filled[t] = k * w
            n += 1
    if n:
        log.info("canada cap-completion: estimated %d caps from index weight", n)
    return filled


def _load_canada() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict, dict]:
    members = pd.read_parquet(_data("canada_search", "members.parquet"))
    closes = pd.read_parquet(_data("canada_search", "closes.parquet")).sort_index()
    closes.index = pd.to_datetime(closes.index)
    closes = closes.loc[:, ~closes.columns.duplicated()]

    cons = pd.DataFrame(index=members.index)
    cons.index.name = "ticker"
    cons["name"] = members["name"].astype(str)
    cons["sector"] = members["sector"].astype(str)

    weights: dict[str, float] = {}
    if "weight" in members.columns:
        weights = {t: float(v) for t, v in members["weight"].items() if pd.notna(v) and float(v) > 0}

    caps = _canada_caps_from_fundamentals()
    # keep only universe names, then complete the gaps from weight
    caps = {t: v for t, v in caps.items() if t in members.index}
    caps = _complete_caps_from_weight(caps, weights)
    return cons, closes, caps, weights, {}


_LOADERS = {"china": _load_china, "hk": _load_hk, "canada": _load_canada}


def build(market: str, site: Path | None = None, *, generated_utc: str | None = None) -> dict:
    """Assemble + write one market's heatmap JSON. Returns the payload."""
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    cons, closes, caps, weights, names_zh = _LOADERS[market]()

    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    payload = hm.build_market_heatmap(
        market, cons, closes,
        caps=caps or None,
        weights=weights or None,
        names_zh=names_zh or None,
        generated_utc=generated_utc,
    )

    outdir = site / "marketdata"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{market}_heatmap.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s — %d tiles, %d sectors, size=%s, asof=%s",
             out.name, payload["n_tiles"], len(payload["sectors"]),
             payload["size_basis"], payload["asof"])
    return payload


def build_all(site: Path | None = None, *, generated_utc: str | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m in MARKETS:
        try:
            out[m] = build(m, site, generated_utc=generated_utc)
        except Exception as e:  # noqa: BLE001 — one market must never break the others / the site
            log.error("%s heatmap failed: %s", m, e)
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Build the CN/HK/CA sector heatmap feeds")
    ap.add_argument("--market", choices=MARKETS, help="build a single market (default: all)")
    args = ap.parse_args(argv)
    if args.market:
        build(args.market)
    else:
        build_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
