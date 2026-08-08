"""Outage-window stamp audit — did the blackout put RUN dates on SIGNAL events?

`daily.yml` was dead 2026-08-03..08-06 and artifacts published days after the sessions
they describe. This script re-derives, for every date stamped inside the window, the date
the event was actually KNOWABLE, and prices both anchors, so the drift is measured rather
than assumed.

Three stamped surfaces are audited:

  1. Golden Oracle chart markers  — `site/signals/<T>.json` `markers[].date`
  2. Prophet plans                — `site/prophet/index.json` `plans[]._signal_date`
  3. Prophet forward ledger       — `data/prophet/ledger.jsonl` `signal_date`

The truth anchor for a marker is its own 3D bucket's LAST session
(`engine.signal_quality.marker_last_session`): the bucket's value is its last close, so the
signal is knowable when that session closes. `date` is the bucket's OPEN label (R-SQ2) and
precedes it by up to two sessions. Both are correct fields; reading one as the other is the
defect. The marker rows are additionally TRUNCATION-REPLAYED — the tape is cut at each
candidate session and `analyze` re-run — so the audit reports the first session a run could
have seen the marker, not merely the arithmetic.

Read-only. Writes nothing but its own report:
    python3 research/prophet_us_audit/outage_window_stamp_audit.py [--out <md>] [--json <json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from engine import signal_quality as sq  # noqa: E402
from lib import nyse_calendar  # noqa: E402

WINDOW_LO, WINDOW_HI = "2026-08-03", "2026-08-08"
OUTAGE_NOTE = ("daily.yml collect job dead 2026-08-03..08-06; artifacts frozen at "
               "as_of 07-31 through 08-07; unfreeze commit 3cbef39a6 at 2026-08-08T04:14Z")


def _sessions() -> list[str]:
    return [str(d) for d in nyse_calendar.sessions_between(date(2026, 1, 1), date(2026, 12, 31))]


_SESSION_LIST = _sessions()
_SESSION_POS = {s: i for i, s in enumerate(_SESSION_LIST)}


def _session_gap(a: str | None, b: str | None) -> int | None:
    """Sessions between two dates (b - a). None when either is not a trading session."""
    if a is None or b is None:
        return None
    if a not in _SESSION_POS or b not in _SESSION_POS:
        return None
    return _SESSION_POS[b] - _SESSION_POS[a]


def _tape(ticker: str) -> pd.Series | None:
    p = ROOT / "data" / "stocks" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)["close"].dropna()
    except Exception:
        return None


def _close_on(close: pd.Series, day: str | None) -> float | None:
    if close is None or day is None:
        return None
    try:
        stamp = pd.Timestamp(day)
    except (TypeError, ValueError):
        return None
    if stamp not in close.index:
        return None
    return round(float(close.loc[stamp]), 4)


def _pct(a: float | None, b: float | None) -> float | None:
    """Move from the stamped-basis price to the true-basis close, in percent."""
    if a is None or b is None or a == 0:
        return None
    return round((b - a) / a * 100.0, 4)


def _replay_first_seen(ticker: str, close: pd.Series, marker_date: str,
                       true_date: str | None) -> str | None:
    """Truncation replay: the first session whose tape makes this marker appear.

    Cuts the tape at each session from the marker's own label through the bucket close and
    re-runs `analyze`. Returns None when no truncation reproduces it (the marker is only
    visible on a longer tape than the window covers).
    """
    upper = true_date or marker_date
    candidates = [s for s in _SESSION_LIST if marker_date <= s <= upper]
    for session in candidates:
        cut = close[close.index <= pd.Timestamp(session)]
        if len(cut) < 300:
            continue
        try:
            res = sq.analyze(ticker, cut)
        except Exception:
            continue
        if res and any(m["date"] == marker_date for m in res.get("markers", [])):
            return session
    return None


def audit_markers(replay: bool = True) -> list[dict]:
    rows: list[dict] = []
    for path in sorted((ROOT / "site" / "signals").glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except Exception:
            continue
        hits = [m for m in doc.get("markers", [])
                if WINDOW_LO <= str(m.get("date", ""))[:10] <= WINDOW_HI]
        if not hits:
            continue
        ticker = path.stem
        close = _tape(ticker)
        if close is None:
            continue
        for m in hits:
            stamped = str(m["date"])[:10]
            ls = sq.marker_last_session(close, stamped)
            true_date = str(ls.date()) if ls is not None else None
            p_stamped = _close_on(close, stamped)
            p_true = _close_on(close, true_date)
            rows.append({
                "surface": "signals_marker",
                "ticker": ticker,
                "type": m.get("type"),
                "quality": m.get("quality"),
                "stamped_date": stamped,
                "true_date": true_date,
                "drift_sessions": _session_gap(stamped, true_date),
                "price_stamped_basis": p_stamped,
                "price_true_basis": p_true,
                "price_move_pct": _pct(p_stamped, p_true),
                "published_asof": doc.get("asof"),
                "replay_first_seen": (_replay_first_seen(ticker, close, stamped, true_date)
                                      if replay else None),
            })
    return rows


def audit_plans() -> list[dict]:
    idx = ROOT / "site" / "prophet" / "index.json"
    if not idx.exists():
        return []
    doc = json.loads(idx.read_text())
    board_asof = doc.get("asof")
    rows: list[dict] = []
    for p in doc.get("plans") or []:
        stamped = str(p.get("_signal_date") or p.get("signal_date") or "")[:10]
        if not (WINDOW_LO <= stamped <= WINDOW_HI):
            continue
        ticker = p.get("asset") or p.get("ticker")
        close = _tape(ticker)
        sig_path = ROOT / "site" / "signals" / f"{ticker}.json"
        own_marker = own_true = None
        if sig_path.exists():
            try:
                buys = [m for m in json.loads(sig_path.read_text()).get("markers", [])
                        if m.get("type") in ("buy", "rebuy")]
            except Exception:
                buys = []
            if buys:
                own_marker = str(buys[-1]["date"])[:10]
                if close is not None:
                    ls = sq.marker_last_session(close, own_marker)
                    own_true = str(ls.date()) if ls is not None else None
        p_stamped = _close_on(close, stamped) if close is not None else None
        p_true = _close_on(close, own_true) if close is not None else None
        rows.append({
            "surface": "prophet_plan",
            "ticker": ticker,
            "plan_id": p.get("id"),
            "stamped_date": stamped,
            "board_asof": board_asof,
            "own_last_buy_marker": own_marker,
            "true_date": own_true,
            "drift_sessions": _session_gap(stamped, own_true),
            "price_stamped_basis": p_stamped,
            "price_true_basis": p_true,
            "price_move_pct": _pct(p_stamped, p_true),
        })
    return rows


def audit_ledger() -> tuple[list[dict], dict]:
    path = ROOT / "data" / "prophet" / "ledger.jsonl"
    rows_all: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows_all.append(json.loads(line))
        except Exception:
            continue
    in_window = []
    for r in rows_all:
        stamped = str(r.get("signal_date") or "")[:10]
        if not (WINDOW_LO <= stamped <= WINDOW_HI):
            continue
        ticker = r.get("asset")
        close = _tape(ticker)
        sig_path = ROOT / "site" / "signals" / f"{ticker}.json"
        true_date = None
        if close is not None and sig_path.exists():
            ls = sq.marker_last_session(close, stamped)
            true_date = str(ls.date()) if ls is not None else None
        in_window.append({
            "surface": "prophet_ledger",
            "ticker": ticker,
            "id": r.get("id"),
            "stamped_date": stamped,
            "true_date": true_date,
            "drift_sessions": _session_gap(stamped, true_date),
            "price_stamped_basis": _close_on(close, stamped) if close is not None else None,
            "price_true_basis": _close_on(close, true_date) if close is not None else None,
            "outcome": r.get("outcome"),
            "asof": r.get("asof"),
        })
    touching = [r for r in rows_all
                if any(WINDOW_LO <= str(r.get(k) or "")[:10] <= WINDOW_HI
                       for k in ("signal_date", "entry_date", "close_date"))]
    return in_window, {"rows_total": len(rows_all),
                       "rows_signal_date_in_window": len(in_window),
                       "rows_any_date_in_window": len(touching)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=None, help="write the machine-readable result here")
    ap.add_argument("--no-replay", action="store_true", help="skip the truncation replay")
    args = ap.parse_args()

    markers = audit_markers(replay=not args.no_replay)
    plans = audit_plans()
    ledger_rows, ledger_stats = audit_ledger()

    def _drifted(rows):
        return [r for r in rows if r.get("drift_sessions") not in (0, None)]

    payload = {
        "window": [WINDOW_LO, WINDOW_HI],
        "outage": OUTAGE_NOTE,
        "generated_for": "research/prophet_us_audit/OUTAGE_WINDOW_STAMP_AUDIT_2026-08-08.md",
        "markers": {"n": len(markers), "n_drifted": len(_drifted(markers)), "rows": markers},
        "plans": {"n": len(plans), "n_drifted": len(_drifted(plans)), "rows": plans},
        "ledger": dict(ledger_stats, rows=ledger_rows,
                       n_drifted=len(_drifted(ledger_rows))),
    }
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=1))

    print(f"window {WINDOW_LO}..{WINDOW_HI}")
    for name in ("markers", "plans"):
        blk = payload[name]
        print(f"  {name}: {blk['n']} stamped, {blk['n_drifted']} with drift != 0")
    print(f"  ledger: {ledger_stats['rows_total']} rows, "
          f"{ledger_stats['rows_signal_date_in_window']} with signal_date in window, "
          f"{ledger_stats['rows_any_date_in_window']} with ANY date in window")
    for r in markers[:5]:
        print(f"    {r['ticker']:6s} {r['stamped_date']} -> {r['true_date']} "
              f"drift={r['drift_sessions']} {r['price_stamped_basis']} -> "
              f"{r['price_true_basis']} ({r['price_move_pct']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
