"""Board-ORDER forward track-record for the China standout strip — the keystone the review called
for. The per-name POTENTIAL grader ([[china-name-potential-score]] → engine/name_score_grader)
scores potential_score rank-IC; it does NOT observe the ``signal_gate.blend_sorted`` BOARD ORDER
(cascade tier × setup percentile × washout/extension bonus) that actually decides which names sit
at the TOP of china_stocks.html. So nothing today measures the user's exact worry — "the top pick
already ran / underperforms". This ledger closes that gap:

  • append_board(rows, asof) — append today's ranked top-N standout rows (board_rank, ticker, tier,
    setup, extended, washout, and the as-of close `level`) to an append-only, point-in-time store,
    keep-FIRST per (date, ticker) so a logged rank is never overwritten / leaked.
  • grade() — for every matured row join the name's forward return and report, per horizon:
    TOP-decile vs rest mean forward return, the board RANK-IC (rank vs forward — a well-ordered
    board has a NEGATIVE rank-IC: rank #1 should outperform), and EXTENDED-vs-not forward (does the
    anti-chase demote actually flag underperformers?). "accruing" until enough.

GRADING CONVENTIONS (locked in the SAME pass as the store-group fix so the first number ever
published is unbiased — CN-1 masterplan §W6-CN):
  • CSI300-RELATIVE excess, never absolute. Benchmark = 510300.SS (the CSI300 ETF, data/china).
    An absolute A-share return conflates the reversal pick with the whole-market beta; the honest
    question is "did the top-of-board beat the index it was picked from".
  • FILL-REALISTIC entry. The logged reference `level` is the as-of CLOSE, which a retail user cannot
    trade — the earliest legal fill is the NEXT session (T+1). Entry = T+1 (H+L)/2 (Open is not
    collected for the whole store yet; (H+L)/2 with the high as the bound is the measured proxy —
    +4.41%/21d vs +2.13% buy-the-high, the dominant fill uncertainty). Once collectors/_stock_ohlc
    carries a real Open, upgrade the proxy to the true T+1 open (see ENTRY_BASIS below).
  • EXCLUDE locked-limit-all-day rows on the entry day (high==low==close): genuinely unfillable
    (0.22% of entries) — grading them fabricates a fill that never existed.
  • FLAG pinned-at-limit reference closes (the as-of close sat at the ±limit): the measured bias
    DOUBLES there (hit 50%→42.6%). We already grade every row from the T+1 fill (never the pinned
    reference close), so the pin only carries an informational `pinned` flag in the output.
  • NEVER grade from §7 marker dates. engine/signal_quality.py:161 resolves a 'take' label with the
    NEXT bar's close (+5.7pp/10d look-ahead). This ledger anchors ONLY on the board-date close
    (post-confirmation — verified safe 60/60), then fills T+1. The confirmation-day close is the
    earliest legal anchor; the forward window starts at the T+1 fill.

This is the honest prerequisite for promoting the anti-chase extension DEMOTE to a HARD veto: only
once grade() shows extended top-of-board names underperform (CSI300-relative, fill-realistic) should
the veto go live. Append-only, point-in-time, keep-first (leak-free). RESEARCH / display telemetry —
never a trade trigger. Mirrors engine/name_score_grader. See [[signal-track-record-logger]]."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

_HORIZONS_D = (21, 63)                    # ~1 / 3 months
_TOP_DECILE = 0.10
_STORE = "china_standout_track"
# A-share session settles ~07:00 UTC (15:00 CST close). A price panel collected BEFORE that on the
# board date carries a mid-session partial bar (93.9% of names differ from settled close, median
# 1.2%). The ledger's integrity today rests on a keep-first ACCIDENT (a stale panel reuses the prior
# as_of whose keys already exist, so the partial board is silently discarded). Make it explicit.
_SESSION_SETTLE_UTC_H = 7
_PANEL_SOURCE = "china_stocks"            # the run_status source whose checked_at = panel collection UTC
_BENCH = "510300.SS"                      # CSI300 ETF — the ONLY China excess benchmark (data/china)
# Board tickers are per-NAME A-shares (.SS/.SZ) that live in the china_stocks OHLC store; the small
# handful of ETFs on a board fall back to the index/ETF store. The #791 bug read only `china` (30
# ETFs) → 0/120 names resolved → n_graded=0 forever. Try names first, ETFs second.
_PRICE_GROUPS = ("china_stocks", "china")
ENTRY_BASIS = "t1_hl2"                    # T+1 (H+L)/2 proxy; upgrades to true T+1 open when collected
_MIN_GRADED = 8                           # per-horizon rows required before a number is published


def _store_path():
    return config.data_dir() / _STORE / "board.parquet"


def session_status(asof: str | None = None) -> dict:
    """Is the board's price panel a SETTLED session or a mid-session partial bar?

    Reads run_status.json for the ``china_stocks`` source: ``checked_at`` (collection UTC) and
    ``last_date`` (newest bar in the panel). A board is a PARTIAL SESSION when the panel's newest bar
    IS the board date AND that panel was collected before ~07:00 UTC (before the A-share close
    settled). Returns {partial_session, collected_utc, collected_hour_utc, last_date, reason}.
    Fail-OPEN on missing status (treat as settled) — a missing stamp must not silently block a real
    nightly board; the asia-lane gate below is the belt-and-braces."""
    out = {"partial_session": False, "collected_utc": None, "collected_hour_utc": None,
           "last_date": None, "reason": "no run_status — assumed settled"}
    try:
        st = store.read_status()
        src = (st.get("sources") or {}).get(_PANEL_SOURCE) or {}
        checked = src.get("checked_at")
        last_date = src.get("last_date")
        out["collected_utc"] = checked
        out["last_date"] = last_date
        if not checked:
            return out
        ts = pd.Timestamp(checked)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        ts = ts.tz_convert("UTC")
        out["collected_hour_utc"] = int(ts.hour)
        # only the CURRENT session can be partial: if the panel's newest bar is the board date and it
        # was collected before the close settled, the board-date bar is mid-session.
        same_day = (asof is not None and last_date is not None and str(last_date) == str(asof))
        if same_day and ts.hour < _SESSION_SETTLE_UTC_H:
            out["partial_session"] = True
            out["reason"] = (f"panel {_PANEL_SOURCE} for {asof} collected {ts.hour:02d}:xx UTC "
                             f"(< {_SESSION_SETTLE_UTC_H:02d}:00 settle) — mid-session partial bar")
        else:
            out["reason"] = "settled (collected after session close or a prior-session board)"
    except Exception as e:  # noqa: BLE001 — a guard failure must not block the ledger
        out["reason"] = f"session-status unreadable: {e}"
    return out


def append_board(rows: list[dict], asof: str | None = None, top_n: int = 60,
                 lane: str | None = None) -> int:
    """Append today's ranked top-N standout rows. Each row is a china_standouts `buy` entry (already
    in board order); we stamp its 1-based board_rank + the fields the grade needs. Keep-FIRST per
    (date, ticker). Returns the ledger row count after the merge. Best-effort — never raises.

    LEDGER-INTEGRITY GATES (CN-1 §W6-CN), replacing the keep-first accident:
      • asia-lane gate: appends only from the asia collection lane (``lane == 'asia'``). The nightly
        render lanes must NOT persist a board (they discard data/ writes anyway); passing lane=None
        preserves the legacy call for the asia build, which is the only one that commits data/.
      • partial-session refusal: if the board's price panel was collected before the A-share close
        settled (session_status().partial_session), REFUSE the append — a mid-session board must
        never win the date in the ledger."""
    if not rows or not asof:
        return 0
    # explicit asia-lane gate: a lane was passed and it is NOT asia → refuse (render lanes never
    # persist). lane=None keeps the historical (asia-build) call working unchanged.
    if lane is not None and lane != "asia":
        log.info("china standout board-track: append gated (lane=%s, not asia)", lane)
        return 0
    sess = session_status(asof)
    if sess.get("partial_session"):
        log.warning("china standout board-track: REFUSING append — %s", sess.get("reason"))
        return 0
    out = []
    for i, r in enumerate(rows[:top_n]):
        tk = r.get("ticker")
        if not tk:
            continue
        ext = r.get("extension") or {}
        sig = r.get("signal") or {}
        _cb = r.get("coiled") or {}
        _es = r.get("entry_signal") or {}
        out.append({
            "date": str(asof), "ticker": str(tk), "board_rank": i + 1,
            "tier": sig.get("tier_cascade"),
            "setup": r.get("setup"),
            "extended": bool(ext.get("extended")),
            "washout": bool(r.get("washout_2w")),
            "level": r.get("price"),
            # COILED wave-3 CN columns (wave-3 ship record 2026-07-02). New columns appended
            # to existing parquet rows via pd.concat schema union — old rows read fine (missing
            # cols become NaN, which pd.concat handles transparently; bool() of NaN = False).
            "coiled":        bool(_cb.get("coiled")),
            "coiled_star":   bool(_cb.get("star")),
            "coiled_cohort": _cb.get("cohort"),
            # COILED-FIRE wave-4 display chip fields (wave-4 ship record 2026-07-02).
            # Schema-union safe: old parquet rows missing these cols read as NaN (handled by concat).
            "coiled_fire":       bool(_cb.get("fire")),
            "coiled_fire_ticks": _cb.get("fire_ticks"),
            # W0.2a — tier+stage-stratified grading fields (W0 ship record 2026-07-03).
            # Schema-union safe: old parquet rows missing these cols read as NaN via pd.concat.
            # ticks / provisional: native-TF ticks since cross (None for projected T3/T4 cross).
            "ticks":        sig.get("ticks"),
            "provisional":  bool(sig.get("provisional")) if sig.get("provisional") is not None else False,
            # ext_score: extension score 0..1 at fire time (anti-chase anti-rank lever).
            "ext_score":    float((ext.get("score")) or 0.0),
            # washout_2w: explicit-name alias for the 2W StochRSI washout-reclaim flag
            # (kept alongside legacy "washout" for backward compat with existing parquet).
            "washout_2w":   bool(r.get("washout_2w")),
            # hold_state: W6-C basing-state after confluence anchor. None until the HOLD builder
            # port (W0.1) lands and begins populating rec["hold"] — wired here as a schema
            # placeholder so the ledger schema is stable before the first real value arrives.
            "hold_state":   (r.get("hold") or {}).get("state"),
            # entry_status: confluence-gated "buyable now" flag from entry_signal.status.
            "entry_status": _es.get("status"),
            # sector_turn: W0.10 sector first-tick-up flag (phase==Trough & osc_slope>0 in
            # forward_log). Schema-union safe: old parquet rows missing this col read as NaN
            # (handled by pd.concat transparently). "bottoming" when sector qualifies; None otherwise.
            "sector_turn":  (r.get("sector_turn") or {}).get("state"),
            # W1-B stage: lifecycle shelf (ENTRY / RAN_LATE / None) for board rows (rules 1-2).
            # Schema-union safe: old parquet rows missing this col read as NaN via pd.concat.
            "stage":        r.get("stage"),
        })
    if not out:
        return 0
    try:
        new = pd.DataFrame(out)
        p = _store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True).drop_duplicates(
                subset=["date", "ticker"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("china standout board-track append failed: %s", e)
        return 0


def _price_frame(ticker: str) -> pd.DataFrame | None:
    """OHLC frame for a board name — names resolve in china_stocks, ETFs in china. Returns the first
    store that has the ticker, else None. (The #791 dead-on-arrival bug: only `china` was read.)"""
    for g in _PRICE_GROUPS:
        df = store.read(g, str(ticker))
        if df is not None and "close" in df:
            return df
    return None


def _bench_close() -> pd.Series | None:
    """CSI300 (510300.SS) close series, for CSI300-relative excess. None if unavailable."""
    df = store.read("china", _BENCH)
    if df is None or "close" not in df:
        return None
    return pd.to_numeric(df["close"], errors="coerce").dropna()


def _t1_fill(df: pd.DataFrame, d0: pd.Timestamp) -> tuple[float | None, bool, bool]:
    """Fill-realistic entry: the FIRST session strictly AFTER the board-date close (T+1). Returns
    (fill_price, locked_limit, pinned). fill = (H+L)/2 proxy (or true Open if the column exists).
    ``locked_limit`` = T+1 bar printed high==low==close (unfillable — caller must exclude).
    ``pinned`` = the board-date reference CLOSE sat at that day's high==close (informational)."""
    idx = df.index
    after = idx[idx > d0]
    if len(after) == 0:
        return None, False, False
    t1 = after[0]
    row = df.loc[t1]
    hi, lo = row.get("high"), row.get("low")
    op = row.get("open") if "open" in df.columns else None
    close = row.get("close")
    locked = (hi is not None and lo is not None and close is not None
              and pd.notna(hi) and pd.notna(lo) and pd.notna(close)
              and float(hi) == float(lo) == float(close))
    # pinned reference close: the board-date bar closed AT its own high (limit-up-style pin) — the
    # reference the user saw was untradeable; we already grade from the T+1 fill so this is a flag.
    ref = df.loc[d0] if d0 in df.index else None
    pinned = bool(ref is not None and pd.notna(ref.get("high")) and pd.notna(ref.get("close"))
                  and float(ref.get("high")) == float(ref.get("close")))
    if op is not None and pd.notna(op):
        fill = float(op)                                  # true T+1 open once collected
    elif hi is not None and lo is not None and pd.notna(hi) and pd.notna(lo):
        fill = (float(hi) + float(lo)) / 2.0              # (H+L)/2 proxy
    elif close is not None and pd.notna(close):
        fill = float(close)
    else:
        return None, locked, pinned
    return fill, bool(locked), pinned


def _fwd_excess(ticker: str, d0: pd.Timestamp, h: int,
                bench: pd.Series | None) -> tuple[float | None, bool]:
    """Fill-realistic, CSI300-RELATIVE forward excess over ``h`` sessions from a T+1 entry.

    Returns (excess_or_None, pinned). excess = name (fill→+h close) − CSI300 (T+1→+h) return.
    None when: the name doesn't resolve, T+1 is locked-limit (unfillable), or the horizon can't
    mature. NEVER anchored on a §7 marker date — the anchor is the board-date close (post-
    confirmation) and the return is measured from the earliest legal fill (T+1)."""
    df = _price_frame(ticker)
    if df is None:
        return None, False
    fill, locked, pinned = _t1_fill(df, d0)
    if fill is None or locked:                            # unfillable → exclude, don't fabricate
        return None, pinned
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    fwd = close[close.index > d0]                         # sessions after the board date (T+1, T+2, …)
    if len(fwd) <= h:
        return None, pinned
    name_ret = float(fwd.iloc[h] / fill - 1.0)            # buy at the T+1 fill, exit +h sessions
    if bench is None:
        return name_ret, pinned                           # degrade to absolute if the ETF is missing
    bslice = bench[bench.index > d0]
    if len(bslice) <= h:
        return None, pinned
    bench_ret = float(bslice.iloc[h] / bslice.iloc[0] - 1.0)
    return name_ret - bench_ret, pinned                   # CSI300-relative excess


def grade() -> dict:
    """Score every matured board row, CSI300-relative + fill-realistic. {available, n_rows, dates,
    grading, by_horizon} where each horizon carries top-decile vs rest mean forward EXCESS, the
    board rank-IC, extended-vs-not forward excess, and a Wilson-CI hit rate vs CSI300."""
    p = _store_path()
    if not p.exists():
        return {"available": False, "note": "no board rows logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "note": "empty"}

    bench = _bench_close()
    out = {"available": True, "n_rows": int(len(df)),
           "dates": sorted(df["date"].dropna().unique().tolist()),
           "horizons_d": list(_HORIZONS_D),
           "grading": {
               "benchmark": _BENCH, "relative": True, "entry_basis": ENTRY_BASIS,
               "excludes_locked_limit": True, "flags_pinned": True,
               "anchor": "board_close_then_t1_fill", "marker_dates": "forbidden",
               "bench_available": bench is not None,
           },
           "by_horizon": {}}
    for h in _HORIZONS_D:
        recs = []
        n_pinned = 0
        for _i, row in df.iterrows():
            ex, pinned = _fwd_excess(row["ticker"], pd.Timestamp(row["date"]), h, bench)
            if pinned:
                n_pinned += 1
            if ex is None:
                continue
            # W0.2a — carry tier + flag columns into the grade record for stratification.
            # Old rows pre-W0.2a have NaN for the new fields; _slice_table groups NaN → "None".
            recs.append({
                "date": row["date"], "rank": row.get("board_rank"),
                "extended": bool(row.get("extended")), "fwd": ex,
                # tier_cascade (T1/T2/T3/T4) — the primary stratification dimension.
                "tier": row.get("tier"),
                # washout_2w: prefer the explicit-name field (W0.2a schema); fall back to
                # the legacy "washout" column so old ledger rows are still stratified.
                "washout_2w": (
                    row.get("washout_2w")
                    if row.get("washout_2w") is not None
                    else row.get("washout")
                ),
                # coiled: COILED cohort-washout flag (wave-3).
                "coiled": row.get("coiled"),
                # hold_state: W6-C basing state (None until W0.1 HOLD port populates it).
                "hold_state": row.get("hold_state"),
                # entry_status: confluence-gated entry gate label.
                "entry_status": row.get("entry_status"),
                # sector_turn: W0.10 sector first-tick-up state ("bottoming" or None).
                # Old rows pre-W0.10 will show NaN here (grouped as "None" in _slice_table).
                "sector_turn": row.get("sector_turn"),
            })
        if len(recs) < _MIN_GRADED:
            out["by_horizon"][f"{h}d"] = {"n": len(recs), "note": "accruing"}
            continue
        g = pd.DataFrame(recs)
        # board rank-IC per date (rank vs forward excess; NEGATIVE = a well-ordered board)
        ics = []
        for _d, sub in g.groupby("date"):
            if sub["rank"].nunique() >= 5:
                ics.append(float(sub["rank"].rank().corr(sub["fwd"].rank())))
        # top-decile (by best rank) vs the rest
        g = g.sort_values("rank")
        k = max(1, int(round(len(g) * _TOP_DECILE)))
        top_fwd = float(g.head(k)["fwd"].mean())
        rest_fwd = float(g.tail(len(g) - k)["fwd"].mean()) if len(g) > k else None
        ext = g[g["extended"]]
        non = g[~g["extended"]]
        hit = float((g["fwd"] > 0).mean())                # share beating CSI300
        lo, hi = _wilson_ci(int((g["fwd"] > 0).sum()), int(len(g)))
        out["by_horizon"][f"{h}d"] = {
            "n": int(len(g)),
            "hit_vs_csi300": round(hit, 4),
            "hit_ci": [round(lo, 4), round(hi, 4)],
            "median_excess": round(float(g["fwd"].median()), 4),
            "top_decile_fwd": round(top_fwd, 4),
            "rest_fwd": round(rest_fwd, 4) if rest_fwd is not None else None,
            "board_rank_ic": round(float(np.mean(ics)), 4) if ics else None, "n_ic_dates": len(ics),
            "extended_fwd": round(float(ext["fwd"].mean()), 4) if len(ext) >= 5 else None,
            "not_extended_fwd": round(float(non["fwd"].mean()), 4) if len(non) >= 5 else None,
            "n_extended": int(len(ext)),
            "n_pinned": int(n_pinned),
            # W0.2a — tier+stage-stratified forward grading (F3 discipline; calibrates from ledger,
            # never by fiat). Mirrors grade_us_board._slice_table idiom. "None" = column absent in
            # pre-W0.2a rows (old ledger rows pre-schema will appear here until the ledger matures).
            "by_tier":         _slice_table(g, "tier"),
            "by_washout_2w":   _slice_table(g, "washout_2w"),
            "by_coiled":       _slice_table(g, "coiled"),
            "by_hold_state":   _slice_table(g, "hold_state"),
            "by_entry_status": _slice_table(g, "entry_status"),
            # W0.10 — sector first-tick-up stratification (display/ledger only; bonus/rank
            # change ONLY after ledger matures per F3 discipline). "bottoming" vs None.
            "by_sector_turn":  _slice_table(g, "sector_turn"),
        }
    out["n_graded"] = max((v.get("n", 0) for v in out["by_horizon"].values()), default=0)
    return out


def _slice_table(df: pd.DataFrame, by: str, col: str = "fwd") -> dict:
    """Stratify a grade DataFrame by one column, returning per-stratum hit-stats.

    Mirrors grade_us_board._slice_table (same idiom, same output schema). NaN values are
    grouped under the key "None" so the JSON is always valid. Only strata with at least one
    non-null `col` row are included — thin strata report their honest n.

    Args:
        df:  per-row grade DataFrame (output of the grade() inner loop — must have `col`).
        by:  column name to stratify on (e.g. "tier", "washout_2w", "coiled").
        col: excess column to compute hit-stats on (default "fwd" — CSI300-relative excess).
    Returns:
        dict keyed by stratum value (str); each value has {n, hit_rate, wilson_lo, wilson_hi,
        median_excess, mean_excess} — honest small-sample stats with Wilson CI.
    """
    import math
    out: dict = {}
    for val, g in df.groupby(by, dropna=False):
        key = "None" if (val is None or (isinstance(val, float) and math.isnan(val))) else str(val)
        vals = g[col].dropna()
        n = len(vals)
        if n == 0:
            continue
        k = int((vals > 0).sum())
        lo, hi = _wilson_ci(k, n)
        out[key] = {
            "n": n,
            "hit_rate": round(k / n, 4),
            "wilson_lo": round(lo, 4),
            "wilson_hi": round(hi, 4),
            "median_excess": round(float(vals.median()), 5),
            "mean_excess": round(float(vals.mean()), 5),
        }
    return out


def _ripening_path():
    return config.data_dir() / _STORE / "ripening.parquet"


def append_ripening(rows: list[dict], asof: str | None = None,
                    lane: str | None = None) -> int:
    """Append today's RIPENING names as a compact log (conversion grading in W6 needs this
    history). Separate parquet from the main board so consumers of buy are unaffected.

    Row schema: date, ticker, reasons (comma-joined str), imminence (macd_bars_to_cross or None),
    w2_stoch, setup_live. Keep-FIRST per (date, ticker). Same asia-lane gate as append_board.
    Best-effort — never raises.
    """
    if not rows or not asof:
        return 0
    if lane is not None and lane != "asia":
        return 0
    out = []
    for r in rows:
        tk = r.get("ticker")
        if not tk:
            continue
        reasons = r.get("reasons") or []
        out.append({
            "date": str(asof),
            "ticker": str(tk),
            "reasons": ", ".join(reasons) if reasons else "",
            "imminence": r.get("imminence"),
            "w2_stoch": r.get("w2_stoch"),
            "setup_live": True,
        })
    if not out:
        return 0
    try:
        new = pd.DataFrame(out)
        p = _ripening_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True).drop_duplicates(
                subset=["date", "ticker"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("china standout ripening-track append failed: %s", e)
        return 0


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a hit rate k/n (n>0). Honest small-sample bounds."""
    if n <= 0:
        return 0.0, 0.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, centre - half), min(1.0, centre + half)
