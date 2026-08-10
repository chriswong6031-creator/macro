"""engine.close_pass.reconcile — the provisional → nightly confirmation delta.

This is the integrity metric, and it is free. A provisional board nobody ever
grades is a second opinion; the same board with a published per-name delta is a
claim that gets marked every single night. It costs one set difference.

WHAT IS COMPARED, AND WHY NOT THE SCORE
The provisional board scores 40 of the board's 100 points (see board.py — three
legs are omitted, not imputed), so its ordering is NOT numerically comparable to
the nightly's and a rank diff would mark almost every name "adjusted" and mean
nothing. What IS comparable is the thing both boards compute the same way: the
admission gate's verdict. So a name is

  confirmed  the nightly still admits it, at the same confluence tier
  adjusted   the nightly still admits it, at a DIFFERENT tier
  dropped    the nightly does not admit it at all

and `added` — a name the nightly admits that the evening pass did not — is
reported beside the identity rather than inside it, because the spec's
arithmetic is over the PROVISIONAL board's population
(``n_confirmed + n_adjusted + n_dropped == n_total``) and folding additions in
would break the one invariant the surface is allowed to trust.

MEASURED 2026-08-07, on the real universe — read this before reading a receipt.
The close-only pass admitted 131 names. The nightly's published buy lane carried
79, of which 72 were also admitted here, and the nightly's own admission set
(buyable verdicts across all four lanes) was 75 — **every one of which this pass
also admitted, zero misses**. So the close-only gate reproduces the nightly's
admission COMPLETELY and then over-admits about 1.7x on top of it.

The extra ~56 are not gate disagreements. The published lanes are a CURATED
subset: `lane_counts` splits the buy lane into continuation (35) and bottoming
(44), a stage classification that comes from the per-name cycles pass, not from
closes. So a first receipt reads "72 confirmed, 59 dropped of 131" — an
unflattering number that is the honest one, and exactly what an integrity metric
is for. Redefining the comparison until it flattered the lane would delete the
finding. What it says is: membership is solved, the CARD GRID is not, and a
card-for-card provisional board needs the lane classification a close pass
cannot compute. That is the next wave's problem, and this number is how it will
be known to be fixed.

NO RECEIPT IS BETTER THAN A WRONG ONE (spec §7). Every path that cannot produce
a reconciling count returns None: no provisional board that night, the two
boards describing different sessions, a duplicate ticker on either side, or an
arithmetic that does not close. The surface renders no receipt line rather than
a receipt whose figures do not add up in front of the reader.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

RECEIPT_SCHEMA = "us_board_confirmation/v1"


def _tickers(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict]:
    """{ticker: row}, or {} when any ticker repeats.

    A duplicate is not a merge candidate: two rows for one name means one of the
    boards is malformed, and every count computed over it would be wrong in a
    way the arithmetic check below cannot see (the totals still add up).
    """
    out: dict[str, dict] = {}
    for row in rows or ():
        ticker = (row or {}).get("ticker")
        if not isinstance(ticker, str) or not ticker or ticker in out:
            return {}
        out[ticker] = dict(row)
    return out


def _nightly_buy_rows(nightly: Mapping[str, Any] | None) -> list[dict]:
    """The nightly board of record's buy lane — the countersignature."""
    return list((nightly or {}).get("buy") or [])


def _nightly_tier(row: Mapping[str, Any]) -> Any:
    """The gate verdict's tier on a nightly row.

    ``build_stock_library`` stamps the whole gate verdict under ``signal``; a
    row that carries the compacted form keeps the same key, so one lookup
    covers both shapes.
    """
    return ((row or {}).get("signal") or {}).get("tier_cascade")


def confirmation_receipt(provisional: Mapping[str, Any] | None,
                         nightly: Mapping[str, Any] | None,
                         *, built_at: datetime | None = None) -> dict | None:
    """The per-name delta, or None when an honest one cannot be produced."""
    if not provisional or not nightly:
        return None

    session = provisional.get("as_of")
    # Two boards that describe different sessions cannot be reconciled: this is
    # the spec's "no receipt after a `behind` night" — there was no provisional
    # board for THIS session to countersign, and diffing against an older one
    # would report last night's names as tonight's drops.
    if not session or session != nightly.get("as_of"):
        return None

    prov = _tickers(provisional.get("names") or ())
    live = _tickers(_nightly_buy_rows(nightly))
    if not prov or not live:
        return None

    confirmed: list[str] = []
    adjusted: list[str] = []
    dropped: list[str] = []
    moved: dict[str, dict] = {}
    for ticker, row in sorted(prov.items()):
        night = live.get(ticker)
        if night is None:
            dropped.append(ticker)
        elif _nightly_tier(night) == row.get("tier_cascade"):
            confirmed.append(ticker)
        else:
            adjusted.append(ticker)
            moved[ticker] = {"from": row.get("tier_cascade"),
                             "to": _nightly_tier(night)}

    n_total = len(prov)
    if len(confirmed) + len(adjusted) + len(dropped) != n_total:
        # Unreachable by construction today — which is exactly why it is
        # checked rather than asserted in a comment. If a future edit makes the
        # three lanes overlap, the surface gets no receipt instead of figures
        # that do not add up in front of the reader.
        print("::warning title=close-pass::confirmation delta does not reconcile "
              f"({len(confirmed)}+{len(adjusted)}+{len(dropped)} != {n_total}) "
              "— publishing no receipt", flush=True)
        return None

    # Timezone-aware always: a naive stamp here would be the receipt's only
    # clock, and the estate's convention is UTC (#2463).
    stamp = built_at or datetime.now(timezone.utc)
    return {
        "schema": RECEIPT_SCHEMA,
        "as_of": session,
        "built_at": stamp.isoformat().replace("+00:00", "Z"),
        "provisional_built_at": provisional.get("built_at"),
        "n_total": n_total,
        "n_confirmed": len(confirmed),
        "n_adjusted": len(adjusted),
        "n_dropped": len(dropped),
        "confirmed": confirmed,
        "adjusted": adjusted,
        "dropped": dropped,
        # Beside the identity, never inside it — see the module docstring.
        "detail": {
            "n_added": len(set(live) - set(prov)),
            "added": sorted(set(live) - set(prov)),
            "tier_moves": moved,
            "basis": "confluence tier of the admission gate's verdict",
        },
    }


def board_state_payload(receipt: Mapping[str, Any] | None) -> dict | None:
    """Project a receipt into the surface's ``board_state`` contract, or None.

    ONE COMPUTATION, ONE PROJECTION. ``confirmation_receipt`` above is the only
    place the delta is computed; this is the only place it is dressed for the
    page. It is the exact sibling of ``board.board_state``, which does the same
    for the PROVISIONAL side of the same surface — so neither side of the W-L1
    contract has a second definition living somewhere a reader would not think
    to look.

    NO ``rel``. The board this grades IS the board of record, and the record has
    no position relative to itself — the absent stamp is the spec's load-bearing
    third state (§3). ``lib.board_state`` refuses ``rel`` server-side regardless,
    so emitting one here would be a field that exists only to be thrown away.

    ``adjusted`` rides along because the per-card ``Adjusted`` mark and the
    receipt line it belongs to are published together or not at all (spec §7):
    the consumer stamps the cards only after the interpreter has vouched for the
    line, and it needs the names to do it.
    """
    if not receipt:
        return None
    return {
        "note": "confirmed",
        "as_of": receipt.get("as_of"),
        "generated_at": receipt.get("built_at"),
        "n_total": receipt.get("n_total"),
        "n_confirmed": receipt.get("n_confirmed"),
        "n_adjusted": receipt.get("n_adjusted"),
        "n_dropped": receipt.get("n_dropped"),
        "dropped": list(receipt.get("dropped") or ()),
        "adjusted": list(receipt.get("adjusted") or ()),
    }
