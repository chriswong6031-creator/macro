"""intel_hub policy-lean gate (W0 fix, QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md §4 brief 1).

A low- or absent-conviction policy facet must contribute NOTHING:
  - dirs["policy"] must be None  (not the raw direction)
  - early_edge flag must not fire
  - policy_aligned / policy_conflict flags must not fire
  - gap_mult must equal the no-policy baseline (gap unchanged)

Audit finding: build_policy_index stores conviction but all downstream consumption
sites read the lean direction without checking it, so a low-conviction thesis steered
dirs["policy"], fired early_edge, and inflated gap_mult.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.intel_hub import (  # noqa: E402
    _dirs,
    _dossier,
    _leading_gap,
    _policy_usable,
    _VOTING_DESKS,
    build_policy_index,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _make_policy_facet(conviction: str | None, dir_: int = 1) -> dict:
    return {"dir": dir_, "lean": "overweight", "conviction": conviction,
            "actor": "Fed", "thesis": "test thesis", "horizon_d": 90, "via": "direct"}


def _make_v(with_alt: bool = True) -> dict:
    """Minimal per-ticker facet bundle — enough for _dirs / _leading_gap / _dossier."""
    alt = {"signal_score": 75, "action": "BUY", "extended": False} if with_alt else {}
    radar = {"state": "POSITIVE_DIVERGENCE", "lifecycle": "forming"}
    news = {"sentiment_lean": "pos", "sentiment_score": 0.1, "n_recent": 0,
            "sectors": ["XLK"], "name": "ACME Corp", "baskets": []}
    return {"alt": alt, "radar": radar, "news": news}


def _empty_pidx() -> dict:
    return {"by_ticker": {}, "by_sector": {}, "regime": None}


# --------------------------------------------------------------------------- #
# _policy_usable
# --------------------------------------------------------------------------- #

def test_policy_usable_high_conviction():
    assert _policy_usable({"conviction": "high", "dir": 1}) is True


def test_policy_usable_medium_conviction():
    assert _policy_usable({"conviction": "medium", "dir": 1}) is True


def test_policy_usable_low_conviction_is_false():
    assert _policy_usable({"conviction": "low", "dir": 1}) is False


def test_policy_usable_none_conviction_is_false():
    assert _policy_usable({"conviction": None, "dir": 1}) is False


def test_policy_usable_none_facet_is_false():
    assert _policy_usable(None) is False


# --------------------------------------------------------------------------- #
# _dirs — low-conviction facet must yield dirs["policy"] == None
# --------------------------------------------------------------------------- #

def test_dirs_policy_none_when_low_conviction():
    facet = _make_policy_facet(conviction="low", dir_=1)
    v = _make_v()
    d = _dirs(v, facet)
    assert d["policy"] is None, (
        f"Expected dirs['policy']=None for low-conviction facet, got {d['policy']}"
    )


def test_dirs_policy_none_when_no_conviction():
    facet = _make_policy_facet(conviction=None, dir_=1)
    v = _make_v()
    d = _dirs(v, facet)
    assert d["policy"] is None


def test_dirs_policy_set_when_high_conviction():
    facet = _make_policy_facet(conviction="high", dir_=1)
    v = _make_v()
    d = _dirs(v, facet)
    assert d["policy"] == 1


# --------------------------------------------------------------------------- #
# _leading_gap — policy contributes to lag_up / lag_present at NO conviction level
# (operator ruling 2026-08-08, Option A — DNR:KILL-LLM-ORIGINATION / constitution A7).
# The conviction gate this file originally guarded is now MOOT for scoring: the policy
# desk's direction is LLM-originated, so it casts no vote at any conviction.
# --------------------------------------------------------------------------- #

def test_leading_gap_never_moved_by_policy_at_any_conviction():
    """Policy must not affect lag_up or lag_present — low OR high conviction.

    A minimal bundle with no news/standout leaves policy as the ONLY candidate lagging
    desk, so any non-zero lag_up/lag_present here could only have come from policy.
    Before the A7 heal a high-conviction bullish policy lean scored lag_up=1, which
    dropped gap by 1 and cut opportunity_score by 15% — an LLM-originated rank move.
    """
    # strip news/standout so only alt + radar (leading) + policy (lagging candidate) remain
    v_minimal = {"alt": {"signal_score": 75, "action": "BUY", "extended": False},
                 "radar": {"state": "POSITIVE_DIVERGENCE", "lifecycle": "forming"}}

    for conviction in (None, "low", "medium", "high"):
        facet = _make_policy_facet(conviction=conviction, dir_=1)
        gap = _leading_gap(v_minimal, _dirs(v_minimal, facet))
        assert gap["lag_up"] == 0, (
            f"policy (conviction={conviction}) must not contribute to lag_up, got {gap['lag_up']}"
        )
        assert gap["lag_present"] == 0, (
            f"policy (conviction={conviction}) must not appear in lag_present, "
            f"got {gap['lag_present']}"
        )

    # the display direction is still carried on the dossier — only the VOTE is gone
    assert _dirs(v_minimal, _make_policy_facet(conviction="high", dir_=1))["policy"] == 1


# --------------------------------------------------------------------------- #
# early_edge flag — must NOT fire when conviction is low
# --------------------------------------------------------------------------- #

def test_early_edge_does_not_fire_for_low_conviction_policy():
    """The primary audit finding: low-conviction policy was triggering early_edge."""
    v = _make_v(with_alt=True)
    # low-conviction overweight → should NOT fire early_edge
    low_facet = _make_policy_facet(conviction="low", dir_=1)
    pidx = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
    import datetime, tempfile
    from pathlib import Path as P
    from unittest.mock import patch
    today = datetime.date(2026, 7, 2)
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}
    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d = _dossier("ACME", v, pidx, vel)
    assert "early_edge" not in d["flags"], (
        f"early_edge must not fire for low-conviction policy; flags={d['flags']}"
    )


def test_early_edge_fires_for_high_conviction_policy():
    """Sanity: high-conviction policy + stealth conditions should fire early_edge."""
    v = _make_v(with_alt=True)
    # quiet news + alt=1 + radar POSITIVE_DIVERGENCE + usable policy dir=1 → early_edge
    high_facet = _make_policy_facet(conviction="high", dir_=1)
    pidx = {"by_ticker": {"ACME": high_facet}, "by_sector": {}, "regime": None}
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch
    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d = _dossier("ACME", v, pidx, vel)
    assert "early_edge" in d["flags"], (
        f"early_edge should fire for high-conviction policy; flags={d['flags']}"
    )


# --------------------------------------------------------------------------- #
# policy_aligned / policy_conflict — must not fire for low-conviction facets
# --------------------------------------------------------------------------- #

def test_policy_aligned_does_not_fire_for_low_conviction():
    v = _make_v(with_alt=True)
    low_facet = _make_policy_facet(conviction="low", dir_=1)
    pidx = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch
    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d = _dossier("ACME", v, pidx, vel)
    assert "policy_aligned" not in d["flags"], f"flags={d['flags']}"
    assert "policy_conflict" not in d["flags"], f"flags={d['flags']}"


def test_policy_conflict_does_not_fire_for_low_conviction():
    v = _make_v(with_alt=True)
    # low-conviction bearish policy against a bullish name
    low_facet = _make_policy_facet(conviction="low", dir_=-1)
    pidx = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch
    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d = _dossier("ACME", v, pidx, vel)
    assert "policy_conflict" not in d["flags"], f"flags={d['flags']}"


# --------------------------------------------------------------------------- #
# gap_mult — low-conviction policy must not inflate gap, so gap_mult equals the
# no-policy value.  gap_mult = 1.0 + 0.15 * max(-2, min(2, gap["gap"])).
# With no policy contribution the gap is determined by leading desks only.
# --------------------------------------------------------------------------- #

def test_gap_mult_equals_no_policy_when_low_conviction():
    """opportunity_score and gap_mult must be the same whether policy is low-conviction
    or absent entirely — the no-policy baseline."""
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch

    v = _make_v(with_alt=True)
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}

    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        # no policy
        d_none = _dossier("ACME", v, _empty_pidx(), vel)
        # low-conviction policy that would have inflated gap if ungated
        low_facet = _make_policy_facet(conviction="low", dir_=1)
        pidx_low = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
        d_low = _dossier("ACME", v, pidx_low, vel)

    assert d_low["opportunity_score"] == d_none["opportunity_score"], (
        f"low-conviction policy must not change opportunity: "
        f"no-policy={d_none['opportunity_score']} low={d_low['opportunity_score']}"
    )
    assert d_low["leading_gap"] == d_none["leading_gap"], (
        f"leading_gap must be identical: no-policy={d_none['leading_gap']} low={d_low['leading_gap']}"
    )


def test_composite_and_source_mix_unchanged_by_low_conviction_policy():
    """A low-conviction facet must contribute NOTHING — it must not inflate
    composite_conviction (via len(present)), n_facets, source_mix, or the human read."""
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch

    v = _make_v(with_alt=True)
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}

    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d_none = _dossier("ACME", v, _empty_pidx(), vel)
        low_facet = _make_policy_facet(conviction="low", dir_=1)
        pidx_low = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
        d_low = _dossier("ACME", v, pidx_low, vel)

    assert d_low["composite_conviction"] == d_none["composite_conviction"], (
        f"low-conviction policy must not inflate composite: "
        f"no-policy={d_none['composite_conviction']} low={d_low['composite_conviction']}"
    )
    assert d_low["n_facets"] == d_none["n_facets"]
    assert "policy" not in d_low["source_mix"], f"source_mix={d_low['source_mix']}"
    assert "policy tailwind" not in d_low["read"], (
        f"human read must not claim a policy tailwind for a low-conviction lean: {d_low['read']}"
    )


# --------------------------------------------------------------------------- #
# hero tooltip copy (XPV2-IH-T0 / DAC-008 Data-Authority review) — the visible
# ranking-method popover must not describe policy as a voting desk. The tests
# above prove the DATA layer excludes policy from every score; these prove the
# visible COPY says so too, never the reverse. Production previously read
# "Five desks vote on each name: news flow, alt-data, divergence radar,
# buy-board, policy intent" — a false authority story the data never supported.
# --------------------------------------------------------------------------- #
_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "intelligence_hub.html.j2"


def _hero_tooltip() -> tuple[str, str]:
    """(en, zh) text of the hero '?' popover that explains how the page ranks names."""
    src = _TEMPLATE.read_text()
    m = re.search(r'data-tip-en="([^"]*)"\s+data-tip-zh="([^"]*)">\?</button>', src)
    assert m, "hero lens-q ranking-method tooltip not found in intelligence_hub.html.j2"
    return m.group(1), m.group(2)


def test_hero_tooltip_does_not_claim_policy_votes():
    """DAC-008's exact defect: a sentence naming the voting desks must never also
    name policy. Policy is display-only (excluded from _VOTING_DESKS — A7 /
    DNR:KILL-LLM-ORIGINATION); the copy must say so, never imply the opposite."""
    en, zh = _hero_tooltip()
    for sentence in en.split(". "):
        if "vote" in sentence.lower() and "never" not in sentence.lower():
            assert "policy" not in sentence.lower(), (
                f"a voting-desk sentence must not also name policy: {sentence!r}"
            )
    assert "never votes" in en, f"EN tooltip must state policy never votes: {en!r}"
    assert "从不参与投票" in zh, f"ZH tooltip must state policy never votes: {zh!r}"


def test_hero_tooltip_states_the_ranking_invariants():
    """Observable end state (XPV2-IH-T0 handoff): rank rises with signal/edge/
    timing; conviction only breaks a tie; a proven-wrong feeder can only
    de-escalate a name's rank; policy is context and never votes; the page is
    not a trade trigger. Checked in both languages so a future edit can't fix
    one and silently drop the other. The voting-desk count is tied to
    _VOTING_DESKS itself so a future change to that constant has to touch this
    test rather than let the copy drift silently out of sync."""
    en, zh = _hero_tooltip()
    assert set(_VOTING_DESKS) == {"news", "alt", "radar", "standout"}
    num_words = {4: "Four", 5: "Five", 6: "Six"}
    want = f"{num_words[len(_VOTING_DESKS)]} desks vote"
    assert want in en, f"tooltip must say {want!r} to match _VOTING_DESKS: {en!r}"
    for label, desk in (("news flow", "新闻流"), ("alt-data", "另类数据"),
                        ("divergence radar", "背离雷达"), ("buy-board", "买入榜")):
        assert label in en, f"voting desk {label!r} missing from EN tooltip: {en!r}"
        assert desk in zh, f"voting desk {desk!r} missing from ZH tooltip: {zh!r}"
    assert "tie" in en, f"EN tooltip must state conviction is a tie-break: {en!r}"
    assert "打破平局" in zh, f"ZH tooltip must state conviction is a tie-break: {zh!r}"
    assert "never lift it" in en, (
        f"EN tooltip must state a proven-wrong feeder can only de-escalate: {en!r}"
    )
    assert "绝不会拉高" in zh, (
        f"ZH tooltip must state a proven-wrong feeder can only de-escalate: {zh!r}"
    )
    assert "never a trade trigger" in en, f"EN tooltip must keep the no-trade-trigger line: {en!r}"
    assert "绝非交易触发" in zh, f"ZH tooltip must keep the no-trade-trigger line: {zh!r}"
