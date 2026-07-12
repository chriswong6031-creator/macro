"""engine/t0_indicator.py — T0 beta turn indicator (display-only).

Produces site/factordata/t0_indicator.json (schema: t0_indicator.v1).

AUTHORITY: tier=display, may_rank/gate/size/escalate = False.

DISPLAY-TIER LAW: no buy/act-now verbs. Disclosure printed, not hidden.
Matches are early, unproven turn flags — not buy signals.

The T0 condition (frozen):
  - 3B-grid StochRSI K < 30 (oversold territory on the 3-bar resampled grid)
  - 1D StochRSI K crossed above D on the LATEST daily bar (d1_kd_xup_bars == 0)

These two grids are produced by the same engine used in pick_lab
(engine.pick_lab.signals_1d.compute_grids and engine.signal_quality.signal_frame).
This module is PURE in build_artifact (no I/O) — all I/O is in write_artifact.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (invariant — display-tier)
# ---------------------------------------------------------------------------

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

# ---------------------------------------------------------------------------
# T0 condition constants (frozen)
# ---------------------------------------------------------------------------

T0_D3K_MAX: float = 30.0  # 3B-grid StochRSI K must be strictly below this


# ---------------------------------------------------------------------------
# Core artifact builder (pure — no I/O)
# ---------------------------------------------------------------------------

def build_artifact(
    d1_grid: pd.DataFrame,
    d3_map: dict[str, dict],
    closes: pd.DataFrame,
    asof: str | None,
    sector_map: dict[str, str | None] | None = None,
    liq_map: dict[str, dict] | None = None,
) -> dict:
    """Build the t0_indicator.v1 artifact dict (pure, no I/O).

    Parameters
    ----------
    d1_grid : pd.DataFrame
        Output of engine.pick_lab.signals_1d.compute_grids — indexed by ticker,
        columns include d1_kd_xup_bars, d1_k, d1_d. May be empty DataFrame.
        d1_kd_xup_bars semantics: 0.0 = K crossed above D on the latest daily
        bar; None/NaN = no cross within 15 bars.
    d3_map : dict[str, dict]
        Per-ticker dict with at least "d3_k" and "d3_d" keys (floats or None).
        Built in build_stock_library from engine.signal_quality.signal_frame on
        the 3B grid.
    closes : pd.DataFrame
        Daily close panel (columns = tickers). Used for universe_n count and
        last close per matched ticker.
    asof : str | None
        Panel data date string (YYYY-MM-DD). Passed through to artifact as-of.
    sector_map : dict[str, str | None] | None
        Ticker -> sector string (or None). Optional.
    liq_map : dict[str, dict] | None
        Ticker -> liquidity chip dict (must contain "adv_dollar_20d_median" key).
        Optional; used for sort order and the dollar_adv_20d field.

    Returns
    -------
    dict
        Frozen t0_indicator.v1 artifact schema.
    """
    sector_map = sector_map or {}
    liq_map = liq_map or {}

    universe_n: int = len(closes.columns) if closes is not None and not closes.empty else 0

    matches: list[dict] = []

    # Compute last non-NaN close per ticker upfront for matched tickers
    def _last_close(ticker: str) -> float | None:
        if closes is None or closes.empty or ticker not in closes.columns:
            return None
        s = closes[ticker].dropna()
        if s.empty:
            return None
        return float(s.iloc[-1])

    # Iterate over tickers that appear in d3_map (the full universe scanned)
    for ticker, d3 in d3_map.items():
        d3_k = d3.get("d3_k")

        # T0 gate 1: 3B-grid StochRSI K strictly below T0_D3K_MAX
        if d3_k is None:
            continue
        try:
            d3_k_f = float(d3_k)
        except (TypeError, ValueError):
            continue
        if d3_k_f >= T0_D3K_MAX:
            continue

        # T0 gate 2: 1D K crossed above D on the latest bar (d1_kd_xup_bars == 0)
        if d1_grid.empty or ticker not in d1_grid.index:
            continue
        row = d1_grid.loc[ticker]
        xup_bars = row.get("d1_kd_xup_bars") if hasattr(row, "get") else row["d1_kd_xup_bars"]
        if xup_bars is None or (hasattr(pd, "isna") and pd.isna(xup_bars)):
            continue
        try:
            xup_bars_f = float(xup_bars)
        except (TypeError, ValueError):
            continue
        if xup_bars_f != 0.0:
            continue

        # Match — collect fields
        d3_d = d3.get("d3_d")
        d1_k_val = row.get("d1_k") if hasattr(row, "get") else row["d1_k"]
        d1_d_val = row.get("d1_d") if hasattr(row, "get") else row["d1_d"]

        def _opt_float(v: Any) -> float | None:
            if v is None:
                return None
            try:
                f = float(v)
                return None if pd.isna(f) else f
            except (TypeError, ValueError):
                return None

        liq = liq_map.get(ticker) or {}
        adv = liq.get("adv_dollar_20d_median")
        adv_f = _opt_float(adv)

        matches.append({
            "ticker": ticker,
            "d3_k": round(d3_k_f, 4),
            "d3_d": _opt_float(d3_d),
            "d1_k": _opt_float(d1_k_val),
            "d1_d": _opt_float(d1_d_val),
            "close": _last_close(ticker),
            "sector": sector_map.get(ticker) or None,
            "dollar_adv_20d": adv_f,
        })

    # Sort: dollar_adv_20d descending, None last
    matches.sort(
        key=lambda m: (m["dollar_adv_20d"] is None, -(m["dollar_adv_20d"] or 0.0))
    )

    return {
        "schema": "t0_indicator.v1",
        "as_of": asof,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "params": {
            "d3_k_max": T0_D3K_MAX,
            "cross_age_bars": 0,
            "stoch": "RSI14/Stoch14/K3/D3",
            "d3_grid": "3B",
            "d1_grid": "1B",
        },
        "universe_n": universe_n,
        "matches": matches,
        "authority": dict(AUTHORITY),
        "disclosure_en": "Beta screen — an early, unproven turn flag; not a buy signal.",
        "disclosure_zh": "测试版筛选 — 早期且未经验证的拐点提示，并非买入信号。",
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def write_artifact(artifact: dict, site_dir: Path) -> Path:
    """Write site_dir/factordata/t0_indicator.json atomically.

    Uses tempfile + os.replace for crash-safe atomic write. Creates parent
    directories as needed.

    Parameters
    ----------
    artifact : dict
        Output of build_artifact.
    site_dir : Path
        Root site directory (e.g. config.ROOT / "site").

    Returns
    -------
    Path
        Path of the written file.
    """
    out_dir = Path(site_dir) / "factordata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "t0_indicator.json"

    payload = json.dumps(artifact, separators=(",", ":"), default=str)
    fd, tmp_path = tempfile.mkstemp(dir=out_dir, prefix=".t0_indicator_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.write("\n")
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    log.info("t0_indicator: wrote %s (%d matches)", out_path, len(artifact.get("matches", [])))
    return out_path
