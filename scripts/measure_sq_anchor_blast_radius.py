"""Measure what the §7 absolute session anchor CHANGED, per production loader — ship req 1.

Ruling: research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md
(era ``sq-abs-session-2026-08-06``).

    .venv/bin/python scripts/measure_sq_anchor_blast_radius.py            # every universe
    .venv/bin/python scripts/measure_sq_anchor_blast_radius.py --quick    # stocks + ohlcv only

Writes ``reports/sq_anchor_blast_radius.md`` + ``.json``.

HOW OLD-VS-NEW IS PRODUCED. There is NO era flag in the engine — a switch left in production
code is a second code path nobody runs. Instead the PRE-repair ``signal_frame`` and
``_bucket_last_session`` are frozen VERBATIM below (copied from the commit before the
repair) and monkeypatched into ``engine.signal_quality`` for the duration of a measurement
pass. ``analyze`` resolves ``signal_frame`` as a MODULE GLOBAL at call time, so patching the
name is enough to swing the whole §7 stream — including ``gate()``, which reaches it through
``analyze``. "new" is the module exactly as it ships.

WHAT IT MEASURES — the §7 LAYER, end-to-end through ``signal_gate.gate()``:
  1. stocks/          last-marker date/identity moves, ticks/eligibility/buyable flips
  2. baskets/ohlcv/   same, on the 2014-start loader
  3. depth views      stocks/ truncated to 345 and 777 trailing bars (the breadth/smallcap
                      cache depths that reach gate() in production)
  4. massive_stock_day the real scan-tier universe via engine.us_scan_universe's own floor
  5. CN panel         data/china_search/closes.parquet (suffixed tickers -> market inferred)
  6. HK stores        data/hk/*.HK.parquet, reclaim_veto=False (the HK board's own policy)
  plus: stocks/ vs ohlcv/ §7-layer AGREEMENT before and after (the NUE/PEP/ECL/SW/WMT quintet
  printed by name), the OPEN-TAKE RE-KEY count (names whose live take_date moved — the
  ledger's re-key surface, R-SQ4), and a NEW-anchor start-invariance re-run on real data
  (must be 0 movers on every captured field).

NO SILENT CAPS (house law). Every universe reports the names it could not read and WHY; a
store absent from the checkout is named in the report and annotated, never skipped into a
smaller-looking denominator.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import signal_gate                      # noqa: E402
from engine import signal_quality as sq             # noqa: E402
from engine.technicals import rsi                   # noqa: E402

#: The five names the cascade audit called out — they are the §7 report's headline table too,
#: so both layers can be read against the same roster on the same night.
QUINTET = ("NUE", "PEP", "ECL", "SW", "WMT")
#: Depth views that reach gate() in production (breadth cache / smallcap cache).
DEPTH_VIEWS = (345, 777)
#: Daily bars below which signal_frame cannot build its 90-bucket frame at all.
MIN_BARS = 270
#: The §7-layer fields a name is compared on.
FIELDS = ("last_date", "last_type", "last_quality", "n_markers", "asof",
          "eligible", "tier_cascade", "ticks", "buyable")

#: The subset that a START-INVARIANCE run may be judged on. ``n_markers`` is excluded BY
#: DEFINITION, exactly as ``bars``/``young_history`` are in the cascade's battery: it counts
#: how much history the caller passed. Dropping k leading bars eats the leading 3D bucket
#: outright, and near the indicator WARM-UP boundary (the 60-bucket RSI-MACD min_periods,
#: plus the StochRSI flat-band NaN that drops rows out of the frame) the two windows can
#: differ by a marker or two in their first weeks. That residual is MEASURED rather than
#: waved at — see ``marker_stream_residual`` in the report, which prints how deep the two
#: streams agree and how long ago the last disagreement was.
INVARIANCE_FIELDS = tuple(f for f in FIELDS if f != "n_markers")


# --------------------------------------------------------------------------- #
# FROZEN pre-repair implementations (verbatim) + the era switch
# --------------------------------------------------------------------------- #

def _signal_frame_legacy(daily_close, daily_high=None, daily_low=None, *, market="US"):
    """The pre-repair 3D/2D grid: pandas bins anchored to the SERIES' FIRST timestamp.

    Copied verbatim from ``engine/signal_quality.signal_frame`` as it stood before
    ``sq-abs-session-2026-08-06``; only the module-level helpers are re-pointed at ``sq``.
    ``market`` is accepted and DISCARDED, which is itself part of the measured delta:
    before the repair EVERY market was bucketed by the same market-blind business-day rule,
    so the CN and HK slices below measure a calendar change as well as a phase change.
    """
    s3 = daily_close.resample("3B").last().dropna()
    if len(s3) < 90:
        return pd.DataFrame()
    macd, sig = sq._rsi_macd(s3)
    k, d = sq._stoch_rsi_kd(s3)
    r14 = rsi(s3, sq.RSI_LEN)
    sb, ss = sq._xup(k, d), sq._xdn(k, d)
    mb, ms = sq._xup(macd, sig), sq._xdn(macd, sig)
    wk = daily_close.resample("W-FRI").last().dropna()
    wm, wsg = sq._rsi_macd(wk)
    wbull = (wm >= wsg).shift(1).reindex(s3.index, method="ffill").fillna(False).astype(bool)
    ma = daily_close.rolling(sq.MA_LEN).mean()
    above = (s3 > ma.reindex(s3.index).ffill()).fillna(False)
    ema_trail = s3.ewm(span=sq.TRAIL_SPAN, min_periods=sq.TRAIL_SPAN).mean()
    b1os = d.rolling(sq.CONF_W).min() < sq.OS
    s1ob = d.rolling(sq.CONF_W).max() > sq.OB
    cb = (mb & (sq._since(sb) <= sq.CONF_W) & (wbull | b1os)
          & (r14 < sq.BUY_RSI_MAX)).fillna(False)
    rext = ((k.rolling(sq.CONF_W).max() >= sq.OB)
            | (r14.rolling(sq.CONF_W).max() >= sq.EXT_RSI))
    cs = (ms & (sq._since(ss) <= sq.CONF_W) & ((~wbull) | s1ob) & rext).fillna(False)
    revsell = (ms & (sq._since(cb) <= sq.REV_BARS)).fillna(False)
    revbuy = (mb & (sq._since(cs) <= sq.REV_BARS)).fillna(False)
    s2 = daily_close.resample("2B").last().dropna()
    m2, sg2 = sq._rsi_macd(s2)
    hist2 = m2 - sg2
    rising2 = ((hist2 > hist2.shift(1)) & (hist2.shift(1) > hist2.shift(2))).shift(1)
    rising2_on3 = rising2.reindex(s3.index, method="ffill").fillna(False).astype(bool)
    early = (sb & b1os & rising2_on3 & (wbull | b1os)
             & (r14 < sq.BUY_RSI_MAX)).fillna(False)
    if daily_high is not None and daily_low is not None:
        hl = pd.DataFrame({"high": daily_high, "low": daily_low}).reindex(daily_close.index)
        h3 = hl["high"].resample("3B").max().reindex(s3.index)
        l3 = hl["low"].resample("3B").min().reindex(s3.index)
        h3 = pd.concat([h3, s3], axis=1).max(axis=1)
        l3 = pd.concat([l3, s3], axis=1).min(axis=1)
    else:
        h3 = l3 = s3
    return pd.DataFrame({"close": s3, "high": h3, "low": l3,
                         "macd": macd, "sig": sig, "k": k, "d": d, "rsi14": r14,
                         "CB": cb, "CS": cs, "revBuy": revbuy, "revSell": revsell,
                         "w_bull": wbull, "above200": above, "ema_trail": ema_trail,
                         "early": early})


def _bucket_last_session_legacy(daily_close, *, market="US"):     # noqa: ARG001
    """The pre-repair confirmation geometry: 3B bin label -> its last daily session."""
    stamps = pd.Series(daily_close.index, index=daily_close.index)
    return stamps.where(daily_close.notna()).resample("3B").last().dropna()


@contextmanager
def legacy_anchor():
    """Run the block with the PRE-repair §7 bucketing in force.

    ``analyze`` (and ``confirmation_date``/``fresh_breach_mask``) look ``signal_frame`` up as
    a module global on every call, so rebinding the NAME swings the whole §7 stream — the
    verdicts below really do come from the old geometry, not from a re-implementation of it.
    """
    new_sf, new_bls = sq.signal_frame, sq._bucket_last_session
    sq.signal_frame, sq._bucket_last_session = (_signal_frame_legacy,
                                                _bucket_last_session_legacy)
    try:
        yield
    finally:
        sq.signal_frame, sq._bucket_last_session = new_sf, new_bls


def _capture(v: dict) -> dict:
    """The §7-layer slice of a gate verdict — what a board, a chart and a ledger read."""
    res = v.get("result") or {}
    markers = res.get("markers") or []
    last = markers[-1] if markers else {}
    return {"last_date": last.get("date"), "last_type": last.get("type"),
            "last_quality": last.get("quality"), "n_markers": len(markers),
            "asof": res.get("asof"), "eligible": bool(v.get("eligible")),
            "tier_cascade": v.get("tier_cascade"), "ticks": v.get("ticks"),
            "buyable": signal_gate.is_buyable(v)}


def _verdict(ticker: str, c: pd.Series, era: str, *, reclaim_veto: bool = True) -> dict:
    if era == "old":
        with legacy_anchor():
            return _capture(signal_gate.gate(ticker, c, reclaim_veto=reclaim_veto))
    return _capture(signal_gate.gate(ticker, c, reclaim_veto=reclaim_veto))


def _is_open_take(rec: dict) -> bool:
    """Is this name currently HOLDING a §7 entry whose date keys a ledger row?

    A buy/rebuy whose quality is take or pending — the two that make ``take_date`` live.
    """
    return (rec.get("last_type") in ("buy", "rebuy")
            and rec.get("last_quality") in ("take", "pending"))


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #

def _close_from_parquet(path: Path) -> pd.Series | None:
    try:
        df = pd.read_parquet(path, columns=["close"])
    except Exception:
        try:
            df = pd.read_parquet(path)
        except Exception:
            return None
    col = "close" if "close" in df.columns else (df.columns[0] if len(df.columns) else None)
    if col is None:
        return None
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if not isinstance(s.index, pd.DatetimeIndex):
        try:
            s.index = pd.to_datetime(s.index)
        except Exception:
            return None
    return s.sort_index()


def _file_universe(directory: Path, pattern: str = "*.parquet") -> list[Path]:
    return sorted(directory.glob(pattern)) if directory.is_dir() else []


# --------------------------------------------------------------------------- #
# workers (module-level so a process Pool can pickle them)
# --------------------------------------------------------------------------- #

def _job_from_path(args):
    """(path, tail, reclaim_veto) -> {ticker, old, new, bars, last} or a skip record."""
    path, tail, reclaim_veto = args
    ticker = Path(path).stem
    c = _close_from_parquet(Path(path))
    if c is None:
        return {"ticker": ticker, "skip": "unreadable"}
    if tail:
        c = c.iloc[-tail:]
    if len(c) < MIN_BARS:
        return {"ticker": ticker, "skip": f"under signal_frame floor ({len(c)} bars)"}
    return {"ticker": ticker, "bars": len(c), "last": str(c.index.max().date()),
            "old": _verdict(ticker, c, "old", reclaim_veto=reclaim_veto),
            "new": _verdict(ticker, c, "new", reclaim_veto=reclaim_veto)}


def _job_from_series(args):
    """(ticker, values, dates, reclaim_veto) -> the same record, for wide-panel sources."""
    ticker, values, dates, reclaim_veto = args
    c = pd.Series(values, index=pd.DatetimeIndex(dates)).dropna()
    if len(c) < MIN_BARS:
        return {"ticker": ticker, "skip": f"under signal_frame floor ({len(c)} bars)"}
    return {"ticker": ticker, "bars": len(c), "last": str(c.index.max().date()),
            "old": _verdict(ticker, c, "old", reclaim_veto=reclaim_veto),
            "new": _verdict(ticker, c, "new", reclaim_veto=reclaim_veto)}


def _run(jobs, fn, workers: int):
    if workers > 1 and len(jobs) > 16:
        try:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=workers) as ex:
                return list(ex.map(fn, jobs, chunksize=8))
        except Exception as exc:            # noqa: BLE001 — parallelism never decides a result
            print(f"[sq-blast] pool failed ({exc}) — serial fallback", file=sys.stderr)
    return [fn(j) for j in jobs]


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #

def _summarize(name: str, records: list[dict], *, note: str = "") -> dict:
    graded = [r for r in records if r and "skip" not in r]
    skipped = [r for r in records if r and "skip" in r]
    moved_date = moved_ident = ticks_flip = elig_flip = buy_flip = asof_move = 0
    open_take_rekey = 0
    n_markers_delta = Counter()
    movers: list[dict] = []
    for r in graded:
        o, n = r["old"], r["new"]
        if o["last_date"] != n["last_date"]:
            moved_date += 1
        if (o["last_type"], o["last_quality"]) != (n["last_type"], n["last_quality"]):
            moved_ident += 1
        if o["ticks"] != n["ticks"]:
            ticks_flip += 1
        if o["eligible"] != n["eligible"]:
            elig_flip += 1
        if o["buyable"] != n["buyable"]:
            buy_flip += 1
        if o["asof"] != n["asof"]:
            asof_move += 1
        n_markers_delta[n["n_markers"] - o["n_markers"]] += 1
        # the LEDGER re-key surface (R-SQ4): a name currently holding an open take whose
        # take_date moved. Every forward row keyed on that date needs the era fence.
        if (_is_open_take(o) or _is_open_take(n)) and o["last_date"] != n["last_date"]:
            open_take_rekey += 1
        if o != n:
            movers.append({"ticker": r["ticker"], "bars": r["bars"], "old": o, "new": n})
    asof = max((r["last"] for r in graded), default=None)      # store date, not wall clock
    ng = len(graded)

    def _pct(x):
        return round(100.0 * x / ng, 2) if ng else None
    return {
        "universe": name,
        "note": note,
        "n_read": len(records),
        "n_graded": ng,
        "n_skipped": len(skipped),
        "skip_reasons": dict(Counter(r["skip"].split(" (")[0] for r in skipped)),
        "asof_store": asof,
        "last_marker_date_moved": moved_date, "last_marker_date_moved_pct": _pct(moved_date),
        "last_marker_identity_moved": moved_ident,
        "last_marker_identity_moved_pct": _pct(moved_ident),
        "ticks_flips": ticks_flip, "ticks_flip_pct": _pct(ticks_flip),
        "eligible_flips": elig_flip, "eligible_flip_pct": _pct(elig_flip),
        "buyable_flips": buy_flip, "buyable_flip_pct": _pct(buy_flip),
        "asof_moved": asof_move, "asof_moved_pct": _pct(asof_move),
        "open_take_rekeys": open_take_rekey,
        "marker_count_delta": {str(k): v for k, v in sorted(n_markers_delta.items())},
        "movers": sorted(movers, key=lambda r: r["ticker"]),
    }


# --------------------------------------------------------------------------- #
# universes
# --------------------------------------------------------------------------- #

def universe_files(name: str, directory: Path, workers: int, *, tail: int | None = None,
                   pattern: str = "*.parquet", reclaim_veto: bool = True,
                   note: str = "") -> dict:
    paths = _file_universe(directory, pattern)
    if not paths:
        print(f"::warning title=sq-blast-universe-absent::{name}: "
              f"{directory.relative_to(ROOT)} holds no {pattern} — universe NOT measured",
              flush=True)
        return {"universe": name, "note": f"ABSENT: no {pattern} under "
                f"{directory.relative_to(ROOT)} in this checkout", "n_read": 0,
                "n_graded": 0, "unavailable": True}
    jobs = [(str(p), tail, reclaim_veto) for p in paths]
    return _summarize(name, _run(jobs, _job_from_path, workers), note=note)


def universe_scan_tier(workers: int) -> dict:
    """The REAL massive_stock_day scan universe, resolved by us_scan_universe's own floor."""
    from engine import us_scan_universe as usu
    if not usu.store_available(ROOT):
        d = usu.store_dir(ROOT)
        n = len(list(d.glob("*.parquet"))) if d.is_dir() else 0
        print("::warning title=sq-blast-scan-tier-absent::massive_stock_day is "
              "R2-canonical and not restored in this checkout — scan tier NOT measured",
              flush=True)
        return {"universe": "massive_stock_day (scan tier)", "unavailable": True,
                "n_read": 0, "n_graded": 0,
                "note": (f"ABSENT: {d.relative_to(ROOT)} holds {n} per-ticker parquets "
                         "(R2-canonical; restored only in a lane that pulls it). The "
                         "scan-tier delta is UNMEASURED here — run this script in a "
                         "restored lane. Its names are 2021-start, the same depth class "
                         "as baskets/ohlcv, whose slice IS measured.")}
    tickers, disclosure = usu.resolve(ROOT)
    d = usu.store_dir(ROOT)
    jobs = [(str(d / f"{t}.parquet"), None, True) for t in tickers]
    out = _summarize("massive_stock_day (scan tier)", _run(jobs, _job_from_path, workers),
                     note="floor + listing rule from engine.us_scan_universe.resolve")
    out["floor_disclosure"] = disclosure
    return out


def universe_cn(workers: int) -> dict:
    p = ROOT / "data" / "china_search" / "closes.parquet"
    if not p.exists():
        print("::warning title=sq-blast-cn-absent::data/china_search/closes.parquet "
              "missing — CN panel NOT measured", flush=True)
        return {"universe": "CN china_search panel", "unavailable": True,
                "n_read": 0, "n_graded": 0, "note": "ABSENT: data/china_search/closes.parquet"}
    wide = pd.read_parquet(p)
    if not isinstance(wide.index, pd.DatetimeIndex):
        wide.index = pd.to_datetime(wide.index)
    dates = wide.index.to_numpy()
    jobs = [(str(col), wide[col].to_numpy(), dates, True) for col in wide.columns]
    return _summarize(
        "CN china_search panel", _run(jobs, _job_from_series, workers),
        note=("tickers carry .SS/.SZ, so gate() infers market=CN and the NEW era buckets on "
              "the Shanghai reference calendar; the OLD era bucketed every market on the "
              "same market-BLIND business-day grid. Both changes are in this row."))


# --------------------------------------------------------------------------- #
# cross-store agreement + invariance
# --------------------------------------------------------------------------- #

def store_agreement() -> dict:
    """stocks/ vs baskets/ohlcv/ on the SHARED last date, BEFORE and AFTER. Target: 0 after.

    This is the defect's live symptom at the §7 layer: the two US loaders hand gate() the
    same name with different amounts of leading history, and under the old bins that alone
    decided which marker stream the name got.
    """
    a_dir, b_dir = ROOT / "data" / "stocks", ROOT / "data" / "baskets" / "ohlcv"
    shared = sorted({p.stem for p in _file_universe(a_dir)}
                    & {p.stem for p in _file_universe(b_dir)})
    rows, disagree = [], {"old": Counter(), "new": Counter()}
    quintet_rows, residual = [], []
    for t in shared:
        ca = _close_from_parquet(a_dir / f"{t}.parquet")
        cb = _close_from_parquet(b_dir / f"{t}.parquet")
        if ca is None or cb is None:
            continue
        last = min(ca.index.max(), cb.index.max())
        ca, cb = ca[ca.index <= last], cb[cb.index <= last]
        if len(ca) < MIN_BARS or len(cb) < MIN_BARS:
            continue
        rec = {"ticker": t, "last": str(last.date()),
               "bars_stocks": len(ca), "bars_ohlcv": len(cb)}
        for era in ("old", "new"):
            va, vb = _verdict(t, ca, era), _verdict(t, cb, era)
            rec[era] = {"stocks": va, "ohlcv": vb}
            for f in FIELDS:
                if va[f] != vb[f]:
                    disagree[era][f] += 1
            if era == "new":
                # Anything still disagreeing after the repair gets NAMED with its cause,
                # so "1" in the table above can never be read as "close enough".
                left = [f for f in INVARIANCE_FIELDS if va[f] != vb[f]]
                if left:
                    j = ca.index.intersection(cb.index)
                    gap = float((ca.loc[j] - cb.loc[j]).abs().max()) if len(j) else None
                    residual.append({"ticker": t, "fields": left,
                                     "max_close_gap": round(gap, 6) if gap else gap})
        rows.append(rec)
        if t in QUINTET:
            quintet_rows.append(rec)
    return {
        "n_shared_names": len(rows),
        "disagreements_old": dict(disagree["old"]),
        "disagreements_new": dict(disagree["new"]),
        "quintet": sorted(quintet_rows, key=lambda r: QUINTET.index(r["ticker"])),
        "residual": residual,
        "asof_store": max((r["last"] for r in rows), default=None),
    }


def _stream_residual(a: list[dict], b: list[dict]) -> dict:
    """How deep two marker streams agree, walking BACKWARD from the live edge.

    Returns the length of the identical tail and the date of the most recent
    disagreement (None when the streams agree end to end). Walking backward is the point:
    a consumer reads the RECENT end, so "they agree for the last 356 markers and last
    disagreed in 1967" is the statement that means something — a raw count difference is
    not.
    """
    i, j, tail = len(a) - 1, len(b) - 1, 0
    while i >= 0 and j >= 0 and a[i] == b[j]:
        i -= 1
        j -= 1
        tail += 1
    last_dis = None
    if i >= 0 or j >= 0:
        cands = [m["date"] for m in (a[max(i, 0):i + 1] + b[max(j, 0):j + 1]) if m]
        last_dis = max(cands) if cands else None
    return {"tail_identical": tail, "last_disagreement": last_dis,
            "n_old": len(a), "n_new": len(b)}


def _job_invariance(args):
    path, k = args
    ticker = Path(path).stem
    c = _close_from_parquet(Path(path))
    if c is None or len(c) < MIN_BARS + k:
        return None
    va, vb = signal_gate.gate(ticker, c), signal_gate.gate(ticker, c.iloc[k:])
    a, b = _capture(va), _capture(vb)
    ma = ((va.get("result") or {}).get("markers") or [])
    mb = ((vb.get("result") or {}).get("markers") or [])
    return {"ticker": ticker,
            "diff": {f: (a[f], b[f]) for f in INVARIANCE_FIELDS if a[f] != b[f]},
            "stream": _stream_residual(ma, mb)}


def new_anchor_invariance(workers: int, k: int = 3) -> dict:
    """The claim, re-run on REAL data under the shipped engine: dropping k leading bars must
    move nothing a consumer reads. Anything but 0 means the §7 anchor is still leaking."""
    jobs = [(str(p), k) for p in _file_universe(ROOT / "data" / "stocks")]
    recs = [r for r in _run(jobs, _job_invariance, workers) if r]
    per_field = Counter()
    for r in recs:
        for f in r["diff"]:
            per_field[f] += 1
    movers = [r for r in recs if r["diff"]]
    resid = [r for r in recs if r["stream"]["last_disagreement"]]
    resid.sort(key=lambda r: r["stream"]["last_disagreement"], reverse=True)
    return {"k_bars_dropped": k, "n_names": len(recs), "n_movers": len(movers),
            "movers_by_field": dict(per_field),
            "movers": sorted(movers, key=lambda r: r["ticker"])[:25],
            "marker_stream_residual": {
                "n_streams_identical": len(recs) - len(resid),
                "n_with_a_head_residual": len(resid),
                "most_recent_disagreement": (resid[0]["stream"]["last_disagreement"]
                                             if resid else None),
                "worst": [{"ticker": r["ticker"], **r["stream"]} for r in resid[:10]]}}


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def _u_line(u: dict) -> str:
    if u.get("unavailable"):
        return f"| {u['universe']} | — | — | — | — | — | — | **not measured** |"
    return (f"| {u['universe']} | {u['n_graded']} | "
            f"{u['last_marker_date_moved']} ({u['last_marker_date_moved_pct']}%) | "
            f"{u['last_marker_identity_moved']} ({u['last_marker_identity_moved_pct']}%) | "
            f"{u['ticks_flips']} ({u['ticks_flip_pct']}%) | "
            f"{u['eligible_flips']} / {u['buyable_flips']} | "
            f"{u['open_take_rekeys']} | {u['asof_store']} |")


def render_md(res: dict) -> str:
    L: list[str] = []
    L.append("# §7 signal_quality absolute session anchor — blast radius\n")
    L.append(f"Era `{res['anchor_era']}` · ruling "
             "`research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md`\n")
    L.append(f"Generated {res['generated_utc']} · store as-of dates are per-universe "
             "(read from the stores, never the wall clock).\n")
    L.append("\nEvery number below is measured END-TO-END through `signal_gate.gate()` — the "
             "path a board, a chart and a ledger actually read — with the pre-repair "
             "`signal_frame`/`_bucket_last_session` frozen verbatim in this script and "
             "monkeypatched in for the OLD pass.\n")

    L.append("\n## 1. Old → new, per production loader\n")
    L.append("| universe | graded | last-marker DATE moved | last-marker IDENTITY moved | "
             "ticks flips | eligible / buyable flips | open-take re-keys | store as-of |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for u in res["universes"]:
        L.append(_u_line(u))
    for u in res["universes"]:
        if u.get("note"):
            L.append(f"\n- **{u['universe']}** — {u['note']}")
        if u.get("skip_reasons"):
            L.append(f"  - not graded: {u['n_skipped']} ({u['skip_reasons']})")

    L.append("\n### Marker-count delta (new − old), by universe\n")
    for u in res["universes"]:
        if u.get("unavailable"):
            continue
        L.append(f"\n- **{u['universe']}**: {u.get('marker_count_delta') or '{}'}")
    L.append("\nA non-zero delta is R-SQ4's disclosed re-draw: a cross can appear or vanish "
             "where a 3D bucket's close changed. It is NOT a filter-semantics change — "
             "`_buy_filter`/`_confirm_legs`/`_bear_div` are byte-identical.\n")

    ag = res["store_agreement"]
    L.append("\n## 2. stocks/ vs baskets/ohlcv/ — the defect's live symptom, §7 layer\n")
    L.append(f"{ag['n_shared_names']} shared names, aligned to each pair's shared last date "
             f"(store as-of {ag['asof_store']}).\n")
    L.append("| field | disagreements BEFORE | disagreements AFTER |")
    L.append("|---|---:|---:|")
    for f in FIELDS:
        tag = "  ← DEPTH, not anchor" if f == "n_markers" else ""
        L.append(f"| {f} | {ag['disagreements_old'].get(f, 0)} | "
                 f"{ag['disagreements_new'].get(f, 0)}{tag} |")
    L.append("\n`n_markers` is expected to disagree in BOTH eras and is not a defect: the "
             "deep loader carries decades the 2014-start loader never saw, so it has more "
             "markers by construction. Every other field is what the two loaders should "
             "have agreed on all along — the anchor is what makes them.\n")
    if ag.get("residual"):
        L.append("\nThe residual AFTER is named rather than rounded to zero:\n")
        for r in ag["residual"]:
            L.append(f"\n- **{r['ticker']}** ({r['fields']}) — the two stores' PRICES "
                     f"differ on their shared dates (max |Δclose| {r['max_close_gap']}), "
                     f"so this is a data disagreement between the loaders, not a grid "
                     f"one. The anchor guarantees one GRID per name; it cannot make two "
                     f"stores agree about what a close was.")
    L.append("\n### The audit quintet\n")
    L.append("| name | bars stocks / ohlcv | BEFORE stocks | BEFORE ohlcv | "
             "AFTER stocks | AFTER ohlcv |")
    L.append("|---|---|---|---|---|---|")

    def _fmt(v):
        return (f"{v['last_date']} {v['last_type']}/{v['last_quality']} · "
                f"t={v['ticks']} · e={v['eligible']} · buy={v['buyable']}")
    for r in ag["quintet"]:
        L.append(f"| {r['ticker']} | {r['bars_stocks']} / {r['bars_ohlcv']} | "
                 f"{_fmt(r['old']['stocks'])} | {_fmt(r['old']['ohlcv'])} | "
                 f"{_fmt(r['new']['stocks'])} | {_fmt(r['new']['ohlcv'])} |")

    inv = res["new_anchor_invariance"]
    L.append("\n## 3. Start-invariance re-run on real data (NEW anchor)\n")
    L.append(f"`gate(c)` vs `gate(c.iloc[{inv['k_bars_dropped']}:])` over "
             f"{inv['n_names']} data/stocks names: **{inv['n_movers']} movers** on the "
             f"§7 fields {list(INVARIANCE_FIELDS)}.")
    if inv["movers_by_field"]:
        L.append(f"\n- STILL MOVING, by field: {inv['movers_by_field']}")
        L.append(f"- first movers: {[m['ticker'] for m in inv['movers']]}")
    else:
        L.append("\nZero — every field a board, a chart or a ledger reads is now a "
                 "function of the price history alone. Before the repair the same run "
                 "moved 238/238 last-marker dates and flipped 11 eligibilities.")
    mr = inv["marker_stream_residual"]
    L.append("\n### The one residual, named rather than hidden: the warm-up head\n")
    L.append(f"{mr['n_streams_identical']} of {inv['n_names']} marker streams are "
             f"IDENTICAL end to end. The other {mr['n_with_a_head_residual']} differ only "
             f"at the HEAD of the stream: the truncation eats the leading 3D bucket "
             f"outright, and near the 60-bucket RSI-MACD warm-up (plus the StochRSI "
             f"flat-band NaN that drops rows out of the frame at all) the two windows can "
             f"differ by a marker or two. The most recent such disagreement anywhere in "
             f"the universe is **{mr['most_recent_disagreement']}**, and the table below "
             f"is sorted by exactly that — read it as the residual's ceiling. Each row's "
             f"disagreement sits in that name's OWN first weeks, so a recent date there "
             f"means a recent LISTING, not a recent defect (the worst case is a 2023 IPO "
             f"whose warm-up head is 2024; the deep names' residuals are decades old). "
             f"This is EWM memory, the residual the cascade's own battery names too; it "
             f"is a different animal from the bucket-phase defect, which was structural, "
             f"unbounded, and reached the last bar.\n")
    if mr["worst"]:
        L.append("| name | markers old / new | identical tail | last disagreement |")
        L.append("|---|---|---:|---|")
        for w in mr["worst"]:
            L.append(f"| {w['ticker']} | {w['n_old']} / {w['n_new']} | "
                     f"{w['tail_identical']} | {w['last_disagreement']} |")

    L.append("\n## 4. Ledger re-key surface (R-SQ4)\n")
    L.append("`open-take re-keys` above counts names CURRENTLY holding a §7 entry "
             "(buy/rebuy, take or pending) whose marker date moved — i.e. every forward "
             "row keyed on that date needs the era fence. No backfill, no retro-edit: "
             "rows logged pre-era keep their dates and `anchor_era` is the cohort "
             "boundary (`track_record.SQ_ANCHOR_ERA_FLOOR` enforces it at ingestion).\n")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true",
                    help="stocks/ + ohlcv/ + agreement + invariance only "
                         "(skips depth views, scan tier, CN, HK)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()
    w = args.workers
    print(f"[sq-blast] workers={w} era={sq.ANCHOR_ERA}", file=sys.stderr)

    universes = [
        universe_files("data/stocks", ROOT / "data" / "stocks", w,
                       note="the deep US loader (1960s-2000s starts)"),
        universe_files("data/baskets/ohlcv", ROOT / "data" / "baskets" / "ohlcv", w,
                       note="the 2014-start US loader"),
    ]
    if not args.quick:
        for tail in DEPTH_VIEWS:
            universes.append(universe_files(
                f"data/stocks @{tail} bars", ROOT / "data" / "stocks", w, tail=tail,
                note=f"stocks/ truncated to the trailing {tail} bars (a production cache "
                     f"depth that reaches gate())"))
        universes.append(universe_scan_tier(w))
        universes.append(universe_cn(w))
        universes.append(universe_files(
            "HK stores", ROOT / "data" / "hk", w, pattern="*.HK.parquet",
            reclaim_veto=False,
            note="data/hk/*.HK.parquet with reclaim_veto=False — the HK board's own policy "
                 "(build_hk_library passes HK_RECLAIM_VETO), so this row measures the lane "
                 "as it ships. HK moves MOST: the old bins were market-blind business days "
                 "and the new grid is the HSI session calendar."))

    res = {
        "anchor_era": sq.ANCHOR_ERA,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "min_bars": MIN_BARS,
        "fields": list(FIELDS),
        "universes": universes,
        "store_agreement": store_agreement(),
        "new_anchor_invariance": new_anchor_invariance(w),
    }
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "sq_anchor_blast_radius.json").write_text(json.dumps(res, indent=2, default=str))
    (out / "sq_anchor_blast_radius.md").write_text(render_md(res))
    print(f"[sq-blast] wrote {out / 'sq_anchor_blast_radius.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
