"""tests/test_ofac_sdn_collector.py — parser + persist contract for collectors/ofac_sdn.py."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from unittest import mock

import collectors.ofac_sdn as ofac_sdn
from engine.sanctions_map import split_program_field


def test_extract_program_codes_matches_engine_splitter():
    csv_text = '1,"x","y","[A] [B]"\n2,"x","y","[C]  [D]"\n3,"x","y","-0-"\n'
    codes = ofac_sdn.extract_program_codes(csv_text)
    assert codes == ["A", "B", "C", "D"]
    # Same tokens the engine splitter would emit from each field.
    assert split_program_field("[A] [B]") == ["A", "B"]
    assert split_program_field("[C]  [D]") == ["C", "D"]


def test_persist_snapshot_writes_published_date(tmp_path, monkeypatch):
    monkeypatch.setattr(ofac_sdn, "STORE_DIR", tmp_path)
    monkeypatch.setattr(ofac_sdn, "STORE_FILE", tmp_path / "sdn_snapshot.csv.gz")
    monkeypatch.setattr(ofac_sdn, "META_FILE", tmp_path / "meta.json")
    meta = ofac_sdn.persist_snapshot("1,a,b,IRAN\n", list_published_date="2026-09-04")
    assert meta["list_published_date"] == "2026-09-04"
    assert meta["source_url"] == ofac_sdn.OFAC_SDN_CSV_URL
    written_csv = gzip.decompress((tmp_path / "sdn_snapshot.csv.gz").read_bytes()).decode("utf-8")
    assert written_csv.startswith("1,")
    written = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert written["list_published_date"] == "2026-09-04"


def test_run_passes_last_modified_as_published_date(tmp_path, monkeypatch):
    monkeypatch.setattr(ofac_sdn, "STORE_DIR", tmp_path)
    monkeypatch.setattr(ofac_sdn, "STORE_FILE", tmp_path / "sdn_snapshot.csv.gz")
    monkeypatch.setattr(ofac_sdn, "META_FILE", tmp_path / "meta.json")

    def fake_fetch(timeout: int = 30):
        return '1,"n","a","IRAN"\n', "2026-09-05"

    monkeypatch.setattr(ofac_sdn, "fetch_sdn_csv", fake_fetch)
    result = ofac_sdn.run()
    assert result["ok"] is True
    assert result["list_published_date"] == "2026-09-05"
    assert result["n_codes"] == 1
