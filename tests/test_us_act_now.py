"""tests/test_us_act_now.py — US bottoming-watch lane assembler (W-A).

Pins the lane gate, the ordering, the cap, the FT-R1 dual-read id set, the
BUY-quote + trend-gate-conflict flags, the honest null, and the two display
fences that keep a WATCH lane free of buy verbs.

The live receipt (gate G0.2) is `test_gold_miners_case_from_committed_log`:
the real committed `data/sector_cycles/forward_log.parquet` row
`b-gold_miners: Trough, pos=2.0, osc_slope=+1.3, signal=BUY, above200d=False`
must land on the lane with its gate-shut conflict flagged.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.us_act_now import (
    BOTTOMING_CAP,
    DISPLAY_FORBIDDEN_FIELDS,
    NULL_DISCLOSURE_EN,
    NULL_DISCLOSURE_ZH,
    assemble_bottoming_watch,
    canonical_id,
    contains_buy_word,
)

TEMPLATE = ROOT / "templates" / "sector_central.html.j2"


# ─────────────────────────────────────── helpers ──────────────────────────────
def _row(id_="b-x", phase="Trough", pos=5.0, slope=1.0, signal="BUY",
         above200d=False, kind="basket", name=None, timing="COUNTERTREND BOUNCE"):
    return {
        "id": id_, "kind": kind, "name": name or id_, "phase": phase,
        "pos": pos, "osc_slope": slope, "signal": signal,
        "above200d": above200d, "timing_state": timing,
    }


def _ids(out):
    return [r["id"] for r in out["bottoming_watch"]]


# ─────────────────────────────────── the lane gate ────────────────────────────
def test_trough_and_rising_qualifies():
    out = assemble_bottoming_watch([_row(id_="b-gold_miners", slope=1.3)])
    assert _ids(out) == ["b-gold_miners"]


def test_trough_and_falling_does_not_qualify():
    out = assemble_bottoming_watch([_row(slope=-1.3)])
    assert out["bottoming_watch"] == []


def test_trough_and_flat_slope_does_not_qualify():
    """osc_slope == 0 is not rising — the gate is strict."""
    assert assemble_bottoming_watch([_row(slope=0.0)])["bottoming_watch"] == []


def test_non_trough_phase_does_not_qualify():
    for phase in ("Expansion", "Downturn", "Peak", "Recovery"):
        out = assemble_bottoming_watch([_row(phase=phase, slope=2.0)])
        assert out["bottoming_watch"] == [], f"{phase} must not reach the lane"


def test_missing_slope_is_unknown_not_rising():
    """A null slope must never manufacture a bottoming call."""
    assert assemble_bottoming_watch([_row(slope=None)])["bottoming_watch"] == []
    assert assemble_bottoming_watch([_row(slope=float("nan"))])["bottoming_watch"] == []


def test_phase_match_is_exact():
    """'Trough' only — no substring/case slop that would widen the gate."""
    for phase in ("trough", "TROUGH", "Trough Watch", "Pre-Trough"):
        out = assemble_bottoming_watch([_row(phase=phase, slope=2.0)])
        assert out["bottoming_watch"] == [], f"{phase!r} must not pass the gate"


# ─────────────────────────────────── ordering + cap ───────────────────────────
def test_sorted_by_pos_ascending():
    """Deepest in the cycle low first."""
    rows = [_row(id_=f"b-{p}", pos=p, slope=1.0) for p in (18.6, 2.0, 12.3, 3.5)]
    out = assemble_bottoming_watch(rows)
    assert [r["pos"] for r in out["bottoming_watch"]] == [2.0, 3.5, 12.3, 18.6]


def test_unknown_pos_sorts_last_not_first():
    """A missing pos must not be treated as 0 and jump the queue."""
    out = assemble_bottoming_watch(
        [_row(id_="b-none", pos=None, slope=1.0), _row(id_="b-deep", pos=9.0, slope=1.0)]
    )
    assert _ids(out) == ["b-deep", "b-none"]


def test_cap_respected_and_disclosed():
    rows = [_row(id_=f"b-{i}", pos=float(i), slope=1.0) for i in range(20)]
    out = assemble_bottoming_watch(rows)
    assert len(out["bottoming_watch"]) == BOTTOMING_CAP == 8
    # the deepest 8 survive, in order
    assert _ids(out) == [f"b-{i}" for i in range(8)]
    # the truncation is disclosed, never silent
    assert any("capped" in n for n in out["notes"]), out["notes"]


def test_cap_is_overridable_and_no_note_when_nothing_dropped():
    rows = [_row(id_=f"b-{i}", pos=float(i), slope=1.0) for i in range(3)]
    out = assemble_bottoming_watch(rows, cap=2)
    assert len(out["bottoming_watch"]) == 2
    full = assemble_bottoming_watch(rows)
    assert full["notes"] == []


# ─────────────────────────────── FT-R1 dual read ──────────────────────────────
def test_dual_read_ids_match_across_the_b_prefix():
    """forward-log 'b-gold_miners' must find theme id 'gold_miners'."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", slope=1.3)],
        reduce_ids=["gold_miners", "housing", "crypto"],
    )
    assert set(out["dual_read_ids"]) == {"b-gold_miners", "gold_miners"}


def test_dual_read_excludes_non_reduce_rows():
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", pos=1.0, slope=1.3),
         _row(id_="b-us_sector_comm", pos=2.0, slope=2.7)],
        reduce_ids=["gold_miners"],
    )
    assert set(out["dual_read_ids"]) == {"b-gold_miners", "gold_miners"}
    assert "us_sector_comm" not in out["dual_read_ids"]


def test_sector_etf_row_has_no_theme_counterpart():
    """'xlu' must not dual-read against the theme id 'us_sector_utilities'."""
    out = assemble_bottoming_watch(
        [_row(id_="xlu", kind="sector", slope=1.3)],
        reduce_ids=["us_sector_utilities"],
    )
    assert out["dual_read_ids"] == []
    assert _ids(out) == ["xlu"]


def test_dual_read_empty_without_reduce_ids():
    out = assemble_bottoming_watch([_row(id_="b-gold_miners", slope=1.3)])
    assert out["dual_read_ids"] == []


def test_dual_read_ids_are_sorted_and_json_safe():
    out = assemble_bottoming_watch(
        [_row(id_="b-z", pos=1.0, slope=1.0), _row(id_="b-a", pos=2.0, slope=1.0)],
        reduce_ids=["z", "a"],
    )
    assert out["dual_read_ids"] == sorted(out["dual_read_ids"])
    json.dumps(out)  # must not raise


# ─────────────────────────── bilingual names (G0.5) ──────────────────────────
def test_name_zh_resolves_by_canonical_and_raw_id():
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", pos=1.0, slope=1.3, name="Gold Miners"),
         _row(id_="xlu", kind="sector", pos=2.0, slope=1.3, name="Utilities")],
        names_zh={"gold_miners": "黄金矿业", "xlu": "公用事业"},
    )
    assert [r["name_zh"] for r in out["bottoming_watch"]] == ["黄金矿业", "公用事业"]


def test_missing_name_zh_is_none_not_a_slug():
    """No zh name → None, so the template falls back to the English display name."""
    r = assemble_bottoming_watch([_row(id_="b-mystery", slope=1.0)])["bottoming_watch"][0]
    assert r["name_zh"] is None


def test_template_falls_back_to_english_when_name_zh_absent():
    src = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r"\nfunction botRow\(x\)\{(.*?)\n\}\n", src, re.S)
    assert m
    assert "x.name_zh||x.name" in m.group(1), (
        "botRow() must fall back to the English name when name_zh is absent"
    )


def test_canonical_id():
    assert canonical_id("b-gold_miners") == "gold_miners"
    assert canonical_id("xlc") == "xlc"
    assert canonical_id(None) == ""


# ──────────────────── BUY quote + trend-gate conflict flags ───────────────────
def test_buy_signal_is_quoted_and_gate_conflict_set():
    out = assemble_bottoming_watch([_row(signal="BUY", above200d=False, slope=1.3)])
    r = out["bottoming_watch"][0]
    assert r["cycle_signal"] == "BUY"
    assert r["gate_conflict"] is True


def test_buy_signal_above_trend_has_no_conflict():
    r = assemble_bottoming_watch(
        [_row(signal="BUY", above200d=True, slope=1.3)]
    )["bottoming_watch"][0]
    assert r["cycle_signal"] == "BUY"
    assert r["gate_conflict"] is False


def test_non_buy_signal_carries_no_cycle_signal():
    r = assemble_bottoming_watch(
        [_row(signal="SELL", above200d=False, slope=1.3)]
    )["bottoming_watch"][0]
    assert r["cycle_signal"] is None
    # no cycle turn was signalled, so there is no conflict to print
    assert r["gate_conflict"] is False


def test_unknown_above200d_does_not_fabricate_a_conflict():
    """None is UNKNOWN, not False — an unknown trend gate must not print 'gate shut'."""
    r = assemble_bottoming_watch(
        [_row(signal="BUY", above200d=None, slope=1.3)]
    )["bottoming_watch"][0]
    assert r["above200d"] is None
    assert r["gate_conflict"] is False


# ───────────────────────── empty log → empty lane + null ──────────────────────
def test_absent_log_yields_empty_lane_with_note():
    out = assemble_bottoming_watch(None)
    assert out["bottoming_watch"] == []
    assert out["dual_read_ids"] == []
    assert any("absent" in n for n in out["notes"]), out["notes"]


def test_empty_log_yields_empty_lane_without_absent_note():
    out = assemble_bottoming_watch([])
    assert out["bottoming_watch"] == []
    assert out["notes"] == []


def test_null_disclosure_always_present():
    """Honest null (G0.4) rides the payload whether or not the lane has rows."""
    for rows in (None, [], [_row(slope=1.0)]):
        auth = assemble_bottoming_watch(rows)["authority"]
        assert auth["null_disclosure_en"] == NULL_DISCLOSURE_EN
        assert auth["null_disclosure_zh"] == NULL_DISCLOSURE_ZH
        assert auth["null_disclosure_en"].strip()
        assert auth["null_disclosure_zh"].strip()


def test_authority_block_is_display_tier_with_zero_powers():
    """G0.1 — nothing in this lane may rank, gate, size, or escalate."""
    auth = assemble_bottoming_watch([_row(slope=1.0)])["authority"]
    assert auth["tier"] == "display"
    for k in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert auth[k] is False, k


def test_malformed_rows_are_skipped_not_fatal():
    out = assemble_bottoming_watch(["not a dict", None, 42, _row(slope=1.0)])
    assert len(out["bottoming_watch"]) == 1


# ───────────────────── never-buy-words discipline (display) ───────────────────
def test_contains_buy_word_detects_the_forward_log_vocabulary():
    assert contains_buy_word("FRESH BUY")
    assert contains_buy_word("BUY")
    assert contains_buy_word("clean entry")
    assert not contains_buy_word("COUNTERTREND BOUNCE")
    assert not contains_buy_word("cycle turn signal — watch only")
    assert not contains_buy_word(None)


def test_rendered_lane_copy_carries_no_buy_verb():
    """Every fixed string the lane renders must be watch vocabulary."""
    rendered = [
        "Bottoming watch", "cycle lows forming — watch, don't chase",
        "cycle turn signal — watch only", "below 200-day trend — gate shut",
        "no basing candidates tonight", "may be bottoming",
        NULL_DISCLOSURE_EN,
    ]
    for s in rendered:
        assert not contains_buy_word(s), f"buy verb in rendered copy: {s!r}"


def test_row_name_is_the_only_free_text_field_rendered():
    """`signal` and `timing_state` carry buy words — they must stay payload-only.

    This test pins WHY the fence exists: the real vocabulary of `timing_state`
    includes the literal value "FRESH BUY".
    """
    r = assemble_bottoming_watch(
        [_row(signal="BUY", timing="FRESH BUY", slope=1.0)]
    )["bottoming_watch"][0]
    assert contains_buy_word(r["timing_state"])
    assert contains_buy_word(r["signal"])
    assert set(DISPLAY_FORBIDDEN_FIELDS) == {"signal", "timing_state"}


@pytest.mark.parametrize("field", DISPLAY_FORBIDDEN_FIELDS)
def test_template_bottoming_row_never_renders_a_buy_word_field(field):
    """The fence is only real if the renderer actually omits these fields.

    Reads the shipped `botRow()` body out of the template. A future edit that
    prints `timing_state` ("FRESH BUY") on a watch-only lane fails here.
    """
    src = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r"\nfunction botRow\(x\)\{(.*?)\n\}\n", src, re.S)
    assert m, "botRow() not found in sector_central.html.j2 — did it get renamed?"
    body = m.group(1)
    assert f"x.{field}" not in body, (
        f"botRow() renders x.{field}, which carries buy-family words "
        f"(e.g. timing_state == 'FRESH BUY') onto a watch-only lane"
    )


def test_template_lane_declares_the_watch_caption_in_both_languages():
    src = TEMPLATE.read_text(encoding="utf-8")
    for s in ("Bottoming watch", "筑底观察",
              "cycle lows forming", "周期底部形成中",
              "cycle turn signal — watch only", "周期转折信号——仅观察",
              "below 200-day trend — gate shut", "低于200日趋势——闸门关闭",
              "no basing candidates tonight", "今晚无筑底候选",
              "may be bottoming", "或正筑底"):
        assert s in src, f"missing lane string: {s!r}"


def test_template_has_no_translated_title_attribute():
    """House law: no translated text in title= attributes (CI-guarded elsewhere;
    pinned here for the strings this lane adds)."""
    src = TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r"\nfunction botRow\(x\)\{(.*?)\n\}\n", src, re.S)
    assert m
    assert "title=" not in m.group(1)


# ──────────────────── G0.3 — the existing lanes stay untouched ────────────────
def test_assembler_never_mutates_the_reduce_lane_input():
    reduce_ids = ["gold_miners", "housing"]
    snapshot = list(reduce_ids)
    assemble_bottoming_watch([_row(id_="b-gold_miners", slope=1.3)], reduce_ids=reduce_ids)
    assert reduce_ids == snapshot


def test_wiring_leaves_buy_wait_reduce_membership_byte_identical():
    """G0.3 — the W-A wiring may only ADD keys to act_now.

    Replays exactly what scripts/build_baskets.py does to a real act_now payload
    and asserts the three pre-existing lanes are unchanged, member for member.
    """
    from engine.us_act_now import assemble_bottoming_watch as _asm

    act_now = {
        "buy": [{"id": "robotics_automation", "name": "Robotics", "score": 71}],
        "add_on_pullback": [{"id": "mag7", "name": "Mag 7", "score": 63}],
        "reduce": [{"id": "gold_miners", "name": "Gold Miners", "score": 31},
                   {"id": "crypto_rails", "name": "Crypto Rails", "score": 28}],
        "conflicted": [],
    }
    before = json.dumps(act_now, sort_keys=True)

    bw = _asm([_row(id_="b-gold_miners", pos=2.0, slope=1.3)],
              reduce_ids=[x["id"] for x in act_now["reduce"]])
    act_now["bottoming_watch"] = bw["bottoming_watch"]
    act_now["dual_read_ids"] = bw["dual_read_ids"]
    act_now["bottoming_authority"] = bw["authority"]

    after = {k: act_now[k] for k in ("buy", "add_on_pullback", "reduce", "conflicted")}
    assert json.dumps(after, sort_keys=True) == before
    # and the new keys really did land
    assert act_now["bottoming_watch"] and act_now["dual_read_ids"]


# ───────────────────── G0.2 — the live gold_miners receipt ────────────────────
def test_gold_miners_case_from_committed_log():
    """The §2 D9 case, reproduced from the real committed forward log.

    `b-gold_miners` on 2026-08-04: Trough, pos=2.0, osc_slope=+1.3, signal=BUY,
    above200d=False — the row the Act board buried on reduce/avoid.
    """
    pd = pytest.importorskip("pandas")
    p = ROOT / "data" / "sector_cycles" / "forward_log.parquet"
    if not p.exists():
        pytest.skip("forward_log.parquet not present in this checkout")
    df = pd.read_parquet(p)
    latest = df[df["date"] == df["date"].max()]
    rows = latest.to_dict(orient="records")

    out = assemble_bottoming_watch(rows, reduce_ids=["gold_miners", "crypto_rails"])
    by_id = {r["id"]: r for r in out["bottoming_watch"]}

    assert "b-gold_miners" in by_id, (
        "gold_miners must reach the bottoming lane — this is the whole point of W-A"
    )
    g = by_id["b-gold_miners"]
    assert g["name"] == "Gold Miners"
    assert g["cid"] == "gold_miners"
    assert g["kind"] == "BASKET"
    assert g["pos"] == pytest.approx(2.0)
    assert g["osc_slope"] == pytest.approx(1.3)
    assert g["cycle_signal"] == "BUY"
    assert g["above200d"] is False
    assert g["gate_conflict"] is True, "the D10 trend-gate conflict must be flagged"
    assert g["href"] == "basket/gold_miners.html"

    # deepest low first — gold_miners at pos=2.0 leads the lane
    assert out["bottoming_watch"][0]["id"] == "b-gold_miners"
    # and it dual-reads against its reduce/avoid row
    assert "gold_miners" in out["dual_read_ids"]

    # every row on the lane genuinely satisfies the gate
    for r in out["bottoming_watch"]:
        src = next(x for x in rows if str(x["id"]) == r["id"])
        assert src["phase"] == "Trough"
        assert float(src["osc_slope"]) > 0


def test_committed_log_rows_are_json_serializable():
    """pandas/numpy scalars must be coerced at the boundary or the artifact breaks."""
    pd = pytest.importorskip("pandas")
    p = ROOT / "data" / "sector_cycles" / "forward_log.parquet"
    if not p.exists():
        pytest.skip("forward_log.parquet not present in this checkout")
    df = pd.read_parquet(p)
    rows = df[df["date"] == df["date"].max()].to_dict(orient="records")
    out = assemble_bottoming_watch(rows, reduce_ids=["gold_miners"])
    json.dumps(out, ensure_ascii=False)  # must not raise
    for r in out["bottoming_watch"]:
        assert isinstance(r["pos"], (float, type(None)))
        assert isinstance(r["above200d"], (bool, type(None)))
        assert isinstance(r["gate_conflict"], bool)
