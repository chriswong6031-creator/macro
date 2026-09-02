"""The shared public regular-session quote projector.

This module is the single owner of the honesty law that used to live only in
``app/dossier_quote.py``: freshness describes the FEED, session describes the
MARKET, ``chg`` is always a percent, and the absolute move is always DERIVED
rather than trusted verbatim. Both the dossier and the Intelligence Hub batch
route (``app/intelligence_hub_market_pulse.py``) wrap this one function, so a
regression here is a regression in both public quote surfaces at once.
"""
from __future__ import annotations

import math

import pytest

from app.public_quote_projection import (
    PublicQuote,
    QuoteProjectionError,
    finite_number,
    freshness_of,
    is_realtime_basis,
    project_regular_quote,
    session_of,
)

NOW = 1787871758.0 + 5
CLOSED_NOW = 1787871758.0 + 5 * 3600
PUBLISHED = "2026-08-31T14:31:10.214Z"

# A verbatim-shaped RTH row (mirrors tests/test_dossier_quote_api.py's
# HUB_NVDA_DELAYED capture): the exact production row that shipped the
# original dossier defect, reused here so the shared owner is pinned against
# the same real-world shape.
HUB_NVDA_RTH = {
    "sym": "NVDA", "last": 227.98, "ts": 1787871758, "live": False,
    "source": "polygon-snapshot", "market": "us", "basis": "DELAYED_15M",
    "regularSession": "rth", "close": 227.98, "prevClose": 209.66,
    "chg": 8.7379566917867, "anchor_source": "snapshot", "marketSession": "post",
    "regularSessionDate": "2026-08-27",
    "extPrice": 226.25, "extChg": -0.7588384946047855, "extTs": 1787872020,
    "extSession": "post", "extSource": "polygon-delayed", "extBasis": "DELAYED_15M",
}

HUB_NVDA_CLOSED = dict(HUB_NVDA_RTH, regularSession="closed", marketSession="overnight", close=None)

# The load-bearing discrimination case: regular session UP, extended session
# DOWN. If this module ever read an ext* field, the sign would flip.
HUB_OPPOSITE_SIGNS = dict(HUB_NVDA_RTH)


def _row(**overrides):
    row = dict(HUB_NVDA_RTH)
    row.update(overrides)
    return row


# ── the three plan-named fixtures, verbatim ─────────────────────────────────

def test_chg_is_percent_and_absolute_move_is_derived():
    q = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.change_abs == pytest.approx(HUB_NVDA_RTH["last"] - HUB_NVDA_RTH["prevClose"])
    assert q.change_pct == pytest.approx(HUB_NVDA_RTH["chg"])


def test_closed_regular_print_is_settled_not_immediately_stale():
    q = project_regular_quote(HUB_NVDA_CLOSED, ticker="NVDA", now=CLOSED_NOW, published_at=PUBLISHED)
    assert q.session == "closed"
    assert q.freshness != "stale"


def test_extended_fields_cannot_replace_regular_tuple():
    q = project_regular_quote(HUB_OPPOSITE_SIGNS, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.change_pct > 0
    assert HUB_OPPOSITE_SIGNS["extChg"] < 0


# ── freshness: every uncertain input resolves downward ─────────────────────

def test_delayed_basis_can_never_report_live():
    q = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.freshness == "delayed"


def test_realtime_flag_alone_cannot_produce_live_while_basis_is_delayed():
    q = project_regular_quote(_row(live=True), ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.freshness == "delayed"


def test_a_measured_fresh_realtime_regular_row_is_the_only_live_case():
    q = project_regular_quote(
        _row(live=True, basis="REALTIME", marketSession="regular"),
        ticker="NVDA", now=NOW, published_at=PUBLISHED,
    )
    assert q.freshness == "live"
    assert q.session == "regular"


def test_an_unrecognised_basis_is_not_proven_realtime():
    for basis in ("15M", "IEX_ONLY", "SOMETHING_NEW", ""):
        q = project_regular_quote(
            _row(live=True, basis=basis, marketSession="regular"),
            ticker="NVDA", now=NOW, published_at=PUBLISHED,
        )
        assert q.freshness == "delayed", basis


def test_missing_timestamp_fails_closed_rather_than_assuming_fresh():
    row = _row(live=True, basis="REALTIME", marketSession="regular")
    row.pop("ts")
    q = project_regular_quote(row, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.freshness == "stale"
    assert q.observed_at is None  # never fabricate an observation time


def test_a_far_future_clock_is_a_fault_not_a_fresh_quote():
    q = project_regular_quote(
        _row(live=True, basis="REALTIME", marketSession="regular"),
        ticker="NVDA", now=1787871758.0 - 86_400, published_at=PUBLISHED,
    )
    assert q.freshness == "stale"


def test_realtime_row_older_than_the_bound_is_not_live():
    q = project_regular_quote(
        _row(live=True, basis="REALTIME", marketSession="regular"),
        ticker="NVDA", now=1787871758.0 + 4000, published_at=PUBLISHED,
        live_max_age_seconds=120.0, stale_max_age_seconds=900.0,
    )
    assert q.freshness == "stale"


def test_a_dead_hub_still_fails_closed_outside_regular_hours():
    q = project_regular_quote(
        HUB_NVDA_RTH, ticker="NVDA", now=1787871758.0 + 9 * 24 * 3600, published_at=PUBLISHED,
    )
    assert q.freshness == "stale"


# ── request/projection time never refreshes source freshness ───────────────

def test_freshness_uses_now_never_published_at():
    """`now` (real clock) and `published_at` (a caller-chosen label) must be
    independent — a slow response minting a fresh `published_at` string must
    not manufacture live freshness for a genuinely stale source print."""
    q = project_regular_quote(
        _row(live=True, basis="REALTIME", marketSession="regular"),
        ticker="NVDA", now=1787871758.0 + 4000,
        published_at="2099-01-01T00:00:00Z",  # deliberately "fresh-looking"
        live_max_age_seconds=120.0, stale_max_age_seconds=900.0,
    )
    assert q.freshness == "stale"
    assert q.published_at == "2099-01-01T00:00:00Z"  # published_at still just echoes through


# ── regular-session semantics ───────────────────────────────────────────────

def test_change_pct_is_read_from_chg_never_from_extChg():
    """Discriminates the specific field read, not merely "is it derived".

    `chg` sits just inside the consistency epsilon of the derived percent (so
    it is kept as-is, not replaced); `extChg` sits far outside it (so reading
    it instead would trigger the self-heal fallback and silently converge
    back to the derived value). Reading the wrong field is therefore only
    observable at tight precision — this pins that precision.
    """
    last, prev_close = 120.0, 100.0
    derived_pct = (last - prev_close) / prev_close * 100.0  # 20.0
    row = _row(last=last, prevClose=prev_close, chg=derived_pct + 0.01, extChg=derived_pct + 10.0)
    q = project_regular_quote(row, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.change_pct == pytest.approx(derived_pct + 0.01, abs=1e-9)


def test_change_abs_is_derived_not_read_from_the_percent_field():
    q = project_regular_quote(
        _row(last=120.0, prevClose=100.0, chg=20.0), ticker="NVDA", now=NOW, published_at=PUBLISHED,
    )
    assert q.change_abs == pytest.approx(20.0)
    assert q.change_pct == pytest.approx(20.0)
    q2 = project_regular_quote(
        _row(last=60.0, prevClose=50.0, chg=20.0), ticker="NVDA", now=NOW, published_at=PUBLISHED,
    )
    assert q2.change_abs == pytest.approx(10.0)
    assert q2.change_pct == pytest.approx(20.0)


def test_a_percent_that_contradicts_the_price_pair_is_replaced():
    q = project_regular_quote(
        _row(chg=-0.7588384946047855), ticker="NVDA", now=NOW, published_at=PUBLISHED,
    )
    assert q.change_abs == pytest.approx(18.32, abs=1e-6)
    assert q.change_pct == pytest.approx(8.7379566917867, abs=1e-6)


def test_a_rolled_forward_anchor_never_flattens_the_move_to_zero():
    premarket = dict(
        sym="NVDA", last=227.98, ts=1787917374, live=False, basis="DELAYED_15M",
        regularSession="closed", prevClose=227.98, chg=8.7379566917867,
        prevSessionChg=8.7379566917867, marketSession="pre",
    )
    q = project_regular_quote(premarket, ticker="NVDA", now=1787917374 + 30, published_at=PUBLISHED)
    assert q.price == pytest.approx(227.98)
    assert q.change_pct == pytest.approx(8.7379566917867, abs=1e-9)
    assert q.change_abs != pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("bad", [-100.0, -100.0000001, -250.0, float("nan"), float("inf"), None, "8.74", 0.0])
def test_an_unusable_previous_session_percent_falls_back_instead_of_dividing_by_zero(bad):
    row = dict(
        sym="NVDA", last=227.98, ts=1787917374, live=False, basis="DELAYED_15M",
        regularSession="closed", prevClose=227.98, chg=8.7379566917867,
        prevSessionChg=bad, marketSession="pre",
    )
    q = project_regular_quote(row, ticker="NVDA", now=1787917374 + 30, published_at=PUBLISHED)
    assert math.isfinite(q.change_abs)
    assert math.isfinite(q.change_pct)


@pytest.mark.parametrize("tag", ["pre", "post", "after-hours", "extended"])
def test_an_explicitly_extended_print_is_refused(tag):
    with pytest.raises(QuoteProjectionError):
        project_regular_quote(_row(regularSession=tag), ticker="NVDA", now=NOW, published_at=PUBLISHED)


def test_a_row_with_no_usable_price_is_refused():
    with pytest.raises(QuoteProjectionError):
        project_regular_quote(
            {"sym": "NVDA", "last": "not-a-number"}, ticker="NVDA", now=NOW, published_at=PUBLISHED,
        )


def test_a_negative_or_zero_price_is_refused():
    with pytest.raises(QuoteProjectionError):
        project_regular_quote(_row(last=0.0), ticker="NVDA", now=NOW, published_at=PUBLISHED)
    with pytest.raises(QuoteProjectionError):
        project_regular_quote(_row(last=-5.0), ticker="NVDA", now=NOW, published_at=PUBLISHED)


# ── debrand / allowlist ──────────────────────────────────────────────────────

def test_projection_never_carries_ext_or_transport_fields():
    q = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    dumped = vars(q)
    for dropped in ("source", "anchor_source", "basis", "extPrice", "extChg", "extTs", "extBasis", "extSource"):
        assert dropped not in dumped
    assert q.currency == "USD"


def test_received_at_is_never_fabricated():
    """No trustworthy upstream receive clock exists today; received_at must
    stay None rather than being synthesised from `now` or `published_at`."""
    q = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q.received_at is None


# ── revision fingerprint / identity ─────────────────────────────────────────

def test_revision_is_deterministic_and_equal_for_identical_prints():
    q1 = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    q2 = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at="a-different-envelope-time")
    assert q1.revision == q2.revision  # published_at is not part of the identity


def test_revision_changes_when_the_underlying_print_changes():
    q1 = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    q2 = project_regular_quote(_row(last=228.5), ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert q1.revision != q2.revision


def test_symbol_is_normalized_uppercase():
    q = project_regular_quote(HUB_NVDA_RTH, ticker="nvda", now=NOW, published_at=PUBLISHED)
    assert q.symbol == "NVDA"


# ── small pure helpers stay directly testable/importable ───────────────────

def test_finite_number_rejects_booleans():
    assert finite_number(True) is None
    assert finite_number(False) is None
    assert finite_number(1.5) == 1.5
    assert finite_number(float("nan")) is None
    assert finite_number(float("inf")) is None


def test_is_realtime_basis_is_an_allowlist():
    assert is_realtime_basis("REALTIME") is True
    assert is_realtime_basis("LIVE") is True
    assert is_realtime_basis("15M") is False
    assert is_realtime_basis(None) is False


def test_session_of_maps_known_tokens():
    assert session_of({"marketSession": "regular"}) == "regular"
    assert session_of({"marketSession": "pre"}) == "pre"
    assert session_of({"marketSession": "post"}) == "post"
    assert session_of({"marketSession": "overnight"}) == "closed"
    assert session_of({}) == "closed"


def test_freshness_of_is_directly_callable():
    assert freshness_of({"ts": None}, session="regular", now=NOW) == "stale"


def test_public_quote_is_frozen_dataclass():
    q = project_regular_quote(HUB_NVDA_RTH, ticker="NVDA", now=NOW, published_at=PUBLISHED)
    assert isinstance(q, PublicQuote)
    with pytest.raises(Exception):
        q.price = 1.0  # type: ignore[misc]
