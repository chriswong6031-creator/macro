"""Tests for engine/commodity_cycle_state.py — commodity-cycle structural clock bridge.

Deliverable 4 of the P3 data bridge (cycle.html ↔ commodity engine).

Run: python -m pytest tests/test_commodity_cycle_state.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import commodity_cycle_state as ccs  # noqa: E402
from engine.regime_prior import _read_commodity_complex, regime_prior  # noqa: E402

# --------------------------------------------------------------------------- #
# Expected mapped member names (subset — must all appear in CYCLE_TO_MEMBERS
# fanout)
# --------------------------------------------------------------------------- #
_ALL_MAPPED_MEMBERS: frozenset[str] = frozenset(
    m for members in ccs.CYCLE_TO_MEMBERS.values() for m in members
)
# 10 members: gold silver copper oil natgas platinum palladium corn wheat soybeans
_EXPECTED_COUNT = 10

# Required CycleEntry fields
_REQUIRED_FIELDS = frozenset(
    {
        "cycle_ref",
        "pos",
        "phase",
        "phase_v2",
        "overdue",
        "overdue_frac",
        "hazard_1m",
        "hazard_3m",
        "hazard_6m",
        "asof",
    }
)


# --------------------------------------------------------------------------- #
# build_cycle_positions() — may call real engine (data present on disk)
# --------------------------------------------------------------------------- #

class TestBuildCyclePositions:
    def test_returns_dict(self):
        result = ccs.build_cycle_positions()
        assert isinstance(result, dict)

    def test_keys_are_subset_of_mapped_members(self):
        result = ccs.build_cycle_positions()
        assert set(result.keys()).issubset(_ALL_MAPPED_MEMBERS), (
            f"unexpected keys: {set(result.keys()) - _ALL_MAPPED_MEMBERS}"
        )

    def test_each_value_has_required_fields(self):
        result = ccs.build_cycle_positions()
        for member, entry in result.items():
            missing = _REQUIRED_FIELDS - set(entry.keys())
            assert not missing, f"member {member!r} missing fields: {missing}"

    def test_json_serialisable(self):
        result = ccs.build_cycle_positions()
        # must not raise — no numpy scalars, no NaN
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_platinum_and_palladium_share_pgms_cycle_ref(self):
        result = ccs.build_cycle_positions()
        if "platinum" not in result or "palladium" not in result:
            pytest.skip("pgms cycle not available on this environment")
        assert result["platinum"]["cycle_ref"] == "pgms"
        assert result["palladium"]["cycle_ref"] == "pgms"
        # Both must have identical pos and phase (fanned out from same computation)
        assert result["platinum"]["pos"] == result["palladium"]["pos"]
        assert result["platinum"]["phase"] == result["palladium"]["phase"]

    def test_unmapped_member_absent(self):
        result = ccs.build_cycle_positions()
        for unmapped in ("coffee", "cattle", "gasoline", "heating_oil"):
            assert unmapped not in result, (
                f"{unmapped!r} should not appear in cycle_positions"
            )

    def test_cycle_ref_values_are_valid_cids(self):
        result = ccs.build_cycle_positions()
        valid_cids = set(ccs.CYCLE_TO_MEMBERS.keys())
        for member, entry in result.items():
            assert entry["cycle_ref"] in valid_cids, (
                f"member {member!r} has invalid cycle_ref {entry['cycle_ref']!r}"
            )

    def test_numeric_fields_are_float_or_none(self):
        result = ccs.build_cycle_positions()
        float_fields = ("pos", "overdue_frac", "hazard_1m", "hazard_3m", "hazard_6m")
        for member, entry in result.items():
            for field in float_fields:
                val = entry[field]
                assert val is None or isinstance(val, float), (
                    f"member {member!r} field {field!r} = {val!r} (expected float | None)"
                )

    def test_asof_is_date_string(self):
        result = ccs.build_cycle_positions()
        import re
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for member, entry in result.items():
            assert date_re.match(entry["asof"]), (
                f"member {member!r} asof={entry['asof']!r} is not YYYY-MM-DD"
            )

    def test_no_nan_in_serialised_output(self):
        result = ccs.build_cycle_positions()
        serialised = json.dumps(result)
        assert "NaN" not in serialised, "NaN found in JSON output — use None instead"
        assert "Infinity" not in serialised, "Infinity found in JSON output"


# --------------------------------------------------------------------------- #
# write_cycle_positions() — writes to a temp dir, checks file content
# --------------------------------------------------------------------------- #

class TestWriteCyclePositions:
    def test_writes_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            result = ccs.write_cycle_positions(data_dir=tmp_path)
            out_file = tmp_path / "commodity" / "cycle_positions.json"
            assert out_file.exists(), "cycle_positions.json was not created"
            loaded = json.loads(out_file.read_text())
            assert loaded == result

    def test_returns_same_as_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = ccs.write_cycle_positions(data_dir=Path(tmp))
            direct = ccs.build_cycle_positions()
            # Keys must match (order may differ)
            assert set(written.keys()) == set(direct.keys())


# --------------------------------------------------------------------------- #
# _read_commodity_complex() from regime_prior
# --------------------------------------------------------------------------- #

class TestReadCommodityComplex:
    def test_missing_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _read_commodity_complex(Path(tmp))
            assert result == {}

    def test_reads_written_fixture(self):
        fixture = {
            "asof": "2026-07-12",
            "complex_regime": "Risk-On",
            "dollar_dir": "down",
            "growth_dir": "up",
            "index": {"state": "trending_up"},
            "breadth": {"pct_up_trend": 0.72, "n_up": 9, "n_members": 12},
            "confluence": {"index": {"state": "bottom"}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "commodity").mkdir()
            (tmp_path / "commodity" / "complex_latest.json").write_text(
                json.dumps(fixture)
            )
            result = _read_commodity_complex(tmp_path)
            assert result["complex_regime"] == "Risk-On"
            assert result["breadth"]["pct_up_trend"] == 0.72

    def test_corrupted_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "commodity").mkdir()
            (tmp_path / "commodity" / "complex_latest.json").write_text(
                "not valid json {{{"
            )
            result = _read_commodity_complex(tmp_path)
            assert result == {}


# --------------------------------------------------------------------------- #
# regime_prior() — schema + commodity_complex key present
# --------------------------------------------------------------------------- #

class TestRegimePrior:
    def test_returns_dict_with_schema_1(self):
        result = regime_prior()
        assert isinstance(result, dict)
        assert result.get("schema") == 1

    def test_has_commodity_complex_key(self):
        result = regime_prior()
        assert "commodity_complex" in result, (
            "regime_prior() must include 'commodity_complex' key"
        )

    def test_commodity_complex_has_not_a_model_input(self):
        result = regime_prior()
        cc = result["commodity_complex"]
        assert isinstance(cc, dict)
        assert cc.get("not_a_model_input") is True

    def test_commodity_complex_has_status(self):
        result = regime_prior()
        cc = result["commodity_complex"]
        assert cc.get("status") in ("fresh", "stale", "unavailable", "partial")

    def test_sources_includes_commodity_complex(self):
        result = regime_prior()
        sources = result.get("sources") or {}
        assert "commodity_complex" in sources, (
            "sources dict must include commodity_complex entry"
        )

    def test_json_serialisable(self):
        result = regime_prior()
        serialised = json.dumps(result)
        assert isinstance(serialised, str)
        assert "NaN" not in serialised
