"""tests/test_us_act_now.py — US bottoming-watch lane assembler (W-A).

Pins the lane gate, the ordering, the cap, the FT-R1 dual-read id set, the
BUY-quote + trend-gate-conflict flags, the honest null, and the two display
fences that keep a WATCH lane free of buy verbs.

The live receipt (gate G0.2) is `test_gold_miners_case_from_committed_log`:
the real committed `data/sector_cycles/forward_log.parquet` row
`b-gold_miners: Trough, pos=2.0, osc_slope=+1.3, signal=BUY, above200d=False`
must land on the lane with its gate-shut conflict flagged.

Both committed-log receipts pin an EXPLICIT DATE, never `date.max()`. The first
cut of this file pinned the latest row and asserted gold_miners was on the lane;
when the cycle engine graduated it Trough→Recovery on 2026-08-05 the assertion
became false and the suite went red on unchanged code. A receipt for a transient
state must name the session it is a receipt for.

`test_gold_miners_graduation_case_from_committed_log` is that graduation, pinned
as the receipt for the opposite half: off the lane, and carrying the recovering
chip instead.

DISPLAY REGRESSION (#4642): no US template renders this lane any more. The
template tests here used to pin sector_central's client renderer by function name
(botRow/actRow); #4642 deleted that renderer when it transplanted the shared
server-rendered act board, and its replacement ships no bottoming lane. The
display fences survive as `test_surface_*`, parametrised over
`_us_bottoming_surfaces()` so they cover the shipped board today and arm
themselves against a restored lane automatically. See the DISPLAY REGRESSION
block further down for the full record.
"""
from __future__ import annotations

import json
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
    RECOVERING_CHIP_EN,
    RECOVERING_CHIP_ZH,
    RECOVERING_DISCLOSURE_EN,
    RECOVERING_DISCLOSURE_ZH,
    RECOVERING_POS_MAX,
    RECOVERING_TIP_EN,
    RECOVERING_TIP_ZH,
    assemble_bottoming_watch,
    canonical_id,
    contains_buy_word,
)

TEMPLATES = ROOT / "templates"

# The US act board's home since #4642. Before it, sector_central.html.j2 carried a
# client-side renderer (renderActBoard/actRow/actLane/botRow) that these template
# tests pinned by function name; #4642 replaced it with this shared, server-rendered
# include and deleted the client renderer outright. See the DISPLAY REGRESSION note
# above `test_the_bottoming_payload_is_built_but_no_us_surface_renders_it`.
ACT_BOARD = TEMPLATES / "_us_act_now_board.html.j2"


def _us_bottoming_surfaces() -> list[Path]:
    """Every US template the bottoming-watch payload could reach.

    Always includes the shipped act board, so the display fences below can never
    degrade into a vacuous zero-case parametrisation, and picks up any other US
    template that starts rendering the payload — the fences then arm themselves
    against the restored lane without anyone remembering to re-point them.

    China is excluded on purpose: `_china_act_now_board.html.j2` renders its own
    bottoming lane and is fenced by the China suite.
    """
    found = {ACT_BOARD}
    for path in sorted(TEMPLATES.glob("*.j2")):
        if "china" in path.name:
            continue
        src = path.read_text(encoding="utf-8")
        if "bottoming_watch" in src or "botRow" in src:
            found.add(path)
    return sorted(found)


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


@pytest.mark.parametrize("surface", _us_bottoming_surfaces(), ids=lambda p: p.name)
def test_surface_falls_back_to_english_when_name_zh_absent(surface):
    """Bilingual law: an absent zh name renders the English one, never a blank.

    Was pinned on botRow()'s `x.name_zh||x.name`; the shipped board expresses the
    same law as `(x.name_zh or x.name)`. Counted rather than merely searched — a
    single guarded occurrence must not vouch for an unguarded one added later.
    """
    src = surface.read_text(encoding="utf-8")
    total = src.count("name_zh")
    assert total, f"{surface.name} renders no zh name at all"
    guarded = src.count("name_zh or ") + src.count("name_zh||")
    assert guarded == total, (
        f"{surface.name} has {total - guarded} zh-name reference(s) with no "
        f"English fallback — an absent name_zh would render blank"
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


@pytest.mark.parametrize("surface", _us_bottoming_surfaces(), ids=lambda p: p.name)
@pytest.mark.parametrize("field", DISPLAY_FORBIDDEN_FIELDS)
def test_surface_never_renders_a_buy_word_field(field, surface):
    """The fence is only real if the renderer actually omits these fields.

    `timing_state`'s real vocabulary includes the literal "FRESH BUY" and `signal`
    is "BUY" — printing either on a watch-only lane puts a buy verb on a surface
    that must carry none. Armed against the shipped board so that a restored
    bottoming lane inherits the fence rather than having to re-earn it.
    """
    src = surface.read_text(encoding="utf-8")
    for access in (f".{field}", f"get('{field}')", f'get("{field}")'):
        assert access not in src, (
            f"{surface.name} renders {access}, which carries buy-family words "
            f"(e.g. timing_state == 'FRESH BUY') onto a watch-only lane"
        )


def test_lane_copy_is_declared_bilingually_by_the_engine():
    """The lane's fixed copy must exist in both languages before anything renders it.

    Was pinned as literal strings inside sector_central's botRow()/actLane() calls.
    #4642 deleted that renderer, so the copy is pinned where it is now authored —
    the engine's authority block, which is the single source the page must quote
    (`test_recovering_copy_ships_from_the_engine_authority_block`).
    """
    auth = assemble_bottoming_watch([_row(slope=1.0)])["authority"]
    for en, zh in ((NULL_DISCLOSURE_EN, NULL_DISCLOSURE_ZH),
                   (RECOVERING_CHIP_EN, RECOVERING_CHIP_ZH),
                   (RECOVERING_TIP_EN, RECOVERING_TIP_ZH),
                   (RECOVERING_DISCLOSURE_EN, RECOVERING_DISCLOSURE_ZH)):
        assert en.strip() and zh.strip()
        assert zh != en, "zh copy must actually be translated"
    assert auth["null_disclosure_en"] == NULL_DISCLOSURE_EN


@pytest.mark.parametrize("surface", _us_bottoming_surfaces(), ids=lambda p: p.name)
def test_surface_has_no_translated_title_attribute(surface):
    """House law: no translated text in title= attributes — hover copy ships as
    data-tip-en/data-tip-zh so the language switch can reach it."""
    src = surface.read_text(encoding="utf-8")
    assert "title=" not in src, (
        f"{surface.name} carries a title= attribute; use data-tip-en/data-tip-zh"
    )


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
def _committed_rows(date_str: str) -> list[dict]:
    """Rows of the committed forward log for ONE named session.

    Deliberately not `date.max()`: these receipts pin transient states, so they
    must name their session or they expire the next time the engine moves.
    """
    pd = pytest.importorskip("pandas")
    p = ROOT / "data" / "sector_cycles" / "forward_log.parquet"
    if not p.exists():
        pytest.skip("forward_log.parquet not present in this checkout")
    df = pd.read_parquet(p)
    sel = df[df["date"].astype(str).str.startswith(date_str)]
    if sel.empty:
        pytest.skip(f"forward log has no {date_str} session in this checkout")
    return sel.to_dict(orient="records")


def test_gold_miners_case_from_committed_log():
    """The §2 D9 case, reproduced from the real committed forward log.

    `b-gold_miners` on 2026-08-04: Trough, pos=2.0, osc_slope=+1.3, signal=BUY,
    above200d=False — the row the Act board buried on reduce/avoid.
    """
    rows = _committed_rows("2026-08-04")

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
    assert all(isinstance(i, str) for i in out["recovering_ids"])


# ═════════════ the graduation gap — reduce/avoid rows on NO lane ══════════════
# The cycle engine graduates a basket Trough→Recovery the session its phase
# turns, so it leaves the lane at once. The Act board's momentum label keeps it
# on reduce/avoid until its 20d relative flips positive. Between those two events
# the basket sits on no lane at all. These pin the bridge.

def test_recovering_row_on_the_reduce_lane_is_chipped():
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["gold_miners"],
    )
    assert out["bottoming_watch"] == [], "a graduated row must NOT be on the lane"
    assert set(out["recovering_ids"]) == {"b-gold_miners", "gold_miners"}


def test_recovering_requires_the_row_to_be_on_the_reduce_lane():
    """The chip exists to un-bury a reduce/avoid row. No reduce row, no chip."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["housing"],
    )
    assert out["recovering_ids"] == []


def test_recovering_requires_a_rising_oscillator():
    for slope in (-1.5, 0.0):
        out = assemble_bottoming_watch(
            [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=slope)],
            reduce_ids=["gold_miners"],
        )
        assert out["recovering_ids"] == [], f"slope={slope} must not chip"


def test_recovering_unknown_slope_is_not_rising():
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=None)],
        reduce_ids=["gold_miners"],
    )
    assert out["recovering_ids"] == []


def test_recovering_respects_the_position_fence():
    """`Recovery` spans pos 2.3→31.9 on one night. The chip says "recovering from
    cycle low", so it may only fire while the row is still AT the low."""
    inside = assemble_bottoming_watch(
        [_row(id_="b-a", phase="Recovery", pos=RECOVERING_POS_MAX, slope=1.0)],
        reduce_ids=["a"],
    )
    outside = assemble_bottoming_watch(
        [_row(id_="b-a", phase="Recovery", pos=RECOVERING_POS_MAX + 0.1, slope=1.0)],
        reduce_ids=["a"],
    )
    assert set(inside["recovering_ids"]) == {"b-a", "a"}, "the fence is inclusive"
    assert outside["recovering_ids"] == []


def test_recovering_unknown_pos_cannot_claim_the_low():
    """A missing position must never manufacture the claim the chip's copy makes."""
    out = assemble_bottoming_watch(
        [_row(id_="b-a", phase="Recovery", pos=None, slope=1.0)], reduce_ids=["a"]
    )
    assert out["recovering_ids"] == []


def test_recovering_phase_match_is_exact():
    for phase in ("recovery", "RECOVERY", "Recovering", "Trough"):
        out = assemble_bottoming_watch(
            [_row(id_="b-a", phase=phase, pos=2.0, slope=1.0)], reduce_ids=["a"]
        )
        assert out["recovering_ids"] == [], f"phase={phase!r} must not chip"


def test_recovering_matches_a_sector_etf_without_the_b_prefix():
    out = assemble_bottoming_watch(
        [_row(id_="xlc", phase="Recovery", pos=6.7, slope=5.0, kind="sector")],
        reduce_ids=["xlc"],
    )
    assert out["recovering_ids"] == ["xlc"]


def test_recovering_ids_are_sorted_and_json_safe():
    out = assemble_bottoming_watch(
        [_row(id_="b-z", phase="Recovery", pos=1.0, slope=1.0),
         _row(id_="b-a", phase="Recovery", pos=2.0, slope=1.0)],
        reduce_ids=["z", "a"],
    )
    assert out["recovering_ids"] == sorted(out["recovering_ids"])
    json.dumps(out, ensure_ascii=False)


def test_recovering_note_counts_names_not_id_spellings():
    """A basket contributes two spellings ('b-x','x'), a sector ETF one."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5),
         _row(id_="xlc", phase="Recovery", pos=6.7, slope=5.0, kind="sector")],
        reduce_ids=["gold_miners", "xlc"],
    )
    assert any("recovering-from-low chips: 2" in n for n in out["notes"]), out["notes"]


# ── the two id sets must never be confused for one another ───────────────────
def test_dual_read_and_recovering_sets_are_disjoint():
    """FT-R1's chip says "also on Bottoming watch". The recovering chip fires for
    rows that are on NO lane. A row in both sets would render a false sentence."""
    out = assemble_bottoming_watch(
        [_row(id_="b-uranium_miners", phase="Trough", pos=0.8, slope=0.4),
         _row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["uranium_miners", "gold_miners"],
    )
    assert set(out["dual_read_ids"]) == {"b-uranium_miners", "uranium_miners"}
    assert set(out["recovering_ids"]) == {"b-gold_miners", "gold_miners"}
    assert not set(out["dual_read_ids"]) & set(out["recovering_ids"])


def test_dual_read_ids_stay_a_subset_of_the_lane_and_recovering_never_joins_it():
    """The invariant every consumer of `dual_read_ids` relies on."""
    out = assemble_bottoming_watch(
        [_row(id_="b-uranium_miners", phase="Trough", pos=0.8, slope=0.4),
         _row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["uranium_miners", "gold_miners"],
    )
    lane = {r["id"] for r in out["bottoming_watch"]} | {
        r["cid"] for r in out["bottoming_watch"]
    }
    assert set(out["dual_read_ids"]) <= lane
    assert not set(out["recovering_ids"]) & lane


def test_recovering_ids_present_even_when_the_lane_is_empty():
    """The whole point: the lane can be empty while a graduated row still needs
    its chip. An absent key here would be the re-blindness this closes."""
    out = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=["gold_miners"],
    )
    assert out["bottoming_watch"] == []
    assert out["recovering_ids"]


@pytest.mark.parametrize("rows", [None, []])
def test_recovering_ids_is_always_a_list(rows):
    assert assemble_bottoming_watch(rows)["recovering_ids"] == []


def test_recovering_assembler_never_mutates_the_reduce_lane_input():
    reduce_ids = ["gold_miners", "housing"]
    snapshot = list(reduce_ids)
    assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5)],
        reduce_ids=reduce_ids,
    )
    assert reduce_ids == snapshot


# ── the graduation receipt (the case this bridge was built for) ───────────────
def test_gold_miners_graduation_case_from_committed_log():
    """`b-gold_miners` on 2026-08-05: Trough→Recovery, pos=2.3, osc_slope=+1.5,
    signal=BUY, above200d=False.

    The session it left the lane. Its board row still read `deteriorating/avoid`
    (20d relative −8.14%), so without the chip it sat on no lane at all.
    """
    rows = _committed_rows("2026-08-05")
    src = next(r for r in rows if str(r["id"]) == "b-gold_miners")
    assert src["phase"] == "Recovery", "fixture drift — this pins the graduation"
    assert float(src["pos"]) == pytest.approx(2.3)
    assert float(src["osc_slope"]) == pytest.approx(1.5)
    assert str(src["signal"]).upper() == "BUY"
    assert bool(src["above200d"]) is False

    out = assemble_bottoming_watch(rows, reduce_ids=["gold_miners", "crypto_rails"])

    # it has LEFT the lane — the CN-faithful gate is untouched by this bridge
    assert "b-gold_miners" not in {r["id"] for r in out["bottoming_watch"]}
    # ...and the chip is what now carries it
    assert "gold_miners" in out["recovering_ids"]
    assert "b-gold_miners" in out["recovering_ids"]
    # the lane itself still works on the same night
    assert "b-uranium_miners" in {r["id"] for r in out["bottoming_watch"]}


def test_committed_graduation_keeps_the_two_chip_sets_disjoint():
    """Belt-and-braces on the real night both chips were live."""
    out = assemble_bottoming_watch(
        _committed_rows("2026-08-05"),
        reduce_ids=["gold_miners", "uranium_miners", "crypto_rails"],
    )
    assert set(out["dual_read_ids"]) & set(out["recovering_ids"]) == set()
    # uranium_miners is Trough+rising and on reduce → the FT-R1 chip
    assert "uranium_miners" in out["dual_read_ids"]
    # gold_miners graduated → the recovering chip
    assert "gold_miners" in out["recovering_ids"]


# ── never-buy words + bilingual law for the new copy ──────────────────────────
def test_recovering_copy_carries_no_buy_verb():
    for s in (RECOVERING_CHIP_EN, RECOVERING_TIP_EN, RECOVERING_DISCLOSURE_EN):
        assert not contains_buy_word(s), f"buy verb in rendered copy: {s!r}"


def test_recovering_copy_is_bilingual_and_non_empty():
    for en, zh in ((RECOVERING_CHIP_EN, RECOVERING_CHIP_ZH),
                   (RECOVERING_TIP_EN, RECOVERING_TIP_ZH),
                   (RECOVERING_DISCLOSURE_EN, RECOVERING_DISCLOSURE_ZH)):
        assert en.strip() and zh.strip()
        assert zh != en, "zh copy must actually be translated"


def test_recovering_copy_uses_no_house_jargon_or_raw_slugs():
    """Glance-tier vocabulary law: no internal state names, no raw slugs."""
    banned = ("Trough", "Recovery", "osc_slope", "forward_log", "phase==",
              "FT-R1", "W-A", "pos<=", "b-")
    for s in (RECOVERING_CHIP_EN, RECOVERING_TIP_EN, RECOVERING_DISCLOSURE_EN):
        for b in banned:
            assert b not in s, f"house jargon {b!r} in user copy: {s!r}"


def test_recovering_copy_ships_from_the_engine_authority_block():
    """The page must not carry its own wording — one source, no drift."""
    auth = assemble_bottoming_watch([])["authority"]
    assert auth["recovering_chip_en"] == RECOVERING_CHIP_EN
    assert auth["recovering_chip_zh"] == RECOVERING_CHIP_ZH
    assert auth["recovering_tip_en"] == RECOVERING_TIP_EN
    assert auth["recovering_tip_zh"] == RECOVERING_TIP_ZH
    assert auth["recovering_disclosure_en"] == RECOVERING_DISCLOSURE_EN
    assert auth["recovering_disclosure_zh"] == RECOVERING_DISCLOSURE_ZH


def test_recovering_tip_does_not_claim_bottoming_lane_membership():
    """The defect this design avoids: FT-R1's tip says "also on Bottoming watch".
    These rows are on no lane, so that sentence would send the reader to a lane
    the name has left."""
    assert "Bottoming watch" not in RECOVERING_TIP_EN
    assert "筑底观察" not in RECOVERING_TIP_ZH


# ── DISPLAY REGRESSION: the US bottoming lane has no renderer ────────────────
#
# #4642 ("transplant the V2 five-lane action board onto US Sector Intelligence")
# replaced sector_central's client-rendered act board with the shared server-
# rendered templates/_us_act_now_board.html.j2. Its summary describes the board it
# deleted as "the client-rendered 4-lane themes-only board" — but the deleted code
# ran FIVE actLane() calls: buy, wait, trim, avoid, AND bottom. The replacement
# board has no bottoming lane (`grep -c bottoming templates/_us_act_now_board.html.j2`
# → 0), so the W-A lane shipped by #4599 and amended by #4614 is DARK on the US
# site while engine/us_act_now.py and scripts/build_baskets.py still compute and
# ship its payload. China's board (`_china_act_now_board.html.j2`) still renders
# its equivalent lane, so this is a US-only display loss.
#
# The four tests that used to live here pinned that deleted renderer by function
# name (actRow's BOT_REC chip, its one-chip-per-row gate, its footnote wiring).
# They are replaced by the payload-liveness pin below plus the surface fences
# above, which arm themselves against whatever renders the lane next. Restoring
# the lane is a product decision with its own owner, not a CI heal — see the PR
# that healed this suite.

def test_the_bottoming_payload_is_built_but_no_us_surface_renders_it():
    """Records the #4642 display regression and keeps the restore path alive.

    The loss is display-only: the assembler still runs and the builder still
    writes every key a renderer would need. If this test starts failing because
    the BUILDER stopped writing them, the lane is no longer merely dark — the
    data is gone too, and the restore is a rebuild rather than a re-render.
    """
    src = (ROOT / "scripts" / "build_baskets.py").read_text(encoding="utf-8")
    for key in ("bottoming_watch", "dual_read_ids", "recovering_ids",
                "bottoming_authority"):
        assert f'_an_ba["{key}"] = _bw[' in src, (
            f"build_baskets stopped shipping act_now[{key!r}] — the US bottoming "
            f"lane's payload is now gone, not just unrendered"
        )
    # and the assembler still produces them
    out = assemble_bottoming_watch([_row(slope=1.0)])
    assert set(out) >= {"bottoming_watch", "dual_read_ids", "recovering_ids",
                        "authority"}


def test_the_recovering_chip_copy_is_still_shipped_for_a_future_renderer():
    """The chip's words ship from the engine so a page cannot drift from the
    measured basis. Pinned at the authority block — the source a restored
    renderer must quote — now that no template carries the wording."""
    auth = assemble_bottoming_watch([])["authority"]
    for key in ("recovering_chip_en", "recovering_chip_zh",
                "recovering_tip_en", "recovering_tip_zh",
                "recovering_disclosure_en", "recovering_disclosure_zh"):
        assert auth[key].strip(), f"engine stopped shipping {key}"


def test_the_recovering_and_dual_read_sets_stay_disjoint():
    """The one-chip-per-row guarantee, pinned at its source.

    actRow() used to enforce it in the renderer (`!x._conflicted && !BOT_DUAL.has`);
    with the renderer gone the guarantee lives where it is actually decided — the
    assembler, which never puts an id in both sets (engine/us_act_now.py:
    `recovering_ids ∩ bottoming_watch = ∅`).
    """
    bw = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5),
         _row(id_="b-uranium_miners", phase="Trough", pos=0.8, slope=0.4)],
        reduce_ids=["gold_miners", "uranium_miners"],
    )
    assert bw["recovering_ids"] and bw["dual_read_ids"]
    assert not (set(bw["recovering_ids"]) & set(bw["dual_read_ids"])), (
        "an id in both sets would render two chips on one row"
    )
    on_lane = {r["id"] for r in bw["bottoming_watch"]}
    assert not (set(bw["recovering_ids"]) & on_lane), (
        "a recovering id must have LEFT the bottoming lane"
    )


def test_wiring_adds_recovering_ids_without_touching_the_other_lanes():
    """G0.3 — the bridge may only ADD a key."""
    act_now = {
        "buy": [{"id": "robotics_automation", "name": "Robotics", "score": 71}],
        "add_on_pullback": [{"id": "mag7", "name": "Mag 7", "score": 63}],
        "reduce": [{"id": "gold_miners", "name": "Gold Miners", "score": 34},
                   {"id": "uranium_miners", "name": "Uranium", "score": 36}],
        "conflicted": [],
    }
    before = json.dumps(act_now, sort_keys=True)
    bw = assemble_bottoming_watch(
        [_row(id_="b-gold_miners", phase="Recovery", pos=2.3, slope=1.5),
         _row(id_="b-uranium_miners", phase="Trough", pos=0.8, slope=0.4)],
        reduce_ids=[x["id"] for x in act_now["reduce"]],
    )
    act_now["bottoming_watch"] = bw["bottoming_watch"]
    act_now["dual_read_ids"] = bw["dual_read_ids"]
    act_now["recovering_ids"] = bw["recovering_ids"]
    act_now["bottoming_authority"] = bw["authority"]

    after = {k: act_now[k] for k in ("buy", "add_on_pullback", "reduce", "conflicted")}
    assert json.dumps(after, sort_keys=True) == before
    assert act_now["recovering_ids"] and act_now["dual_read_ids"]


def test_build_wiring_ships_the_recovering_key():
    """The engine key is inert unless the builder actually writes it."""
    src = (ROOT / "scripts" / "build_baskets.py").read_text(encoding="utf-8")
    assert '_an_ba["recovering_ids"] = _bw["recovering_ids"]' in src
