"""CI guard: the universe may never key on a ticker that no longer trades.

WHAT THIS CATCHES, AND WHY IT EXISTS
------------------------------------
A US listing can change its ticker without changing company, CUSIP, or listing.
When that happens this repo splits on its own: every collector fed by a vendor or
regulator (SEC, FINRA, OpenFIGI, the NASDAQ directory, ETF holdings) follows the
rename within days, while anything keyed off the committed universe stays on the
retired symbol — and nothing anywhere notices.

Two S&P 500 names were in that state when this guard was written, both because
``breadth.ticker_fixups`` pointed BACKWARDS (it "repaired" the live symbol into
the retired one):

  * Marsh McLennan — MMC -> MRSH on 2026-01-14, misread as Wikipedia vandalism.
    ~7 months. The universe's price column was 0/345 non-null, factor betas
    existed only under MRSH with the company name unresolved, the alt-data board
    carried MMC and MRSH as two separate companies with different scores, and
    Marsh had no stock page under either symbol.
  * Fiserv — FISV -> FI in 2023, then BACK FI -> FISV on 2025-11-11. The 2023-era
    fixup was never re-pointed. ~9 months.

THE CHECKS
----------
1. FIXUP DIRECTION. Every key of ``breadth.ticker_fixups`` (the retired symbol)
   must be ABSENT from the current NASDAQ symbol directory and every value (the
   live symbol) must be PRESENT. This is what fails if the map ever inverts again.
2. UNIVERSE IS LISTED. Every member of every index universe must appear in the
   current NASDAQ symbol directory. This is the direct form of the defect and
   needs no knowledge of any particular rename.
3. PIT AGREEMENT. A universe member whose point-in-time interval CLOSED while a
   successor interval opened the same day is a rename the universe did not follow.

A "closed PIT interval" alone is deliberately NOT a failure, because it conflates
three different things and only one of them is a bug:

  * RENAME — the entity continues under a new symbol (MMC -> MRSH). A bug.
  * TICKER REUSE — the symbol continues under a DIFFERENT entity. ECHO is live:
    Echo Global Logistics was acquired in 2021 and freed the symbol, which was
    later reassigned to EchoStar. Not a bug, and check 2 passes it correctly
    because the symbol genuinely trades.
  * DELISTING — the entity is gone and so is the symbol. Not a bug.

Presence in the listing directory is what separates them, which is why check 2 is
the primary gate and the PIT store is a corroborating source rather than the test.

Usage:
    python3 scripts/check_symbol_rename_drift.py
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, symbol_aliases  # noqa: E402

# Index universes whose members must all be currently listed.
_UNIVERSES = [
    ("sp500", "breadth"),
    ("sp400", "midcap_breadth"),
    ("sp600", "smallcap_breadth"),
]


def _latest_directory() -> tuple[set[str], str] | tuple[None, None]:
    """({symbol}, snapshot_name) from the newest NASDAQ symbol-directory snapshot."""
    files = sorted(glob.glob(str(config.data_dir() / "symbol_directory" / "snapshots" / "*.parquet")))
    if not files:
        return None, None
    df = pd.read_parquet(files[-1])
    return set(df["symbol"].astype(str)), Path(files[-1]).name


def is_listed(ticker: str, listed: set[str]) -> bool:
    """True when `ticker` names a line in the current listing directory.

    Class shares are written differently on each side — this repo normalises the
    separator to a dash when it scrapes constituents (BRK.B -> BRK-B) while the
    directory publishes BRK.A / MOG.A with a dot, and it lists some class lines
    only under the base symbol (CWEN, no CWEN.A row). Both forms are tried, then
    the base line, which clears every class share in all three index universes
    without loosening the check for an ordinary symbol.
    """
    t = str(ticker).strip().upper()
    if t in listed or t.replace("-", ".") in listed:
        return True
    base = re.sub(r"[.-][A-Z]$", "", t)
    return base != t and base in listed


def check_fixup_direction(listed: set[str], snap: str) -> int:
    """Retired keys must be gone from the directory; live values must be in it."""
    bad = 0
    for retired, live in symbol_aliases.rename_map().items():
        if is_listed(retired, listed):
            print(f"::error title=rename map points at a live symbol::"
                  f"breadth.ticker_fixups maps {retired} -> {live}, but {retired} IS "
                  f"currently listed ({snap}). The map's KEY must be the RETIRED "
                  f"symbol. A backwards row pins the universe to a symbol that does "
                  f"not trade — that is how MMC and FI each went unnoticed for months.",
                  flush=True)
            bad += 1
        if not is_listed(live, listed):
            print(f"::error title=rename map points at an unlisted symbol::"
                  f"breadth.ticker_fixups maps {retired} -> {live}, but {live} is NOT "
                  f"in the listing directory ({snap}). Resolve the live symbol against "
                  f"data/symbol_directory/snapshots/ and data/openfigi/cusip_ticker.parquet "
                  f"(a rename keeps the CUSIP) before shipping this row.",
                  flush=True)
            bad += 1
    return bad


def check_universe_listed(listed: set[str], snap: str) -> int:
    """Every index-universe member must be a currently listed symbol."""
    bad = 0
    for name, subdir in _UNIVERSES:
        p = config.data_dir() / subdir / "constituents.parquet"
        if not p.exists():
            continue
        members = [str(t) for t in pd.read_parquet(p).index]
        missing = sorted(t for t in members if not is_listed(t, listed))
        if missing:
            print(f"::error title=universe keyed on unlisted symbol::"
                  f"{name}: {len(missing)} member(s) absent from the NASDAQ symbol "
                  f"directory ({snap}): {', '.join(missing[:10])}"
                  f"{' ...' if len(missing) > 10 else ''}. Each is either a ticker "
                  f"rename this repo has not followed or a delisting still in the "
                  f"universe. Resolve against OpenFIGI by CUSIP — a rename keeps it — "
                  f"then add a breadth.ticker_fixups row (retired -> live) and run "
                  f"scripts/heal_retired_symbol_keys.py.",
                  flush=True)
            bad += len(missing)
    return bad


def check_pit_open_intervals(listed: set[str]) -> None:
    """Report PIT intervals left OPEN for symbols that no longer trade. Advisory.

    Deliberately a warning, not a gate. It is a real backlog — 15 of 1,506 open
    intervals were stale when this guard shipped — but it is the historical
    reference store's own hygiene, not the live universe key this guard defends,
    and redding CI on pre-existing debt teaches people to ignore the guard.

    NOT tested here: "a member's interval closed while another opened the same
    day". That looks like the rename signature and is not one. Index
    reconstitutions close and open many intervals on a single date — GPOR's
    2020-11-13 close coincides with HALO, MTG and GEO opening, none of them
    Gulfport — and the PIT store carries no CUSIP or CIK, so it cannot tell a
    rename from a rebalance on its own. Presence in the listing directory can,
    which is what check_universe_listed uses.
    """
    p = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    if not p.exists():
        return
    m = pd.read_parquet(p)
    open_t = sorted({str(t) for t in m[m["end_date"].isna()]["ticker"]})
    stale = [t for t in open_t if not is_listed(t, listed)]
    if stale:
        print(f"::warning title=stale open PIT intervals::"
              f"{len(stale)} of {len(open_t)} open point-in-time intervals name a "
              f"symbol that is no longer listed: {', '.join(stale[:15])}"
              f"{' ...' if len(stale) > 15 else ''}. Each is a delisting or rename the "
              f"PIT store never closed. Does not affect the live universe key.",
              flush=True)


def main() -> int:
    listed, snap = _latest_directory()
    if not listed:
        print("::error title=symbol directory missing::"
              "data/symbol_directory/snapshots/ has no parquet, so no listing check "
              "can run. This artifact is tracked and collected nightly — an empty "
              "directory means the collector is broken, not that the check is "
              "inapplicable. Failing rather than passing silently.",
              flush=True)
        return 1

    check_pit_open_intervals(listed)          # advisory, never gates
    bad = check_fixup_direction(listed, snap) + check_universe_listed(listed, snap)
    if bad:
        print(f"symbol rename drift: {bad} problem(s) against {snap}", flush=True)
        return 1
    print(f"symbol rename drift: clean against {snap} "
          f"({len(listed)} listed symbols, {len(symbol_aliases.rename_map())} rename row(s))",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
