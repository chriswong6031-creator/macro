"""The delisted-symbol exit ledger (`config/delisted_symbols.yml`), read once.

A row here means the SECURITY STOPPED EXISTING — it is not a rename and not a
broken feed. Three consumers act on that fact, and each acts differently:

  * `collectors.yahoo.YahooAdapter.all_tickers` drops the symbol from the FETCH.
    It can never return, so requesting it nightly guarantees a permanent entry in
    the requested-vs-returned warning that #4643 added — and a warning that is
    always on is a warning nobody reads when the next real outage lands.
  * `collectors.yahoo.audit_store_freshness` classifies it as `delisted`, not
    `stale`, so the store-tip audit stops reporting a finished tape as a defect.
  * `scripts.build_stock_library` swaps the cause-neutral `feed_stale` disclosure
    for a truthful `delisted` one and strips scoring authority unconditionally —
    the demotion no longer depends on the 7-day lag arithmetic that only happens
    to be true while the tape is recent.

What NO consumer does is delete anything. The store keeps its history, the ticker
keeps its `stock_search.extra_tickers` membership, and the page keeps its deep
links (CSP-R1). The exit is disclosed, never disappeared.

Layering: `collectors/` may not import `engine/`, so this lives in `lib/` where
both halves of the stack can reach it. It has no pandas/network dependency —
`is_delisted()` is called inside per-ticker loops.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

LEDGER_PATH = Path(__file__).resolve().parent.parent / "config" / "delisted_symbols.yml"

# Fields a row must carry to be usable. A row missing any of them is DROPPED with a
# loud log line rather than half-applied: a half-read row would strip a name's
# scoring authority while leaving the page unable to say why, which is a worse
# state than the cause-neutral frozen-feed disclosure it replaces.
_REQUIRED = ("company", "last_session", "delisted_on", "reason")


@lru_cache(maxsize=1)
def ledger() -> dict[str, dict]:
    """{ticker: row} for every well-formed row, or {} when the file is absent or
    unreadable.

    Fail-OPEN by design. Every consumer's fallback for an empty ledger is the
    behaviour that shipped before this module existed (fetch the symbol, call it
    stale, demote on lag) — degraded but honest. Fail-CLOSED would mean a typo in
    a YAML comment silently un-scoring names, or worse, blanking pages."""
    try:
        raw = yaml.safe_load(LEDGER_PATH.read_text()) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001 — a malformed ledger must never break collect/build
        log.warning("delisted-symbol ledger unreadable (%s) — treated as empty", e)
        return {}
    symbols = raw.get("symbols") or {}
    if not isinstance(symbols, dict):
        log.warning("delisted-symbol ledger: `symbols` is %s, expected a mapping — "
                    "treated as empty", type(symbols).__name__)
        return {}
    out: dict[str, dict] = {}
    for ticker, row in symbols.items():
        if not isinstance(row, dict):
            log.warning("delisted-symbol ledger: %s is not a mapping — row dropped", ticker)
            continue
        missing = [k for k in _REQUIRED if not row.get(k)]
        if missing:
            log.warning("delisted-symbol ledger: %s missing %s — row dropped",
                        ticker, ", ".join(missing))
            continue
        out[str(ticker)] = dict(row)
    return out


def is_delisted(ticker: str) -> bool:
    """True iff `ticker` has a well-formed exit row."""
    return ticker in ledger()


def disclosure(ticker: str) -> dict | None:
    """The user-facing subset of a row, or None when the ticker is still listed.

    Deliberately narrow: the ticker's page needs the date, who bought it, and the
    English/Chinese label — it does NOT need the CIK, the accession numbers, or
    the consideration terms. Those are the audit trail for the next engineer who
    re-opens the question, and they stay in the YAML where that reader will look.
    `successor_ticker` is carried through because a null there is the explicit
    statement that nothing continues this price series (see the file header)."""
    row = ledger().get(ticker)
    if row is None:
        return None
    return {
        "on": str(row["delisted_on"]),
        "last_session": str(row["last_session"]),
        "reason": str(row["reason"]),
        "acquirer": row.get("acquirer"),
        "acquirer_zh": row.get("acquirer_zh") or row.get("acquirer"),
        "successor_ticker": row.get("successor_ticker"),
    }


def tickers() -> frozenset[str]:
    """Every delisted ticker — the set collectors filter their fetch list against."""
    return frozenset(ledger())
