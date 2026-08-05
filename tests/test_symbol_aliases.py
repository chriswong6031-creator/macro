"""Retired-ticker resolution: lib.symbol_aliases and the readers wired to it.

A US listing can change ticker without changing company, CUSIP, or listing. When
that happens the vendor-fed collectors follow within days and the universe-keyed
half does not, so one company accrues as two — which is what happened to Marsh
McLennan (MMC -> MRSH, 2026-01-14) for ~7 months and Fiserv (FI -> FISV,
2025-11-11) for ~9. These tests pin the three properties that keep the halves
joined, plus the one property that keeps the join honest: it must never turn a
genuine absence into a neighbouring company's data.
"""
import json
import logging
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, symbol_aliases          # noqa: E402
from engine import ai_desk                      # noqa: E402
from engine.altdata_models import _valid_ticker  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_resolve_is_identity_for_a_live_symbol():
    assert symbol_aliases.resolve("AAPL") == "AAPL"
    assert symbol_aliases.resolve("MRSH") == "MRSH"
    assert symbol_aliases.resolve("FISV") == "FISV"


def test_resolve_maps_retired_to_live_and_normalises_case():
    assert symbol_aliases.resolve("MMC") == "MRSH"
    assert symbol_aliases.resolve("  mmc  ") == "MRSH"
    assert symbol_aliases.resolve("fi") == "FISV"


def test_map_never_contains_a_self_referential_row():
    """A self-map would make resolve() a no-op that reads as working."""
    assert all(k != v for k, v in symbol_aliases.rename_map().items())


def test_no_chained_renames():
    """Values must be the CURRENTLY live symbol, never an intermediate — resolve()
    takes exactly one hop, so a chain would silently resolve only halfway."""
    m = symbol_aliases.rename_map()
    assert not (set(m.values()) & set(m)), (
        f"a rename value is also a rename key: {set(m.values()) & set(m)}")


def test_retired_and_all_symbols_round_trip():
    assert symbol_aliases.retired_for("MRSH") == ["MMC"]
    assert symbol_aliases.all_symbols_for("MMC") == ["MRSH", "MMC"]
    assert symbol_aliases.all_symbols_for("AAPL") == ["AAPL"]


# --------------------------------------------------------------------------- #
# the price layer forward claims grade on
# --------------------------------------------------------------------------- #

def test_close_series_serves_a_retired_symbol_from_the_live_one(caplog):
    """The property the operator's STRAND ruling depends on.

    Before this wiring _close_series('MMC') returned None on every rung — yahoo
    has no MMC.parquet and the breadth cache column was 0/345 non-null — so all 13
    stranded claims would have graded against nothing at all.
    """
    live = ai_desk._close_series("MRSH", str(ROOT))
    if live is None or live.empty:
        pytest.skip("no MRSH price series in this checkout")
    with caplog.at_level(logging.WARNING, logger="engine.ai_desk"):
        retired = ai_desk._close_series("MMC", str(ROOT))
    assert retired is not None and len(retired) == len(live)
    # and it must SAY so — a silent alias hop is how the split stayed invisible
    assert any("retired symbol" in r.getMessage() for r in caplog.records), \
        "the alias hop must be logged, not silent"


def test_close_series_does_not_invent_data_for_an_absent_symbol():
    """The alias rung must not turn 'no such ticker' into someone else's prices."""
    assert ai_desk._close_series("ZZZQQ", str(ROOT)) is None


def test_close_series_prefers_the_direct_read_over_the_alias():
    """A live symbol resolves from its own store, never through the rename map."""
    direct = ai_desk._close_series_direct("FISV", str(ROOT))
    if direct is None:
        pytest.skip("no FISV price series in this checkout")
    assert ai_desk._close_series("FISV", str(ROOT)).equals(direct)


# --------------------------------------------------------------------------- #
# the convergence board: one company, one record
# --------------------------------------------------------------------------- #

def test_altdata_hygiene_gate_collapses_a_rename_onto_one_key():
    """Marsh sat on the alt-data board as two companies with different scores."""
    assert _valid_ticker("MMC") == "MRSH"
    assert _valid_ticker("MRSH") == "MRSH"
    assert _valid_ticker("FI") == "FISV"


def test_altdata_hygiene_gate_still_rejects_junk_and_keeps_other_tickers():
    assert _valid_ticker("N/A") is None
    assert _valid_ticker("") is None
    assert _valid_ticker("AAPL") == "AAPL"


# --------------------------------------------------------------------------- #
# a rename is not a death
# --------------------------------------------------------------------------- #

def test_renamed_tickers_are_not_in_the_dead_name_universe():
    from collectors import edgar_deadnames
    p = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    if not p.exists():
        pytest.skip("no PIT membership store")
    dead = set(edgar_deadnames.dead_universe())
    for retired in symbol_aliases.rename_map():
        assert retired not in dead, (
            f"{retired} was RENAMED, not delisted — processing it as a dead name "
            "hunts for the final filings of a company that never stopped filing")


def test_a_genuinely_dead_ticker_is_still_dead():
    """The exclusion must be narrow. ECHO's PIT interval closed because Echo Global
    Logistics was acquired in 2021; EchoStar later took the symbol. The old filer
    is still dead-name work, and a ticker REUSE must not be read as a rename."""
    from collectors import edgar_deadnames
    p = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    if not p.exists():
        pytest.skip("no PIT membership store")
    assert "ECHO" in set(edgar_deadnames.dead_universe())


# --------------------------------------------------------------------------- #
# the stranding receipt
# --------------------------------------------------------------------------- #

def test_stranded_claims_carry_a_disclosure_that_matches_the_ledger():
    """Operator ruling 2026-08-05: strand the open MMC claims, disclose them. The
    receipt has to keep matching the ledger it describes, or it is decoration."""
    dp = config.data_dir() / "qledger" / "retired_symbol_disclosures.json"
    assert dp.exists(), "the STRAND ruling requires a disclosure record"
    doc = json.loads(dp.read_text())
    entry = next(d for d in doc["disclosures"] if d["retired_symbol"] == "MMC")
    assert entry["live_symbol"] == "MRSH"
    assert entry["ruling"].startswith("STRAND")

    cp = config.data_dir() / "qledger" / "claims.jsonl"
    if not cp.exists():
        pytest.skip("no claims ledger")
    claims = [json.loads(l) for l in cp.read_text().splitlines() if l.strip()]
    mmc = {c["claim_id"] for c in claims if c.get("scope", {}).get("key") == "MMC"}
    disclosed = next(s for s in entry["stranded"] if s["store"].endswith("claims.jsonl"))
    assert set(disclosed["claim_ids"]) == mmc, (
        "the disclosure names a different set of claims than the ledger holds")
    assert disclosed["rows"] == len(mmc)


def test_no_new_claims_are_registered_under_a_retired_symbol():
    """Stranding is about EXISTING rows. Anything registered after the rename date
    under the retired symbol means a writer is still keyed on a dead ticker."""
    cp = config.data_dir() / "qledger" / "claims.jsonl"
    if not cp.exists():
        pytest.skip("no claims ledger")
    claims = [json.loads(l) for l in cp.read_text().splitlines() if l.strip()]
    disclosures = json.loads(
        (config.data_dir() / "qledger" / "retired_symbol_disclosures.json").read_text())
    known = {d["retired_symbol"]: d for d in disclosures["disclosures"]}
    stranded = {cid for d in known.values() for s in d["stranded"]
                for cid in s.get("claim_ids", [])}
    for c in claims:
        key = c.get("scope", {}).get("key")
        if key in known and c["claim_id"] not in stranded:
            raise AssertionError(
                f"claim {c['claim_id']} (asof {c.get('asof')}) is scoped to the retired "
                f"symbol {key} but is not in the disclosure. Either it predates the "
                f"disclosure and belongs in it, or a writer is still keyed on {key} "
                f"instead of {known[key]['live_symbol']}.")
