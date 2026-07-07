"""Build the Technical Lab hub: site/tech_lab.html.

Single-page hub combining a signal screener (what is firing now) and a signal
lab (descriptive backtest profiles).  Display-only / research framing.

Reads:
  site/factordata/tech_screener.json  — per-signal firing tickers + per-stock profile
  site/factordata/tech_lab.json       — per-signal backtest profile

If either JSON is absent at build time the page renders with an embedded SAMPLE
fixture and a 'data pending nightly generation' note.  The builder NEVER raises —
it wraps everything in try/except and returns 0 (additive, like build_congress.py).

Schema (shared contract — data-gen writes, this UI reads):

tech_screener.json = {
  "generated_utc": str, "universe_n": int,
  "signals": {
    "<signal_id>": {
      "display_en", "display_zh", "family", "direction": +1|-1|0, "glyph",
      "n_firing": int,
      "tickers": [{"ticker","name","price","score","band"}, ...]
    }
  },
  "stocks": {
    "<TICKER>": {
      "name","price","score","band","active_buy":int,"active_total":int,
      "perf_7d","perf_30d","perf_12m",
      "signals": [{"id","display_en","direction","glyph","state":0|1,"age_days":int}, ...]
    }
  }
}

tech_lab.json = {
  "generated_utc": str, "universe_n": int,
  "universe_caveat": "survivor mega-caps; descriptive not §5.9 verdict",
  "signals": {
    "<signal_id>": {
      "display_en","family","direction","n_fires":int,"n_months":int,
      "wr_21d":float,"mean_21d":float,"base_wr":float,"base_mean":float,
      "edge_wr":float,"edge_mean":float,
      "mfe_mae_med":float,"durable_rate":float,"median_lag_pct":float,
      "days_since_low_med":float,"up_tape_pct":float,
      "wr_pre2010":float|null,"wr_post2010":float
    }
  }
}
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("build_tech_lab")

# ---------------------------------------------------------------------------
# Sample fixtures — rendered when real JSON is absent
# ---------------------------------------------------------------------------
_SAMPLE_SCREENER: dict = {
    "generated_utc": "pending",
    "universe_n": 0,
    "_sample": True,
    "signals": {
        "MACD_CROSS_UP": {
            "display_en": "MACD Cross Up",
            "display_zh": "MACD 金叉",
            "family": "momentum",
            "direction": 1,
            "glyph": "▲",
            "n_firing": 3,
            "tickers": [
                {"ticker": "AAPL", "name": "Apple Inc.", "price": 195.0, "score": 7.2, "band": "high"},
                {"ticker": "MSFT", "name": "Microsoft Corp.", "price": 420.0, "score": 6.8, "band": "high"},
                {"ticker": "NVDA", "name": "NVIDIA Corp.", "price": 130.0, "score": 5.9, "band": "moderate"},
            ],
        },
        "RSI_OVERSOLD": {
            "display_en": "RSI Oversold Bounce",
            "display_zh": "RSI 超卖反弹",
            "family": "mean_reversion",
            "direction": 1,
            "glyph": "↑",
            "n_firing": 2,
            "tickers": [
                {"ticker": "META", "name": "Meta Platforms", "price": 560.0, "score": 4.1, "band": "moderate"},
                {"ticker": "AMZN", "name": "Amazon.com", "price": 195.0, "score": 3.8, "band": "low"},
            ],
        },
        "COMPOSITE": {
            "display_en": "Composite Score",
            "display_zh": "综合评分",
            "family": "composite",
            "direction": 1,
            "glyph": "★",
            "n_firing": 5,
            "tickers": [
                {"ticker": "AAPL", "name": "Apple Inc.", "price": 195.0, "score": 7.2, "band": "high"},
                {"ticker": "MSFT", "name": "Microsoft Corp.", "price": 420.0, "score": 6.8, "band": "high"},
                {"ticker": "NVDA", "name": "NVIDIA Corp.", "price": 130.0, "score": 5.9, "band": "moderate"},
                {"ticker": "META", "name": "Meta Platforms", "price": 560.0, "score": 4.1, "band": "moderate"},
                {"ticker": "AMZN", "name": "Amazon.com", "price": 195.0, "score": 3.8, "band": "low"},
            ],
        },
    },
    "stocks": {
        "AAPL": {
            "name": "Apple Inc.", "price": 195.0, "score": 7.2, "band": "high",
            "active_buy": 2, "active_total": 3,
            "perf_7d": 1.4, "perf_30d": 3.8, "perf_12m": 18.2,
            "signals": [
                {"id": "MACD_CROSS_UP", "display_en": "MACD Cross Up", "direction": 1, "glyph": "▲", "state": 1, "age_days": 2},
                {"id": "RSI_TREND", "display_en": "RSI Trending", "direction": 1, "glyph": "↑", "state": 1, "age_days": 5},
                {"id": "BELOW_50DMA", "display_en": "Below 50-DMA", "direction": -1, "glyph": "▼", "state": 0, "age_days": 0},
            ],
        },
    },
}

_SAMPLE_LAB: dict = {
    "generated_utc": "pending",
    "universe_n": 0,
    "universe_caveat": "survivor mega-caps; descriptive not §5.9 verdict",
    "_sample": True,
    "signals": {
        "MACD_CROSS_UP": {
            "display_en": "MACD Cross Up", "family": "momentum", "direction": 1,
            "n_fires": 142, "n_months": 36,
            "wr_21d": 0.58, "mean_21d": 1.2, "base_wr": 0.52, "base_mean": 0.7,
            "edge_wr": 0.06, "edge_mean": 0.5,
            "mfe_mae_med": 1.8, "durable_rate": 0.61, "median_lag_pct": 3.2,
            "days_since_low_med": 12.0, "up_tape_pct": 0.67,
            "wr_pre2010": 0.54, "wr_post2010": 0.60,
        },
        "RSI_OVERSOLD": {
            "display_en": "RSI Oversold Bounce", "family": "mean_reversion", "direction": 1,
            "n_fires": 89, "n_months": 36,
            "wr_21d": 0.55, "mean_21d": 0.9, "base_wr": 0.52, "base_mean": 0.7,
            "edge_wr": 0.03, "edge_mean": 0.2,
            "mfe_mae_med": 1.5, "durable_rate": 0.54, "median_lag_pct": 5.1,
            "days_since_low_med": 8.0, "up_tape_pct": 0.59,
            "wr_pre2010": None, "wr_post2010": 0.55,
        },
    },
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path, fallback: dict) -> dict:
    """Load JSON with try/except; return fallback (with _sample=True) on error."""
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("Could not load %s (%s) — using sample fixture", path, e)
        return fallback


def _group_signals(signals: dict) -> list[dict]:
    """Return signals grouped by family, sorted alphabetically within each group."""
    by_family: dict[str, list] = {}
    for sig_id, sig in signals.items():
        fam = sig.get("family", "other")
        by_family.setdefault(fam, []).append({"id": sig_id, **sig})
    groups = []
    for fam in sorted(by_family):
        items = sorted(by_family[fam], key=lambda x: x.get("display_en", x["id"]))
        groups.append({"family": fam, "signals": items})
    return groups


def _band_class(band: str | None) -> str:
    """CSS class for a conviction band (matches tech_score Strong Buy/Buy/Hold/Sell labels)."""
    b = (band or "").lower()
    if b == "strong buy":
        return "band-strong"
    if b == "buy":
        return "band-high"
    if b == "hold":
        return "band-low"
    if b in ("sell", "strong sell"):
        return "band-avoid"
    return "band-none"


def _pct_fmt(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:+.{decimals}f}%"


def _wr_fmt(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.0f}%"


def _edge_cls(edge: float | None) -> str:
    if edge is None:
        return ""
    if edge >= 0.04:
        return "r-pos"
    if edge <= -0.04:
        return "r-neg"
    return "mut"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        site = config.ROOT / "site"
        factordata = site / "factordata"

        screener = _load_json(factordata / "tech_screener.json", _SAMPLE_SCREENER)
        lab = _load_json(factordata / "tech_lab.json", _SAMPLE_LAB)

        is_sample = screener.get("_sample") or lab.get("_sample")

        # Merge signal metadata: lab profile keyed on same signal IDs as screener
        screener_signals = screener.get("signals") or {}
        lab_signals = lab.get("signals") or {}
        stocks = screener.get("stocks") or {}

        # Merge: for each signal in screener, attach lab profile if available
        merged_signals: dict[str, dict] = {}
        for sig_id, sig in screener_signals.items():
            merged_signals[sig_id] = {**sig, "lab": lab_signals.get(sig_id)}

        # Also include lab-only signals (no screener tickers)
        for sig_id, sig in lab_signals.items():
            if sig_id not in merged_signals:
                merged_signals[sig_id] = {
                    "display_en": sig.get("display_en", sig_id),
                    "display_zh": sig.get("display_en", sig_id),
                    "family": sig.get("family", "other"),
                    "direction": sig.get("direction", 0),
                    "glyph": "○",
                    "n_firing": 0,
                    "tickers": [],
                    "lab": sig,
                }

        signal_groups = _group_signals(merged_signals)

        # Build a JSON blob to embed in the page for client-side filtering
        # Only include what the JS needs; keep it compact
        embedded_data = {
            "signals": {
                sig_id: {
                    "display_en": s.get("display_en", sig_id),
                    "display_zh": s.get("display_zh", s.get("display_en", sig_id)),
                    "family": s.get("family", "other"),
                    "direction": s.get("direction", 0),
                    "glyph": s.get("glyph", "○"),
                    "n_firing": s.get("n_firing", 0),
                    "tickers": s.get("tickers", []),
                    "lab": s.get("lab"),
                }
                for sig_id, s in merged_signals.items()
            },
            "stocks": stocks,
        }

        built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
        try:
            html = env.get_template("tech_lab.html.j2").render(
                generated_utc=built,
                is_sample=is_sample,
                signal_groups=signal_groups,
                screener=screener,
                lab=lab,
                embedded_data_json=json.dumps(embedded_data).replace("</", "<\\/"),
                universe_caveat=lab.get("universe_caveat", ""),
                universe_n_screener=screener.get("universe_n", 0),
                universe_n_lab=lab.get("universe_n", 0),
                n_signals=len(merged_signals),
                band_class=_band_class,
                wr_fmt=_wr_fmt,
                pct_fmt=_pct_fmt,
                edge_cls=_edge_cls,
                active_section="research",
                active_page="tech_lab",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("tech_lab render failed — skipping (additive): %s", e)
            return 0

        site.mkdir(exist_ok=True)
        write_page(site / "tech_lab.html", html)
        log.info(
            "wrote site/tech_lab.html (%d signals, sample=%s, %d KB)",
            len(merged_signals), is_sample, len(html) // 1024,
        )
        return 0

    except Exception as e:  # noqa: BLE001 — never break the daily build
        log.warning("tech_lab page failed — skipping (additive): %s", e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
