"""Hong Kong calibration — the Phase-2 checkpoint deliverable.

Measures, honestly and split-half:
  1. Regime quad -> forward returns of the market index (Hang Seng Index, deep
     history; HSI macro read exists ~2006->). Per house rule, a signal is
     reported with its measured record; no edge -> shipped as "context".
  2. Liquidity overlay (dual: PBoC stance + Fed-via-peg + southbound) -> forward
     returns.
  3. Global risk overlay (engine.hk_global risk-on/off) -> forward returns. This
     is the KEY HK test: HK is the regional risk-on/off proxy, so the question is
     whether the global risk state differentiates HSI forward returns.
  4. The cycle ladder (engine.cycles.calibrate_ladder) on the DEEP HK panel
     (curated constituents + indices + ETF proxies), endpoint return + forward
     drawdown per state.

Writes reports/hk-calibration.md. Run offline / weekly, like scripts/recalibrate.py.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from collectors.hk_breadth import HkBreadthAdapter
from engine.hk_inputs import build_features
from engine.hk_regime import classify
from engine.cycles import calibrate_ladder
from lib import config, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("calibrate_hk")


def _fwd_returns(px: pd.Series, fwd: int) -> pd.Series:
    return px.pct_change(fwd).shift(-fwd)


def _group_table(df: pd.DataFrame, by: str, fwd_cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(by):
        rec = {by: key, "n": len(g)}
        for fc in fwd_cols:
            v = g[fc].dropna()
            if len(v):
                rec[f"{fc}_mean%"] = round(100 * v.mean(), 2)
                rec[f"{fc}_hit%"] = round(100 * (v > 0).mean(), 1)
        rows.append(rec)
    return pd.DataFrame(rows).set_index(by)


def regime_records(regime: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    hcfg = config.load()["hk"]["engine"]["calibration"]
    fwds = hcfg["forward_days"]
    split = pd.Timestamp(hcfg["split_date"])

    mkt = store.read("hk", config.load()["hk"]["yahoo"]["market_index"])
    px = mkt["close"].reindex(regime.index).ffill(limit=3)

    df = regime[["quad_name", "liquidity", "risk_state", "regime_confidence"]].copy()
    for fwd in fwds:
        df[f"f{fwd}"] = _fwd_returns(px, fwd)
    df = df[df["regime_confidence"] > 0]                      # only confident days count
    fwd_cols = [f"f{fwd}" for fwd in fwds]

    tables = {}
    for label, sub in [("full", df), ("pre_" + split.strftime("%Y"), df[df.index < split]),
                       ("post_" + split.strftime("%Y"), df[df.index >= split])]:
        tables[f"quad_{label}"] = _group_table(sub.dropna(subset=["quad_name"]), "quad_name", fwd_cols)
    tables["liquidity_full"] = _group_table(df.dropna(subset=["liquidity"]), "liquidity", fwd_cols)
    tables["risk_state_full"] = _group_table(df.dropna(subset=["risk_state"]), "risk_state", fwd_cols)
    return df, tables


def deep_panel() -> dict[str, pd.Series]:
    """Deep close panel for ladder calibration: curated constituents (fresh max
    download) + indices + ETF proxies already in the store."""
    panel: dict[str, pd.Series] = {}
    hy = config.load()["hk"]["yahoo"]
    for t in list(hy["indices"]) + list(hy.get("etf_proxies", {})):
        df = store.read("hk", t)
        if df is not None and "close" in df.columns:
            panel[t] = df["close"]
    adapter = HkBreadthAdapter()
    tickers = adapter.constituents()["symbol"].tolist()
    try:
        wide = adapter._download_closes(tickers, "max")
        for c in wide.columns:
            s = wide[c].dropna()
            if len(s) >= 600:
                panel[c] = s
    except Exception as e:  # noqa: BLE001
        log.warning("deep constituent download failed (%s); calibrating on indices+proxies only", e)
    return panel


def _fmt(df: pd.DataFrame) -> str:
    return df.to_markdown() if not df.empty else "_(no rows)_"


def main() -> int:
    log.info("building Hong Kong features + regime ...")
    regime = classify(build_features())
    df, tables = regime_records(regime)
    span = f"{df.index.min().date()} -> {df.index.max().date()}"

    log.info("calibrating cycle ladder on the deep panel ...")
    hcfg = config.load()["hk"]["engine"]["calibration"]
    panel = deep_panel()
    ladder = calibrate_ladder(panel, fwd=hcfg.get("ladder_fwd", 21), step=hcfg.get("ladder_step", 10))
    # persist the ladder record as JSON for the stock-search "measured record" table
    import json as _json
    hdir = config.data_dir() / "hk_regime"
    hdir.mkdir(parents=True, exist_ok=True)
    (hdir / "ladder_calibration.json").write_text(_json.dumps(ladder, indent=2))
    lad_df = pd.DataFrame(ladder).T
    if not lad_df.empty:
        lad_df = lad_df.reindex(columns=["n", "hit_pct", "avg_fwd_pct", "dd_med_pct",
                                         "dd_p10_pct", "dd_bad_pct"])

    out = ["# Hong Kong / Hang Seng Dashboard — Calibration",
           "",
           "Honest, split-half measurement before any UI is built — the same gate used for the",
           "US, China and Bitcoin Vector dashboards. House rule: a signal is shipped with its **measured**",
           "forward-return record; no measured edge -> it ships as *context, not a signal*.",
           "",
           f"- Confident-regime sample: **{span}** ({len(df)} days, confidence>0).",
           f"- Ladder panel: **{len(panel)} instruments** (curated constituents + indices + ETF proxies).",
           "- Caveats: the HK macro read piggybacks on China fundamentals (PMI/CPI/PPI/M2), monthly",
           "  back to ~2006-08 (shorter + more regime-unstable than the US); HSI itself is the regional",
           "  risk-on/off proxy, so the THREE-LEG engine here is quad (growth×inflation) + dual liquidity",
           "  (PBoC + Fed-via-peg) + the global risk overlay — the third leg is the one to scrutinise.",
           "",
           "## 1. Regime quad -> forward return of the market index (Hang Seng Index)",
           "", "**Full sample**", "", _fmt(tables["quad_full"]),
           "", "**Split-half robustness** (a quad's edge is only trustworthy if it survives both halves)",
           "", "_Pre-split_", "", _fmt(tables[[k for k in tables if k.startswith("quad_pre")][0]]),
           "", "_Post-split_", "", _fmt(tables[[k for k in tables if k.startswith("quad_post")][0]]),
           "", "## 2. Liquidity overlay (dual: PBoC stance + Fed-via-peg + southbound flow) -> forward return",
           "", _fmt(tables["liquidity_full"]),
           "", "## 3. Global risk overlay (risk-on/off) -> forward return",
           "", "_The KEY HK test: HK is the regional risk-on/off proxy, so does the global risk state",
           "differentiate HSI forward returns?_",
           "", _fmt(tables["risk_state_full"]),
           "", "## 4. Cycle ladder (deep HK panel) — endpoint return + forward drawdown",
           "", _fmt(lad_df),
           "", "## Reading this",
           "- Quad rows whose sign/ranking flips between the two halves are **regime-unstable** ->",
           "  frame as risk context, never a standalone allocation rule.",
           "- The ladder's value is the DRAWDOWN columns (dd_*): scary states with shallow typical",
           "  dips are the asymmetric setups; the avg_fwd alone is U-shaped/misleading (macro D43).",
           ""]
    rp = config.load()["storage"]["reports_dir"]
    path = Path(config.ROOT) / rp / "hk-calibration.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out))
    log.info("wrote %s", path)
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    raise SystemExit(main())
