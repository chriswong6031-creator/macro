"""W3S dead-instrument control set — the screens that must REFUSE.

Registration: research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md
(operation SI-W3S-DEAD-CONTROL-V1). The acceptance tests there name five hostile
fixtures that must fail. Each is asserted here against a hermetic fixture repo, so a
future edit that "fixes" the shortfall by loosening a screen fails this file instead
of silently shipping a control set built out of living companies.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from engine.stock_identity import dead_control as dc  # noqa: E402

SNAPS = ["2026-07-13", "2026-08-10", "2026-08-27", "2026-08-29"]


def _tape(n: int, last: str, *, volume: bool = True, flat_tail: int = 0,
          cols=("open", "high", "low", "close", "volume")) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=n, name="Date")
    rng = np.random.default_rng(7)
    close = 50.0 + np.cumsum(rng.normal(0, 0.6, n))
    close = np.maximum(close, 1.0)
    if flat_tail:
        close[-flat_tail:] = close[-flat_tail - 1]
    vol = rng.integers(1_000_000, 4_000_000, n).astype(float)
    if flat_tail:
        vol[-flat_tail:] = 0.0
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": vol if volume else 0.0}, index=idx)
    return df[[c for c in cols if c in df.columns]]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Minimal hermetic repo the builder can screen."""
    (tmp_path / "config").mkdir()
    (tmp_path / "data/quality").mkdir(parents=True)
    (tmp_path / "data/edgar").mkdir(parents=True)
    (tmp_path / "data/symbol_directory/snapshots").mkdir(parents=True)
    (tmp_path / "data/baskets/ohlcv").mkdir(parents=True)
    (tmp_path / "data/stocks").mkdir(parents=True)
    (tmp_path / "data/stock_identity/ohlcv").mkdir(parents=True)
    (tmp_path / "config.yml").write_text(yaml.safe_dump({"quality": {}, "breadth": {}}))
    (tmp_path / "config/delisted_symbols.yml").write_text(yaml.safe_dump({"version": 1, "symbols": {}}))
    (tmp_path / "data/quality/reused_tickers_audit.json").write_text(
        json.dumps({"unacked_delisted_printing": [], "delisted_printing_acks": []}))
    (tmp_path / "data/edgar/dead_name_cik.json").write_text("{}")
    (tmp_path / "data/edgar/dead_name_delisting.json").write_text("{}")
    for d in SNAPS:
        pd.DataFrame([{"date": d, "symbol": "KEEP", "security_name": "Keep Inc",
                       "exchange": "N", "etf": False, "test_issue": False,
                       "is_preferred": False, "source": "otherlisted"}]
                     ).to_parquet(tmp_path / f"data/symbol_directory/snapshots/{d}.parquet")
    return tmp_path


def _listed(repo: Path, sym: str, dates: list[str], **over) -> None:
    for d in dates:
        p = repo / f"data/symbol_directory/snapshots/{d}.parquet"
        df = pd.read_parquet(p)
        row = {"date": d, "symbol": sym, "security_name": f"{sym} Corp", "exchange": "N",
               "etf": False, "test_issue": False, "is_preferred": False, "source": "otherlisted"}
        row.update(over)
        pd.concat([df, pd.DataFrame([row])], ignore_index=True).to_parquet(p)


def _ledger(repo: Path, sym: str, **row) -> None:
    p = repo / "config/delisted_symbols.yml"
    d = yaml.safe_load(p.read_text())
    d["symbols"][sym] = {"company": f"{sym} Corp", "exchange": "NYSE", "cik": "0000000001",
                         "reason": "acquisition", "successor_ticker": None,
                         "receipts": ["form-25"], **row}
    p.write_text(yaml.safe_dump(d))


def _verdict(repo: Path, sym: str) -> dict:
    return next(c for c in dc.build_cohort(repo)["ledger"] if c["ticker"] == sym)


# --------------------------------------------------------------------------- #
# The control that MUST be accepted — otherwise every refusal below is vacuous.
# --------------------------------------------------------------------------- #
def test_a_clean_terminated_tape_is_accepted(repo: Path) -> None:
    _ledger(repo, "DEAD", last_session="2026-08-10")
    _listed(repo, "DEAD", ["2026-07-13", "2026-08-10"])
    _tape(600, "2026-08-10").to_parquet(repo / "data/baskets/ohlcv/DEAD.parquet")
    v = _verdict(repo, "DEAD")
    assert v["accepted"], v["reason"]
    assert v["receipt"]["price_plane_id"] == "baskets_ohlcv_v1"
    assert v["receipt"]["sessions"] >= dc.MIN_SESSIONS


# --------------------------------------------------------------------------- #
# Registration §8 hostile fixtures — each MUST fail.
# --------------------------------------------------------------------------- #
def test_live_name_relabeled_dead_is_refused(repo: Path) -> None:
    """A ledger row does not make a listed company dead."""
    _ledger(repo, "ALIVE", last_session="2026-08-29")
    _listed(repo, "ALIVE", SNAPS)                       # still in the latest snapshot
    _tape(600, "2026-08-29").to_parquet(repo / "data/baskets/ohlcv/ALIVE.parquet")
    v = _verdict(repo, "ALIVE")
    assert not v["accepted"]
    assert v["code"] == "E1_NOT_TERMINATED" and v["screen"] == "S1"


def test_index_exited_but_still_listed_is_refused(repo: Path) -> None:
    """dead_universe() closes on INDEX EXIT; 172 such names still trade."""
    (repo / "data/edgar/dead_name_delisting.json").write_text(json.dumps(
        {"IDX": {"method": "8k_item_5.01", "reason": "acquisition", "bankruptcy_accession": None}}))
    _listed(repo, "IDX", SNAPS)
    _tape(600, "2026-08-29").to_parquet(repo / "data/baskets/ohlcv/IDX.parquet")
    v = _verdict(repo, "IDX")
    assert not v["accepted"] and v["code"] == "E1_NOT_TERMINATED"


def test_otc_adr_never_exchange_listed_is_refused(repo: Path) -> None:
    """Absence from the exchange directory is an OTC ADR's normal LIVE state."""
    (repo / "data/edgar/dead_name_delisting.json").write_text(json.dumps(
        {"ADRX": {"method": "8k_item_5.01", "reason": "acquisition", "bankruptcy_accession": None}}))
    _tape(600, "2026-08-27").to_parquet(repo / "data/baskets/ohlcv/ADRX.parquet")
    v = _verdict(repo, "ADRX")
    assert not v["accepted"]
    assert v["code"] == "E3_NOT_US_LISTED" and v["screen"] == "S3"


def test_successor_spliced_tape_is_refused(repo: Path) -> None:
    """The AVB failure mode: real bars keep printing past the terminal date."""
    _ledger(repo, "SPLICE", last_session="2026-08-10")
    _listed(repo, "SPLICE", ["2026-07-13", "2026-08-10"])
    _tape(600, "2026-08-26").to_parquet(repo / "data/baskets/ohlcv/SPLICE.parquet")
    v = _verdict(repo, "SPLICE")
    assert not v["accepted"]
    assert v["code"] == "E8_TAPE_CONTAMINATED" and v["screen"] == "S8"
    assert v["receipt"]["bars_after_ledger_last_session"] > 0


def test_reused_ticker_is_refused(repo: Path) -> None:
    """A reused ticker splices a different company's history into one series."""
    (repo / "config.yml").write_text(yaml.safe_dump(
        {"quality": {"reused_ticker_acks": {"REUSE": "two issuers under one key"}}, "breadth": {}}))
    _ledger(repo, "REUSE", last_session="2026-08-10")
    _listed(repo, "REUSE", ["2026-07-13", "2026-08-10"])
    _tape(600, "2026-08-10").to_parquet(repo / "data/baskets/ohlcv/REUSE.parquet")
    v = _verdict(repo, "REUSE")
    assert not v["accepted"]
    assert v["code"] == "E9_IDENTITY_UNRESOLVED" and v["screen"] == "S4"


def test_key_migration_is_refused(repo: Path) -> None:
    """A rename keeps the instrument alive under a new key; it is not a death."""
    _ledger(repo, "OLDK", last_session="2026-08-10", successor_ticker="NEWK")
    _listed(repo, "OLDK", ["2026-07-13", "2026-08-10"])
    _tape(600, "2026-08-10").to_parquet(repo / "data/baskets/ohlcv/OLDK.parquet")
    v = _verdict(repo, "OLDK")
    assert not v["accepted"]
    assert v["code"] == "E2_KEY_MIGRATION" and v["screen"] == "S2"


def test_close_only_tape_is_refused(repo: Path) -> None:
    """Missing is an exclusion, never a partial control."""
    _ledger(repo, "CLOSEONLY", last_session="2026-08-10")
    _listed(repo, "CLOSEONLY", ["2026-07-13", "2026-08-10"])
    _tape(600, "2026-08-10", cols=("close",)).to_parquet(
        repo / "data/baskets/ohlcv/CLOSEONLY.parquet")
    v = _verdict(repo, "CLOSEONLY")
    assert not v["accepted"]
    assert v["code"] == "E6_NO_LAWFUL_ADJUSTED_OHLCV" and v["screen"] == "S5"


def test_short_history_is_refused(repo: Path) -> None:
    """Below MIN_SESSIONS the fingerprint is all-null — a hole, not a control."""
    _ledger(repo, "SHORT", last_session="2026-08-10")
    _listed(repo, "SHORT", ["2026-07-13", "2026-08-10"])
    _tape(100, "2026-08-10").to_parquet(repo / "data/baskets/ohlcv/SHORT.parquet")
    v = _verdict(repo, "SHORT")
    assert not v["accepted"]
    assert v["code"] == "E5_INSUFFICIENT_HISTORY" and v["screen"] == "S7"


def test_flat_forward_padding_is_stripped_not_counted(repo: Path) -> None:
    """The zero-volume flat-forward tell is padding, not a post-death print."""
    _ledger(repo, "PAD", last_session="2026-08-10")
    _listed(repo, "PAD", ["2026-07-13", "2026-08-10"])
    _tape(600, "2026-08-13", flat_tail=3).to_parquet(repo / "data/baskets/ohlcv/PAD.parquet")
    v = _verdict(repo, "PAD")
    assert v["accepted"], v["reason"]
    assert v["receipt"]["flat_forward_bars_stripped"] == 3


# --------------------------------------------------------------------------- #
# Law-level invariants
# --------------------------------------------------------------------------- #
def test_build_is_deterministic(repo: Path) -> None:
    _ledger(repo, "DEAD", last_session="2026-08-10")
    _listed(repo, "DEAD", ["2026-07-13", "2026-08-10"])
    _tape(600, "2026-08-10").to_parquet(repo / "data/baskets/ohlcv/DEAD.parquet")
    a = json.dumps(dc.build_cohort(repo), sort_keys=True)
    b = json.dumps(dc.build_cohort(repo), sort_keys=True)
    assert a == b


def test_cohort_carries_no_authority(repo: Path) -> None:
    """A control set describes; it never ranks, sizes, gates or escalates."""
    assert dc.build_cohort(repo)["authority"] == {
        "can_rank": False, "can_size": False, "can_gate": False,
        "can_escalate": False, "can_originate_signal": False}


def test_min_sessions_tracks_the_fingerprint_floor() -> None:
    """The floor is the machinery's, not a local knob."""
    from engine.stock_identity import fingerprint
    assert dc.MIN_SESSIONS == fingerprint.MIN_SESSIONS == 252
