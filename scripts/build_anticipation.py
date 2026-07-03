"""Build the Anticipation page -> site/anticipation.html (+ site/anticipationdata/anticipation.json).

Multi-horizon probabilistic forward-outcome CONES (the validated conditional drawdown /
return-quantile distribution; direction is display-only/coin-flip) for the S&P/Nasdaq
index, the 11 SPDR sectors, and a watchlist of mega-caps. Reads
engine.anticipation.anticipate() with the shared market overlay (macro_legs_frame) and
the Phase-0 gate (data/regime/anticipation_gate.json). Additive — any failure logs and
returns 0 so it never breaks the rest of the site.

Run standalone:  python -m scripts.build_anticipation
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402
from engine import anticipation  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_anticipation")

INDEX = [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("IWM", "Russell 2000")]
SECTORS = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care",
           "XLI": "Industrials", "XLY": "Cons. Discretionary", "XLP": "Cons. Staples",
           "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real Estate",
           "XLC": "Communication"}
# Narrow thematic ETFs (deep history) — purer-driver exposures than broad sectors.
THEMES = {"SMH": "Semiconductors", "SOXX": "Semis (SOXX)", "IGV": "Software", "XBI": "Biotech",
          "IBB": "Biotech (IBB)", "GDX": "Gold Miners", "GDXJ": "Jr Gold Miners",
          "KRE": "Regional Banks", "ITB": "Homebuilders", "XME": "Metals & Mining",
          "XOP": "Oil & Gas E&P", "OIH": "Oil Services", "XRT": "Retail", "TAN": "Solar"}
# Default watchlist — the most-watched US mega-caps (one-line change; all in data/stocks).
WATCHLIST = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD",
             "JPM", "XOM", "LLY", "UNH", "COST", "V", "MA", "HD", "WMT", "BRK-B", "CAT"]


def _close(group: str, tkr: str):
    d = config.data_dir()
    p = (d / "stocks" / f"{tkr}.parquet") if group == "stock" else (d / "yahoo" / f"{tkr}.parquet")
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)["close"].dropna()
    except Exception:
        return None


def main() -> int:
    try:
        site = config.ROOT / "site"
        built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        d = config.data_dir()
        bench = _close("index", "SPY")
        try:
            breadth = pd.read_parquet(d / "breadth" / "breadth.parquet")["pct_above_200"]
        except Exception:
            breadth = None
        macro = anticipation.macro_legs_frame()
        gate = anticipation.load_gate("US")

        groups = ([("index", t, n) for t, n in INDEX]
                  + [("sector", t, n) for t, n in SECTORS.items()]
                  + [("theme", t, n) for t, n in THEMES.items()]
                  + [("stock", t, t) for t in WATCHLIST])
        assets = []
        for group, tkr, name in groups:
            close = _close(group, tkr)
            if close is None or len(close) < 300:
                log.warning("skip %s (no/short data)", tkr)
                continue
            a = anticipation.anticipate(
                close, bench=bench, breadth=breadth, asset=tkr,
                asset_class=("us_equity" if group == "stock" else group),
                macro_frame=(None if macro.empty else macro), gate=gate)
            if not a:
                continue
            a["name"], a["group"] = name, group
            assets.append(a)
        if not assets:
            log.warning("no anticipation assets built — skipping page")
            return 0

        as_of = assets[0]["as_of"]
        macro_now = (anticipation.macro_overlay(macro, gate, as_of)
                     if not macro.empty else None)
        payload = {
            "as_of": as_of, "generated_utc": built,
            "go_legs": sorted(k for k, v in gate.items() if v == "GO"),
            "macro": ({"stress_pct": macro_now["stress_pct"], "width_mult": macro_now["width_mult"],
                       "go_legs": macro_now["go_legs"]} if macro_now else None),
            "horizons_meta": {k: list(v[:2]) for k, v in anticipation.HORIZONS.items()},
            "n_assets": len(assets), "assets": assets,
        }
        fdir = site / "anticipationdata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "anticipation.json").write_text(json.dumps(payload, separators=(",", ":"), default=str))
        # per-ticker JSONs so the stock-analyzer panel can fetch one name (safeTicker
        # mirrors stockdata.js: [=^] -> _; BRK-B keeps its dash)
        for a in assets:
            safe = a["asset"].replace("=", "_").replace("^", "_")
            (fdir / f"{safe}.json").write_text(json.dumps(a, separators=(",", ":"), default=str))

        env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
        html = env.get_template("anticipation.html.j2").render(
            d=payload, data_json=json.dumps(payload, separators=(",", ":"), default=str),
            generated_utc=built)
        write_page(site / "anticipation.html", html)
        log.info("wrote %s/anticipation.html (%d assets, %d KB)", site, len(assets), len(html) // 1024)
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_anticipation failed (non-fatal): %s", e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
