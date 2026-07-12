"""China Pick Lab asia-lane runner (spec §6, CNPL-R8).

Steps
-----
(a) Load latest CN snapshot via engine.pick_lab.snapshot.latest_snapshot(profile=CN_PROFILE);
    if none, log honest no-op and return 0 (first night after build_china_library runs).
(b) ENRICHMENT JOIN: fill cycle_phase, participation_regime, participation_risk,
    policy_impulse, qvix_z from site/chinastatedata/*.json; enrich per-name limit_state,
    fillable, chase_veto, t_plus_one_risk from microstructure name_packets; join THS
    basket membership/breadth from site/chinabasketdata/baskets_ths.json (null-honest
    when absent). Persist enriched frame (upsert mode) via CN_PROFILE.
(c) Run all 20 CN books + flagship2_mirror via cn.run_book_cn; apply 21-session refire
    lockout from the CN ledger; append fires with CN stamps (board, limit_state,
    fillable, cycle_phase, participation_regime, policy_impulse, qvix_z, config_hash).
    sealed_up fires are logged but NOT appended (skipped_unfillable counter, CNPL-R4).
(d) GRADE PASS (CNPL-R4): (H+L)/2 fills from data/china_stocks_raw/<ticker>.parquet
    (fill_basis='hl2'); fallback to close (fill_basis='close') when raw OHLC absent.
    CSI 300 excess via CN_PROFILE.benchmark_loader. Only fired tickers loaded from raw
    store — never a full-universe scan. Absolute return recorded alongside.
(e) Scoreboard via book.all_scoreboards(profile=CN_PROFILE); write site/labdata/china_pick_lab.json.
(f) Render via engine.pick_lab.render_cn.

CNPL-R8: CN_LANE=asia env gate for ALL ledger/data writes. Non-asia = honest no-op.
Always exits 0 (CNPL-R8 never-break).
Authority: display_only throughout (CNPL-R1).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from lib import config

log = logging.getLogger("build_china_pick_lab")

# ------------------------------------------------------------------ constants ---

# Lane gate: ALL ledger and data writes require CN_LANE=asia (CNPL-R8)
_CN_LANE = os.environ.get("CN_LANE", "")
_IS_ASIA_LANE = _CN_LANE == "asia"

# Output paths
_LABDATA_DIR = Path("site") / "labdata"
_CN_PICK_LAB_JSON = _LABDATA_DIR / "china_pick_lab.json"

# Raw OHLC store: per-ticker parquet files
# Data/china_stocks_raw/<ticker>.parquet  (columns: open, close, high, low, volume)
_RAW_STORE_DIR = Path("data") / "china_stocks_raw"

# chinastatedata artifact paths
_CHINA_STATE_DIR = Path("site") / "chinastatedata"

# THS basket data
_THS_BASKETS_PATH = Path("site") / "chinabasketdata" / "baskets_ths.json"

# CSI 300 benchmark ticker
_CSI300_TICKER = "510300.SS"

# Max recent fires to include per book in the site payload
_RECENT_FIRES_PER_BOOK = 30


# ------------------------------------------------------------------ state loaders ---


def _load_cycle_phase() -> dict:
    """Load site/chinastatedata/cycle_phase.json; return {} on failure."""
    p = config.ROOT / _CHINA_STATE_DIR / "cycle_phase.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("cn_pick_lab: cycle_phase.json unreadable (%s)", exc)
        return {}


def _load_participation() -> dict:
    """Load site/chinastatedata/participation.json; return {} on failure."""
    p = config.ROOT / _CHINA_STATE_DIR / "participation.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("cn_pick_lab: participation.json unreadable (%s)", exc)
        return {}


def _load_policy_transmission() -> dict:
    """Load site/chinastatedata/policy_transmission.json; return {} on failure."""
    p = config.ROOT / _CHINA_STATE_DIR / "policy_transmission.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("cn_pick_lab: policy_transmission.json unreadable (%s)", exc)
        return {}


def _load_microstructure() -> dict:
    """Load site/chinastatedata/microstructure.json; return {} on failure."""
    p = config.ROOT / _CHINA_STATE_DIR / "microstructure.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("cn_pick_lab: microstructure.json unreadable (%s)", exc)
        return {}


def _load_ths_baskets() -> dict:
    """Load site/chinabasketdata/baskets_ths.json; return {} on failure (null-honest per CNPL-R9)."""
    p = config.ROOT / _THS_BASKETS_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("cn_pick_lab: baskets_ths.json unreadable (%s) — THS basket context absent", exc)
        return {}


# ------------------------------------------------------------------ enrichment ---


def _build_ths_membership(ths_data: dict) -> dict[str, dict]:
    """Return {ticker: {theme_basket, theme_breadth_pct, theme_member_ret21_rank}} from THS data.

    For each member of each basket: assign the basket with the best (highest) 20d return
    as the 'theme_basket'.  theme_breadth_pct = basket's 20d breadth proxy (n_members_up / n).
    theme_member_ret21_rank = member's ret_20d rank within the basket (0..1, lower = better performer).

    Null-honest: tickers with no basket membership receive no entry in the result dict.
    """
    baskets = ths_data.get("baskets") or []
    # {ticker: {basket_name, perf_20d, n_members, member_ret_rank}}
    best_by_ticker: dict[str, dict] = {}

    for basket in baskets:
        basket_name = basket.get("name") or basket.get("id") or ""
        perf = basket.get("perf") or {}
        basket_ret_20d = perf.get("20d")  # float or None
        members = basket.get("members") or []
        n = len(members)
        if n == 0:
            continue

        # Breadth proxy: percentage of members with positive 20d return (0..100 scale).
        # The book config uses theme_breadth_pct_min=80.0 (percent), so multiply by 100
        # here so that enrichment and book thresholds agree on the same scale.
        n_positive = sum(1 for m in members if isinstance(m.get("ret_20d"), (int, float)) and m["ret_20d"] > 1.0)
        breadth_pct = (n_positive / n * 100.0) if n > 0 else None

        # Rank members by ret_20d within this basket (ascending: lower = weaker performer = laggard).
        # Emit rank as a percentile on 0..100 scale to match book threshold le(50).
        member_rets = [(m.get("symbol", ""), m.get("ret_20d")) for m in members]
        ranked = sorted(member_rets, key=lambda x: float(x[1]) if isinstance(x[1], (int, float)) else 0.0)
        rank_by_ticker: dict[str, float] = {
            sym: (i / max(n - 1, 1) * 100.0) for i, (sym, _) in enumerate(ranked)
        }

        for member in members:
            sym = member.get("symbol", "")
            if not sym:
                continue
            ret_20d = member.get("ret_20d")
            cur = best_by_ticker.get(sym)
            # Keep the basket whose 20d performance is highest (most active theme)
            if cur is None or (
                isinstance(basket_ret_20d, (int, float)) and
                (cur.get("basket_ret_20d") is None or basket_ret_20d > cur["basket_ret_20d"])
            ):
                best_by_ticker[sym] = {
                    "theme_basket": basket_name,
                    "theme_breadth_pct": breadth_pct,
                    "theme_member_ret21_rank": rank_by_ticker.get(sym),
                    "basket_ret_20d": basket_ret_20d,
                }

    # Strip internal field
    result: dict[str, dict] = {}
    for ticker, v in best_by_ticker.items():
        result[ticker] = {
            "theme_basket": v["theme_basket"],
            "theme_breadth_pct": v["theme_breadth_pct"],
            "theme_member_ret21_rank": v["theme_member_ret21_rank"],
        }
    return result


def _build_microstructure_by_ticker(ms: dict) -> dict[str, dict]:
    """Return {ticker: {limit_state, fillable, chase_veto, t_plus_one_risk}} from microstructure."""
    name_packets = ms.get("name_packets") or []
    result: dict[str, dict] = {}
    for pkt in name_packets:
        ticker = pkt.get("ticker", "")
        if not ticker:
            continue
        cv = pkt.get("chase_veto") or {}
        result[ticker] = {
            "limit_state": pkt.get("limit_state"),
            "fillable": pkt.get("fillable"),
            "chase_veto": bool(cv.get("flag")) if isinstance(cv, dict) else bool(cv),
            "t_plus_one_risk": pkt.get("t_plus_one_risk"),
        }
    return result


def _enrich_snapshot(
    snap: pd.DataFrame,
    cycle: dict,
    participation: dict,
    policy: dict,
    ms_by_ticker: dict[str, dict],
    ths_by_ticker: dict[str, dict],
) -> pd.DataFrame:
    """Fill regime scalars + per-ticker limit/THS context onto the snapshot DataFrame.

    Enrichment is ADDITIVE (PL-R7 pattern): a join failure leaves the column null.
    Existing non-null snapshot values are not overwritten (snapshot producer may have
    set them already; enrichment fills gaps only).
    """
    df = snap.copy()

    # ---- Regime scalars (broadcast to all rows) ----------------------------
    cycle_phase: Optional[str] = cycle.get("phase")
    participation_regime: Optional[str] = (participation.get("regime") or {}).get("name") if isinstance(participation.get("regime"), dict) else participation.get("regime")
    participation_risk: Optional[str] = participation.get("risk")
    policy_impulse: Optional[str] = policy.get("policy_impulse")
    qvix_z_val: Optional[float] = participation.get("qvix_z")

    scalar_map = {
        "cycle_phase": cycle_phase,
        "participation_regime": participation_regime,
        "participation_risk": participation_risk,
        "policy_impulse": policy_impulse,
        "qvix_z": qvix_z_val,
    }
    for col, val in scalar_map.items():
        if val is None:
            continue
        if col not in df.columns:
            df[col] = val
        else:
            null_mask = df[col].isna()
            if null_mask.any():
                df.loc[null_mask, col] = val

    # ---- Per-ticker limit/execution context from microstructure ------------
    if ms_by_ticker:
        for col in ("limit_state", "fillable", "chase_veto", "t_plus_one_risk"):
            if col not in df.columns:
                df[col] = None
            col_ser = pd.Series(
                {t: ms_by_ticker[t][col] for t in df.index if t in ms_by_ticker},
                dtype=object,
            )
            # Only fill rows where both the new series has a value and the existing is null
            for ticker in col_ser.index:
                if ticker in df.index and (df.at[ticker, col] is None or pd.isna(df.at[ticker, col])):
                    df.at[ticker, col] = col_ser[ticker]

    # ---- Per-ticker THS basket context ------------------------------------
    if ths_by_ticker:
        for col in ("theme_basket", "theme_breadth_pct", "theme_member_ret21_rank"):
            if col not in df.columns:
                df[col] = None
            for ticker in df.index:
                if ticker in ths_by_ticker:
                    if df.at[ticker, col] is None or (not isinstance(df.at[ticker, col], str) and pd.isna(df.at[ticker, col])):
                        df.at[ticker, col] = ths_by_ticker[ticker].get(col)

    return df


# ------------------------------------------------------------------ fill price (CNPL-R4) ---


def _load_ticker_raw_closes(ticker: str, raw_dir: Path) -> pd.DataFrame:
    """Load the per-ticker raw OHLC parquet; return empty DataFrame on failure."""
    p = raw_dir / f"{ticker}.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as exc:
        log.debug("cn_pick_lab: raw OHLC for %s unreadable (%s)", ticker, exc)
        return pd.DataFrame()


def _exec_price_cn(
    ticker: str,
    fire_date: pd.Timestamp,
    date_index: pd.DatetimeIndex,
    raw_dir: Path,
) -> tuple[Optional[float], str]:
    """Return (exec_price, fill_basis) for a CN fire.

    CNPL-R4:
      exec_date  = next trading session AFTER fire_date (from date_index)
      fill price = (H+L)/2 from data/china_stocks_raw/<ticker>.parquet (fill_basis='hl2')
      fallback   = exec-session close from same file (fill_basis='close')
      fallback2  = None when raw file absent (fill_basis='unavailable')
    """
    future = date_index[date_index > fire_date]
    if len(future) == 0:
        return None, "unavailable"
    exec_date = future[0]

    raw = _load_ticker_raw_closes(ticker, raw_dir)
    if raw.empty:
        return None, "unavailable"

    raw_index = pd.DatetimeIndex(raw.index)
    if exec_date not in raw_index:
        return None, "unavailable"

    row = raw.loc[exec_date]
    h = row.get("high") if hasattr(row, "get") else row["high"] if "high" in raw.columns else None
    lo = row.get("low") if hasattr(row, "get") else row["low"] if "low" in raw.columns else None
    cl = row.get("close") if hasattr(row, "get") else row["close"] if "close" in raw.columns else None

    try:
        h_f = float(h) if h is not None and not pd.isna(h) else None
        lo_f = float(lo) if lo is not None and not pd.isna(lo) else None
    except (TypeError, ValueError):
        h_f = lo_f = None

    if h_f is not None and lo_f is not None:
        return round((h_f + lo_f) / 2.0, 4), "hl2"

    try:
        cl_f = float(cl) if cl is not None and not pd.isna(cl) else None
    except (TypeError, ValueError):
        cl_f = None

    if cl_f is not None:
        return cl_f, "close"

    return None, "unavailable"


# ------------------------------------------------------------------ fire pass ---


def _fire_all_cn_books(
    snap: pd.DataFrame,
    asof: str,
    fires_existing: list[dict],
    trading_dates: pd.DatetimeIndex,
    reversion_desk_rows: list[dict],
) -> tuple[list[dict], int]:
    """Run all 20 CN books + flagship2_mirror; apply refire lockout.

    Returns (new_entry_fires, skipped_unfillable_count).

    CNPL-R4: fires stamped sealed_up at fire close are counted in skipped_unfillable
    and NOT appended to the ledger.
    CNPL-R8: only writes if CN_LANE=asia; if not, returns empty list + 0.
    """
    if not _IS_ASIA_LANE:
        log.info("cn_pick_lab: CN_LANE!='asia' — fire pass is a no-op (CNPL-R8)")
        return [], 0

    from engine.pick_lab.cn import run_book_cn
    from engine.pick_lab.ledger import is_open
    from engine.pick_lab.registry_cn import CN_REGISTRY, FLAGSHIP2_MIRROR_ID

    new_fires: list[dict] = []
    skipped_unfillable = 0

    snap_with_asof = snap.copy()
    snap_with_asof.attrs["asof"] = asof

    # Build flagship2_mirror picks from the reversion desk rows (§4)
    f2_picks: list[dict] = []
    for i, row in enumerate(reversion_desk_rows or [], 1):
        ticker = row.get("ticker", "")
        if ticker:
            f2_picks.append({
                "ticker": ticker,
                "rank": i,
                "close": row.get("close"),
                "sector": row.get("sector"),
                "board": None,
                "liq_unknown": False,
                "why": ["flagship2_mirror"],
                "features": {"score": row.get("score")},
                "authority": "display_only",
            })

    # CN_REGISTRY books + synthetic flagship2_mirror entry
    _FLAGSHIP2_BOOK = {
        "engine_id": FLAGSHIP2_MIRROR_ID,
        "refire_lockout_sessions": 21,
        "config_hash": "flagship2_mirror",
    }

    all_books_iter = list(CN_REGISTRY) + [None]  # None = flagship2 sentinel

    for book_or_none in all_books_iter:
        is_f2 = book_or_none is None
        if is_f2:
            book = _FLAGSHIP2_BOOK
            picks_raw = f2_picks
            data_gap = False
        else:
            book = book_or_none
            result = run_book_cn(book, snap_with_asof)
            picks_raw = result.get("picks") or []
            data_gap = result.get("data_gap", False)

        engine_id = book["engine_id"]
        lockout = book["refire_lockout_sessions"]

        for pick in picks_raw:
            ticker = pick.get("ticker")
            if not ticker:
                continue

            # Refire lockout check (CNPL-R4)
            if is_open(engine_id, ticker, trading_dates, fires_existing, lockout):
                log.debug("cn_pick_lab: %s/%s lockout — skip fire", engine_id, ticker)
                continue

            # CNPL-R4: sealed_up fires are excluded from the ledger (skipped_unfillable counter)
            # The snap may have limit_state per ticker; check it
            limit_state = None
            fillable = True
            if not is_f2 and "limit_state" in snap.columns and ticker in snap.index:
                limit_state = snap.at[ticker, "limit_state"]
                # Explicit guard: only read fillable when the column exists and has a value
                if "fillable" in snap.columns:
                    raw_fillable = snap.at[ticker, "fillable"]
                    if raw_fillable is not None and not pd.isna(raw_fillable):
                        fillable = bool(raw_fillable)
                    else:
                        fillable = limit_state != "sealed_up" if limit_state is not None else True
                else:
                    # fillable column absent — infer from limit_state
                    fillable = limit_state != "sealed_up" if limit_state is not None else True

            if not fillable or limit_state == "sealed_up":
                log.debug(
                    "cn_pick_lab: %s/%s sealed_up at fire close — excluded (CNPL-R4)",
                    engine_id, ticker,
                )
                skipped_unfillable += 1
                continue

            # Stamp CN-specific fields from snapshot
            def _snap_val(col: str, default=None):
                if col in snap.columns and ticker in snap.index:
                    v = snap.at[ticker, col]
                    try:
                        if not isinstance(v, str) and pd.isna(v):
                            return None
                    except Exception:
                        pass
                    return v
                return default

            fire_row: dict = {
                "engine_id": engine_id,
                "ticker": ticker,
                "fire_date": asof,
                "exec_date": None,       # filled at grade time
                "rank": pick.get("rank"),
                "close_at_fire": pick.get("close"),
                "sector": pick.get("sector"),
                "board": pick.get("board") or _snap_val("board"),
                "why": pick.get("why") or [],
                "features": pick.get("features") or {},
                "liq_unknown": bool(pick.get("liq_unknown")),
                "data_gap": bool(data_gap),
                # CN stamps (CNPL-R4 + spec §5)
                "limit_state": limit_state or _snap_val("limit_state"),
                "limit_width": _snap_val("limit_width"),
                "fillable": bool(fillable),
                "t_plus_one_risk": _snap_val("t_plus_one_risk"),
                "cycle_phase": _snap_val("cycle_phase"),
                "participation_regime": _snap_val("participation_regime"),
                "policy_impulse": _snap_val("policy_impulse"),
                "qvix_z": _snap_val("qvix_z"),
                "config_hash": book["config_hash"],
                "authority": "display_only",
            }

            new_fires.append(fire_row)
            fires_existing.append(fire_row)   # so later books see this fire for lockout

    log.info(
        "cn_pick_lab: fires this run — %d new, %d sealed_up excluded",
        len(new_fires), skipped_unfillable,
    )
    return new_fires, skipped_unfillable


# ------------------------------------------------------------------ grade pass ---


def _cn_grade_pass(
    fires: list[dict],
    grades_existing: list[dict],
    asof: str,
    raw_dir: Path,
) -> int:
    """Grade matured CN fires per CNPL-R4.

    Only loads raw OHLC for FIRED tickers (never full-universe scan).
    fill_basis stamped per fire (hl2 or close).
    CSI 300 benchmark loaded via CN_PROFILE.benchmark_loader.
    Absolute return recorded alongside CSI 300 excess.

    Returns count of new grade rows written.
    """
    if not _IS_ASIA_LANE:
        log.info("cn_pick_lab: CN_LANE!='asia' — grade pass is a no-op (CNPL-R8)")
        return 0

    from engine.pick_lab.grade import ENTRY_HORIZONS, _NOT_YET_ELAPSED
    from engine.pick_lab.ledger import GRADE_KEY, append_grades
    from engine.pick_lab.profile import CN_PROFILE

    # Load CSI 300 benchmark
    csi300: Optional[pd.Series] = None
    try:
        loader = CN_PROFILE.benchmark_loader
        if callable(loader):
            csi300 = loader()
    except Exception as exc:
        log.warning("cn_pick_lab: CSI 300 benchmark load failed (%s) — excess returns will be null", exc)

    # Build existing-grade key set for keep-first dedup
    already_graded: set[tuple] = {
        tuple(g.get(f) for f in GRADE_KEY) for g in grades_existing
    }

    # Fired tickers — load raw OHLC only for them
    fired_tickers = {f.get("ticker", "") for f in fires if f.get("ticker")}
    raw_by_ticker: dict[str, pd.DataFrame] = {}
    for ticker in fired_tickers:
        raw = _load_ticker_raw_closes(ticker, raw_dir)
        if not raw.empty:
            raw.index = pd.DatetimeIndex(raw.index)
            raw_by_ticker[ticker] = raw

    # Build a unified date index from all available raw OHLC dates
    all_dates: set[pd.Timestamp] = set()
    for df in raw_by_ticker.values():
        all_dates.update(df.index)
    if csi300 is not None:
        all_dates.update(csi300.index)
    date_index = pd.DatetimeIndex(sorted(all_dates))

    graded_at = datetime.now(tz=timezone.utc).isoformat()
    new_grades: list[dict] = []

    for fire in fires:
        engine_id = fire.get("engine_id", "")
        ticker = str(fire.get("ticker", ""))
        fire_date_raw = fire.get("fire_date")

        try:
            fire_date = pd.Timestamp(fire_date_raw)
        except Exception:
            continue

        # Exec date = next trading session after fire_date
        future = date_index[date_index > fire_date]
        if len(future) == 0:
            continue
        exec_date = future[0]

        # exec_price via hl2 fill (CNPL-R4)
        exec_price: Optional[float] = None
        fill_basis: str = "unavailable"

        raw_df = raw_by_ticker.get(ticker)
        if raw_df is not None and not raw_df.empty:
            exec_price, fill_basis = _exec_price_cn(ticker, fire_date, date_index, raw_dir)

        if exec_price is None:
            log.debug("cn_pick_lab: grade — %s/%s no exec_price at %s; skip", engine_id, ticker, exec_date)
            continue

        # Use the ticker's own trading calendar for horizon counting so that
        # halts/gaps in other tickers don't misalign the 'h sessions' count.
        ticker_index = raw_df.index if raw_df is not None and not raw_df.empty else date_index

        for h in ENTRY_HORIZONS:
            grade_key = (engine_id, ticker, str(fire_date.date()), h)
            if grade_key in already_graded:
                continue

            # Price at exec + h sessions (counted on this ticker's own session calendar)
            if raw_df is None or raw_df.empty:
                continue

            exec_pos_arr = ticker_index.searchsorted(exec_date, side="left")
            exec_pos = int(exec_pos_arr)
            target_pos = exec_pos + h
            if target_pos >= len(ticker_index):
                continue  # not yet elapsed

            target_date = ticker_index[target_pos]
            close_h: Optional[float] = None
            if "close" in raw_df.columns and target_date in raw_df.index:
                try:
                    val = raw_df.at[target_date, "close"]
                    close_h = float(val) if not pd.isna(val) else None
                except Exception:
                    pass

            if close_h is None:
                continue  # elapsed but price unavailable

            ret_abs = (close_h - exec_price) / exec_price

            # CSI 300 excess
            ret_excess: Optional[float] = None
            if csi300 is not None:
                try:
                    if exec_date in csi300.index and target_date in csi300.index:
                        csi_exec = float(csi300[exec_date])
                        csi_h = float(csi300[target_date])
                        if csi_exec and csi_h:
                            ret_excess = ret_abs - (csi_h - csi_exec) / csi_exec
                except Exception:
                    pass

            row: dict = {
                "engine_id": engine_id,
                "ticker": ticker,
                "fire_date": str(fire_date.date()),
                "horizon": h,
                "exec_date": str(exec_date.date()),
                "exec_price": round(exec_price, 4),
                "fill_basis": fill_basis,
                "ret_abs": round(ret_abs, 6),
                "ret_excess_spy": round(ret_excess, 6) if ret_excess is not None else None,
                "benchmark_ticker": _CSI300_TICKER,
                "matured": True,
                "graded_at": graded_at,
                "authority": "display_only",
            }
            new_grades.append(row)
            already_graded.add(grade_key)

    if new_grades:
        from engine.pick_lab.profile import CN_PROFILE
        written = append_grades(new_grades, hold_thesis=False, profile=CN_PROFILE)
        log.info("cn_pick_lab: wrote %d new grade rows", written)
        return written

    log.info("cn_pick_lab: no new grades this run")
    return 0


# ------------------------------------------------------------------ site payload ---


def _build_recent_fires_with_grades(
    fires: list[dict],
    grades: list[dict],
    engine_id: str,
    n: int = _RECENT_FIRES_PER_BOOK,
) -> list[dict]:
    """Return N most recent fires for engine_id with h=21 grade attached if matured."""
    my_fires = sorted(
        [f for f in fires if f.get("engine_id") == engine_id],
        key=lambda x: x.get("fire_date", ""),
        reverse=True,
    )[:n]

    grade_map: dict[tuple, dict] = {}
    for g in grades:
        if g.get("engine_id") != engine_id:
            continue
        k = (g.get("ticker"), g.get("fire_date"))
        h = g.get("horizon")
        if k not in grade_map or h == 21:
            grade_map[k] = g

    result = []
    for f in my_fires:
        k = (f.get("ticker"), f.get("fire_date"))
        g = grade_map.get(k)
        row = dict(f)
        if g:
            row["ret21_excess"] = g.get("ret_excess_spy")
            row["ret21_abs"] = g.get("ret_abs")
            row["matured"] = bool(g.get("matured"))
        else:
            row["ret21_excess"] = None
            row["ret21_abs"] = None
            row["matured"] = False
        result.append(row)
    return result


def _picks_today(fires: list[dict], asof: str) -> dict[str, list[dict]]:
    """Return {engine_id: [pick dicts]} for today's fires."""
    result: dict[str, list[dict]] = {}
    for f in fires:
        if f.get("fire_date") != asof:
            continue
        eid = f.get("engine_id", "")
        result.setdefault(eid, []).append(f)
    return result


def _build_cn_site_payload(
    asof: str,
    scoreboards: list[dict],
    fires: list[dict],
    grades: list[dict],
    skipped_unfillable: int,
) -> dict:
    """Build the dict written to site/labdata/china_pick_lab.json."""
    from engine.pick_lab.registry_cn import CN_REGISTRY, FLAGSHIP2_MIRROR_ID

    picks_today_by_book = _picks_today(fires, asof)

    # All books (CN_REGISTRY + flagship2_mirror) for the payload
    all_book_ids = [b["engine_id"] for b in CN_REGISTRY] + [FLAGSHIP2_MIRROR_ID]
    book_meta = {b["engine_id"]: b for b in CN_REGISTRY}

    books: dict = {}
    for eid in all_book_ids:
        bm = book_meta.get(eid, {"engine_id": eid, "name_en": eid, "name_zh": eid, "family": ""})
        books[eid] = {
            "engine_id": eid,
            "name_en": bm.get("name_en", eid),
            "name_zh": bm.get("name_zh", eid),
            "family": bm.get("family", ""),
            "picks_today": picks_today_by_book.get(eid) or [],
            "recent_fires": _build_recent_fires_with_grades(fires, grades, eid),
            "data_gap": False,   # updated per book when data_gap fires exist
        }

    # Detect data_gap books from fires
    for f in fires:
        eid = f.get("engine_id", "")
        if f.get("data_gap") and eid in books:
            books[eid]["data_gap"] = True

    # Scoreboard: denormalize name/family from registry
    scoreboard_out = []
    for sb in scoreboards:
        eid = sb.get("engine_id", "")
        bm = book_meta.get(eid, {})
        row = dict(sb)
        row["name_en"] = bm.get("name_en", eid)
        row["name_zh"] = bm.get("name_zh", eid)
        row["family"] = bm.get("family", "")
        row["horizon_role"] = bm.get("horizon_role", "entry")
        row["ruler"] = bm.get("ruler", "21d_csi300_excess")
        # Remap book.py keys → template schema
        row["wr21_abs"] = sb.get("h21_wr_abs")
        row["wr21_excess"] = sb.get("h21_wr_exc")
        row["med_excess21"] = sb.get("h21_med_exc")
        row["mfe_med"] = sb.get("h21_med_mfe")
        row["mae_med"] = sb.get("h21_med_abs_mae")
        row["asym"] = sb.get("h21_asym")
        row["nav_excess_cum"] = (sb.get("nav_final") or 1.0) - 1.0 if sb.get("nav_final") else None
        row["max_dd"] = sb.get("nav_max_drawdown")
        row["vs_random_lift"] = sb.get("lift_vs_ctrl")
        row["vs_universe_lift"] = sb.get("lift_vs_universe_base")
        row["n_dates"] = sb.get("n_distinct_fire_dates")
        scoreboard_out.append(row)

    return {
        "as_of": asof,
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "scoreboard": scoreboard_out,
        "books": books,
        "total_skipped_unfillable": skipped_unfillable,
        "method_note": (
            "CN A-share Pick Lab — display-only forward-evidence lab. "
            "All books ACCRUING until n≥25 fires / ≥3 months / ≥6 distinct fire dates (CNPL-R4). "
            "cnlab_random_ctrl = yardstick. Ruler: 21d CSI 300 excess. "
            "T+1 execution; fill = (H+L)/2 from raw OHLC (fill_basis stamped). "
            "sealed_up fires excluded (skipped_unfillable counter). "
            "Authority: display_only. Never gates or scores anything."
        ),
        "authority": "display_only",
    }


# ------------------------------------------------------------------ write helper ---


def _write_site_artifact(path: Path, payload: dict) -> None:
    """Atomically write a JSON site artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, default=str)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    log.info("cn_pick_lab: wrote %s (%.0f KB)", path, path.stat().st_size / 1024)


# ------------------------------------------------------------------ main build ---


def _build() -> None:
    """Core CN Pick Lab build (all exceptions propagate to main's try/except)."""
    t_start = time.monotonic()
    log.info("cn_pick_lab: start (CN_LANE=%r)", _CN_LANE)

    from engine.pick_lab import snapshot as snap_mod
    from engine.pick_lab.ledger import (
        append_fires,
        load_fires,
        load_grades,
        append_grades,
    )
    from engine.pick_lab.book import all_scoreboards
    from engine.pick_lab.profile import CN_PROFILE
    from engine.pick_lab.registry_cn import CN_REGISTRY, FLAGSHIP2_MIRROR_ID

    # (a) Load latest CN snapshot
    snap, asof = snap_mod.latest_snapshot(profile=CN_PROFILE)
    if snap is None or asof is None:
        log.info(
            "cn_pick_lab: no snapshot found in %s — honest no-op "
            "(first run after build_china_library produces one)",
            CN_PROFILE.snapshot_dir,
        )
        return

    log.info("cn_pick_lab: snapshot asof=%s, %d rows", asof, len(snap))

    # (b) Enrichment join from chinastatedata + microstructure + THS
    cycle = _load_cycle_phase()
    participation = _load_participation()
    policy = _load_policy_transmission()
    ms = _load_microstructure()
    ths_data = _load_ths_baskets()

    ms_by_ticker = _build_microstructure_by_ticker(ms)
    ths_by_ticker = _build_ths_membership(ths_data)

    snap_enriched = _enrich_snapshot(snap, cycle, participation, policy, ms_by_ticker, ths_by_ticker)
    log.info(
        "cn_pick_lab: enrichment — cycle=%r participation=%r policy=%r ms_tickers=%d ths_tickers=%d",
        cycle.get("phase"), participation.get("regime"), policy.get("policy_impulse"),
        len(ms_by_ticker), len(ths_by_ticker),
    )

    # Persist enriched snapshot (upsert; CNPL-R8 lane gate)
    if _IS_ASIA_LANE:
        try:
            snap_mod.write_snapshot(snap_enriched.reset_index(), asof, mode="upsert", profile=CN_PROFILE)
        except Exception as exc:
            log.warning(
                "cn_pick_lab: enriched snapshot persist failed (%s) — proceeding in-memory",
                exc,
            )
    else:
        log.info("cn_pick_lab: CN_LANE!='asia' — snapshot write skipped (CNPL-R8)")

    # Build trading date index for the refire-lockout check.
    # Prefer the CSI300 benchmark (stable, non-halted) over an arbitrary raw ticker.
    # Fall back to the union of raw-store dates if the benchmark is unavailable.
    trading_dates: pd.DatetimeIndex = pd.DatetimeIndex([])
    raw_dir = config.ROOT / _RAW_STORE_DIR
    try:
        bm_loader = CN_PROFILE.benchmark_loader
        if callable(bm_loader):
            _bm = bm_loader()
            if _bm is not None and not _bm.empty:
                trading_dates = pd.DatetimeIndex(_bm.index).sort_values()
        if len(trading_dates) == 0:
            # Fallback: union of all raw-store ticker dates (more stable than raw_files[0])
            raw_files = list(raw_dir.glob("*.parquet")) if raw_dir.exists() else []
            all_raw_dates: set = set()
            for fp in raw_files[:20]:  # sample up to 20 tickers for the union
                try:
                    _s = pd.read_parquet(fp, columns=["close"])
                    all_raw_dates.update(pd.DatetimeIndex(_s.index))
                except Exception:
                    pass
            if all_raw_dates:
                trading_dates = pd.DatetimeIndex(sorted(all_raw_dates))
    except Exception as exc:
        log.warning("cn_pick_lab: trading date index build failed (%s)", exc)

    # Load reversion desk rows (for flagship2_mirror)
    reversion_desk_rows: list[dict] = []
    try:
        rd_path = config.ROOT / "site" / "factordata" / "china_reversion_desk.json"
        if rd_path.exists():
            rd = json.loads(rd_path.read_text(encoding="utf-8"))
            reversion_desk_rows = rd.get("rows") or []
    except Exception as exc:
        log.debug("cn_pick_lab: china_reversion_desk.json unreadable (%s) — flagship2_mirror empty", exc)

    # (c) Fire pass
    fires_entry = load_fires(hold_thesis=False, profile=CN_PROFILE)

    new_fires, skipped_unfillable = _fire_all_cn_books(
        snap_enriched, asof, fires_entry, trading_dates, reversion_desk_rows
    )

    if _IS_ASIA_LANE and new_fires:
        written = append_fires(new_fires, hold_thesis=False, profile=CN_PROFILE)
        log.info("cn_pick_lab: appended %d CN entry fires", written)

    # Reload fires (for scoreboard + grade pass)
    fires_entry = load_fires(hold_thesis=False, profile=CN_PROFILE)

    # (d) Grade pass
    grades_entry = load_grades(hold_thesis=False, profile=CN_PROFILE)
    _cn_grade_pass(fires_entry, grades_entry, asof, raw_dir)

    # Reload grades after append
    grades_entry = load_grades(hold_thesis=False, profile=CN_PROFILE)

    # (e) Scoreboard
    all_books_in_registry = CN_REGISTRY
    # Include flagship2_mirror in the horizon_role_map with entry role
    horizon_role_map = {b["engine_id"]: b["horizon_role"] for b in all_books_in_registry}
    horizon_role_map[FLAGSHIP2_MIRROR_ID] = "entry"
    ruler_map = {b["engine_id"]: b.get("ruler", "21d_csi300_excess") for b in all_books_in_registry}
    ruler_map[FLAGSHIP2_MIRROR_ID] = "21d_csi300_excess"

    ctrl_fires = [f for f in fires_entry if f.get("engine_id") == CN_PROFILE.random_ctrl_id]
    ctrl_grades = [g for g in grades_entry if g.get("engine_id") == CN_PROFILE.random_ctrl_id]

    scoreboards = all_scoreboards(
        fires_entry,
        grades_entry,
        horizon_role_map,
        ruler_map=ruler_map,
        ctrl_fires=ctrl_fires,
        ctrl_grades=ctrl_grades,
        profile=CN_PROFILE,
    )

    # Build and write site artifact
    payload = _build_cn_site_payload(asof, scoreboards, fires_entry, grades_entry, skipped_unfillable)
    site = config.ROOT / "site"
    labdata = site / "labdata"
    if _IS_ASIA_LANE:
        _write_site_artifact(labdata / "china_pick_lab.json", payload)
    else:
        log.info("cn_pick_lab: CN_LANE!='asia' — site/labdata/china_pick_lab.json write skipped (CNPL-R8)")

    # (f) Render
    try:
        from engine.pick_lab.render_cn import build_vm, render_page, _load_cn_audit_scoreboard
        # SA-W5 F1: load the committed CN scoreboard explicitly so build_vm injects real
        # cells/mix data.  Without this audit_scoreboard=None → {"present": False} and
        # render_page's "not in vm" guard never fires (key IS present but False).
        audit_sb = _load_cn_audit_scoreboard(site)
        vm = build_vm(payload, audit_scoreboard=audit_sb)
        if _IS_ASIA_LANE:
            render_page(vm, site)
        else:
            log.info("cn_pick_lab: CN_LANE!='asia' — page render skipped (CNPL-R8)")
    except Exception as exc:
        log.warning("cn_pick_lab: page render failed (%s) — data artifacts are good", exc)

    elapsed = time.monotonic() - t_start
    log.info(
        "cn_pick_lab: done in %.1fs (budget 120s) — fires=%d skipped_unfillable=%d",
        elapsed, len(new_fires), skipped_unfillable,
    )
    if elapsed > 120:
        log.warning(
            "cn_pick_lab: elapsed %.1fs exceeds 2-minute budget (CNPL-R8)",
            elapsed,
        )


def main() -> int:
    """CN Pick Lab asia-lane runner. Always returns 0 (CNPL-R8 never-break contract)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s :: %(message)s",
    )
    if not _IS_ASIA_LANE:
        log.info(
            "cn_pick_lab: CN_LANE=%r — non-asia invocation is an honest no-op "
            "(ledger/data writes gated on CN_LANE=asia per CNPL-R8)",
            _CN_LANE,
        )
        # Still attempt the render from committed artifacts (no ledger writes)
        try:
            _build()
        except Exception:
            log.warning(
                "cn_pick_lab: non-asia build failed — non-fatal\n%s",
                traceback.format_exc(),
            )
        return 0

    try:
        _build()
    except Exception:
        log.warning(
            "cn_pick_lab: build failed — traceback below (non-fatal, returning 0)\n%s",
            traceback.format_exc(),
        )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
