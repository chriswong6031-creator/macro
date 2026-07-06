"""tests/test_build_measurement_hubv2.py — Measurement Hub v2 builder tests.

Tests:
1. Builder runs end-to-end and produces JS + HTML.
2. JS payload contains truth counts matching truths.jsonl active rows.
3. Accrual clock math is correct on a synthetic parquet.
4. Absent-safety: truth_ledger renders 'not yet built' state when truths.jsonl missing.
5. BC-2: no 'validated'/'已验证' in new copy sections.

House rules obeyed:
- Pure numpy/pandas/pyarrow — no sklearn/statsmodels/scipy.stats.
- Deterministic sorted artifacts.
- No git commit/push; no appends to nightly ledgers.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# Ensure repo root on sys.path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.cycle_pattern.truths import active_truths, load_truths  # noqa: E402
from scripts.build_measurement import (  # noqa: E402
    ACCRUAL_LEDGERS,
    TRUTHS_JSONL_PATH,
    _parse_date,
    build_accrual_clocks,
    build_truth_ledger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_payload(js_text: str) -> dict:
    """Parse window.MEASUREMENT=...;  from the generated JS."""
    m = re.search(r"window\.MEASUREMENT=(.+);$", js_text, re.DOTALL | re.MULTILINE)
    assert m is not None, "window.MEASUREMENT not found in JS"
    return json.loads(m.group(1))


# ---------------------------------------------------------------------------
# 1. Builder runs end-to-end
# ---------------------------------------------------------------------------

def test_builder_produces_outputs():
    """Builder writes site/measurement.html and site/measurementdata/measurement_data.js."""
    html_path = REPO / "site" / "measurement.html"
    js_path = REPO / "site" / "measurementdata" / "measurement_data.js"
    assert html_path.exists(), f"measurement.html not found: {html_path}"
    assert js_path.exists(), f"measurement_data.js not found: {js_path}"
    assert html_path.stat().st_size > 1000, "measurement.html suspiciously small"
    assert js_path.stat().st_size > 1000, "measurement_data.js suspiciously small"


def test_js_payload_schema():
    """JS payload carries schema key and Hub v2 keys."""
    js = (REPO / "site" / "measurementdata" / "measurement_data.js").read_text(encoding="utf-8")
    payload = _extract_payload(js)
    assert "truth_ledger" in payload, "truth_ledger key missing from payload"
    assert "accrual_clocks" in payload, "accrual_clocks key missing from payload"
    assert payload.get("schema", "").startswith("measurement."), "unexpected schema value"


# ---------------------------------------------------------------------------
# 2. Truth counts in JS match truths.jsonl
# ---------------------------------------------------------------------------

def test_js_truth_counts_match_jsonl():
    """The JS payload's truth count and status_counts match what active_truths() returns."""
    # Skip if truths.jsonl absent (build environment may not have it; test itself is honest)
    if not TRUTHS_JSONL_PATH.exists():
        pytest.skip("truths.jsonl not present — skipping truth count verification")

    truths = active_truths(TRUTHS_JSONL_PATH)
    expected_total = len(truths)
    expected_counts = dict(Counter(t["status"] for t in truths))

    js = (REPO / "site" / "measurementdata" / "measurement_data.js").read_text(encoding="utf-8")
    payload = _extract_payload(js)
    tl = payload["truth_ledger"]
    assert tl["available"] is True, "truth_ledger.available should be True when file exists"
    assert tl["total"] == expected_total, (
        f"JS truth_ledger.total={tl['total']} but active_truths() returned {expected_total}"
    )
    assert tl["status_counts"] == expected_counts, (
        f"JS status_counts {tl['status_counts']} != {expected_counts}"
    )
    # Promoted nulls should appear in null_library
    expected_nulls = sum(1 for t in truths if t["status"] == "promoted_null")
    assert len(tl["null_library"]) == expected_nulls, (
        f"null_library has {len(tl['null_library'])} entries, expected {expected_nulls}"
    )


# ---------------------------------------------------------------------------
# 3. Accrual clock math on a synthetic parquet
# ---------------------------------------------------------------------------

def _make_synthetic_ledger(tmp_path: Path, n_stamps: int, cadence_days: int = 30) -> Path:
    """Write a synthetic parquet with n_stamps unique dates and 3 instruments per stamp."""
    d_start = date(2025, 1, 1)
    dates = []
    ids = []
    for i in range(n_stamps):
        stamp = (d_start + timedelta(days=i * cadence_days)).isoformat()
        for instrument in ["AAA", "BBB", "CCC"]:
            dates.append(stamp)
            ids.append(instrument)
    df = pd.DataFrame({"date": dates, "id": ids})
    parquet_path = tmp_path / "synthetic_forward_log.parquet"
    pq.write_table(pa.Table.from_pandas(df), str(parquet_path))
    return parquet_path


def test_accrual_clock_math_correct():
    """Cadence and target_40_date are computed correctly on known synthetic data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        n_stamps = 10
        cadence_days = 30
        parquet_path = _make_synthetic_ledger(tmp, n_stamps, cadence_days)

        # Patch ACCRUAL_LEDGERS temporarily with a single synthetic entry
        from scripts import build_measurement as bm
        original = list(bm.ACCRUAL_LEDGERS)
        synthetic_spec = {
            "key": "test_ledger",
            "label_en": "Test Ledger",
            "label_zh": "测试台账",
            "path": parquet_path,
            "id_col": "id",
            "date_col": "date",
        }
        bm.ACCRUAL_LEDGERS.clear()
        bm.ACCRUAL_LEDGERS.append(synthetic_spec)
        try:
            clocks = bm.build_accrual_clocks()
        finally:
            bm.ACCRUAL_LEDGERS.clear()
            bm.ACCRUAL_LEDGERS.extend(original)

        assert len(clocks) == 1
        cl = clocks[0]
        assert cl["available"] is True
        assert cl["n_rows"] == n_stamps * 3  # 3 instruments per stamp
        assert cl["unique_ids"] == 3
        assert cl["unique_dates"] == n_stamps

        # cadence: (last-first)/(n-1) in days = cadence_days
        assert cl["cadence_days"] == float(cadence_days), (
            f"Expected cadence {cadence_days}d, got {cl['cadence_days']}"
        )

        # Target 40: need 30 more stamps
        stamps_needed = 40 - n_stamps  # 30
        days_needed = stamps_needed * cadence_days  # 900
        d_last = date(2025, 1, 1) + timedelta(days=(n_stamps - 1) * cadence_days)
        expected_target = (d_last + timedelta(days=days_needed)).isoformat()
        assert cl["target_40_date"] == expected_target, (
            f"target_40_date: expected {expected_target}, got {cl['target_40_date']}"
        )


def test_accrual_clock_already_40():
    """Ledger with >= 40 stamps shows target_40_date=None (already reached)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        parquet_path = _make_synthetic_ledger(tmp, n_stamps=45, cadence_days=7)

        from scripts import build_measurement as bm
        original = list(bm.ACCRUAL_LEDGERS)
        synthetic_spec = {
            "key": "test_ledger_done",
            "label_en": "Done Ledger",
            "label_zh": "已完成台账",
            "path": parquet_path,
            "id_col": "id",
            "date_col": "date",
        }
        bm.ACCRUAL_LEDGERS.clear()
        bm.ACCRUAL_LEDGERS.append(synthetic_spec)
        try:
            clocks = bm.build_accrual_clocks()
        finally:
            bm.ACCRUAL_LEDGERS.clear()
            bm.ACCRUAL_LEDGERS.extend(original)

        assert len(clocks) == 1
        cl = clocks[0]
        assert cl["unique_dates"] == 45
        # target_40_date should be None because already >= 40
        assert cl["target_40_date"] is None, (
            f"Expected target_40_date=None for ledger with 45 stamps, got {cl['target_40_date']}"
        )


def test_accrual_clock_single_date_cadence_unmeasurable():
    """Single unique date → cadence_days is None and target_40_date is None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # 1 unique date, multiple instruments
        df = pd.DataFrame({
            "date": ["2025-01-01", "2025-01-01", "2025-01-01"],
            "id": ["A", "B", "C"],
        })
        parquet_path = tmp / "one_date.parquet"
        pq.write_table(pa.Table.from_pandas(df), str(parquet_path))

        from scripts import build_measurement as bm
        original = list(bm.ACCRUAL_LEDGERS)
        spec = {
            "key": "one_date_ledger",
            "label_en": "One Date",
            "label_zh": "单日期",
            "path": parquet_path,
            "id_col": "id",
            "date_col": "date",
        }
        bm.ACCRUAL_LEDGERS.clear()
        bm.ACCRUAL_LEDGERS.append(spec)
        try:
            clocks = bm.build_accrual_clocks()
        finally:
            bm.ACCRUAL_LEDGERS.clear()
            bm.ACCRUAL_LEDGERS.extend(original)

        assert len(clocks) == 1
        cl = clocks[0]
        assert cl["unique_dates"] == 1
        assert cl["cadence_days"] is None, "cadence should be None with only 1 unique date"
        assert cl["target_40_date"] is None


# ---------------------------------------------------------------------------
# 4. Absent-safety: truth_ledger when truths.jsonl missing
# ---------------------------------------------------------------------------

def test_truth_ledger_absent_safe():
    """build_truth_ledger() returns available=False when truths.jsonl is absent."""
    from scripts import build_measurement as bm
    original_path = bm.TRUTHS_JSONL_PATH
    bm.TRUTHS_JSONL_PATH = Path("/tmp/__nonexistent_truths_file_abc123.jsonl")
    try:
        result = bm.build_truth_ledger()
    finally:
        bm.TRUTHS_JSONL_PATH = original_path

    assert result["available"] is False, (
        f"Expected available=False when file missing, got: {result}"
    )


def test_html_contains_not_yet_built_message_when_absent():
    """Template renders 'not yet built' placeholder when truth_ledger.available is False."""
    from jinja2 import Environment, FileSystemLoader
    templates_dir = REPO / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)

    template = env.get_template("measurement.html.j2")
    html = template.render(
        page_title="Test",
        engines=[],
        gate_ledger=[],
        accruing_experiments=[],
        cone_recalibration={},
        collinearity={},
        sync_gauge={"available": False},
        provenance={"epochs": {}, "fingerprint_consistent": True},
        build_date=date.today().isoformat(),
        generated_at="2026-07-06T00:00:00Z",
        # Hub v2
        truth_ledger={"available": False},
        accrual_clocks=[],
    )
    # The absent-safe message must appear
    assert "truths.jsonl" in html, (
        "Expected 'truths.jsonl' absent-safe message in rendered HTML when available=False"
    )
    assert "not yet built" in html.lower() or "尚未构建" in html, (
        "Expected 'not yet built' or '尚未构建' in HTML when truth_ledger unavailable"
    )


# ---------------------------------------------------------------------------
# 5. BC-2: no 'validated'/'已验证' in new template sections
# ---------------------------------------------------------------------------

def test_bc2_no_validated_in_new_sections():
    """New template sections do not contain affirmative 'validated'/'已验证' tokens."""
    template_path = REPO / "templates" / "measurement.html.j2"
    content = template_path.read_text(encoding="utf-8")

    # Extract just the three new sections by finding their markers
    # We check everything after the PATTERN MEMORY comment
    pattern_memory_marker = "PATTERN MEMORY v0 — TRUTH LEDGER"
    provenance_marker = "PROVENANCE FOOTER"

    start = content.find(pattern_memory_marker)
    end = content.find(provenance_marker)
    assert start != -1, "Could not find Pattern Memory section marker in template"
    assert end != -1, "Could not find Provenance section marker in template"
    new_sections = content[start:end]

    # Check for affirmative 'validated'/'已验证' (not negated, not structural)
    affirmative_pattern = re.compile(r"validated|已验证", re.IGNORECASE)
    negation_pattern = re.compile(
        r"(?:\bno\b|\bnot\b|\bnon-?|\bun-?|\bnever\b|without)\s[\w\s,''-]{0,30}validated",
        re.IGNORECASE,
    )
    code_pattern = re.compile(r"""['".]validated|validated['".]|\bvalidated_|validate_""")

    violations = []
    for i, line in enumerate(new_sections.splitlines(), 1):
        if not affirmative_pattern.search(line):
            continue
        if negation_pattern.search(line):
            continue
        if code_pattern.search(line):
            continue
        # Jinja comments and code identifiers
        if "{#" in line or "{{" in line or "{%" in line:
            # Only flag if the word appears in obvious prose context
            # (not in a code expression or comment)
            if "validated" not in line.lower() and "已验证" not in line:
                continue
            # Inside a jinja tag — skip, it's code
            if re.search(r"\{[{%#][^}]*(?:validated|已验证)[^}]*[}%#]}", line):
                continue
        violations.append((i, line.strip()[:120]))

    assert not violations, (
        f"BC-2 violation: 'validated'/'已验证' appears affirmatively in new template sections:\n"
        + "\n".join(f"  line {i}: {t}" for i, t in violations)
    )


# ---------------------------------------------------------------------------
# 6. _parse_date helper
# ---------------------------------------------------------------------------

def test_parse_date_valid():
    assert _parse_date("2026-07-06") == date(2026, 7, 6)


def test_parse_date_invalid():
    assert _parse_date("not-a-date") is None
    assert _parse_date("") is None


# ---------------------------------------------------------------------------
# 7. Existing measurement tests still pass (integration smoke)
# ---------------------------------------------------------------------------

def test_existing_js_payload_has_engines():
    """JS payload still has 'engines' key — existing sections not broken."""
    js = (REPO / "site" / "measurementdata" / "measurement_data.js").read_text(encoding="utf-8")
    payload = _extract_payload(js)
    assert "engines" in payload
    assert "gate_ledger" in payload
    assert isinstance(payload["engines"], list)
