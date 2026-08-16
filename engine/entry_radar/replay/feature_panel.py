"""Builds the §7 matching panel: raw per-name features, then cross-sectional cuts.

This module IMPLEMENTS the laws :mod:`engine.entry_radar.replay.features` declares
(cohort order, C32, regime, the matching feature list).  Nothing is redefined here
— the frozen predicates live there and are called; what this module adds is the
two-pass mechanics the laws imply:

**Pass 1 — :func:`build_feature_rows`** is per NAME.  It computes every quantity
that is a property of that name alone, as of each requested decision session D:
proximity to the 63-bar close min, trailing dollar volume, 60-session return,
20-session realized vol, the hotness inputs, market cap, the cohort tag, C32 and
the regime tag.  Indicator values (StochRSI %K) are read through the **prior
confirmed close** (D−1), which is what ``features``' own docstring pins and what
:func:`features.c32_flag`'s ``asof_pos`` argument means.

**Pass 2 — :func:`cross_sectionalize`** is per (panel, session).  Deciles and
quintiles are CROSS-SECTIONAL by construction — a "decile 9 dollar volume" is a
statement about the panel on that day, not about the name's own history — so they
cannot be computed in pass 1 without leaking one name's rank into another's.
Ranking is ``rank(method="first")`` over a deterministic ticker sort, so ties
resolve identically on every machine and every re-run; the raw columns are dropped
on the way out so what ``controls`` receives is exactly the declared panel.

MARKET CAP (frozen §7 PIT proxy, and its footgun)
--------------------------------------------------
``cap_usd_fn(ticker)`` returns **CURRENT SHARES OUTSTANDING**, not a cap.  Cap at
D = shares × adjusted close at D — the only PIT-computable form without a
shares-history feed, exact up to buyback/issuance drift, applied to candidates and
controls alike so the bucket-assignment error is symmetric.  The parameter keeps
the name the runner contract gave it; the units are stated here and in the
signature so nobody multiplies a cap by a price.

PURITY.  No network, no clock, no environment, no writes.  Every input is passed in.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.entry_radar import indicator_core as ic
from engine.entry_radar.replay import controls, features, prereg

#: The panel columns ``controls`` requires, plus the episode-facing tags.  This is
#: EXACTLY what :func:`cross_sectionalize` returns (plus ``panel`` when the caller
#: supplied one) — a drift here is a test failure, not a silent widening.
PANEL_COLUMNS: tuple[str, ...] = controls.REQUIRED_COLUMNS + (
    "session", "cohort", "c32", "regime", "history_sessions",
)

#: Raw (pre-rank) columns pass 1 emits and pass 2 consumes and drops.
RAW_COLUMNS: tuple[str, ...] = (
    "raw_proximity", "raw_dollar_vol", "raw_ret60", "raw_absret60", "raw_vol20",
    "raw_relvol20", "raw_absret5", "raw_cap_usd",
)

#: Sentinel for a bucket index that pass 2 has not filled yet.  Never -1 after
#: :func:`cross_sectionalize`; a surviving -1 means the row was not ranked.
UNRANKED = -1

_QUINTILES = 5
_DECILES = 10

#: Trailing window for the matching dollar-volume feature.  Same window as §11's
#: ADV floor (``prereg.ADV_WINDOW_SESSIONS``), so "the liquidity bucket" and "the
#: cost tier" are statements about one measured quantity rather than two.
_DOLLAR_VOL_WINDOW = prereg.ADV_WINDOW_SESSIONS
_RET_WINDOW = 60
_VOL_WINDOW = 20
_RELVOL_WINDOW = 20
_RET5_WINDOW = 5
_MA_LONG = 200
_HIGH_252 = 252


class FeaturePanelError(RuntimeError):
    """A malformed feature input.  Named rather than absorbed into a NaN."""


# --------------------------------------------------------------------------- #
# pass 1 — per name
# --------------------------------------------------------------------------- #
def build_feature_rows(ticker: str, daily_ohlc: pd.DataFrame,
                       spy_close: pd.Series, sector: str | None,
                       cap_usd_fn: Callable[[str], float | None],
                       sessions: Sequence[date] | pd.DatetimeIndex,
                       *, panel: str | None = None) -> pd.DataFrame:
    """One name's §7 feature rows at each requested decision session.

    ``daily_ohlc`` carries ``o,h,l,c,v`` (vendor plane) or ``close/high/low/volume``
    (curated plane) — both spellings are accepted and normalised, because Panel-A's
    G0/C5 math runs on the curated store while every outcome leg runs on the vendor
    plane (§4), and a feature builder that only spoke one of them would force a
    silent basis mix at the call site.

    ``cap_usd_fn(ticker)`` returns SHARES OUTSTANDING (see the module docstring).

    Returns the panel columns with UNRANKED bucket indices — :func:`cross_sectionalize`
    fills them.  Sessions with no bar at or before D, or with no finite close, are
    OMITTED: a feature row that cannot be computed is absent from the panel and
    counted in the refusal census, never emitted with a fabricated value.
    """
    frame = _normalise(daily_ohlc)
    if frame.empty:
        return _empty_rows()
    close = frame["c"]
    index = pd.DatetimeIndex(frame.index)

    # ---- vectorised once per name; the session loop is O(1) lookups ---------
    roll_min_close = close.rolling(prereg.PROXIMITY_WINDOW_SESSIONS, min_periods=2).min()
    dollar_vol = (close * frame["v"]).rolling(_DOLLAR_VOL_WINDOW, min_periods=5).median()
    ret60 = close / close.shift(_RET_WINDOW) - 1.0
    ret1 = close.pct_change()
    vol20 = ret1.rolling(_VOL_WINDOW, min_periods=10).std()
    relvol20 = frame["v"] / frame["v"].rolling(_RELVOL_WINDOW, min_periods=5).mean()
    absret5 = (close / close.shift(_RET5_WINDOW) - 1.0).abs()
    dd63 = close / close.rolling(features.DEEP_DD_SESSIONS, min_periods=2).max() - 1.0
    dd252 = close / close.rolling(_HIGH_252, min_periods=20).max() - 1.0
    ma200 = close.rolling(_MA_LONG, min_periods=_MA_LONG).mean()
    ret120 = close / close.shift(120) - 1.0
    gap_abs = ((frame["o"] / close.shift(1) - 1.0).abs()
               if "o" in frame.columns and frame["o"].notna().any() else None)
    gap_hit = (gap_abs.rolling(features.GAP_LOOKBACK_SESSIONS, min_periods=1).max()
               if gap_abs is not None else None)

    k_conf, _d_conf = ic.stoch_rsi_kd(close)
    k_conf = pd.Series(np.asarray(k_conf, dtype=float), index=index)
    k_min5 = k_conf.rolling(features.FULL_WASHOUT_LOOKBACK, min_periods=1).min()
    k_min8 = k_conf.rolling(features.PARTIAL_WASHOUT_LOOKBACK, min_periods=1).min()

    mtf_d = _mtf_pct_d(close)
    shares = _shares(cap_usd_fn, ticker)

    rows: list[dict[str, object]] = []
    for session in _as_dates(sessions):
        pos = int(index.searchsorted(pd.Timestamp(session), side="right")) - 1
        if pos < 0:
            continue
        c_d = float(close.iloc[pos])
        if not np.isfinite(c_d) or c_d <= 0:
            continue
        prior = pos - 1                       # the PRIOR CONFIRMED bar (features law)
        history = pos + 1
        cap_usd = None if shares is None else float(shares) * c_d
        rows.append({
            "ticker": str(ticker),
            "session": session,
            "sector": sector,
            "cap_bucket": features.cap_bucket_of(cap_usd),
            "proximity_decile": UNRANKED,
            "dollar_vol_decile": UNRANKED,
            "ret60_quintile": UNRANKED,
            "vol20_quintile": UNRANKED,
            "hot_tier": UNRANKED,
            "cohort": _cohort(
                history=history, prior=prior, pos=pos, close=close,
                gap_hit=gap_hit, dd63=dd63, dd252=dd252, ma200=ma200,
                ret120=ret120, k_min5=k_min5, k_min8=k_min8, mtf_d=mtf_d,
                cap_usd=cap_usd),
            "c32": features.c32_flag(close, prior) if prior >= 0 else None,
            "regime": features.regime_tag(spy_close, session),
            "history_sessions": int(history),
            "raw_proximity": _proximity(c_d, roll_min_close, pos),
            "raw_dollar_vol": _at(dollar_vol, pos),
            "raw_ret60": _at(ret60, pos),
            "raw_absret60": (None if _at(ret60, pos) is None
                             else abs(float(_at(ret60, pos)))),
            "raw_vol20": _at(vol20, pos),
            "raw_relvol20": _at(relvol20, pos),
            "raw_absret5": _at(absret5, pos),
            "raw_cap_usd": cap_usd,
        })
    out = pd.DataFrame(rows, columns=list(PANEL_COLUMNS) + list(RAW_COLUMNS))
    if panel is not None:
        out["panel"] = str(panel)
    return out


def _empty_rows() -> pd.DataFrame:
    return pd.DataFrame(columns=list(PANEL_COLUMNS) + list(RAW_COLUMNS))


def _normalise(daily: pd.DataFrame) -> pd.DataFrame:
    """Accept the vendor (``o,h,l,c,v``) or curated (``close,high,low,volume``) spelling."""
    if daily is None or not len(daily):
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"])
    frame = daily.copy()
    rename = {"close": "c", "high": "h", "low": "l", "volume": "v", "open": "o"}
    frame = frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})
    if "c" not in frame.columns:
        raise FeaturePanelError(
            f"daily frame needs a close column (o/h/l/c/v or close/high/low/volume); "
            f"got {list(daily.columns)}")
    for col in ("o", "h", "l", "v"):
        if col not in frame.columns:
            frame[col] = np.nan
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    for col in ("o", "h", "l", "c", "v"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype(float)
    return frame[["o", "h", "l", "c", "v"]]


def _as_dates(sessions: Sequence[date] | pd.DatetimeIndex) -> list[date]:
    return [pd.Timestamp(s).date() for s in pd.DatetimeIndex(pd.Index(list(sessions)))]


def _at(series: pd.Series, pos: int) -> float | None:
    if pos < 0 or pos >= len(series):
        return None
    value = float(series.iloc[pos])
    return value if np.isfinite(value) else None


def _proximity(close_d: float, roll_min: pd.Series, pos: int) -> float | None:
    """Distance above the 63-bar close minimum, as a fraction.

    0.0 = the name IS at its 63-bar close low (maximum proximity).  The §9 kill arm
    bands on the DECILE of this quantity, so the sign convention matters only in
    that it is monotone: smaller = closer to the low.
    """
    floor = _at(roll_min, pos)
    if floor is None or floor <= 0:
        return None
    return float(close_d / floor - 1.0)


def _shares(cap_usd_fn: Callable[[str], float | None] | Mapping[str, float] | None,
            ticker: str) -> float | None:
    if cap_usd_fn is None:
        return None
    try:
        raw = (cap_usd_fn.get(ticker) if isinstance(cap_usd_fn, Mapping)
               else cap_usd_fn(ticker))
    except Exception:  # noqa: BLE001 — a reference miss is UNKNOWN, not a crash
        return None
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) and value > 0 else None


def _mtf_pct_d(close: pd.Series) -> dict[int, pd.Series]:
    """2D and 3D StochRSI %D on the ABSOLUTE session anchor, mapped back to daily.

    Uses the frozen W3 primitive ``challengers.mtf_buckets`` (imported lazily so
    this module stays importable without the detector stack) — the absolute anchor
    is what makes two callers holding two windows of the same name agree bar for
    bar.  Each daily session carries the %D of the last bucket that had CLOSED by
    then, so the cohort test never reads a bucket from its own future.
    """
    from engine.entry_radar.challengers import mtf_buckets  # local: frozen W3 API

    out: dict[int, pd.Series] = {}
    index = pd.DatetimeIndex(close.index)
    for n in (2, 3):
        try:
            buckets = mtf_buckets(close, n)
        except Exception:  # noqa: BLE001 — an unanchorable series yields no MTF leg
            out[n] = pd.Series(np.nan, index=index)
            continue
        confirmed = [b for b in buckets if b.confirmed]
        if len(confirmed) < 3:
            out[n] = pd.Series(np.nan, index=index)
            continue
        values = pd.Series([b.close for b in confirmed],
                           index=pd.DatetimeIndex([pd.Timestamp(b.last_session)
                                                   for b in confirmed]))
        _k, d = ic.stoch_rsi_kd(values)
        d = pd.Series(np.asarray(d, dtype=float), index=values.index)
        pos = d.index.searchsorted(index, side="right") - 1
        mapped = np.full(len(index), np.nan)
        ok = pos >= 0
        mapped[ok] = d.to_numpy(dtype=float)[pos[ok]]
        out[n] = pd.Series(mapped, index=index)
    return out


def _cohort(*, history: int, prior: int, pos: int, close: pd.Series,
            gap_hit: pd.Series | None, dd63: pd.Series, dd252: pd.Series,
            ma200: pd.Series, ret120: pd.Series, k_min5: pd.Series,
            k_min8: pd.Series, mtf_d: Mapping[int, pd.Series],
            cap_usd: float | None) -> str:
    """The frozen cohort law, FIRST MATCH WINS, in ``features``' stated order.

    Two mechanical notes, both consequences of the law rather than choices:

    * ``smallcap_highvol_momentum`` needs cross-sectional quintiles that pass 1
      cannot know, so it is resolved in :func:`cross_sectionalize` — pass 1 marks
      the row with its non-quintile prerequisites and lets pass 2 finish the test.
      A row that fails the cap test here can never become that cohort, so the
      first-match order is preserved exactly.
    * ``gap_catalyst`` needs OPENs.  On a plane without them the test is
      UNEVALUABLE and the row falls through to the next cohort — recorded as such
      by the absence of the ``o`` column in the run's provenance, never scored as
      a measured "no gap".
    """
    if history < features.IPO_YOUNG_SESSIONS:
        return "ipo_young"
    if gap_hit is not None:
        gap = _at(gap_hit, pos)
        if gap is not None and gap >= features.GAP_ABS_PCT:
            return "gap_catalyst"
    deep_dd = _at(dd63, pos)
    if deep_dd is not None and deep_dd <= features.DEEP_DRAWDOWN:
        return "deep_mtf_washout"
    d2, d3 = _at(mtf_d.get(2, pd.Series(dtype=float)), pos), _at(
        mtf_d.get(3, pd.Series(dtype=float)), pos)
    if d2 is not None and d3 is not None and d2 < ic.OVERSOLD and d3 < ic.OVERSOLD:
        return "deep_mtf_washout"
    k5 = _at(k_min5, prior) if prior >= 0 else None
    if k5 is not None and k5 < features.FULL_WASHOUT_K:
        return "full_daily_washout"
    k8 = _at(k_min8, prior) if prior >= 0 else None
    if k8 is not None and features.FULL_WASHOUT_K < k8 <= ic.OVERSOLD:
        return "partial_shallow_washout"
    if features.cap_bucket_of(cap_usd) == "<2B":
        return "_pending_smallcap"          # pass 2 finishes the quintile test
    c_d = float(close.iloc[pos])
    ma = _at(ma200, pos)
    dd_252 = _at(dd252, pos)
    if ma is not None and dd_252 is not None and c_d < ma and dd_252 <= features.DAMAGED_DD_252:
        return "damaged_trend_rebound"
    r120 = _at(ret120, pos)
    if r120 is not None and r120 >= features.LEADER_RET120:
        return "leader_reset"
    return "other"


#: Rows pass 1 could not finish (small-cap momentum needs pass-2 quintiles).
PENDING_SMALLCAP = "_pending_smallcap"


# --------------------------------------------------------------------------- #
# pass 2 — cross-sectional, per (panel, session)
# --------------------------------------------------------------------------- #
def cross_sectionalize(rows: pd.DataFrame) -> pd.DataFrame:
    """Fill the decile/quintile/hot columns CROSS-SECTIONALLY per (panel, session).

    Deterministic by construction: rows are sorted by ticker inside each group and
    ranked with ``method="first"``, so a tie is broken by the lexicographic ticker
    and never by input order.  A group whose feature is entirely missing leaves the
    bucket at :data:`UNRANKED` rather than assigning everyone to the same decile —
    the CEM cell then simply does not match on it, which is visible, and a fake
    uniform decile would not be.

    Returns the panel with :data:`RAW_COLUMNS` dropped and
    ``attrs["session_pos_by_date"]`` attached for ``controls._session_offset``.
    """
    if rows is None or not len(rows):
        out = pd.DataFrame(columns=list(PANEL_COLUMNS))
        out.attrs["session_pos_by_date"] = attach_session_positions(out)
        return out
    frame = rows.copy()
    missing = [c for c in RAW_COLUMNS if c not in frame.columns]
    if missing:
        raise FeaturePanelError(f"cross_sectionalize needs the raw columns {missing}; "
                                f"pass build_feature_rows output, not a trimmed panel")
    keys = ["panel", "session"] if "panel" in frame.columns else ["session"]
    frame = frame.sort_values(keys + ["ticker"], kind="mergesort").reset_index(drop=True)

    frame["proximity_decile"] = _bucket(frame, keys, "raw_proximity", _DECILES)
    frame["dollar_vol_decile"] = _bucket(frame, keys, "raw_dollar_vol", _DECILES)
    frame["ret60_quintile"] = _bucket(frame, keys, "raw_ret60", _QUINTILES)
    frame["vol20_quintile"] = _bucket(frame, keys, "raw_vol20", _QUINTILES)

    relvol_decile = _bucket(frame, keys, "raw_relvol20", _DECILES)
    absret_decile = _bucket(frame, keys, "raw_absret5", _DECILES)
    hot = ((relvol_decile >= prereg.HOT_RELVOL_DECILE)
           | (absret_decile >= prereg.HOT_ABS_RET5_DECILE))
    frame["hot_tier"] = np.where(hot, 1, 0).astype(int)

    pending = frame["cohort"] == PENDING_SMALLCAP
    if pending.any():
        # The law's third leg is "|60d return| quintile 5" — the ABSOLUTE return's
        # top quintile, not an extreme of the signed one.  Ranked separately here
        # and never exported: ``ret60_quintile`` stays the SIGNED matching feature
        # the CEM distance uses, and conflating the two would put a −40% name and a
        # +40% name in the same matching bucket.
        absret60_quintile = _bucket(frame, keys, "raw_absret60", _QUINTILES)
        smallcap = (pending
                    & (frame["vol20_quintile"] == _QUINTILES - 1)
                    & (absret60_quintile == _QUINTILES - 1))
        frame.loc[smallcap, "cohort"] = "smallcap_highvol_momentum"
        frame.loc[pending & ~smallcap, "cohort"] = "other"

    out = frame.drop(columns=[c for c in RAW_COLUMNS if c in frame.columns])
    ordered = list(PANEL_COLUMNS) + (["panel"] if "panel" in out.columns else [])
    out = out[ordered]
    out.attrs["session_pos_by_date"] = attach_session_positions(out)
    return out


def _bucket(frame: pd.DataFrame, keys: list[str], column: str, n: int) -> pd.Series:
    """Cross-sectional 0..n-1 bucket index within each group; UNRANKED where absent.

    ``rank(method="first")`` over the already-ticker-sorted frame, then a floor
    division into ``n`` equal-count buckets.  ``qcut`` is deliberately not used:
    it raises on duplicate edges and silently produces fewer bins on a degenerate
    day, and neither behaviour is acceptable inside a matching cell.
    """
    values = pd.to_numeric(frame[column], errors="coerce")
    out = pd.Series(UNRANKED, index=frame.index, dtype=int)
    for _key, group in frame.groupby(keys, sort=False, dropna=False):
        idx = group.index
        vals = values.loc[idx]
        ok = vals.notna()
        count = int(ok.sum())
        if count == 0:
            continue
        ranks = vals[ok].rank(method="first").to_numpy(dtype=float)
        buckets = np.minimum((ranks - 1.0) * n / count, n - 1).astype(int)
        out.loc[idx[ok.to_numpy()]] = buckets
    return out


def attach_session_positions(panel: pd.DataFrame,
                             calendar: pd.DatetimeIndex | None = None,
                             ) -> "panels.SessionPositions":
    """``{Timestamp: position}`` for ``controls._session_offset``.

    Derived from the panel's own distinct sessions unless a bench ``calendar`` is
    supplied — and it SHOULD be, for anything that will compare offsets across
    names: a panel that happens to hold no rows on a session would otherwise make
    that session invisible to the ±5-session exclusion, quietly admitting a control
    that fired four sessions ago.  ``panels.session_calendar`` is the bench source.

    The returned mapping is a read-only :class:`panels.SessionPositions` (a dict
    subclass) so that riding in ``DataFrame.attrs`` costs nothing: see that class
    for why a plain dict here is measured in CPU-hours.
    """
    from engine.entry_radar.replay import panels  # noqa: PLC0415 — leaf import

    if calendar is not None:
        return panels.session_positions(pd.DatetimeIndex(calendar))
    if panel is None or not len(panel) or "session" not in panel.columns:
        return panels.SessionPositions()
    stamps = pd.DatetimeIndex(sorted({pd.Timestamp(s) for s in panel["session"]}))
    return panels.SessionPositions((ts, pos) for pos, ts in enumerate(stamps))


__all__ = ["PANEL_COLUMNS", "RAW_COLUMNS", "UNRANKED", "PENDING_SMALLCAP",
           "FeaturePanelError", "build_feature_rows", "cross_sectionalize",
           "attach_session_positions"]
