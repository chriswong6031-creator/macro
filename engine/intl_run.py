"""International dashboard engine entrypoint: per-country features -> uniform
regime classification -> cross-country comparison -> data/intl/latest.json (+
per-country regime history parquets for the charts). Recomputes full history each
run so live == backtest. Every read is descriptive / display-only.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from engine import intl_compare, intl_equity_risk, intl_inputs
from engine.intl_regime import classify, recession_band
from lib import config

log = logging.getLogger(__name__)


def _macro_present(snap: dict) -> int:
    return sum(1 for k in ("yield_10y", "cpi_yoy", "gdp_yoy", "unemployment")
              if snap.get(k) is not None)


def country_record(cc: str, closes: pd.DataFrame, macro: pd.DataFrame,
                   equity: dict) -> tuple[dict | None, pd.DataFrame | None]:
    c = intl_inputs.countries()[cc]
    f = intl_inputs.country_frame(cc, closes, macro)
    if f.empty:
        return None, None
    reg = classify(f)
    asof = reg["quad"].last_valid_index()
    if asof is None:
        return None, None
    row = reg.loc[asof]
    snap = intl_inputs.latest_macro_snapshot(cc, f)
    g_n = int(row.get("growth_n_components", 0) or 0)
    i_n = int(row.get("inflation_n_components", 0) or 0)
    rec_score = float(row["recession_score"]) if pd.notna(row.get("recession_score")) else None

    record = {
        "cc": cc, "name": c["name"], "name_zh": c.get("name_zh", c["name"]),
        "flag": c["flag"], "region": c.get("region"),
        "date": str(asof.date()),
        "quad": row["quad"], "quad_name": row["quad_name"],
        "growth_score": round(float(row["growth_score"]), 3),
        "inflation_score": round(float(row["inflation_score"]), 3),
        "confidence": round(float(row["regime_confidence"]), 3),
        "liquidity": row["liquidity"],
        "recession_score": round(rec_score, 0) if rec_score is not None else None,
        "recession_band": recession_band(rec_score),
        "macro": snap,
        "macro_asof": intl_inputs.macro_freshness(cc, macro),
        "equity": equity.get(cc, {}),
        "data_limited": bool(g_n < 2 or i_n < 2 or _macro_present(snap) < 2),
    }
    hist = reg[[col for col in reg.columns if not str(col).startswith("c_")]]
    return record, hist


def run() -> dict:
    closes = intl_inputs._intl_closes()
    macro = intl_inputs._macro_frame()
    equity = intl_equity_risk.equity_risk_all()
    if closes.empty:
        raise RuntimeError("no intl price data in store — run collectors first")

    p = config.data_dir() / "intl_regime"
    p.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    for cc in intl_inputs.countries():
        try:
            rec, hist = country_record(cc, closes, macro, equity)
        except Exception as e:  # noqa: BLE001 — one country can't kill the board
            log.warning("intl: %s record failed: %s", cc, e)
            continue
        if rec is None:
            continue
        records.append(rec)
        if hist is not None:
            hist.to_parquet(p / f"{cc}_history.parquet")

    if not records:
        raise RuntimeError("intl engine produced no country records")

    latest = {
        "date": max(r["date"] for r in records),
        "summary": intl_compare.global_summary(records),
        "records": records,
        "rankings": intl_compare.rankings(records),
        "heatmap": intl_compare.regime_heatmap(records),
        "periphery": intl_compare.periphery_panel(),
    }
    out = config.data_dir() / "intl"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "latest.json", "w") as fh:
        json.dump(latest, fh, indent=2, default=str)

    s = latest["summary"]
    log.info("intl regime: %d economies, dominant=%s, recession-watch=%d, dd-watch=%d",
             s["n"], s["dominant_quad"], s["recession_watch"], s["drawdown_watch"])
    return latest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    print(json.dumps(run(), indent=2, default=str)[:3000])
