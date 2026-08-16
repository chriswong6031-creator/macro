"""The three frozen naive comparators (registration §5).

These are **reference constructions**, not production engines: nothing in the repo emits
them, nothing consumes them, and they exist so a later ruler has a floor that is not
another house detector. All three are built on the canon oscillator core only — one RSI
family per module, per the indicator-core law — read completed bars, and use a close
basis. Their spec hashes are minted from the constants below.

``rsi30_cross``     canon RSI(14) daily crosses UP through 30 (prior close < 30, this close >= 30)
``low20d_bounce``   close prints a 20-session low, then the NEXT session closes above the
                    prior session's close (the fire is the bounce bar)
``stoch2w_cross``   2W-grid StochRSI (canon 14/3/3) %K crosses up through %D with BOTH lines
                    below 20 at the prior completed 2W bar — the PSS incumbent gauge's shape

The 2W grid takes each completed bucket's last actual session as its known-ts, so a 2W fire
is stamped at a real traded close and never at a calendar Friday the name did not trade.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine import canon

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay.grid import (
    KNOWN_BASIS_BUCKET,
    KNOWN_BASIS_DAILY,
    two_week_bars,
)

__all__ = ["FAMILY_KEYS", "ERA", "constants", "fires"]

FAMILY_KEYS: tuple[str, ...] = ("rsi30_cross", "low20d_bounce", "stoch2w_cross")

#: These constructions are minted BY this registration, so their era is this wave.
ERA = "si-naive-comparators-v0-2026-08-14"

RSI30_LEVEL = 30.0
LOW_WINDOW = 20
STOCH2W_BAND = 20.0


def constants(family_key: str) -> dict[str, Any]:
    base = {
        "producer": f"engine.stock_identity.replay.naive:{family_key}",
        "era": ERA,
        "oscillator_core": "engine.canon (SMA-seeded RMA; one RSI family)",
        "basis": "close, completed bars only",
    }
    if family_key == "rsi30_cross":
        base |= {"rsi_len": canon.RSI_LEN, "level": RSI30_LEVEL, "grain": "1D",
                 "rule": "prior close RSI < 30 and this close RSI >= 30"}
    elif family_key == "low20d_bounce":
        base |= {"window": LOW_WINDOW, "grain": "1D",
                 "rule": "close prints a 20-session low, next session closes above the "
                         "prior session's close"}
    elif family_key == "stoch2w_cross":
        base |= {"stoch_len": canon.STOCH_LEN, "smooth_k": canon.SMOOTH_K,
                 "smooth_d": canon.SMOOTH_D, "band": STOCH2W_BAND, "grain": "2W",
                 "rule": "%K crosses up through %D with both < 20 on the completed 2W bar",
                 "grid_anchor": "absolute week index (label.toordinal() // 7) // 2 over "
                                "calendar-anchored W-FRI bars — never resample('2W-FRI'), "
                                "which phases from the series' first row"}
    else:  # pragma: no cover - guarded by the caller
        raise ValueError(f"unknown naive family {family_key!r}")
    return base


def _event(
    *, family_key: str, subtype: str, symbol: str, price_plane_id: str, grain: str,
    signal_ts, signal_known_ts, known_basis: str, spec_hash: str,
    family_first_available: str | None, context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ev.make_event(
        family_key=family_key,
        producer=f"engine.stock_identity.replay.naive:{family_key}",
        family="naive_comparator",
        subtype=subtype,
        stage="REFERENCE",
        symbol=symbol,
        price_plane_id=price_plane_id,
        grain=grain,
        signal_ts=signal_ts,
        signal_known_ts=signal_known_ts,
        known_basis=known_basis,
        signal_era=ERA,
        detector_spec_hash=spec_hash,
        source_hash=spec_hash,
        field_origin="replay_recomputed",
        provenance_class="R",
        family_first_available=family_first_available,
        scored_authority=False,
        spec_postdates_history=False,
        context=context,
    )


def fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hashes: dict[str, str],
    family_first_available: dict[str, str | None],
) -> list[dict[str, Any]]:
    """All three comparators for one name."""
    close = df["close"].astype(float).dropna().sort_index()
    if len(close) < 60:
        return []
    rows: list[dict[str, Any]] = []
    idx = pd.DatetimeIndex(close.index)

    # --- rsi30_cross ---------------------------------------------------------
    r = canon.rsi(close, canon.RSI_LEN)
    up = ((r >= RSI30_LEVEL) & (r.shift(1) < RSI30_LEVEL)).fillna(False).to_numpy()
    for i in np.flatnonzero(up):
        ts = pd.Timestamp(idx[i])
        rows.append(_event(
            family_key="rsi30_cross", subtype="cross_up_30", symbol=symbol,
            price_plane_id=price_plane_id, grain="1D", signal_ts=ts, signal_known_ts=ts,
            known_basis=KNOWN_BASIS_DAILY, spec_hash=spec_hashes["rsi30_cross"],
            family_first_available=family_first_available.get("rsi30_cross"),
        ))

    # --- low20d_bounce -------------------------------------------------------
    roll_min = close.rolling(LOW_WINDOW).min()
    at_low = (close <= roll_min).fillna(False).to_numpy()
    higher = (close > close.shift(1)).fillna(False).to_numpy()
    bounce = np.zeros(len(close), dtype=bool)
    bounce[1:] = at_low[:-1] & higher[1:]
    for i in np.flatnonzero(bounce):
        ts = pd.Timestamp(idx[i])
        rows.append(_event(
            family_key="low20d_bounce", subtype="bounce_after_20d_low", symbol=symbol,
            price_plane_id=price_plane_id, grain="1D", signal_ts=ts, signal_known_ts=ts,
            known_basis=KNOWN_BASIS_DAILY, spec_hash=spec_hashes["low20d_bounce"],
            family_first_available=family_first_available.get("low20d_bounce"),
            context={"low_session": str(pd.Timestamp(idx[i - 1]).date())},
        ))

    # --- stoch2w_cross -------------------------------------------------------
    bars = two_week_bars(close)
    if len(bars) >= canon.STOCH_LEN + canon.SMOOTH_K + canon.SMOOTH_D + 2:
        k2, d2 = canon.stoch_rsi_kd(pd.Series(bars["close"].to_numpy(dtype="float64")))
        sel = (
            canon.crossover(k2, d2) & (k2 < STOCH2W_BAND) & (d2 < STOCH2W_BAND)
        ).fillna(False).to_numpy()
        for i in np.flatnonzero(sel):
            open_s, known = bars["open"].iloc[i], bars["known"].iloc[i]
            if pd.isna(known) or pd.isna(open_s):
                continue
            rows.append(_event(
                family_key="stoch2w_cross", subtype="k_over_d_oversold", symbol=symbol,
                price_plane_id=price_plane_id, grain="2W",
                signal_ts=pd.Timestamp(open_s), signal_known_ts=pd.Timestamp(known),
                known_basis=KNOWN_BASIS_BUCKET, spec_hash=spec_hashes["stoch2w_cross"],
                family_first_available=family_first_available.get("stoch2w_cross"),
                context={"calendar_label": str(pd.Timestamp(bars['label'].iloc[i]).date())},
            ))
    return rows
