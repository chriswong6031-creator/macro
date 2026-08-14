"""Ticker-identity hygiene (masterplan §9.6) — run on every name before it is read.

A reused ticker splices a *different company's* history into one series "born
clean". The behavioral layer is the worst possible consumer of that: a fingerprint
computed across a splice describes an instrument that never existed, and an
episode catalog invents a decline where a corpse handed its symbol to a newborn.

Four repo sources are cross-checked, plus a first-print sanity read:

``config.yml quality.reused_ticker_acks``   symbols knowingly carrying a foreign
                                            prior holder's era in the same series
``config.yml quality.ticker_key_migrations`` rename pairs (old key -> new key): the
                                            SAME security continuing, which is
                                            instrument-level CONTINUITY, not a splice
``config.yml breadth.ticker_fixups``        the breadth-side rename map
``config/delisted_symbols.yml``             securities that stopped existing
``data/ipo/calendar.parquet``               first-print sanity vs the deal record

A rename and a reuse look identical in a bare price series and are opposite facts.
The rename keeps one instrument's identity; the reuse ends one and starts another.
This module never resolves one with the other's mechanism.

W1 finding, recorded rather than silently handled: ``data/baskets/ohlcv/ABX.parquet``
(2020-09-14 onward) sits alongside ``GOLD.parquet`` (2014-03-17 onward). ABX was
Barrick's retired symbol, renamed to GOLD in 2018; the ABX file is therefore a
DIFFERENT instrument on the reused symbol. Neither appears in
``reused_ticker_acks``/``ticker_key_migrations``/``ticker_fixups``, so the reuse is
**unacknowledged in config** — flagged here, and ABX is excluded from every
computation this program performs. GOLD.parquet is Barrick's continuous history
under its current symbol (the pre-2018 rows are the ABX era restated), which is
instrument-level continuity via rename and is legitimate to read.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

log = logging.getLogger(__name__)

#: Symbols this program refuses to read regardless of the draw, with the reason
#: printed in every receipt. A name here still appears in the universe snapshot
#: (censored-never-dropped, registration §1) but is never *consumed*.
COMPUTE_BLOCKLIST: dict[str, str] = {
    "ABX": (
        "unacknowledged reused symbol: Barrick retired ABX in the 2018 rename to GOLD; "
        "the file's 2020-09 onward tape is a different instrument, and the reuse is "
        "absent from reused_ticker_acks / ticker_key_migrations / breadth.ticker_fixups"
    ),
}


#: Informational annotations — facts a reader of a per-name artifact needs, that are
#: NOT blocking flags. A note never excludes a name; it explains one. The distinction
#: matters: GOLD is perfectly readable, but a reader who sees ABX.parquet sitting next
#: to it deserves to be told which file is Barrick and which is a stranger.
HYGIENE_NOTES: dict[str, str] = {
    "GOLD": (
        "REUSED SYMBOL, wrong-issuer tape (verified against the stores 2026-08-14): "
        "Gold.com, Inc. — fka A-Mark Precious Metals, a bullion dealer; EDGAR CIK "
        "1591588, FIGI BBG005ZVDK48 — has held NYSE 'GOLD' since 2025-12-02. Barrick "
        "left the symbol 2025-05-08 and trades as NYSE 'B' (Barrick Mining, EDGAR CIK "
        "756894). Every US store under GOLD holds the DEALER's 2014-03-17-> tape, never "
        "Barrick (data/yahoo/GOLD.parquet and data/baskets/ohlcv/GOLD.parquet both "
        "checked; an earlier revision of this note asserted continuous Barrick history "
        "from the symbol lineage without checking the tape). Barrick's continuous entity "
        "history lives under 'B' (data/yahoo/B.parquet, 1985->). Ratified break rows: "
        "config/theme_graph_identity_breaks.yml; acks: config.yml reused_ticker_acks "
        "(PR #5613)."
    ),
}


@lru_cache(maxsize=4)
def _load_config(repo_root: str) -> dict[str, Any]:
    p = Path(repo_root) / "config.yml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=4)
def _load_delisted(repo_root: str) -> dict[str, Any]:
    p = Path(repo_root) / "config" / "delisted_symbols.yml"
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("symbols", {}) or {}


@lru_cache(maxsize=4)
def _load_ipo_calendar(repo_root: str) -> pd.DataFrame:
    p = Path(repo_root) / "data" / "ipo" / "calendar.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("ipo calendar unreadable (%s) — first-print sanity degrades to UNKNOWN", exc)
        return pd.DataFrame()
    return df


def ipo_calendar_coverage(repo_root: str | Path) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Earliest and latest ``priced_date`` in the deal calendar, or (None, None)."""
    df = _load_ipo_calendar(str(repo_root))
    if df.empty or "priced_date" not in df.columns:
        return None, None
    d = pd.to_datetime(df["priced_date"], errors="coerce").dropna()
    if d.empty:
        return None, None
    return d.min(), d.max()


def check_symbol(
    symbol: str,
    *,
    repo_root: str | Path,
    first_date: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Hygiene verdict for one symbol.

    Returns ``flags`` (machine-readable), ``notes`` (per-flag resolution prose),
    ``first_print_sanity`` and ``compute_eligible``. Nothing is dropped here — the
    caller decides, and registration §1 says a hygiene annotation marks a row, it
    does not delete it.
    """
    root = str(repo_root)
    cfg = _load_config(root)
    quality = (cfg.get("quality") or {}) if isinstance(cfg, dict) else {}
    breadth = (cfg.get("breadth") or {}) if isinstance(cfg, dict) else {}
    reused = quality.get("reused_ticker_acks") or {}
    migrations = quality.get("ticker_key_migrations") or {}
    fixups = breadth.get("ticker_fixups") or {}
    delisted = _load_delisted(root)

    flags: list[str] = []
    notes: dict[str, str] = {}

    if symbol in reused:
        flags.append("reused_ticker_acked")
        notes["reused_ticker_acked"] = str(reused[symbol])
    if symbol in migrations:
        flags.append("ticker_key_migration_source")
        notes["ticker_key_migration_source"] = (
            f"{symbol} is the OLD key; history continues under {migrations[symbol]} "
            "(instrument continuity via rename, not a splice)"
        )
    if symbol in set(migrations.values()):
        src = [k for k, v in migrations.items() if v == symbol]
        flags.append("ticker_key_migration_target")
        notes["ticker_key_migration_target"] = (
            f"{symbol} is the CURRENT key; prior key(s) {src} renamed into it "
            "(instrument continuity via rename, not a splice)"
        )
    if symbol in fixups or symbol in set(fixups.values()):
        flags.append("breadth_ticker_fixup")
        notes["breadth_ticker_fixup"] = f"present in breadth.ticker_fixups map ({fixups})"
    if symbol in delisted:
        row = delisted[symbol] or {}
        flags.append("delisted_ledger_row")
        notes["delisted_ledger_row"] = (
            f"reason={row.get('reason')}, last_session={row.get('last_session')}"
        )
    if symbol in COMPUTE_BLOCKLIST:
        flags.append("reused_ticker_unacked")
        notes["reused_ticker_unacked"] = COMPUTE_BLOCKLIST[symbol]
    if symbol in HYGIENE_NOTES:
        flags.append("symbol_history_note")
        notes["symbol_history_note"] = HYGIENE_NOTES[symbol]

    sanity, sanity_note = _first_print_sanity(symbol, root, first_date)

    return {
        "symbol": symbol,
        "flags": flags,
        "notes": notes,
        "first_print_sanity": sanity,
        "first_print_note": sanity_note,
        "compute_eligible": symbol not in COMPUTE_BLOCKLIST,
        "blind_eligible": not (
            symbol in COMPUTE_BLOCKLIST or "reused_ticker_acked" in flags
        ),
    }


def _first_print_sanity(
    symbol: str, repo_root: str, first_date: pd.Timestamp | None
) -> tuple[str, str]:
    """Compare the store's first print against the IPO deal record.

    Three honest outcomes, and "predates calendar coverage" is one of them: the
    Nasdaq deal reference only reaches back a few years, so a 1980 first print is
    not a failure, it is out of the instrument's range.
    """
    if first_date is None or pd.isna(first_date):
        return "UNKNOWN", "no first print available"
    cal = _load_ipo_calendar(repo_root)
    cov_lo, _ = ipo_calendar_coverage(repo_root)
    if cal.empty or "ticker" not in cal.columns:
        return "UNKNOWN", "ipo calendar unavailable"
    if cov_lo is not None and pd.Timestamp(first_date) < pd.Timestamp(cov_lo):
        return "PREDATES_CALENDAR", (
            f"first print {pd.Timestamp(first_date).date()} predates the deal calendar's "
            f"earliest priced date ({pd.Timestamp(cov_lo).date()})"
        )
    hit = cal[(cal["ticker"] == symbol) & (cal.get("status") == "priced")]
    if hit.empty:
        return "NO_DEAL_ROW", "no priced deal row for this ticker in the calendar window"
    priced = pd.to_datetime(hit["priced_date"], errors="coerce").dropna()
    if priced.empty:
        return "NO_DEAL_ROW", "deal row carries no priced date"
    delta = (pd.Timestamp(first_date) - priced.min()).days
    if abs(delta) <= 7:
        return "OK", f"first print within {delta}d of priced date {priced.min().date()}"
    return "MISMATCH", (
        f"first print {pd.Timestamp(first_date).date()} is {delta}d from the priced date "
        f"{priced.min().date()} — inspect before trusting pre-deal rows"
    )


def dead_name_reason(symbol: str, repo_root: str | Path) -> str:
    """``terminated_reason`` for a ceased-tape name.

    A ledger row's reason is used where one exists; otherwise the honest string is
    ``tape_ended (cause unverified)``. It is never inferred into something more
    specific — an unresolved delisting reason is a disclosure, not a guess
    (registration §2, and the ledger's own every-row-is-resolved protocol).
    """
    delisted = _load_delisted(str(repo_root))
    row = delisted.get(symbol)
    if isinstance(row, dict) and row.get("reason"):
        return str(row["reason"])
    return "tape_ended (cause unverified)"
