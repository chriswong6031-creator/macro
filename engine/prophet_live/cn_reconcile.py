"""CN breathing-platform settlement (CN-PR-2, spec §8).

Two jobs, both keep-first and both lane-gated by the caller:

  * event-spool → ``data/cn_prophet_live/forward.parquet`` (the PIT substrate)
  * close_board vs canonical china_standouts → confirmation receipt

No gate re-run. The pack already froze the nightly legs; this module only
joins what the session already observed. Stdlib + optional pandas (parquet
I/O). No CN-LIMIT-ALPHA imports.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

FORWARD_SCHEMA = "cn_prophet_live.forward/v1"
RECEIPT_SCHEMA = "cn_board_confirmation/v1"
LEDGER_FLOOR_SESSION = "2026-08-17"

KEY = ("date", "ticker", "kind")
FIRST_WINS = (
    "confirmed", "first_ts", "first_px", "cross_px", "cross_basis_close",
)

CANONICAL_LANES = ("buy", "more_actionable", "forming")
PROVISIONAL_LANES = ("featured", "more_actionable", "forming", "cross")


def _iso(now: datetime) -> str:
    t = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _row_key(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    date = str(row.get("date") or row.get("session") or "")
    ticker = str(row.get("ticker") or "")
    kind = str(row.get("kind") or "")
    if not date or not ticker or not kind or date < LEDGER_FLOOR_SESSION:
        return None
    return date, ticker, kind


def merge_rows(existing: Iterable[Mapping[str, Any]],
               incoming: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Union-merge on (date, ticker, kind). First non-null wins on FIRST_WINS.

    A later run may fill ``next_close_fill`` / ``close_same_day`` when those
    were null; it may never revise a confirmed verdict or a first-cross print.
    """
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for src in (existing, incoming):
        for raw in src:
            key = _row_key(raw)
            if key is None:
                continue
            row = dict(raw)
            row["date"], row["ticker"], row["kind"] = key
            prev = out.get(key)
            if prev is None:
                out[key] = row
                continue
            merged = dict(prev)
            for col, val in row.items():
                if col in FIRST_WINS:
                    if merged.get(col) in (None, ""):
                        merged[col] = val
                elif val not in (None, ""):
                    merged[col] = val
            out[key] = merged
    return [out[k] for k in sorted(out)]


def events_to_rows(events: Iterable[Mapping[str, Any]],
                   *, session: str,
                   confirmed: set[str] | None = None) -> list[dict[str, Any]]:
    """One ledger row per (session, ticker, kind). First occurrence is the print."""
    first: dict[tuple[str, str], dict[str, Any]] = {}
    last: dict[tuple[str, str], dict[str, Any]] = {}
    counts: dict[tuple[str, str], int] = {}
    for ev in events:
        tkr = str(ev.get("ticker") or "")
        kind = str(ev.get("kind") or "")
        if not tkr or not kind:
            continue
        key = (tkr, kind)
        counts[key] = counts.get(key, 0) + 1
        last[key] = dict(ev)
        first.setdefault(key, dict(ev))
    rows: list[dict[str, Any]] = []
    hit = confirmed or set()
    for (tkr, kind), ev in sorted(first.items()):
        tail = last[(tkr, kind)]
        rows.append({
            "date": session,
            "ticker": tkr,
            "kind": kind,
            "first_ts": ev.get("ts") or ev.get("first_ts"),
            "first_px": ev.get("px") or ev.get("first_px") or ev.get("cross_px"),
            "cross_px": ev.get("px") or ev.get("cross_px"),
            "last_ts": tail.get("ts") or tail.get("last_ts"),
            "last_px": tail.get("px") or tail.get("last_px"),
            "occurrences": counts[(tkr, kind)],
            "confirmed": tkr in hit if hit else None,
            "close_same_day": None,
            "next_close_fill": None,
        })
    return rows


def _lane_tickers(block: Mapping[str, Any] | Iterable[Any],
                  lanes: tuple[str, ...]) -> dict[str, str]:
    """ticker → lane name, first lane wins."""
    out: dict[str, str] = {}
    if isinstance(block, Mapping):
        for lane in lanes:
            rows = block.get(lane)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                tkr = str(row.get("ticker") or row.get("tk") or "")
                if tkr and tkr not in out:
                    out[tkr] = lane
    return out


def confirmation_receipt(close_board: Mapping[str, Any] | None,
                         standouts: Mapping[str, Any] | None,
                         *, session: str,
                         built_at: datetime | None = None) -> dict[str, Any] | None:
    """Per-name delta of the provisional close board vs the canonical standouts.

    None when the two artifacts do not describe the same session — there is no
    receipt after a behind night (the #5220 lesson). ``added`` rides beside
    the identity, never inside it.
    """
    if not close_board or not standouts:
        return None
    standouts_asof = str(standouts.get("as_of") or "")
    if not session or session != standouts_asof:
        return None
    lanes = close_board.get("lanes") if isinstance(close_board.get("lanes"), dict) else close_board
    prov = _lane_tickers(lanes if isinstance(lanes, Mapping) else {}, PROVISIONAL_LANES)
    live = _lane_tickers(standouts, CANONICAL_LANES)
    if not prov or not live:
        return None

    confirmed: list[str] = []
    adjusted: list[str] = []
    dropped: list[str] = []
    moved: dict[str, dict[str, str]] = {}
    for ticker, lane in sorted(prov.items()):
        night = live.get(ticker)
        if night is None:
            dropped.append(ticker)
        elif night == lane or (lane == "featured" and night == "buy"):
            confirmed.append(ticker)
        else:
            adjusted.append(ticker)
            moved[ticker] = {"from": lane, "to": night}

    n_total = len(prov)
    if len(confirmed) + len(adjusted) + len(dropped) != n_total:
        return None

    stamp = built_at or datetime.now(timezone.utc)
    added = sorted(set(live) - set(prov))
    return {
        "schema": RECEIPT_SCHEMA,
        "as_of": session,
        "built_at": _iso(stamp),
        "n_total": n_total,
        "n_confirmed": len(confirmed),
        "n_adjusted": len(adjusted),
        "n_dropped": len(dropped),
        "confirmed": confirmed,
        "adjusted": adjusted,
        "dropped": dropped,
        "detail": {
            "n_added": len(added),
            "added": added,
            "lane_moves": moved,
            "basis": "close_board lanes vs china_standouts buy/more_actionable/forming",
        },
    }
