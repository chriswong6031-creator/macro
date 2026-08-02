"""gex_state_index tests (MSC R3.2/R3.3) — the cross-root positioning aggregate.

Pins the contracts the Terminal consumers depend on: row shape (glance-tier
fields only — no pin_probability/triggers), per-row asof dates with the index
asof = max, underscore/malformed-file exclusion, and the never-blank rule
(no rows → None, prior index left untouched by the writer).
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.gex_state_index import SCHEMA, build_index, write_index


def _state(root: str, **over) -> dict:
    base = {
        "schema": "options_structure.gex_state/v1",
        "asof": "2026-08-01T20:00:00+00:00",
        "root": root,
        "spot": 100.0,
        "net_gex_bn": 1.5,
        "gamma_regime": "PIN",
        "stability_pct": 82.0,
        "gamma_flip": 97.0,
        "dist_to_flip_pct": -3.0,
        "call_wall": 110.0,
        "put_wall": 90.0,
        "pin_probability": 0.61,
        "cascade_trigger": 88.0,
        "authority_tier": "display",
    }
    base.update(over)
    return base


def _write(d: Path, name: str, payload) -> None:
    (d / name).write_text(payload if isinstance(payload, str) else json.dumps(payload))


def test_index_shape_and_field_subset(tmp_path: Path) -> None:
    _write(tmp_path, "NVDA.json", _state("NVDA"))
    _write(tmp_path, "SPY.json", _state("SPY", gamma_regime="TREND", asof="2026-08-02T20:00:00+00:00"))
    idx = build_index(tmp_path)
    assert idx is not None
    assert idx["schema"] == SCHEMA
    assert idx["n_roots"] == 2
    row = idx["rows"]["NVDA"]
    assert row["gamma_regime"] == "PIN"
    assert row["call_wall"] == 110.0
    assert row["asof"] == "2026-08-01"
    # Tier-C / desk-only fields must NOT be distributed through the index.
    assert "pin_probability" not in row
    assert "cascade_trigger" not in row
    # Index asof = max of the row stamps (SPY's newer session wins).
    assert idx["asof"] == "2026-08-02T20:00:00+00:00"


def test_underscore_and_malformed_files_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "AMD.json", _state("AMD"))
    _write(tmp_path, "_index.json", {"schema": SCHEMA, "rows": {"STALE": {}}})
    _write(tmp_path, "BROKEN.json", "{not json")
    _write(tmp_path, "NOROOT.json", {"asof": "2026-08-01T00:00:00+00:00", "spot": 5})
    idx = build_index(tmp_path)
    assert idx is not None
    assert set(idx["rows"]) == {"AMD"}


def test_missing_fields_are_omitted_not_faked(tmp_path: Path) -> None:
    s = _state("XLE")
    del s["call_wall"]
    s["put_wall"] = None
    _write(tmp_path, "XLE.json", s)
    row = build_index(tmp_path)["rows"]["XLE"]
    assert "call_wall" not in row
    assert "put_wall" not in row
    assert row["gamma_flip"] == 97.0


def test_root_key_is_uppercased(tmp_path: Path) -> None:
    _write(tmp_path, "brk-b.json", _state("brk-b"))
    assert "BRK-B" in build_index(tmp_path)["rows"]


def test_empty_dir_returns_none_and_writer_preserves_prior(tmp_path: Path) -> None:
    prior = {"schema": SCHEMA, "asof": "x", "n_roots": 1, "rows": {"OLD": {"spot": 1}}}
    _write(tmp_path, "_index.json", prior)
    assert build_index(tmp_path) is None  # _index itself never counts as a row
    assert write_index(tmp_path) is None
    # the never-blank rule: the failed aggregation left the prior file untouched
    assert json.loads((tmp_path / "_index.json").read_text()) == prior


def test_write_index_roundtrip(tmp_path: Path) -> None:
    _write(tmp_path, "QQQ.json", _state("QQQ", gamma_regime="TRANSITION"))
    out = write_index(tmp_path)
    assert out is not None and out.name == "_index.json"
    idx = json.loads(out.read_text())
    assert idx["rows"]["QQQ"]["gamma_regime"] == "TRANSITION"
    # writer output must itself be excluded on a rebuild (idempotent)
    idx2 = build_index(tmp_path)
    assert set(idx2["rows"]) == {"QQQ"}


def test_missing_dir_is_nonfatal(tmp_path: Path) -> None:
    assert write_index(tmp_path / "nope") is None
