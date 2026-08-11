"""`early_signal_dates` — the ADDITIVE knowability stamp for the dots (§6.7 family).

The dots in `site/signals/<T>.json` are stamped with their 3D bucket's OPEN label, which is
the chart's x-anchor but NOT the close at which the dot became knowable (the bake-off
measured 3,756 of 3,760 published dots carrying the open label). The repair is additive by
construction: `early_markers` keeps its exact meaning, position and content, and a parallel
`early_signal_dates` carries the same dots' last-session dates.

These tests exist because the additive path only stays additive if something enforces it —
every consumer census'd for this change is represented here:

  * the producer                    engine/signal_quality.analyze
  * the published contract          research/signal_engine/SCHEMA.json (additionalProperties: false)
  * the nightly validator           scripts/validate_signals.py
  * the exported field inventory    scripts/export_signal_contracts.py
  * the scored gate                 engine/signal_gate.verdict  (must not notice)

The Terminal is deliberately absent: charting-app computes its own `early_dots` from prices
(`signal_layer/confluence_v2.early_dots`) and does not read this list, so it cannot be
broken by a field added here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import signal_gate
from engine.signal_quality import analyze
from scripts import validate_signals as vs

SCHEMA = vs.load_schema()
FIXTURES = Path(__file__).parent / "fixtures" / "us_early_turn"


def _doc(ticker: str = "STLD") -> dict:
    df = pd.read_csv(FIXTURES / f"{ticker}.csv", index_col="date", parse_dates=True)
    return analyze(ticker, df["close"], df["high"], df["low"])


def _valid_ticker() -> dict:
    return {
        "ticker": "AAPL", "asof": "2026-06-18", "tf": "3D",
        "state": "long-bias", "above200": True, "weekly_bull": False,
        "early_markers": ["2025-07-09", "2026-03-05"],
        "early_signal_dates": ["2025-07-11", "2026-03-09"],
        "early_now": False,
        "markers": [{"date": "2025-07-16", "type": "buy", "quality": "take",
                     "reason": "held confirmation"}],
    }


# ---- the additive contract -------------------------------------------------
def test_legacy_document_without_the_field_still_validates():
    """A document written before this field existed must stay valid forever."""
    doc = _valid_ticker()
    doc.pop("early_signal_dates")
    assert vs.validate_ticker_doc(doc, SCHEMA, "legacy") == []


def test_document_with_the_field_validates():
    assert vs.validate_ticker_doc(_valid_ticker(), SCHEMA, "new") == []


def test_schema_admits_the_key_despite_additional_properties_false():
    """`perTicker` closes with additionalProperties: false, so a new key is only additive if
    the published schema learned it in the same change."""
    per = SCHEMA["$defs"]["perTicker"]
    assert per.get("additionalProperties") is False
    assert "early_signal_dates" in per["properties"]
    assert "early_signal_dates" not in per.get("required", [])


def test_pairing_is_enforced_not_assumed():
    """The two lists are positionally paired. A length drift would silently re-index every
    pair, so it must be an error rather than a shrug."""
    doc = _valid_ticker()
    doc["early_signal_dates"] = ["2025-07-11"]
    errs = vs.validate_ticker_doc(doc, SCHEMA, "mismatch")
    assert any("positionally paired" in e for e in errs), errs


def test_stamp_list_must_still_be_ascending_dates():
    doc = _valid_ticker()
    doc["early_signal_dates"] = ["2026-03-09", "2025-07-11"]
    errs = vs.validate_ticker_doc(doc, SCHEMA, "unsorted")
    assert any("early_signal_dates" in e for e in errs), errs


def test_exported_contract_inventory_lists_the_field():
    """`export_signal_contracts` publishes the per-stock field inventory cross-repo; a field
    the producer emits but the inventory omits is a contract that drifted on the day it
    shipped."""
    src = Path("scripts/export_signal_contracts.py").read_text()
    assert '"early_signal_dates"' in src


# ---- the producer ----------------------------------------------------------
def test_producer_emits_a_paired_stamp_that_is_at_or_after_the_open_label():
    """Knowability is at or after the chart anchor, never before it: a bucket's last session
    is by definition >= its open label."""
    doc = _doc()
    dots, stamps = doc["early_markers"], doc.get("early_signal_dates")
    assert stamps is not None, "the producer should stamp when every bucket resolves"
    assert len(stamps) == len(dots)
    for label, known in zip(dots, stamps):
        assert known >= label


def test_producer_reproduces_the_measured_stld_stamp():
    """The bake-off measured STLD's published 2026-07-10 dot as knowable at 2026-07-14.
    That exact pair is the receipt this field exists to publish."""
    doc = _doc("STLD")
    pairs = dict(zip(doc["early_markers"], doc["early_signal_dates"]))
    assert pairs.get("2026-07-10") == "2026-07-14"


def test_legacy_list_is_untouched_by_the_addition():
    """`early_markers` is the field every existing consumer reads. Its content must be
    exactly what it was before the stamp existed — the addition may not re-date a dot."""
    doc = _doc()
    assert all(isinstance(d, str) and len(d) == 10 for d in doc["early_markers"])
    assert doc["early_markers"] == sorted(doc["early_markers"])
    # the stamp is a SEPARATE list, never a mutation of the legacy one
    assert doc["early_markers"] != doc["early_signal_dates"]


def test_producer_output_validates_against_the_published_schema():
    assert vs.validate_ticker_doc(_doc(), SCHEMA, "produced") == []


# ---- the scored gate is blind to it ----------------------------------------
def test_gate_verdict_ignores_the_new_field():
    doc = _doc()
    legacy = {k: v for k, v in doc.items() if k != "early_signal_dates"}
    assert signal_gate.verdict(doc) == signal_gate.verdict(legacy)


def test_gate_verdict_is_unmoved_by_a_wrong_stamp():
    """Belt and braces: even a nonsense stamp may not move a scored verdict, because the
    gate must never read this list at all."""
    doc = _doc()
    poisoned = dict(doc)
    poisoned["early_signal_dates"] = ["1970-01-01"] * len(doc["early_markers"])
    assert signal_gate.verdict(poisoned) == signal_gate.verdict(doc)
