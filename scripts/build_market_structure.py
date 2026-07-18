"""scripts/build_market_structure.py — MSP W1 nightly market-structure data spine.

Produces:
  data/market_structure/latest.json   — market_structure_context.v1 artifact
  data/market_structure/history.parquet — full backcast frame (deterministic recompute)
  data/market_structure/ledger.parquet  — forward ledger (LANE-GATED: COLLECT_LANE=nightly)

Inputs (each block is fail-open — absent input → honest nulls, never crash):
  SPX closes     : data/yahoo/_GSPC.parquet (yahoo store group)
  Dealer gamma   : data/cboe/gex_SPX.parquet
  Correlation    : data/cboe/cor1m.parquet, cor3m.parquet, dspx.parquet
  VIX futures    : data/cboe/vix_curve.parquet

Runtime target: trivially fast (<10s on any modern machine).

MSP laws enforced:
  MSP-R3  no fused positioning numeric composite
  MSP-R8  deterministic price arithmetic only, no LLM
  MSP-R9  full-history backcast written on every run
  MSP-R10 ledger gated on COLLECT_LANE=nightly
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger("build_market_structure")

_TRADING_YEAR = 252
_VC_DEADBAND_BN   = 1.0    # |5d VC flow bn| < 1.0 → pausing
_CTA_DEADBAND     = 0.02   # |5d CTA score change| < 0.02 → pausing
_COR1M_PCTILE_LO  = 20     # ≤20th pctile → dispersion
_COR1M_PCTILE_HI  = 80     # ≥80th pctile → elevated
_HISTORY_ROWS     = 500    # max rows in history sections


# ---------------------------------------------------------------------------
# Lane gate (MSP-R10)
# ---------------------------------------------------------------------------

def _ledger_lane_armed() -> bool:
    """True only on a ledger-advancing collect lane (COLLECT_LANE=nightly).

    House law: nightly is the SOLE advancer of data/ forward ledgers.
    Off-lane runs write latest.json + history.parquet but MUST NOT write
    the ledger (keep-first-wins semantics; off-lane append would displace
    the nightly row permanently).
    """
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------

def _read_parquet(path: Path, date_col: str | None = None) -> pd.DataFrame | None:
    """Read a parquet safely; return None on any error."""
    try:
        if not path.exists():
            log.warning("market_structure: %s not found", path)
            return None
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception as exc:  # noqa: BLE001
        log.warning("market_structure: failed to read %s: %s", path, exc)
        return None


def _spx_closes(data_dir: Path) -> pd.Series | None:
    df = _read_parquet(data_dir / "yahoo" / "_GSPC.parquet")
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else df.columns[0]
    s = df[col].astype(float).dropna()
    return s if not s.empty else None


# ---------------------------------------------------------------------------
# Gamma block
# ---------------------------------------------------------------------------

def _build_gamma_block(data_dir: Path) -> dict:
    """Read gex_SPX.parquet → gamma context block.  Fail-open → nulls."""
    null = {
        "regime": None, "net_gex_bn": None, "net_gex_pctile": None,
        "gamma_flip": None, "spot": None, "dist_to_flip_pct": None,
        "days_in_regime": None, "series_start": None, "history": [],
    }
    try:
        df = _read_parquet(data_dir / "cboe" / "gex_SPX.parquet")
        if df is None or df.empty:
            return null
        if "net_gex_bn" not in df.columns:
            log.warning("market_structure: gex_SPX missing net_gex_bn column")
            return null

        latest = df.iloc[-1]
        regime = str(latest.get("gamma_regime") or "null")
        if regime == "nan":
            regime = None

        # Net GEX percentile vs full stored history
        gex_series = df["net_gex_bn"].dropna()
        pctile: float | None = None
        if len(gex_series) >= 2:
            latest_gex = float(gex_series.iloc[-1])
            pctile = float((gex_series < latest_gex).sum() / len(gex_series) * 100)

        # Days in current regime
        days_in_regime: int | None = None
        if regime and "gamma_regime" in df.columns:
            regime_ser = df["gamma_regime"].fillna("null")
            # Count consecutive tail rows with same regime
            rev = regime_ser.iloc[::-1]
            count = 0
            for v in rev:
                if v == regime:
                    count += 1
                else:
                    break
            days_in_regime = count

        series_start = str(df.index.min().date())

        # History (last ≤500 rows)
        hist_df = df[["net_gex_bn", "gamma_regime", "gamma_flip", "spot"]].copy()
        hist_df = hist_df.tail(_HISTORY_ROWS)
        history = []
        for dt, row in hist_df.iterrows():
            history.append({
                "date": str(dt.date()),
                "net_gex_bn": _safe_float(row.get("net_gex_bn")),
                "regime": str(row.get("gamma_regime") or "null") if pd.notna(row.get("gamma_regime")) else None,
                "flip": _safe_float(row.get("gamma_flip")),
                "spot": _safe_float(row.get("spot")),
            })

        return {
            "regime": regime,
            "net_gex_bn": _safe_float(latest.get("net_gex_bn")),
            "net_gex_pctile": round(pctile, 1) if pctile is not None else None,
            "gamma_flip": _safe_float(latest.get("gamma_flip")),
            "spot": _safe_float(latest.get("spot")),
            "dist_to_flip_pct": _safe_float(latest.get("dist_to_flip_pct")),
            "days_in_regime": days_in_regime,
            "series_start": series_start,
            "history": history,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("market_structure: gamma block failed: %s", exc)
        return null


# ---------------------------------------------------------------------------
# Systematic block (VC + CTA)
# ---------------------------------------------------------------------------

def _build_systematic_block(
    closes: pd.Series | None,
) -> tuple[dict, pd.DataFrame | None]:
    """Build VC + CTA block + history frame.  Fail-open → nulls."""
    null_sys = {
        "vc": {
            "alloc_bn": None, "alloc_frac": None, "flow_1d_bn": None,
            "flow_5d_bn": None, "state": None,
            "aum_bn": 300.0, "target_vol_pct": 10.0, "series_start": None,
        },
        "cta": {
            "score": None, "z": None, "flow_1d": None, "flow_5d": None, "state": None,
        },
        "agreement": None,
        "history": [],
    }
    if closes is None or closes.empty:
        return null_sys, None

    try:
        from engine.systematic_flows import (  # noqa: PLC0415
            vc_exposure, cta_positioning, rv_cross_state as rv_xs,
            flow_state, agreement,
        )

        vc_df  = vc_exposure(closes)
        cta_df = cta_positioning(closes)

        # 5-day rolling sums for state classification
        vc_flow_5d  = vc_df["flow_bn"].rolling(5, min_periods=1).sum()
        cta_flow_5d = cta_df["cta_flow"].rolling(5, min_periods=1).sum()

        # Latest values
        latest_vc  = vc_df.iloc[-1]
        latest_cta = cta_df.iloc[-1]
        latest_vc_flow_5d  = _safe_float(vc_flow_5d.iloc[-1])
        latest_cta_flow_5d = _safe_float(cta_flow_5d.iloc[-1])

        vc_s   = flow_state(latest_vc_flow_5d, _VC_DEADBAND_BN, mode="vc")
        cta_s  = flow_state(latest_cta_flow_5d, _CTA_DEADBAND,  mode="cta")
        agr    = agreement(vc_s, cta_s)
        series_start = str(closes.index.min().date())

        # History frame (last ≤500 rows)
        hist = pd.DataFrame({
            "vc_alloc_bn":  vc_df["alloc_bn"],
            "vc_flow_bn":   vc_df["flow_bn"],
            "cta_score":    cta_df["cta_score"],
            "cta_flow":     cta_df["cta_flow"],
            "spx_close":    closes,
        }).dropna(how="all")

        hist_rows = []
        for dt, row in hist.tail(_HISTORY_ROWS).iterrows():
            hist_rows.append({
                "date":        str(dt.date()),
                "vc_alloc_bn": _safe_float(row["vc_alloc_bn"]),
                "vc_flow_bn":  _safe_float(row["vc_flow_bn"]),
                "cta_score":   _safe_float(row["cta_score"]),
                "cta_flow":    _safe_float(row["cta_flow"]),
                "spx_close":   _safe_float(row["spx_close"]),
            })

        sys_block = {
            "vc": {
                "alloc_bn":     _safe_float(latest_vc["alloc_bn"]),
                "alloc_frac":   _safe_float(latest_vc["alloc_frac"]),
                "flow_1d_bn":   _safe_float(latest_vc["flow_bn"]),
                "flow_5d_bn":   latest_vc_flow_5d,
                "state":        vc_s,
                "aum_bn":       300.0,
                "target_vol_pct": 10.0,
                "series_start": series_start,
            },
            "cta": {
                "score":    _safe_float(latest_cta["cta_score"]),
                "z":        _safe_float(latest_cta["cta_z"]),
                "flow_1d":  _safe_float(latest_cta["cta_flow"]),
                "flow_5d":  latest_cta_flow_5d,
                "state":    cta_s,
            },
            "agreement": agr,
            "history":   hist_rows,
        }

        return sys_block, hist

    except Exception as exc:  # noqa: BLE001
        log.warning("market_structure: systematic block failed: %s", exc)
        return null_sys, None


# ---------------------------------------------------------------------------
# Vol block
# ---------------------------------------------------------------------------

def _build_vol_block(closes: pd.Series | None, data_dir: Path) -> dict:
    """RV cross-state + VIX futures curve.  Fail-open → nulls."""
    null = {
        "rv21": None, "rv63": None, "rv_cross_state": None,
        "vix_curve": None, "vix_curve_slope": None, "series_start_curve": None,
    }
    if closes is None:
        return null

    try:
        from engine.systematic_flows import rv_cross_state  # noqa: PLC0415

        rets = closes.pct_change(fill_method=None)
        rv21_ser = rets.rolling(21, min_periods=11).std(ddof=0) * np.sqrt(_TRADING_YEAR)
        rv63_ser = rets.rolling(63, min_periods=32).std(ddof=0) * np.sqrt(_TRADING_YEAR)

        rv21_v = _safe_float(rv21_ser.iloc[-1]) if not rv21_ser.empty else None
        rv63_v = _safe_float(rv63_ser.iloc[-1]) if not rv63_ser.empty else None
        rvcs   = rv_cross_state(rv21_v, rv63_v)

        # VIX futures curve
        curve_block: list | None = None
        curve_slope: float | None = None
        curve_series_start: str | None = None

        try:
            vix_df = _read_parquet(data_dir / "cboe" / "vix_curve.parquet")
            if vix_df is not None and not vix_df.empty:
                latest_row = vix_df.iloc[-1]
                tenors = [("M1",1), ("M2",2), ("M3",3), ("M4",4), ("M5",5), ("M6",6)]
                curve_block = []
                for tenor_name, i in tenors:
                    settle_col = f"m{i}_settle"
                    dte_col    = f"m{i}_dte"
                    if settle_col in vix_df.columns:
                        curve_block.append({
                            "tenor":  tenor_name,
                            "settle": _safe_float(latest_row.get(settle_col)),
                            "dte":    int(latest_row.get(dte_col, 0)) if pd.notna(latest_row.get(dte_col)) else None,
                        })
                if len(curve_block) >= 2:
                    m1 = curve_block[0]["settle"]
                    m6 = next((c["settle"] for c in curve_block if c["tenor"] == "M6"), None)
                    if m1 is not None and m6 is not None:
                        curve_slope = round(m6 - m1, 4)
                curve_series_start = str(vix_df.index.min().date())
        except Exception as exc:  # noqa: BLE001
            log.warning("market_structure: vix_curve read failed: %s", exc)

        return {
            "rv21":               rv21_v,
            "rv63":               rv63_v,
            "rv_cross_state":     rvcs,
            "vix_curve":          curve_block,
            "vix_curve_slope":    curve_slope,
            "series_start_curve": curve_series_start,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("market_structure: vol block failed: %s", exc)
        return null


# ---------------------------------------------------------------------------
# Dispersion block
# ---------------------------------------------------------------------------

def _build_dispersion_block(data_dir: Path) -> dict:
    """COR1M/COR3M/DSPX block.  Fail-open → nulls."""
    null = {
        "cor1m": None, "cor1m_regime": None, "cor1m_1y_delta": None,
        "cor1m_pctile_2y": None, "cor3m": None, "dspx": None, "history": [],
    }
    try:
        cor1m_df = _read_parquet(data_dir / "cboe" / "cor1m.parquet")
        if cor1m_df is None or cor1m_df.empty:
            return null

        # Use 'close' column
        cor1m_col = "close" if "close" in cor1m_df.columns else cor1m_df.columns[-1]
        cor1m_s = cor1m_df[cor1m_col].astype(float).dropna()

        latest_cor1m = _safe_float(cor1m_s.iloc[-1]) if not cor1m_s.empty else None

        # 2-year trailing percentile for regime classification (percentile-based — MSP-R5)
        pctile_2y: float | None = None
        cor1m_regime: str | None = None
        if len(cor1m_s) >= 20:
            window_2y = cor1m_s.tail(504)  # ~2 trading years
            current_val = cor1m_s.iloc[-1]
            pctile_2y = float((window_2y <= current_val).sum() / len(window_2y) * 100)
            if pctile_2y >= _COR1M_PCTILE_HI:
                cor1m_regime = "elevated"
            elif pctile_2y <= _COR1M_PCTILE_LO:
                cor1m_regime = "dispersion"
            else:
                cor1m_regime = "normal"

        # 1-year delta
        cor1m_1y_delta: float | None = None
        if len(cor1m_s) >= _TRADING_YEAR:
            prior = _safe_float(cor1m_s.iloc[-_TRADING_YEAR])
            if prior is not None and latest_cor1m is not None:
                cor1m_1y_delta = round(latest_cor1m - prior, 4)

        # COR3M
        cor3m_v: float | None = None
        try:
            cor3m_df = _read_parquet(data_dir / "cboe" / "cor3m.parquet")
            if cor3m_df is not None and not cor3m_df.empty:
                col3 = "close" if "close" in cor3m_df.columns else cor3m_df.columns[-1]
                cor3m_v = _safe_float(cor3m_df[col3].astype(float).dropna().iloc[-1])
        except Exception:  # noqa: BLE001
            pass

        # DSPX
        dspx_v: float | None = None
        try:
            dspx_df = _read_parquet(data_dir / "cboe" / "dspx.parquet")
            if dspx_df is not None and not dspx_df.empty:
                col_d = "close" if "close" in dspx_df.columns else dspx_df.columns[-1]
                dspx_v = _safe_float(dspx_df[col_d].astype(float).dropna().iloc[-1])
        except Exception:  # noqa: BLE001
            pass

        # History (last ≤500 rows of COR1M)
        hist_rows = []
        for dt, val in cor1m_s.tail(_HISTORY_ROWS).items():
            hist_rows.append({
                "date":   str(dt.date()),
                "cor1m":  _safe_float(val),
            })

        return {
            "cor1m":            latest_cor1m,
            "cor1m_regime":     cor1m_regime,
            "cor1m_1y_delta":   cor1m_1y_delta,
            "cor1m_pctile_2y":  round(pctile_2y, 1) if pctile_2y is not None else None,
            "cor3m":            cor3m_v,
            "dspx":             dspx_v,
            "history":          hist_rows,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("market_structure: dispersion block failed: %s", exc)
        return null


# ---------------------------------------------------------------------------
# Ledger writers (MSP-R10 lane-gated)
# ---------------------------------------------------------------------------

def _ledger_path(data_dir: Path) -> Path:
    p = data_dir / "market_structure" / "ledger.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _append_ledger(
    rows: list[dict],
    data_dir: Path,
) -> None:
    """Append rows to ledger.parquet.  Deduped on (date, type). LANE-GATED."""
    if not _ledger_lane_armed():
        log.debug("market_structure: ledger write skipped (COLLECT_LANE != nightly)")
        return
    if not rows:
        return
    path = _ledger_path(data_dir)
    try:
        new_df = pd.DataFrame(rows)
        new_df["date"] = pd.to_datetime(new_df["date"])
        if path.exists():
            old_df = pd.read_parquet(path)
            old_df["date"] = pd.to_datetime(old_df["date"])
            combined = pd.concat([old_df, new_df], ignore_index=True)
            # Dedup: keep first occurrence of (date, type)
            combined = combined.drop_duplicates(subset=["date", "type"], keep="first")
        else:
            combined = new_df
        combined = combined.sort_values("date").reset_index(drop=True)
        combined.to_parquet(path, index=False)
        log.info("market_structure: ledger updated (%d rows)", len(combined))
    except Exception as exc:  # noqa: BLE001
        log.warning("market_structure: ledger write failed: %s", exc)


def _build_ledger_rows(
    artifact: dict,
    closes: pd.Series | None,
    prev_artifact: dict | None,
) -> list[dict]:
    """Compute ledger rows for this nightly run.

    Row types (MSP-W1 plan, §5 ledgers L-1..L-3):
    - gamma_regime_flip : when regime != previous stored regime
    - systematic_state  : daily snapshot (vc_state, cta_state, agreement)
    - em_breach         : when |1d SPX return| > prior-day IV30/sqrt(252)
    """
    rows: list[dict] = []
    asof = artifact.get("asof") or str(datetime.now(timezone.utc).date())

    # L-1: gamma_regime_flip
    try:
        gamma = artifact.get("gamma") or {}
        curr_regime = gamma.get("regime")
        prev_regime = None
        if prev_artifact:
            prev_regime = (prev_artifact.get("gamma") or {}).get("regime")
        if curr_regime and prev_regime and curr_regime != prev_regime:
            rows.append({
                "date":   asof,
                "type":   "gamma_regime_flip",
                "from_regime": prev_regime,
                "to_regime":   curr_regime,
                "net_gex_bn":  gamma.get("net_gex_bn"),
                "spot":        gamma.get("spot"),
            })
    except Exception as exc:  # noqa: BLE001
        log.debug("market_structure: ledger gamma_regime_flip failed: %s", exc)

    # L-2: systematic_state (daily)
    try:
        sys_block = artifact.get("systematic") or {}
        vc   = sys_block.get("vc") or {}
        cta  = sys_block.get("cta") or {}
        rows.append({
            "date":     asof,
            "type":     "systematic_state",
            "vc_state": vc.get("state"),
            "cta_state": cta.get("state"),
            "agreement": sys_block.get("agreement"),
            "vc_alloc_bn": vc.get("alloc_bn"),
            "cta_score":   cta.get("score"),
            "cta_z":       cta.get("z"),
        })
    except Exception as exc:  # noqa: BLE001
        log.debug("market_structure: ledger systematic_state failed: %s", exc)

    # L-3: em_breach
    try:
        if closes is not None and len(closes) >= 2:
            gex_df = _read_parquet(
                config.data_dir() / "cboe" / "gex_SPX.parquet"
            )
            if gex_df is not None and "iv30" in gex_df.columns and not gex_df.empty:
                # Prior-day IV30 (no lookahead: use t-1 iv30)
                prior_iv30 = float(gex_df["iv30"].iloc[-2]) if len(gex_df) >= 2 else None
                if prior_iv30 and prior_iv30 > 0:
                    # daily band = iv30 / sqrt(252)
                    band = prior_iv30 / np.sqrt(_TRADING_YEAR)
                    ret_1d = float(closes.pct_change(fill_method=None).iloc[-1])
                    if abs(ret_1d) > band:
                        rows.append({
                            "date":      asof,
                            "type":      "em_breach",
                            "ret_1d":    round(ret_1d, 6),
                            "band":      round(band, 6),
                            "direction": "up" if ret_1d > 0 else "down",
                            "iv30":      round(prior_iv30, 4),
                        })
    except Exception as exc:  # noqa: BLE001
        log.debug("market_structure: ledger em_breach failed: %s", exc)

    return rows


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 6)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    data_dir = config.data_dir()
    out_dir  = data_dir / "market_structure"
    out_dir.mkdir(parents=True, exist_ok=True)

    built_at = datetime.now(timezone.utc).isoformat()

    # --- Load SPX closes ---
    closes = _spx_closes(data_dir)
    asof: str = ""
    if closes is not None and not closes.empty:
        asof = str(closes.index[-1].date())
    else:
        log.warning("market_structure: SPX closes unavailable — systematic + vol blocks will be null")

    # --- Load previous artifact for change-feed ---
    prev_artifact: dict | None = None
    latest_path = out_dir / "latest.json"
    if latest_path.exists():
        try:
            prev_artifact = json.loads(latest_path.read_text())
        except Exception:  # noqa: BLE001
            prev_artifact = None

    # --- Build blocks (fail-open) ---
    gamma_block     = _build_gamma_block(data_dir)
    sys_block, hist_frame = _build_systematic_block(closes)
    vol_block       = _build_vol_block(closes, data_dir)
    disp_block      = _build_dispersion_block(data_dir)

    # --- Change feed ---
    from engine.market_structure_context import build_changes  # noqa: PLC0415
    artifact_draft: dict = {
        "schema":         "market_structure_context.v1",
        "asof":           asof or str(datetime.now(timezone.utc).date()),
        "built_at":       built_at,
        "is_context_only": True,
        "display_only":   True,
        "gamma":          gamma_block,
        "systematic":     sys_block,
        "vol":            vol_block,
        "dispersion":     disp_block,
    }
    changes, prev_state = build_changes(prev_artifact, artifact_draft, artifact_draft["asof"])

    artifact = dict(artifact_draft)
    artifact["state_changes"] = changes
    artifact["prev_state"]    = prev_state

    # --- Write latest.json ---
    latest_path.write_text(json.dumps(artifact, indent=2, default=str, ensure_ascii=False))
    log.info(
        "market_structure: wrote latest.json (asof=%s, regime=%s, agreement=%s, "
        "rv_state=%s, cor1m=%s)",
        asof,
        gamma_block.get("regime"),
        sys_block.get("agreement"),
        vol_block.get("rv_cross_state"),
        disp_block.get("cor1m"),
    )

    # --- Write history.parquet (full backcast, deterministic) ---
    if closes is not None and hist_frame is not None:
        try:
            from engine.systematic_flows import vc_exposure, cta_positioning  # noqa: PLC0415
            vc_df  = vc_exposure(closes)
            cta_df = cta_positioning(closes)
            rets   = closes.pct_change(fill_method=None)
            rv21_s = rets.rolling(21, min_periods=11).std(ddof=0) * np.sqrt(_TRADING_YEAR)
            rv63_s = rets.rolling(63, min_periods=32).std(ddof=0) * np.sqrt(_TRADING_YEAR)

            history_df = pd.DataFrame({
                "spx_close":   closes,
                "rv21":        rv21_s,
                "rv63":        rv63_s,
                "vc_alloc_bn": vc_df["alloc_bn"],
                "vc_flow_bn":  vc_df["flow_bn"],
                "cta_score":   cta_df["cta_score"],
                "cta_z":       cta_df["cta_z"],
                "cta_flow":    cta_df["cta_flow"],
            })
            history_df.index.name = "date"
            history_df.to_parquet(out_dir / "history.parquet")
            log.info("market_structure: wrote history.parquet (%d rows)", len(history_df))
        except Exception as exc:  # noqa: BLE001
            log.warning("market_structure: history.parquet write failed: %s", exc)

    # --- Write ledger (LANE-GATED) ---
    try:
        ledger_rows = _build_ledger_rows(artifact, closes, prev_artifact)
        _append_ledger(ledger_rows, data_dir)
    except Exception as exc:  # noqa: BLE001
        log.warning("market_structure: ledger build failed: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
