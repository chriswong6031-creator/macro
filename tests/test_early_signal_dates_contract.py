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

import inspect
import json
from pathlib import Path

import pandas as pd
import pytest

from engine import signal_gate
from engine.session_anchor import session_positions
from engine.signal_quality import analyze
from scripts import validate_signals as vs

SCHEMA = vs.load_schema()
FIXTURES = Path(__file__).parent / "fixtures" / "us_early_turn"
#: Both committed fixtures, so the producer pins are not a one-name anecdote.
PRODUCER_FIXTURES = ("STLD", "NEM")


def _frame(ticker: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / f"{ticker}.csv", index_col="date", parse_dates=True)


def _doc(ticker: str = "STLD") -> dict:
    df = _frame(ticker)
    return analyze(ticker, df["close"], df["high"], df["low"])


def _bucket_sessions(index, label: str) -> pd.DatetimeIndex:
    """The sessions of ``label``'s OWN 3D bucket that this series carries.

    Computed from the absolute session calendar, not from the producer's output, so the
    pins below check the stamp against an independent reading of the same grid.
    """
    di = pd.DatetimeIndex(index)
    buckets = session_positions(di, "US") // 3
    target = int(session_positions(pd.DatetimeIndex([pd.Timestamp(label)]), "US")[0]) // 3
    return di[buckets == target]


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


def test_stamp_before_its_own_label_is_an_error_not_a_shrug():
    """The KNOWABILITY RELATION, pair by pair. A stamp that PRECEDES its own open label is
    not a late stamp — a bucket's last session cannot come before the bucket opens — so it
    means the two lists have drifted out of positional register and every downstream
    (dot, date) join is silently wrong. A length check cannot see this."""
    doc = _valid_ticker()
    doc["early_signal_dates"] = ["2025-07-11", "2026-03-04"]   # [1] precedes its label
    errs = vs.validate_ticker_doc(doc, SCHEMA, "before-label")
    assert any("BEFORE its own" in e and "[1]" in e for e in errs), errs
    # ...and the legal pairing raises nothing
    assert vs.validate_ticker_doc(_valid_ticker(), SCHEMA, "paired") == []


def test_a_stamp_equal_to_its_label_is_legal():
    """A one-session bucket (a holiday-shortened 3D bucket) is knowable on its own open
    label. The relation is `>=`, so equality must not be reported as drift."""
    doc = _valid_ticker()
    doc["early_signal_dates"] = list(doc["early_markers"])
    assert vs.validate_ticker_doc(doc, SCHEMA, "equal") == []


def test_the_knowability_check_is_reachable_from_the_document_validator():
    """Belt-and-braces on the wiring: the helper must be CALLED by validate_ticker_doc, not
    merely exist. A guard nobody runs is a guard that is green for the wrong reason."""
    assert vs.check_knowability_pairing(["2026-03-05"], ["2026-03-04"], "w")
    assert vs.check_knowability_pairing(["2026-03-05"], ["2026-03-05"], "w") == []
    src = inspect.getsource(vs.validate_ticker_doc)
    assert "check_knowability_pairing" in src


# ---- the exported contract inventory ---------------------------------------
def _signal_manifest_entry(manifest_artifacts) -> dict:
    entries = [a for a in manifest_artifacts if a.get("kind") == "per_stock_signal"]
    assert len(entries) == 1, entries
    return entries[0]


def test_the_field_is_registered_as_OPTIONAL_not_as_always_present():
    """`export_signal_contracts` publishes the per-stock field inventory cross-repo, and its
    own law is explicit: schema_fields are ALWAYS-PRESENT keys, optional_fields are the
    conditional ones. The producer emits this key ALL-OR-NOTHING (`stamped = all(...)` in
    signal_quality.analyze), so registering it as required would have flipped the drift lane
    red on the next manifest regeneration and then flapped it with the data forever after."""
    from scripts.export_signal_contracts import ARTIFACT_MANIFEST
    entry = _signal_manifest_entry(ARTIFACT_MANIFEST)
    assert "early_signal_dates" in entry.get("optional_fields", [])
    assert "early_signal_dates" not in entry["schema_fields"]
    assert entry["schema_version"] == "1.3.0", (
        "adding a conditional field is additive — the exporter's own convention is a MINOR "
        "bump, and the version must move or consumers cannot tell the contract changed")


def test_the_committed_manifest_agrees_with_the_producer():
    """The committed artifact is what consumers and `check_contract_drift.py` actually read.
    A source-only registration that was never regenerated is a contract that exists in the
    repo and nowhere else — which is exactly how this shipped green on a stale manifest."""
    from scripts.export_signal_contracts import OUT
    manifest = json.loads((OUT / "artifact_manifest.json").read_text())
    entry = _signal_manifest_entry(manifest["artifacts"])
    assert entry["schema_version"] == "1.3.0"
    assert entry.get("optional_fields") == ["early_signal_dates"]
    assert "early_signal_dates" not in entry["schema_fields"]


def test_conditional_emission_keeps_the_registration_optional():
    """The counterfactual this registration exists to avoid, measured on the committed
    store rather than argued. Originally that measurement was "no file carries the key"
    (pre-rebuild); the 2026-08-12 01:46Z engine-render rebuilt the store with the merged
    union-admission producer and 240/241 files now carry it — while SATS, whose right
    edge is stale, lawfully does NOT: the producer stamps all-or-nothing per name
    (`stamped = all(...)` in signal_quality.analyze), so any name with an unknowable dot
    ships without the key. While even one live file can lawfully lack the key, a
    REQUIRED registration is `removed` drift on that file — optional is the structural
    home of a conditionally-emitted field, not a convergence state to graduate out of,
    unless the emission law itself changes."""
    live = sorted(Path("site/signals").glob("*.json"))
    if not live:  # pragma: no cover - the store is committed
        pytest.skip("no committed site/signals sample in this checkout")
    non_carriers = [p.name for p in live
                    if "early_signal_dates" not in json.loads(p.read_text())]
    from scripts.export_signal_contracts import ARTIFACT_MANIFEST
    entry = _signal_manifest_entry(ARTIFACT_MANIFEST)
    if non_carriers:
        assert "early_signal_dates" in entry.get("optional_fields", []), (
            f"{len(non_carriers)} live signal file(s) lack early_signal_dates "
            f"(e.g. {non_carriers[:3]}) yet the field is not registered optional — "
            f"conditional emission makes a REQUIRED registration `removed` drift on "
            f"each of them")
        assert "early_signal_dates" not in entry["schema_fields"], (
            f"early_signal_dates is in schema_fields while {len(non_carriers)} live "
            f"file(s) lawfully lack it (e.g. {non_carriers[:3]})")


# ---- the producer ----------------------------------------------------------
@pytest.mark.parametrize("ticker", PRODUCER_FIXTURES)
def test_producer_stamps_each_dot_at_its_own_buckets_LAST_session(ticker):
    """The stamp is not merely "at or after" the chart anchor — it IS the bucket's last
    session, and the inequality is STRICT on any bucket carrying more than one session.

    `known >= label` was the weak form: it also passes for a producer that copied the label
    straight across, which is the exact defect this field exists to repair (3,756 of 3,760
    published dots carried the open label). The bucket membership below is recomputed from
    the absolute session calendar, independently of the producer.
    """
    df = _frame(ticker)
    doc = analyze(ticker, df["close"], df["high"], df["low"])
    dots, stamps = doc["early_markers"], doc.get("early_signal_dates")
    assert stamps is not None, "the producer should stamp when every bucket resolves"
    assert len(stamps) == len(dots) and dots, f"{ticker} carries no dots to pin"
    for label, known in zip(dots, stamps):
        sessions = _bucket_sessions(df.index, label)
        assert len(sessions) >= 1
        assert known == str(sessions[-1].date()), (
            f"{ticker} {label}: stamp {known} is not its bucket's last session")
        if len(sessions) > 1:
            assert known > label, (
                f"{ticker} {label}: a {len(sessions)}-session bucket cannot be knowable "
                f"on its own open label")


def test_producer_reproduces_the_measured_stld_stamp():
    """The bake-off measured STLD's published 2026-07-10 dot as knowable at 2026-07-14.
    That exact pair is the receipt this field exists to publish."""
    doc = _doc("STLD")
    pairs = dict(zip(doc["early_markers"], doc["early_signal_dates"]))
    assert pairs.get("2026-07-10") == "2026-07-14"


def test_the_second_fixture_carries_MORE_THAN_ONE_dot_and_every_stamp_moves():
    """A one-dot receipt cannot distinguish "the stamp works" from "the stamp happens to
    be right once". NEM carries three dots and every one of them is re-dated forward by two
    sessions — the same +2 the STLD receipt shows, on an independent name."""
    df = _frame("NEM")
    doc = analyze("NEM", df["close"], df["high"], df["low"])
    pairs = dict(zip(doc["early_markers"], doc["early_signal_dates"]))
    assert len(pairs) >= 2, f"NEM should carry >=2 dots for this pin, got {pairs}"
    assert pairs == {"2025-02-05": "2025-02-07",
                     "2025-11-05": "2025-11-07",
                     "2025-12-02": "2025-12-04"}
    assert all(k > label for label, k in pairs.items()), (
        "every one of these buckets carries three sessions, so no stamp may equal its label")


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
