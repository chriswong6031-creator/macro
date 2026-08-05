"""Constituents repair guard for the breadth collectors (BreadthAdapter._repair).

Wikipedia's index-membership tables are community-edited and periodically ship a
stale pre-rename ticker, plus the odd non-ticker junk cell. Unrepaired, those
silently drop the real name from the searchable universe.

TWO KINDS OF TEST LIVE HERE, AND THE SPLIT IS THE POINT
-------------------------------------------------------
The mechanical tests build a synthetic fixups dict and assert _repair normalises,
de-junks, maps and dedups. They are pure-function and say nothing about which
symbols are real.

The DIRECTION tests read config.yml itself. That distinction is what this file got
wrong before: every test here built its own ``{"MRSH": "MMC", "FISV": "FI"}`` dict
and asserted ``"MRSH" not in syms``. So the suite passed for ~7 months while the
shipping config pointed the map BACKWARDS — repairing Marsh McLennan's live NYSE
symbol (MRSH, renamed from MMC on 2026-01-14) into the retired one, and Fiserv's
live FISV into the retired FI. Flipping config to the correct direction would not
have failed a single assertion, and the suite would have gone on enforcing the
retired direction in perpetuity. A guard that supplies its own copy of the value
under test cannot see the defect it exists to catch.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import BreadthAdapter  # noqa: E402
from lib import config, symbol_aliases         # noqa: E402


def _adapter(fixups: dict) -> BreadthAdapter:
    # skip __init__/config.load — _repair only reads self.cfg + self.name
    a = BreadthAdapter.__new__(BreadthAdapter)
    a.cfg = {"ticker_fixups": fixups}
    return a


def _shipping_fixups() -> dict:
    return (config.load().get("breadth", {}) or {}).get("ticker_fixups") or {}


# --------------------------------------------------------------------------- #
# direction — reads the REAL config, so an inverted row fails here
# --------------------------------------------------------------------------- #

def test_shipping_fixups_map_retired_to_live_not_the_reverse():
    """The map's KEY is the retired symbol and its VALUE is the one that trades.

    Pinned against the live listing record rather than a hardcoded expectation, so
    this keeps working when the next rename lands. data/symbol_directory/snapshots
    is the NASDAQ-published listing file: the retired symbol is absent from it, the
    live symbol is present.
    """
    import glob
    snaps = sorted(glob.glob(str(config.data_dir() / "symbol_directory" / "snapshots" / "*.parquet")))
    if not snaps:
        pytest.skip("no symbol-directory snapshot available")
    listed = set(pd.read_parquet(snaps[-1])["symbol"].astype(str))
    from scripts.check_symbol_rename_drift import is_listed

    fixups = _shipping_fixups()
    assert fixups, "config.yml ships no breadth.ticker_fixups — expected at least one"
    for retired, live in fixups.items():
        assert not is_listed(retired, listed), (
            f"breadth.ticker_fixups maps {retired} -> {live}, but {retired} is still "
            f"listed. The map is inverted: its key must be the RETIRED symbol.")
        assert is_listed(live, listed), (
            f"breadth.ticker_fixups maps {retired} -> {live}, but {live} is not in "
            f"the listing directory.")


def test_shipping_fixups_pin_the_two_known_renames():
    """Marsh and Fiserv specifically, by name — both were pinned backwards.

    A regression here means someone re-added the pre-2026-08-05 direction.
    """
    fixups = {k.upper(): v.upper() for k, v in _shipping_fixups().items()}
    assert fixups.get("MMC") == "MRSH", (
        "Marsh McLennan renamed MMC -> MRSH on 2026-01-14 (same CUSIP 571748102). "
        "MMC is the retired key; MRSH is the live value.")
    assert fixups.get("FI") == "FISV", (
        "Fiserv renamed FISV -> FI in 2023 and BACK FI -> FISV on 2025-11-11. "
        "FI is the retired key; FISV is the live value.")
    assert "MRSH" not in fixups and "FISV" not in fixups, (
        "a live symbol must never appear as a fixup KEY — that repairs the symbol "
        "that trades into one that does not")


def test_repair_uses_the_shipping_config_direction():
    """_repair driven by the REAL config maps the retired symbol to the live one."""
    a = _adapter(_shipping_fixups())
    df = pd.DataFrame({
        "symbol": ["AAPL", "MMC", "FI"],
        "name": ["Apple", "Marsh McLennan", "Fiserv"],
        "sector": ["IT", "Fin", "Fin"],
    })
    syms = list(a._repair(df)["symbol"])
    assert "MRSH" in syms and "FISV" in syms
    assert "MMC" not in syms and "FI" not in syms


def test_symbol_aliases_agrees_with_the_shipping_config():
    """lib.symbol_aliases is the site-wide reader of this same map — one list."""
    assert symbol_aliases.rename_map() == {
        k.upper(): v.upper() for k, v in _shipping_fixups().items() if k.upper() != v.upper()}
    assert symbol_aliases.resolve("MMC") == "MRSH"
    assert symbol_aliases.resolve("MRSH") == "MRSH"       # live symbol is a fixed point
    assert symbol_aliases.retired_for("MRSH") == ["MMC"]


# --------------------------------------------------------------------------- #
# mechanics — synthetic fixups, direction-agnostic
# --------------------------------------------------------------------------- #

def test_repair_maps_stale_symbols_and_drops_junk():
    a = _adapter({"MMC": "MRSH", "FI": "FISV"})
    df = pd.DataFrame({
        "symbol": ["AAPL", "BRK.B", "MMC", "FI", "—", "n/a", "MRSH"],
        "name": ["Apple", "Berkshire", "Marsh McLennan", "Fiserv",
                 "junk", "junk", "Marsh dup"],
        "sector": ["IT", "Fin", "Fin", "Fin", "x", "x", "Fin"],
    })
    out = a._repair(df)
    syms = list(out["symbol"])
    # stale symbols repaired to the current ticker
    assert "MRSH" in syms and "FISV" in syms
    assert "MMC" not in syms and "FI" not in syms
    # BRK.B normalised to the yfinance form
    assert "BRK-B" in syms
    # non-ticker junk dropped
    assert "—" not in syms and "N/A" not in syms
    # the repaired MMC row collides with the genuine MRSH row -> kept once
    assert syms.count("MRSH") == 1
    # output keeps the reference columns and a clean index
    assert list(out.columns) == ["symbol", "name", "sector"]


def test_repair_is_noop_without_fixups():
    a = _adapter({})
    df = pd.DataFrame({"symbol": ["AAPL", "MSFT", "BRK.B"],
                       "name": ["a", "b", "c"], "sector": ["IT", "IT", "Fin"]})
    out = a._repair(df)
    assert list(out["symbol"]) == ["AAPL", "MSFT", "BRK-B"]


def test_repair_handles_lowercase_and_whitespace_symbols():
    a = _adapter({"FI": "FISV"})
    df = pd.DataFrame({"symbol": [" aapl ", "fi"],
                       "name": ["Apple", "Fiserv"], "sector": ["IT", "Fin"]})
    out = a._repair(df)
    assert set(out["symbol"]) == {"AAPL", "FISV"}
