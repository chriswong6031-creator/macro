"""FL-E — statement tape tests (FC-R9 / PS-R1).

Covers:
  1. Registry schema guard: every real row in registry.jsonl passes validate_row().
  2. Schema rejects missing required fields.
  3. Schema rejects invalid stance_tag.
  4. Schema rejects bad date format.
  5. Schema rejects PS-R1-banned keys (signal/forecast/prediction/probability).
  6. Schema accepts null ts_utc (no timestamp known).
  7. Schema accepts paraphrase=true rows.
  8. Collector feasibility: no automated collector shipped (Truth Social is an
     HTML SPA with no machine-readable feed); the collector module is absent by
     design — test confirms it does not exist under collectors/statement_tape.py.
  9. Fixture fixture page (no network): check_statement_tape parse is idempotent on
     a temp registry with synthetic rows.

Run:
    python -m pytest tests/test_statement_tape.py -q
    python -m tests.test_statement_tape
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_statement_tape import validate_row, load_rows, VALID_STANCES, REGISTRY

# ---------------------------------------------------------------------------
# Minimal valid row — a factory so each test gets a clean copy
# ---------------------------------------------------------------------------
def _valid_row(**overrides) -> dict:
    base = {
        "date": "2025-04-09",
        "ts_utc": "2025-04-09T13:37:00Z",
        "speaker": "Donald Trump",
        "venue": "Truth Social",
        "quote": "THIS IS A GREAT TIME TO BUY!!! DJT",
        "paraphrase": False,
        "stance_tag": "market_boost",
        "source_url": "https://example.com/post",
        "added_by": "session/test",
        "added_at": "2026-07-11T00:00:00Z",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Live registry: all rows pass schema validation
# ---------------------------------------------------------------------------
def test_live_registry_valid():
    """Every real row in data/statement_tape/registry.jsonl must be schema-valid."""
    if not REGISTRY.exists():
        pytest.skip("registry not found (not in this checkout)")
    rows = load_rows(REGISTRY)
    assert rows, "registry has no data rows — expected at least 7 seeded entries"
    all_errors = []
    for lineno, row in rows:
        errors = validate_row(row, lineno)
        all_errors.extend(errors)
    assert not all_errors, (
        f"{len(all_errors)} schema error(s) in live registry:\n"
        + "\n".join(all_errors)
    )


def test_live_registry_minimum_rows():
    """Seeded registry must contain at least 7 rows (the 7 verified episodes)."""
    if not REGISTRY.exists():
        pytest.skip("registry not found")
    rows = load_rows(REGISTRY)
    assert len(rows) >= 7, f"expected ≥7 seeded rows, got {len(rows)}"


def test_live_registry_stance_tags_valid():
    """All stance_tags in the live registry are drawn from the defined enum."""
    if not REGISTRY.exists():
        pytest.skip("registry not found")
    rows = load_rows(REGISTRY)
    for _, row in rows:
        tag = row.get("stance_tag", "")
        assert tag in VALID_STANCES, f"unexpected stance_tag {tag!r}"


# ---------------------------------------------------------------------------
# 2. Required-field rejection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["date", "speaker", "venue", "quote", "stance_tag", "added_by", "added_at"])
def test_missing_required_field(field):
    row = _valid_row()
    del row[field]
    errors = validate_row(row, 1)
    assert any(field in e for e in errors), f"expected error for missing '{field}'"


# ---------------------------------------------------------------------------
# 3. Invalid stance_tag
# ---------------------------------------------------------------------------
def test_invalid_stance_tag():
    row = _valid_row(stance_tag="bullish")  # not in VALID_STANCES
    errors = validate_row(row, 1)
    assert any("stance_tag" in e for e in errors)


def test_all_valid_stances_accepted():
    for tag in VALID_STANCES:
        row = _valid_row(stance_tag=tag)
        errors = validate_row(row, 1)
        assert not errors, f"valid stance_tag {tag!r} was rejected: {errors}"


# ---------------------------------------------------------------------------
# 4. Date format validation
# ---------------------------------------------------------------------------
def test_bad_date_format():
    row = _valid_row(date="04/09/2025")  # US format, not ISO
    errors = validate_row(row, 1)
    assert any("date" in e for e in errors)


def test_valid_date_accepted():
    row = _valid_row(date="2025-04-09")
    errors = validate_row(row, 1)
    assert not errors


# ---------------------------------------------------------------------------
# 5. PS-R1 banned key enforcement
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("banned_key", ["signal", "forecast", "prediction", "probability", "edge"])
def test_ps_r1_banned_key(banned_key):
    """A row with a field containing a PS-R1-banned key substring must be rejected."""
    row = _valid_row(**{banned_key + "_score": 0.7})
    errors = validate_row(row, 1)
    assert any(banned_key in e for e in errors), (
        f"expected PS-R1 violation for key containing {banned_key!r}"
    )


# ---------------------------------------------------------------------------
# 6. Null ts_utc is valid
# ---------------------------------------------------------------------------
def test_null_ts_utc_valid():
    row = _valid_row(ts_utc=None)
    errors = validate_row(row, 1)
    assert not errors, f"null ts_utc should be valid; got {errors}"


# ---------------------------------------------------------------------------
# 7. Paraphrase=True is valid
# ---------------------------------------------------------------------------
def test_paraphrase_true_valid():
    row = _valid_row(paraphrase=True, quote="He said markets should go higher (paraphrase)")
    errors = validate_row(row, 1)
    assert not errors


# ---------------------------------------------------------------------------
# 8. No automated collector (Truth Social is an HTML SPA — no machine-readable feed)
# ---------------------------------------------------------------------------
def test_no_automated_collector():
    """Confirm collectors/statement_tape.py does not exist (feasibility = NOT VIABLE).

    Truth Social returns an HTML SPA with no machine-readable feed endpoint.
    FactBase moved to Roll Call (404 on both). No reliable free source exists.
    The registry is operator/session-appended only.
    """
    root = Path(__file__).resolve().parent.parent
    collector_path = root / "collectors" / "statement_tape.py"
    assert not collector_path.exists(), (
        f"collectors/statement_tape.py exists but Truth Social has no machine-readable feed. "
        f"If a source becomes available, remove this test and wire the collector."
    )


# ---------------------------------------------------------------------------
# 9. Fixture registry round-trip (no network, temp file)
# ---------------------------------------------------------------------------
def test_fixture_registry_round_trip():
    """A temp registry with synthetic rows loads and validates without errors."""
    rows_in = [
        _valid_row(date="2018-12-26", ts_utc=None, venue="Twitter",
                   quote="Market tweet", stance_tag="fed_pressure"),
        _valid_row(date="2020-03-13", ts_utc="2020-03-13T17:00:00Z",
                   paraphrase=True, quote="paraphrase example", stance_tag="market_boost"),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        # write a header comment row
        fh.write(json.dumps({"_comment": "test"}) + "\n")
        for row in rows_in:
            fh.write(json.dumps(row) + "\n")
        tmp = Path(fh.name)

    try:
        loaded = load_rows(tmp)
        assert len(loaded) == 2, f"expected 2 data rows, got {len(loaded)}"
        for lineno, row in loaded:
            errors = validate_row(row, lineno)
            assert not errors, f"synthetic row failed validation: {errors}"
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
