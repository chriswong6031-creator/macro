"""INTL session-stamp helper + the two remaining always-None alpha as_of sites.

``engine.intl_stocks.compute_intl_alpha`` returns ``{per_ticker, markets, n}``
or None — never ``as_of``. PR #5683 wires the name-score append through
``_intl_session_asof`` (alpha as_of → library tip → wall-clock). This suite
covers that helper and pins the conviction-profile ctx + B2 accrual sites,
which used to pass ``(alpha or {}).get("as_of")`` and therefore always None.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_intl_library import _intl_session_asof


def test_intl_session_anchor_resolves_without_alpha_as_of():
    """compute_intl_alpha carries NO as_of key, so an
    ``(alpha or {}).get("as_of")`` anchor is ALWAYS None. The helper must
    resolve from the library tip (max per-rec asof) and only mark
    session_keyed=False when nothing does."""
    alpha = {"per_ticker": {"X": {}}, "markets": {}, "n": 1}
    to_write = [("a", {"asof": "2026-08-12"}), ("b", {"asof": "2026-08-13"}),
                ("c", {"asof": None}), ("d", {})]
    assert _intl_session_asof(alpha, to_write) == ("2026-08-13", True)
    # a future alpha as_of, if one ever appears, outranks the tip
    assert _intl_session_asof({"as_of": "2026-08-11"}, to_write) == ("2026-08-11", True)
    # nothing resolves -> wall-clock, marked as such
    before = str(pd.Timestamp.utcnow().date())
    out = _intl_session_asof(None, [("x", {})])
    after = str(pd.Timestamp.utcnow().date())
    assert out[0] in (before, after) and out[1] is False


def test_intl_session_anchor_skips_corrupt_alpha_as_of():
    to_write = [("a", {"asof": "2026-08-10"})]
    assert _intl_session_asof({"as_of": "not-a-date"}, to_write) == ("2026-08-10", True)


def test_conviction_profile_and_b2_use_session_asof():
    """Wiring pin: both remaining sites must consume the helper's session date,
    not the always-None alpha as_of expression. A text pin on
    ``(alpha or {}).get("as_of")`` at these sites is the defect."""
    src = Path(__file__).resolve().parents[1] / "scripts" / "build_intl_library.py"
    text = src.read_text()
    assert "def _intl_session_asof(" in text
    assert '_session_asof, _ = _intl_session_asof(' in text
    assert 'ctx={"as_of": _session_asof}' in text
    assert 'ctx={"as_of": (alpha or {}).get("as_of")}' not in text
    # B2: the archive call is fed the helper stamp, not alpha as_of
    b2 = text.index("archive_member_conviction(")
    window = text[b2:b2 + 200]
    assert "asof=_b2_asof" in window
    assert "_b2_asof = _session_asof" in text
    assert '_b2_asof = (alpha or {}).get("as_of")' not in text
