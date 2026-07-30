"""scripts/reconcile_prophet_live.py — nightly Prophet Live event reconciler (P0 D4).

Turns the day's intraday event spool into the forward ledger that the §5/§6
promotion gauntlet will eventually be pre-registered on:
``data/prophet_live/forward.parquet``. It is the ENTIRE evidence base for the
operator's "acting at the intraday cross beats the graded next-close fill"
hypothesis, and it accrues from week one with no user surface attached.

    python -m scripts.reconcile_prophet_live --nightly [--pack PATH] [--now ISO]

WHAT IT JOINS, per event row:
  * ``confirmed`` — did the gate, run on the series through the EVENT'S OWN session,
    put the name in a buyable tier? Vintage is load-bearing and was wrong twice:
    the default [yesterday, today] window re-processes session D on night D+1, and
    the pack read on night D+1 carries as_of D+1 — so every re-processed row was
    stamped with a verdict one session too late, and on a pack-build-failure night
    the R2 fallback graded today's events off yesterday's pack. Now ``confirmed`` is
    written ONLY from a verdict whose basis IS the row's session (tonight's pack when
    its as_of matches, else the gate re-run on the series truncated through that
    session), and once non-null it is never overwritten.
  * ``close_same_day`` — the actual close of the session the event fired in.
  * ``next_close_fill`` — the official fill: the close of the bar STRICTLY AFTER the
    event's session, mirroring :func:`engine.grading.fill_index` (grade_us_board's
    next-bar convention). Filled on a LATER night, when that bar exists — the row is
    written the night of the event with a null fill and matured in place.
  * ``first_ts``/``first_px`` and ``last_ts``/``last_px`` + ``occurrences`` — the
    FIRST cross is the user-actionable one. Keeping only the last occurrence recorded
    a name that formed at 100 and re-formed at 108 as a 108 entry, which would have
    biased the entry-advantage measurement the program exists to make.

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

#: The merge identity. One row per (session, name, transition kind); a name that
#: forms, fades and re-forms in a day contributes one row per kind, carrying both the
#: first and the last occurrence of it.
KEY = ["date", "ticker", "kind"]

#: Columns where the FIRST non-null value wins and later runs may never revise it.
#: ``confirmed`` because a verdict is a claim about one session's close and a later
#: night has no standing to restate it; the first-cross fields because they are the
#: user-actionable print and a re-read over an expired spool must not lose them.
#:
#: ``cross_px`` is in here for a proven failure: if one pass object of a session's spool
#: becomes unreadable, a re-read rebuilds the row from a PARTIAL spool, so ``first_px``
#: stays frozen at the real first cross while ``cross_px`` — the same number, and the
#: base of both derived percentages — takes the later print. That put a 100 entry and a
#: 108 basis in one row with a sign-flipped ``fill_vs_cross_pct``, and
#: :func:`maturing_rows` then re-derived from the clobbered value the next night.
FIRST_WINS = ("confirmed", "confirmed_basis", "first_ts", "first_px", "cross_px")

#: Percentages recomputed from the MERGED row after every merge: ``{column: numerator}``,
#: always over ``cross_px``. Merging them column-wise let a partial re-read leave a
#: percentage derived from a base the merged row no longer carries — the mixed-basis
#: fabrication the house law forbids, inside a single row.
_DERIVED = {"close_vs_cross_pct": "close_same_day", "fill_vs_cross_pct": "next_close_fill"}

#: Sessions strictly before this are NEVER accrued. Belt-and-braces for B4: any
#: pre-merge spool object may have been written by a receipt or a rehearsal rather
#: than a real market pass, and a fabricated row joined to real closes is
#: indistinguishable from a genuine one forever. Raising this floor is safe; lowering
#: it re-opens the window and needs a deliberate audit of what is under the prefix.
LEDGER_FLOOR_SESSION = "2026-07-30"


def _iso(now: datetime) -> str:
    t = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ─────────────────────────────────────────────────────────────────────────────
# Spool
# ─────────────────────────────────────────────────────────────────────────────

def spool_sessions(*, s3=None, prefix: str = r2io.EVENTS_PREFIX,
                   sessions: list[str] | None = None) -> dict[str, list[str]]:
    """``{session_date: [object keys]}`` for the requested sessions.

    Lists the per-session prefixes, not the whole history: the spool grows by ~80
    objects a session forever, and paginating all of it to pick out two days would
    turn into thousands of listed keys a night for no gain.
    """
    prefixes = ([f"{prefix}/{s}/" for s in sessions] if sessions is not None
                else [f"{prefix}/"])
    out: dict[str, list[str]] = {}
    for pfx in prefixes:
        for key in r2io.list_keys(pfx, s3=s3):
            parts = key[len(prefix):].strip("/").split("/")
            if len(parts) != 2 or not parts[1].endswith(".json"):
                continue
            sess = parts[0]
            if sessions is not None and sess not in sessions:
                continue
            if sess < LEDGER_FLOOR_SESSION:
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


def _f(v: Any) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pct(a: float | None, b: float | None) -> float | None:
    """``a`` relative to ``b``, in percent. None unless both are usable."""
    try:
        if a is None or b is None or float(b) == 0.0:
            return None
        return (float(a) / float(b) - 1.0) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def session_verdicts(session: str, tickers: set[str], *, closes: dict[str, Any],
                     pack_as_of: str | None,
                     pack_verdicts: dict[str, bool]) -> tuple[dict[str, bool], str]:
    """``({ticker: is_buyable}, basis)`` for ONE session — same gate, same basis.

    When tonight's pack was built on this very session, its ``center_buyable`` IS the
    verdict and no gate re-run is needed. Otherwise the gate is re-run on each name's
    close series TRUNCATED THROUGH the session, which reproduces the basis the pack
    would have had that night: same function, same close-only inputs, no second
    definition of "buyable" anywhere.

    Caveat worth knowing when reading old rows: a truncated replay sees the store as
    it stands TODAY. If a name's history has since been restated (dividend
    re-rounding moves adjusted closes), a replayed verdict can differ from what that
    night's pack computed. ``confirmed_basis`` records which route produced the value
    so a later audit can tell the two apart.
    """
    if pack_as_of and str(pack_as_of)[:10] == session:
        return ({t: pack_verdicts[t] for t in tickers if t in pack_verdicts}, "pack")
    import pandas as pd  # noqa: PLC0415
    from engine import signal_gate  # noqa: PLC0415
    cut = pd.Timestamp(session)
    out: dict[str, bool] = {}
    for tkr in sorted(tickers):
        s = closes.get(tkr)
        if s is None:
            continue
        trunc = s[pd.DatetimeIndex(s.index).normalize() <= cut]
        if not len(trunc):
            continue
        try:
            out[tkr] = bool(signal_gate.is_buyable(signal_gate.gate(tkr, trunc)))
        except Exception as exc:  # noqa: BLE001
            log.warning("reconcile_prophet_live: replay gate failed for %s @ %s: %s",
                        tkr, session, exc)
    return out, "replay"


def build_rows(events: list[dict[str, Any]], *, verdicts_for: Any,
               closes: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """One ledger row per (session, ticker, kind), carrying FIRST and LAST occurrence.

    ``verdicts_for(session, tickers)`` returns ``({ticker: bool}, basis)`` for that
    session — see :func:`session_verdicts`. Events are grouped before any verdict is
    resolved so the gate is re-run at most once per session, not once per row.
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for ev in events:
        day = str(ev.get("session_et") or "")[:10]
        if not day or day < LEDGER_FLOOR_SESSION:
            continue
        groups.setdefault((day, str(ev["ticker"]).upper(), str(ev["kind"])), []).append(ev)

    by_session: dict[str, set[str]] = {}
    for (day, tkr, _kind) in groups:
        by_session.setdefault(day, set()).add(tkr)
    resolved = {day: verdicts_for(day, tkrs) for day, tkrs in by_session.items()}

    rows: list[dict[str, Any]] = []
    for (day, tkr, kind), evs in sorted(groups.items()):
        # Spool keys are HHMMSS per pass, and load_events reads them in key order, so
        # list order is pass order; ts breaks any tie defensively.
        evs = sorted(evs, key=lambda e: str(e.get("ts") or ""))
        first, last = evs[0], evs[-1]
        series = closes.get(tkr)
        same = close_on(series, day) if series is not None else None
        nxt, nxt_day = next_close(series, day) if series is not None else (None, None)
        first_px = _f(first.get("price"))
        verdict_map, basis = resolved.get(day, ({}, "none"))
        rows.append({
            "date": day,
            "ticker": tkr,
            "kind": kind,
            # The FIRST occurrence is the actionable one — what a user could have
            # traded — so it owns cross_px and the derived percentages.
            "first_ts": first.get("ts"),
            "first_px": first_px,
            "cross_px": first_px,
            "last_ts": last.get("ts"),
            "last_px": _f(last.get("price")),
            "occurrences": len(evs),
            "quote_age_min": first.get("quote_age_min"),
            "passes": first.get("passes"),
            "from_state": first.get("from"),
            "entered": first.get("entered"),
            "via": first.get("via"),
            "session_phase": first.get("session_phase"),
            "pack_as_of": first.get("pack_as_of"),
            # None, not False: "no verdict of this session's vintage" is not the same
            # claim as "the gate rejected it".
            "confirmed": verdict_map.get(tkr),
            "confirmed_basis": basis if tkr in verdict_map else None,
            "close_same_day": same,
            "next_close_fill": nxt,
            "next_close_date": nxt_day,
            "close_vs_cross_pct": _pct(same, first_px),
            # The measurement the whole program exists to make: the official graded
            # fill is the NEXT close, so this is what a same-session entry gave up
            # or gained against the convention the track record uses.
            "fill_vs_cross_pct": _pct(nxt, first_px),
            "reconciled_at": _iso(now),
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Ledger
# ─────────────────────────────────────────────────────────────────────────────

def merge_ledger(path: Path, rows: list[dict[str, Any]]):
    """Union-merge ``rows`` into the parquet on :data:`KEY`, field-wise.

    ``groupby(KEY).last()`` keeps the last NON-NULL value per column, so a maturing
    fill lands without erasing anything the earlier write already knew, and running
    the reconciler twice on a pinned clock produces a byte-identical frame.

    :data:`FIRST_WINS` columns take ``.first()`` instead: a verdict is a claim about
    one session's close, and a later night — which sees a later pack and a possibly
    restated store — has no standing to revise it. That is the second half of the
    vintage fix; without it the [yesterday, today] window would still overwrite
    night D's ``confirmed`` on night D+1 even though the value it wrote was correct.
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
    grouped = combined.groupby(KEY, as_index=False, sort=True)
    out = grouped.last()
    firsts = grouped.first()
    for col in FIRST_WINS:
        if col in out.columns and col in firsts.columns:
            out[col] = firsts[col]
    # A derived percentage must be a function of the row it sits in, not of whichever
    # write last touched that column.
    if "cross_px" in out.columns:
        base = out["cross_px"]
        for col, num in _DERIVED.items():
            if col in out.columns and num in out.columns:
                out[col] = [_pct(a, b) for a, b in zip(out[num], base)]
    return out.sort_values(KEY, kind="stable").reset_index(drop=True)


def confirmed_pairs(path: Path) -> set[tuple[str, str]]:
    """``(date, ticker)`` pairs that already carry a verdict of their own vintage.

    Re-deriving one is pure waste: :data:`FIRST_WINS` discards the second answer. It is
    also the reconciler's only unbounded cost — the default window re-processes
    yesterday's session every night, and a replay over a busy day's tickers would run
    the gate hundreds of times against a 3-minute step cap for a value that cannot
    land.
    """
    import pandas as pd  # noqa: PLC0415
    if not path.exists():
        return set()
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return set()
    if df.empty or "confirmed" not in df.columns:
        return set()
    have = df[df["confirmed"].notna()]
    return {(str(r.date), str(r.ticker)) for r in have.itertuples()}


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
    """Fill updates for rows whose next-session close now exists.

    Both derived percentages are recomputed here, not just the raw closes: rewriting
    ``close_same_day`` while leaving a ``close_vs_cross_pct`` derived from an earlier
    value of it is exactly the mixed-basis fabrication the house law forbids. The
    cross price comes from the stored row so the ratio's two legs stay same-row.
    """
    import pandas as pd  # noqa: PLC0415
    if not path.exists():
        return []
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return []
    cross_by_pair: dict[tuple[str, str], float | None] = {}
    for r in df.itertuples():
        cross_by_pair.setdefault((str(r.date), str(r.ticker)),
                                 _f(getattr(r, "cross_px", None)))
    out: list[dict[str, Any]] = []
    for day, tkr in open_rows(path):
        series = closes.get(tkr)
        if series is None:
            continue
        nxt, nxt_day = next_close(series, day)
        if nxt is None:
            continue
        same = close_on(series, day)
        cross = cross_by_pair.get((day, tkr))
        out.append({"date": day, "ticker": tkr, "next_close_fill": nxt,
                    "next_close_date": nxt_day, "close_same_day": same,
                    "close_vs_cross_pct": _pct(same, cross),
                    "fill_vs_cross_pct": _pct(nxt, cross),
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

def load_verdicts(pack_path: Path | None, *, s3=None) -> tuple[dict[str, bool], str | None]:
    """``({ticker: center_buyable}, pack_as_of)`` from an armed pack.

    THE as_of COMES BACK WITH THE VERDICTS, deliberately. The earlier version returned
    the map alone, so a caller had no way to know which session it described — and on
    a night when the pack build failed, the R2 fallback silently supplied YESTERDAY's
    pack to grade today's events. Callers must compare ``pack_as_of`` to the row's
    session before writing ``confirmed`` (see :func:`session_verdicts`).
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
        return {}, None
    verdicts = {str(t).upper(): bool((e or {}).get("center_buyable"))
                for t, e in (pack.get("names") or {}).items()}
    return verdicts, (str(pack.get("as_of"))[:10] if pack.get("as_of") else None)


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
    sessions = [s for s in sessions if s >= LEDGER_FLOOR_SESSION]
    if not sessions:
        print(f"prophet-live reconcile: every requested session is before the ledger "
              f"floor {LEDGER_FLOOR_SESSION} — nothing accrued", flush=True)
        return 0

    spool = spool_sessions(s3=s3, sessions=sessions)
    events: list[dict[str, Any]] = []
    for sess, keys in spool.items():
        got = load_events(keys, s3=s3)
        print(f"prophet-live reconcile: session {sess} passes={len(keys)} events={len(got)}",
              flush=True)
        events.extend(got)

    verdicts, pack_as_of = load_verdicts(pack_path, s3=s3)
    if not verdicts:
        print("::warning title=prophet-live-reconcile::no armed pack readable — "
              "verdicts come from a truncated gate replay per session", flush=True)
    print(f"prophet-live reconcile: pack as_of={pack_as_of} verdicts={len(verdicts)}",
          flush=True)

    want = {str(e["ticker"]).upper() for e in events}
    want |= {t for _d, t in open_rows(path)}
    closes = load_closes(want) if want else {}
    missing = sorted(want - set(closes))
    if missing:
        print(f"::warning title=prophet-live-reconcile::{len(missing)} tickers have no "
              f"close series ({', '.join(missing[:8])}) — their fills and verdicts "
              "stay null", flush=True)

    done = confirmed_pairs(path)

    def _verdicts_for(session: str, tickers: set[str]):
        # Anything already confirmed of its own vintage is skipped: FIRST_WINS would
        # throw the new answer away, and the replay is this step's only unbounded cost.
        need = {t for t in tickers if (session, t) not in done}
        if not need:
            print(f"prophet-live reconcile: session {session} already confirmed "
                  f"({len(tickers)} names) — no verdict work", flush=True)
            return {}, "already"
        got, basis = session_verdicts(session, need, closes=closes,
                                      pack_as_of=pack_as_of, pack_verdicts=verdicts)
        print(f"prophet-live reconcile: session {session} verdicts={len(got)}/"
              f"{len(need)} needed of {len(tickers)} basis={basis}", flush=True)
        return got, basis

    rows = build_rows(events, verdicts_for=_verdicts_for, closes=closes, now=ts)
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
