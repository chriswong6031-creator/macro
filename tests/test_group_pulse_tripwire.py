"""No-fused-number tripwire for the Group Reads plane (program law R-TIL-3).

The plane may print participation, direction and arc STATE. It may never print a
fused cross-basket score, rank, or heat number — the single thing that would turn a
context surface into a covert ranker. This file is the standing check.

Covers:
  (1)  The COMMITTED site/basketdata/pulse.json carries no key matching
       score|rank|heat at ANY depth.
  (2)  A freshly assembled object carries none either — the artifact could be stale;
       the code path is what must stay clean.
  (3)  The episode ledger's frozen columns carry none.
  (4)  GUARD-THE-GUARD: the same scanner run over a seeded mutant goes RED. A
       tripwire whose scan comes back clean is indistinguishable from a tripwire
       that no longer fires, so the green above only means something because this
       synthetic insertion goes red.
  (5)  No banned vocabulary in any artifact string value — the CI-guarded word
       "validated", or ignition language, would reach a user surface through GR1.
  (6)  site/basketdata/episodes.json gets the same treatment, and must join 1:1
       with pulse.json — the surface indexes both by basket_id, blind.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engine import group_pulse as GP

#: A key naming a fused number. `rank` also catches `ranking`/`rank_pctile`;
#: `heat` catches `heat_score`/`heatmap`.
FUSED_KEY = re.compile(r"score|rank|heat", re.IGNORECASE)

#: Vocabulary that must never reach a user-facing surface through this artifact.
BANNED_TEXT = re.compile(r"\bvalidated\b|ignit(e|ed|ing|ion)", re.IGNORECASE)

_SITE = Path(__file__).resolve().parent.parent / "site" / "basketdata"
ARTIFACT = _SITE / "pulse.json"
EPISODES_ARTIFACT = _SITE / "episodes.json"


def _offending_keys(obj, path: str = "") -> list[str]:
    """Every key in a nested structure whose NAME matches FUSED_KEY."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}/{k}"
            if FUSED_KEY.search(str(k)):
                out.append(here)
            out.extend(_offending_keys(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_offending_keys(v, f"{path}[{i}]"))
    return out


def _string_values(obj) -> list[str]:
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _string_values(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _string_values(v)]
    return [obj] if isinstance(obj, str) else []


@pytest.fixture(scope="module")
def committed() -> dict:
    if not ARTIFACT.exists():
        pytest.skip(f"{ARTIFACT} not built in this checkout")
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def committed_episodes() -> dict:
    if not EPISODES_ARTIFACT.exists():
        pytest.skip(f"{EPISODES_ARTIFACT} not built in this checkout")
    return json.loads(EPISODES_ARTIFACT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fresh() -> dict:
    """One object assembled through the real code path (see the contract suite's
    fixture builders) — the ARTIFACT can be stale, the CODE PATH cannot be."""
    from tests.test_group_pulse_contract import _assemble, _basket, _idx, _panel
    tk = [f"T{i:02d}" for i in range(8)]
    panel, _ = _panel(tk, _idx(), spike={"T00": 1.25}, vol_spike={"T01": 5.0})
    return {"tripwire_basket": _assemble("tripwire_basket", _basket(tk), panel)}


# ---------------------------------------------------------------------------
# (1)-(3) nothing fused anywhere
# ---------------------------------------------------------------------------

def test_committed_artifact_has_no_fused_number(committed):
    assert _offending_keys(committed) == []


def test_freshly_assembled_object_has_no_fused_number(fresh):
    assert _offending_keys(fresh) == []


def test_the_frozen_contract_key_set_has_no_fused_number():
    for k in (GP._TOP_KEYS, GP._PART_KEYS, GP._DIR_KEYS, GP._ARC_KEYS,
              GP._EPI_KEYS, GP._BASIS_KEYS):
        assert [x for x in k if FUSED_KEY.search(str(x))] == []


def test_the_episode_ledger_columns_have_no_fused_number():
    assert [c for c in GP.EPISODE_COLUMNS if FUSED_KEY.search(c)] == []


def test_every_basket_object_in_the_artifact_still_validates(committed):
    assert GP.validate_payload(committed) == []


def test_every_basket_object_declares_context_only(committed):
    assert committed, "the committed artifact must not be empty"
    for bid, obj in committed.items():
        assert obj["authority"] == "context_only", bid
        assert obj["schema"] == GP.SCHEMA, bid
        assert obj["arc"]["null_disclosure"] == GP.ARC_NULL_DISCLOSURE, bid


def test_committed_episodes_artifact_has_no_fused_number(committed_episodes):
    assert _offending_keys(committed_episodes) == []


def test_the_episode_history_key_set_has_no_fused_number():
    assert [k for k in GP.EPISODE_JSON_KEYS if FUSED_KEY.search(k)] == []


def test_committed_episodes_artifact_still_validates(committed_episodes):
    assert GP.validate_episode_history(committed_episodes) == []


def test_the_two_artifacts_join_one_to_one(committed, committed_episodes):
    """episodes.json is indexed by the SAME basket ids as pulse.json — the surface
    joins them blind, so a key present in one and absent from the other is a bug the
    page would render as a hole."""
    assert set(committed_episodes) == set(committed)


# ---------------------------------------------------------------------------
# (4) guard-the-guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [
    {"conviction_score": 0.7},
    {"rank": 3},
    {"heat": 0.9},
    {"nested": {"deep": [{"pulse_rank_pctile": 1}]}},
])
def test_the_scanner_goes_red_on_a_seeded_fused_number(fresh, seed):
    mutant = {**fresh, "mutant": seed}
    assert _offending_keys(mutant), f"scanner missed a seeded {seed!r}"


def test_the_scanner_does_not_fire_on_the_contract_it_guards():
    """Every key this plane actually ships must read clean, or the tripwire is a
    permanent red that someone will exempt away."""
    assert _offending_keys({"cohesion": 0.4, "agreement_pct": 0.3,
                            "trend_share_50d": 0.6, "washed_out_share": 0.1,
                            "persistence_share": 1.0, "state_change": "steady"}) == []


def test_the_scanner_is_deliberately_a_SUBSTRING_match():
    """Pinned so nobody narrows it by accident: `wheat` matches, because the rule is
    "no key CONTAINING score|rank|heat", not "no key EQUAL to" one. Over-firing is
    the safe direction here — the contract's key set is frozen and closed (an unknown
    key is already a validation violation), so a false positive costs nothing while a
    false negative is a covert ranker shipping to a surface."""
    assert _offending_keys({"wheat": 1}) == ["/wheat"]
    assert _offending_keys({"franchise": 1, "research": 2}) == []


# ---------------------------------------------------------------------------
# (5) banned vocabulary
# ---------------------------------------------------------------------------

def test_committed_artifact_carries_no_banned_vocabulary(committed):
    bad = [s for s in _string_values(committed) if BANNED_TEXT.search(s)]
    assert bad == [], bad


def test_freshly_assembled_object_carries_no_banned_vocabulary(fresh):
    bad = [s for s in _string_values(fresh) if BANNED_TEXT.search(s)]
    assert bad == [], bad


def test_the_text_scanner_goes_red_on_seeded_banned_words():
    for seeded in ("this signal is validated", "the basket is igniting"):
        assert BANNED_TEXT.search(seeded), seeded
