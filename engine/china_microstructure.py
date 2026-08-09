"""engine/china_microstructure.py — A-share microstructure lobe (W1).

Produces the limit-state historical tape (PIT market-day aggregates + event rows) from
data/china_stocks_raw/*.parquet (raw nominal OHLCV, auto_adjust=False).

Authority: context_only (CN-SYS-R1, CN-SYS-R3).

Board-aware limit widths (CN-SYS-R12)
--------------------------------------
  main board (600/601/603/605/000/001/002/003.SS/SZ): ±10%
  STAR (688/689.SS): ±20% from listing
  ChiNext (300/301.SZ): ±10% BEFORE 2020-08-24; ±20% on/after 2020-08-24
  BSE (8x/4x): ±30% (2021-11-15→) — not present in raw store as of 2026-07-08, handled
  ST/*ST on MAIN boards only: ±5% before 2026-07-06, ±10% on/after 2026-07-06
  ST names on STAR/ChiNext keep their board widths (20% in the covered eras)

IPO exclusion windows (CN-SYS-R12)
------------------------------------
  STAR/ChiNext names: first 5 sessions excluded from limit detection (44% cap regime)
  All pre-2014 listings (first bar before 2014-01-01): first session excluded (44% cap regime)

Ex-div caveat
--------------
Raw prices are nominal so limit reconstruction is exact against raw prices. However on
ex-dividend/ex-rights days the price can gap beyond the limit width without a genuine
limit event. We mark suspect=True when |prev_close - open| / prev_close > limit_width * 1.5
and suppress events on those days (they are counted in a separate excluded_exdiv counter).

ST flags
---------
data/china_st/ carries st_snapshot.parquet (a current-membership snapshot) and
st_history.parquet (currently only one 2026-07-06 cross-section). Historical ST membership is
NOT available. The snapshot is a proxy, not PIT history: membership is accepted only on its
own attested ``asof`` date; unknown later membership uses the ordinary board width with an
alarm. A 'st_flags_current_only' caveat is stamped in tape metadata.

CAVEAT: st_flags_current_only — only the snapshot's exact attested date has usable membership.
For every other date we apply ordinary board widths. Historical events for then-ST names can
therefore be misclassified; the manifest records the snapshot hash/asof and staleness explicitly.

Schema contracts (§5, frozen)
------------------------------
limit_tape.parquet (market-day aggregates):
  date, limit_up_count, limit_down_count, sealed_up_close, failed_up_seal_count,
  lianban_2plus, lianban_max, limit_up_breadth_pct, limit_down_breadth_pct,
  st_excluded_counts, universe_n, backfill(bool)

limit_events.parquet (event rows):
  date, ticker, board, limit_width, event, lianban_count, close_off_limit_pct
  event ∈ {sealed_up, failed_up_seal, sealed_down, failed_down_seal, touched_up, touched_down}

  Enum subset note: this producer intentionally emits {sealed_up, failed_up_seal, sealed_down,
  failed_down_seal}.  The §5 schema lists touched_up / touched_down as valid values for future
  producers; they are NOT emitted here because touched-but-unsealed is captured by failed_*_seal.

  close_off_limit_pct is stored as a FRACTION (not percent):
    up-side:   (lim_up  - close) / lim_up   for sealed_up / failed_up_seal
    down-side: (close   - lim_down) / lim_down for sealed_down / failed_down_seal
  0.0 = closed exactly at the limit; positive = closed inside (away from the limit).

Lianban undercount caveat (nightly increments only)
-----------------------------------------------------
The nightly build_increment uses a ~20-session lookback window.  A lianban streak that began
before the window will be undercounted in the appended rows (e.g. a genuine 3rd consecutive
board is reported as lianban_count=1).  Backfill rows are unaffected.  Downstream aggregates
lianban_2plus / lianban_max for those specific dates may be mildly understated.  Risk is
bounded by NIGHTLY_LOOKBACK; widening that constant reduces (but does not eliminate) the gap.

microstructure.json (site/chinastatedata/):
  latest aggregates + per-name packet for standout tickers:
    board, limit_width, limit_state, fillable, t_plus_one_risk, chase_veto{flag, reason}
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

CHINEXT_WIDE_DATE = pd.Timestamp("2020-08-24")   # ChiNext switched to ±20% on this date
BSE_LAUNCH_DATE   = pd.Timestamp("2021-11-15")   # BSE launched
STAR_LAUNCH_DATE  = pd.Timestamp("2019-07-22")   # STAR market launched
IPO_PRE2014_DATE  = pd.Timestamp("2014-01-01")   # pre-2014 = 44% cap on day 1
CHINEXT_STAR_IPO_WINDOW = 5                       # first N sessions excluded for STAR/ChiNext
PRE2014_IPO_WINDOW      = 1                       # first session excluded for pre-2014 listings

# Earliest date for which this module produces valid limit data.  The A-share ±10% daily price
# limit was introduced 1996-12; before that date, applying a 10% rule generates fabricated
# artefacts.  The §5 frozen contract specifies "2011→" as the data floor; this constant enforces
# it in backfill and nightly builders alike.
LIMIT_TAPE_START_DATE = pd.Timestamp("2011-01-01")

ST_STORE_COVERAGE_DATE = pd.Timestamp("2026-07-06")  # first date st_history covers

# Shanghai and Shenzhen both widened main-board risk-warning price limits from 5% to 10%
# effective 2026-07-06.  STAR/ChiNext remain governed by their board widths.
# SSE: https://star.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml
# SZSE: https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf
MAIN_RISK_WARNING_WIDE_DATE = pd.Timestamp("2026-07-06")


class STMembershipSnapshot(frozenset[str]):
    """Ticker set carrying the one date on which current membership is attested."""

    def __new__(
        cls,
        tickers: object = (),
        *,
        attested_asof: pd.Timestamp | None = None,
        source_path: Path | None = None,
    ) -> "STMembershipSnapshot":
        obj = super().__new__(cls, tickers)
        obj.attested_asof = (
            pd.Timestamp(attested_asof).normalize() if attested_asof is not None else None
        )
        obj.source_path = source_path
        return obj


# ── board classification ───────────────────────────────────────────────────────

def _board_from_ticker(ticker: str) -> str:
    """Return board name from ticker string.

    Logic mirrors engine.china_signals.board_type() prefix rules.  Intentionally kept as a
    local copy so this module has no import-time dependency on china_signals; a pinning test
    in tests/test_china_microstructure.py guards parity with board_type().  If board_type()
    changes its prefix logic, update here and the test simultaneously.

    Note: this function deliberately ignores board_type()'s era-aware ChiNext 20% width; the
    width is resolved separately in limit_width_for_date().
    """
    t = (ticker or "").upper()
    code = t.split(".")[0]
    if code.startswith(("688", "689")):
        return "star"
    # 302xxx added 2026-08-04 alongside china_signals.board_type — the block is
    # ChiNext and trades the ±20% band; reading it as "main" applied a 10% band.
    if code.startswith(("300", "301", "302")):
        return "chinext"
    if code.startswith(("8", "4", "92")):
        return "bse"
    return "main"


def limit_width_for_date(board: str, trade_date: pd.Timestamp,
                          is_st: bool = False) -> float:
    """Return the limit-up/down width as a decimal fraction for a given board+date.

    ST flag applies ONLY on main board (CN-SYS-R12); its width is 5% before
    2026-07-06 and 10% on/after that date. STAR/ChiNext keep their board width.
    BSE: 30% from 2021-11-15; before that date, BSE did not exist — treated as 30% for
    any bar in the raw store that starts after BSE_LAUNCH_DATE.
    """
    if board == "star":
        return 0.20
    if board == "chinext":
        if trade_date >= CHINEXT_WIDE_DATE:
            return 0.20
        return 0.10
    if board == "bse":
        return 0.30
    # main board
    if is_st:
        return 0.10 if trade_date >= MAIN_RISK_WARNING_WIDE_DATE else 0.05
    return 0.10


# ── ST membership lookup ───────────────────────────────────────────────────────

def _load_st_set(data_dir: Path) -> STMembershipSnapshot:
    """Load the ST snapshot; unknown dates use ordinary width and emit a stale alarm."""
    st_path = data_dir / "china_st" / "st_snapshot.parquet"
    if not st_path.exists():
        log.warning("ST snapshot not found at %s; ST widths not applied", st_path)
        return STMembershipSnapshot(source_path=st_path)
    try:
        df = pd.read_parquet(st_path)
        col = "ticker" if "ticker" in df.columns else df.columns[0]
        asof_values = (
            pd.to_datetime(df["asof"], errors="coerce").dropna().dt.normalize().unique()
            if "asof" in df.columns
            else []
        )
        attested_asof = pd.Timestamp(asof_values[0]) if len(asof_values) == 1 else None
        snapshot = STMembershipSnapshot(
            df[col].astype(str).tolist(),
            attested_asof=attested_asof,
            source_path=st_path,
        )
        if attested_asof is None:
            log.warning(
                "ST snapshot at %s has no single attested asof; membership will not be applied",
                st_path,
            )
        elif attested_asof < pd.Timestamp(date.today()):
            log.warning(
                "ST snapshot is stale (asof=%s, today=%s); membership applies only on its "
                "attested date",
                attested_asof.date(),
                date.today(),
            )
        return snapshot
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load ST snapshot: %s", exc)
        return STMembershipSnapshot(source_path=st_path)


def _st_membership_attested(
    st_set: frozenset[str],
    ticker: str,
    trade_date: pd.Timestamp,
) -> bool:
    """True only when membership is present and attested for ``trade_date``.

    Plain frozensets remain supported for explicit synthetic/test callers. Production loads use
    ``STMembershipSnapshot`` and therefore use ordinary width outside the snapshot's own asof.
    """
    if ticker not in st_set:
        return False
    if not isinstance(st_set, STMembershipSnapshot):
        return True
    return (
        st_set.attested_asof is not None
        and pd.Timestamp(trade_date).normalize() == st_set.attested_asof
    )


# ── per-ticker event detection ─────────────────────────────────────────────────

def _detect_limit_events(
    ticker: str,
    df: pd.DataFrame,
    board: str,
    st_set: frozenset[str],
    start_date: Optional[pd.Timestamp] = None,
    end_date: Optional[pd.Timestamp] = None,
) -> tuple[list[dict], int, int]:
    """Scan one ticker's OHLCV for limit-state events.

    Returns:
        (event_rows, ipo_excluded_count, exdiv_excluded_count)

    Each event row is a dict matching the limit_events schema.
    """
    if df.empty or len(df) < 2:
        return [], 0, 0

    # Normalise index to date
    df = df.copy()
    df.index = pd.to_datetime(df.index)

    # Apply date filter if requested
    if start_date is not None:
        df = df[df.index >= start_date]
    if end_date is not None:
        df = df[df.index <= end_date]
    if df.empty:
        return [], 0, 0

    # Determine IPO exclusion window
    first_bar_global = pd.to_datetime(df.index.min())
    ipo_window = 0
    if board in ("star", "chinext"):
        ipo_window = CHINEXT_STAR_IPO_WINDOW
    elif first_bar_global < IPO_PRE2014_DATE:
        ipo_window = PRE2014_IPO_WINDOW

    # Build prev_close shifted series
    closes     = df["close"].astype(float)
    highs      = df["high"].astype(float)
    lows       = df["low"].astype(float)
    opens_     = df["open"].astype(float)
    prev_close = closes.shift(1)

    events: list[dict] = []
    ipo_excluded    = 0
    exdiv_excluded  = 0
    lianban_streak  = 0  # consecutive sealed_up days for lianban count

    for i, (ts, row) in enumerate(df.iterrows()):
        trade_date = pd.Timestamp(ts)

        # --- IPO window exclusion ---
        if i < ipo_window:
            ipo_excluded += 1
            lianban_streak = 0
            continue

        pc = prev_close.iloc[i]
        if pd.isna(pc) or pc <= 0:
            lianban_streak = 0
            continue

        # Current-snapshot membership is accepted only on its exact attested date. A plain
        # frozenset is treated as an explicit caller-provided fixture/attestation.
        is_st = (
            board == "main"
            and _st_membership_attested(st_set, ticker, trade_date)
            and trade_date >= ST_STORE_COVERAGE_DATE
        )

        width = limit_width_for_date(board, trade_date, is_st=is_st)

        # --- ex-div suspect check ---
        # If open gaps more than 1.5x width vs prev_close → suspected ex-div/ex-rights day
        open_move = abs(float(opens_.iloc[i]) - pc) / pc
        if open_move > width * 1.5:
            exdiv_excluded += 1
            lianban_streak = 0
            continue

        # --- limit price computation ---
        lim_up   = round(pc * (1 + width), 2)
        lim_down = round(pc * (1 - width), 2)

        high_val  = float(highs.iloc[i])
        low_val   = float(lows.iloc[i])
        close_val = float(closes.iloc[i])

        touched_up   = high_val  >= lim_up
        touched_down = low_val   <= lim_down
        sealed_up    = close_val >= lim_up
        sealed_down  = close_val <= lim_down

        # Update lianban streak
        if sealed_up:
            lianban_streak += 1
        else:
            lianban_streak = 0

        # close_off_limit_pct: stored as a FRACTION (not percent), matching the §5 contract:
        #   up-side:   (lim_up - close) / lim_up   — 0.0 when sealed exactly, positive when below
        #   down-side: (close - lim_down) / lim_down — 0.0 when sealed exactly, positive when above
        # Negative values are theoretically impossible but can occur due to rounding; consumers
        # should treat values <= 0 as "at or inside the limit".
        close_off_up   = round((lim_up - close_val) / lim_up, 6)
        close_off_down = round((close_val - lim_down) / lim_down, 6) if lim_down > 0 else None

        # Emit events
        date_str = trade_date.strftime("%Y-%m-%d")

        # Emit up-side events (seal takes priority over touched-only)
        if sealed_up:
            events.append({
                "date": date_str,
                "ticker": ticker,
                "board": board,
                "limit_width": round(width * 100, 1),
                "event": "sealed_up",
                "lianban_count": lianban_streak,
                "close_off_limit_pct": close_off_up,
            })
        elif touched_up:
            events.append({
                "date": date_str,
                "ticker": ticker,
                "board": board,
                "limit_width": round(width * 100, 1),
                "event": "failed_up_seal",
                "lianban_count": 0,
                "close_off_limit_pct": close_off_up,
            })

        # Emit down-side events (independent of up-side; a name can touch up AND down is separate)
        if sealed_down:
            events.append({
                "date": date_str,
                "ticker": ticker,
                "board": board,
                "limit_width": round(width * 100, 1),
                "event": "sealed_down",
                "lianban_count": 0,
                "close_off_limit_pct": close_off_down,
            })
        elif touched_down:
            events.append({
                "date": date_str,
                "ticker": ticker,
                "board": board,
                "limit_width": round(width * 100, 1),
                "event": "failed_down_seal",
                "lianban_count": 0,
                "close_off_limit_pct": close_off_down,
            })

    return events, ipo_excluded, exdiv_excluded


# ── aggregate computation ─────────────────────────────────────────────────────

def aggregate_daily(
    events_df: pd.DataFrame,
    universe_n_by_date: dict[str, int],
    st_excluded_by_date: dict[str, int],
    *,
    backfill: bool,
) -> pd.DataFrame:
    """Aggregate event rows into market-day aggregates matching limit_tape schema.

    Parameters
    ----------
    events_df : DataFrame with columns matching limit_events schema
    universe_n_by_date : {date_str: n_names_with_data_on_that_date}
    st_excluded_by_date : {date_str: count_of_ipo_excluded_bars}
    backfill : True only for a full historical reconstruction; False for nightly/incremental rows

    The output calendar is the union of event dates and ``universe_n_by_date``. This is
    deliberate: a trading session with zero limit events is still a valid tape row.
    """
    columns = [
        "date", "limit_up_count", "limit_down_count", "sealed_up_close",
        "failed_up_seal_count", "lianban_2plus", "lianban_max",
        "limit_up_breadth_pct", "limit_down_breadth_pct",
        "st_excluded_counts", "universe_n", "backfill",
    ]

    def _normalise_date_key(value: object) -> str:
        return pd.Timestamp(value).strftime("%Y-%m-%d")

    universe = {_normalise_date_key(key): int(value) for key, value in universe_n_by_date.items()}
    excluded = {_normalise_date_key(key): int(value) for key, value in st_excluded_by_date.items()}
    events = events_df.copy()
    if events.empty:
        events = pd.DataFrame(columns=["date", "event", "lianban_count"])
        event_dates: set[str] = set()
    else:
        events["date"] = pd.to_datetime(events["date"]).dt.strftime("%Y-%m-%d")
        event_dates = set(events["date"])

    dates = sorted(set(universe) | event_dates)
    if not dates:
        return pd.DataFrame(columns=columns)

    records: list[dict] = []
    for d in dates:
        day = events[events["date"] == d]
        su = day[day["event"] == "sealed_up"]
        sd = day[day["event"] == "sealed_down"]
        fu = day[day["event"] == "failed_up_seal"]
        n = universe.get(d, 0)
        records.append({
            "date": d,
            "limit_up_count": int(len(su) + len(fu)),
            "limit_down_count": int(len(sd)),
            "sealed_up_close": int(len(su)),
            "failed_up_seal_count": int(len(fu)),
            "lianban_2plus": int((su["lianban_count"] >= 2).sum()) if len(su) else 0,
            "lianban_max": int(su["lianban_count"].max()) if len(su) else 0,
            "limit_up_breadth_pct": round((len(su) + len(fu)) / n * 100, 4) if n else None,
            "limit_down_breadth_pct": round(len(sd) / n * 100, 4) if n else None,
            "st_excluded_counts": excluded.get(d, 0),
            "universe_n": n,
            "backfill": bool(backfill),
        })

    return pd.DataFrame.from_records(records, columns=columns)


# ── per-name microstructure packet ───────────────────────────────────────────

def name_packet(
    ticker: str,
    df: pd.DataFrame,
    st_set: frozenset[str],
) -> dict:
    """Compute the per-name microstructure packet for the latest session.

    Returns fields: board, limit_width, limit_state, fillable, t_plus_one_risk,
    chase_veto{flag, reason}

    Degrades to nulls if insufficient data.
    """
    result: dict = {
        "ticker": ticker,
        "board": None,
        "limit_width": None,
        "limit_state": None,
        "fillable": None,
        "t_plus_one_risk": None,
        "chase_veto": {"flag": False, "reason": None},
    }
    board = _board_from_ticker(ticker)
    result["board"] = board

    if df is None or df.empty or len(df) < 2:
        return result

    df = df.copy()
    df.index = pd.to_datetime(df.index)
    latest = df.index[-1]

    is_st = board == "main" and _st_membership_attested(st_set, ticker, latest)
    width = limit_width_for_date(board, latest, is_st=is_st)
    result["limit_width"] = round(width * 100, 1)

    closes = df["close"].astype(float)
    highs  = df["high"].astype(float)
    lows   = df["low"].astype(float)
    prev_close = float(closes.iloc[-2])
    close_val  = float(closes.iloc[-1])
    high_val   = float(highs.iloc[-1])
    low_val    = float(lows.iloc[-1])

    if prev_close <= 0:
        return result

    lim_up   = round(prev_close * (1 + width), 2)
    lim_down = round(prev_close * (1 - width), 2)

    sealed_up   = close_val >= lim_up
    touched_up  = high_val  >= lim_up
    sealed_down = close_val <= lim_down

    # limit_state: label for display
    if sealed_up:
        limit_state = "sealed_up"
    elif touched_up:
        limit_state = "touched_up_failed"
    elif sealed_down:
        limit_state = "sealed_down"
    else:
        limit_state = "open"
    result["limit_state"] = limit_state

    # fillable: false when sealed_up (locked limit-up = not fillable on T+1)
    result["fillable"] = not sealed_up

    # t_plus_one_risk: deterministic heuristic
    # HIGH when: sealed_up (extension + lock) OR lianban sequence detected (previous day also sealed_up)
    # ELEVATED when: touched_up but failed to seal (magnet effect, next-day follow risk)
    # NORMAL otherwise
    # Look back 2 sessions for lianban
    lianban = False
    if len(closes) >= 3:
        prev2_close = float(closes.iloc[-3])
        if prev2_close > 0:
            lim_up_prev = round(prev2_close * (1 + width), 2)
            lianban = (prev_close >= lim_up_prev)  # yesterday was a sealed_up day

    if sealed_up and lianban:
        t1_risk = "high_lianban"
    elif sealed_up:
        t1_risk = "high"
    elif touched_up and not sealed_up:
        t1_risk = "elevated"
    else:
        t1_risk = "normal"
    result["t_plus_one_risk"] = t1_risk

    # chase_veto: reuse china_signals logic (CN-SYS-R3)
    # Veto fires when: sealed_up (locked = chase-veto) OR previous 5d run >= 15%
    chase_flag = False
    chase_reason = None
    if sealed_up:
        chase_flag = True
        chase_reason = "locked at limit-up (T+1 fillability blocked)"
    else:
        # check 5-session run
        if len(closes) >= 6:
            run5 = (close_val / float(closes.iloc[-6]) - 1.0) * 100
            if run5 >= 15.0:
                chase_flag = True
                chase_reason = f"+{run5:.0f}% 5-session run (extension risk)"
    result["chase_veto"] = {"flag": chase_flag, "reason": chase_reason}

    return result


# ── THS snapshot side-car ─────────────────────────────────────────────────────

def snapshot_ths_concepts(
    data_dir: Path,
    as_of: Optional[str] = None,
    offline_ok: bool = True,
) -> dict:
    """Append a dated THS concept-membership snapshot to data/baskets_china_ths/snapshots/.

    Dedup by date: if today's snapshot already exists, return existing content without network call.
    Degrades softly offline (logs warning, returns empty dict).

    This is a DISPLAY-TIER data collection step — it does not modify membership.json or any
    live page. Wiring into asia-close is W5a's task; this entrypoint is the --snapshot CLI.

    Parameters
    ----------
    data_dir : path to data/ directory
    as_of : ISO date string; defaults to today
    offline_ok : if True, network failures return {} gracefully; if False, raise
    """
    today = as_of or date.today().isoformat()
    snap_dir = data_dir / "baskets_china_ths" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{today}.json"

    if snap_path.exists():
        log.info("THS snapshot for %s already exists; skipping network call", today)
        try:
            import json
            return json.loads(snap_path.read_text())
        except Exception:  # noqa: BLE001
            return {}

    log.info("THS concept snapshot: collecting %s", today)
    try:
        from collectors import china_ths_concepts as ths
        mem_path = data_dir / "baskets_china_ths" / "membership.json"
        if not mem_path.exists():
            log.warning("THS membership.json not found; cannot snapshot")
            return {}

        import json
        with open(mem_path) as fh:
            membership = json.load(fh)
        basket_keys = list((membership.get("baskets") or {}).keys())
        if not basket_keys:
            log.warning("No baskets found in membership.json")
            return {}

        # Attempt to pull concept codes for the curated baskets
        try:
            concept_map = ths.concept_code_map()
            concepts = [k for k in concept_map if k in basket_keys or True][:10]
            result = ths.snapshot(concepts, as_of=today, resume=True)
        except Exception as net_exc:  # noqa: BLE001
            if not offline_ok:
                raise
            log.warning("THS snapshot network call failed (offline?): %s", net_exc)
            return {}

        snap_path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        log.info("THS snapshot written: %s (%d concepts)", snap_path, len(result))
        return result

    except ImportError as imp_exc:
        log.warning("THS collectors not available: %s", imp_exc)
        if not offline_ok:
            raise
        return {}
    except Exception as exc:  # noqa: BLE001
        log.warning("THS snapshot failed: %s", exc)
        if not offline_ok:
            raise
        return {}
