#!/usr/bin/env python3
"""Census: CN Prophet board picks whose qualifying signal was ERASED, not aged out.

WHY THIS EXISTS.  On 2026-08-06 the board's #1 name of the previous session — 300363.SZ
博腾股份, prophet 90.32, featured, buy zone 16.52-17.60 — was absent from all seven lanes with
no departure notice.  It closed +20.02% (the ChiNext limit) the next session.  The pick itself
was never lost: ``data/china_standout_track/board.parquet`` is keep-first PIT and holds the row
(rank 1, cn_prophet_v2, fill_basis t1_hl2), and ``china_standout_track.grade()`` matures rows
straight off that store without consulting the live board, so an erased name still grades.
What was lost was the OPERATOR'S LINE OF SIGHT on a live pick, for one session, silently.

THE DISCRIMINATOR.  A name leaving the board is normal — the shelf is explicitly "just-crossed
only" (``confluence_tiers.FRESH_TICKS``).  What is not normal is a qualifying event that a
previous run SAW and a later run, on the same history plus one bar, no longer sees:

    event(D')  <  event(D)   -> ERASED: a bar that already printed lost its annotation
    event(D') == event(D)    -> AGED OUT: by design, the tick counter simply advanced

Measured on the 2026-08-05 -> 2026-08-06 transition, on the engine revision that actually
built those boards (3b19189d17d): 85 names left the board, 42 lost buyability, and of those
40 aged out with an UNCHANGED event date.  Exactly 2 were erased — 300363.SZ and 300059.SZ,
both from the 17-name buy shelf.

THE MECHANISM.  ``confluence_tiers._to_daily`` stamps each timeframe bucket's value onto the
daily bar equal to that bucket's known-date (its last session).  The trailing bucket is
INCOMPLETE, so its known-date advances every session while the bucket stays open:

    3D bucket X -> known 2026-08-05   (run of 08-05)   ... bar 08-05 carries recent3 = True
    3D bucket X -> known 2026-08-06   (run of 08-06)   ... bar 08-05 now ffills from 08-03

The 2D cross event stays pinned to its own (closed) bucket, but its 3D partner leg walks off
the bar underneath it, so the T2 conjunction at ``confluence_tiers.py`` (t2_buy) un-fires on a
bar that already printed.  The last surviving event then falls back many ticks, blows the
freshness window, and the name drops out of every lane at once.

NOT CLOSED BY THE ANCHOR REPAIR.  PRs #4732/#4799 (era abs-session-2026-08-06) re-anchored the
2D/3D grid to the absolute session calendar, which fixed bin PHASE — the grid no longer moves
with loaded history depth.  It did NOT change bucket COMPLETION: the trailing bucket is still
open and its known-date still advances (verified directly on 300363.SZ), and the ``_to_daily``
stamping is unchanged.  Running this census on origin/main AFTER both PRs still finds the
family firing: 86 erasure events across 78 names in 12 sessions.

MARKET CALENDAR.  ``_tf_bars(daily, n, market)`` defaults to the US session calendar.
``signal_gate.gate()`` resolves it properly via ``session_anchor.market_for_ticker``; a bare
``_tf_bars(c, n)`` buckets A-shares on the wrong grid entirely and makes this census measure
nothing.  Always pass the resolved market.

Usage:
    python3 scripts/research/cn_board_erasure_census.py [--sessions 12] [--out PATH]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import engine.confluence_tiers as ct  # noqa: E402
from engine import session_anchor  # noqa: E402

FWD_HORIZONS = (1, 3, 5)


def last_t2_event(close: pd.Series, market: str) -> str | None:
    """Date of the most recent T2 confluence event as a run holding ``close`` sees it.

    Rebuilds the conjunction ``cascade()`` evaluates for its T2 leg — the 2D RSI-MACD cross
    event AND the 3D StochRSI recency AND the weekly/from-oversold confirmation AND the RSI
    ceiling — on the daily grid, through the same ``_to_daily`` known-date stamping that
    carries the defect.  Returns None when no event survives anywhere in the history.
    """
    di = close.index
    sm, smk = ct._tf_bars(close, 2, market)
    ss3, sk3 = ct._tf_bars(close, 3, market)
    m2, s2 = ct._rsi_macd(sm)
    mb2 = ct._xup(m2, s2)
    k3, d3 = ct._stoch_rsi_kd(ss3)
    recent3 = ct._since(ct._xup(k3, d3)) <= ct.CONF_W
    fromos3 = d3.rolling(ct.CONF_W).min() < ct.OS
    r14 = ct.rsi(ss3, ct.RSI_LEN)
    wk = close.resample("W-FRI").last().dropna()
    wm, ws = ct._rsi_macd(wk)
    wbull = (wm >= ws).shift(1)

    def td(series, known, how="ffill"):
        return ct._to_daily(series, known, di, how)

    ev = (td(mb2.fillna(False), smk, "event")
          & td(recent3.fillna(False), sk3).fillna(False)
          & (wbull.reindex(di, method="ffill").fillna(False).astype(bool)
             | td(fromos3.fillna(False), sk3).fillna(False))
          & (td(r14, sk3) < ct.BUY_RSI_MAX).fillna(False)).fillna(False)
    hits = np.where(ev.to_numpy())[0]
    return str(di[int(hits[-1])].date()) if len(hits) else None


def scan_one(path: str, sessions: int) -> list[dict]:
    """Walk a name's trailing sessions, re-running the event scan with history truncated at
    each one, and emit a row wherever the event date moved BACKWARD."""
    ticker = os.path.basename(path).replace(".parquet", "")
    try:
        df = pd.read_parquet(path).sort_index()
    except Exception:
        return []
    if "close" not in df.columns or len(df) < ct.MIN_HISTORY + 5:
        return []
    try:
        market = session_anchor.market_for_ticker(ticker)
    except Exception:
        market = "CN"
    close = df["close"].dropna()
    rows: list[dict] = []
    prev_event, prev_date = None, None
    for day in close.index[-sessions:]:
        try:
            event = last_t2_event(close.loc[:day], market)
        except Exception:
            prev_event, prev_date = None, None
            continue
        if prev_event and (event is None or event < prev_event):
            i = close.index.get_loc(day)
            px = float(close.iloc[i])
            fwd = {}
            for h in FWD_HORIZONS:
                j = i + h
                fwd[f"fwd{h}_pct"] = (round((float(close.iloc[j]) / px - 1) * 100, 2)
                                      if j < len(close) else None)
            rows.append(dict(ticker=ticker, market=market,
                             asof_prev=str(prev_date.date()), asof=str(day.date()),
                             event_prev=prev_event, event_now=event,
                             close_at_erasure=round(px, 3), **fwd))
        prev_event, prev_date = event, day
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", type=int, default=12,
                    help="trailing sessions to walk per name (default 12)")
    ap.add_argument("--glob", default="data/china_stocks/*.parquet")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    files = sorted(glob.glob(args.glob))
    if not files:
        print(f"::warning title=cn-erasure-census::no price files matched {args.glob}",
              flush=True)
        return 0
    print(f"universe {len(files)} names | trailing {args.sessions} sessions", flush=True)

    out: list[dict] = []
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 4) - 2)) as ex:
        futures = [ex.submit(scan_one, f, args.sessions) for f in files]
        for done, fut in enumerate(as_completed(futures), 1):
            try:
                out.extend(fut.result())
            except Exception:
                pass
            if done % 300 == 0:
                print(f"  {done}/{len(files)} ... {len(out)} erasures", flush=True)

    df = pd.DataFrame(out)
    print(f"\n{len(df)} erasure events across "
          f"{df.ticker.nunique() if len(df) else 0} names", flush=True)
    if len(df):
        print(df.groupby("asof").size().to_string(), flush=True)
        # A GitHub annotation must START the line and must not go through a logger — every
        # builder here logs with a prefixing format, which silently swallows the directive.
        print(f"::warning title=cn-board-erasure::{len(df)} confluence events erased across "
              f"{df.ticker.nunique()} names in the trailing {args.sessions} sessions "
              f"(a fired event un-fired on a bar that already printed)", flush=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out, index=False)
        print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
