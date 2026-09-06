"""Tests for packet B-A-F01-2 — the F01 credit/commodity data-plane wiring trace.

Pure-stdlib pytest: no network, no `gh`, no engine imports. Asserts the trace and
the DSC exist, that every source path it names still exists on disk, that every
file:line anchor is still in range, and that the trace is honest about what it did
and did not discharge — so the record fails loudly when the plane moves.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "research/market_intelligence_productization/F01_CREDIT_AND_COMMODITY_WIRING_TRACE_2026-09-06.md"
DSC = ROOT / "agentos/discoveries/DSC-F01-CREDIT-PLANE-IS-SINGLE-ISSUER-ONLY.md"

# Deliberately excludes data/ and site/: those trees are omitted in sparse
# worktrees per the sparse-worktree law, so asserting on them would fail in
# every session checkout.
PATH_RE = re.compile(
    r"(?:engine|scripts|templates|tests|lib|app)/[A-Za-z0-9_./-]+\.(?:py|j2|html|yml|json)"
)
ANCHOR_RE = re.compile(
    r"((?:engine|scripts|templates|tests|lib|app)/[A-Za-z0-9_./-]+\.(?:py|j2|html|yml|json)):(\d+)(?:-(\d+))?"
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_trace_and_dsc_exist():
    assert TRACE.exists(), f"missing trace: {TRACE}"
    assert DSC.exists(), f"missing DSC: {DSC}"
    assert len(_read(TRACE).strip()) > 500
    assert len(_read(DSC).strip()) > 200


# Paths the trace deliberately names as NOT existing yet — the in-flight
# PR #6904 reconciliation in §5 discusses engine/credit_window.py and its
# test before that PR has merged. Their absence is the point being made,
# not a stale anchor, so they are excluded from the existence check (test 6
# separately asserts the trace still names them).
KNOWN_ABSENT_INFLIGHT = {"engine/credit_window.py", "tests/test_credit_window.py"}


def test_every_source_path_named_in_the_trace_still_exists():
    text = _read(TRACE)
    paths = set()
    for m in PATH_RE.findall(text):
        p = m.rstrip(").,;:")
        paths.add(p)
    assert paths, "regex extracted no repo paths from the trace — pattern regressed"
    required = {
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
    assert required.issubset(paths), f"missing required anchors: {required - paths}"
    checkable = paths - KNOWN_ABSENT_INFLIGHT
    missing = [p for p in checkable if not (ROOT / p).exists()]
    assert not missing, f"trace names paths that no longer exist: {missing}"


def test_line_anchors_are_in_range():
    text = _read(TRACE)
    line_counts: dict[str, int] = {}
    checked = 0
    for path, n, m in ANCHOR_RE.findall(text):
        clean = path.rstrip(").,;:")
        full = ROOT / clean
        if not full.exists():
            continue
        if clean not in line_counts:
            line_counts[clean] = len(_read(full).splitlines())
        count = line_counts[clean]
        n_i = int(n)
        assert count >= n_i, f"{clean} has {count} lines, trace cites line {n_i}"
        if m:
            m_i = int(m)
            assert count >= m_i, f"{clean} has {count} lines, trace cites range end {m_i}"
        checked += 1
    assert checked > 10, "too few line anchors were actually checked"


def test_dsc_carries_both_admission_gates():
    text = _read(DSC)
    assert text.startswith("---"), "DSC missing YAML frontmatter delimiter"
    end = text.index("\n---", 3)
    frontmatter = text[3:end]
    required_keys = [
        "key",
        "claim",
        "falsifier",
        "so_what",
        "kind",
        "verified_at",
        "verified_by",
        "scope",
        "confidence",
    ]
    try:
        import yaml  # type: ignore

        fields = yaml.safe_load(frontmatter) or {}
    except ImportError:
        # Minimal stdlib fallback: parse "key:" / "key: value" / block-scalar
        # (">"), keeping subsequent indented lines as part of the value.
        fields = {}
        current_key = None
        buf: list[str] = []
        for raw_line in frontmatter.splitlines():
            m = re.match(r"^([a-z_]+):\s?(.*)$", raw_line)
            is_indented = raw_line.startswith((" ", "\t"))
            if m and not is_indented:
                if current_key is not None:
                    fields[current_key] = "\n".join(buf).strip()
                current_key = m.group(1)
                rest = m.group(2)
                buf = [] if rest == ">" else [rest]
            elif current_key is not None:
                buf.append(raw_line.strip())
        if current_key is not None:
            fields[current_key] = "\n".join(buf).strip()

    for key in required_keys:
        assert key in fields, f"DSC missing key: {key}"
        assert fields[key], f"DSC key {key} is empty"

    assert len(str(fields["falsifier"])) > 40, "falsifier looks like a stub"
    assert len(str(fields["so_what"])) > 40, "so_what looks like a stub"


def test_trace_records_the_undischarged_rows():
    text = _read(TRACE)
    for token in ("MO-DELTA-008", "MO-DELTA-013", "MO-PAID-004", "read pass done, build child now scopable"):
        assert token in text, f"trace missing required token: {token}"
    assert "MO-DELTA-008 closed" not in text, "trace must not claim MO-DELTA-008 is closed"


def test_trace_names_the_in_flight_credit_window():
    text = _read(TRACE)
    assert "engine/credit_window.py" in text
    assert "#6904" in text
    # Do NOT assert credit_window.py's absence — that would fail the whole
    # suite the moment #6904 merges. If it now exists, the §5 reconciliation
    # text must still be present so the staleness is visible, not silent.
    if (ROOT / "engine/credit_window.py").exists():
        assert "§5" in text or "In-flight reconciliation" in text
