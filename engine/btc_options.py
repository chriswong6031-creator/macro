"""Publish the existing Deribit snapshot as a stable display-only contract."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from lib import store

SCHEMA = "crypto.btc_options/v1"


def _f(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_contract(
    reader: Callable[[str, str], pd.DataFrame | None] = store.read,
) -> dict:
    frame = reader("deribit", "options_structure")
    dvol_frame = reader("deribit", "dvol")
    if frame is None or frame.empty:
        return {
            "schema": SCHEMA,
            "tier": "display",
            "display_only": True,
            "as_of": None,
            "coverage": {
                "available": False,
                "observations": 0,
                "note_en": "Deribit options snapshot is awaiting its next collection.",
                "note_zh": "Deribit 期权快照正在等待下一次采集。",
            },
            "spot": None,
            "volatility": {
                "dvol": None,
                "atm_iv_7d": None,
                "atm_iv_30d": None,
                "atm_iv_90d": None,
                "atm_iv_180d": None,
                "term_slope_30_90": None,
                "rr_25d": None,
                "skew_25d": None,
                "skew_term": None,
            },
            "positioning": {
                "put_call_oi_ratio": None,
                "put_call_vol_ratio": None,
                "max_pain": None,
                "max_pain_expiry_d": None,
                "total_oi_btc": None,
            },
            "gamma": {
                "gex_per_1pct_usd": None,
                "gamma_concentration_usd": None,
                "flip": None,
                "distance_pct": None,
                "regime": None,
                "assumption_en": "Dealer sign assumes long calls and short puts.",
                "assumption_zh": "交易商符号假设为多头看涨、空头看跌。",
            },
            "basis": {
                "annualized_pct": None,
                "front_annualized_pct": None,
                "slope_pct": None,
            },
        }
    frame = frame.sort_index()
    last = frame.iloc[-1]
    as_of = str(pd.Timestamp(frame.index[-1]).date())
    dvol = None
    if dvol_frame is not None and not dvol_frame.empty:
        col = "dvol_close" if "dvol_close" in dvol_frame.columns else "close"
        if col in dvol_frame:
            dvol = _f(dvol_frame[col].dropna().iloc[-1])
    return {
        "schema": SCHEMA,
        "tier": "display",
        "display_only": True,
        "as_of": as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": {
            "available": True,
            "observations": int(len(frame)),
            "first_date": str(pd.Timestamp(frame.index[0]).date()),
            "last_date": as_of,
            "note_en": (
                f"{len(frame):,} daily point-in-time chain snapshots accrued since "
                f"{pd.Timestamp(frame.index[0]).date()}."
            ),
            "note_zh": (
                f"自 {pd.Timestamp(frame.index[0]).date()} 起已积累 "
                f"{len(frame):,} 个每日链上快照。"
            ),
        },
        "spot": _f(last.get("underlying")),
        "volatility": {
            "dvol": dvol,
            "atm_iv_7d": _f(last.get("atm_iv_7d")),
            "atm_iv_30d": _f(last.get("atm_iv_30d")),
            "atm_iv_90d": _f(last.get("atm_iv_90d")),
            "atm_iv_180d": _f(last.get("atm_iv_180d")),
            "term_slope_30_90": _f(last.get("term_slope_30_90")),
            "rr_25d": _f(last.get("rr_25d")),
            "skew_25d": _f(last.get("skew_25d")),
            "skew_term": _f(last.get("skew_term")),
        },
        "positioning": {
            "put_call_oi_ratio": _f(last.get("put_call_oi_ratio")),
            "put_call_vol_ratio": _f(last.get("put_call_vol_ratio")),
            "max_pain": _f(last.get("max_pain")),
            "max_pain_expiry_d": _f(last.get("max_pain_expiry_d")),
            "total_oi_btc": _f(last.get("total_oi_btc")),
        },
        "gamma": {
            "gex_per_1pct_usd": _f(last.get("gex_per_1pct_usd")),
            "gamma_concentration_usd": _f(last.get("gamma_concentration_usd")),
            "flip": _f(last.get("gamma_flip")),
            "distance_pct": _f(last.get("dist_to_flip_pct")),
            "regime": last.get("gamma_regime"),
            "assumption_en": "Dealer sign assumes long calls and short puts.",
            "assumption_zh": "交易商符号假设为多头看涨、空头看跌。",
        },
        "basis": {
            "annualized_pct": _f(last.get("basis_ann")),
            "front_annualized_pct": _f(last.get("basis_front_ann")),
            "slope_pct": _f(last.get("basis_slope")),
        },
    }


def write_contract(site: Path, contract: dict | None = None) -> Path:
    site.mkdir(parents=True, exist_ok=True)
    path = site / "btc_options.json"
    payload = contract if contract is not None else build_contract()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
