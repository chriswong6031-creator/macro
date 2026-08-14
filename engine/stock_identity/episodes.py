"""Identity-episode catalog v0 — expert-independent, path-anchored (registration §7).

Three episode types, built once per instrument from daily bars by a frozen
mechanical segmentation. **No expert fire appears anywhere in the construction**
(masterplan G-3) — that is the property that makes the catalog an independent
ruler later rather than a mirror of the thing it would measure.

``reset_decline``      a leg from a 126-session closing high that falls >= X*A0 AND
                       >= Y%, ending at a durable low (no lower close for >= N
                       sessions AND a rebound of >= k*A0 and >= z%) or at truncation
``reclaim``            the first sustained recapture of the 200DMA after a breakdown
                       state; resolution held/failed within M sessions
``failed_breakdown``   a close below the prior 60-session low that recovers the level
                       within m sessions

Anchors are per type (masterplan §7.3, review finding 25): the durable low for a
decline, the recapture bar for a reclaim, the breakdown low for a failed
breakdown. Metrics are never pooled across types without the type reported.

Censored, never dropped
-----------------------
A leg still open at the right edge of the tape is emitted with
``resolution="censored"`` and a ``terminated_reason``, not discarded (LER
convention, masterplan §9.5). A YELP-class secular decline that never prints a
durable low is exactly the case this rule exists for: dropping it would turn every
downstream recall figure into a survivorship filter. Censored episodes have no
anchor.

Labeling honesty
----------------
Resolution labels use future data **by design** — the catalog is a research-time
labeling instrument, never a live signal, and nothing downstream ships a label
before its window matures (masterplan §7.2). ``resolution_known_date`` records the
first date on which each label was knowable, so a PIT consumer can honor it.

Depth is context, never a bonus: tiers exist so a later recall figure can quote the
tier it was measured at, not so deeper episodes score higher.

A0 basis
--------
``A0 = Wilder ATR(14) at the prior confirmed close`` (LER convention). Two A0s are
recorded because two different questions are being asked: ``a0_leg`` (at the leg's
126-session high) scales the *fall*, ``a0_anchor`` (at the low) scales the
*rebound* and every low-relative distance. A single stale A0 across a 24-month leg
would misstate both.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

from engine.stock_technicals import atr as _atr

log = logging.getLogger(__name__)

EPISODE_TYPES: tuple[str, ...] = ("reset_decline", "reclaim", "failed_breakdown")

RESOLUTIONS: tuple[str, ...] = ("durable_low", "held", "failed", "recovered", "censored")

ATR_BASIS = "wilder_atr14_at_prior_confirmed_close"

#: Rolling window whose closing high starts a decline leg (registration §7).
HIGH_WIN = 126
#: Window whose low a failed breakdown undercuts (registration §7).
BREAKDOWN_LOW_WIN = 60
#: Tier depth floors (registration §7). Duration floors are the calibrated D1/D2.
TIER1_DEPTH = 0.35
TIER2_DEPTH = 0.20


@dataclass(frozen=True)
class EpisodeConstants:
    """Catalog constants frozen in ``si_constants_v1.json`` (registration §7)."""

    X: float          # decline qualification in A0 units
    Y: float          # decline qualification as a fraction of the high
    N: int            # sessions a low must survive to be durable
    k: float          # durable-low rebound in A0 units
    z: float          # durable-low rebound as a fraction of the low
    M: int            # sessions in which a reclaim resolves held/failed
    m: int            # sessions in which a failed breakdown must recover
    D1: int           # tier-1 duration floor in sessions
    D2: int           # tier-2 duration floor in sessions
    S_reclaim: int    # sessions above the 200DMA that make a recapture "sustained"

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass
class Episode:
    symbol: str
    price_plane_id: str
    episode_type: str
    tier: int
    start_date: pd.Timestamp
    anchor_date: pd.Timestamp | None
    end_date: pd.Timestamp
    resolution: str
    censored: bool
    depth_pct: float
    depth_atr: float
    duration_sessions: int
    a0_leg: float
    a0_anchor: float | None
    atr_basis: str = ATR_BASIS
    resolution_known_date: pd.Timestamp | None = None
    terminated_reason: str | None = None
    reference_price: float = float("nan")
    anchor_price: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        row = asdict(self)
        row.pop("extras", None)
        row.update(self.extras)
        return row


# ---------------------------------------------------------------------------
# shared primitives
# ---------------------------------------------------------------------------
def a0_series(df: pd.DataFrame) -> pd.Series:
    """Wilder ATR(14) shifted one session — A0 at the *prior confirmed close*."""
    if not {"high", "low", "close"}.issubset(df.columns):
        return pd.Series(np.nan, index=df.index)
    return _atr(df["high"], df["low"], df["close"], n=14).shift(1)


def _tier(depth: float, duration: int, const: EpisodeConstants) -> int:
    if depth >= TIER1_DEPTH and duration >= const.D1:
        return 1
    if depth >= TIER2_DEPTH and duration >= const.D2:
        return 2
    return 3


def candidate_lows(
    df: pd.DataFrame, *, min_depth: float = TIER2_DEPTH, high_win: int = HIGH_WIN
) -> list[dict[str, Any]]:
    """Running-minimum candidate lows inside depth-qualified decline legs.

    **Depth-only qualification on purpose.** The calibrator needs candidate lows to
    *choose* N, k, z and the false-start threshold; if candidacy already depended on
    those constants the selection rules would be circular. So a candidate here is
    any running minimum inside a leg that has fallen ``min_depth`` from its
    126-session high — no A0 gate, no survival gate, no rebound gate.

    Each record carries the index of the low, its A0, the leg's high and A0, and the
    sessions elapsed since the leg's high.
    """
    close = df["close"].astype(float)
    n = len(close)
    if n < high_win + 2:
        return []
    cv = close.to_numpy(dtype=float)
    roll = close.rolling(high_win, min_periods=high_win).max().to_numpy(dtype=float)
    a0 = a0_series(df).to_numpy(dtype=float)

    out: list[dict[str, Any]] = []
    peak_i: int | None = None
    peak_v = np.nan
    run_min = np.inf
    for t in range(n):
        if np.isfinite(roll[t]) and cv[t] >= roll[t]:
            peak_i, peak_v, run_min = t, cv[t], np.inf
            continue
        if peak_i is None or not np.isfinite(peak_v) or peak_v <= 0:
            continue
        if cv[t] < run_min:
            run_min = cv[t]
            depth = (peak_v - cv[t]) / peak_v
            if depth >= min_depth:
                out.append(
                    {
                        "low_i": t,
                        "low_price": float(cv[t]),
                        "a0_low": float(a0[t]) if np.isfinite(a0[t]) else np.nan,
                        "leg_i": peak_i,
                        "leg_price": float(peak_v),
                        "a0_leg": float(a0[peak_i]) if np.isfinite(a0[peak_i]) else np.nan,
                        "depth": float(depth),
                        "duration": int(t - peak_i),
                    }
                )
    return out


def high_refresh_indices(df: pd.DataFrame, high_win: int = HIGH_WIN) -> np.ndarray:
    """Indices where the close sets a new ``high_win``-session closing high."""
    close = df["close"].astype(float)
    roll = close.rolling(high_win, min_periods=high_win).max()
    return np.flatnonzero((close >= roll).to_numpy() & roll.notna().to_numpy())


# ---------------------------------------------------------------------------
# reset / decline episodes
# ---------------------------------------------------------------------------
def _find_durable_low(
    cv: np.ndarray, a0: np.ndarray, start: int, const: EpisodeConstants
) -> tuple[int, str, int | None, int | None]:
    """Scan forward from ``start`` for the first durable low.

    Returns ``(low_index, resolution, resolution_known_index, end_index)``.
    ``resolution`` is ``durable_low`` or ``censored``; a censored leg's low index is
    the deepest running minimum seen and carries no anchor downstream.
    """
    n = len(cv)
    run_min = np.inf
    run_min_i = start
    t = start + 1
    while t < n:
        c = cv[t]
        if c < run_min:
            run_min, run_min_i = c, t
            if t + const.N < n:
                window = cv[t + 1 : t + const.N + 1]
                if float(window.min()) >= c:
                    rebound = float(window.max()) - c
                    a0_low = a0[t]
                    atr_ok = np.isfinite(a0_low) and a0_low > 0 and rebound >= const.k * a0_low
                    pct_ok = c > 0 and (rebound / c) >= const.z
                    if atr_ok and pct_ok:
                        return t, "durable_low", t + const.N, t
        t += 1
    return run_min_i, "censored", None, n - 1


def reset_decline_episodes(
    df: pd.DataFrame,
    *,
    symbol: str,
    plane_id: str,
    const: EpisodeConstants,
    terminated_reason: str | None = None,
) -> list[Episode]:
    close = df["close"].astype(float)
    n = len(close)
    if n < HIGH_WIN + 2:
        return []
    cv = close.to_numpy(dtype=float)
    roll = close.rolling(HIGH_WIN, min_periods=HIGH_WIN).max().to_numpy(dtype=float)
    a0 = a0_series(df).to_numpy(dtype=float)
    idx = df.index

    episodes: list[Episode] = []
    peak_i: int | None = None
    peak_v = np.nan
    t = 0
    while t < n:
        if np.isfinite(roll[t]) and cv[t] >= roll[t]:
            peak_i, peak_v = t, cv[t]
            t += 1
            continue
        if peak_i is None or not np.isfinite(peak_v) or peak_v <= 0:
            t += 1
            continue

        a0_leg = a0[peak_i]
        drop_pct = (peak_v - cv[t]) / peak_v
        drop_atr = (
            (peak_v - cv[t]) / a0_leg if np.isfinite(a0_leg) and a0_leg > 0 else np.nan
        )
        qualified = drop_pct >= const.Y and np.isfinite(drop_atr) and drop_atr >= const.X
        if not qualified:
            t += 1
            continue

        low_i, resolution, known_i, end_i = _find_durable_low(cv, a0, peak_i, const)
        low_v = float(cv[low_i])
        depth = (peak_v - low_v) / peak_v
        duration = int((end_i if end_i is not None else low_i) - peak_i)
        censored = resolution == "censored"
        a0_low = float(a0[low_i]) if np.isfinite(a0[low_i]) else None

        extras: dict[str, Any] = {}
        if not censored:
            extras.update(_recovery_stats(cv, a0, low_i, peak_v, low_v))

        episodes.append(
            Episode(
                symbol=symbol,
                price_plane_id=plane_id,
                episode_type="reset_decline",
                tier=_tier(depth, duration, const),
                start_date=idx[peak_i],
                anchor_date=None if censored else idx[low_i],
                end_date=idx[end_i if end_i is not None else n - 1],
                resolution=resolution,
                censored=censored,
                depth_pct=float(depth),
                depth_atr=float((peak_v - low_v) / a0_leg) if np.isfinite(a0_leg) and a0_leg > 0 else float("nan"),
                duration_sessions=duration,
                a0_leg=float(a0_leg) if np.isfinite(a0_leg) else float("nan"),
                a0_anchor=a0_low,
                resolution_known_date=None if known_i is None else idx[known_i],
                terminated_reason=terminated_reason if censored else None,
                reference_price=float(peak_v),
                anchor_price=None if censored else low_v,
                extras=extras,
            )
        )
        if censored:
            break
        peak_i = None
        peak_v = np.nan
        t = low_i + 1
    return episodes


def _recovery_stats(
    cv: np.ndarray, a0: np.ndarray, low_i: int, peak_v: float, low_v: float
) -> dict[str, Any]:
    """F3 inputs for one resolved decline: post-trough advance and retrace speed."""
    n = len(cv)
    out: dict[str, Any] = {"post_trough_63d_atr": np.nan, "sessions_to_50pct_retrace": np.nan}
    a0_low = a0[low_i]
    if low_i + 63 < n and np.isfinite(a0_low) and a0_low > 0:
        out["post_trough_63d_atr"] = float((cv[low_i + 63] - low_v) / a0_low)
    target = low_v + 0.5 * (peak_v - low_v)
    fwd = cv[low_i + 1 :]
    hit = np.flatnonzero(fwd >= target)
    if len(hit):
        out["sessions_to_50pct_retrace"] = float(hit[0] + 1)
    return out


# ---------------------------------------------------------------------------
# reclaim episodes
# ---------------------------------------------------------------------------
def reclaim_episodes(
    df: pd.DataFrame,
    states: pd.Series,
    *,
    symbol: str,
    plane_id: str,
    const: EpisodeConstants,
    terminated_reason: str | None = None,
) -> list[Episode]:
    """First sustained 200DMA recapture after each breakdown-state run.

    "Sustained" needs an operational definition that registration §7 does not give;
    ``S_reclaim`` (declared, not partition-computed) supplies it: the close must sit
    above the 200DMA for ``S_reclaim`` consecutive sessions. One reclaim per
    breakdown run — a second recapture inside the same run would double-count the
    same structural event.
    """
    close = df["close"].astype(float)
    n = len(close)
    if n < 210:
        return []
    cv = close.to_numpy(dtype=float)
    sma200 = close.rolling(200, min_periods=200).mean().to_numpy(dtype=float)
    a0 = a0_series(df).to_numpy(dtype=float)
    idx = df.index
    st = states.reindex(df.index).to_numpy()

    is_bd = np.asarray([s == "breakdown" for s in st], dtype=bool)
    runs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if is_bd[i]:
            j = i
            while j + 1 < n and is_bd[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1

    episodes: list[Episode] = []
    for r, (b0, b1) in enumerate(runs):
        stop = runs[r + 1][0] if r + 1 < len(runs) else n
        anchor = None
        for t in range(b1 + 1, stop):
            if t + const.S_reclaim > n:
                break
            w = slice(t, t + const.S_reclaim)
            if np.all(np.isfinite(sma200[w])) and np.all(cv[w] > sma200[w]):
                anchor = t
                break
        if anchor is None:
            continue

        seg = cv[b0 : b1 + 1]
        low_v = float(np.min(seg)) if len(seg) else float(cv[b1])
        ref = float(np.max(cv[max(0, b0 - 252) : b0 + 1])) if b0 > 0 else float(cv[b0])
        depth = (ref - low_v) / ref if ref > 0 else 0.0

        resolution = "censored"
        end_i = n - 1
        known_i: int | None = None
        horizon = min(anchor + const.M, n - 1)
        broke = None
        for t in range(anchor + 1, horizon + 1):
            if np.isfinite(sma200[t]) and cv[t] < sma200[t]:
                broke = t
                break
        if broke is not None:
            resolution, end_i, known_i = "failed", broke, broke
        elif anchor + const.M <= n - 1:
            resolution, end_i, known_i = "held", anchor + const.M, anchor + const.M

        duration = int(anchor - b0)
        a0_leg = a0[b0] if np.isfinite(a0[b0]) else np.nan
        episodes.append(
            Episode(
                symbol=symbol,
                price_plane_id=plane_id,
                episode_type="reclaim",
                tier=_tier(depth, duration, const),
                start_date=idx[b0],
                anchor_date=idx[anchor],
                end_date=idx[end_i],
                resolution=resolution,
                censored=resolution == "censored",
                depth_pct=float(depth),
                depth_atr=float((ref - low_v) / a0_leg) if np.isfinite(a0_leg) and a0_leg > 0 else float("nan"),
                duration_sessions=duration,
                a0_leg=float(a0_leg) if np.isfinite(a0_leg) else float("nan"),
                a0_anchor=float(a0[anchor]) if np.isfinite(a0[anchor]) else None,
                resolution_known_date=None if known_i is None else idx[known_i],
                terminated_reason=terminated_reason if resolution == "censored" else None,
                reference_price=ref,
                anchor_price=float(cv[anchor]),
                extras={"breakdown_low": low_v},
            )
        )
    return episodes


# ---------------------------------------------------------------------------
# failed-breakdown episodes
# ---------------------------------------------------------------------------
def failed_breakdown_episodes(
    df: pd.DataFrame,
    *,
    symbol: str,
    plane_id: str,
    const: EpisodeConstants,
    terminated_reason: str | None = None,
) -> list[Episode]:
    """A close below the prior 60-session low that recovers the level within m.

    Registration §7 defines this type by its recovery, so an undercut that never
    recovers is **not** a failed breakdown — it is decline-leg material and is
    catalogued there. Only the truncated case (fewer than m sessions of tape left)
    is emitted as censored, because there the label is unknown rather than negative.
    """
    close = df["close"].astype(float)
    n = len(close)
    if n < BREAKDOWN_LOW_WIN + 3:
        return []
    cv = close.to_numpy(dtype=float)
    low60 = (
        close.rolling(BREAKDOWN_LOW_WIN, min_periods=BREAKDOWN_LOW_WIN).min().shift(1)
    ).to_numpy(dtype=float)
    a0 = a0_series(df).to_numpy(dtype=float)
    idx = df.index

    episodes: list[Episode] = []
    t = BREAKDOWN_LOW_WIN
    while t < n:
        level = low60[t]
        if not np.isfinite(level) or cv[t] >= level:
            t += 1
            continue
        horizon = min(t + const.m, n - 1)
        rec = None
        for j in range(t + 1, horizon + 1):
            if cv[j] >= level:
                rec = j
                break
        if rec is None and horizon < t + const.m:
            seg = cv[t : n]
            li = t + int(np.argmin(seg))
            depth = (level - float(cv[li])) / level if level > 0 else 0.0
            a0_leg = a0[t] if np.isfinite(a0[t]) else np.nan
            episodes.append(
                Episode(
                    symbol=symbol, price_plane_id=plane_id, episode_type="failed_breakdown",
                    tier=_tier(depth, int(n - 1 - t), const),
                    start_date=idx[t], anchor_date=None, end_date=idx[n - 1],
                    resolution="censored", censored=True,
                    depth_pct=float(depth),
                    depth_atr=float((level - cv[li]) / a0_leg) if np.isfinite(a0_leg) and a0_leg > 0 else float("nan"),
                    duration_sessions=int(n - 1 - t),
                    a0_leg=float(a0_leg) if np.isfinite(a0_leg) else float("nan"),
                    a0_anchor=None,
                    terminated_reason=terminated_reason,
                    reference_price=float(level),
                    anchor_price=None,
                )
            )
            break
        if rec is None:
            t = horizon + 1
            continue

        seg = cv[t : rec + 1]
        li = t + int(np.argmin(seg))
        depth = (level - float(cv[li])) / level if level > 0 else 0.0
        duration = int(rec - t)
        a0_leg = a0[t] if np.isfinite(a0[t]) else np.nan
        episodes.append(
            Episode(
                symbol=symbol, price_plane_id=plane_id, episode_type="failed_breakdown",
                tier=_tier(depth, duration, const),
                start_date=idx[t], anchor_date=idx[li], end_date=idx[rec],
                resolution="recovered", censored=False,
                depth_pct=float(depth),
                depth_atr=float((level - cv[li]) / a0_leg) if np.isfinite(a0_leg) and a0_leg > 0 else float("nan"),
                duration_sessions=duration,
                a0_leg=float(a0_leg) if np.isfinite(a0_leg) else float("nan"),
                a0_anchor=float(a0[li]) if np.isfinite(a0[li]) else None,
                resolution_known_date=idx[rec],
                reference_price=float(level),
                anchor_price=float(cv[li]),
            )
        )
        t = rec + 1
    return episodes


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------
def build_catalog(
    df: pd.DataFrame,
    *,
    symbol: str,
    plane_id: str,
    const: EpisodeConstants,
    states: pd.Series | None = None,
    terminated_reason: str | None = None,
) -> pd.DataFrame:
    """All three episode types for one instrument, sorted by start date."""
    eps: list[Episode] = []
    eps += reset_decline_episodes(
        df, symbol=symbol, plane_id=plane_id, const=const,
        terminated_reason=terminated_reason,
    )
    if states is not None:
        eps += reclaim_episodes(
            df, states, symbol=symbol, plane_id=plane_id, const=const,
            terminated_reason=terminated_reason,
        )
    eps += failed_breakdown_episodes(
        df, symbol=symbol, plane_id=plane_id, const=const,
        terminated_reason=terminated_reason,
    )
    if not eps:
        return pd.DataFrame(columns=list(Episode(
            symbol="", price_plane_id="", episode_type="", tier=3,
            start_date=pd.NaT, anchor_date=None, end_date=pd.NaT, resolution="censored",
            censored=True, depth_pct=0.0, depth_atr=0.0, duration_sessions=0,
            a0_leg=0.0, a0_anchor=None,
        ).as_row().keys()))
    rows = [e.as_row() for e in eps]
    out = pd.DataFrame(rows).sort_values(["start_date", "episode_type"]).reset_index(drop=True)
    return out


def catalog_f3_stats(catalog: pd.DataFrame) -> dict[str, float | None]:
    """F3 (recovery velocity) fingerprint inputs, from resolved decline episodes only."""
    if catalog is None or catalog.empty:
        return {"f3_post_trough_63d_atr_median": None, "f3_time_to_50pct_retrace_median": None}
    sub = catalog[(catalog["episode_type"] == "reset_decline") & (~catalog["censored"])]
    out: dict[str, float | None] = {}
    for col, key in (
        ("post_trough_63d_atr", "f3_post_trough_63d_atr_median"),
        ("sessions_to_50pct_retrace", "f3_time_to_50pct_retrace_median"),
    ):
        if col in sub.columns:
            vals = pd.to_numeric(sub[col], errors="coerce").dropna()
            out[key] = float(vals.median()) if len(vals) else None
        else:
            out[key] = None
    return out


def durable_lows(catalog: pd.DataFrame, min_tier: int = 2) -> pd.DataFrame:
    """Resolved decline anchors at ``min_tier`` or better — the calibrator's material
    for the useful-zone constants."""
    if catalog is None or catalog.empty:
        return pd.DataFrame()
    return catalog[
        (catalog["episode_type"] == "reset_decline")
        & (catalog["resolution"] == "durable_low")
        & (catalog["tier"] <= min_tier)
    ].copy()


def summarize(catalog: pd.DataFrame) -> dict[str, Any]:
    """Small per-name summary used by dossiers and the census."""
    if catalog is None or catalog.empty:
        return {"n_episodes": 0, "n_censored": 0, "by_type": {}, "by_tier": {}}
    return {
        "n_episodes": int(len(catalog)),
        "n_censored": int(catalog["censored"].sum()),
        "by_type": {k: int(v) for k, v in catalog["episode_type"].value_counts().items()},
        "by_tier": {int(k): int(v) for k, v in catalog["tier"].value_counts().items()},
    }


def episode_columns() -> Sequence[str]:
    return (
        "symbol", "price_plane_id", "episode_type", "tier", "start_date", "anchor_date",
        "end_date", "resolution", "censored", "depth_pct", "depth_atr",
        "duration_sessions", "a0_leg", "a0_anchor", "atr_basis",
        "resolution_known_date", "terminated_reason", "reference_price", "anchor_price",
    )
