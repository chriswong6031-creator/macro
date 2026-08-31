"""ZHC-509: Canada Entry column must carry the entry engine's owner-native labels.

The English ``entry_status`` slug remains the machine/sort/filter identity. Display
copy comes from the same deterministic ``engine.entry_signal.assess`` result via
``headline`` / ``headline_zh``; the template must not reconstruct or translate it.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
_HELPERS_SPEC = importlib.util.spec_from_file_location(
    "canada_build_test_helpers", ROOT / "tests" / "test_canada_build.py"
)
assert _HELPERS_SPEC and _HELPERS_SPEC.loader
_HELPERS = importlib.util.module_from_spec(_HELPERS_SPEC)
_HELPERS_SPEC.loader.exec_module(_HELPERS)


def _rendered_rows() -> tuple[dict, list[dict]]:
    vm = _HELPERS._w8g_vm()
    html = _HELPERS._env().get_template("canada.html.j2").render(**vm, mode="stocks")
    match = re.search(r'id="stocktable-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert match, "Canada stocktable-data block missing"
    return vm, json.loads(match.group(1))["rows"]


def test_canada_serializes_owner_native_entry_labels_beside_machine_status():
    """Each real row must preserve status and project its exact EN/ZH owner pair."""
    vm, serialized_rows = _rendered_rows()
    expected = {
        row["ticker"]: row["entry_signal"]
        for row in vm["setups"]["buy"]
    }

    assert [row["ticker"] for row in serialized_rows] == list(expected)
    for row in serialized_rows:
        owner = expected[row["ticker"]]
        assert row["entry_status"] == owner["status"]
        assert row["entry_status_label"] == owner["headline"]
        assert row["entry_status_label_zh"] == owner["headline_zh"]
