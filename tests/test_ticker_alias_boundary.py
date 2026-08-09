"""Regression teeth for the stable-key / price-vendor alias boundary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import edgar_deadnames  # noqa: E402
from engine import ai_desk, altdata_models  # noqa: E402
from lib import ticker_aliases  # noqa: E402
from scripts import check_symbol_rename_drift, heal_retired_symbol_keys  # noqa: E402


def test_no_competing_company_identity_alias_module() -> None:
    assert not (ROOT / "lib" / "symbol_aliases.py").exists()
    assert ticker_aliases.fetch_symbol("MMC") == "MRSH"
    assert ticker_aliases.store_key("MRSH") == "MMC"
    assert ticker_aliases.fetch_symbol("FI") == "FISV"
    assert ticker_aliases.store_key("FISV") == "FI"


def test_altdata_provider_keys_collapse_to_stable_company_keys() -> None:
    assert altdata_models._valid_ticker("MRSH") == "MMC"
    assert altdata_models._valid_ticker("FISV") == "FI"
    assert altdata_models._valid_ticker("AAPL") == "AAPL"


def test_ai_desk_reads_vendor_alias_only_after_stable_store_misses(tmp_path: Path) -> None:
    yahoo = tmp_path / "data" / "yahoo"
    yahoo.mkdir(parents=True)
    index = pd.date_range("2026-08-03", periods=3)
    pd.DataFrame({"close": [180.0, 181.0, 182.0]}, index=index).to_parquet(
        yahoo / "MRSH.parquet"
    )
    ai_desk._BREADTH_MEMO.clear()
    ai_desk._CLOSE_MEMO.clear()
    series = ai_desk._close_series("MMC", tmp_path)
    assert series is not None and list(series) == [180.0, 181.0, 182.0]
    assert not (yahoo / "MMC.parquet").exists(), "a read must not mint a second store"


def test_healer_inverts_vendor_columns_back_to_stable_keys() -> None:
    frame = pd.DataFrame({"MRSH": [1.0], "AAPL": [2.0]})
    healed, hits = heal_retired_symbol_keys._rekey_axis(
        frame, "columns", ticker_aliases.YAHOO_FETCH_ALIASES
    )
    assert hits == {"MRSH": "MMC"}
    assert list(healed.columns) == ["MMC", "AAPL"]


def test_dead_name_universe_excludes_known_listing_moves() -> None:
    frame = pd.DataFrame({
        "ticker": ["MMC", "MRSH", "FI", "FISV", "ECHO"],
        "end_date": ["2026-01-14", None, "2025-11-11", None, "2021-01-01"],
    })
    assert edgar_deadnames._dead_only(frame) == {"ECHO"}


def test_disclosure_rows_match_the_boundary_and_observed_minima() -> None:
    path = ROOT / "data" / "qledger" / "retired_symbol_disclosures.json"
    document = json.loads(path.read_text())
    assert document["authority"] == "facts_and_context_only"
    rows = {row["stable_key"]: row for row in document["disclosures"]}
    assert {key: row["vendor_symbol"] for key, row in rows.items()} == {
        "MMC": "MRSH", "FI": "FISV"
    }

    counts = {"MMC": 0, "FI": 0}
    claims = ROOT / "data" / "qledger" / "claims.jsonl"
    for line in claims.read_text().splitlines():
        row = json.loads(line)
        key = str((row.get("scope") or {}).get("key", "")).upper()
        if key in counts and row.get("status") == "open":
            counts[key] += 1
    for key, count in counts.items():
        minimum = rows[key]["observed_stable_rows"][
            "data/qledger/claims.jsonl_open_minimum"
        ]
        assert count >= minimum


def test_repository_alias_guard_is_green() -> None:
    assert check_symbol_rename_drift.main() == 0
