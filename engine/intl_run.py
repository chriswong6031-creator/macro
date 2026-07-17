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

_RADAR_KEYS = {"JP": "jp", "KR": "kr", "TW": "tw", "IN": "in", "AU": "au", "GB": "gb", "EZ": "ez"}


def _ledger_lane_armed() -> bool:
    """True only on the nightly collect lane (COLLECT_LANE=nightly, legacy alias
    US_LANE). House law: nightly is the SOLE advancer of data/ forward ledgers —
    sentinel intraday (CBF_INTRADAY=1) and the engine-render/render re-render lanes
    run build_intl too; on those lanes the radar snapshot still renders but the
    forward log / tuner must not advance (a mid-session append is PIT-inconsistent
    and, being idempotent-by-asof, would permanently displace the nightly row).
    Canonical implementation lives with the ledger writer it guards
    (engine.risk_radar_intl_audit.ledger_lane_armed); CN/HK/CA builds share it."""
    from engine.risk_radar_intl_audit import ledger_lane_armed
    return ledger_lane_armed()


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
        # Leading-risk radar (engine/risk_radar_intl.py): calibrated forward-drawdown
        # radar per market — US rate shocks + FX depreciation + extension percentile
        # (melt-up/KOSPI class). Display-only until this market's own forward log
        # matures (can_force); append is idempotent by as-of (nightly is the sole
        # advancer; re-render lanes dedupe). Never fatal.
        try:
            from engine import risk_radar_intl as _rri
            _prof = _rri.PROFILES.get(_RADAR_KEYS.get(cc, ""))
            if _prof is not None:
                rec["risk_radar"] = _rri.snapshot(_prof)
                try:
                    from engine import risk_radar_intl_audit as _rra
                    if _ledger_lane_armed():
                        from engine import risk_radar_intl_tune as _rrt
                        rec["risk_radar"]["forward_log"] = _rra.snapshot_and_grade(rec["risk_radar"], _prof)
                        rec["risk_radar"]["can_force"] = bool(rec["risk_radar"]["forward_log"].get("can_force"))
                        _rrt.tune(_prof)
                    else:
                        # Read-only fast-path: snapshot still renders; ledger/tuner do not advance.
                        sc = _rra.scorecard(_prof.key, log_governance=False)
                        rec["risk_radar"]["forward_log"] = sc
                        rec["risk_radar"]["can_force"] = bool(sc.get("can_force"))
                except Exception as _e:  # noqa: BLE001
                    log.warning("intl %s risk-radar audit/tune failed (%s); snapshot only", cc, _e)
        except Exception as _e:  # noqa: BLE001
            log.warning("intl %s risk-radar failed (%s); skipping", cc, _e)

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
