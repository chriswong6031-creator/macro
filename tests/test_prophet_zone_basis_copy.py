"""tests/test_prophet_zone_basis_copy.py — no raw token reaches the zone copy.

WHY THIS SUITE EXISTS
---------------------
`entry_zone` is whitelisted onto the published `site/prophet/index.json` row (the Terminal
and the showcase read that file, not the per-plan JSON), so every string inside it is
USER-VISIBLE COPY.

Two of those strings were built by interpolating engine vocabulary straight into a
sentence:

    basis               f"leader pullback ({leader_pullback['state']}) — reset band, ..."
    conversion_evidence "us_basket_turn washout/turning membership"

The first renders as "leader pullback (RESET_TURN) — …"; the second names an internal
module and two more raw states.  Neither had ever appeared on a live plan, for one reason
only: nothing published `site/anticipationdata/us_leader_pullback.json`, so
`is_leader_pullback` was False on every production row and that branch was unreachable.
Shipping the coverage publisher makes it reachable — which is why the copy is fixed in the
same change, and pinned here.

WHAT IS PINNED
--------------
* EXHAUSTIVE over the organ's own state vocabulary plus an unmapped state and ``None`` —
  an unmapped token must fall back to a PHRASE, never to the token;
* every EN string ships a ZH half, written as ZH (CJK, not a gloss), and the two differ;
* no raw enum, no snake_case slug, no internal module or study name, no untranslated
  indicator jargon, no falsifier/refutation vocabulary (operator 2026-07-27, #3821);
* the SOURCE never interpolates the raw provenance variables into the copy again — the
  mutation guard, because a table can be correct while the call site bypasses it.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import prophet_bridge as pb  # noqa: E402
from engine import us_early_turn as et  # noqa: E402
from engine import us_leader_pullback as organ  # noqa: E402

ASOF = "2026-07-02"

#: Every literal `_reset_band_or_board` can hand the copy layer.  Two come from this
#: module, two from `engine.us_early_turn.reset_band`.  A new one that is not mapped is a
#: new raw string on a user-visible payload, so this list is a CONTRACT, not a snapshot.
BAND_BASIS_LITERALS = (
    "entry ladder reset band",
    "MA10/MA20 reset",
    "1-2x ATR band (price already under both short MAs)",
    "board band (reset band unresolved)",
)

#: Raw vocabulary that must never reach a reader.  Enum tokens and internal state names
#: are checked case-SENSITIVELY (the plain English words "pullback", "leader", "none" are
#: fine; the enum spellings are not).
BANNED_TOKENS = (
    # engine.us_leader_pullback states
    "PULLBACK", "RESET_TURN", "RESUMED", "LEADER", "NONE",
    # engine.us_basket_turn states
    "WASHED_OUT", "BASING", "TURNING", "CONFIRMED", "FALLING",
    # module / study / field names
    "us_basket_turn", "us_leader_pullback", "prophet_bridge", "us_early_turn",
    "entry_signal", "buy_zone", "zone_class", "conversion_class", "coiled",
    "washout_ctx", "pullback_range_close_basis", "lane=bottoming", "washout/turning",
    # untranslated indicator jargon (a stat the reader cannot parse is not plain words)
    "MA10", "MA20", "ATR", "StochRSI", "RSI-MACD", "%K", "%D", "200dMA", "dMA",
)

#: Falsifier / settled-fact vocabulary. Tripwires keep evaluating in the background; the
#: user-facing cycle surfaces show windows and conditions, never verdicts.
BANNED_VOICE = ("falsif", "refut", "证伪", "validated", "已验证", "guarantee", "保证")


def _copy_fields(zone: dict) -> dict[str, str]:
    """Only the strings a reader can see. `zone_class`/`stance` are machine keys."""
    return {k: v for k, v in zone.items()
            if k in ("basis", "basis_zh", "conversion_evidence",
                     "conversion_evidence_zh") and isinstance(v, str)}


def _assert_plain(zone: dict) -> None:
    fields = _copy_fields(zone)
    assert set(fields) == {"basis", "basis_zh", "conversion_evidence",
                           "conversion_evidence_zh"}, fields
    for key, text in fields.items():
        assert text.strip(), key
        # The house slug guard: engine vocabulary is snake_case, prose is not.
        assert "_" not in text, (key, text)
        for token in BANNED_TOKENS:
            assert token not in text, (key, token, text)
        for word in BANNED_VOICE:
            assert word not in text.lower(), (key, word, text)
    assert fields["basis"] != fields["basis_zh"]
    assert fields["conversion_evidence"] != fields["conversion_evidence_zh"]
    for zh_key in ("basis_zh", "conversion_evidence_zh"):
        assert any("一" <= ch <= "鿿" for ch in fields[zh_key]), fields[zh_key]
    for en_key in ("basis", "conversion_evidence"):
        assert not any("一" <= ch <= "鿿" for ch in fields[en_key]), \
            fields[en_key]


def _row(lane: str = "continuation", spot: float = 100.0) -> dict:
    return {
        "ticker": "T", "dir": "up", "lane": lane,
        "entry_signal": {
            "act_level": 3, "status": "buy_now", "spot": spot, "atr_pct": 2.0,
            "buy_zone": {"low": spot * 0.97, "high": spot},
            "chase_above": spot * 1.01,
            "timing": {"opens_in_days_lo": 0, "opens_in_days_hi": None},
        },
    }


def _zone(**kwargs) -> dict:
    params = {"entry": 100.0, "klass": None, "price_basis_date": ASOF}
    row = kwargs.pop("row", None) or _row()
    params.update(kwargs)
    return pb.build_entry_zone(row, **params)


# =========================================================================== #
# 1. Every reachable branch is plain words in both languages                   #
# =========================================================================== #
class TestEveryBranchIsPlainWords:
    @pytest.mark.parametrize("state", (*organ.STATES, "A_BRAND_NEW_STATE", None))
    def test_the_leader_pullback_branch_never_prints_the_ORGANS_state(self, state):
        """THE DEFECT.  This branch used to read
        ``f"leader pullback ({leader_pullback['state']}) — …"``.

        EXHAUSTIVE over the organ's vocabulary AND over a state the map has never been
        taught: an unmapped token must fall back to a phrase, so a future widening of
        `LEADER_PULLBACK_CONTEXT_STATES` cannot leak one.
        """
        zone = _zone(leader_pullback={"leader_pullback": True, "state": state,
                                      "pullback_high": 118.0})
        assert zone["zone_class"] == pb.ZONE_CLASS_RESET_BAND
        _assert_plain(zone)
        assert "market leader" in zone["basis"]

    def test_the_two_states_that_can_ACTUALLY_reach_this_branch_are_mapped(self):
        """The fallback is a safety net, not the plan: both live context states have
        their own copy, so the reader is told which one it is."""
        for state in sorted(et.LEADER_PULLBACK_CONTEXT_STATES):
            assert state in pb.ZONE_LEADER_STATE_COPY, state
        turned = _zone(leader_pullback={"leader_pullback": True,
                                        "state": "RESET_TURN", "pullback_high": 118.0})
        retracing = _zone(leader_pullback={"leader_pullback": True,
                                           "state": "PULLBACK", "pullback_high": 118.0})
        assert turned["basis"] != retracing["basis"]
        assert turned["basis_zh"] != retracing["basis_zh"]

    def test_the_both_stretched_branch_is_plain_words(self):
        zone = _zone(extension={"both_extended": True})
        assert zone["zone_class"] == pb.ZONE_CLASS_WAIT_RESET
        _assert_plain(zone)

    def test_the_patience_branch_is_plain_words(self):
        zone = _zone(klass=pb.ADMISSION_CLASS_PATIENCE)
        assert zone["zone_class"] == pb.ZONE_CLASS_RESET_BAND
        _assert_plain(zone)

    def test_the_default_accumulate_branch_is_plain_words(self):
        zone = _zone()
        assert zone["zone_class"] == pb.ZONE_CLASS_ACCUMULATE
        _assert_plain(zone)

    @pytest.mark.parametrize(
        "kwargs", (
            {"washout_context": True},
            {"row": _row(lane="bottoming")},
            {"row": _row(lane="continuation")},
        ))
    def test_every_conversion_evidence_branch_is_plain_words(self, kwargs):
        """It used to name a module and two raw states, or a board slug."""
        _assert_plain(_zone(**kwargs))

    def test_the_starter_stance_does_not_change_the_copy_law(self):
        _assert_plain(_zone(early_turn=True, leader_pullback={
            "leader_pullback": True, "state": "PULLBACK", "pullback_high": 118.0}))


# =========================================================================== #
# 2. The lexicons themselves                                                   #
# =========================================================================== #
class TestLexicons:
    @pytest.mark.parametrize("table", (
        pb.ZONE_LEADER_STATE_COPY, pb.ZONE_BAND_BASIS_COPY,
        pb.ZONE_CONVERSION_EVIDENCE_COPY))
    def test_every_entry_is_a_bilingual_pair_of_plain_words(self, table):
        for key, row in table.items():
            assert set(row) == {"en", "zh"}, key
            assert row["en"] and row["zh"] and row["en"] != row["zh"], key
            assert "_" not in row["en"], key
            assert any("一" <= ch <= "鿿" for ch in row["zh"]), key
            for token in BANNED_TOKENS:
                assert token not in row["en"], (key, token)
                assert token not in row["zh"], (key, token)

    def test_every_band_provenance_string_the_code_can_produce_is_MAPPED(self):
        """FAIL-CLOSED LANE GATE.  A new band source that nobody maps would otherwise
        ship its raw provenance string onto a published payload."""
        for literal in BAND_BASIS_LITERALS:
            assert literal in pb.ZONE_BAND_BASIS_COPY, literal

    def test_those_literals_are_the_ones_the_code_actually_emits(self):
        """The list above is only a contract if it tracks the source.  Both producers
        are read here, so adding a fifth literal reds this test rather than shipping."""
        band_src = inspect.getsource(pb.build_entry_zone)
        reset_src = inspect.getsource(et.reset_band)
        for literal in BAND_BASIS_LITERALS:
            assert (literal in band_src) or (literal in reset_src), literal

    def test_an_unmapped_key_returns_a_PHRASE_never_the_key(self):
        """`_copy` is the single chokepoint; if it ever echoed its key back, every guard
        above would still pass on the mapped cases and leak on the unmapped one."""
        for table, fallback in (
            (pb.ZONE_LEADER_STATE_COPY, pb.ZONE_LEADER_STATE_FALLBACK),
            (pb.ZONE_BAND_BASIS_COPY, pb.ZONE_BAND_BASIS_FALLBACK),
        ):
            en, zh = pb._copy(table, "TOTALLY_UNKNOWN_TOKEN", fallback)
            assert en == fallback["en"] and zh == fallback["zh"]
            assert "TOTALLY_UNKNOWN_TOKEN" not in en and "TOTALLY_UNKNOWN_TOKEN" not in zh


# =========================================================================== #
# 3. Mutation guard — the call site must not bypass the tables                  #
# =========================================================================== #
class TestTheCallSiteCannotBypassTheTables:
    def test_no_raw_provenance_variable_is_interpolated_into_the_copy(self):
        """A correct lexicon proves nothing if the sentence is still built by hand.

        This is the exact line that shipped:
            basis = f"leader pullback ({(leader_pullback or {}).get('state') or ...
        """
        source = inspect.getsource(pb.build_entry_zone)
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "basis = " in stripped or "basis_zh = " in stripped or (
                    stripped.startswith(("f\"", "f'")) and "basis" in source):
                assert "{band_basis}" not in stripped, stripped
                assert "leader_pullback" not in stripped or "_copy" in stripped, stripped
        assert "{band_basis}" not in source, (
            "the raw provenance string is interpolated into user-visible copy again")
        assert ".get('state')}" not in source and '.get("state")}' not in source

    def test_the_evidence_half_of_the_conversion_class_is_a_bilingual_pair(self):
        """`zone_conversion_class` returns (class, en, zh). A 2-tuple return would mean
        the ZH half was dropped somewhere — and ZH-less copy is a house-law break, not a
        cosmetic one."""
        for kwargs in ({"washout_context": True}, {"washout_context": False}):
            out = pb.zone_conversion_class(_row(), **kwargs)
            assert len(out) == 3, out
            klass, en, zh = out
            assert klass in (pb.ZONE_CONVERSION_WASHOUT, pb.ZONE_CONVERSION_PULLBACK)
            assert en and zh and en != zh
