"""Point-in-time market-context legs for Government Revenue shadow packets.

Wave 9E, first half.  This module answers one question for one already-selected
candidate: *what did the tape look like at the moment we could first have known
about this procurement event?*  It never selects, ranks, sizes, or scores.

TWO LAWS GOVERN EVERY LINE HERE
===============================

**Reuse, never rebuild.**  Every number comes from a loader or transform the
boards and Prophet already run.  Nothing in this file reads a price file that
`engine.prophet_stage_inputs` would not read, and nothing computes an indicator
that `engine.stock_technicals` does not already own:

  * price/volume basis  → the two-rung `baskets/ohlcv` → `stocks` union that
    ``prophet_stage_inputs.load_ticker_prices`` resolves (pinned by test);
  * benchmark           → ``prophet_stage_inputs.load_bench_close`` (SPY);
  * trend/vol/RS        → ``stock_technicals.snapshot``, the same per-stock read
    the US standout board ships;
  * liquidity capacity  → ``validation.dollar_adv`` (rolling MEDIAN ADV$);
  * own-history ranks   → ``indicators.expanding_percentile`` (no lookahead);
  * regime              → ``regime_vector.get_vector_for_date`` (PIT by design);
  * Prophet's own state → ``us_context_vector.load_candidates`` (READ-ONLY; that
    store's README fences it at zero authority and we do not move that fence).

**Point-in-time or abstain.**  Every leg is cut at the candidate's ``known_at``:
the latest bar with a timestamp at or before it, never a "latest" read.  A leg
with no usable source says ``missing``; a leg whose source exists but whose
required denominator or clock does not says ``abstained``; a leg whose newest
observation is older than its own SLA says ``stale``.  None of those three is a
zero, and none of them is silently dropped.

A LEG IS A NAMED BAG OF NAMED READINGS
--------------------------------------
There is deliberately no leg-level number.  A leg carries ``readings`` — each
with its own name, value, unit and kind — plus its own clocks, freshness and
provenance.  Nothing here may sum, average, or weight readings across legs into
a single figure: that is the fused super-score the integration ruling forbids
(constitution A7), and `shadow_context` enforces its absence structurally.

TIMEZONE TRAP (measured, load-bearing)
--------------------------------------
`government_revenue.point_in_time.timestamp()` returns tz-AWARE UTC.  Every
price and regime store in this repo carries a tz-NAIVE ``DatetimeIndex``.
Comparing them raises ``TypeError: Invalid comparison between dtype=
datetime64[us] and Timestamp``, so `_naive_cutoff` strips the zone exactly once,
at the boundary, and every slice below uses that value.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd


CONTRACT = "government_revenue_market_context.v1"
SCHEMA_VERSION = "1.0.0"

#: The complete leg-status vocabulary.  ``contradictory`` is set by the packet
#: builder when two legs disagree, never by a leg about itself.
LEG_STATUSES = ("present", "stale", "missing", "abstained", "contradictory")

#: Benchmark for every relative-strength reading — the single house benchmark.
BENCH_TICKER = "SPY"

#: Preference order for the price basis.  Mirrors
#: ``prophet_stage_inputs.load_ticker_prices`` exactly; a test pins the two
#: together so this list can never drift into a second basis.
PRICE_RUNGS = ("baskets/ohlcv", "stocks")

#: Per-leg staleness SLA, in calendar days between the newest usable source
#: observation and ``known_at``.  Prices get a week (a long holiday weekend plus
#: a collector miss); the two derived stores get ten days because they are
#: stamped by a nightly that can legitimately skip.
PRICE_SLA_DAYS = 7.0
REGIME_SLA_DAYS = 10.0
PROPHET_STATE_SLA_DAYS = 10.0

#: Minimum bars before a percentile against a name's own history means anything.
#: Matches ``indicators.expanding_percentile``'s own default.
OWN_HISTORY_MIN_OBS = 252

#: Narrow projection of Prophet's published candidate store.  Reading 153
#: columns to answer "what tier was this name" would cost the render budget for
#: nothing.
_PROPHET_STATE_COLUMNS = (
    "stamp_date",
    "ticker",
    "tier",
    "tier_cascade",
    "gate_state",
    "gate_provisional",
    "ext_z",
    "turnover_pctile_20d",
)


def _r(value: Any, digits: int) -> float | None:
    """Round to a fixed precision so a packet is byte-stable across runs."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    rendered = str(value).strip()
    return rendered or None


def _bool(value: Any) -> bool | None:
    return bool(value) if isinstance(value, (bool,)) else None


def _utc(value: Any) -> datetime | None:
    """Parse anything this repo stores as an instant into tz-aware UTC."""

    if value is None:
        return None
    try:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _naive_cutoff(known_at: Any) -> pd.Timestamp | None:
    """Return the tz-naive UTC instant every price/regime slice compares against.

    The zone is stripped exactly once, here.  See the module docstring: a
    tz-aware candidate clock against a tz-naive store index is a ``TypeError``,
    not a silent miss, so this boundary is the only correct place to normalize.
    """

    moment = _utc(known_at)
    if moment is None:
        return None
    return pd.Timestamp(moment).tz_convert("UTC").tz_localize(None)


def _store_ticker(ticker: str) -> str | None:
    """Dash-normalize a dotted ticker the way every price store on disk is keyed."""

    symbol = _text(ticker)
    if symbol is None:
        return None
    return symbol.upper().replace(".", "-")


def _age_days(source_time: pd.Timestamp | None, cutoff: pd.Timestamp) -> float | None:
    if source_time is None:
        return None
    return _r((cutoff.normalize() - source_time.normalize()).total_seconds() / 86_400.0, 3)


def _freshness(
    source_time: pd.Timestamp | None,
    cutoff: pd.Timestamp,
    *,
    sla_days: float,
) -> tuple[str, dict[str, Any]]:
    """Return ``(status, freshness_block)`` for one leg's newest observation.

    A future-dated source is ``abstained``, not ``present``: a bar stamped after
    the knowledge clock is a leak, and refusing it is cheaper than explaining it.
    """

    age = _age_days(source_time, cutoff)
    if age is None:
        return "missing", {
            "status": "missing",
            "age_days": None,
            "sla_days": _r(sla_days, 3),
        }
    if age < 0:
        return "abstained", {
            "status": "future_source",
            "age_days": age,
            "sla_days": _r(sla_days, 3),
        }
    status = "stale" if age > sla_days else "present"
    return status, {
        "status": status,
        "age_days": age,
        "sla_days": _r(sla_days, 3),
    }


def _reading(name: str, value: Any, *, kind: str, units: str | None = None) -> dict[str, Any]:
    """One named, separately-inspectable measurement inside a leg."""

    return {"name": name, "value": value, "kind": kind, "units": units}


def _leg(
    name: str,
    *,
    status: str,
    readings: Sequence[Mapping[str, Any]] = (),
    reason_code: str | None = None,
    clocks: Mapping[str, Any] | None = None,
    freshness: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in LEG_STATUSES:
        raise ValueError(f"unknown leg status {status!r}")
    return {
        "leg_id": f"market_{name}",
        "leg_family": "market_context",
        "name": name,
        "status": status,
        "reason_code": reason_code,
        "readings": [dict(row) for row in readings],
        "clocks": dict(clocks or {}),
        "freshness": dict(freshness or {}),
        "provenance": dict(provenance or {}),
    }


def _absent_leg(name: str, *, status: str, reason_code: str, known_at: str | None) -> dict[str, Any]:
    return _leg(
        name,
        status=status,
        reason_code=reason_code,
        clocks={"source_time": None, "observed_at": None, "known_at": known_at},
        freshness={"status": status, "age_days": None, "sla_days": None},
    )


# --------------------------------------------------------------------------- #
# the point-in-time price window
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PitPriceWindow:
    """One name's OHLCV history truncated at the candidate knowledge clock.

    ``coverage`` records what the basis actually delivered: ``ohlcv`` when high
    and low survived the rung that answered, ``close_volume`` when the rung has
    no high/low (``data/stocks``), so an ATR-shaped leg abstains by name instead
    of reporting a fabricated zero.
    """

    ticker: str
    store_ticker: str
    close: pd.Series
    volume: pd.Series | None
    high: pd.Series | None
    low: pd.Series | None
    bench_close: pd.Series | None
    rung: str
    coverage: str
    cutoff: pd.Timestamp

    @property
    def source_time(self) -> pd.Timestamp:
        return pd.Timestamp(self.close.index[-1])

    @property
    def bench_source_time(self) -> pd.Timestamp | None:
        if self.bench_close is None or not len(self.bench_close):
            return None
        return pd.Timestamp(self.bench_close.index[-1])


def _read_rung(path: Path) -> pd.DataFrame | None:
    """Read one price rung, mirroring ``prophet_stage_inputs._read_ohlcv``.

    Kept local rather than importing the private symbol, and pinned to the
    public loader by ``test_price_basis_is_the_same_basis_prophet_reads``: the
    public API drops high/low, which an ATR-shaped reading needs, so the extra
    columns are the only reason this exists.
    """

    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path)
    except Exception:  # noqa: BLE001 — an unreadable rung must fall through, not raise
        return None
    if frame is None or frame.empty or "close" not in frame.columns:
        return None
    if not isinstance(frame.index, pd.DatetimeIndex):
        try:
            frame.index = pd.to_datetime(frame.index)
        except Exception:  # noqa: BLE001
            return None
    if getattr(frame.index, "tz", None) is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    return frame.sort_index()


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in frame.columns:
        return None
    series = pd.to_numeric(frame[column], errors="coerce").dropna()
    return series if len(series) else None


def load_pit_window(
    ticker: str,
    known_at: Any,
    *,
    data_root: Path | str,
    bench_ticker: str = BENCH_TICKER,
) -> PitPriceWindow | None:
    """Return the OHLCV window ending at the last bar at or before ``known_at``.

    Fail-open: any missing store, unreadable rung, or empty post-cutoff slice
    returns ``None``, and the caller turns that into a ``missing`` leg with a
    reason code rather than a zero.
    """

    cutoff = _naive_cutoff(known_at)
    store_ticker = _store_ticker(ticker)
    if cutoff is None or store_ticker is None:
        return None
    root = Path(data_root)
    for rung in PRICE_RUNGS:
        frame = _read_rung(root / rung / f"{store_ticker}.parquet")
        if frame is None:
            continue
        window = frame.loc[frame.index <= cutoff]
        close = _numeric(window, "close")
        if close is None:
            continue
        high = _numeric(window, "high")
        low = _numeric(window, "low")
        bench = _pit_bench(root, cutoff, bench_ticker)
        return PitPriceWindow(
            ticker=str(ticker).upper(),
            store_ticker=store_ticker,
            close=close,
            volume=_numeric(window, "volume"),
            high=high,
            low=low,
            bench_close=bench,
            rung=rung,
            coverage="ohlcv" if (high is not None and low is not None) else "close_volume",
            cutoff=cutoff,
        )
    return None


def _pit_bench(root: Path, cutoff: pd.Timestamp, bench_ticker: str) -> pd.Series | None:
    """SPY close truncated at the cutoff, from the one benchmark store."""

    path = root / "yahoo" / f"{_store_ticker(bench_ticker)}.parquet"
    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return None
    if frame is None or frame.empty:
        return None
    column = "close" if "close" in frame.columns else ("close_price" if "close_price" in frame.columns else None)
    if column is None:
        return None
    if not isinstance(frame.index, pd.DatetimeIndex):
        try:
            frame.index = pd.to_datetime(frame.index)
        except Exception:  # noqa: BLE001
            return None
    if getattr(frame.index, "tz", None) is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    series = pd.to_numeric(frame[column], errors="coerce").dropna().sort_index()
    series = series.loc[series.index <= cutoff]
    return series if len(series) else None


def _price_provenance(window: PitPriceWindow, *, loader: str) -> dict[str, Any]:
    return {
        "lobe": "price_store",
        "loader": loader,
        "artifact": f"data/{window.rung}/{window.store_ticker}.parquet",
        "adjustment_basis": "adjusted",
        "coverage": window.coverage,
        "bars_at_known_at": int(len(window.close)),
    }


def _price_clocks(window: PitPriceWindow) -> dict[str, Any]:
    source = window.source_time
    return {
        "source_time": source.date().isoformat(),
        "observed_at": source.date().isoformat(),
        "observed_at_basis": "source_bar_date",
        "known_at": window.cutoff.isoformat(),
    }


# --------------------------------------------------------------------------- #
# the legs
# --------------------------------------------------------------------------- #


def technical_trend_leg(window: PitPriceWindow) -> dict[str, Any]:
    """Trend state at ``known_at`` — the board's own per-stock technical read."""

    from engine.stock_technicals import snapshot  # noqa: PLC0415 — heavy, leg-local

    snap = snapshot(window.close, window.high, window.low, window.volume, window.bench_close)
    status, freshness = _freshness(window.source_time, window.cutoff, sla_days=PRICE_SLA_DAYS)
    readings = [
        _reading("close", _r(snap.get("price"), 4), kind="level", units="usd"),
        _reading("above_50dma", _bool(snap.get("above50")), kind="state"),
        _reading("above_200dma", _bool(snap.get("above200")), kind="state"),
        _reading("gap_vs_50dma", _r(snap.get("pct_vs_50dma"), 3), kind="percent", units="pct"),
        _reading("gap_vs_200dma", _r(snap.get("pct_vs_200dma"), 3), kind="percent", units="pct"),
        _reading("golden_cross", _bool(snap.get("golden")), kind="state"),
        _reading("sma50_slope_up", _bool(snap.get("sma50_slope_up")), kind="state"),
        _reading("rsi_14", _r(snap.get("rsi14"), 3), kind="level"),
        _reading("macd_hist_positive", _bool(snap.get("macd_pos")), kind="state"),
    ]
    return _leg(
        "technical_trend",
        status=status,
        readings=readings,
        clocks=_price_clocks(window),
        freshness=freshness,
        provenance=_price_provenance(window, loader="engine.stock_technicals.snapshot"),
    )


def relative_strength_leg(window: PitPriceWindow) -> dict[str, Any]:
    """Strength against the one house benchmark, cut at the same clock.

    Abstains by name when the benchmark store is absent: an RS reading with no
    benchmark is not a weak reading, it is no reading.
    """

    known_at = window.cutoff.isoformat()
    if window.bench_close is None or len(window.bench_close) < 2:
        leg = _absent_leg(
            "relative_strength",
            status="abstained",
            reason_code="benchmark_series_unavailable_at_known_at",
            known_at=known_at,
        )
        leg["provenance"] = {
            "lobe": "price_store",
            "loader": "engine.government_revenue.market_context._pit_bench",
            "artifact": f"data/yahoo/{BENCH_TICKER}.parquet",
            "benchmark": BENCH_TICKER,
        }
        return leg

    from engine.leader_lifecycle import rs_series, rs_slope  # noqa: PLC0415
    from engine.stock_technicals import snapshot  # noqa: PLC0415

    snap = snapshot(window.close, window.high, window.low, window.volume, window.bench_close)
    rs = rs_series(window.close, window.bench_close)
    slope_63 = None
    if len(rs) > 63:
        slope_63 = _r(rs_slope(rs, 63).iloc[-1], 8)
    bench_source = window.bench_source_time
    # The leg is only as current as its OLDER leg; a fresh name against a stale
    # benchmark is a stale comparison.
    oldest = min(window.source_time, bench_source) if bench_source is not None else window.source_time
    status, freshness = _freshness(oldest, window.cutoff, sla_days=PRICE_SLA_DAYS)
    readings = [
        _reading("rs_1m_vs_bench", _r(snap.get("rs_1m"), 3), kind="percent", units="pct"),
        _reading("rs_3m_vs_bench", _r(snap.get("rs_3m"), 3), kind="percent", units="pct"),
        _reading("rs_6m_vs_bench", _r(snap.get("rs_6m"), 3), kind="percent", units="pct"),
        _reading("rs_ratio", _r(rs.iloc[-1], 8) if len(rs) else None, kind="ratio"),
        _reading("rs_slope_63d", slope_63, kind="ratio"),
    ]
    clocks = _price_clocks(window)
    clocks["benchmark_source_time"] = (
        bench_source.date().isoformat() if bench_source is not None else None
    )
    provenance = _price_provenance(window, loader="engine.leader_lifecycle.rs_series")
    provenance["benchmark"] = BENCH_TICKER
    provenance["benchmark_artifact"] = f"data/yahoo/{BENCH_TICKER}.parquet"
    return _leg(
        "relative_strength",
        status=status,
        readings=readings,
        clocks=clocks,
        freshness=freshness,
        provenance=provenance,
    )


def volatility_liquidity_leg(window: PitPriceWindow) -> dict[str, Any]:
    """Volatility and tradable capacity at ``known_at``.

    ATR is reported only when the answering rung actually carried high/low.  On
    a close-only rung the ATR readings are ``None`` and ``reason_code`` names the
    gap — the volatility readings that survive a close-only basis still ship.
    """

    from engine.stock_technicals import snapshot  # noqa: PLC0415
    from engine.validation import dollar_adv  # noqa: PLC0415

    snap = snapshot(window.close, window.high, window.low, window.volume, window.bench_close)
    adv_median = None
    if window.volume is not None and len(window.volume) > 2:
        aligned = window.volume.reindex(window.close.index).dropna()
        if len(aligned) > 2:
            series = dollar_adv(window.close.reindex(aligned.index), aligned, 21).dropna()
            if len(series):
                adv_median = _r(series.iloc[-1], 2)
    status, freshness = _freshness(window.source_time, window.cutoff, sla_days=PRICE_SLA_DAYS)
    reason: str | None = None
    if window.coverage != "ohlcv":
        reason = "atr_requires_high_low_absent_from_answering_price_rung"
    elif window.volume is None:
        reason = "volume_absent_from_answering_price_rung"
    readings = [
        _reading("realized_vol_20d", _r(snap.get("hv20"), 3), kind="percent", units="pct_annualized"),
        _reading("realized_vol_own_history_percentile", _r(snap.get("hv_pctile"), 3), kind="percentile", units="pct"),
        _reading("atr_14", _r(snap.get("atr14"), 4), kind="level", units="usd"),
        _reading("atr_14_pct_of_price", _r(snap.get("atr_pct"), 3), kind="percent", units="pct"),
        _reading("dollar_volume_20d", _r(snap.get("dollar_vol_20d"), 2), kind="level", units="usd"),
        _reading("dollar_adv_21d_median", adv_median, kind="level", units="usd"),
        _reading("relative_volume", _r(snap.get("rel_volume"), 3), kind="ratio"),
    ]
    return _leg(
        "volatility_liquidity",
        status=status,
        readings=readings,
        reason_code=reason,
        clocks=_price_clocks(window),
        freshness=freshness,
        provenance=_price_provenance(window, loader="engine.validation.dollar_adv"),
    )


def runup_extension_leg(window: PitPriceWindow) -> dict[str, Any]:
    """Run-up and extension as percentiles of the name's OWN history.

    The integration ruling binds this leg specifically: percentiles against the
    name's own history, never absolutes.  Absolute moves ship alongside as
    separately named readings so the percentile can be checked, but the ranked
    readings are the ones that answer "is this already extended".
    """

    from engine.indicators import expanding_percentile  # noqa: PLC0415

    close = window.close
    status, freshness = _freshness(window.source_time, window.cutoff, sla_days=PRICE_SLA_DAYS)
    bars = len(close)
    reason = None if bars >= OWN_HISTORY_MIN_OBS else "own_history_shorter_than_percentile_minimum"

    def _last_pct(series: pd.Series) -> float | None:
        ranked = expanding_percentile(series.dropna(), OWN_HISTORY_MIN_OBS).dropna()
        return _r(ranked.iloc[-1], 6) if len(ranked) else None

    runup_21 = close.pct_change(21, fill_method=None)
    runup_63 = close.pct_change(63, fill_method=None)
    sma50 = close.rolling(50, min_periods=50).mean()
    extension = (close / sma50 - 1.0).replace([float("inf"), float("-inf")], pd.NA).dropna()
    high_252 = close.rolling(252, min_periods=200).max()
    off_high = (close / high_252 - 1.0).dropna()

    readings = [
        _reading("runup_21d", _r(runup_21.iloc[-1] * 100.0 if len(runup_21.dropna()) else None, 3), kind="percent", units="pct"),
        _reading("runup_21d_own_history_percentile", _last_pct(runup_21), kind="percentile", units="fraction"),
        _reading("runup_63d", _r(runup_63.iloc[-1] * 100.0 if len(runup_63.dropna()) else None, 3), kind="percent", units="pct"),
        _reading("runup_63d_own_history_percentile", _last_pct(runup_63), kind="percentile", units="fraction"),
        _reading("extension_vs_50dma", _r(extension.iloc[-1] * 100.0 if len(extension) else None, 3), kind="percent", units="pct"),
        _reading("extension_vs_50dma_own_history_percentile", _last_pct(extension.astype(float)), kind="percentile", units="fraction"),
        _reading("off_52w_high", _r(off_high.iloc[-1] * 100.0 if len(off_high) else None, 3), kind="percent", units="pct"),
    ]
    return _leg(
        "runup_extension",
        status=status,
        readings=readings,
        reason_code=reason,
        clocks=_price_clocks(window),
        freshness=freshness,
        provenance=_price_provenance(window, loader="engine.indicators.expanding_percentile"),
    )


def regime_fit_leg(known_at: Any, *, data_root: Path | str) -> dict[str, Any]:
    """Market regime as it was stamped at or before ``known_at``.

    ``regime_vector.get_vector_for_date`` is PIT-safe by construction and
    carries its own ``staleness_hours`` disclosure, which is carried through
    rather than re-derived.
    """

    cutoff = _naive_cutoff(known_at)
    if cutoff is None:
        return _absent_leg(
            "regime_fit",
            status="missing",
            reason_code="known_at_unparseable",
            known_at=None,
        )
    known_iso = cutoff.isoformat()
    try:
        from engine.regime_vector import get_vector_for_date  # noqa: PLC0415

        vector = get_vector_for_date(cutoff, data_dir=Path(data_root))
    except Exception:  # noqa: BLE001 — an unavailable regime store is a missing leg
        return _absent_leg(
            "regime_fit",
            status="missing",
            reason_code="regime_vector_store_unreadable",
            known_at=known_iso,
        )
    if not isinstance(vector, Mapping) or _text(vector.get("vector_asof")) is None:
        return _absent_leg(
            "regime_fit",
            status="missing",
            reason_code="no_regime_row_at_or_before_known_at",
            known_at=known_iso,
        )
    source_time = pd.Timestamp(str(vector["vector_asof"]))
    status, freshness = _freshness(source_time, cutoff, sla_days=REGIME_SLA_DAYS)
    degraded = vector.get("regime_vector_degraded")
    readings = [
        _reading("quad", _text(vector.get("quad_hard_label")), kind="state"),
        _reading("fused_risk", _text(vector.get("fused_risk_label")), kind="state"),
        _reading("vol_regime", _text(vector.get("vol_regime")), kind="state"),
        _reading("rate_pressure", _text(vector.get("rate_pressure")), kind="state"),
        _reading("risk_radar", _text(vector.get("risk_radar_state")), kind="state"),
        _reading("regime_row_degraded", bool(degraded) if degraded is not None else None, kind="state"),
        _reading("carry_forward_staleness_hours", _r(vector.get("staleness_hours"), 3), kind="level", units="hours"),
    ]
    return _leg(
        "regime_fit",
        status=status,
        readings=readings,
        reason_code="regime_row_self_reported_degraded" if bool(degraded) else None,
        clocks={
            "source_time": source_time.date().isoformat(),
            "observed_at": source_time.date().isoformat(),
            "observed_at_basis": "regime_vector_asof",
            "known_at": known_iso,
        },
        freshness=freshness,
        provenance={
            "lobe": "regime_vector",
            "loader": "engine.regime_vector.get_vector_for_date",
            "artifact": "data/regime/regime_vector.parquet",
            "point_in_time": True,
        },
    )


def prophet_confluence_leg(
    ticker: str,
    known_at: Any,
    *,
    repo_root: Path | str,
) -> dict[str, Any]:
    """Prophet's OWN published technical-confluence state for the name, read-only.

    This leg reads Prophet; it never writes to Prophet and never asks Prophet a
    question about this candidate.  Absence is "not measured", never a negative:
    the store stamps its curated board universe nightly, and a niche government
    contractor may legitimately have no row on any given night.
    """

    cutoff = _naive_cutoff(known_at)
    symbol = _text(ticker)
    if cutoff is None or symbol is None:
        return _absent_leg(
            "prophet_confluence_state",
            status="missing",
            reason_code="known_at_or_ticker_unusable",
            known_at=None if cutoff is None else cutoff.isoformat(),
        )
    known_iso = cutoff.isoformat()
    absent = _absent_leg(
        "prophet_confluence_state",
        status="missing",
        reason_code="no_published_prophet_row_for_ticker_at_or_before_known_at",
        known_at=known_iso,
    )
    absent["provenance"] = {
        "lobe": "us_prophet_rank",
        "loader": "engine.us_context_vector.load_candidates",
        "artifact": "data/us_prophet_rank/candidates/<YYYY-MM>.parquet",
        "access": "read_only",
        "absence_meaning": "not_measured_not_negative",
    }
    try:
        from engine.us_context_vector import load_candidates  # noqa: PLC0415

        months = sorted({
            (cutoff - pd.offsets.MonthBegin(offset)).strftime("%Y-%m")
            if offset else cutoff.strftime("%Y-%m")
            for offset in (0, 1, 2)
        })
        frame = load_candidates(
            Path(repo_root), months=months, columns=list(_PROPHET_STATE_COLUMNS)
        )
    except Exception:  # noqa: BLE001 — an unreadable store is a missing leg
        absent["reason_code"] = "prophet_candidate_store_unreadable"
        return absent
    if not isinstance(frame, pd.DataFrame) or frame.empty or "ticker" not in frame.columns:
        return absent
    rows = frame.loc[frame["ticker"].astype("string").str.upper() == symbol.upper()].copy()
    if rows.empty or "stamp_date" not in rows.columns:
        return absent
    rows["_stamp"] = pd.to_datetime(rows["stamp_date"], errors="coerce")
    rows = rows.loc[rows["_stamp"].notna() & (rows["_stamp"] <= cutoff)]
    if rows.empty:
        return absent
    rows = rows.sort_values("_stamp")
    row = rows.iloc[-1]
    source_time = pd.Timestamp(row["_stamp"])
    status, freshness = _freshness(source_time, cutoff, sla_days=PROPHET_STATE_SLA_DAYS)
    readings = [
        _reading("board_tier", _text(row.get("tier")), kind="state"),
        _reading("tier_cascade", _text(row.get("tier_cascade")), kind="state"),
        _reading("gate_state", _text(row.get("gate_state")), kind="state"),
        _reading("gate_provisional", _bool(bool(row.get("gate_provisional"))) if row.get("gate_provisional") is not None else None, kind="state"),
        _reading("extension_z", _r(row.get("ext_z"), 6), kind="level"),
        _reading("turnover_percentile_20d", _r(row.get("turnover_pctile_20d"), 6), kind="percentile", units="fraction"),
    ]
    return _leg(
        "prophet_confluence_state",
        status=status,
        readings=readings,
        clocks={
            "source_time": source_time.date().isoformat(),
            "observed_at": source_time.date().isoformat(),
            "observed_at_basis": "prophet_stamp_date",
            "known_at": known_iso,
        },
        freshness=freshness,
        provenance={
            "lobe": "us_prophet_rank",
            "loader": "engine.us_context_vector.load_candidates",
            "artifact": f"data/us_prophet_rank/candidates/{source_time.strftime('%Y-%m')}.parquet",
            "access": "read_only",
            "absence_meaning": "not_measured_not_negative",
        },
    )


def budget_theme_leg(
    ticker: str,
    known_at: Any,
    *,
    theme_reader: Callable[[str, Any], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Budget/geopolitical theme relevance — only when an artifact provides it.

    No reader is wired in this wave, so the leg abstains by name.  It exists as
    a named abstention rather than an omission because a silent gap reads as
    "no theme relevance", which is a claim this lobe has not earned.
    """

    cutoff = _naive_cutoff(known_at)
    known_iso = cutoff.isoformat() if cutoff is not None else None
    if theme_reader is None:
        return _absent_leg(
            "budget_theme_relevance",
            status="abstained",
            reason_code="no_reviewed_budget_theme_artifact_wired",
            known_at=known_iso,
        )
    try:
        payload = theme_reader(str(ticker), known_at)
    except Exception:  # noqa: BLE001
        return _absent_leg(
            "budget_theme_relevance",
            status="missing",
            reason_code="budget_theme_reader_failed",
            known_at=known_iso,
        )
    return _external_leg(
        "budget_theme_relevance",
        payload,
        cutoff=cutoff,
        known_iso=known_iso,
        sla_days=REGIME_SLA_DAYS,
        empty_reason="budget_theme_artifact_returned_no_row",
    )


def filings_corroboration_leg(
    ticker: str,
    known_at: Any,
    *,
    filings_reader: Callable[[str, Any], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Filings/transcript corroboration — only when an artifact provides it.

    Same shape and same reasoning as ``budget_theme_leg``: absent evidence is
    disclosed as an abstention, never as an absence of corroboration.
    """

    cutoff = _naive_cutoff(known_at)
    known_iso = cutoff.isoformat() if cutoff is not None else None
    if filings_reader is None:
        return _absent_leg(
            "filings_corroboration",
            status="abstained",
            reason_code="no_reviewed_filings_corroboration_artifact_wired",
            known_at=known_iso,
        )
    try:
        payload = filings_reader(str(ticker), known_at)
    except Exception:  # noqa: BLE001
        return _absent_leg(
            "filings_corroboration",
            status="missing",
            reason_code="filings_reader_failed",
            known_at=known_iso,
        )
    return _external_leg(
        "filings_corroboration",
        payload,
        cutoff=cutoff,
        known_iso=known_iso,
        sla_days=PROPHET_STATE_SLA_DAYS,
        empty_reason="filings_artifact_returned_no_row",
    )


def _external_leg(
    name: str,
    payload: Mapping[str, Any] | None,
    *,
    cutoff: pd.Timestamp | None,
    known_iso: str | None,
    sla_days: float,
    empty_reason: str,
) -> dict[str, Any]:
    """Normalize an injected reader's row into the same leg shape as every other.

    A reader that returns a row with no source clock is ``abstained``, not
    ``present``: the time-consciousness law makes a clockless reading unusable,
    and refusing it here keeps that law in one place.
    """

    if not isinstance(payload, Mapping) or not payload:
        return _absent_leg(name, status="missing", reason_code=empty_reason, known_at=known_iso)
    source_time = _utc(payload.get("source_time") or payload.get("observed_at"))
    if source_time is None or cutoff is None:
        return _absent_leg(
            name,
            status="abstained",
            reason_code="reader_row_carries_no_source_clock",
            known_at=known_iso,
        )
    naive_source = pd.Timestamp(source_time).tz_convert("UTC").tz_localize(None)
    status, freshness = _freshness(naive_source, cutoff, sla_days=sla_days)
    raw_readings = payload.get("readings")
    readings = [
        _reading(
            _text(row.get("name")) or "unnamed",
            row.get("value"),
            kind=_text(row.get("kind")) or "state",
            units=_text(row.get("units")),
        )
        for row in (raw_readings if isinstance(raw_readings, Sequence) else [])
        if isinstance(row, Mapping)
    ]
    if not readings:
        return _absent_leg(name, status="missing", reason_code=empty_reason, known_at=known_iso)
    return _leg(
        name,
        status=status,
        readings=readings,
        reason_code=_text(payload.get("reason_code")),
        clocks={
            "source_time": naive_source.isoformat(),
            "observed_at": naive_source.isoformat(),
            "observed_at_basis": _text(payload.get("observed_at_basis")) or "reader_reported",
            "known_at": known_iso,
        },
        freshness=freshness,
        provenance={
            "lobe": _text(payload.get("lobe")) or "external_reader",
            "loader": _text(payload.get("loader")) or "injected_reader",
            "artifact": _text(payload.get("artifact")),
            "access": "read_only",
        },
    )


def market_context_legs(
    ticker: str,
    known_at: Any,
    *,
    repo_root: Path | str,
    data_root: Path | str | None = None,
    theme_reader: Callable[[str, Any], Mapping[str, Any] | None] | None = None,
    filings_reader: Callable[[str, Any], Mapping[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    """Every market-context leg for one name at one knowledge clock.

    The returned order is fixed so a packet is byte-stable.  A leg is always
    present in the list: a name with no price history returns four ``missing``
    price legs, not a shorter list, because a shorter list reads as "we did not
    look" rather than "we looked and found nothing".
    """

    root = Path(repo_root)
    prices = Path(data_root) if data_root is not None else root / "data"
    cutoff = _naive_cutoff(known_at)
    known_iso = cutoff.isoformat() if cutoff is not None else None
    window = load_pit_window(ticker, known_at, data_root=prices)
    if window is None:
        reason = (
            "known_at_unparseable" if cutoff is None
            else "no_price_bar_at_or_before_known_at_in_any_rung"
        )
        price_legs = [
            _absent_leg(name, status="missing", reason_code=reason, known_at=known_iso)
            for name in (
                "technical_trend",
                "relative_strength",
                "volatility_liquidity",
                "runup_extension",
            )
        ]
    else:
        price_legs = [
            technical_trend_leg(window),
            relative_strength_leg(window),
            volatility_liquidity_leg(window),
            runup_extension_leg(window),
        ]
    return [
        *price_legs,
        regime_fit_leg(known_at, data_root=prices),
        prophet_confluence_leg(ticker, known_at, repo_root=root),
        budget_theme_leg(ticker, known_at, theme_reader=theme_reader),
        filings_corroboration_leg(ticker, known_at, filings_reader=filings_reader),
    ]


__all__ = [
    "BENCH_TICKER",
    "CONTRACT",
    "LEG_STATUSES",
    "OWN_HISTORY_MIN_OBS",
    "PRICE_RUNGS",
    "PRICE_SLA_DAYS",
    "PROPHET_STATE_SLA_DAYS",
    "REGIME_SLA_DAYS",
    "SCHEMA_VERSION",
    "PitPriceWindow",
    "budget_theme_leg",
    "filings_corroboration_leg",
    "load_pit_window",
    "market_context_legs",
    "prophet_confluence_leg",
    "regime_fit_leg",
    "relative_strength_leg",
    "runup_extension_leg",
    "technical_trend_leg",
    "volatility_liquidity_leg",
]
