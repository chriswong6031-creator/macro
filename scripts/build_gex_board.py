"""Build the dealer-gamma "magnets" board -> site/gex.html (P3, display-only).

Standalone (like build_discovery.py). Fetches the live Cboe delayed chain for a set
of liquid underlyings, runs engine.gex_engine.compute_gex for the summary AND a
per-strike net-GEX ladder (the dealer-wall profile), then renders templates/gex.html.j2.

HONEST FRAMING (carried onto the page): daily EOD/delayed levels, NOT live intraday
flow; a VOL-REGIME + LEVELS MAP, NOT a buy list; the dealer long-call/short-put SIGN
is an unobservable assumption (fragile for single names). See LIMITATIONS.md.

Run: .venv/bin/python -m scripts.build_gex_board
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_gex_board")

# (cboe symbol, en label, zh label) — indices first, then liquid single names
BOARD = [("_SPX", "S&P 500", "标普500"), ("SPY", "SPY", "标普ETF"),
         ("QQQ", "QQQ", "纳指ETF"), ("IWM", "IWM", "小盘ETF"),
         ("AAPL", "Apple", "苹果"), ("NVDA", "Nvidia", "英伟达"), ("TSLA", "Tesla", "特斯拉")]
LADDER_WINDOW = 0.08   # ±8% of spot for the dealer-wall profile
LADDER_MAX = 26        # strike rows shown


def _f(x, n=2):
    return round(float(x), n) if isinstance(x, (int, float)) and x is not None and x == x else None


def _ladder(chain: pd.DataFrame, spot: float, cfg: dict) -> list[dict]:
    """Per-strike net GEX (the call-wall / put-wall profile) within ±8% of spot."""
    w = LADDER_WINDOW
    c = chain[(chain["T"] > 0) & chain["K"].between(spot * (1 - w), spot * (1 + w))
              & (chain["oi"] > 0) & chain["gamma"].notna()].copy()
    if c.empty:
        return []
    mult, pm = cfg.get("contract_multiplier", 100.0), cfg.get("pct_move", 0.01)
    sign = np.where(c["is_call"], 1.0, -1.0)
    base = c["gamma"] * c["oi"] * mult * spot ** 2 * pm
    c["net_gex"] = sign * base
    c["abs_dg"] = base.abs()
    g = (c.groupby("K").agg(net_gex=("net_gex", "sum"), abs_dg=("abs_dg", "sum"))
         .reset_index().sort_values("abs_dg", ascending=False).head(LADDER_MAX)
         .sort_values("K", ascending=False))
    mx = float(g["net_gex"].abs().max()) or 1.0
    return [{"strike": float(r["K"]), "net_gex_mn": round(float(r["net_gex"]) / 1e6, 1),
             "pct": round(float(r["net_gex"]) / mx * 100, 1),
             "side": "call" if r["net_gex"] >= 0 else "put"} for _, r in g.iterrows()]


def _vm(adapter, sym, label, zh) -> dict | None:
    from collectors.cboe import GEX_Q
    from engine.gex_engine import compute_gex
    try:
        chain, spot = adapter._chain(sym)
    except Exception as e:  # noqa: BLE001 — partial board still useful
        log.warning("gex board: %s chain failed: %s", sym, e)
        return None
    gcfg = adapter.cfg["gex"]
    ecfg = {k: gcfg[k] for k in ("contract_multiplier", "pct_move",
                                 "strike_window_pct", "max_expiry_days") if k in gcfg}
    summ = compute_gex(chain, spot, cfg={**ecfg, "r": gcfg.get("r", 0.043), "q": GEX_Q.get(sym, 0.0)})
    if summ.get("tier") in (None, "no_options"):
        return None
    return {"key": sym.lstrip("_"), "label": label, "zh": zh,
            "is_index": sym in ("_SPX", "SPY", "QQQ", "IWM"),
            "spot": _f(summ.get("spot")), "regime": summ.get("gamma_regime"), "tier": summ.get("tier"),
            "net_gex_bn": _f(summ.get("net_gex_bn")), "gamma_flip": _f(summ.get("gamma_flip")),
            "dist_to_flip_pct": _f(summ.get("dist_to_flip_pct")), "magnet_up": _f(summ.get("magnet_up")),
            "magnet_down": _f(summ.get("magnet_down")), "charm_anchor": _f(summ.get("charm_anchor")),
            "iv30": (round(summ["iv30"] * 100, 1) if summ.get("iv30") is not None else None),
            "put_call_oi_ratio": _f(summ.get("put_call_oi_ratio")), "max_pain": _f(summ.get("max_pain")),
            "top_oi_share": _f(summ.get("top_oi_share"), 3), "n_strikes": summ.get("n_strikes"),
            "ladder": _ladder(chain, spot, ecfg)}


def main() -> int:
    from collectors.cboe import GexAdapter
    adapter = GexAdapter()
    vms = [v for v in (_vm(adapter, s, l, z) for s, l, z in BOARD) if v]
    if not vms:
        log.error("gex board: no symbols computed; skipping")
        return 0
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=td, tr=tr)
    html = env.get_template("gex.html.j2").render(symbols=vms, built=built)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    (site / "gex.html").write_text(html)
    log.info("wrote %s/gex.html (%d symbols: %s)", site, len(vms), ", ".join(v["key"] for v in vms))
    return 0


if __name__ == "__main__":
    sys.exit(main())
