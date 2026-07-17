"""XSR-W1b: fast-lens board-rail completion + sector-strip build-order fix.

Part A — fast-tape rail on Sector Central:
  - _attach_rotation() stores per-kind ordinal + n_matched on each rotation block.
  - state_plain_en/zh translations cover all known states (no raw enum at tier 1).
  - When rotation artifact is absent, all records get rotation=None (quiet placeholder).

Part B — sector-strip build-order fix:
  - Client-side JS patch replaces stale conviction fragment in baked data-tip attributes.
    Tested by verifying the regex substitution logic (Python equivalent of the JS regex).
  - dag.yml note for build_sector_central acknowledges the client-side resolution.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import sector_central as sc
from engine import us_sector_rotation as usr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sector_rec(ticker: str, label: str = "Neutral", score: int = 50) -> dict:
    """Minimal sector record shaped like _carry()/_fuse() output."""
    return {
        "id": ticker.lower(),
        "ticker": ticker,
        "kind": "sector",
        "name": f"Sector {ticker}",
        "name_zh": f"{ticker}板块",
        "group": "Test",
        "conviction": {"score": score, "label_en": label, "label_zh": label, "dir": "flat"},
    }


def _rot_inst(ticker: str, kind: str = "sector", rank: int = 1, score: float = 10.0,
              state: str = "FRESH BUY") -> dict:
    """Minimal rotation instrument as emitted by build_us_sector_rotation."""
    return {
        "id": ticker.lower(), "key": ticker.lower(), "kind": kind,
        "ticker": ticker, "basket_id": ticker.lower(),
        "rotation_rank": rank, "rotation_score": score,
        "state_used": state, "components": {"mom20": score},
        "stale_flags": [],
    }


# ---------------------------------------------------------------------------
# Part A.1 — ordinal + n_matched stored in rotation dict
# ---------------------------------------------------------------------------

def test_attach_rotation_stores_ordinal_and_n_matched():
    """_attach_rotation() must store per-kind ordinal (1-indexed position in sorted
    matched list) and n_matched (total matched in this kind) on each rotation record."""
    recs = [_sector_rec("XLK"), _sector_rec("XLV"), _sector_rec("XLE")]
    rot_raw = {
        "instruments": [
            _rot_inst("XLK", rank=1, score=20.0, state="FRESH BUY"),
            _rot_inst("XLV", rank=7, score=5.0,  state="TURN SIGNALED"),
            _rot_inst("XLE", rank=11, score=1.0,  state="DECLINE"),
        ]
    }
    result = sc._attach_rotation(recs, rot_raw, kind="sector")
    # All 3 should be matched
    assert all(r.get("rotation") is not None for r in result)
    ordinals = {r["ticker"]: r["rotation"]["ordinal"] for r in result}
    n_matched = {r["ticker"]: r["rotation"]["n_matched"] for r in result}
    # Sorted by global rotation_rank ascending → XLK is #1, XLV is #2, XLE is #3
    assert ordinals["XLK"] == 1
    assert ordinals["XLV"] == 2
    assert ordinals["XLE"] == 3
    # All should share the same n_matched = 3
    assert n_matched["XLK"] == 3
    assert n_matched["XLV"] == 3
    assert n_matched["XLE"] == 3


def test_attach_rotation_ordinal_reflects_rank_sort_not_input_order():
    """Ordinal is determined by rotation_rank sort, not input order of records/instruments."""
    recs = [_sector_rec("XLY", score=80), _sector_rec("XLP", score=30)]
    # XLP has a better (lower) rotation_rank
    rot_raw = {
        "instruments": [
            _rot_inst("XLY", rank=5, state="RALLY ON"),
            _rot_inst("XLP", rank=2, state="TURN SIGNALED"),
        ]
    }
    result = sc._attach_rotation(recs, rot_raw, kind="sector")
    by_ticker = {r["ticker"]: r["rotation"] for r in result}
    # XLP has rank=2 (better), so ordinal=1; XLY rank=5 → ordinal=2
    assert by_ticker["XLP"]["ordinal"] == 1
    assert by_ticker["XLY"]["ordinal"] == 2
    assert by_ticker["XLP"]["n_matched"] == 2
    assert by_ticker["XLY"]["n_matched"] == 2


# ---------------------------------------------------------------------------
# Part A.2 — state_plain_en/zh translated (no raw enum at tier 1)
# ---------------------------------------------------------------------------

def test_attach_rotation_state_plain_covers_all_known_states():
    """Every state defined in us_sector_rotation._STATE_GOVS must be translated in both
    plain-word maps. Deriving from _STATE_GOVS (the authoritative enum producer) ensures
    any future added state immediately fails this test instead of leaking at tier 1."""
    # Authoritative source: the mapping that governs rotation-score governors.
    authoritative_states = list(usr._STATE_GOVS.keys())
    assert len(authoritative_states) >= 9, (
        "Expected at least 9 states in _STATE_GOVS (including CONFIRMING TURN)"
    )
    for state in authoritative_states:
        plain_en = sc._STATE_PLAIN_EN.get(state)
        plain_zh = sc._STATE_PLAIN_ZH.get(state)
        assert plain_en, f"_STATE_PLAIN_EN missing translation for: {state!r}"
        assert plain_zh, f"_STATE_PLAIN_ZH missing translation for: {state!r}"
        # Plain-word: must NOT be the verbatim uppercase enum (case-exact check).
        # Lowercase equivalents (e.g. "rolling over") are acceptable plain-word phrases.
        assert plain_en != state, (
            f"_STATE_PLAIN_EN[{state!r}] is the raw enum verbatim — must be translated"
        )
        # Must not ALL-CAPS match (TURN SIGNALED → plain word must differ from the enum)
        assert plain_en.upper() != state.upper() or plain_en != plain_en.upper(), (
            f"Plain word {plain_en!r} is uppercase-identical to enum {state!r}"
        )


def test_attach_rotation_embeds_state_plain_on_each_record():
    """Each rotation dict must carry state_plain_en + state_plain_zh from the engine map."""
    recs = [_sector_rec("XLK")]
    rot_raw = {"instruments": [_rot_inst("XLK", rank=1, state="FRESH BUY")]}
    result = sc._attach_rotation(recs, rot_raw, kind="sector")
    rot = result[0]["rotation"]
    assert rot["state_plain_en"] == sc._STATE_PLAIN_EN["FRESH BUY"]
    assert rot["state_plain_zh"] == sc._STATE_PLAIN_ZH["FRESH BUY"]
    # The raw state is preserved (for hover/receipt) but NOT used at tier 1
    assert rot["state"] == "FRESH BUY"


def test_attach_rotation_unknown_state_guard_rail():
    """Guard-rail: an unrecognised state_used value must NOT render as a raw ALL-CAPS enum
    at tier 1. The raw state is preserved in rot['state'] for hover receipt only.

    All currently known states are covered by test_attach_rotation_state_plain_covers_all_known_states.
    This guard catches any truly unknown state (programming error or new enum added without
    updating the plain-word maps) — the fallback must be an empty string, never the raw enum.
    """
    # Use a plausible-looking unknown state (what a new enum might look like)
    unknown_state = "NEW_UNKNOWN_STATE"
    recs = [_sector_rec("XLK")]
    rot_raw = {"instruments": [_rot_inst("XLK", rank=1, state=unknown_state)]}
    result = sc._attach_rotation(recs, rot_raw, kind="sector")
    rot = result[0]["rotation"]

    # The raw state is stored for hover/receipt (correct)
    assert rot["state"] == unknown_state

    # Tier-1 guard: state_plain_en must NOT be a raw ALL-CAPS-words enum.
    # Implementation: unknown states fall back to "" (empty), never the raw enum string.
    plain_en = rot["state_plain_en"]
    is_raw_allcaps_enum = bool(re.fullmatch(r"[A-Z][A-Z0-9_ ]+", plain_en))
    assert not is_raw_allcaps_enum, (
        f"state_plain_en {plain_en!r} looks like a raw ALL-CAPS enum leaked to tier 1 "
        f"for unknown state {unknown_state!r}. Add it to _STATE_PLAIN_EN/_STATE_PLAIN_ZH."
    )


# ---------------------------------------------------------------------------
# Part A.3 — absent rotation artifact → rotation=None on all records
# ---------------------------------------------------------------------------

def test_attach_rotation_absent_artifact_sets_null():
    """When rotation_raw is empty {}, all records get rotation=None (quiet placeholder
    for the 'awaiting tonight's data' branch in the template)."""
    recs = [_sector_rec("XLK"), _sector_rec("XLV")]
    result = sc._attach_rotation(recs, {}, kind="sector")
    assert all(r["rotation"] is None for r in result), (
        "Expected rotation=None for all records when artifact is absent"
    )


def test_attach_rotation_no_instruments_in_artifact_sets_null():
    """instruments key present but empty list → all records get rotation=None."""
    recs = [_sector_rec("XLK")]
    result = sc._attach_rotation(recs, {"instruments": []}, kind="sector")
    assert result[0]["rotation"] is None


# ---------------------------------------------------------------------------
# Part A.4 — kind isolation: basket instruments don't bleed into sector records
# ---------------------------------------------------------------------------

def test_attach_rotation_kind_isolation():
    """A basket instrument must not match a sector record of the same ticker.
    Per-kind ordinal must be computed over the correct universe."""
    sector_recs = [_sector_rec("XLK"), _sector_rec("XLV")]
    rot_raw = {
        "instruments": [
            _rot_inst("XLK", kind="basket", rank=1, state="FRESH BUY"),   # basket kind
            _rot_inst("XLV", kind="sector", rank=3, state="RALLY ON"),    # sector kind
        ]
    }
    result = sc._attach_rotation(sector_recs, rot_raw, kind="sector")
    by_ticker = {r["ticker"]: r["rotation"] for r in result}
    # XLK is a basket instrument — must NOT match sector record → rotation=None
    assert by_ticker["XLK"] is None, "Basket instrument must not match sector record"
    # XLV is a sector instrument — must match
    assert by_ticker["XLV"] is not None
    assert by_ticker["XLV"]["ordinal"] == 1
    assert by_ticker["XLV"]["n_matched"] == 1   # only 1 sector instrument matched


# ---------------------------------------------------------------------------
# Part B — client-side conviction tooltip patch (Python equivalent of JS logic)
# ---------------------------------------------------------------------------

def _apply_tip_patch(baked_tip_en: str, baked_tip_zh: str,
                     sc_label_en: str, sc_label_zh: str) -> tuple[str, str]:
    """Python equivalent of the JS regex patch in _leadership_board.html.j2.

    The JS replaces ' · conviction: <old>' with ' · conviction: <new>' in
    data-tip-en, and ' · 评级：<old>' with ' · 评级：<new>' in data-tip-zh.
    If no conviction fragment exists, it appends one.
    """
    new_en = re.sub(r" · conviction:.*$", "", baked_tip_en)
    new_zh = re.sub(r" · 评级：.*$", "", baked_tip_zh)
    if sc_label_en:
        new_en = new_en + " · conviction: " + sc_label_en
    if sc_label_zh:
        new_zh = new_zh + " · 评级：" + sc_label_zh
    return new_en, new_zh


def test_tip_patch_replaces_stale_conviction_with_fresh():
    """XLV stale label (Reduce, from previous nightly) is patched to today's Cautious."""
    stale_tip_en = "RS #2 — Health Care: leading · conviction: Reduce"
    stale_tip_zh = "RS #2 — 医疗保健: 领先 · 评级：减配"
    patched_en, patched_zh = _apply_tip_patch(stale_tip_en, stale_tip_zh, "Cautious", "谨慎")
    assert "Cautious" in patched_en
    assert "Reduce" not in patched_en
    assert "谨慎" in patched_zh
    assert "减配" not in patched_zh
    # Base RS data is preserved
    assert "RS #2" in patched_en
    assert "leading" in patched_en


def test_tip_patch_appends_when_no_conviction_fragment():
    """When the baked tip has no conviction fragment, the patch appends it."""
    baked_en = "RS #5 — Technology: mid-pack"
    baked_zh = "RS #5 — 科技：中间"
    patched_en, patched_zh = _apply_tip_patch(baked_en, baked_zh, "Constructive", "建设性")
    assert "Constructive" in patched_en
    assert "建设性" in patched_zh
    assert "RS #5" in patched_en


def test_tip_patch_no_label_leaves_tip_unchanged_except_strip():
    """When fresh label is empty, the conviction fragment is stripped (honest null)."""
    baked_en = "RS #1 — Energy: leading · conviction: Reduce"
    baked_zh = "RS #1 — 能源: 领先 · 评级：减配"
    patched_en, patched_zh = _apply_tip_patch(baked_en, baked_zh, "", "")
    # Fragment stripped, nothing appended
    assert "conviction" not in patched_en
    assert "评级" not in patched_zh
    assert "RS #1" in patched_en


def test_tip_patch_idempotent_on_already_fresh_tip():
    """If the baked tip already has the correct label, patching is idempotent."""
    correct_en = "RS #2 — Health Care: leading · conviction: Cautious"
    correct_zh = "RS #2 — 医疗保健: 领先 · 评级：谨慎"
    patched_en, patched_zh = _apply_tip_patch(correct_en, correct_zh, "Cautious", "谨慎")
    assert patched_en == correct_en
    assert patched_zh == correct_zh


# ---------------------------------------------------------------------------
# Part B — dag.yml declaration: build_sector_central carries the client-side note
# ---------------------------------------------------------------------------

def test_dag_yml_sector_central_has_client_side_note():
    """dag.yml entry for scripts.build_sector_central must document the client-side
    conviction-tooltip patch (XSR-W1b build-order fix)."""
    dag = Path(__file__).resolve().parent.parent / "config" / "dag.yml"
    assert dag.exists(), "config/dag.yml not found"
    content = dag.read_text(encoding="utf-8")
    # The note must reference the XSR-W1b fix and the client-side fetch
    assert "XSR-W1b" in content, (
        "dag.yml build_sector_central entry must carry the XSR-W1b build-order note"
    )
    assert "sectordata/sector_central.json" in content, (
        "dag.yml must declare sectordata/sector_central.json as the correct write path"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
