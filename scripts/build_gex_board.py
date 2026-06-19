"""Build the Options Desk — dealer-gamma + options-flow page -> site/gex.html (display-only).

Standalone (like build_discovery.py). For a broad universe of liquid optionable
underlyings it fetches the live Cboe delayed chain, runs engine.gex_model (the rich
modeling layer: net-gamma profile curve, GEX-by-strike walls, strike×expiry heatmap,
vol smile + IV term structure, expected move, max-pain per expiry), and writes:

  * site/gex/<KEY>.json  — one rich payload per underlying, fetched on demand by the
                           page so any prebuilt ticker is instantly look-up-able.
  * site/gex/index.json  — a lightweight manifest (regime / net-GEX / flip / IV per
                           symbol) that drives the at-a-glance board + the search.
  * site/gex.html        — the interactive shell (templates/gex.html.j2 + site/gex.js).

HONEST FRAMING (carried onto the page): daily delayed Cboe levels, NOT live intraday
flow; a VOL-REGIME + LEVELS MAP, not a buy list; the dealer long-call/short-put SIGN is
an unobservable assumption — robust for indices, fragile for single names. See
LIMITATIONS.md.

Run: .venv/bin/python -m scripts.build_gex_board
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_gex_board")

# (cboe symbol, key, en label, zh label, group). cboe index tickers carry a leading
# underscore (_SPX). Groups drive the board's section headers + search filters. A
# failed/thin symbol is skipped gracefully — partial coverage is still useful.
UNIVERSE = [
    ("_SPX", "SPX", "S&P 500", "标普500", "Index"),
    ("_NDX", "NDX", "Nasdaq 100", "纳指100", "Index"),
    ("_RUT", "RUT", "Russell 2000", "罗素2000", "Index"),
    ("SPY", "SPY", "S&P 500 ETF", "标普500 ETF", "ETF"),
    ("QQQ", "QQQ", "Nasdaq 100 ETF", "纳指100 ETF", "ETF"),
    ("IWM", "IWM", "Russell 2000 ETF", "小盘ETF", "ETF"),
    ("DIA", "DIA", "Dow ETF", "道指ETF", "ETF"),
    ("SMH", "SMH", "Semiconductors ETF", "半导体ETF", "Sector ETF"),
    ("XLK", "XLK", "Technology ETF", "科技板块ETF", "Sector ETF"),
    ("XLF", "XLF", "Financials ETF", "金融板块ETF", "Sector ETF"),
    ("XLE", "XLE", "Energy ETF", "能源板块ETF", "Sector ETF"),
    ("GLD", "GLD", "Gold ETF", "黄金ETF", "Macro ETF"),
    ("TLT", "TLT", "20Y+ Treasury ETF", "长债ETF", "Macro ETF"),
    ("HYG", "HYG", "High-Yield Credit ETF", "高收益债ETF", "Macro ETF"),
    ("ARKK", "ARKK", "ARK Innovation ETF", "ARK创新ETF", "Macro ETF"),
    ("NVDA", "NVDA", "Nvidia", "英伟达", "Mega-cap Tech"),
    ("AAPL", "AAPL", "Apple", "苹果", "Mega-cap Tech"),
    ("MSFT", "MSFT", "Microsoft", "微软", "Mega-cap Tech"),
    ("AMZN", "AMZN", "Amazon", "亚马逊", "Mega-cap Tech"),
    ("GOOGL", "GOOGL", "Alphabet", "谷歌", "Mega-cap Tech"),
    ("META", "META", "Meta", "Meta", "Mega-cap Tech"),
    ("TSLA", "TSLA", "Tesla", "特斯拉", "Mega-cap Tech"),
    ("AMD", "AMD", "AMD", "超威", "Semis & AI"),
    ("AVGO", "AVGO", "Broadcom", "博通", "Semis & AI"),
    ("MU", "MU", "Micron", "美光", "Semis & AI"),
    ("SMCI", "SMCI", "Super Micro", "超微电脑", "Semis & AI"),
    ("MRVL", "MRVL", "Marvell", "迈威尔", "Semis & AI"),
    ("ARM", "ARM", "Arm Holdings", "Arm", "Semis & AI"),
    ("PLTR", "PLTR", "Palantir", "Palantir", "Popular / Retail"),
    ("COIN", "COIN", "Coinbase", "Coinbase", "Popular / Retail"),
    ("MSTR", "MSTR", "MicroStrategy", "微策略", "Popular / Retail"),
    ("NFLX", "NFLX", "Netflix", "奈飞", "Popular / Retail"),
    ("BABA", "BABA", "Alibaba", "阿里巴巴", "Popular / Retail"),
    ("HOOD", "HOOD", "Robinhood", "Robinhood", "Popular / Retail"),
    ("UBER", "UBER", "Uber", "优步", "Popular / Retail"),
    ("GME", "GME", "GameStop", "游戏驿站", "Popular / Retail"),
]

# dividend yields used by the dividend-adjusted greeks (small effect; names -> 0)
DIV_Q = {"SPX": 0.013, "SPY": 0.013, "QQQ": 0.006, "IWM": 0.013, "DIA": 0.018,
         "NDX": 0.008, "RUT": 0.013, "GLD": 0.0, "TLT": 0.038, "HYG": 0.058,
         "XLK": 0.006, "XLF": 0.016, "XLE": 0.032, "SMH": 0.004}

HISTORY_DAYS = 40  # net-GEX history sparkline depth (from the stored daily summary)


def _history(key: str) -> list[dict]:
    """Last HISTORY_DAYS of stored daily {date, net_gex_bn, regime} for the sparkline.
    Reads the cboe summary parquet the daily collector accrues; empty if absent."""
    try:
        from lib import store
        df = store.read("cboe", f"gex_{key}")
        if df is None or not len(df) or "net_gex_bn" not in df.columns:
            return []
        df = df.tail(HISTORY_DAYS)
        return [{"date": str(pd.Timestamp(i).date()),
                 "net_gex_bn": (round(float(v), 2) if pd.notna(v) else None),
                 "regime": (str(r) if pd.notna(r) else None)}
                for i, v, r in zip(df.index, df["net_gex_bn"],
                                   df.get("gamma_regime", pd.Series([None] * len(df))))]
    except Exception:  # noqa: BLE001 — history is a nicety, never fatal
        return []


def _build_one(adapter, row: dict) -> tuple[dict, dict] | None:
    """Fetch + model one underlying -> (full payload, manifest row). None on failure."""
    from engine.gex_model import build_model
    sym, key = row["sym"], row["key"]
    try:
        chain, spot = adapter._chain(sym)
    except Exception as e:  # noqa: BLE001 — partial board still useful
        log.warning("gex: %s chain failed: %s", sym, e)
        return None
    gcfg = adapter.cfg.get("gex", {})
    cfg = {"q": DIV_Q.get(key, 0.0), "r": 0.043,
           "max_expiry_days": gcfg.get("max_expiry_days", 365)}
    meta = {"key": key, "en": row["en"], "zh": row["zh"], "grp": row["grp"],
            "asof": str(date.today())}
    model = build_model(chain, spot, cfg, meta=meta, history=_history(key))
    if model is None:
        log.warning("gex: %s modeled empty — skipping", sym)
        return None
    s = model["summary"]
    em = model["expected_move"]
    manifest = {
        "key": key, "en": row["en"], "zh": row["zh"], "grp": row["grp"],
        "spot": s["spot"], "regime": s["regime"], "tier": s["tier"],
        "net_gex_bn": s["net_gex_bn"], "gamma_flip": s["gamma_flip"],
        "dist_to_flip_pct": s["dist_to_flip_pct"], "iv30": s["iv30"],
        "call_wall": s["call_wall"], "put_wall": s["put_wall"],
        "max_pain": s["max_pain"], "daily_move_pct": em.get("daily_pct"),
        "put_call_oi_ratio": s["put_call_oi_ratio"], "asof": str(date.today()),
    }
    return model, manifest


def main() -> int:
    from collectors.cboe import GexAdapter
    adapter = GexAdapter()
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site / "gex"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    for sym, key, en, zh, grp in UNIVERSE:
        res = _build_one(adapter, {"sym": sym, "key": key, "en": en, "zh": zh, "grp": grp})
        if not res:
            continue
        model, mrow = res
        (out_dir / f"{key}.json").write_text(json.dumps(model, default=float, separators=(",", ":")))
        manifest.append(mrow)
        log.info("gex: %s ok (regime=%s net=%.2f flip=%s)",
                 key, mrow["regime"], mrow["net_gex_bn"] or 0, mrow["gamma_flip"])

    if not manifest:
        log.error("gex: no symbols computed; leaving prior site/gex.html in place")
        return 0

    (out_dir / "index.json").write_text(json.dumps(manifest, default=float, separators=(",", ":")))

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=td, tr=tr)
    # group order for the board sections
    groups = []
    for m in manifest:
        if m["grp"] not in groups:
            groups.append(m["grp"])
    keys = {m["key"] for m in manifest}
    default_key = "SPY" if "SPY" in keys else manifest[0]["key"]
    html = env.get_template("gex.html.j2").render(
        manifest=manifest, groups=groups, built=built,
        default_key=default_key, manifest_json=json.dumps(manifest, default=float))
    (site / "gex.html").write_text(html)
    log.info("wrote %s/gex.html + %d per-symbol payloads (%s)",
             site, len(manifest), ", ".join(m["key"] for m in manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
