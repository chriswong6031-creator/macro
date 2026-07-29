"""scripts/reconcile_prophet_live.py — nightly Prophet Live event reconciler (P0 D4).

Turns the day's intraday event spool into the forward ledger that the §5/§6
promotion gauntlet will eventually be pre-registered on:
``data/prophet_live/forward.parquet``. It is the ENTIRE evidence base for the
operator's "acting at the intraday cross beats the graded next-close fill"
hypothesis, and it accrues from week one with no user surface attached.

    python -m scripts.reconcile_prophet_live --nightly [--pack PATH] [--now ISO]

WHAT IT JOINS, per event row:
  * ``confirmed`` — did tonight's REAL gate verdict put the name in a buyable tier?
    Tonight's freshly built armed pack IS that verdict set (``center_buyable``), so
    the reconciler runs immediately after the pack build and needs no second gate
    pass.
  * ``close_same_day`` — the actual close of the session the event fired in.
  * ``next_close_fill`` — the official fill: the close of the bar STRICTLY AFTER the
    event's session, mirroring :func:`engine.grading.fill_index` (grade_us_board's
    next-bar convention). Filled on a LATER night, when that bar exists — the row is
    written the night of the event with a null fill and matured in place.

SOLE WRITER (G0.2/RUL-P10). This nightly step is the only writer of
``data/prophet_live/``. The intraday lane writes R2 only. Rows are merged
union-style on ``(date, ticker, kind)`` and updated field-wise, so a rebake or a
double run is idempotent and can only ever ADD information — a re-read that no
longer carries a fill never erases one.

Non-fatal by construction: every failure prints a bare ``::warning`` and returns 0.
A reconciler that reddens the nightly is worse than one that skips a day, because
the spool it reads is durable in R2 and the next night picks the day back up.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, _CODE_ROOT)

from engine.prophet_live import r2io  # noqa: E402

log = logging.getLogger("reconcile_prophet_live")

SCHEMA = "prophet_live.forward/v1"
LEDGER_REL = Path("data") / "prophet_live" / "forward.parquet"

#: The merge identity. One row per (session, name, transition kind): a name that
#: forms, fades and re-forms in a day contributes one row per kind, and the LAST
#: occurrence of that kind wins its price/time fields.
KEY = ["date", "ticker", "kind"]

#: Columns that mature later. groupby-last keeps the newest NON-NULL value per
#: column, which is what makes "write the row tonight, fill it in on a later
#: night" idempotent instead of destructive.
_MATURING = ("confirmed", "close_same_day", "next_close_fill", "next_close_date",
             "fill_vs_cross_pct", "close_vs_cross_pct")


def _iso(now: datetime) -> str:
    t = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ─────────────────────────────────────────────────────────────────────────────
# Spool
# ─────────────────────────────────────────────────────────────────────────────

def spool_sessions(*, s3=None, prefix: str = r2io.EVENTS_PREFIX,
                   sessions: list[str] | None = None) -> dict[str, list[str]]:
    """``{session_date: [object keys]}`` under the events prefix."""
    out: dict[str, list[str]] = {}
    for key in r2io.list_keys(prefix + "/", s3=s3):
        parts = key[len(prefix):].strip("/").split("/")
        if len(parts) != 2 or not parts[1].endswith(".json"):
            continue
        sess = parts[0]
        if sessions is not None and sess not in sessions:
            continue
        out.setdefault(sess, []).append(key)
    return {k: sorted(v) for k, v in sorted(out.items())}


def load_events(keys: list[str], *, s3=None) -> list[dict[str, Any]]:
    """Every event row from a session's pass objects, in pass order."""
    rows: list[dict[str, Any]] = []
    for key in keys:
        obj = r2io.get_json(key, s3=s3, allow_public=False)
        if not isinstance(obj, dict):
            continue
        for ev in obj.get("events") or []:
            if not isinstance(ev, dict) or not ev.get("ticker") or not ev.get("kind"):
                continue
            rows.append({**ev, "_spool_key": key,
                         "session_et": obj.get("session_et"),
                         "pack_as_of": obj.get("pack_as_of")})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Price joins
# ─────────────────────────────────────────────────────────────────────────────

def load_closes(tickers: set[str]) -> dict[str, Any]:
    """Close series for the named tickers, from the SAME universe the gate reads.

    Reusing ``build_stock_library.universe()`` is deliberate: a second loader would
    be a second definition of the price basis, and a fill graded off a different
    series than the signal was armed on is the mixed-basis trap.
    """
    from engine.prophet_live.armed_pack import clean_closes  # noqa: PLC0415
    from scripts.build_stock_library import universe  # noqa: PLC0415
    out: dict[str, Any] = {}
    for tkr, close, _high, _name, _sector in universe():
        if tkr not in tickers:
            continue
        s = clean_closes(close)
        if s is not None and len(s):
            out[tkr] = s
    return out


def close_on(series: Any, day: str) -> float | None:
    """The close of session ``day`` for this name, or None when there is no such bar."""
    import pandas as pd  # noqa: PLC0415
    try:
        target = pd.Timestamp(day).normalize()
        idx = pd.DatetimeIndex(series.index).normalize()
        hit = series[idx == target]
        return float(hit.iloc[-1]) if len(hit) else None
    except Exception:  # noqa: BLE001
        return None


def next_close(series: Any, day: str) -> tuple[float | None, str | None]:
    """The official fill: close of the bar STRICTLY AFTER ``day``.

    Delegates the offset to :func:`engine.grading.fill_index` so this ledger and
    ``grade_us_board`` cannot drift apart on what "the fill" means. None when the
    bar does not exist yet — the row stays open and matures on a later night.
    """
    try:
        import pandas as pd  # noqa: PLC0415
        from engine.grading import fill_index  # noqa: PLC0415
        loc = fill_index(series, pd.Timestamp(day))
        if loc is None:
            return None, None
        return float(series.iloc[loc]), str(pd.Timestamp(series.index[loc]).date())
    except Exception as exc:  # noqa: BLE001
        log.warning("reconcile_prophet_live: next_close failed for %s: %s", day, exc)
        return None, None


def _pct(a: float | None, b: float | None) -> float | None:
    """``a`` relative to ``b``, in percent. None unless both are usable."""
    try:
        if a is None or b is None or float(b) == 0.0:
            return None
        return (float(a) / float(b) - 1.0) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def build_rows(events: list[dict[str, Any]], *, verdicts: dict[str, bool],
               closes: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """One ledger row per (session, ticker, kind) — last occurrence of the kind wins."""
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for ev in events:
        tkr = str(ev["ticker"]).upper()
        day = str(ev.get("session_et") or "")[:10]
        kind = str(ev["kind"])
        if not day:
            continue
        series = closes.get(tkr)
        same = close_on(series, day) if series is not None else None
        nxt, nxt_day = next_close(series, day) if series is not None else (None, None)
        cross = ev.get("price")
        rows[(day, tkr, kind)] = {
            "date": day,
            "ticker": tkr,
            "kind": kind,
            "ts": ev.get("ts"),
            "cross_px": float(cross) if cross is not None else None,
            "quote_age_min": ev.get("quote_age_min"),
            "passes": ev.get("passes"),
            "from_state": ev.get("from"),
            "pack_as_of": ev.get("pack_as_of"),
            # None, not False: "tonight's pack did not carry this name" is not the
            # same claim as "tonight's gate rejected it".
            "confirmed": verdicts.get(tkr),
            "close_same_day": same,
            "next_close_fill": nxt,
            "next_close_date": nxt_day,
            "close_vs_cross_pct": _pct(same, cross),
            # The measurement the whole program exists to make: the official graded
            # fill is the NEXT close, so this is what a same-session entry gave up
            # or gained against the convention the track record uses.
            "fill_vs_cross_pct": _pct(nxt, cross),
            "reconciled_at": _iso(now),
        }
    return list(rows.values())


# ─────────────────────────────────────────────────────────────────────────────
# Ledger
# ─────────────────────────────────────────────────────────────────────────────

def merge_ledger(path: Path, rows: list[dict[str, Any]]):
    """Union-merge ``rows`` into the parquet on :data:`KEY`, field-wise newest-wins.

    ``groupby(KEY).last()`` keeps the last NON-NULL value per column, so a maturing
    fill lands without erasing anything the earlier write already knew, and running
    the reconciler twice produces a byte-identical frame.
    """
    import pandas as pd  # noqa: PLC0415
    new = pd.DataFrame(rows)
    if new.empty:
        return pd.read_parquet(path) if path.exists() else new
    hist = pd.DataFrame()
    if path.exists():
        try:
            hist = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=prophet-live-reconcile::existing ledger unreadable "
                  f"({exc}) — starting a new frame beside it", flush=True)
            hist = pd.DataFrame()
    combined = pd.concat([hist, new], ignore_index=True) if len(hist) else new
    for col in KEY:
        combined[col] = combined[col].astype(str)
    out = combined.groupby(KEY, as_index=False, sort=True).last()
    return out.sort_values(KEY, kind="stable").reset_index(drop=True)


def open_rows(path: Path) -> list[tuple[str, str]]:
    """``(date, ticker)`` pairs whose fill has not matured yet — the re-visit list."""
    import pandas as pd  # noqa: PLC0415
    if not path.exists():
        return []
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return []
    if df.empty or "next_close_fill" not in df.columns:
        return []
    todo = df[df["next_close_fill"].isna()]
    return sorted({(str(r.date), str(r.ticker)) for r in todo.itertuples()})


def maturing_rows(path: Path, *, closes: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """Fill-only updates for rows whose next-session close now exists."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for day, tkr in open_rows(path):
        if (day, tkr) in seen:
            continue
        seen.add((day, tkr))
        series = closes.get(tkr)
        if series is None:
            continue
        nxt, nxt_day = next_close(series, day)
        if nxt is None:
            continue
        same = close_on(series, day)
        out.append({"date": day, "ticker": tkr, "next_close_fill": nxt,
                    "next_close_date": nxt_day, "close_same_day": same,
                    "reconciled_at": _iso(now)})
    return out


def _expand_maturing(path: Path, updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fan a (date, ticker) fill update out to every kind row it covers."""
    import pandas as pd  # noqa: PLC0415
    if not updates or not path.exists():
        return []
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return []
    by_pair: dict[tuple[str, str], list[str]] = {}
    for r in df.itertuples():
        by_pair.setdefault((str(r.date), str(r.ticker)), []).append(str(r.kind))
    out: list[dict[str, Any]] = []
    for u in updates:
        for kind in by_pair.get((u["date"], u["ticker"]), []):
            out.append({**u, "kind": kind})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

def load_verdicts(pack_path: Path | None, *, s3=None) -> dict[str, bool]:
    """``{ticker: center_buyable}`` from tonight's freshly built armed pack.

    That IS tonight's real gate verdict set: the pack's ``center_buyable`` is
    ``signal_gate.is_buyable`` at the actual close, so no second gate pass is needed
    to know which of the day's crosses the nightly build kept.
    """
    pack: dict[str, Any] | None = None
    if pack_path and pack_path.exists():
        try:
            import json  # noqa: PLC0415
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=prophet-live-reconcile::local pack {pack_path} "
                  f"unreadable ({exc}) — falling back to R2", flush=True)
    if pack is None:
        pack = r2io.get_json(r2io.PACK_KEY, s3=s3)
    if not isinstance(pack, dict):
        return {}
    return {str(t).upper(): bool((e or {}).get("center_buyable"))
            for t, e in (pack.get("names") or {}).items()}


def run(root: Path, *, now: datetime | None = None, pack_path: Path | None = None,
        sessions: list[str] | None = None, dry_run: bool = False) -> int:
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    path = root / LEDGER_REL

    s3 = r2io.client()
    if s3 is None:
        print("::warning title=prophet-live-reconcile::no R2 credentials — the event "
              "spool cannot be listed; nothing accrued tonight", flush=True)
        return 0

    if sessions is None:
        # Today and yesterday in ET: a pass that fires at 16:10 ET lands after the
        # UTC date has already rolled, so a today-only window loses the close-side
        # transitions of the session the nightly is reconciling.
        from engine.prophet_live.live_states import et_clock  # noqa: PLC0415
        et = et_clock(ts).date()
        sessions = [(et - timedelta(days=1)).isoformat(), et.isoformat()]

    spool = spool_sessions(s3=s3, sessions=sessions)
    events: list[dict[str, Any]] = []
    for sess, keys in spool.items():
        got = load_events(keys, s3=s3)
        print(f"prophet-live reconcile: session {sess} passes={len(keys)} events={len(got)}",
              flush=True)
        events.extend(got)

    verdicts = load_verdicts(pack_path, s3=s3)
    if not verdicts:
        print("::warning title=prophet-live-reconcile::no armed pack readable — rows "
              "accrue with confirmed=null rather than a guessed verdict", flush=True)

    want = {str(e["ticker"]).upper() for e in events}
    want |= {t for _d, t in open_rows(path)}
    closes = load_closes(want) if want else {}
    missing = sorted(want - set(closes))
    if missing:
        print(f"::warning title=prophet-live-reconcile::{len(missing)} tickers have no "
              f"close series ({', '.join(missing[:8])}) — their fills stay null", flush=True)

    rows = build_rows(events, verdicts=verdicts, closes=closes, now=ts)
    rows.extend(_expand_maturing(path, maturing_rows(path, closes=closes, now=ts)))
    if not rows:
        print("prophet-live reconcile: nothing to accrue tonight", flush=True)
        return 0

    frame = merge_ledger(path, rows)
    if dry_run:
        print(f"prophet-live reconcile: DRY RUN — {len(rows)} updates would leave "
              f"{len(frame)} ledger rows", flush=True)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    matured = int(frame["next_close_fill"].notna().sum()) if len(frame) else 0
    print(f"prophet-live reconcile: {len(rows)} updates -> {len(frame)} rows "
          f"({matured} with a next-close fill) at {path}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile the Prophet Live intraday event spool into the forward ledger.")
    parser.add_argument("--nightly", action="store_true",
                        help="the nightly lane (required: this is the sole writer)")
    parser.add_argument("--pack", default=None,
                        help="path to tonight's armed pack JSON (else read from R2)")
    parser.add_argument("--session", action="append", default=None,
                        help="restrict to this ET session date (repeatable)")
    parser.add_argument("--now", default=None, help="ISO timestamp override (tests / replays)")
    parser.add_argument("--root", default=None, help="repo root (default: this script's parent)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="compute and report; write no parquet")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stderr)
    if not args.nightly:
        print("::warning title=prophet-live-reconcile::--nightly is required (the "
              "nightly lane is the sole writer of data/prophet_live/)", flush=True)
        return 0
    now: datetime | None = None
    if args.now:
        try:
            now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            print(f"::error title=prophet-live-reconcile::unparseable --now {args.now!r}",
                  flush=True)
            return 2
    root = Path(args.root) if args.root else Path(_CODE_ROOT)
    try:
        return run(root, now=now, pack_path=Path(args.pack) if args.pack else None,
                   sessions=args.session, dry_run=bool(args.dry_run))
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=prophet-live-reconcile::reconcile failed: {exc}", flush=True)
        log.warning("reconcile_prophet_live: unexpected failure", exc_info=True)
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
