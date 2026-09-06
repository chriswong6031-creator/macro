"""Tests for packet B-A-F01-2: F01 credit/commodity data-plane wiring trace.

Pure stdlib pytest. No network, no `gh`, no engine imports. Guards the trace and DSC
record against the plane moving underneath them (per the packet's honesty law).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "research/market_intelligence_productization/F01_CREDIT_AND_COMMODITY_WIRING_TRACE_2026-09-06.md"
DSC = ROOT / "agentos/discoveries/DSC-F01-CREDIT-PLANE-IS-SINGLE-ISSUER-ONLY.md"

PATH_RE = re.compile(r"(?:engine|scripts|templates|tests|lib|app)/[A-Za-z0-9_./-]+\.(?:py|j2|html|yml|json)")
ANCHOR_RE = re.compile(
    r"((?:engine|scripts|templates|tests|lib|app)/[A-Za-z0-9_./-]+\.(?:py|j2|html|yml|json)):(\d+)(?:-(\d+))?"
)

# Named in §5 as an in-flight PR (#6904) NOT yet merged to main at the time this trace
# was written — the trace explicitly states these do not exist on main yet, so the
# generic existence check must not fail on them. test_trace_names_the_in_flight_credit_window
# separately guards that the trace stays honest once #6904 does merge.
NOT_YET_ON_MAIN = {
    "engine/credit_window.py",
    "tests/test_credit_window.py",
}

REQUIRED_PATHS = {
    "engine/credit_momentum.py",
    "engine/bond_cross_asset.py",
    "engine/market_drivers.py",
    "templates/bonds.html.j2",
    "templates/commodities.html.j2",
    "templates/commodity_strategies.html.j2",
    "templates/spr.html.j2",
    "scripts/build_bonds.py",
    "scripts/build_commodities.py",
    "scripts/build_commodity_strategies.py",
    "scripts/build_spr.py",
}


def _trace_text() -> str:
    return TRACE.read_text(encoding="utf-8")


def _dsc_text() -> str:
    return DSC.read_text(encoding="utf-8")


def _extract_paths(text: str) -> set[str]:
    found = set()
    for m in PATH_RE.findall(text):
        p = m.rstrip(").,;:")
        found.add(p)
    return found


def test_trace_and_dsc_exist():
    assert TRACE.exists(), f"missing trace at {TRACE}"
    assert DSC.exists(), f"missing DSC at {DSC}"
    assert len(_trace_text().strip()) > 0
    assert len(_dsc_text().strip()) > 0


def test_every_source_path_named_in_the_trace_still_exists():
    text = _trace_text()
    paths = _extract_paths(text)
    # sparse-worktree law: data/ and site/ trees are omitted, never assert on them
    paths = {p for p in paths if not p.startswith("data/") and not p.startswith("site/")}
    assert paths, "path-extraction regex matched nothing — regex is broken"
    missing_required = REQUIRED_PATHS - paths
    assert not missing_required, f"trace is missing required anchors: {missing_required}"
    checkable = paths - NOT_YET_ON_MAIN
    missing_on_disk = sorted(p for p in checkable if not (ROOT / p).exists())
    assert not missing_on_disk, f"trace names paths that no longer exist: {missing_on_disk}"


def test_line_anchors_are_in_range():
    text = _trace_text()
    for path, start, end in ANCHOR_RE.findall(text):
        if path.startswith("data/") or path.startswith("site/"):
            continue
        full = ROOT / path
        if not full.exists():
            continue
        n_lines = sum(1 for _ in full.open("r", encoding="utf-8", errors="replace"))
        start_n = int(start)
        assert n_lines >= start_n, f"{path}:{start} out of range (file has {n_lines} lines)"
        if end:
            end_n = int(end)
            assert n_lines >= end_n, f"{path}:{start}-{end} out of range (file has {n_lines} lines)"


def test_dsc_carries_both_admission_gates():
    text = _dsc_text()
    fields = {}
    current_key = None
    buf = []
    for line in text.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m and m.group(1) in {
            "key", "claim", "falsifier", "so_what", "kind",
            "verified_at", "verified_by", "scope", "confidence",
        }:
            if current_key is not None:
                fields[current_key] = "\n".join(buf).strip()
            current_key = m.group(1)
            buf = [m.group(2)] if m.group(2) and m.group(2) != ">" else []
        elif current_key is not None:
            if line.strip() == "":
                continue
            buf.append(line.strip())
    if current_key is not None:
        fields[current_key] = "\n".join(buf).strip()

    required = ["key", "claim", "falsifier", "so_what", "kind", "verified_at", "verified_by", "scope", "confidence"]
    for f in required:
        assert f in fields and fields[f], f"DSC missing or empty field: {f}"

    assert len(fields["falsifier"]) > 40, "falsifier reads like a stub"
    assert len(fields["so_what"]) > 40, "so_what reads like a stub"


def test_trace_records_the_undischarged_rows():
    text = _trace_text()
    for token in ("MO-DELTA-008", "MO-DELTA-013", "MO-PAID-004", "read pass done, build child now scopable"):
        assert token in text, f"trace missing required token: {token}"
    assert "MO-DELTA-008 closed" not in text, "trace must never claim MO-DELTA-008 is closed"


def test_trace_names_the_in_flight_credit_window():
    text = _trace_text()
    assert "engine/credit_window.py" in text
    assert "#6904" in text
    if (ROOT / "engine/credit_window.py").exists():
        # #6904 has merged since this trace was written; staleness must stay visible,
        # not silently pass. Do not assert absence — that would break on merge.
        assert "§5" in text or "In-flight reconciliation" in text
