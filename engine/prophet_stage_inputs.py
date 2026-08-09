"""engine/prophet_stage_inputs.py — the GOVERNED point-in-time inputs for the
Prophet × Stage hold-leash and its forward shadow.

WHY THIS MODULE EXISTS (R0-C, earnings/company-event suite Wave 0).
``engine/prophet_bridge.py`` (production origination) and
``engine/prophet_stage_shadow.py`` (the nightly forward shadow) both used to
``import engine.prophet_stage_fusion`` — a RESEARCH BACKTEST HARNESS — to reach six
small point-in-time primitives. That made a 2022-26 backtest module a live
dependency of nightly plan origination: a split-brain in which a research edit could
move a shipped plan and a production edit could move a frozen research result.

This module owns those primitives. ``prophet_stage_fusion`` now imports them FROM
here and re-exports them, so every published PSF/PSQ result stays reproducible
against identical code while production no longer depends on the harness.

WHAT LIVES HERE. Only inputs — reads and point-in-time lookups. No arm membership,
no win-rate statistics, no bootstrap, no verdicts. Nothing here ranks, sizes, gates,
or scores anything; the leash that consumes these values is owned by
``prophet_bridge`` and its authority is documented there.

THE EARNINGS-CALL SOURCE IS NOT SHIPPED (read this before trusting an EC-negative).
``load_ec_table`` reads ``data/stage_analysis/backfill/earnings_calls.parquet`` — a
one-time local EquityDesk backfill that is gitignored (``.gitignore``: "on CI/deploy
they are absent and every consumer fails-open"), has never been committed, and has no
fetch/publish pair. On every CI and deploy host the file is simply absent, so the EC
join returns an empty table and every EC lookup answers ``None``.

That fail-open is deliberate and stays. What was missing is the DISCLOSURE: a caller
could not tell "this name has no positive earnings call" from "there is no earnings
call data on this host at all". ``resolve_ec_source`` / ``load_ec_table_with_source``
report that difference explicitly so a starved negative is never read as an honest one.

``EC_SENT_GATE = 24`` is calibrated to EquityDesk's 0-100 ``earnings_call_sent``
scale. It is NOT comparable to this repo's own -1..1 ``sentiment`` in
``data/earnings_calls/scores.parquet`` (a different artifact with a sibling name).
Re-pointing this join at another field would silently re-scale a promoted signal's
construction, which is a promotion-gauntlet violation rather than a repair.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from engine import grading, weinstein_stage

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Frozen shared constants. These mirror research/PROPHET_STAGE_FUSION_PREREG.md  #
# §2-§4 and are re-exported by engine.prophet_stage_fusion, so the research      #
# harness and the production leash read ONE definition of each. Changing a value #
# here changes both — it needs a prereg amendment row, not a code review.        #
# --------------------------------------------------------------------------- #
STAGE2 = 2                                 # Weinstein Stage-2 (advancing)
FRESH_WEEKS_MAX = 10                       # §2 B-fresh: weeks_in_stage <= 10
EC_SENT_GATE = 24                          # §2 arm C: earnings_call_sent >= 24 (published gate)
BENCH_TICKER = "SPY"                       # §2 bench

# §3 two ruler parameterizations.
PARAM_CLEAN15_126 = dict(liftoff_mult=grading.LIFTOFF_15, liftoff_horizon=grading.LIFTOFF_HORIZON_126)
PARAM_CLEAN8_21 = dict(liftoff_mult=grading.LIFTOFF_8, liftoff_horizon=grading.LIFTOFF_HORIZON_21)

# §4 forward-metric horizons.
FWD_HORIZONS = (21, 63, 126)

# --------------------------------------------------------------------------- #
# EC source state — the honest-negative / starved-negative split.               #
# --------------------------------------------------------------------------- #
EC_SOURCE_AVAILABLE = "available"
EC_SOURCE_UNAVAILABLE = "unavailable"

EC_ABSENT_REASON = (
    "no earnings-call source on this host — the EquityDesk backfill parquet is "
    "local-only and absent on CI/deploy, so every earnings lookup answers null"
)

_EC_COLUMNS = ["ticker", "call_date", "earnings_call_sent"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _display_path(p: Path) -> str:
    """Repo-relative when possible, so the string is identical on every host and
    safe to publish inside a plan artifact."""
    try:
        return str(Path(p).resolve().relative_to(_repo_root()))
    except Exception:  # noqa: BLE001
        return str(p)


def ec_source_path(ec_path: str | Path | None = None) -> Path:
    """The resolved earnings-call table path (default: the local EquityDesk backfill)."""
    if ec_path is not None:
        return Path(ec_path)
    from lib import config  # noqa: PLC0415
    return config.data_dir() / "stage_analysis" / "backfill" / "earnings_calls.parquet"


def resolve_ec_source(ec_path: str | Path | None = None) -> dict:
    """Existence-only source record — no parquet read, safe to call anywhere.

    Returns ``{"state", "path", "reason"}`` where ``state`` is ``available`` or
    ``unavailable`` and ``reason`` is None when the source is present. This is the
    field that lets a reader tell an honest EC-negative from a starved one.
    """
    try:
        p = ec_source_path(ec_path)
    except Exception as e:  # noqa: BLE001
        return {"state": EC_SOURCE_UNAVAILABLE, "path": None,
                "reason": f"earnings-call source path unresolvable: {e}"}
    rel = _display_path(p)
    if not p.exists():
        return {"state": EC_SOURCE_UNAVAILABLE, "path": rel, "reason": EC_ABSENT_REASON}
    return {"state": EC_SOURCE_AVAILABLE, "path": rel, "reason": None}


def load_ec_table_with_source(
    ec_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict]:
    """``(table, source_record)`` in ONE read.

    The table is the same fail-open frame ``load_ec_table`` has always returned (empty
    on absence or unreadability, never a raise). The record adds ``rows`` and downgrades
    ``state`` to ``unavailable`` when a present file could not be read.
    """
    source = resolve_ec_source(ec_path)
    if source["state"] == EC_SOURCE_UNAVAILABLE:
        log.warning("psi: earnings_calls parquet absent (%s) — EC join degrades to n=0",
                    source["path"])
        return pd.DataFrame(columns=_EC_COLUMNS), {**source, "rows": 0}

    p = ec_source_path(ec_path)
    try:
        df = pd.read_parquet(p, columns=["document_ticker", "call_date", "earnings_call_sent"])
    except Exception as e:  # noqa: BLE001
        log.warning("psi: earnings_calls unreadable (%s) — EC join degrades to n=0", e)
        return pd.DataFrame(columns=_EC_COLUMNS), {
            "state": EC_SOURCE_UNAVAILABLE,
            "path": source["path"],
            "reason": f"earnings-call source unreadable: {e}",
            "rows": 0,
        }

    out = pd.DataFrame({
        "ticker": df["document_ticker"].astype(str),
        "call_date": pd.to_datetime(df["call_date"], errors="coerce"),
        "earnings_call_sent": pd.to_numeric(df["earnings_call_sent"], errors="coerce"),
    }).dropna(subset=["call_date"])
    out = out.sort_values("call_date").reset_index(drop=True)
    return out, {**source, "rows": int(len(out))}


def load_ec_table(ec_path: str | Path | None = None) -> pd.DataFrame:
    """Load the earnings-call backfill table, or an EMPTY frame if absent (fail-open, §5).

    Columns kept: ticker (from ``document_ticker``), call_date (datetime),
    earnings_call_sent. When the local gitignored parquet is missing, returns an empty
    frame so arm C simply yields n=0 (the harness must degrade, never crash — the
    fail-open-on-absent-EC test). Callers that need to DISCLOSE the absence should use
    ``load_ec_table_with_source`` instead of inferring it from an empty frame.
    """
    return load_ec_table_with_source(ec_path)[0]


def ec_sent_at_entry(ec_by_ticker: dict[str, pd.DataFrame], ticker: str, entry_date) -> float | None:
    """Most-recent ``earnings_call_sent`` with ``call_date < entry_date`` for ``ticker``.

    STRICTLY-BEFORE (call_date < entry_date, §7 look-ahead control): a call printed on the
    entry day itself is NOT usable (its sentiment would not be known pre-fill). Returns None
    when the ticker has no prior call (arm C then excludes the fire). Never raises.
    """
    g = ec_by_ticker.get(str(ticker))
    if g is None or g.empty:
        return None
    ed = pd.Timestamp(entry_date)
    prior = g[g["call_date"] < ed]
    if prior.empty:
        return None
    v = prior["earnings_call_sent"].iloc[-1]  # g is call_date-sorted → last is most-recent
    return float(v) if pd.notna(v) else None


def ec_index(ec_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{ticker -> call_date-sorted frame} for fast per-fire most-recent lookup."""
    if ec_df is None or ec_df.empty:
        return {}
    out: dict[str, pd.DataFrame] = {}
    for tk, g in ec_df.groupby("ticker"):
        out[str(tk)] = g.sort_values("call_date").reset_index(drop=True)
    return out


# --------------------------------------------------------------------------- #
# PIT stage lookup at an entry date (look-ahead-safe).                          #
# --------------------------------------------------------------------------- #
def stage_at_entry(close: pd.Series, volume: pd.Series | None,
                   bench_close: pd.Series, entry_date) -> tuple[int, int, int]:
    """PIT (stage, weeks_in_stage, n_completed_weeks) at ``entry_date``.

    LOOK-AHEAD GUARD (§7): inputs are TRUNCATED to the entry bar — the close (and bench,
    and volume) are sliced to ``<= entry_date`` before classification, so the weekly stage
    can only see completed weeks on-or-before the entry. Returns (0, 0, n_weeks) for a
    too-young name (< 45 completed weeks). Never raises.
    """
    try:
        ed = pd.Timestamp(entry_date)
        c = close[close.index <= ed]
        v = volume[volume.index <= ed] if volume is not None and len(volume) else None
        b = bench_close[bench_close.index <= ed] if bench_close is not None and len(bench_close) else bench_close
        res = weinstein_stage.classify(c, v, b)
        return int(res.get("stage", 0) or 0), int(res.get("weeks_in_stage", 0) or 0), int(res.get("n_weeks", 0) or 0)
    except Exception as e:  # noqa: BLE001
        log.warning("psi: stage_at_entry failed (%s)", e)
        return 0, 0, 0


# --------------------------------------------------------------------------- #
# Price loaders (§2 union: baskets/ohlcv ∪ data/stocks; bench = data/yahoo/SPY). #
# --------------------------------------------------------------------------- #
def _read_ohlcv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty or "close" not in df.columns:
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:  # noqa: BLE001
            return None
    return df


def load_ticker_prices(ticker: str, data_root: Path) -> tuple[pd.Series | None, pd.Series | None]:
    """(close, volume) daily series for a ticker, preferring baskets/ohlcv then data/stocks
    (the §2 union; the deep stocks store extends late-IPO history). Fail-open → (None, None)."""
    for sub in ("baskets/ohlcv", "stocks"):
        p = Path(data_root) / sub / f"{ticker}.parquet"
        if not p.exists():
            continue
        df = _read_ohlcv(p)
        if df is None:
            continue
        close = df["close"].dropna()
        vol = df["volume"].dropna() if "volume" in df.columns else None
        if len(close):
            return close, vol
    return None, None


def load_bench_close(data_root: Path) -> pd.Series | None:
    """SPY daily close (data/yahoo/SPY.parquet) — the single §2 benchmark. Fail-open → None."""
    p = Path(data_root) / "yahoo" / f"{BENCH_TICKER}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else ("close_price" if "close_price" in df.columns else None)
    if col is None:
        return None
    s = df[col].dropna()
    return s if len(s) else None
