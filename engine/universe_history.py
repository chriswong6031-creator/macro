"""Point-in-time index-membership ledger — the go-forward survivorship fix.

The factor universe is read from today's S&P 1500 constituents, so any historical
cross-section silently uses today's members (survivorship bias: delisted/dropped
names are absent). The EDGAR point-in-time panel removed look-ahead but cannot undo
survivorship for years already gone (free prices don't cover delisted names). What
we CAN do — for free, starting now — is record who is in the universe on each run,
so the membership history compounds into a survivorship-bias-free universe over time.

update_membership() upserts a ledger keyed by (ticker, group) with first_seen /
last_seen / active. A constituent present today refreshes last_seen; one that has
dropped out keeps its last_seen (the date it was last a member) and goes active=False.
as_of_members(date) then reconstructs the universe as it stood on a date — exact for
dates after accrual began, best-effort before (every current name's first_seen is the
first run, so pre-accrual reconstruction still inherits survivorship; that's the
documented cold-start limit). ADDITIVE: collect.py calls update_membership() each run.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

GROUPS = {"breadth": "sp500", "midcap_breadth": "sp400", "smallcap_breadth": "sp600"}
LEDGER_COLS = ["ticker", "group", "name", "sector", "first_seen", "last_seen", "active"]


def _ledger_path():
    p = config.data_dir() / "universe" / "membership.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _current_constituents() -> pd.DataFrame:
    """Today's members across the three index groups (ticker, group, name, sector)."""
    rows = []
    for grp, label in GROUPS.items():
        p = config.data_dir() / grp / "constituents.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        for t, r in df.iterrows():
            rows.append({"ticker": str(t), "group": label,
                         "name": str(r.get("name", t)), "sector": str(r.get("sector", "—"))})
    return pd.DataFrame(rows)


def load_ledger() -> pd.DataFrame | None:
    p = _ledger_path()
    return pd.read_parquet(p) if p.exists() else None


def update_membership(asof) -> pd.DataFrame:
    """Upsert today's constituents into the membership ledger and return it. A
    present member refreshes last_seen; a dropped member keeps last_seen and goes
    inactive. Idempotent within a day."""
    asof = pd.Timestamp(asof).normalize()
    cur = _current_constituents()
    if cur.empty:
        log.warning("universe membership: no constituents — skip")
        return load_ledger() if load_ledger() is not None else pd.DataFrame(columns=LEDGER_COLS)

    led = load_ledger()
    if led is None or led.empty:
        cur["first_seen"] = asof
        cur["last_seen"] = asof
        cur["active"] = True
        out = cur[LEDGER_COLS]
    else:
        led = led.set_index(["ticker", "group"])
        cur_keyed = cur.set_index(["ticker", "group"])
        present = set(cur_keyed.index)
        for key, r in cur_keyed.iterrows():
            if key in led.index:
                led.loc[key, "last_seen"] = asof
                led.loc[key, "active"] = True
                led.loc[key, "name"] = r["name"]
                led.loc[key, "sector"] = r["sector"]
            else:
                led.loc[key, ["name", "sector", "first_seen", "last_seen", "active"]] = \
                    [r["name"], r["sector"], asof, asof, True]
        # mark names no longer present as inactive (last_seen frozen)
        gone = [k for k in led.index if k not in present]
        for key in gone:
            led.loc[key, "active"] = False
        out = led.reset_index()[LEDGER_COLS]

    for c in ("first_seen", "last_seen"):
        out[c] = pd.to_datetime(out[c])
    out.to_parquet(_ledger_path(), index=False)
    n_active = int(out["active"].sum())
    log.info("universe membership: %d active / %d ever, asof %s", n_active, len(out), asof.date())
    return out


def as_of_members(asof, group: str | None = None, ledger: pd.DataFrame | None = None) -> list[str]:
    """Tickers that were index members on `asof` (first_seen <= asof <= last_seen).
    Exact only for dates after accrual began — see the cold-start caveat above."""
    led = ledger if ledger is not None else load_ledger()
    if led is None or led.empty:
        return []
    asof = pd.Timestamp(asof).normalize()
    m = (pd.to_datetime(led["first_seen"]) <= asof) & (pd.to_datetime(led["last_seen"]) >= asof)
    if group:
        m &= led["group"] == group
    return sorted(led.loc[m, "ticker"].unique().tolist())


def dropped_members(ledger: pd.DataFrame | None = None) -> list[str]:
    """Tickers that were once index members but have since dropped out (active=False).
    Retaining these in the EDGAR fundamentals universe keeps their data in the panel
    going forward — the fundamentals half of the survivorship fix (the ledger records
    WHEN names left; this keeps WHAT they last reported)."""
    led = ledger if ledger is not None else load_ledger()
    if led is None or led.empty or "active" not in led.columns:
        return []
    gone = led.loc[~led["active"].astype(bool), "ticker"]
    return sorted(gone.astype(str).unique().tolist())
